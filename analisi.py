"""
analisi.py - Logica di analisi sui dati del Lista_Finale_Master.csv.

Nessuna dipendenza da Telegram: si puo' testare da solo.
Gerarchia dei criteri (dalla piu' importante):
  1. Bonus e fantamedia   -> Fm, e soprattutto Fm - Mv = bonus per partita
  2. Presenze/titolarita' -> Pv, senza voti non esiste fantamedia
  3. Gol subiti squadra   -> non danno malus ai difensori, ma abbassano il
                             voto puro (Mv) e bloccano il modificatore
"""

import pandas as pd

PARTITE_STAGIONE = 38

SOGLIE_TITOLARITA = [(0.80, "inamovibile"), (0.60, "titolare"),
                     (0.35, "alternanza"), (0.0, "riserva")]

# Le medie a partita su poche presenze non sono confrontabili: vengono
# avvicinate alla media del ruolo. Con K=8, chi ha 8 presenze pesa meta'
# se stesso e meta' baseline. Senza questo, un giocatore con 1 partita da
# 9.50 batterebbe chi ne ha fatte 36 a 7.38.
K_PRESENZE = 8
BASELINE_FALLBACK = {'P': (5.0, 0.1), 'D': (5.8, 0.2), 'C': (6.0, 0.4), 'A': (6.2, 0.7)}


def _testo(valore):
    """Le celle vuote del CSV diventano NaN e str(NaN) e' la stringa 'nan':
    senza questo filtro il bot scriveva 'INDISPONIBILE: nan' su tutti."""
    if valore is None:
        return ""
    try:
        if pd.isna(valore):
            return ""
    except (TypeError, ValueError):
        pass
    testo = str(valore).strip()
    return "" if testo.lower() in ('nan', 'none', 'nat') else testo


def _num(valore, default=0.0):
    n = pd.to_numeric(str(valore).replace(',', '.'), errors='coerce')
    return default if pd.isna(n) else float(n)


# L'API restituisce le cause in inglese ("Knee Injury"): qui si traducono.
PARTI_CORPO = {
    'knee': 'al ginocchio', 'calf': 'al polpaccio', 'thigh': 'alla coscia',
    'ankle': 'alla caviglia', 'groin': "all'inguine", 'hamstring': 'al flessore',
    'shoulder': 'alla spalla', 'back': 'alla schiena', 'foot': 'al piede',
    'hip': "all'anca", 'toe': 'a un dito del piede', 'head': 'alla testa',
    'elbow': 'al gomito', 'wrist': 'al polso', 'hand': 'alla mano',
    'neck': 'al collo', 'chest': 'al torace', 'abdominal': "all'addome",
    'adductor': "all'adduttore", 'rib': 'alle costole', 'leg': 'alla gamba',
    'arm': 'al braccio', 'muscle': 'muscolare', 'facial': 'al volto',
    'shin': 'alla tibia', 'heel': 'al tallone', 'finger': 'a un dito',
}

FRASI_INFORTUNIO = {
    'cruciate ligament rupture': 'rottura del legamento crociato',
    'cruciate ligament injury': 'lesione del legamento crociato',
    'ankle/foot injury': 'infortunio a caviglia o piede',
    'achilles tendon injury': "infortunio al tendine d'Achille",
    'achilles tendon rupture': "rottura del tendine d'Achille",
    'meniscus injury': 'lesione del menisco',
    'broken ankle': 'frattura della caviglia',
    'broken leg': 'frattura della gamba',
    'broken foot': 'frattura del piede',
    'muscle injury': 'infortunio muscolare',
    'knock': 'contusione',
    'illness': 'malattia',
    'flu': 'influenza',
    'fever': 'febbre',
    'fitness': 'condizione fisica',
    'fatigue': 'affaticamento',
    'rest': 'riposo',
    'suspended': 'squalifica',
    'suspension': 'squalifica',
    'red card suspension': 'squalifica per espulsione',
    'yellow cards suspension': 'squalifica per somma di ammonizioni',
    'personal reasons': 'motivi personali',
    'national selection': 'impegni con la nazionale',
    'coronavirus': 'Covid',
    'concussion': 'trauma cranico',
    'missing fixture': 'indisponibile',
    'questionable': 'in dubbio',
    'doubtful': 'in dubbio',
    'surgery': 'operazione',
    'groin surgery': "operazione all'inguine",
    'back surgery': 'operazione alla schiena',
    'unknown': 'motivo non specificato',
}

SUFFISSI = [('injury', 'infortunio'), ('strain', 'stiramento'),
            ('rupture', 'rottura'), ('fracture', 'frattura'),
            ('sprain', 'distorsione'), ('problems', 'problemi'),
            ('surgery', 'operazione'), ('inflammation', 'infiammazione')]


def _maiuscola(testo):
    """Alza solo la prima lettera: capitalize() rovinerebbe "tendine d'Achille"."""
    return testo[:1].upper() + testo[1:] if testo else testo


def traduci_causa(testo):
    """'Knee Injury' -> 'Infortunio al ginocchio'. Se non riconosce, lascia com'e'."""
    grezzo = _testo(testo)
    if not grezzo:
        return ""

    minuscolo = grezzo.lower().strip()
    if minuscolo in FRASI_INFORTUNIO:
        return _maiuscola(FRASI_INFORTUNIO[minuscolo])

    for suffisso, tradotto in SUFFISSI:
        if minuscolo.endswith(suffisso):
            parte = minuscolo[:-len(suffisso)].strip()
            if parte in PARTI_CORPO:
                return _maiuscola(f"{tradotto} {PARTI_CORPO[parte]}")
            if not parte:
                return _maiuscola(tradotto)

    for chiave, valore in FRASI_INFORTUNIO.items():
        if chiave in minuscolo:
            return _maiuscola(valore)

    return grezzo


def _giorni_fermo(data_inizio):
    """Da quanti giorni e' fermo. La data di rientro non e' un dato disponibile."""
    import datetime
    try:
        return (datetime.date.today() - datetime.date.fromisoformat(str(data_inizio))).days
    except Exception:
        return None


def _colonna(df, nome):
    return df[nome].apply(_num) if nome in df.columns else pd.Series(0.0, index=df.index)


