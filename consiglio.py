"""
consiglio.py - Le risposte. Un solo calcolo per tutto il bot.

Prima ogni schermata si arrangiava: il suggerimento dopo una vendita ordinava
per bonus entro un tetto, il Panic ordinava per solidita' dentro fasce di
spesa, e i due numeri non coincidevano mai. Da qui in avanti il valore di un
giocatore si calcola in un posto solo, e si misura in PUNTI A PARTITA - la
stessa unita' in cui si vincono e si perdono le giornate.

Ogni consiglio porta con se' il motivo per cui e' li'. Un elenco senza motivo
non e' una risposta: e' la domanda spostata piu' avanti.
"""

import pandas as pd

import modificatore as mod

PARTITE = 38
# Sopra questa soglia si e' titolari pieni. Il portiere ha un'asticella piu'
# alta di tutti: chi ne gioca 27 su 38 non e' un titolare che ha saltato
# qualche gara, e' uno in ballottaggio - e per giunta non sai in quali
# domeniche giochera'.
PRESENZE_TITOLARE = {'P': 34, 'D': 30, 'C': 30, 'A': 30}
PRESENZE_BALLOTTAGGIO_P = 32
K_PONDERAZIONE = 8          # quanto pesa la media di ruolo su chi ha giocato poco

NOMI_RUOLO = {'P': 'portiere', 'D': 'difensore', 'C': 'centrocampista', 'A': 'attaccante'}
PLURALE_RUOLO = {'P': 'portieri', 'D': 'difensori', 'C': 'centrocampisti', 'A': 'attaccanti'}


def _num(valore, predefinito=0.0):
    convertito = pd.to_numeric(valore, errors='coerce')
    return predefinito if pd.isna(convertito) else float(convertito)


def contesto_valutazione(df, modificatore_attivo=False, tabella=None):
    """
    I riferimenti contro cui si misura tutto: la fantamedia media di ogni
    ruolo e la media voto del reparto arretrato. Si calcolano una volta sola
    e si passano in giro, cosi' ogni schermata usa gli stessi numeri.
    """
    lavoro = df.copy()
    for chiave, colonna in (('_pv', 'Pv'), ('_fm', 'Fm'), ('_mv', 'Mv')):
        lavoro[chiave] = pd.to_numeric(lavoro[colonna], errors='coerce').fillna(0)
    solidi = lavoro[(lavoro['_pv'] >= 15) & (lavoro['_fm'] > 0)]

    riferimenti = {}
    for ruolo in ('P', 'D', 'C', 'A'):
        gruppo = solidi[solidi['R'].astype(str).str.upper() == ruolo]
        riferimenti[ruolo] = (round(gruppo['_fm'].median(), 2) if len(gruppo) >= 10
                              else {'P': 5.4, 'D': 5.9, 'C': 6.0, 'A': 6.2}[ruolo])

    arretrati = solidi[solidi['R'].astype(str).str.upper().isin(['P', 'D'])]
    riferimento_voto = round(arretrati['_mv'].median(), 2) if len(arretrati) >= 10 else 6.0

    return {'fantamedia': riferimenti, 'voto_arretrato': riferimento_voto,
            'modificatore': bool(modificatore_attivo), 'tabella': tabella}


