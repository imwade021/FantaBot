"""
prezzi.py - I prezzi ce li facciamo noi.

Agganciarsi a un listino altrui e' una fotografia: vale finche' quella lista
non cambia, e non sa niente della lega che giochi tu. Qui il prezzo si genera
dai dati che rigeneriamo ogni notte, e da un'idea sola:

    quello che paghi non e' quanto un giocatore e' forte,
    ma quanto e' piu' forte di quello che prenderesti al suo posto.

Il "al suo posto" e' il giocatore che ti resterebbe se lo perdessi, e dipende
da quante squadre sono in asta. In una lega da otto servono ventiquattro
portieri: il ventiquattresimo e' ancora un portiere di Serie A. In una lega da
dodici ne servono trentasei, e il trentaseiesimo non giochera' mai. Ecco perche'
gli stessi sei portieri buoni costano molto di piu' a dodici che a otto - e il
modello lo scopre da solo, senza che nessuno gli dica "coi dodici alza i
portieri".

Da qui viene tutto il resto: le quote per reparto NON sono percentuali decise a
tavolino, sono il risultato. Se il modificatore rende preziosi i portieri, la
loro fetta cresce da se'.
"""

import pandas as pd

import consiglio

# Quanto si concentra la spesa sui migliori. A 1 si paga in proporzione esatta
# al vantaggio sul sostituto, che e' la regola pulita: nessuna preferenza
# aggiunta a mano. Alzandolo la cima si impenna, come nelle aste dove il primo
# nome scatena la guerra e il quinto lo prendi in silenzio; abbassandolo si
# appiattisce. E' l'unica manopola di gusto rimasta, ed e' dichiarata.
IMPENNATA = 1.0

# Sotto questo prezzo non si scende: un giocatore in lista lo paghi comunque.
PREZZO_MINIMO = 1

# Quanti se ne schierano ogni domenica, in media fra i moduli.
#
# E' il numero che conta davvero per la scarsita', e sbagliarlo ribalta tutto.
# Usando le caselle di rosa, il sostituto del portiere risultava il ventiquattresimo
# della lista - uno che non gioca mai - e allora ogni portiere titolare sembrava
# un affare irripetibile: uscivano cinque portieri identici a 70 crediti e un
# quarto del monte speso in porta. Ma tu i portieri ne compri tre e ne schieri
# uno: il vero concorrente per quel posto e' l'ottavo portiere della lista, non
# il ventiquattresimo. Il secondo e il terzo li paghi un credito, come nella
# realta'.
TITOLARI_PER_RUOLO = {'P': 1.0, 'D': 3.5, 'C': 3.7, 'A': 2.8}


def valori(df, modificatore_attivo=False, tabella=None, aggiustamenti=None):
    """
    Il valore di ogni giocatore in punti a partita, piu' le correzioni.

    aggiustamenti: {'Nome': 1.2} moltiplica il valore. Serve per quello che i
    numeri della stagione scorsa non possono sapere: il neoacquisto su cui
    tutti si buttano, il ritorno da un infortunio lungo, il giovane lanciato
    titolare. Resta una scelta tua dichiarata, non una correzione nascosta
    dentro il calcolo.
    """
    contesto = consiglio.contesto_valutazione(df, modificatore_attivo, tabella)
    grezzi = [max(0.0, consiglio.valuta(riga, contesto)['produzione'])
              for _, riga in df.iterrows()]
    if aggiustamenti:
        grezzi = [v * float(aggiustamenti.get(str(nome), 1.0))
                  for v, nome in zip(grezzi, df['Nome'])]
    return pd.Series(grezzi, index=df.index)


def livello_sostituto(valori_ruolo, posti):
    """
    Il valore del giocatore che ti resta se perdi quello che volevi.

    Non e' il secondo della lista: e' il primo che avanza dopo che tutte le
    altre squadre hanno riempito quella casella. E' qui che entra la dimensione
    della lega, ed e' l'unico punto in cui serve saperla.
    """
    ordinati = sorted(valori_ruolo, reverse=True)
    if not ordinati:
        return 0.0
    return float(ordinati[min(len(ordinati) - 1, max(0, posti - 1))])