# ----------------------------------------------------------------------
# CONTESTO SQUADRA
# ----------------------------------------------------------------------
def baseline_ruoli(df):
    """Fantamedia e bonus/partita medi per ruolo, fra chi ha giocato molto."""
    baseline = {}
    if df is None or df.empty:
        return {r: v for r, v in BASELINE_FALLBACK.items()}

    lavoro = df.copy()
    lavoro['_pv'] = _colonna(lavoro, 'Pv')
    lavoro['_fm'] = _colonna(lavoro, 'Fm')
    lavoro['_mv'] = _colonna(lavoro, 'Mv')
    affidabili = lavoro[(lavoro['_pv'] >= 15) & (lavoro['_fm'] > 0) & (lavoro['_mv'] > 0)]

    for ruolo, (fm_default, bonus_default) in BASELINE_FALLBACK.items():
        gruppo = affidabili[affidabili['R'].astype(str).str.upper() == ruolo]
        if len(gruppo) >= 10:
            baseline[ruolo] = (round(gruppo['_fm'].median(), 2),
                               round((gruppo['_fm'] - gruppo['_mv']).median(), 2))
        else:
            baseline[ruolo] = (fm_default, bonus_default)
    return baseline


def statistiche_squadre(df):
    """
    Gol subiti e gol fatti per squadra, ricavati dal listone stesso:
    i gol subiti sono quelli del portiere piu' impiegato.
    """
    risultato = {}
    lavoro = df.copy()
    lavoro['_gs'] = _colonna(lavoro, 'Gs')
    lavoro['_pv'] = _colonna(lavoro, 'Pv')
    lavoro['_gf'] = _colonna(lavoro, 'Gf')

    for squadra, gruppo in lavoro.groupby(lavoro['Squadra'].astype(str)):
        portieri = gruppo[gruppo['R'].astype(str).str.upper() == 'P'].sort_values('_pv', ascending=False)
        gs_totali = float(portieri['_gs'].sum())
        pv_portieri = float(portieri['_pv'].sum())
        risultato[squadra] = {
            'gol_subiti': gs_totali,
            'gol_subiti_partita': round(gs_totali / pv_portieri, 2) if pv_portieri > 0 else None,
            'gol_fatti': float(gruppo['_gf'].sum()),
        }
    return risultato


def classifica_difensiva(df):
    """Squadre ordinate dalla meno battuta: serve alla griglia difensiva."""
    stats = statistiche_squadre(df)
    valide = {s: d for s, d in stats.items() if d['gol_subiti_partita'] is not None}
    return sorted(valide.items(), key=lambda x: x[1]['gol_subiti_partita'])


# ----------------------------------------------------------------------
# PROFILO DEL SINGOLO GIOCATORE
# ----------------------------------------------------------------------
def _pondera(valore, presenze, riferimento):
    """Media pesata fra il dato del giocatore e quello del suo ruolo."""
    presenze = max(0.0, float(presenze))
    return (presenze * valore + K_PRESENZE * riferimento) / (presenze + K_PRESENZE)


def profilo(riga, contesto_squadre=None, baseline=None):
    """Trasforma una riga del Master nei numeri che servono a decidere."""
    pv = _num(riga.get('Pv'))
    mv = _num(riga.get('Mv'))
    fm = _num(riga.get('Fm'))
    gol = _num(riga.get('Gf'))
    assist = _num(riga.get('Ass'))
    rigori = _num(riga.get('Rc'))
    ammonizioni = _num(riga.get('Amm'))
    espulsioni = _num(riga.get('Esp'))

    # Presenze totali di stagione: chi arriva a gennaio ha poche gare in Serie A
    # ma non e' un panchinaro. Senza questa distinzione, un 14 gol in 18 partite
    # verrebbe segnalato come rischio invece che come affare.
    pv_totali = _num(riga.get('PvTot'), pv) or pv
    squadre_stagione = int(_num(riga.get('SquadreStag'), 1) or 1)
    # NON si deduce PERCHE' ha giocato poco in Serie A: infortunio, trasferimento
    # di gennaio, ritorno dall'estero e panchina producono gli stessi numeri.
    # Si espone solo il dato: quante gare in Serie A, quante in stagione.
    stagione_piena = pv > 0 and pv_totali >= pv * 1.4 and pv_totali >= 25

    # Gare saltate per infortunio nella stagione passata: e' il dato che
    # distingue chi si e' rotto da chi non veniva schierato.
    # Se il motore ha separato le cause, GareSaltate contiene SOLO gli infortuni
    # e GareSaltateAltro le squalifiche, le nazionali e i turni di riposo.
    # Sui file vecchi la seconda colonna non c'e' e vale 0: il comportamento
    # resta quello di prima.
    gare_saltate = int(_num(riga.get('GareSaltate')))
    gare_altre = int(_num(riga.get('GareSaltateAltro')))
    motivo_stop = traduci_causa(riga.get('MotivoStop'))
    fragile = gare_saltate >= 8

    # Perche' ha poche presenze? Chi parte titolare e gioca 80 minuti ogni volta
    # che c'e' non e' un panchinaro: le partite che mancano sono infortuni o
    # squalifiche. Chi invece entra sempre dalla panchina ha tante presenze e
    # pochi minuti. Sono due rischi diversi e vanno detti in modo diverso.
    da_titolare = _num(riga.get('Tit'))
    minuti = _num(riga.get('Min'))
    quota_titolare = (da_titolare / pv_totali) if pv_totali > 0 and da_titolare > 0 else None
    minuti_medi = (minuti / pv_totali) if pv_totali > 0 and minuti > 0 else None
    titolare_quando_disponibile = bool(
        quota_titolare is not None and quota_titolare >= 0.80 and
        minuti_medi is not None and minuti_medi >= 65
    )
    subentrante = bool(
        quota_titolare is not None and quota_titolare <= 0.45 and
        minuti_medi is not None and minuti_medi <= 45
    )

    titolarita = pv / PARTITE_STAGIONE if pv > 0 else 0.0
    titolarita_reale = titolarita
    if pv > 0:
        etichetta = next(nome for soglia, nome in SOGLIE_TITOLARITA
                         if titolarita_reale >= soglia)
        if fragile:
            etichetta = f"fragile: {gare_saltate} gare saltate"
        elif stagione_piena:
            etichetta += f" in Serie A ({pv_totali} gare in stagione)"
        elif titolare_quando_disponibile and titolarita_reale < 0.75:
            etichetta = "titolare, ma spesso indisponibile"
        elif subentrante:
            etichetta = "subentrante"
    elif fm > 0:
        etichetta = "nuovo in Serie A"
    else:
        etichetta = "nessun dato"

    # Il cuore: quanto della fantamedia arriva dai bonus e non dal voto
    bonus_partita = round(fm - mv, 2) if (fm > 0 and mv > 0) else 0.0

    ruolo_g = str(riga.get('R', '')).strip().upper()
    baseline = baseline or BASELINE_FALLBACK
    fm_rif, bonus_rif = baseline.get(ruolo_g, BASELINE_FALLBACK.get(ruolo_g, (6.0, 0.3)))
    # L'affidabilita' della fantamedia dipende dalle SOLE gare di Serie A su cui
    # e' calcolata: le partite giocate altrove non la rendono piu' solida. Un
    # 8.97 su 18 gare resta un campione da 18 gare, anche se in stagione ne ha 40.
    peso_presenze = pv
    fm_pond = round(_pondera(fm, peso_presenze, fm_rif), 2) if fm > 0 else 0.0
    bonus_pond = round(_pondera(bonus_partita, peso_presenze, bonus_rif), 2) if fm > 0 else 0.0

    infortunio = traduci_causa(riga.get('Infortunio'))
    tipo_infortunio = _testo(riga.get('InfortunioTipo'))

    dati = {
        'infortunato': bool(infortunio),
        'giorni_fermo': _giorni_fermo(riga.get('InfortunioDal')),
        'infortunio': infortunio,
        'infortunio_tipo': tipo_infortunio,
        'aggiornato': _testo(riga.get('Aggiornato')),
        'proiezione': pv == 0 and fm > 0,
        'senza_dati': pv == 0 and fm <= 0,
        'nome': str(riga.get('Nome', '')).strip(),
        'ruolo': str(riga.get('R', '')).strip().upper(),
        'squadra': str(riga.get('Squadra', '')).strip(),
        'prezzo': int(_num(riga.get('Prezzo'), 1)) or 1,
        'quotazione': _num(riga.get('Qt.A')),
        'fvm': _num(riga.get('FVM')),
        'presenze': int(pv),
        'presenze_totali': int(pv_totali),
        'squadre_stagione': squadre_stagione,
        'stagione_piena': stagione_piena,
        'gare_saltate': gare_saltate,
        'gare_altre': gare_altre,
        'motivo_stop': motivo_stop,
        'fragile': fragile,
        'da_titolare': int(da_titolare),
        'minuti_medi': round(minuti_medi, 1) if minuti_medi else None,
        'quota_titolare': round(quota_titolare, 2) if quota_titolare else None,
        'titolare_quando_disponibile': titolare_quando_disponibile,
        'subentrante': subentrante,
        'titolarita': round(titolarita, 2),
        'titolarita_reale': round(titolarita_reale, 2),
        'etichetta_titolarita': etichetta,
        'voto_puro': mv,
        'fantamedia': fm,
        'fantamedia_ponderata': fm_pond,
        'bonus_partita': bonus_partita,
        'bonus_ponderati': bonus_pond,
        'gol': int(gol),
        'assist': int(assist),
        'rigorista': rigori > 0,
        'rigori_calciati': int(rigori),
        'ammonizioni': int(ammonizioni),
        'espulsioni': int(espulsioni),
    }

    if contesto_squadre:
        squadra = contesto_squadre.get(dati['squadra'], {})
        dati['gol_subiti_squadra'] = squadra.get('gol_subiti')
        dati['gol_subiti_partita'] = squadra.get('gol_subiti_partita')

    # Quanto il modello interno si discosta dal valore ufficiale di mercato.
    # Sopra 1 il giocatore vale piu' di quanto lo paghi la lega: e' li' che
    # stanno le occasioni, non nella classifica dei piu' cari.
    dati['fvm_stima'] = _num(riga.get('FVM_Stima'))
    scarto = _num(riga.get('Scarto'))
    if scarto <= 0 and dati['fvm'] > 0 and dati['fvm_stima'] > 0:
        scarto = dati['fvm_stima'] / dati['fvm']
    dati['scarto'] = round(scarto, 2) if scarto > 0 else 0.0

    # Rendimento per credito speso: il bonus conta piu' del voto secco
    dati['resa_per_credito'] = round(
        ((fm_pond - 5.5) * (pv / PARTITE_STAGIONE)) / dati['prezzo'] * 100, 2
    ) if fm > 0 and dati['prezzo'] > 0 else 0.0

    return dati


