"""
modificatore.py - Il modificatore di difesa, e cosa comporta davvero.

In una lega col modificatore il valore di un difensore non sta nei bonus: sta
nella MEDIA VOTO. Il modificatore si calcola sulla media di portiere piu' tre
difensori, e tre decimi di voto in piu' su 38 giornate pesano piu' di quattro
gol in una stagione.

Conseguenza che ribalta mezzo listone: il portiere diventa il giocatore piu'
importante della rosa. Pesa un quarto del modificatore da solo, contro tre
difensori che si dividono il resto, ed e' l'unico ruolo dove schieri sempre la
stessa persona. Un portiere da 6.30 contro uno da 5.90 vale, da solo, circa
mezzo punto a partita.
"""

# Tabella ufficiale Fantacalcio: (media minima, punti). Modificabile dalla
# schermata Lega, perche' quasi ogni lega la personalizza.
TABELLA_STANDARD = [
    (6.00, 1),
    (6.50, 3),
    (7.00, 6),
    (7.50, 8),
]

# Quanti voti entrano nel calcolo: 1 portiere + 3 difensori.
PORTIERI_SCHIERATI = 1
DIFENSORI_SCHIERATI = 3
VOTI_NEL_CALCOLO = PORTIERI_SCHIERATI + DIFENSORI_SCHIERATI


def normalizza_tabella(tabella):
    """Ordina per soglia crescente e scarta le righe malformate."""
    pulita = []
    for riga in (tabella or TABELLA_STANDARD):
        try:
            soglia, punti = float(riga[0]), float(riga[1])
        except (TypeError, ValueError, IndexError):
            continue
        pulita.append((round(soglia, 2), round(punti, 1)))
    return sorted(pulita) or list(TABELLA_STANDARD)


def punti(media, tabella=None):
    """Punti di modificatore per una media voto del reparto."""
    assegnati = 0.0
    for soglia, valore in normalizza_tabella(tabella):
        if media >= soglia:
            assegnati = valore
        else:
            break
    return assegnati


def descrivi_tabella(tabella=None):
    """La tabella in una riga leggibile, per la schermata Lega."""
    righe = normalizza_tabella(tabella)
    pezzi = [f"da {soglia:.2f} → +{punti_:g}" for soglia, punti_ in righe]
    return "  ·  ".join(pezzi)


def _campana(centro, larghezza=0.18, passi=41):
    """Pesi a campana attorno a un valore: serve per la media attesa."""
    import math
    valori = [centro + (indice - passi // 2) * (larghezza * 6 / passi)
              for indice in range(passi)]
    pesi = [math.exp(-0.5 * ((v - centro) / larghezza) ** 2) for v in valori]
    totale = sum(pesi)
    return list(zip(valori, [p / totale for p in pesi]))


def punti_attesi(media, tabella=None, incertezza=0.18):
    """
    Il modificatore ATTESO, non quello di un singolo scenario.

    La tabella e' a gradini: presa alla lettera, un portiere da 6.41 e uno da
    6.26 danno lo stesso identico +1, e non si possono ordinare. Ma tu non sai
    in anticipo che media avranno i tre difensori accanto: il gradino puo'
    cadere da una parte o dall'altra. Mediando sugli scenari plausibili la
    scala torna continua, e chi ha il voto piu' alto risulta piu' prezioso -
    che e' come stanno le cose davvero.
    """
    return round(sum(peso * punti(valore, tabella)
                     for valore, peso in _campana(media, incertezza)), 3)


def impatto(media_voto, media_riferimento=6.05, tabella=None, incertezza=0.18):
    """
    Quanto vale QUESTO giocatore, in punti a partita, dentro il modificatore.

    Si confronta un reparto tutto alla media di riferimento con lo stesso
    reparto in cui una casella e' occupata da lui. E' una stima, non un dato -
    dipende da chi schieri accanto - ma e' nell'unita' di misura giusta:
    quella in cui si vincono e si perdono le giornate.
    """
    if not media_voto or media_voto <= 0:
        return 0.0
    quota = 1.0 / VOTI_NEL_CALCOLO
    media_con = media_riferimento * (1 - quota) + media_voto * quota
    return round(punti_attesi(media_con, tabella, incertezza)
                 - punti_attesi(media_riferimento, tabella, incertezza), 3)


def media_reparto(voti_portiere, voti_difensori):
    """Media dei quattro voti che entrano nel modificatore."""
    voti = list(voti_portiere)[:PORTIERI_SCHIERATI] + \
        sorted(voti_difensori, reverse=True)[:DIFENSORI_SCHIERATI]
    voti = [v for v in voti if v and v > 0]
    return round(sum(voti) / len(voti), 2) if voti else 0.0


def valuta_reparto(voti_portiere, voti_difensori, tabella=None):
    """Il quadro del proprio reparto arretrato, in punti a partita."""
    media = media_reparto(voti_portiere, voti_difensori)
    return {
        'media': media,
        'punti': punti(media, tabella),
        'voti_contati': min(len(voti_portiere), PORTIERI_SCHIERATI)
                        + min(len(voti_difensori), DIFENSORI_SCHIERATI),
        'completo': len(voti_portiere) >= PORTIERI_SCHIERATI
                    and len(voti_difensori) >= DIFENSORI_SCHIERATI,
    }


def quanto_manca(media_attuale, tabella=None):
    """
    Quanti decimi di media mancano al gradino successivo, e quanto vale.

    E' l'informazione che fa decidere se spingere su un difensore: sapere che
    con 12 centesimi in piu' passi da +1 a +3 cambia completamente quanto sei
    disposto a pagarlo.
    """
    righe = normalizza_tabella(tabella)
    attuali = punti(media_attuale, tabella)
    for soglia, valore in righe:
        if media_attuale < soglia:
            return {'soglia': soglia, 'distanza': round(soglia - media_attuale, 2),
                    'guadagno': round(valore - attuali, 1)}
    return None