def valuta(riga, contesto):
    """
    Quanto vale un giocatore, in punti a partita in piu' rispetto a uno
    qualsiasi del suo ruolo.

    Tre pezzi:
      - la fantamedia sopra la media del ruolo, ponderata sulle presenze
      - il modificatore, se la lega lo usa e se e' un portiere o un difensore
      - la titolarita', perche' chi non gioca non ti fa punti: un fenomeno che
        scende in campo dieci volte vale meno di un onesto che gioca sempre
    """
    ruolo = str(riga.get('R', '')).strip().upper()[:1]
    presenze = _num(riga.get('Pv'))
    fantamedia = _num(riga.get('Fm'))
    voto = _num(riga.get('Mv'))
    base = contesto['fantamedia'].get(ruolo, 6.0)

    if fantamedia <= 0:
        return {'totale': 0.0, 'produzione': 0.0, 'rendimento': 0.0, 'modificatore': 0.0,
                'quota_gioco': 0.0, 'presenze': int(presenze), 'ruolo': ruolo,
                'senza_dati': True}

    ponderata = (presenze * fantamedia + K_PONDERAZIONE * base) / (presenze + K_PONDERAZIONE)
    soglia = PRESENZE_TITOLARE.get(ruolo, 30)
    quota_gioco = min(1.0, presenze / soglia) if presenze else 0.0

    rendimento = (ponderata - base) * quota_gioco
    contributo_modificatore = 0.0
    if contesto['modificatore'] and ruolo in ('P', 'D') and voto > 0:
        contributo_modificatore = mod.impatto(
            voto, contesto['voto_arretrato'], contesto['tabella']) * quota_gioco

    return {
        'totale': round(rendimento + contributo_modificatore, 2),
        # La produzione GREZZA: punti a partita in assoluto, senza togliere la
        # media di ruolo. Serve ai prezzi, dove il confronto non e' con un
        # giocatore medio ma col sostituto vero - e quello dipende da quante
        # squadre sono in asta. Sottrarre due volte azzererebbe meta' listone.
        #
        # Nelle domeniche in cui non gioca non schieri il vuoto: schieri un
        # altro. Quindi le giornate mancanti valgono quanto un giocatore
        # qualsiasi del ruolo, non zero. Senza questa riga un difensore da 26
        # presenze finiva sotto la soglia e usciva a un credito.
        'produzione': round(ponderata * quota_gioco + base * (1 - quota_gioco)
                            + contributo_modificatore, 3),
        'rendimento': round(rendimento, 2),
        'modificatore': round(contributo_modificatore, 2),
        'quota_gioco': round(quota_gioco, 2),
        'ballottaggio': ruolo == 'P' and 0 < presenze < PRESENZE_BALLOTTAGGIO_P,
        'presenze': int(presenze), 'voto': voto, 'ruolo': ruolo,
        'gol': int(_num(riga.get('Gf'))), 'assist': int(_num(riga.get('Ass'))),
        'senza_dati': False,
    }


def motivo(riga, punteggio, prezzo, contesto, liberi_simili=None):
    """
    Una riga che spiega perche' quel nome sta li'. Si sceglie la ragione
    dominante invece di elencarle tutte: tre motivi non sono una spiegazione.
    """
    if punteggio['senza_dati']:
        return "mai giocato in Serie A: nessun dato su cui basarsi"

    pezzi = []
    ruolo = punteggio['ruolo']

    if punteggio.get('ballottaggio'):
        return (f"⚠️ ballottaggio: solo {punteggio['presenze']} presenze su 38, "
                f"non sai in quali domeniche gioca")

    if punteggio['modificatore'] >= punteggio['rendimento'] and punteggio['modificatore'] > 0:
        pezzi.append(f"vale per il voto ({punteggio['voto']:.2f}): "
                     f"alza il modificatore di {punteggio['modificatore']:+.2f} a partita")
    elif punteggio['gol'] or punteggio['assist']:
        pezzi.append(f"{punteggio['gol']} gol e {punteggio['assist']} assist "
                     f"in {punteggio['presenze']} presenze")
    else:
        pezzi.append(f"{punteggio['presenze']} presenze, "
                     f"{punteggio['totale']:+.2f} punti a partita")

    if punteggio['quota_gioco'] < 0.6:
        pezzi.append("ma gioca poco")
    if prezzo and punteggio['totale'] > 0:
        crediti_per_punto = round(prezzo / punteggio['totale'])
        if crediti_per_punto <= 15:
            pezzi.append(f"costa {crediti_per_punto} crediti per ogni punto a partita")
    if liberi_simili is not None and liberi_simili <= 2:
        pezzi.append("ne restano pochissimi come lui")

    return " · ".join(pezzi[:2])