# ----------------------------------------------------------------------
# CONFRONTO FRA DUE GIOCATORI
# ----------------------------------------------------------------------
def confronta(riga1, riga2, df=None, modificatore_difesa=False):
    """
    Confronta due giocatori e restituisce dati + verdetto motivato.
    I criteri seguono la gerarchia: bonus/fantamedia, presenze, contesto squadra.
    """
    contesto = statistiche_squadre(df) if df is not None else None
    baseline = baseline_ruoli(df)
    p1, p2 = profilo(riga1, contesto, baseline), profilo(riga2, contesto, baseline)

    voci = []          # (etichetta, valore1, valore2, chi_vince, peso)

    def confronta_voce(etichetta, chiave, peso, piu_e_meglio=True, formato="{:.2f}"):
        v1, v2 = p1.get(chiave) or 0, p2.get(chiave) or 0
        if v1 == v2:
            vincitore = 0
        elif (v1 > v2) == piu_e_meglio:
            vincitore = 1
        else:
            vincitore = 2
        voci.append({
            'etichetta': etichetta,
            'v1': formato.format(v1) if isinstance(v1, float) else str(v1),
            'v2': formato.format(v2) if isinstance(v2, float) else str(v2),
            'vincitore': vincitore,
            'peso': peso,
        })
        return vincitore, peso

    punteggio = {1: 0.0, 2: 0.0}

    def registra(risultato):
        vincitore, peso = risultato
        if vincitore:
            punteggio[vincitore] += peso

    # 1. Bonus e fantamedia: il criterio principale
    registra(confronta_voce("Bonus a partita", 'bonus_ponderati', 3.0))
    registra(confronta_voce("Fantamedia", 'fantamedia_ponderata', 2.5))
    registra(confronta_voce("Gol", 'gol', 1.5, formato="{:.0f}"))
    registra(confronta_voce("Assist", 'assist', 1.0, formato="{:.0f}"))

    # 2. Presenze: senza voti non c'e' fantamedia
    registra(confronta_voce("Presenze", 'presenze', 2.5, formato="{:.0f}"))

    # 3. Contesto: voto puro (risente dei gol subiti) e disciplina
    registra(confronta_voce("Voto puro", 'voto_puro', 1.5))
    registra(confronta_voce("Ammonizioni", 'ammonizioni', 0.5,
                            piu_e_meglio=False, formato="{:.0f}"))

    if modificatore_difesa and p1['ruolo'] in ('P', 'D') and p2['ruolo'] in ('P', 'D'):
        registra(confronta_voce("Gol subiti squadra", 'gol_subiti_partita', 2.0,
                                piu_e_meglio=False))

    # Il prezzo non decide chi e' piu' forte, ma quanto costa esserlo
    differenza_prezzo = p1['prezzo'] - p2['prezzo']

    if p1['rigorista'] != p2['rigorista']:
        vincitore = 1 if p1['rigorista'] else 2
        punteggio[vincitore] += 1.5
        voci.append({
            'etichetta': "Rigorista",
            'v1': f"si ({p1['rigori_calciati']})" if p1['rigorista'] else "no",
            'v2': f"si ({p2['rigori_calciati']})" if p2['rigorista'] else "no",
            'vincitore': vincitore, 'peso': 1.5,
        })

    migliore = 1 if punteggio[1] > punteggio[2] else (2 if punteggio[2] > punteggio[1] else 0)
    vincente, perdente = (p1, p2) if migliore == 1 else (p2, p1)

    motivi = []
    if migliore:
        if vincente['bonus_ponderati'] > perdente['bonus_ponderati'] + 0.05:
            motivi.append(f"porta {vincente['bonus_ponderati']:.2f} di bonus a partita "
                          f"contro {perdente['bonus_ponderati']:.2f}")
        if vincente['presenze'] > perdente['presenze'] + 4:
            motivi.append(f"ha giocato {vincente['presenze'] - perdente['presenze']} partite in piu'")
        if vincente['rigorista'] and not perdente['rigorista']:
            motivi.append("tira i rigori")
        if perdente['titolarita'] < 0.6 <= vincente['titolarita']:
            motivi.append(f"l'altro e' un {perdente['etichetta_titolarita']}")

        costo = vincente['prezzo'] - perdente['prezzo']
        if costo > 0:
            motivi.append(f"ma costa {costo} crediti in piu'")
        elif costo < 0:
            motivi.append(f"e costa pure {abs(costo)} crediti in meno")

    return {
        'p1': p1, 'p2': p2, 'voci': voci,
        'punteggio': punteggio,
        'migliore': migliore,
        'differenza_prezzo': differenza_prezzo,
        'motivi': motivi,
    }


