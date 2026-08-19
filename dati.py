"""
dati.py - Caricamento, download e accesso al Lista_Finale_Master.csv.

Unico punto in cui si legge o si scrive il listone. Nessuna dipendenza da
Telegram: si puo' provare da riga di comando.
"""

import os
import re
import html
import unicodedata
import threading

import pandas as pd
import requests

import config

_cache = None
_lock = threading.Lock()

COLONNE_ATTESE = ['Nome', 'R', 'Squadra', 'Qt.A', 'FVM', 'Prezzo',
                  'Pv', 'Mv', 'Fm', 'Gf', 'Ass', 'Amm', 'Esp', 'Rc',
                  'PvTot', 'Tit', 'Min', 'GareSaltate', 'Infortunio']


def num(valore, default=0.0):
    """Converte in numero qualunque cosa arrivi dal CSV, senza esplodere."""
    n = pd.to_numeric(str(valore).replace(',', '.'), errors='coerce')
    return default if pd.isna(n) else float(n)


def normalizza(testo):
    if pd.isna(testo):
        return ""
    testo = unicodedata.normalize('NFKD', str(testo)).encode('ASCII', 'ignore').decode('utf-8')
    return " ".join(re.sub(r"[^\w\s]", "", testo).lower().split())


# ----------------------------------------------------------------------
# DOWNLOAD
# ----------------------------------------------------------------------
def scarica_master():
    """Scarica il Master da GitHub. Non tocca la cache (niente ricorsione)."""
    print("🔄 Download del Listone Master...")
    try:
        risposta = requests.get(
            config.LISTONE_URL,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15
        )
        if risposta.status_code == 200 and risposta.content:
            # GitHub in errore risponde 200 con una pagina HTML: senza questo
            # controllo la pagina finiva scritta sopra il listone buono.
            prima_riga = risposta.content[:400].decode('utf-8', 'ignore').splitlines()[0]
            if 'Nome' not in prima_riga or ';' not in prima_riga:
                print("❌ Il file scaricato non sembra il Master: listone precedente intatto.")
                return False

            if os.path.exists(config.FILE_MASTER):
                try:
                    os.replace(config.FILE_MASTER, config.FILE_BACKUP)
                except Exception:
                    pass
            with open(config.FILE_MASTER, "wb") as f:
                f.write(risposta.content)
            print("✅ Listone Master scaricato.")
            return True
        print(f"❌ Download fallito (HTTP {risposta.status_code}).")
    except Exception as e:
        print(f"❌ Errore durante il download: {e}")
    return False


# ----------------------------------------------------------------------
# CARICAMENTO
# ----------------------------------------------------------------------
def carica(forza=False):
    """Restituisce il DataFrame del Master, scaricandolo se manca."""
    global _cache
    with _lock:
        if _cache is not None and not forza:
            return _cache

        if not os.path.exists(config.FILE_MASTER):
            print("❌ Master assente: provo a scaricarlo...")
            if not scarica_master():
                print("❌ Nessun dato disponibile.")
                return None

        try:
            try:
                df = pd.read_csv(config.FILE_MASTER, sep=';', on_bad_lines='skip')
            except Exception:
                df = pd.read_csv(config.FILE_MASTER, sep=',', on_bad_lines='skip')

            if 'Nome' not in df.columns:
                print("⚠️ Il file non ha intestazioni valide.")
                return None

            df['Nome'] = df['Nome'].astype(str).str.strip()
            df['R'] = df['R'].astype(str).str.strip().str.upper()
            df = df[df['R'].isin(['P', 'D', 'C', 'A'])].reset_index(drop=True)

            mancanti = [c for c in COLONNE_ATTESE if c not in df.columns]
            if mancanti:
                print(f"⚠️ Colonne assenti nel Master: {', '.join(mancanti)}")

            _cache = df
            print(f"✅ Master caricato: {len(df)} giocatori.")
            return _cache
        except Exception as e:
            print(f"❌ Errore lettura Master: {e}")
            return None


