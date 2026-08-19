"""
config.py - Costanti e impostazioni. Nessuna logica, nessuna dipendenza.

Tutto cio' che si cambia piu' spesso (URL, slot, quote, icone) sta qui,
cosi' non serve piu' cercarlo dentro mille righe di gestione bottoni.
"""

import os

# ----------------------------------------------------------------------
# TOKEN E SORGENTI
# ----------------------------------------------------------------------
TOKEN = os.getenv("BOT_TOKEN")

LISTONE_URL = os.getenv(
    "LISTONE_URL",
    "https://raw.githubusercontent.com/imwade021/fanta-master-ai/main/Lista_Finale_Master.csv"
)

FILE_MASTER = "Lista_Finale_Master.csv"
FILE_BACKUP = FILE_MASTER + ".bak"

# Rose, cassa e scartati sopravvivono a un riavvio del servizio
FILE_SESSIONI = os.getenv("FILE_SESSIONI", "sessioni.json")

# Il bot scarica alle 5:00, dopo che la GitHub Action delle 4:00 ha committato
ORA_DOWNLOAD = int(os.getenv("ORA_DOWNLOAD", "5"))

# ----------------------------------------------------------------------
# REGOLE DELLA LEGA (default, sovrascrivibili dall'utente nel bot)
# ----------------------------------------------------------------------
BUDGET_DEFAULT = 500
PARTECIPANTI_DEFAULT = 8

SLOT_PER_RUOLO = {'P': 3, 'D': 8, 'C': 8, 'A': 6}
ROSA_COMPLETA = sum(SLOT_PER_RUOLO.values())      # 25

# L'asta si svolge per reparti, in quest'ordine. Serve al Panic button per
# capire a che punto sei: quando compri difensori, i crediti per centrocampo
# e attacco vanno tenuti da parte, non sono disponibili.
ORDINE_ASTA = ('P', 'D', 'C', 'A')

# Come si spartisce il budget fra i reparti. Sono le stesse proporzioni che il
# motore usa per calcolare i prezzi: se cambi qui, cambia anche in
# fanta-master-ai (QUOTE_RUOLO in build_master.py).
QUOTE_REPARTO = {'P': 0.08, 'D': 0.14, 'C': 0.28, 'A': 0.50}

# Il Prezzo nel Master e' tarato su questa lega di riferimento
LEGA_RIFERIMENTO_BUDGET = 500
LEGA_RIFERIMENTO_SQUADRE = 8

# Quanto pesa un partecipante in piu' sul prezzo (piu' concorrenza, prezzi alti)
FATTORE_PARTECIPANTE = 0.025

# Stima di ripiego se il Master non ha la colonna Prezzo
QUOTE_FALLBACK = {'A': 0.50, 'C': 0.55, 'D': 0.45, 'P': 0.50}

# Soglie di rilancio rispetto al prezzo consigliato
MOLTIPLICATORE_MAX_RILANCIO = 1.15
MOLTIPLICATORE_STOP = 1.25

# ----------------------------------------------------------------------
# PRESENTAZIONE
# ----------------------------------------------------------------------
ROLE_ICONS = {'P': '🧤', 'D': '🛡️', 'C': '⚙️', 'A': '🎯'}

TEAM_COLORS = {
    'Atalanta': '🔵⚫', 'Bologna': '🔴🔵', 'Cagliari': '🔴🔵', 'Como': '🔵⚪',
    'Cremonese': '🔴⚪', 'Empoli': '🔵⚪', 'Fiorentina': '💜', 'Frosinone': '🟡🔵',
    'Genoa': '🔴🔵', 'Inter': '🔵⚫', 'Juventus': '⚪⚫', 'Lazio': '🩵⚪',
    'Lecce': '🟡🔴', 'Milan': '🔴⚫', 'Monza': '🔴⚪', 'Napoli': '🔵⚪',
    'Parma': '🟡🔵', 'Pisa': '🔵⚫', 'Roma': '🟡🔴', 'Sassuolo': '🟢⚫',
    'Torino': '🟤⚪', 'Udinese': '⚪⚫', 'Venezia': '🟠🟢', 'Verona': '🟡🔵',
    'Bari': '🔴⚪', 'Palermo': '🌸⚫', 'Salernitana': '🟤⚪', 'Spezia': '⚪⚫',
    'Catanzaro': '🟡🔴', 'Reggiana': '🔴⚪', 'Samdoria': '🔵⚪',
}

ICONA_SQUADRA_DEFAULT = '🛡️'

# Colonne minime perche' un file caricato a mano sia accettato.
# 'Prezzo' e' nell'elenco apposta: il listone quotazioni di Fantacalcio ha
# Nome/R/Squadra ma non i prezzi, e veniva accettato al posto del Master.
COLONNE_OBBLIGATORIE = ('Nome', 'R', 'Squadra', 'Prezzo')