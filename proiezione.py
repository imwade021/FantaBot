"""
proiezione.py - Quanto renderà, non quanto ha reso.

Il problema che risolve: il listino ufficiale valuta Dimarco 265, quasi quanto
Hojlund, perche' l'anno scorso ha fatto 7 gol e 17 assist da difensore. Chiunque
abbia giocato a fantacalcio sa che non si ripetera'. Ma "lo sa chiunque" non e'
un calcolo, ed e' inaccettabile che diventi una manopola da girare a mano: una
manopola e' l'ennesima domanda travestita da soluzione.

Si puo' ricavare dai dati, e serve una stagione sola. L'idea e' che due
giocatori dello stesso ruolo si distinguono per due motivi mescolati: perche'
uno e' piu' bravo, e perche' uno e' stato piu' fortunato. La parte di fortuna si
puo' stimare: i gol sono eventi rari, e contarli su trenta partite produce
oscillazione anche a parita' di bravura. Quanta ne produce lo dice la
statistica dei conteggi, non un'opinione.

Confrontando quanto i giocatori di un ruolo differiscono davvero con quanto
differirebbero per solo caso, si ottiene quanto di quel divario e' vero. Sui
dati 2025/26 viene fuori questo:

    difensori     50% ripetibile      i bonus sono rari, meta' e' rumore
    centrocampo   44% ripetibile
    attaccanti    65% ripetibile      i gol sono abbastanza frequenti
    portieri     100%                 ma il loro "bonus" sono i gol subiti

Applicato al singolo giocatore, tenendo conto anche di quante partite ha
giocato, restituisce il rendimento atteso invece di quello passato.
"""

import pandas as pd

# Quanto pesa un gol e quanto un assist nel bonus del fantacalcio: servono per
# stimare l'oscillazione da conteggio, che va col quadrato del valore.
PUNTI_GOL = 3.0
PUNTI_ASSIST = 1.0

PRESENZE_MINIME_CAMPIONE = 15
K_VOTO = 8                      # quanto pesa la media di ruolo su chi ha giocato poco
PRESENZE_TITOLARE = {'P': 34, 'D': 30, 'C': 30, 'A': 30}


def _num(serie, predefinito=0.0):
    return pd.to_numeric(serie, errors='coerce').fillna(predefinito)


def _oscillazione_da_conteggio(gol, assist, presenze):
    """
    Quanto puo' oscillare il bonus medio per puro caso.

    Un giocatore che segna dieci gol in trenta partite ha un tasso di 0.33 a
    partita, ma se rigiocasse la stessa stagione potrebbe farne sette o
    tredici senza essere diventato piu' o meno bravo. Per eventi rari
    l'oscillazione e' proporzionale al tasso, e diminuisce con le partite
    giocate: e' per questo che di chi ha giocato poco ci si fida meno.
    """
    presenze = presenze.clip(lower=1)
    varianza_per_gara = (PUNTI_GOL ** 2) * gol / presenze + \
                        (PUNTI_ASSIST ** 2) * assist / presenze
    return varianza_per_gara / presenze


def ripetibilita(df):
    """
    Quanto e' ripetibile il bonus, ruolo per ruolo.

    Si confronta quanto i giocatori differiscono davvero (varianza osservata)
    con quanto differirebbero per solo caso. Quello che avanza e' bravura.
    """
    lavoro = df.copy()
    lavoro['_ruolo'] = lavoro['R'].astype(str).str.upper().str[:1]
    for chiave, colonna in (('_pv', 'Pv'), ('_gf', 'Gf'), ('_ass', 'Ass'),
                            ('_mv', 'Mv'), ('_fm', 'Fm')):
        lavoro[chiave] = _num(lavoro[colonna])

    misure = {}
    for ruolo in ('P', 'D', 'C', 'A'):
        gruppo = lavoro[(lavoro['_ruolo'] == ruolo) &
                        (lavoro['_pv'] >= PRESENZE_MINIME_CAMPIONE)]
        if len(gruppo) < 10:
            misure[ruolo] = {'media': 0.0, 'bravura': 0.0, 'voto_base': 6.0,
                             'campione': len(gruppo)}
            continue
        bonus = gruppo['_fm'] - gruppo['_mv']
        caso = _oscillazione_da_conteggio(gruppo['_gf'], gruppo['_ass'],
                                          gruppo['_pv']).mean()
        osservata = float(bonus.var())
        misure[ruolo] = {
            'media': round(float(bonus.mean()), 3),
            # Quello che resta togliendo il caso: se venisse negativo,
            # vorrebbe dire che il ruolo e' tutto fortuna.
            'bravura': round(max(0.0, osservata - caso), 4),
            'osservata': round(osservata, 4),
            'caso': round(float(caso), 4),
            'quota_ripetibile': round(max(0.0, osservata - caso) / osservata, 3)
            if osservata else 0.0,
            'voto_base': round(float(gruppo['_mv'].median()), 2),
            'campione': len(gruppo),
        }
    return misure


def attesa(riga, misure):
    """
    La fantamedia attesa di un giocatore: voto piu' bonus, regrediti entrambi.

    Chi ha giocato poco viene tirato verso la media del ruolo perche' su di lui
    si sa poco; chi ha avuto una stagione fuori scala viene tirato verso la
    media perche' quelle stagioni non si ripetono. Sono due correzioni diverse
    e agiscono insieme.
    """
    ruolo = str(riga.get('R', 'C')).upper()[:1]
    riferimento = misure.get(ruolo)
    presenze = float(_num(pd.Series([riga.get('Pv')])).iloc[0])
    if not riferimento or presenze < 1:
        return {'attesa': 0.0, 'bonus_atteso': 0.0, 'affidabilita': 0.0,
                'presenze': 0, 'senza_dati': True}

    gol = float(_num(pd.Series([riga.get('Gf')])).iloc[0])
    assist = float(_num(pd.Series([riga.get('Ass')])).iloc[0])
    voto = float(_num(pd.Series([riga.get('Mv')])).iloc[0])
    fantamedia = float(_num(pd.Series([riga.get('Fm')])).iloc[0])

    caso = float(_oscillazione_da_conteggio(
        pd.Series([gol]), pd.Series([assist]), pd.Series([presenze])).iloc[0])
    bravura = riferimento['bravura']
    affidabilita = bravura / (bravura + caso) if (bravura + caso) > 0 else 0.0

    bonus_grezzo = fantamedia - voto
    bonus_atteso = riferimento['media'] + affidabilita * (bonus_grezzo - riferimento['media'])

    voto_atteso = (presenze * voto + K_VOTO * riferimento['voto_base']) / (presenze + K_VOTO)
    quota_gioco = min(1.0, presenze / PRESENZE_TITOLARE.get(ruolo, 30))

    # Nelle giornate in cui non gioca schieri un altro, non il vuoto.
    valore = (voto_atteso + bonus_atteso) * quota_gioco + \
             riferimento['voto_base'] * (1 - quota_gioco)

    return {
        'attesa': round(valore, 3),
        'bonus_grezzo': round(bonus_grezzo, 3),
        'bonus_atteso': round(bonus_atteso, 3),
        'affidabilita': round(affidabilita, 3),
        'quota_gioco': round(quota_gioco, 2),
        'presenze': int(presenze),
        'senza_dati': False,
    }


def colonna_attesa(df):
    """La fantamedia attesa per tutto il listone, in una passata sola."""
    misure = ripetibilita(df)
    return pd.Series([attesa(riga, misure)['attesa'] for _, riga in df.iterrows()],
                     index=df.index), misure