def salva_da_dataframe(nuovo):
    """
    Sovrascrive il Master mettendo al sicuro quello precedente.
    Rifiuta i file senza le colonne obbligatorie.
    """
    mancanti = [c for c in config.COLONNE_OBBLIGATORIE if c not in nuovo.columns]
    if mancanti or nuovo.empty:
        return False, mancanti or ['(file vuoto)']

    if os.path.exists(config.FILE_MASTER):
        try:
            os.replace(config.FILE_MASTER, config.FILE_BACKUP)
        except Exception:
            pass

    nuovo.to_csv(config.FILE_MASTER, sep=';', index=False)
    carica(forza=True)
    return True, []


# ----------------------------------------------------------------------
# ACCESSO
# ----------------------------------------------------------------------
def cerca_giocatore(nome, df):
    """Match esatto, poi normalizzato, poi parziale sul cognome."""
    if df is None or df.empty or not nome:
        return None

    esatto = df[df['Nome'].astype(str) == str(nome).strip()]
    if not esatto.empty:
        return esatto.iloc[0]

    chiave = normalizza(nome)
    normalizzati = df['Nome'].apply(normalizza)
    uguali = df[normalizzati == chiave]
    if not uguali.empty:
        return uguali.iloc[0]

    parziali = df[normalizzati.str.contains(re.escape(chiave), na=False)] if chiave else df.iloc[0:0]
    return parziali.iloc[0] if not parziali.empty else None


def disponibili(df, session):
    """Esclude chi e' gia' in rosa o e' stato scartato."""
    if df is None or df.empty:
        return df
    presi = {p['nome'] for p in session.get('rosa', [])} | set(session.get('scartati', []))
    return df[~df['Nome'].isin(presi)]


def stato_rosa(session):
    rosa = session.get('rosa', [])
    conteggi = {r: 0 for r in config.SLOT_PER_RUOLO}
    for p in rosa:
        ruolo = p.get('ruolo', 'C')
        if ruolo in conteggi:
            conteggi[ruolo] += 1

    slot_liberi = max(0, config.ROSA_COMPLETA - len(rosa))
    budget = session.get('budget', 0)
    max_offerta = max(0, budget - (slot_liberi - 1)) if slot_liberi > 0 else budget
    return {'counts': conteggi, 'slot_liberi': slot_liberi, 'max_bid': max_offerta}


# ----------------------------------------------------------------------
# PREZZO: unico punto di verita'
# ----------------------------------------------------------------------
def prezzo_consigliato(riga, session):
    """
    Parte dalla colonna Prezzo del Master (tarata sulla lega di riferimento)
    e la riscala su budget e partecipanti della lega dell'utente.
    """
    if riga is None:
        return 1
    dati = riga if isinstance(riga, dict) else riga.to_dict()

    prezzo = num(dati.get('Prezzo'))
    if prezzo <= 0:
        fvm = num(dati.get('FVM'))
        quota = config.QUOTE_FALLBACK.get(str(dati.get('R', '')).upper(), 0.50)
        prezzo = fvm * quota

    budget = session.get('lega_budget_iniziale', config.BUDGET_DEFAULT)
    partecipanti = session.get('lega_partecipanti', config.PARTECIPANTI_DEFAULT)
    fattore = 1 + ((partecipanti - config.LEGA_RIFERIMENTO_SQUADRE) * config.FATTORE_PARTECIPANTE)
    return max(1, int(prezzo * (budget / config.LEGA_RIFERIMENTO_BUDGET) * fattore))


def icona_squadra(squadra):
    return config.TEAM_COLORS.get(str(squadra).strip(), config.ICONA_SQUADRA_DEFAULT)


def scudo(testo):
    return html.escape(str(testo))


if __name__ == "__main__":
    df = carica()
    if df is not None:
        print(df[['Nome', 'R', 'Squadra', 'Prezzo']].head().to_string(index=False))
        sessione = {'rosa': [], 'scartati': [], 'lega_budget_iniziale': 500, 'lega_partecipanti': 8}
        print("Prezzo primo giocatore:", prezzo_consigliato(df.iloc[0], sessione))