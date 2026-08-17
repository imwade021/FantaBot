"""
scarica_foto.py - Scarica una volta sola tutte le foto dei giocatori.

All'asta la velocita' conta: meglio avere le immagini gia' sul disco che
scaricarle mentre stai rilanciando. Si lancia a mano quando cambia il listone.

    python scarica_foto.py
"""

import os
import sys
import time

import pandas as pd
import requests

CARTELLA = "cache_foto"
FILE_MASTER = "Lista_Finale_Master.csv"
PAUSA = 0.15


def nome_file(url):
    pulito = "".join(c for c in str(url).split("/")[-1].split("?")[0]
                     if c.isalnum() or c in "._-")
    return pulito[:80] or "foto.png"


def main():
    if not os.path.exists(FILE_MASTER):
        print(f"❌ {FILE_MASTER} non trovato: scaricalo prima dal bot.")
        return 1

    df = pd.read_csv(FILE_MASTER, sep=';')
    os.makedirs(CARTELLA, exist_ok=True)

    scaricate, saltate, fallite = 0, 0, 0
    for _, riga in df.iterrows():
        # stesse fonti, stesso ordine della card
        for colonna in ('FotoAPI', 'PhotoURL'):
            url = str(riga.get(colonna, '') or '').strip()
            if not url.startswith('http'):
                continue

            percorso = os.path.join(CARTELLA, nome_file(url))
            if os.path.exists(percorso):
                saltate += 1
                break

            try:
                risposta = requests.get(url, timeout=10,
                                        headers={"User-Agent": "Mozilla/5.0"})
                if risposta.status_code == 200 and risposta.content:
                    with open(percorso, "wb") as f:
                        f.write(risposta.content)
                    scaricate += 1
                    time.sleep(PAUSA)
                    break
            except Exception:
                pass
            fallite += 1

    peso = sum(os.path.getsize(os.path.join(CARTELLA, f))
               for f in os.listdir(CARTELLA)) / 1_000_000
    print(f"✅ Scaricate {scaricate} · gia' presenti {saltate} · non riuscite {fallite}")
    print(f"📦 Cartella {CARTELLA}: {peso:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