def formatta_confronto(esito):
    """Rende il confronto in HTML per Telegram."""
    p1, p2 = esito['p1'], esito['p2']
    righe = [f"⚖️ <b>{p1['nome'].upper()}</b>  vs  <b>{p2['nome'].upper()}</b>",
             f"<i>{p1['squadra']} · {p1['prezzo']} cr</i>  |  <i>{p2['squadra']} · {p2['prezzo']} cr</i>",
             "━━━━━━━━━━━━━━━━━━━━"]

    for voce in esito['voci']:
        segno = {0: "=", 1: "◀", 2: "▶"}[voce['vincitore']]
        righe.append(f"{voce['etichetta']}: <b>{voce['v1']}</b> {segno} <b>{voce['v2']}</b>")

    righe.append("━━━━━━━━━━━━━━━━━━━━")
    for profilo_g in (p1, p2):
        righe.append(f"{profilo_g['nome']}: {profilo_g['etichetta_titolarita']} "
                     f"({profilo_g['presenze']} pres., Fm reale {profilo_g['fantamedia']:.2f})")

    if esito['migliore']:
        vincente = p1 if esito['migliore'] == 1 else p2
        righe.append("")
        righe.append(f"✅ <b>Meglio {vincente['nome'].upper()}</b>: " + ", ".join(esito['motivi']) + ".")
    else:
        righe.append("")
        righe.append("🤝 <b>Equivalenti</b>: decidi sul prezzo.")

    return "\n".join(righe)


# ----------------------------------------------------------------------
# FASCE: definite da QUANTI NE ESISTONO, non da soglie in crediti
# ----------------------------------------------------------------------
# Con 8 squadre, i primi 8 attaccanti sono "Top" perche' ce n'e' uno per
# squadra: chi non lo prende resta senza. Soglie in crediti fisse (es. "1a
# fascia sopra 110") si rompono appena cambia il budget della lega.
SLOT_RUOLO = {'P': 3, 'D': 8, 'C': 8, 'A': 6}

# Sei livelli: la corona sta sopra l'oro, chiave inglese e dado sotto il bronzo.
# Cosi' le tre medaglie restano, ma la scala copre tutte le fasce d'asta.
FASCE_ETICHETTE = [
    ('top',        '👑 TOP'),
    ('semitop',    '🥇 SEMI-TOP'),
    ('seconda',    '🥈 2ª FASCIA'),
    ('terza',      '🥉 3ª FASCIA'),
    ('quarta',     '🔧 4ª/5ª FASCIA'),
    ('scommessa',  '🎲 SCOMMESSE'),
]

FASCE = {nome: etichetta for nome, etichetta in FASCE_ETICHETTE}


def soglie_fasce(ruolo, squadre=8):
    """Confini delle fasce espressi in posizioni, non in crediti."""
    slot = SLOT_RUOLO.get(str(ruolo).upper(), 8)
    titolari = slot * squadre          # quanti ne verranno comprati in totale

    # Frazioni dei titolari, non multipli fissi del numero di squadre: con soli
    # 3 slot (portieri) le fasce alte avrebbero divorato tutte le altre.
    grezze = [
        ('top',       titolari * 0.08),
        ('semitop',   titolari * 0.25),
        ('seconda',   titolari * 0.50),
        ('terza',     titolari * 1.00),
        ('quarta',    titolari * 1.60),
    ]

    soglie, precedente = {}, 0
    for nome, valore in grezze:
        # ogni fascia deve contenere almeno un giocatore
        precedente = max(precedente + 1, int(round(valore)))
        soglie[nome] = precedente
    return soglie


def _classifica_ruolo(df, ruolo):
    """Giocatori del ruolo ordinati per valore, dal piu' caro."""
    gruppo = df[df['R'].astype(str).str.upper() == str(ruolo).upper()].copy()
    if gruppo.empty:
        return gruppo
    colonna = 'Prezzo' if 'Prezzo' in gruppo.columns else 'FVM'
    gruppo['_valore'] = _colonna(gruppo, colonna)
    return gruppo.sort_values('_valore', ascending=False)


def fascia_giocatore(nome, df, squadre=8):
    """
    Fascia di un singolo giocatore: (chiave, etichetta, posizione, totale).
    La posizione e' il suo rango nel ruolo, il dato piu' utile all'asta.
    """
    riga = df[df['Nome'].astype(str) == str(nome).strip()]
    if riga.empty:
        return None
    ruolo = str(riga.iloc[0].get('R', '')).upper()

    ordinati = _classifica_ruolo(df, ruolo)
    if ordinati.empty:
        return None

    nomi = list(ordinati['Nome'].astype(str))
    if str(nome).strip() not in nomi:
        return None
    posizione = nomi.index(str(nome).strip()) + 1

    soglie = soglie_fasce(ruolo, squadre)
    chiave = 'scommessa'
    for nome_fascia in ('top', 'semitop', 'seconda', 'terza', 'quarta'):
        if posizione <= soglie[nome_fascia]:
            chiave = nome_fascia
            break

    return chiave, FASCE[chiave], posizione, len(nomi)


PRESENZE_CONFRONTO = 15