def calibra(df, budget=500, partecipanti=8, slot_per_ruolo=None,
            modificatore_attivo=False, tabella=None, aggiustamenti=None,
            impennata=IMPENNATA, titolari_per_ruolo=None):
    """
    Il prezzo di ogni giocatore per QUESTA lega.

    I conti chiudono per costruzione: la somma di quello che verra' speso e'
    esattamente il monte crediti, perche' i crediti si spartiscono, non si
    inventano.
    """
    slot_per_ruolo = slot_per_ruolo or {'P': 3, 'D': 8, 'C': 8, 'A': 6}
    titolari_per_ruolo = titolari_per_ruolo or TITOLARI_PER_RUOLO
    monte = budget * partecipanti

    lavoro = df.copy()
    lavoro['_ruolo'] = lavoro['R'].astype(str).str.upper().str[:1]
    lavoro['_valore'] = valori(lavoro, modificatore_attivo, tabella, aggiustamenti)
    lavoro['_vantaggio'] = 0.0
    lavoro['_comprato'] = False

    sostituti = {}
    for ruolo, slot in slot_per_ruolo.items():
        gruppo = lavoro[lavoro['_ruolo'] == ruolo]
        if gruppo.empty:
            continue
        posti = partecipanti * slot
        # La soglia si misura sui titolari, il denaro si spartisce su tutta la rosa
        titolari = max(1, round(partecipanti * titolari_per_ruolo.get(ruolo, 1)))
        soglia = livello_sostituto(gruppo['_valore'].tolist(), titolari)
        sostituti[ruolo] = soglia

        comprati = gruppo.nlargest(posti, '_valore').index
        lavoro.loc[comprati, '_comprato'] = True
        lavoro.loc[comprati, '_vantaggio'] = (
            gruppo.loc[comprati, '_valore'] - soglia).clip(lower=0.0)

    # I crediti che restano dopo aver messo da parte il minimo per ogni casella
    posti_totali = partecipanti * sum(slot_per_ruolo.values())
    da_spartire = max(0.0, monte - posti_totali * PREZZO_MINIMO)

    pesi = lavoro['_vantaggio'] ** impennata
    totale = pesi[lavoro['_comprato']].sum()
    if totale <= 0:
        lavoro['_prezzo'] = float(PREZZO_MINIMO)
    else:
        lavoro['_prezzo'] = PREZZO_MINIMO + da_spartire * pesi / totale
        lavoro.loc[~lavoro['_comprato'], '_prezzo'] = float(PREZZO_MINIMO)

    prezzi = lavoro['_prezzo'].round().clip(lower=PREZZO_MINIMO).astype(int)
    return prezzi, _resoconto(lavoro, prezzi, monte, partecipanti,
                              slot_per_ruolo, sostituti)


def _resoconto(lavoro, prezzi, monte, partecipanti, slot_per_ruolo, sostituti):
    """
    Come si e' spartito il monte. Le quote per reparto qui sono un RISULTATO:
    se cambia la lega, cambiano da sole.
    """
    lavoro = lavoro.assign(_p=prezzi)
    reparti, speso_totale = {}, 0
    for ruolo, slot in slot_per_ruolo.items():
        gruppo = lavoro[(lavoro['_ruolo'] == ruolo) & lavoro['_comprato']]
        speso = int(gruppo['_p'].sum())
        speso_totale += speso
        reparti[ruolo] = {
            'speso': speso,
            'quota': round(speso / monte, 3) if monte else 0,
            'massimo': int(gruppo['_p'].max()) if len(gruppo) else 0,
            'posti': partecipanti * slot,
            'titolari': max(1, round(partecipanti * TITOLARI_PER_RUOLO.get(ruolo, 1))),
            'sostituto': round(sostituti.get(ruolo, 0.0), 3),
        }
    return {'monte': monte, 'speso': speso_totale,
            'copertura': round(speso_totale / monte, 3) if monte else 0,
            'reparti': reparti}
