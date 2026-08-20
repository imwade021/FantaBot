"""
pronostici.py - I giocatori che costano poco e possono rendere molto.

Per mesi questo modulo non si poteva scrivere, perche' le colonne Min e Tit
erano vuote: senza i minuti, chi ha giocato quindici partite intere e chi e'
entrato quindici volte al novantesimo sono lo stesso identico giocatore. E
dedurre il motivo delle poche presenze, senza il dato, significa inventarlo.

Adesso i minuti ci sono, e permettono di separare tre situazioni che hanno
prezzi simili e futuri opposti:

  - chi ENTRAVA E FACEVA: pochi minuti ma tanti bonus quando era in campo.
    Se quest'anno parte titolare, i numeri si moltiplicano.
  - chi si e' ROTTO: titolare quando stava bene, mezza stagione ai box.
    Il prezzo lo sconta, il rendimento no.
  - chi GIOCAVA SEMPRE in una squadra che segnava poco: nessun bonus, ma
    minuti garantiti. Vale nelle leghe col modificatore, dove conta il voto.

Regola che vale su tutto: si scrivono FATTI. Se il dato non dice perche' uno
ha giocato poco, il bot non lo scrive.

ATTENZIONE ALLE DUE FONTI. Minuti e partite da titolare arrivano da
API-Football e contano TUTTE le competizioni: campionato, coppe, e anche il
campionato precedente di chi e' arrivato dall'estero. Presenze, voto,
fantamedia, gol e assist arrivano invece dal file ufficiale del Fantacalcio e
riguardano SOLO la Serie A.

Mescolarle produce assurdita': su 156 giocatori, 46 risultavano "titolari piu'
volte di quante volte sono scesi in campo", e Wesley usciva con 49 partite da
titolare in un campionato che ne ha 38. Peggio ancora, dividere i gol di Serie
A per i minuti di tutte le competizioni sottostima chiunque giochi le coppe.

Quindi ognuna si usa solo dentro il suo mondo: i minuti dicono SE uno era
titolare o subentrante, i numeri del Fantacalcio dicono QUANTO rendeva. Non si
fa mai una frazione con un pezzo di ciascuno.
"""

import pandas as pd

import consiglio

PARTITE_STAGIONE = 38
MINUTI_PARTITA = 90

# Sotto questa media di minuti si e' un subentrante, non un titolare.
MINUTI_DA_TITOLARE = 65
# Quante gare saltate per infortunio fanno di una stagione una stagione persa.
STOP_RILEVANTE = 8
# Un pronostico ha senso solo se costa poco: sopra, il mercato lo ha gia' visto.
PREZZO_MASSIMO = 20
# Sotto questi minuti totali non si conclude niente: il campione e' troppo corto.
MINUTI_MINIMI = 270


def _num(valore, predefinito=0.0):
    convertito = pd.to_numeric(valore, errors='coerce')
    return predefinito if pd.isna(convertito) else float(convertito)