def _metriche_ruolo(gruppo, ruolo):
    """
    Le metriche su cui ha senso confrontare due giocatori dello stesso ruolo.
    (etichetta, serie di valori, piu_e_meglio). Su un portiere il gol non
    significa niente e i gol subiti si': non e' lo stesso elenco per tutti.
    """
    # L'ultimo campo dice se la metrica puo' finire fra i DIFETTI. Non tutte
    # possono: quasi ogni portiere ha zero rigori parati e quasi ogni difensore
    # zero assist, quindi segnalarli come punti deboli e' solo rumore. Un
    # primato invece resta un primato.
    pv = gruppo['_pv'].replace(0, pd.NA)
    if ruolo == 'P':
        return [
            ("gol subiti/gara", gruppo['_gs'] / pv, False, True),
            ("voto puro", gruppo['_mv'], True, True),
            ("fantamedia", gruppo['_fm'], True, True),
            ("rigori parati", gruppo['_rp'], True, False),
        ]
    return [
        ("gol", gruppo['_gf'], True, False),
        ("assist", gruppo['_ass'], True, False),
        ("fantamedia", gruppo['_fm'], True, True),
        ("bonus/gara", gruppo['_fm'] - gruppo['_mv'], True, True),
        ("ammonizioni/gara", gruppo['_amm'] / pv, False, True),
    ]


def percentili_ruolo(riga, df, presenze_minime=PRESENZE_CONFRONTO):
    """
    In che posizione sta, dentro il suo ruolo, su ogni metrica.

    "Fantamedia 6.62" non dice niente; "4a fra 97 difensori" dice tutto. E' lo
    stesso principio delle fasce - contano la scarsita' e il confronto, non il
    valore assoluto - applicato al rendimento invece che al prezzo.

    Il confronto e' solo fra chi ha almeno 15 presenze: una media su 3 partite
    non e' paragonabile a una su 34.
    """
    if df is None or df.empty:
        return None
    ruolo = str(riga.get('R', '')).strip().upper()
    nome = str(riga.get('Nome', '')).strip()

    gruppo = df[df['R'].astype(str).str.upper() == ruolo].copy()
    for chiave, colonna in (('_pv', 'Pv'), ('_mv', 'Mv'), ('_fm', 'Fm'), ('_gf', 'Gf'),
                            ('_gs', 'Gs'), ('_ass', 'Ass'), ('_amm', 'Amm'), ('_rp', 'Rp')):
        gruppo[chiave] = _colonna(gruppo, colonna)
    gruppo = gruppo[(gruppo['_pv'] >= presenze_minime) & (gruppo['_fm'] > 0)]

    totale = len(gruppo)
    if totale < 12 or nome not in set(gruppo['Nome'].astype(str)):
        return None      # troppo pochi per un confronto onesto

    posizione_riga = gruppo['Nome'].astype(str) == nome
    forze, debolezze = [], []

    for etichetta, valori, piu_e_meglio, vale_come_difetto in _metriche_ruolo(gruppo, ruolo):
        valori = pd.to_numeric(valori, errors='coerce').fillna(0.0)
        mio = float(valori[posizione_riga].iloc[0])
        migliori = int((valori > mio).sum() if piu_e_meglio else (valori < mio).sum())
        rango = migliori + 1

        if rango <= max(3, totale / 3):
            forze.append((etichetta, rango, mio))
        elif vale_come_difetto and rango > totale * 2 / 3:
            debolezze.append((etichetta, rango, mio))

    forze.sort(key=lambda x: x[1])
    debolezze.sort(key=lambda x: -x[1])
    return {'totale': totale, 'ruolo': ruolo,
            'forze': forze[:2], 'debolezze': debolezze[:1]}


def righe_percentili(esito):
    """Due righe al massimo: i primati veri e l'unico difetto che pesa."""
    if not esito:
        return ""
    nome_ruolo = {'P': 'portieri', 'D': 'difensori',
                  'C': 'centrocampisti', 'A': 'attaccanti'}.get(esito['ruolo'], 'giocatori')
    righe = []
    if esito['forze']:
        voci = " · ".join(f"{et} {rango}°" for et, rango, _ in esito['forze'])
        righe.append(f"📊 fra {esito['totale']} {nome_ruolo}: {voci}")
    if esito['debolezze']:
        et, rango, _ = esito['debolezze'][0]
        righe.append(f"📉 {et} {rango}° su {esito['totale']}")
    return "\n".join(righe)


def riga_bonus(prof):
    """
    Da dove arriva il bonus. "+0.43 a partita" e' identico per Barella
    (3 gol, 9 assist) e per Kone I. (6 gol, 0 assist), che sono due giocatori
    opposti: la media da sola nasconde la differenza.

    Il rigorista va scritto sempre: all'asta vale dieci crediti in piu' e
    prima finiva sepolto fra i punti di forza, quindi quasi mai visibile.
    """
    pezzi = []
    if prof['gol'] or prof['assist']:
        pezzi.append(f"<b>{prof['gol']}</b> gol")
        pezzi.append(f"<b>{prof['assist']}</b> assist")
    if prof['rigorista']:
        calciati = prof['rigori_calciati']
        pezzi.append(f"⚽ <b>rigorista</b> ({calciati} calciat{'o' if calciati == 1 else 'i'})")
    return "  ·  ".join(pezzi)


def contesto_asta(nome, df, nomi_disponibili=None, squadre=8):
    """
    Le due domande vere di un'asta: quanto e' raro, e quanti ne restano.

    La fascia da sola non basta: "TOP" non dice se ne sono liberi cinque o uno.
    Il rango si calcola SEMPRE sul listone intero (altrimenti cambierebbe a ogni
    acquisto altrui), mentre i rimasti si contano fra i disponibili.

    Restituisce None se il giocatore non e' nel listone.
    """
    esito = fascia_giocatore(nome, df, squadre)
    if not esito:
        return None
    chiave, etichetta, posizione, totale = esito

    ruolo = str(df[df['Nome'].astype(str) == str(nome).strip()].iloc[0].get('R', '')).upper()
    in_fascia = fascia(df, ruolo, chiave, squadre)
    totale_fascia = 0 if in_fascia is None else len(in_fascia)

    if nomi_disponibili is None:
        rimasti = totale_fascia
    else:
        disponibili = set(nomi_disponibili)
        rimasti = 0 if in_fascia is None else int(
            in_fascia['Nome'].astype(str).isin(disponibili).sum())

    return {
        'chiave': chiave,
        'etichetta': etichetta,
        'posizione': posizione,
        'totale_ruolo': totale,
        'ruolo': ruolo,
        'totale_fascia': totale_fascia,
        'rimasti_fascia': rimasti,
    }