def classifica(disponibili, ruolo, contesto, tetto=None):
    """I giocatori di un ruolo, ordinati per punti a partita, entro un tetto."""
    if disponibili is None or disponibili.empty:
        return None

    gruppo = disponibili[disponibili['R'].astype(str).str.upper() == ruolo].copy()
    if gruppo.empty:
        return None

    gruppo['_prezzo'] = pd.to_numeric(gruppo['Prezzo'], errors='coerce').fillna(1).clip(lower=1)
    if 'Infortunio' in gruppo.columns:
        # Attenzione al doppio tranello di questa colonna. Se e' tutta vuota
        # pandas la legge come numerica; e astype(str) NON produce la stringa
        # "nan" ma lascia il valore mancante. Quindi si guarda direttamente
        # se il dato c'e', senza passare dal testo.
        grezzo = gruppo['Infortunio']
        fermo = grezzo.notna() & (grezzo.astype(str).str.strip() != '')
        gruppo = gruppo[~fermo.fillna(False)]

    valori = [valuta(riga, contesto) for _, riga in gruppo.iterrows()]
    gruppo['_valore'] = [v['totale'] for v in valori]
    gruppo['_dettaglio'] = valori

    if tetto is not None:
        gruppo = gruppo[gruppo['_prezzo'] <= max(1, int(tetto))]
    return gruppo.sort_values('_valore', ascending=False) if not gruppo.empty else None


def tetto_personale(valore, prezzo, valore_migliore, valore_sostituto,
                    prezzo_sostituto, tetto_reparto, inflazione=1.0,
                    ballottaggio=False, moltiplicatore_massimo=2.2):
    """
    Fin dove spingersi su QUESTO giocatore.

    Non e' il tetto della fascia di spesa: quello dice quanto PUOI permetterti,
    e applicato a tutti dava lo stesso "fino a 28" su un portiere da 24 e su
    uno da 2. Qui si ragiona sul costo dell'alternativa: se perdendolo prendi
    comunque un sostituto, l'unica cosa per cui vale pagare di piu' e' il
    vantaggio fra i due.

    Tre limiti, imparati sbagliando:
      - il cambio crediti/punto si ricava dal budget del reparto, non dal
        sostituto: se quello vale quasi zero il rapporto esplode e il tetto
        finisce al massimo per chiunque;
      - non si paga mai piu' del doppio abbondante del listino, che e' gia'
        calibrato sul monte crediti della lega;
      - su un portiere in ballottaggio si taglia: non stai comprando 38
        partite, ne stai comprando forse venti, e non sai quali.
    """
    prezzo = max(1, prezzo)
    cambio = tetto_reparto / max(0.15, valore_migliore)
    equo = max(1, prezzo_sostituto) + max(0.0, valore - valore_sostituto) * cambio

    tetto = max(equo, prezzo) * max(0.9, inflazione)
    tetto = min(tetto, prezzo * moltiplicatore_massimo)
    if ballottaggio:
        tetto *= 0.7
    return int(max(1, min(round(tetto), tetto_reparto)))