def profilo(riga):
    """
    Come ha giocato davvero, non quante volte e' sceso in campo.

    La differenza fra presenze e minuti e' tutto: 27 presenze possono essere
    27 partite intere o 27 spezzoni da dieci minuti, e sono due giocatori
    diversi che il listino prezza uguale.
    """
    presenze = _num(riga.get('Pv'))                 # Serie A
    gol = _num(riga.get('Gf'))                      # Serie A
    assist = _num(riga.get('Ass'))                  # Serie A
    minuti = _num(riga.get('Min'))                  # tutte le competizioni
    titolare = _num(riga.get('Tit'))                # tutte le competizioni

    # Le presenze di riferimento per i minuti devono essere dello stesso mondo
    # dei minuti, altrimenti si divide per il numero sbagliato.
    presenze_totali = _num(riga.get('PvTot'))
    if presenze_totali <= 0:
        presenze_totali = max(presenze, titolare)

    return {
        'presenze': int(presenze),
        'presenze_totali': int(presenze_totali),
        'minuti': int(minuti),
        'da_titolare': int(titolare),
        # quanto stava in campo, sul totale delle sue partite
        'minuti_a_partita': round(minuti / presenze_totali, 1) if presenze_totali else 0.0,
        'quota_titolare': round(min(1.0, titolare / presenze_totali), 2) if presenze_totali else 0.0,
        # quanto rendeva, misurato solo in Serie A
        'bonus': int(gol + assist),
        'bonus_per_presenza': round((gol + assist) / presenze, 2) if presenze else 0.0,
        # La resa vera: i bonus rapportati ai novantesimi realmente giocati.
        # Per presenza tre subentrati diversi davano lo stesso identico 0.38 e
        # non si potevano ordinare; per novanta minuti si distinguono.
        'bonus_per_90': round((gol + assist) / (minuti / MINUTI_PARTITA), 2) if minuti else 0.0,
        'gare_saltate': int(_num(riga.get('GareSaltate'))),
        'dati_sufficienti': minuti >= MINUTI_MINIMI and presenze >= 8,
    }


def forza_squadre(df, presenze_minime=15):
    """
    Quanto rende, in media, un giocatore di quella squadra in quel ruolo.

    E' il miglior pronostico disponibile per chi in Serie A non ha ancora
    giocato: un centrocampista appena arrivato all'Inter eredita la media dei
    centrocampisti dell'Inter. Non e' una certezza, ma non e' nemmeno
    un'invenzione: e' il contesto in cui giochera'.
    """
    lavoro = df.copy()
    lavoro['_pv'] = pd.to_numeric(lavoro['Pv'], errors='coerce').fillna(0)
    lavoro['_fm'] = pd.to_numeric(lavoro['Fm'], errors='coerce').fillna(0)
    lavoro['_ruolo'] = lavoro['R'].astype(str).str.upper().str[:1]

    solidi = lavoro[(lavoro['_pv'] >= presenze_minime) & (lavoro['_fm'] > 0)]
    per_squadra_ruolo = solidi.groupby(['Squadra', '_ruolo'])['_fm'].mean().round(2)
    per_ruolo = solidi.groupby('_ruolo')['_fm'].median().round(2)
    return {'squadra_ruolo': per_squadra_ruolo.to_dict(),
            'ruolo': per_ruolo.to_dict()}


def fantamedia_attesa(riga, forze, peso_contesto=10):
    """
    Quanto ci si aspetta che renda, mescolando quello che ha fatto lui con
    quello che rendono i suoi compagni di reparto.

    Per chi ha trenta presenze contano i suoi numeri; per un nuovo arrivato
    conta la squadra in cui e' finito. Il passaggio fra i due casi e' graduale,
    non a gradini.
    """
    ruolo = str(riga.get('R', '')).strip().upper()[:1]
    squadra = str(riga.get('Squadra', '')).strip()
    presenze = _num(riga.get('Pv'))
    sua = _num(riga.get('Fm'))

    contesto = forze['squadra_ruolo'].get((squadra, ruolo))
    if contesto is None:
        contesto = forze['ruolo'].get(ruolo, 6.0)

    if sua <= 0:
        return round(float(contesto), 2)
    return round((presenze * sua + peso_contesto * contesto) / (presenze + peso_contesto), 2)


def classifica(df, forze, prezzo_massimo=PREZZO_MASSIMO):
    """Ogni giocatore col suo profilo, la sua attesa e il suo prezzo."""
    lavoro = df.copy()
    lavoro['_prezzo'] = pd.to_numeric(lavoro['Prezzo'], errors='coerce').fillna(1)
    lavoro = lavoro[lavoro['_prezzo'] <= prezzo_massimo]

    righe = []
    for _, riga in lavoro.iterrows():
        dati = profilo(riga)
        dati.update({
            'nome': str(riga['Nome']),
            'ruolo': str(riga.get('R', '')).strip().upper()[:1],
            'squadra': str(riga.get('Squadra', '')),
            'prezzo': int(riga['_prezzo']),
            'fantamedia': _num(riga.get('Fm')),
            'voto': _num(riga.get('Mv')),
            'attesa': fantamedia_attesa(riga, forze),
        })
        righe.append(dati)
    return righe


