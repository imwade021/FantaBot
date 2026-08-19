"""
piano.py - Quanto posso spendere, adesso, per questa casella.

Il budget non e' un numero solo: e' quattro budget, uno per reparto, e non
sono fissi. Le percentuali iniziali dicono da dove parti; il mercato dice dove
sei finito.

La differenza fra un piano ANCORATO e uno ADATTIVO conta piu' di quanto sembri.
L'ancorato tiene le percentuali decise ad agosto: se sfori in difesa, lo paghi
in attacco. L'adattivo guarda cosa e' rimasto davvero sul mercato: se a meta'
serata gli attaccanti forti sono gia' stati venduti tutti, tenere meta' budget
per l'attacco e' un errore, e solo l'adattivo se ne accorge.

Qui si usa l'adattivo, con le percentuali iniziali come punto di partenza: a
mercato intatto danno lo stesso risultato, e divergono solo quando e' giusto.
"""

import pandas as pd

ORDINE = ('P', 'D', 'C', 'A')
QUOTE_DEFAULT = {'P': 0.08, 'D': 0.14, 'C': 0.28, 'A': 0.50}
SLOT_DEFAULT = {'P': 3, 'D': 8, 'C': 8, 'A': 6}

STRATEGIE = {
    'corazzata':  (0.40, "pochi fuoriclasse, il resto a un credito"),
    'equilibrata': (0.55, "un titolare per fascia, poi si scala"),
    'spalmata':   (0.72, "nessun buco, nessun campione"),
}


def _prezzo(riga):
    valore = pd.to_numeric(riga.get('Prezzo'), errors='coerce')
    return 1 if pd.isna(valore) else max(1, int(valore))


def preventivo(budget_iniziale, quote=None, slot=None):
    """Da quanto parti, reparto per reparto."""
    quote = quote or QUOTE_DEFAULT
    slot = slot or SLOT_DEFAULT
    return {r: int(round(budget_iniziale * quote.get(r, 0.25))) for r in slot}


def stima_mercato(df_disponibili, ruolo, quanti, partecipanti=8, inflazione=1.0):
    """
    Quanto costerebbe davvero riempire {quanti} caselle di questo ruolo, viste
    le quotazioni di chi e' ANCORA libero.

    Il modello: gli avversari non spariscono. Su {partecipanti} squadre, il
    primo giocatore lo prende qualcuno, il secondo pure... realisticamente a te
    tocca uno ogni {partecipanti}. Quindi si guardano i prezzi in quelle
    posizioni, non i migliori in assoluto - che non prenderai mai tutti.
    """
    if df_disponibili is None or df_disponibili.empty or quanti <= 0:
        return 0

    gruppo = df_disponibili[df_disponibili['R'].astype(str).str.upper() == ruolo]
    if gruppo.empty:
        return quanti          # non c'e' piu' niente: un credito a casella

    prezzi = sorted((_prezzo(r) for _, r in gruppo.iterrows()), reverse=True)
    totale, passo = 0, max(1, int(partecipanti))
    for numero in range(quanti):
        indice = min(len(prezzi) - 1, (numero + 1) * passo - 1)
        totale += prezzi[indice]
    return max(quanti, int(round(totale * inflazione)))


def stato(registro, df_disponibili, slot=None, quote=None, inflazione=1.0):
    """
    Il quadro completo: cosa avevi previsto, cosa hai speso, cosa ti resta e
    quanto costa davvero finire ogni reparto.
    """
    slot = slot or SLOT_DEFAULT
    quote = quote or QUOTE_DEFAULT
    previsto = preventivo(registro.budget_iniziale, quote, slot)
    speso = registro.speso_per_ruolo()
    conteggi = registro.conteggi()

    reparti = {}
    for ruolo in slot:
        mancanti = max(0, slot[ruolo] - conteggi.get(ruolo, 0))
        reparti[ruolo] = {
            'ruolo': ruolo,
            'slot': slot[ruolo],
            'presi': conteggi.get(ruolo, 0),
            'mancanti': mancanti,
            'previsto': previsto[ruolo],
            'speso': speso.get(ruolo, 0),
            'scostamento': speso.get(ruolo, 0) - previsto[ruolo],
            'mercato': stima_mercato(df_disponibili, ruolo, mancanti,
                                     registro.partecipanti, inflazione),
        }

    scoperti = [r for r in ORDINE if reparti[r]['mancanti'] > 0]
    return {'reparti': reparti, 'scoperti': scoperti,
            'budget': registro.budget(), 'speso': registro.speso(),
            'inflazione': inflazione}


