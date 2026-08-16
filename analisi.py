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

# Valori bonus/malus del fantacalcio classico. L'assist "soft" vale meno nelle
# leghe con assist quality: si puo' cambiare qui senza toccare il resto.
PESI = {
    'gol': 3.0,
    'assist': 1.0,
    'assist_soft': 0.5,
    'ammonizione': -0.5,
    'espulsione': -1.0,
    'rigore_sbagliato': -3.0,
    'rigore_parato': 3.0,
}

SOGLIE_TITOLARITA = [(0.80, "inamovibile"), (0.60, "titolare"),
                     (0.35, "alternanza"), (0.0, "riserva")]

# Le medie a partita su poche presenze non sono confrontabili: vengono
# avvicinate alla media del ruolo. Con K=8, chi ha 8 presenze pesa meta'
# se stesso e meta' baseline. Senza questo, un giocatore con 1 partita da
# 9.50 batterebbe chi ne ha fatte 36 a 7.38.
K_PRESENZE = 8
BASELINE_FALLBACK = {'P': (5.0, 0.1), 'D': (5.8, 0.2), 'C': (6.0, 0.4), 'A': (6.2, 0.7)}


def _num(valore, default=0.0):
    n = pd.to_numeric(str(valore).replace(',', '.'), errors='coerce')
    return default if pd.isna(n) else float(n)


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

    titolarita = pv / PARTITE_STAGIONE if pv > 0 else 0.0
    etichetta = next(nome for soglia, nome in SOGLIE_TITOLARITA if titolarita >= soglia)

    # Il cuore: quanto della fantamedia arriva dai bonus e non dal voto
    bonus_partita = round(fm - mv, 2) if (fm > 0 and mv > 0) else 0.0

    ruolo_g = str(riga.get('R', '')).strip().upper()
    baseline = baseline or BASELINE_FALLBACK
    fm_rif, bonus_rif = baseline.get(ruolo_g, BASELINE_FALLBACK.get(ruolo_g, (6.0, 0.3)))
    fm_pond = round(_pondera(fm, pv, fm_rif), 2) if fm > 0 else 0.0
    bonus_pond = round(_pondera(bonus_partita, pv, bonus_rif), 2) if fm > 0 else 0.0

    dati = {
        'nome': str(riga.get('Nome', '')).strip(),
        'ruolo': str(riga.get('R', '')).strip().upper(),
        'squadra': str(riga.get('Squadra', '')).strip(),
        'prezzo': int(_num(riga.get('Prezzo'), 1)) or 1,
        'quotazione': _num(riga.get('Qt.A')),
        'fvm': _num(riga.get('FVM')),
        'presenze': int(pv),
        'titolarita': round(titolarita, 2),
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
# FASCE PER PERCENTILE (sostituiscono le soglie fisse sulla FVM)
# ----------------------------------------------------------------------
FASCE = {
    'top':       (0.85, 1.01),   # il 15% piu' caro del ruolo
    'medi':      (0.45, 0.85),
    'gemme':     (0.20, 0.45),   # poco costosi ma con rendimento
    'panic':     (0.00, 0.20),   # ultima spiaggia
}


def fascia(df, ruolo, nome_fascia, solo_con_dati=True):
    """
    Seleziona una fascia di prezzo DENTRO il ruolo, per percentile.
    Regge anche se la scala della FVM cambia.
    """
    if df is None or df.empty or nome_fascia not in FASCE:
        return df.iloc[0:0] if df is not None else None

    gruppo = df[df['R'].astype(str).str.upper() == str(ruolo).upper()].copy()
    if gruppo.empty:
        return gruppo

    gruppo['_val'] = _colonna(gruppo, 'FVM')
    if solo_con_dati:
        gruppo = gruppo[gruppo['_val'] > 0]
    if gruppo.empty:
        return gruppo

    minimo, massimo = FASCE[nome_fascia]
    rango = gruppo['_val'].rank(pct=True)
    selezione = gruppo[(rango >= minimo) & (rango < massimo)]
    return selezione.sort_values('_val', ascending=False)


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


def scommesse(df, limite=12):
    """Poco costosi ma con rendimento sopra la media del ruolo: la fascia 'gemme'."""
    if df is None or df.empty:
        return df
    pezzi = [fascia(df, ruolo, 'gemme') for ruolo in ('P', 'D', 'C', 'A')]
    pezzi = [p for p in pezzi if p is not None and not p.empty]
    if not pezzi:
        return df.iloc[0:0]
    insieme = pd.concat(pezzi)
    return migliori_per_resa(insieme, limite=limite)