def riga_contesto(contesto, prof):
    """
    La riga compatta sotto il prezzo. Tiene insieme scarsita' e valore, che
    sono le due cose che fanno alzare o mollare: 'RESTANO 2 SU 6 · STIMA 61 CR (+27%)'.
    """
    pezzi = []
    if contesto:
        rimasti, totale = contesto['rimasti_fascia'], contesto['totale_fascia']
        if totale:
            if rimasti <= 0:
                pezzi.append("NESSUN ALTRO IN FASCIA")
            elif rimasti == 1:
                pezzi.append(f"ULTIMO DEI {totale} IN FASCIA")
            elif rimasti == totale:
                pezzi.append(f"{totale} IN QUESTA FASCIA")
            else:
                pezzi.append(f"RESTANO {rimasti} SU {totale} IN FASCIA")

    stima, scarto = prof.get('fvm_stima', 0), prof.get('scarto', 0)
    if stima > 0 and scarto > 0:
        differenza = round((scarto - 1) * 100)
        if abs(differenza) >= 10:
            pezzi.append(f"STIMA {differenza:+d}% SUL MERCATO")

    return "   ·   ".join(pezzi)


def fascia(df, ruolo, nome_fascia, squadre=8, solo_con_dati=True):
    """Tutti i giocatori di una fascia, dal piu' caro."""
    if df is None or df.empty or nome_fascia not in FASCE:
        return df.iloc[0:0] if df is not None else None

    ordinati = _classifica_ruolo(df, ruolo)
    if ordinati.empty:
        return ordinati
    if solo_con_dati:
        ordinati = ordinati[ordinati['_valore'] > 0]

    soglie = soglie_fasce(ruolo, squadre)
    ordine = ['top', 'semitop', 'seconda', 'terza', 'quarta']
    confini, precedente = {}, 0
    for nome in ordine:
        confini[nome] = (precedente, soglie[nome])
        precedente = soglie[nome]
    confini['scommessa'] = (precedente, len(ordinati))
    inizio, fine = confini[nome_fascia]
    return ordinati.iloc[inizio:fine]


# ----------------------------------------------------------------------
# CLASSIFICHE UTILI (ordinamenti, non sorteggi)
# ----------------------------------------------------------------------
def migliori_per_resa(df, ruolo=None, limite=10, prezzo_massimo=None):
    """Chi rende di piu' per credito speso: il vero 'tappabuchi'."""
    if df is None or df.empty:
        return df
    lavoro = df.copy()
    if ruolo:
        lavoro = lavoro[lavoro['R'].astype(str).str.upper() == str(ruolo).upper()]
    if prezzo_massimo is not None:
        lavoro = lavoro[_colonna(lavoro, 'Prezzo') <= prezzo_massimo]
    if lavoro.empty:
        return lavoro

    contesto = statistiche_squadre(df)
    riferimenti = baseline_ruoli(df)
    lavoro['_resa'] = [profilo(r, contesto, riferimenti)['resa_per_credito']
                       for _, r in lavoro.iterrows()]
    return lavoro[lavoro['_resa'] > 0].sort_values('_resa', ascending=False).head(limite)


def stakanovisti(df, ruoli=('D', 'C'), limite=10, presenze_minime=25):
    """Titolari inamovibili a basso costo: si ordina per presenze, non per FVM."""
    if df is None or df.empty:
        return df
    lavoro = df[df['R'].astype(str).str.upper().isin([r.upper() for r in ruoli])].copy()
    lavoro['_pv'] = _colonna(lavoro, 'Pv')
    lavoro['_prezzo'] = _colonna(lavoro, 'Prezzo')
    lavoro = lavoro[lavoro['_pv'] >= presenze_minime]
    return lavoro.sort_values(['_pv', '_prezzo'], ascending=[False, True]).head(limite)


def griglia_difensiva(df, limite_squadre=6, per_squadra=2):
    """
    Difensori delle squadre meno battute, con presenze alte.
    Le squadre arrivano dai dati, non da una lista scritta a mano.
    """
    if df is None or df.empty:
        return df
    migliori = [s for s, _ in classifica_difensiva(df)[:limite_squadre]]
    lavoro = df[(df['R'].astype(str).str.upper() == 'D') &
                (df['Squadra'].astype(str).isin(migliori))].copy()
    if lavoro.empty:
        return lavoro

    lavoro['_pv'] = _colonna(lavoro, 'Pv')
    lavoro['_fm'] = _colonna(lavoro, 'Fm')
    selezione = (lavoro.sort_values(['_pv', '_fm'], ascending=False)
                 .groupby('Squadra').head(per_squadra))
    return selezione.sort_values(['_fm', '_pv'], ascending=False)


def candidati_modificatore(df, limite=15, presenze_minime=20):
    """
    Difensori utili al modificatore di difesa: conta il VOTO PURO (Mv), non la
    fantamedia, perche' il modificatore si calcola sui voti. Pesano anche le
    presenze e il fatto di giocare in una squadra che subisce pochi gol.
    """
    if df is None or df.empty:
        return df
    lavoro = df[df['R'].astype(str).str.upper() == 'D'].copy()
    if lavoro.empty:
        return lavoro

    lavoro['_pv'] = _colonna(lavoro, 'Pv')
    lavoro['_mv'] = _colonna(lavoro, 'Mv')
    lavoro = lavoro[(lavoro['_pv'] >= presenze_minime) & (lavoro['_mv'] > 0)]
    if lavoro.empty:
        return lavoro

    difese = {s: d['gol_subiti_partita'] for s, d in statistiche_squadre(df).items()
              if d['gol_subiti_partita'] is not None}
    media_gol_subiti = sum(difese.values()) / len(difese) if difese else 1.3

    riferimento = BASELINE_FALLBACK['D'][0]

    def punteggio(riga):
        mv_pond = _pondera(_num(riga['_mv']), _num(riga['_pv']), riferimento)
        subiti = difese.get(str(riga['Squadra']), media_gol_subiti)
        # mezzo punto di bonus per ogni gol subito in meno rispetto alla media
        return mv_pond + (media_gol_subiti - subiti) * 0.5

    lavoro['_score'] = [round(punteggio(r), 3) for _, r in lavoro.iterrows()]
    lavoro['_gol_subiti_squadra'] = [round(difese.get(str(r['Squadra']), media_gol_subiti), 2)
                                     for _, r in lavoro.iterrows()]
    return lavoro.sort_values('_score', ascending=False).head(limite)