def consiglia(disponibili, ruolo, contesto, tetto, mancanti=1, inflazione=1.0,
              partecipanti=8):
    """
    Tre risposte a tre situazioni diverse, non tre alternative equivalenti:

      1. IL MIGLIORE   chi prendere, punto
      2. L'ALTERNATIVA chi prendere se te lo soffiano, a meno di due terzi
      3. IL RIPIEGO    chi prendere se i crediti sono finiti

    Ognuno col suo motivo e col suo tetto. Tre nomi senza spiegazione tornano
    a essere una lista, e una lista non decide niente.
    """
    ordinati = classifica(disponibili, ruolo, contesto, tetto)
    if ordinati is None or ordinati.empty:
        return []

    # Il sostituto di riferimento: non il secondo in classifica, ma quello che
    # ti resterebbe davvero. Gli avversari comprano prima di te, quindi in una
    # lega da {partecipanti} squadre realisticamente ti tocca uno ogni tanti.
    valore_migliore = float(ordinati.iloc[0]['_valore'])
    posizione = min(len(ordinati) - 1, max(1, partecipanti - 1))
    riferimento = ordinati.iloc[posizione]
    valore_rif = float(riferimento['_valore'])
    prezzo_rif = int(riferimento['_prezzo'])

    scelte, presi = [], set()

    def aggiungi(candidati, etichetta):
        for _, riga in candidati.iterrows():
            if str(riga['Nome']) in presi:
                continue
            punteggio = riga['_dettaglio']
            simili = int((ordinati['_valore'] >= punteggio['totale'] * 0.85).sum())
            prezzo = int(riga['_prezzo'])
            scelte.append({
                'etichetta': etichetta,
                'nome': str(riga['Nome']),
                'squadra': str(riga.get('Squadra', '')),
                'prezzo': prezzo,
                'tetto': tetto_personale(
                    punteggio['totale'], prezzo, valore_migliore, valore_rif,
                    prezzo_rif, tetto, inflazione,
                    punteggio.get('ballottaggio', False)),
                'valore': punteggio['totale'],
                'motivo': motivo(riga, punteggio, prezzo, contesto, simili),
                'simili_liberi': simili,
                'ballottaggio': punteggio.get('ballottaggio', False),
            })
            presi.add(str(riga['Nome']))
            return True
        return False

    aggiungi(ordinati, "prendi")
    if scelte:
        piu_economici = ordinati[ordinati['_prezzo'] <= max(1, scelte[0]['prezzo'] * 0.66)]
        if not aggiungi(piu_economici, "se lo perdi"):
            aggiungi(ordinati, "se lo perdi")
    aggiungi(ordinati[ordinati['_prezzo'] <= max(1, int(tetto * 0.15))], "se resti a secco")
    return scelte

# ----------------------------------------------------------------------
# COME STO ANDANDO
# ----------------------------------------------------------------------
def andamento(registro, disponibili, contesto, slot_per_ruolo, previsto_per_ruolo,
              inflazione=1.0, ordine=('P', 'D', 'C', 'A')):
    """
    Non una tabella: un giudizio. Tre domande e una frase che le riassume.

      1. sto spendendo troppo o troppo poco, ai prezzi di QUESTA asta
      2. sto comprando bene, cioe' quanti punti a partita mi porta la rosa
      3. cosa mi aspetta, cioe' se i crediti bastano per finire
    """
    conteggi = registro.conteggi()
    speso = registro.speso_per_ruolo()
    voti_arretrati = {'P': [], 'D': []}
    punti_rosa = 0.0

    indice = {str(r['Nome']): r for _, r in disponibili.iterrows()} if disponibili is not None else {}
    for voce in registro.rosa():
        riga = voce.get('_riga') or indice.get(voce['nome'])
        if riga is None:
            continue
        punteggio = valuta(riga, contesto)
        punti_rosa += punteggio['totale']
        if voce['ruolo'] in voti_arretrati:
            voti_arretrati[voce['ruolo']].append(_num(riga.get('Mv')))

    reparti = []
    for ruolo in ordine:
        mancanti = max(0, slot_per_ruolo.get(ruolo, 0) - conteggi.get(ruolo, 0))
        reparti.append({
            'ruolo': ruolo, 'presi': conteggi.get(ruolo, 0),
            'slot': slot_per_ruolo.get(ruolo, 0), 'mancanti': mancanti,
            'speso': speso.get(ruolo, 0),
            'previsto': previsto_per_ruolo.get(ruolo, 0),
            'chiuso': mancanti == 0,
        })

    difesa = None
    if contesto['modificatore'] and (voti_arretrati['P'] or voti_arretrati['D']):
        difesa = mod.valuta_reparto(voti_arretrati['P'], voti_arretrati['D'],
                                    contesto['tabella'])
        difesa['manca'] = mod.quanto_manca(difesa['media'], contesto['tabella'])

    return {'reparti': reparti, 'punti_rosa': round(punti_rosa, 2),
            'difesa': difesa, 'inflazione': inflazione,
            'cassa': registro.budget(), 'speso': registro.speso()}