def pronostici(df, forze=None, prezzo_massimo=PREZZO_MASSIMO, limite=6):
    """
    I nomi su cui scommettere, ognuno con il fatto che lo giustifica.

    Tre categorie separate, perche' rispondono a tre situazioni diverse e
    mescolarle renderebbe la lista di nuovo illeggibile.
    """
    forze = forze or forza_squadre(df)
    tutti = classifica(df, forze, prezzo_massimo)
    base = forze['ruolo']

    entrava, rotti, garantiti = [], [], []
    for g in tutti:
        if not g['dati_sufficienti']:
            continue
        soglia_ruolo = base.get(g['ruolo'], 6.0)

        # 1. Entrava e faceva: pochi minuti, tanti bonus quando in campo.
        #
        # Attenzione a non confondere due cose diverse: chi parte dalla
        # panchina e chi parte titolare ma viene sostituito. Il primo se
        # diventa titolare raddoppia i minuti, il secondo li ha gia' quasi
        # tutti. Guardare solo i minuti a partita li metteva nello stesso
        # sacco, ed e' un'etichetta sbagliata.
        if (g['minuti_a_partita'] < MINUTI_DA_TITOLARE and g['bonus_per_90'] >= 0.30
                and g['ruolo'] in ('C', 'A')):
            subentrante = g['quota_titolare'] < 0.6
            g = dict(
                g,
                etichetta='ENTRAVA E FACEVA' if subentrante else 'TITOLARE A META',
                punteggio=g['bonus_per_90'],
                motivo=(f"{g['bonus']} bonus in soli {g['minuti']} minuti "
                        f"({g['bonus_per_90']:.2f} ogni 90'): "
                        + (f"partiva in panchina ({g['da_titolare']} volte titolare "
                           f"su {g['presenze_totali']})"
                           if subentrante else
                           f"partiva titolare ma usciva presto "
                           f"({g['minuti_a_partita']:.0f} minuti a partita)")))
            entrava.append(g)
            continue

        # 2. Si e' rotto: titolare quando stava bene, mezza stagione ai box
        # Il portiere resta fuori: la sua fantamedia dipende dai gol subiti,
        # cioe' dalla difesa davanti a lui, e un portiere da 4.75 non diventa
        # una scommessa solo perche' si e' fatto male. Per lui vale la media
        # voto, che e' gia' il mestiere del modificatore.
        if (g['ruolo'] != 'P' and g['gare_saltate'] >= STOP_RILEVANTE
                and g['quota_titolare'] >= 0.7 and g['attesa'] >= soglia_ruolo - 0.10):
            g = dict(g, etichetta='STAGIONE PERSA', punteggio=g['attesa'],
                     motivo=(f"quando c'era giocava ({g['quota_titolare']:.0%} da titolare), "
                             f"ma ha saltato {g['gare_saltate']} gare per infortunio: "
                             f"il prezzo lo sconta, il rendimento no"))
            rotti.append(g)
            continue

        # 3. Giocava sempre: minuti garantiti, pochi bonus
        if (g['minuti'] >= 2000 and g['quota_titolare'] >= 0.8
                and g['attesa'] >= soglia_ruolo - 0.15):
            g = dict(g, etichetta='GIOCA SEMPRE', punteggio=g['voto'],
                     motivo=(f"{g['minuti']} minuti, {g['da_titolare']} da titolare: "
                             f"voto {g['voto']:.2f}, non lo togliono mai"))
            garantiti.append(g)

    def migliori(gruppo):
        return sorted(gruppo, key=lambda x: -x['punteggio'])[:limite]

    return {'entrava': migliori(entrava), 'rotti': migliori(rotti),
            'garantiti': migliori(garantiti)}