def scommesse(df, limite=12, squadre=8):
    """
    Poco costosi ma con rendimento sopra la media del ruolo.
    Pesca dalle due fasce basse: 'quarta' e 'scommessa'. (La vecchia fascia
    'gemme' non esiste piu' da quando le fasce sono sei: chiederla restituiva
    sempre zero giocatori e il pulsante SCOMMESSE non rispondeva mai.)
    """
    if df is None or df.empty:
        return df
    pezzi = [fascia(df, ruolo, nome_fascia, squadre)
             for ruolo in ('P', 'D', 'C', 'A')
             for nome_fascia in ('quarta', 'scommessa')]
    pezzi = [p for p in pezzi if p is not None and not p.empty]
    if not pezzi:
        return df.iloc[0:0]
    insieme = pd.concat(pezzi)
    return migliori_per_resa(insieme, limite=limite)


# ----------------------------------------------------------------------
# RISCHIO: non e' una fascia, e' un asse a parte.
# Un giocatore puo' essere TOP e insieme da evitare (caro e mai in campo).
# ----------------------------------------------------------------------
LIVELLI_RISCHIO = [
    (4.0, 'evita',      '⛔ DA EVITARE'),
    (2.0, 'attenzione', '⚠️ ATTENZIONE'),
    (0.8, 'lieve',      '🟨 QUALCHE DUBBIO'),
    (0.0, 'nessuno',    '✅ NESSUN ALLARME'),
]

# Sotto queste soglie di bonus a partita un giocatore offensivo non incide
BONUS_ATTESI = {'A': 0.45, 'C': 0.25, 'D': 0.10, 'P': 0.0}

# Lo stesso difetto pesa diversamente secondo il prezzo: 8 presenze in un TOP
# sono un disastro, in una scommessa da 2 crediti sono il prezzo del biglietto.
PESO_FASCIA = {
    'top': 1.25, 'semitop': 1.15, 'seconda': 1.0,
    'terza': 0.75, 'quarta': 0.5, 'scommessa': 0.4,
}


def valuta_rischio(riga, df, squadre=8):
    """
    Restituisce livello, motivi e punti di forza. Ogni segnale pesa: serve
    piu' di un indizio per arrivare a 'da evitare', perche' un singolo dato
    fuori media capita a tutti.
    """
    baseline = baseline_ruoli(df)
    contesto = statistiche_squadre(df)
    prof = profilo(riga, contesto, baseline)
    ruolo = prof['ruolo']
    fm_rif, bonus_rif = baseline.get(ruolo, (6.0, 0.3))

    punteggio = 0.0
    motivi, forze = [], []

    # --- 0. Indisponibile adesso: e' l'informazione piu' urgente della card ---
    if prof['infortunato']:
        # Piu' a lungo dura lo stop, piu' pesa: un dato certo, non una previsione
        giorni = prof.get('giorni_fermo') or 0
        in_dubbio = str(prof['infortunio_tipo']).lower() == 'questionable'
        if in_dubbio:
            punteggio += 1.0
        elif giorni >= 30:
            punteggio += 3.0
        elif giorni >= 10:
            punteggio += 2.5
        else:
            punteggio += 2.0

        dettaglio = prof['infortunio'] or prof['infortunio_tipo']
        testo = f"{'in dubbio' if in_dubbio else 'FERMO ORA'}: {dettaglio}"
        if giorni > 0:
            testo += f", da {giorni} giorni"
        motivi.append(testo)

    # --- Caso speciale: nessun dato su cui giudicare ---
    if prof['senza_dati']:
        esito = fascia_giocatore(prof['nome'], df, squadre)
        # Il rango da solo inganna: fra i difensori il #16 puo' costare 11 crediti.
        # Conta quanto costa davvero rispetto agli altri del suo ruolo.
        prezzi_ruolo = _colonna(df[df['R'].astype(str).str.upper() == ruolo], 'Prezzo')
        mediana = prezzi_ruolo[prezzi_ruolo > 0].median() if not prezzi_ruolo.empty else 0
        caro = mediana and prof['prezzo'] >= max(10, mediana * 2.5)

        punteggio += 3.5 if caro else 1.0
        motivi.append("nessuna statistica disponibile: e' un'incognita totale"
                      + (f", e costa {prof['prezzo']} crediti" if caro else ""))
        peso = PESO_FASCIA.get(esito[0], 1.0) if esito else 1.0
        return _confeziona_rischio(punteggio * peso, motivi, forze, prof)

    if prof['proiezione']:
        punteggio += 1.0
        motivi.append(f"mai giocato in Serie A: la {prof['fantamedia']:.2f} e' una stima")

    # --- 1. Titolarita': si guarda la stagione intera, non solo la Serie A ---
    if prof['presenze'] > 0:
        if prof['fragile']:
            # Ora il motivo si sa: ha saltato partite per infortunio
            causa = prof['motivo_stop']
            minuscolo = causa.lower()
            dettaglio = f"per {causa[0].lower() + causa[1:]}" if causa else "per infortunio"

            # Squalifiche e assenze non fisiche non fanno di uno un giocatore fragile
            if 'squalific' in minuscolo or 'espulsione' in minuscolo:
                punteggio += 0.8
                conclusione = "problema disciplinare"
            elif any(x in minuscolo for x in ('nazionale', 'motivi personali', 'riposo')):
                punteggio += 0.3
                conclusione = "assenze non fisiche"
            else:
                punteggio += 1.0 if prof['gare_saltate'] < 15 else 2.0
                conclusione = "giocatore fragile"

            motivi.append(f"ha saltato {prof['gare_saltate']} gare {dettaglio}: {conclusione}")
        elif prof['stagione_piena']:
            # Ha giocato tanto, ma non in Serie A: trasferimento o rientro.
            # ATTENZIONE: qui NON si puo' usare il nome 'squadre', che e' il
            # parametro con i partecipanti della lega e serve piu' sotto per
            # calcolare la fascia. Sovrascriverlo faceva calcolare le soglie
            # su 2-3 squadre invece che su 8, falsando fascia e peso.
            club_in_stagione = prof['squadre_stagione']
            punteggio += 0.8
            motivi.append(f"solo {prof['presenze']} gare in Serie A, "
                          f"{prof['presenze_totali']} in stagione"
                          + (f" con {club_in_stagione} squadre" if club_in_stagione > 1 else ""))
        elif prof['titolare_quando_disponibile'] and prof['titolarita_reale'] < 0.75:
            # Titolare vero, ma assente a lungo: rischio fisico, non gerarchia
            punteggio += 1.2
            partite_perse = PARTITE_STAGIONE - int(prof['presenze'])
            motivi.append(f"titolare quando c'e' ({prof['minuti_medi']:.0f} min a partita) "
                          f"ma ha saltato {partite_perse} gare di campionato")
        elif prof['subentrante']:
            punteggio += 2.0
            motivi.append(f"quasi sempre subentrante ({prof['minuti_medi']:.0f} min a partita)")
        elif prof['titolarita_reale'] < 0.45:
            punteggio += 2.0
            motivi.append(f"solo {prof['presenze']} presenze su {PARTITE_STAGIONE}")
        elif prof['titolarita_reale'] < 0.62 and not prof['fragile']:
            punteggio += 1.0
            motivi.append(f"{prof['presenze']} presenze: non e' un titolare fisso")
        elif prof['titolarita_reale'] >= 0.85:
            forze.append(f"inamovibile ({prof['presenze_totali']} presenze in stagione)")

    # --- 2. Bonus: per chi attacca, non portarne e' il difetto peggiore ---
    if prof['presenze'] >= 10:
        atteso = BONUS_ATTESI.get(ruolo, 0.2)
        if ruolo in ('A', 'C') and prof['bonus_partita'] < atteso:
            punteggio += 1.5
            motivi.append(f"bonus quasi assenti ({prof['bonus_partita']:+.2f} a partita)")
        elif prof['bonus_partita'] >= max(0.25, bonus_rif * 1.5):
            forze.append(f"{prof['bonus_partita']:+.2f} di bonus a partita")

    # --- 3. Voto puro sotto la media del ruolo ---
    if prof['presenze'] >= 10 and prof['voto_puro'] > 0:
        if prof['voto_puro'] < fm_rif - 0.35:
            punteggio += 1.0
            motivi.append(f"voto puro basso ({prof['voto_puro']:.2f})")

    # --- 4. Disciplina ---
    if prof['presenze'] >= 10:
        gialli_partita = prof['ammonizioni'] / prof['presenze']
        if gialli_partita >= 0.22:
            punteggio += 1.0
            motivi.append(f"{prof['ammonizioni']} ammonizioni: malus ricorrente")
        if prof['espulsioni'] >= 2:
            punteggio += 0.5
            motivi.append(f"{prof['espulsioni']} espulsioni")

    # --- 5. Squadra che subisce troppo (pesa su difensori e portieri) ---
    subiti = prof.get('gol_subiti_partita')
    if ruolo in ('P', 'D') and subiti:
        medie = [d['gol_subiti_partita'] for d in contesto.values()
                 if d['gol_subiti_partita'] is not None]
        media_lega = sum(medie) / len(medie) if medie else 1.3
        if subiti > media_lega * 1.25:
            punteggio += 1.0
            motivi.append(f"difesa fragile: {subiti} gol subiti a partita")
        elif subiti < media_lega * 0.8:
            forze.append(f"difesa solida ({subiti} gol subiti a partita)")

    # --- 6. Il rischio peggiore: pagare da fascia alta chi non scende in campo ---
    esito = fascia_giocatore(prof['nome'], df, squadre)
    fascia_alta = esito and esito[0] in ('top', 'semitop', 'seconda')
    if fascia_alta:
        nome_fascia = esito[1].split(maxsplit=1)[1].lower()
        if prof['stagione_piena'] or prof['titolare_quando_disponibile']:
            pass          # ha giocato: il poco impiego in Serie A ha altre cause
        elif prof['presenze'] > 0 and prof['titolarita_reale'] < 0.45:
            punteggio += 2.5
            motivi.append(f"costa da {nome_fascia} ma ha giocato "
                          f"{prof['presenze']} partite su {PARTITE_STAGIONE}")
        elif prof['presenze'] > 0 and prof['titolarita_reale'] < 0.62:
            punteggio += 1.5
            motivi.append(f"costa da {nome_fascia} senza essere un titolare fisso")

        if prof['fantamedia_ponderata'] < fm_rif and prof['presenze'] >= 10:
            punteggio += 2.0
            motivi.append(f"prezzo da {nome_fascia}, rendimento sotto la media di ruolo")

    # Assenze non fisiche: e' un fatto da dire, non una fragilita' da pesare.
    if prof['gare_altre'] >= 4 and not prof['fragile']:
        motivi.append(f"{prof['gare_altre']} gare saltate per squalifiche, "
                      f"nazionale o turnover")

    if prof['rigorista']:
        forze.append(f"rigorista ({prof['rigori_calciati']} calciati)")

    # Il rischio si misura su quanto costa: si scala per la fascia
    peso = PESO_FASCIA.get(esito[0], 1.0) if esito else 1.0
    return _confeziona_rischio(punteggio * peso, motivi, forze, prof)