def disponibile(quadro, ruolo, elasticita=1.8):
    """
    Quanti crediti sono davvero miei, adesso, per questo reparto.

    Due vincoli, e vale il piu' stretto:

    1. La cassa meno quello che serve per finire i reparti successivi ai
       prezzi di mercato correnti. Se il mercato futuro si svuota, la riserva
       cala da sola e questi crediti tornano qui: e' il senso dell'adattivo.
    2. Quanto vale il reparto stesso. Senza questo secondo tetto, a inizio
       asta i portieri si prendevano 143 crediti solo perche' erano i primi
       della fila - e nessuno spende 78 crediti sul primo portiere. Il tetto
       e' il costo di mercato del reparto, con un margine per potersi
       permettere un titolare sopra la media.

    Quello che avanza non si perde: resta in cassa e allarga i reparti dopo.
    """
    reparti, cassa = quadro['reparti'], quadro['budget']
    successivi = [r for r in quadro['scoperti'] if r != ruolo]

    riserva = sum(reparti[r]['mercato'] for r in successivi)
    slot_dopo = sum(reparti[r]['mancanti'] for r in successivi)
    mancanti = reparti[ruolo]['mancanti']

    # Non si scende mai sotto un credito a casella per i reparti che restano:
    # e' il vincolo duro dell'asta.
    per_cassa = min(cassa - riserva, cassa - slot_dopo)
    per_mercato = reparti[ruolo]['mercato'] * elasticita
    in_rosso = riserva + mancanti > cassa

    if in_rosso:
        # Non bastano i soldi per finire tutto ai prezzi correnti. Affamare il
        # reparto in corso per proteggere quelli dopo non serve: arriveresti
        # comunque a corto. Si divide in proporzione a quanto costa ciascuno.
        totale_mercato = reparti[ruolo]['mercato'] + riserva
        quota = (reparti[ruolo]['mercato'] / totale_mercato) if totale_mercato else 1
        disponibili = int(max(mancanti, min(cassa - slot_dopo, cassa * quota)))
    else:
        disponibili = int(max(mancanti, min(per_cassa, per_mercato)))

    return {
        'ruolo': ruolo, 'mancanti': mancanti,
        'disponibile': disponibili, 'riserva': cassa - disponibili,
        'riserva_di_mercato': riserva, 'successivi': successivi,
        'cuscinetto': max(0, int(per_cassa - disponibili)),
        # Se per finire i reparti servirebbe piu' di quanto hai, sei in
        # ritardo sul piano: non e' un errore da nascondere, e' un allarme.
        'in_rosso': in_rosso,
    }


def fasce_di_spesa(disponibili, mancanti, strategia='equilibrata'):
    """
    Come dividere i crediti fra le caselle che restano.

    Non in parti uguali: si compra un titolare e poi si tappano i buchi. Ogni
    fascia vale una frazione della precedente, e quanto sia ripida la scala e'
    una scelta di strategia, non una costante universale.
    """
    if mancanti <= 0:
        return []
    decadimento = STRATEGIE.get(strategia, STRATEGIE['equilibrata'])[0]
    pesi = [decadimento ** i for i in range(mancanti)]
    grezzi = [disponibili * p / sum(pesi) for p in pesi]
    fasce = [max(1, int(v)) for v in grezzi]
    avanzo = disponibili - sum(fasce)
    if avanzo > 0:
        fasce[0] += avanzo
    return fasce