def _confeziona_rischio(punteggio, motivi, forze, prof):
    livello, etichetta = next((chiave, testo) for soglia, chiave, testo in LIVELLI_RISCHIO
                              if punteggio >= soglia)
    return {
        'livello': livello,
        'etichetta': etichetta,
        'punteggio': round(punteggio, 1),
        'motivi': motivi,
        'forze': forze,
        'nome': prof['nome'],
    }


MESI = ['gennaio', 'febbraio', 'marzo', 'aprile', 'maggio', 'giugno', 'luglio',
        'agosto', 'settembre', 'ottobre', 'novembre', 'dicembre']


def _data_leggibile(iso):
    """'2026-10-12' -> '12 ottobre'."""
    try:
        anno, mese, giorno = (int(x) for x in str(iso).split('-'))
        return f"{giorno} {MESI[mese - 1]}"
    except Exception:
        return str(iso)


def banner_infortunio(riga):
    """Riga dedicata in cima alla card: se e' fermo, si deve vedere subito."""
    infortunio = traduci_causa(riga.get('Infortunio'))
    if not infortunio:
        return ""

    tipo = _testo(riga.get('InfortunioTipo'))
    aggiornato = _testo(riga.get('Aggiornato'))
    dal = _testo(riga.get('InfortunioDal'))

    etichetta = "🩹 <b>IN DUBBIO</b>" if tipo.lower() == 'questionable' else "🚑 <b>INDISPONIBILE</b>"
    righe = [f"{etichetta}: {infortunio}"]

    if dal:
        giorni = _giorni_fermo(dal)
        durata = f" ({giorni} giorni)" if giorni and giorni > 0 else ""
        righe.append(f"   📅 fermo dal {_data_leggibile(dal)}{durata}")

    if aggiornato:
        righe.append(f"   <i>dato aggiornato al {_data_leggibile(aggiornato)}</i>")
    return "\n".join(righe)


def formatta_rischio(esito, compatto=True):
    """Riga per la card: il timbro da solo non serve, servono i motivi."""
    if not esito:
        return "—"
    if esito['livello'] == 'nessuno':
        testo = esito['etichetta']
        if esito['forze']:
            testo += f" · {esito['forze'][0]}"
        return testo

    motivi = esito['motivi'][:2] if compatto else esito['motivi']
    testo = f"{esito['etichetta']}\n" + "\n".join(f"   └ {m}" for m in motivi)
    if esito['forze']:
        testo += f"\n   ✓ {esito['forze'][0]}"
    return testo