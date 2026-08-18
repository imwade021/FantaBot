"""
interfaccia.py - Disegna le schermate come immagini, non come testo.

Palette a due colori: nero caldo e arancione. Le differenze nascono da
intensita' e spaziatura, non da colori diversi. Nessuna dipendenza da
Telegram: si genera il PNG e lo si guarda da riga di comando.
"""

import io
import math
import os

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

# ----------------------------------------------------------------------
# IDENTITA' VISIVA
# ----------------------------------------------------------------------
NERO = (9, 9, 10)
NERO_CALDO = (16, 14, 13)
SUPERFICIE = (24, 22, 22)
BORDO = (44, 40, 38)
BORDO_ACCESO = (86, 54, 12)

TESTO = (247, 244, 240)
TESTO_MEDIO = (168, 160, 152)
TESTO_DEBOLE = (108, 100, 94)

ARANCIO = (255, 138, 0)
ARANCIO_CHIARO = (255, 186, 92)
ARANCIO_SCURO = (140, 72, 4)
ROSSO = (255, 74, 38)

INTENSITA_RUOLO = {'P': ARANCIO_CHIARO, 'D': (255, 166, 51),
                   'C': ARANCIO, 'A': (208, 92, 0)}
NOMI_RUOLO = {'P': 'PORTIERI', 'D': 'DIFESA', 'C': 'CENTROCAMPO', 'A': 'ATTACCO'}

LARGHEZZA, ALTEZZA = 1080, 1080
PERCORSO_FONT = os.path.join(os.path.dirname(__file__), "font.ttf")


def _font(dimensione):
    try:
        return ImageFont.truetype(PERCORSO_FONT, dimensione)
    except Exception:
        return ImageFont.load_default()


def _spaziato(disegno, xy, testo, font, colore, spaziatura=4):
    """Scrive con spaziatura fra le lettere: e' cio' che rende 'grafica'
    una didascalia maiuscola, molto piu' del font in se'."""
    x, y = xy
    for carattere in testo:
        disegno.text((x, y), carattere, font=font, fill=colore)
        x += disegno.textlength(carattere, font=font) + spaziatura
    return x


def _larghezza_spaziata(disegno, testo, font, spaziatura=4):
    return sum(disegno.textlength(c, font=font) + spaziatura for c in testo) - spaziatura


def _sfondo(immagine):
    """Nero caldo con un alone arancione in alto a sinistra: da' profondita'
    senza introdurre un secondo colore."""
    disegno = ImageDraw.Draw(immagine)
    for y in range(ALTEZZA):
        quota = y / ALTEZZA
        colore = tuple(int(NERO_CALDO[i] + (NERO[i] - NERO_CALDO[i]) * quota) for i in range(3))
        disegno.line([(0, y), (LARGHEZZA, y)], fill=colore)

    alone = Image.new("RGB", (LARGHEZZA, ALTEZZA), (0, 0, 0))
    ImageDraw.Draw(alone).ellipse([-260, -340, 620, 300], fill=(70, 34, 0))
    alone = alone.filter(ImageFilter.GaussianBlur(160))
    return Image.blend(immagine, Image.blend(immagine, alone, 0.0), 0).point(lambda v: v), alone


def _scheda(disegno, riquadro, raggio=30, riempimento=SUPERFICIE, bordo=BORDO):
    disegno.rounded_rectangle(riquadro, raggio, fill=riempimento, outline=bordo, width=2)


def _barra(disegno, x, y, larghezza, altezza, quota, colore):
    raggio = altezza // 2
    disegno.rounded_rectangle([x, y, x + larghezza, y + altezza], raggio, fill=(38, 35, 34))
    piena = max(0.0, min(1.0, quota)) * larghezza
    if piena > altezza:
        disegno.rounded_rectangle([x, y, x + piena, y + altezza], raggio, fill=colore)


def _anello(disegno, centro, raggio, spessore, quota, colore, fondo=(42, 38, 36)):
    """Anello di progresso: piu' 'app' di una barra per una percentuale."""
    cx, cy = centro
    riquadro = [cx - raggio, cy - raggio, cx + raggio, cy + raggio]
    disegno.ellipse(riquadro, outline=fondo, width=spessore)
    gradi = max(0.0, min(1.0, quota)) * 360
    if gradi > 2:
        disegno.arc(riquadro, -90, -90 + gradi, fill=colore, width=spessore)


def _pallini(disegno, x, y, pieni, totale, colore, passo=30, raggio=9):
    """Uno slot, un pallino: per numeri piccoli si leggono meglio di una barra."""
    for indice in range(totale):
        cx = x + indice * passo
        if indice < pieni:
            disegno.ellipse([cx - raggio, y - raggio, cx + raggio, y + raggio], fill=colore)
        else:
            disegno.ellipse([cx - raggio, y - raggio, cx + raggio, y + raggio],
                            outline=(64, 58, 54), width=3)


# ----------------------------------------------------------------------
# DASHBOARD
# ----------------------------------------------------------------------
def disegna_dashboard(dati):
    immagine = Image.new("RGB", (LARGHEZZA, ALTEZZA), NERO)

    # sfondo sfumato + alone
    base = ImageDraw.Draw(immagine)
    for y in range(ALTEZZA):
        quota = y / ALTEZZA
        colore = tuple(int(NERO_CALDO[i] + (NERO[i] - NERO_CALDO[i]) * quota) for i in range(3))
        base.line([(0, y), (LARGHEZZA, y)], fill=colore)
    alone = Image.new("RGB", (LARGHEZZA, ALTEZZA), (0, 0, 0))
    ImageDraw.Draw(alone).ellipse([-300, -380, 660, 260], fill=(86, 42, 0))
    immagine = Image.blend(immagine, alone.filter(ImageFilter.GaussianBlur(170)), 0.55)

    disegno = ImageDraw.Draw(immagine)

    # --- Marchio ---
    disegno.rounded_rectangle([56, 60, 68, 116], 6, fill=ARANCIO)
    disegno.text((92, 52), "FANTA", font=_font(66), fill=TESTO)
    larghezza_marchio = disegno.textlength("FANTA", font=_font(66))
    disegno.text((92 + larghezza_marchio, 52), "HUB", font=_font(66), fill=ARANCIO)

    stato = dati.get('stato', 'pre-asta').upper()
    font_stato = _font(24)
    larghezza_stato = _larghezza_spaziata(disegno, stato, font_stato, 5)
    disegno.rounded_rectangle([LARGHEZZA - 76 - larghezza_stato - 40, 64,
                               LARGHEZZA - 56, 112], 24,
                              fill=(38, 24, 8), outline=BORDO_ACCESO, width=2)
    _spaziato(disegno, (LARGHEZZA - 76 - larghezza_stato - 20, 76), stato,
              font_stato, ARANCIO_CHIARO, 5)

    # --- Scheda cassa ---
    _scheda(disegno, [56, 168, LARGHEZZA - 56, 452])

    budget = int(dati.get('budget', 0))
    iniziale = max(1, int(dati.get('budget_iniziale', 500)))
    quota_budget = budget / iniziale
    colore_cassa = ARANCIO if quota_budget > 0.35 else (ARANCIO_SCURO if quota_budget > 0.15 else ROSSO)

    _spaziato(disegno, (96, 202), "CASSA", _font(26), TESTO_DEBOLE, 6)
    disegno.text((92, 232), str(budget), font=_font(132), fill=TESTO)
    larghezza_cifra = disegno.textlength(str(budget), font=_font(132))
    disegno.text((100 + larghezza_cifra, 302), "cr", font=_font(46), fill=TESTO_MEDIO)

    slot = int(dati.get('slot_liberi', 0))
    media = (budget / slot) if slot else 0
    _spaziato(disegno, (96, 378), f"{media:.0f} CR A SLOT  ·  {slot} DA PRENDERE",
              _font(26), TESTO_MEDIO, 3)

    # anello percentuale
    _anello(disegno, (LARGHEZZA - 190, 300), 92, 16, quota_budget, colore_cassa)
    percentuale = f"{int(quota_budget * 100)}%"
    font_percentuale = _font(52)
    larghezza_percentuale = disegno.textlength(percentuale, font=font_percentuale)
    disegno.text((LARGHEZZA - 190 - larghezza_percentuale / 2, 272), percentuale,
                 font=font_percentuale, fill=TESTO)

    # --- Reparti ---
    _spaziato(disegno, (62, 484), "ROSA", _font(28), TESTO_DEBOLE, 6)

    conteggi = dati.get('conteggi', {})
    totali = dati.get('slot_totali', {'P': 3, 'D': 8, 'C': 8, 'A': 6})
    y = 530
    for ruolo in ('P', 'D', 'C', 'A'):
        avuti, totale = int(conteggi.get(ruolo, 0)), int(totali.get(ruolo, 1))
        colore = INTENSITA_RUOLO[ruolo]
        completo = avuti >= totale

        _scheda(disegno, [56, y, LARGHEZZA - 56, y + 92], 26,
                riempimento=(28, 24, 22) if completo else SUPERFICIE,
                bordo=BORDO_ACCESO if completo else BORDO)
        disegno.rounded_rectangle([56, y + 18, 62, y + 74], 3, fill=colore)

        disegno.text((96, y + 20), ruolo, font=_font(46), fill=colore)
        _spaziato(disegno, (146, y + 34), NOMI_RUOLO[ruolo], _font(26), TESTO_MEDIO, 4)

        _pallini(disegno, 520, y + 46, avuti, totale, colore)

        etichetta = f"{avuti}/{totale}"
        font_etichetta = _font(40)
        larghezza_etichetta = disegno.textlength(etichetta, font=font_etichetta)
        disegno.text((LARGHEZZA - 96 - larghezza_etichetta, y + 24), etichetta,
                     font=font_etichetta, fill=colore if completo else TESTO)
        y += 104

    # --- Piede ---
    _scheda(disegno, [56, ALTEZZA - 132, LARGHEZZA - 56, ALTEZZA - 48], 26,
            riempimento=(30, 20, 12), bordo=BORDO_ACCESO)
    _spaziato(disegno, (96, ALTEZZA - 116), "OFFERTA MASSIMA", _font(24), TESTO_DEBOLE, 5)
    valore = f"{int(dati.get('max_bid', 0))} cr"
    font_valore = _font(44)
    larghezza_valore = disegno.textlength(valore, font=font_valore)
    disegno.text((LARGHEZZA - 96 - larghezza_valore, ALTEZZA - 122), valore,
                 font=font_valore, fill=ARANCIO)

    buffer = io.BytesIO()
    immagine.save(buffer, format="PNG")
    return buffer.getvalue()


if __name__ == "__main__":
    esempio = {
        'budget': 347, 'budget_iniziale': 500, 'slot_liberi': 20, 'max_bid': 328,
        'conteggi': {'P': 3, 'D': 2, 'C': 1, 'A': 1},
        'slot_totali': {'P': 3, 'D': 8, 'C': 8, 'A': 6},
        'stato': 'pre-asta',
    }
    with open("anteprima_home.png", "wb") as f:
        f.write(disegna_dashboard(esempio))
    print("scritto anteprima_home.png")


# ----------------------------------------------------------------------
# CARD GIOCATORE
# ----------------------------------------------------------------------
def _riquadro_valore(disegno, x, y, larghezza, etichetta, valore, colore=TESTO, altezza=118):
    _scheda(disegno, [x, y, x + larghezza, y + altezza], 22, riempimento=(28, 25, 24))
    _spaziato(disegno, (x + 22, y + 20), etichetta, _font(22), TESTO_DEBOLE, 4)
    disegno.text((x + 20, y + 46), valore, font=_font(52), fill=colore)


def disegna_card(g):
    immagine = Image.new("RGB", (LARGHEZZA, ALTEZZA), NERO)
    base = ImageDraw.Draw(immagine)
    for y in range(ALTEZZA):
        q = y / ALTEZZA
        base.line([(0, y), (LARGHEZZA, y)],
                  fill=tuple(int(NERO_CALDO[i] + (NERO[i] - NERO_CALDO[i]) * q) for i in range(3)))
    alone = Image.new("RGB", (LARGHEZZA, ALTEZZA), (0, 0, 0))
    ImageDraw.Draw(alone).ellipse([420, -300, 1300, 420], fill=(92, 44, 0))
    immagine = Image.blend(immagine, alone.filter(ImageFilter.GaussianBlur(170)), 0.5)
    disegno = ImageDraw.Draw(immagine)

    # intestazione: ruolo, nome, squadra
    disegno.rounded_rectangle([56, 62, 132, 138], 20, fill=ARANCIO)
    ruolo = g.get('ruolo', 'A')
    lr = disegno.textlength(ruolo, font=_font(56))
    disegno.text((94 - lr / 2, 74), ruolo, font=_font(56), fill=NERO)

    disegno.text((156, 58), testo_sicuro(g.get('nome', '').upper()), font=_font(72), fill=TESTO)
    _spaziato(disegno, (160, 138), testo_sicuro(g.get('squadra', '').upper()),
              _font(26), TESTO_MEDIO, 5)

    # fascia
    fascia = testo_sicuro(g.get('fascia', ''))
    ff = _font(26)
    lf = _larghezza_spaziata(disegno, fascia, ff, 5)
    disegno.rounded_rectangle([LARGHEZZA - 96 - lf, 66, LARGHEZZA - 56, 118], 24,
                              fill=(38, 24, 8), outline=BORDO_ACCESO, width=2)
    _spaziato(disegno, (LARGHEZZA - 76 - lf, 80), fascia, ff, ARANCIO_CHIARO, 5)

    # tre metriche in barre
    y = 210
    _scheda(disegno, [56, y, LARGHEZZA - 56, y + 268])
    yy = y + 34
    for etichetta, quota, valore in g.get('barre', []):
        _spaziato(disegno, (96, yy), testo_sicuro(etichetta), _font(24), TESTO_MEDIO, 4)
        vl = disegno.textlength(valore, font=_font(34))
        disegno.text((LARGHEZZA - 96 - vl, yy - 8), valore, font=_font(34), fill=TESTO)
        _barra(disegno, 96, yy + 38, LARGHEZZA - 320, 14, quota, ARANCIO)
        yy += 78

    # avviso
    y = 510
    avviso = g.get('avviso')
    if avviso:
        livello, righe = avviso
        colore = {'evita': ROSSO, 'attenzione': ARANCIO, 'ok': (120, 190, 120)}.get(livello, ARANCIO)
        altezza = 70 + 40 * len(righe)
        _scheda(disegno, [56, y, LARGHEZZA - 56, y + altezza], 26,
                riempimento=(32, 20, 14), bordo=(colore[0] // 2, colore[1] // 3, colore[2] // 4))
        disegno.rounded_rectangle([56, y + 20, 62, y + altezza - 20], 3, fill=colore)
        _spaziato(disegno, (96, y + 22), testo_sicuro(g.get('titolo_avviso', '')),
                  _font(26), colore, 5)
        yy = y + 62
        for riga in righe:
            disegno.text((96, yy), "·  " + testo_sicuro(riga), font=_font(28), fill=TESTO_MEDIO)
            yy += 40
        y += altezza + 40

    # prezzi
    larghezza_col = (LARGHEZZA - 112 - 48) // 3
    y = max(y, ALTEZZA - 320)
    _riquadro_valore(disegno, 56, y, larghezza_col, "PREZZO", f"{g.get('prezzo', 0)}", ARANCIO, 140)
    _riquadro_valore(disegno, 56 + larghezza_col + 24, y, larghezza_col, "MAX", f"{g.get('max', 0)}", TESTO, 140)
    _riquadro_valore(disegno, 56 + 2 * (larghezza_col + 24), y, larghezza_col, "STOP",
                     f"{g.get('stop', 0)}", ROSSO, 140)

    # piede: cassa
    _scheda(disegno, [56, ALTEZZA - 132, LARGHEZZA - 56, ALTEZZA - 48], 26,
            riempimento=(24, 22, 21))
    _spaziato(disegno, (96, ALTEZZA - 116), "LA TUA CASSA", _font(24), TESTO_DEBOLE, 5)
    testo = f"{g.get('cassa', 0)} cr  ·  max {g.get('max_bid', 0)}"
    lt = disegno.textlength(testo, font=_font(40))
    disegno.text((LARGHEZZA - 96 - lt, ALTEZZA - 120), testo, font=_font(40), fill=TESTO)

    buffer = io.BytesIO()
    immagine.save(buffer, format="PNG")
    return buffer.getvalue()


# Bebas non ha accenti maiuscoli ne' l'ordinale: si sostituiscono a monte
SOSTITUZIONI_GLIFI = {'À': 'A', 'È': 'E', 'É': 'E', 'Ì': 'I', 'Ò': 'O', 'Ù': 'U',
                      'ª': 'a', '°': 'o', '–': '-', '—': '-', '’': "'"}


def testo_sicuro(testo):
    """Toglie i caratteri che il font non sa disegnare (uscirebbero come quadratini)."""
    for vecchio, nuovo in SOSTITUZIONI_GLIFI.items():
        testo = str(testo).replace(vecchio, nuovo)
    return testo


# ----------------------------------------------------------------------
# DISTINTA / FORMAZIONE
# ----------------------------------------------------------------------
def disegna_formazione(dati):
    immagine = Image.new("RGB", (LARGHEZZA, ALTEZZA), NERO)
    disegno = ImageDraw.Draw(immagine)
    disegno.rectangle([0, 0, LARGHEZZA, ALTEZZA], fill=(12, 11, 11))

    # campo stilizzato: solo linee, niente verde
    campo = [80, 150, LARGHEZZA - 80, ALTEZZA - 150]
    disegno.rounded_rectangle(campo, 18, outline=(48, 42, 38), width=3)
    mezzo = (campo[1] + campo[3]) // 2
    disegno.line([(campo[0], mezzo), (campo[2], mezzo)], fill=(38, 34, 32), width=3)
    disegno.ellipse([LARGHEZZA // 2 - 90, mezzo - 90, LARGHEZZA // 2 + 90, mezzo + 90],
                    outline=(38, 34, 32), width=3)
    disegno.rounded_rectangle([LARGHEZZA // 2 - 190, campo[3] - 130, LARGHEZZA // 2 + 190, campo[3]],
                              4, outline=(38, 34, 32), width=3)
    disegno.rounded_rectangle([LARGHEZZA // 2 - 190, campo[1], LARGHEZZA // 2 + 190, campo[1] + 130],
                              4, outline=(38, 34, 32), width=3)

    _spaziato(disegno, (80, 74), "FORMAZIONE", _font(34), TESTO, 6)
    modulo = testo_sicuro(dati.get('modulo', '3-4-3'))
    lm = disegno.textlength(modulo, font=_font(48))
    disegno.text((LARGHEZZA - 80 - lm, 62), modulo, font=_font(48), fill=ARANCIO)

    reparti = dati.get('reparti', {})
    altezze = {'P': campo[3] - 90, 'D': campo[3] - 300, 'C': mezzo - 40, 'A': campo[1] + 150}
    for ruolo in ('P', 'D', 'C', 'A'):
        giocatori = reparti.get(ruolo, [])
        if not giocatori:
            continue
        y = altezze[ruolo]
        passo = (LARGHEZZA - 200) / (len(giocatori) + 1)
        for indice, nome in enumerate(giocatori):
            x = 100 + passo * (indice + 1)
            disegno.ellipse([x - 42, y - 42, x + 42, y + 42], fill=(30, 26, 24),
                            outline=ARANCIO, width=3)
            iniziale = testo_sicuro(nome[:1].upper())
            li = disegno.textlength(iniziale, font=_font(44))
            disegno.text((x - li / 2, y - 30), iniziale, font=_font(44), fill=ARANCIO)
            nome_corto = testo_sicuro(nome.upper()[:11])
            ln = disegno.textlength(nome_corto, font=_font(26))
            disegno.text((x - ln / 2, y + 50), nome_corto, font=_font(26), fill=TESTO_MEDIO)

    buffer = io.BytesIO()
    immagine.save(buffer, format="PNG")
    return buffer.getvalue()


# ----------------------------------------------------------------------
# CONFRONTO A DUE COLONNE
# ----------------------------------------------------------------------
def disegna_confronto(dati):
    immagine = Image.new("RGB", (LARGHEZZA, ALTEZZA), NERO)
    disegno = ImageDraw.Draw(immagine)
    disegno.rectangle([0, 0, LARGHEZZA, ALTEZZA], fill=(14, 12, 12))

    meta = LARGHEZZA // 2
    disegno.line([(meta, 210), (meta, ALTEZZA - 190)], fill=(40, 36, 34), width=2)

    for lato, chiave in ((0, 'sinistra'), (1, 'destra')):
        g = dati[chiave]
        centro = meta // 2 + lato * meta
        nome = testo_sicuro(g['nome'].upper())
        ln = disegno.textlength(nome, font=_font(60))
        disegno.text((centro - ln / 2, 74), nome, font=_font(60), fill=TESTO)
        squadra = testo_sicuro(g['squadra'].upper())
        ls = _larghezza_spaziata(disegno, squadra, _font(24), 5)
        _spaziato(disegno, (centro - ls / 2, 148), squadra, _font(24), TESTO_MEDIO, 5)

    y = 236
    for voce in dati.get('voci', []):
        etichetta = testo_sicuro(voce['etichetta'])
        le = _larghezza_spaziata(disegno, etichetta, _font(24), 4)
        _spaziato(disegno, (meta - le / 2, y), etichetta, _font(24), TESTO_DEBOLE, 4)

        for lato, chiave in ((0, 'v1'), (1, 'v2')):
            valore = testo_sicuro(voce[chiave])
            vince = voce.get('vincitore') == (lato + 1)
            colore = ARANCIO if vince else TESTO_MEDIO
            font_valore = _font(46 if vince else 40)
            lv = disegno.textlength(valore, font=font_valore)
            x = meta // 2 + lato * meta - lv / 2
            disegno.text((x, y + 34), valore, font=font_valore, fill=colore)

        # barrette proporzionali affiancate
        q1, q2 = voce.get('q1', 0), voce.get('q2', 0)
        _barra(disegno, meta - 40 - 300 * q1, y + 96, max(6, 300 * q1), 12, 1.0,
               ARANCIO if voce.get('vincitore') == 1 else (70, 62, 58))
        _barra(disegno, meta + 40, y + 96, max(6, 300 * q2), 12, 1.0,
               ARANCIO if voce.get('vincitore') == 2 else (70, 62, 58))
        y += 150

    verdetto = testo_sicuro(dati.get('verdetto', ''))
    _scheda(disegno, [56, ALTEZZA - 170, LARGHEZZA - 56, ALTEZZA - 56], 26,
            riempimento=(32, 20, 10), bordo=BORDO_ACCESO)
    _spaziato(disegno, (96, ALTEZZA - 152), "VERDETTO", _font(24), TESTO_DEBOLE, 5)
    disegno.text((96, ALTEZZA - 122), verdetto, font=_font(36), fill=ARANCIO_CHIARO)

    buffer = io.BytesIO()
    immagine.save(buffer, format="PNG")
    return buffer.getvalue()


# ----------------------------------------------------------------------
# RIEPILOGO FINE ASTA (da condividere nel gruppo della lega)
# ----------------------------------------------------------------------
def disegna_riepilogo(dati):
    immagine = Image.new("RGB", (LARGHEZZA, ALTEZZA), NERO)
    base = ImageDraw.Draw(immagine)
    for y in range(ALTEZZA):
        q = y / ALTEZZA
        base.line([(0, y), (LARGHEZZA, y)],
                  fill=tuple(int(NERO_CALDO[i] + (NERO[i] - NERO_CALDO[i]) * q) for i in range(3)))
    alone = Image.new("RGB", (LARGHEZZA, ALTEZZA), (0, 0, 0))
    ImageDraw.Draw(alone).ellipse([-200, 700, 900, 1400], fill=(96, 46, 0))
    immagine = Image.blend(immagine, alone.filter(ImageFilter.GaussianBlur(190)), 0.5)
    disegno = ImageDraw.Draw(immagine)

    _spaziato(disegno, (60, 66), "ASTA COMPLETATA", _font(30), TESTO_DEBOLE, 6)
    disegno.text((56, 104), testo_sicuro(dati.get('squadra', '').upper()),
                 font=_font(78), fill=TESTO)

    # spesa per reparto
    y = 232
    _spaziato(disegno, (62, y), "SPESA PER REPARTO", _font(24), TESTO_DEBOLE, 5)
    y += 46
    spesa = dati.get('spesa', {})
    massimo = max(spesa.values()) if spesa else 1
    for ruolo in ('P', 'D', 'C', 'A'):
        valore = spesa.get(ruolo, 0)
        disegno.text((62, y), ruolo, font=_font(40), fill=INTENSITA_RUOLO[ruolo])
        _barra(disegno, 120, y + 16, 700, 18, valore / massimo if massimo else 0,
               INTENSITA_RUOLO[ruolo])
        testo = f"{valore} cr"
        lt = disegno.textlength(testo, font=_font(34))
        disegno.text((LARGHEZZA - 62 - lt, y + 4), testo, font=_font(34), fill=TESTO)
        y += 64

    # i colpi migliori
    y += 24
    _spaziato(disegno, (62, y), "I TRE COLPI", _font(24), TESTO_DEBOLE, 5)
    y += 46
    for indice, colpo in enumerate(dati.get('colpi', [])[:3]):
        _scheda(disegno, [56, y, LARGHEZZA - 56, y + 108], 24, riempimento=(26, 23, 22))
        disegno.text((92, y + 24), str(indice + 1), font=_font(52), fill=ARANCIO_SCURO)
        disegno.text((156, y + 20), testo_sicuro(colpo['nome'].upper()), font=_font(46), fill=TESTO)
        _spaziato(disegno, (160, y + 72), testo_sicuro(colpo['nota'].upper()),
                  _font(22), TESTO_MEDIO, 4)
        prezzo = f"{colpo['prezzo']} cr"
        lp = disegno.textlength(prezzo, font=_font(44))
        disegno.text((LARGHEZZA - 92 - lp, y + 30), prezzo, font=_font(44), fill=ARANCIO)
        y += 120

    _spaziato(disegno, (62, ALTEZZA - 74), "GENERATO CON FANTAHUB", _font(22), TESTO_DEBOLE, 5)

    buffer = io.BytesIO()
    immagine.save(buffer, format="PNG")
    return buffer.getvalue()


# ----------------------------------------------------------------------
# ANTEPRIMA INLINE (formato largo, per i gruppi)
# ----------------------------------------------------------------------
def disegna_inline(g):
    larghezza, altezza = 1080, 420
    immagine = Image.new("RGB", (larghezza, altezza), (14, 12, 12))
    disegno = ImageDraw.Draw(immagine)
    alone = Image.new("RGB", (larghezza, altezza), (0, 0, 0))
    ImageDraw.Draw(alone).ellipse([700, -200, 1400, 400], fill=(90, 44, 0))
    immagine = Image.blend(immagine, alone.filter(ImageFilter.GaussianBlur(120)), 0.5)
    disegno = ImageDraw.Draw(immagine)

    disegno.rounded_rectangle([44, 46, 108, 110], 18, fill=ARANCIO)
    ruolo = g.get('ruolo', 'A')
    lr = disegno.textlength(ruolo, font=_font(46))
    disegno.text((76 - lr / 2, 56), ruolo, font=_font(46), fill=NERO)

    disegno.text((132, 44), testo_sicuro(g.get('nome', '').upper()), font=_font(62), fill=TESTO)
    _spaziato(disegno, (136, 116), testo_sicuro(f"{g.get('squadra','')} · {g.get('fascia','')}".upper()),
              _font(24), TESTO_MEDIO, 4)

    y = 190
    for etichetta, quota, valore in g.get('barre', [])[:3]:
        _spaziato(disegno, (48, y), testo_sicuro(etichetta), _font(22), TESTO_DEBOLE, 4)
        _barra(disegno, 48, y + 32, 560, 12, quota, ARANCIO)
        disegno.text((624, y + 12), testo_sicuro(valore), font=_font(30), fill=TESTO)
        y += 74

    _scheda(disegno, [760, 180, larghezza - 44, 380], 26, riempimento=(30, 20, 12),
            bordo=BORDO_ACCESO)
    _spaziato(disegno, (792, 206), "PREZZO", _font(22), TESTO_DEBOLE, 5)
    disegno.text((790, 234), str(g.get('prezzo', 0)), font=_font(86), fill=ARANCIO)
    disegno.text((790, 330), f"max {g.get('max', 0)}  ·  stop {g.get('stop', 0)}",
                 font=_font(28), fill=TESTO_MEDIO)

    buffer = io.BytesIO()
    immagine.save(buffer, format="PNG")
    return buffer.getvalue()


# ----------------------------------------------------------------------
# VERSIONE ALLEGGERITA
# Principio: un solo elemento domina, il resto sussurra. Niente riquadri
# dove basta lo spazio bianco, niente etichette dove il numero si spiega.
# ----------------------------------------------------------------------
def _tela():
    immagine = Image.new("RGB", (LARGHEZZA, ALTEZZA), NERO)
    disegno = ImageDraw.Draw(immagine)
    for y in range(ALTEZZA):
        q = y / ALTEZZA
        disegno.line([(0, y), (LARGHEZZA, y)],
                     fill=tuple(int(NERO_CALDO[i] + (NERO[i] - NERO_CALDO[i]) * q) for i in range(3)))
    return immagine


def _fondo_testo(disegno, xy, testo, font):
    """Coordinata Y in cui il testo finisce davvero: con font grandi l'altezza
    dipende dai glifi, e piazzare la riga successiva 'a occhio' fa sovrapporre."""
    riquadro = disegno.textbbox(xy, testo, font=font)
    return riquadro[3]


def _linea(disegno, y, x1=72, x2=LARGHEZZA - 72, colore=(38, 34, 32)):
    disegno.line([(x1, y), (x2, y)], fill=colore, width=2)


def disegna_card_v2(g):
    immagine = _tela()
    disegno = ImageDraw.Draw(immagine)

    # --- Identita': nome grande, tutto il resto in una riga sola ---
    disegno.text((72, 96), testo_sicuro(g.get('nome', '').upper()), font=_font(96), fill=TESTO)
    sottotitolo = testo_sicuro(f"{g.get('ruolo','')}  ·  {g.get('squadra','')}  ·  {g.get('fascia','')}".upper())
    _spaziato(disegno, (76, 206), sottotitolo, _font(26), TESTO_MEDIO, 5)

    # --- IL numero: e' il motivo per cui apri la scheda ---
    prezzo = str(g.get('prezzo', 0))
    font_prezzo = _font(300)
    lp = disegno.textlength(prezzo, font=font_prezzo)
    disegno.text((72, 300), prezzo, font=font_prezzo, fill=ARANCIO)
    disegno.text((84 + lp, 470), "cr", font=_font(76), fill=ARANCIO_SCURO)

    _spaziato(disegno, (76, 596), f"MAX {g.get('max', 0)}   ·   STOP {g.get('stop', 0)}",
              _font(30), TESTO_MEDIO, 5)

    _linea(disegno, 668)

    # --- Tre numeri secondari, senza scatole ---
    y = 712
    colonne = g.get('numeri', [])
    passo = (LARGHEZZA - 144) / max(1, len(colonne))
    for indice, (etichetta, valore, evidenzia) in enumerate(colonne):
        x = 72 + passo * indice
        disegno.text((x, y), testo_sicuro(valore), font=_font(64),
                     fill=ARANCIO if evidenzia else TESTO)
        _spaziato(disegno, (x + 2, y + 76), testo_sicuro(etichetta), _font(22), TESTO_DEBOLE, 4)

    # --- Avviso: una riga, non un elenco ---
    avviso = g.get('avviso')
    if avviso:
        livello, testo = avviso
        colore = ROSSO if livello == 'evita' else ARANCIO
        y = 880
        disegno.rounded_rectangle([72, y, 78, y + 76], 3, fill=colore)
        disegno.text((104, y + 2), testo_sicuro(testo.upper()), font=_font(34), fill=colore)
        if g.get('avviso_extra'):
            disegno.text((104, y + 44), testo_sicuro(g['avviso_extra']),
                         font=_font(28), fill=TESTO_DEBOLE)

    # --- Piede discreto ---
    _spaziato(disegno, (72, ALTEZZA - 66),
              testo_sicuro(f"CASSA {g.get('cassa', 0)} CR  ·  OFFERTA MAX {g.get('max_bid', 0)}"),
              _font(24), TESTO_DEBOLE, 5)

    buffer = io.BytesIO()
    immagine.save(buffer, format="PNG")
    return buffer.getvalue()


def disegna_dashboard_v2(dati):
    immagine = _tela()
    disegno = ImageDraw.Draw(immagine)

    budget = int(dati.get('budget', 0))
    iniziale = max(1, int(dati.get('budget_iniziale', 500)))
    quota = budget / iniziale
    slot = int(dati.get('slot_liberi', 0))
    media = (budget / slot) if slot else 0

    disegno.rounded_rectangle([72, 84, 82, 128], 5, fill=ARANCIO)
    disegno.text((104, 76), "FANTA", font=_font(56), fill=TESTO)
    lm = disegno.textlength("FANTA", font=_font(56))
    disegno.text((104 + lm, 76), "HUB", font=_font(56), fill=ARANCIO)

    # --- IL numero ---
    font_cassa = _font(300)
    disegno.text((72, 210), str(budget), font=font_cassa, fill=TESTO)
    lb = disegno.textlength(str(budget), font=font_cassa)
    fondo_cassa = _fondo_testo(disegno, (72, 210), str(budget), font_cassa)

    font_cr = _font(76)
    disegno.text((84 + lb, fondo_cassa - _fondo_testo(disegno, (0, 0), "cr", font_cr)),
                 "cr", font=font_cr, fill=TESTO_DEBOLE)

    y_sotto = fondo_cassa + 34
    _spaziato(disegno, (76, y_sotto), testo_sicuro(f"{slot} SLOT DA RIEMPIRE  ·  {media:.0f} CR A TESTA"),
              _font(30), TESTO_MEDIO, 5)

    colore = ARANCIO if quota > 0.35 else (ARANCIO_SCURO if quota > 0.15 else ROSSO)
    _barra(disegno, 72, y_sotto + 62, LARGHEZZA - 144, 10, quota, colore)

    _linea(disegno, y_sotto + 152)

    # --- Reparti: una riga sola, niente schede ---
    conteggi = dati.get('conteggi', {})
    totali = dati.get('slot_totali', {'P': 3, 'D': 8, 'C': 8, 'A': 6})
    y = 730
    passo = (LARGHEZZA - 144) / 4
    for indice, ruolo in enumerate(('P', 'D', 'C', 'A')):
        avuti, totale = int(conteggi.get(ruolo, 0)), int(totali.get(ruolo, 1))
        x = 72 + passo * indice
        completo = avuti >= totale
        disegno.text((x, y), f"{avuti}", font=_font(84),
                     fill=ARANCIO if completo else TESTO)
        la = disegno.textlength(f"{avuti}", font=_font(84))
        disegno.text((x + la + 6, y + 34), f"/{totale}", font=_font(40), fill=TESTO_DEBOLE)
        _spaziato(disegno, (x + 2, y + 116), NOMI_RUOLO[ruolo], _font(22), TESTO_DEBOLE, 4)
        _barra(disegno, x, y + 156, passo - 60, 8, avuti / totale if totale else 0,
               ARANCIO if completo else (86, 76, 70))

    _spaziato(disegno, (72, ALTEZZA - 66),
              testo_sicuro(f"OFFERTA MASSIMA {dati.get('max_bid', 0)} CR"),
              _font(24), TESTO_DEBOLE, 5)

    buffer = io.BytesIO()
    immagine.save(buffer, format="PNG")
    return buffer.getvalue()


# ----------------------------------------------------------------------
# FOTO GIOCATORE
# Il Master contiene PhotoURL (i "campioncini" di Fantacalcio): si scarica
# una volta, si tiene in cache su disco e si compone dentro la card.
# ----------------------------------------------------------------------
CARTELLA_FOTO = os.path.join(os.path.dirname(__file__), "cache_foto")


def _rimuovi_sfondo_chiaro(foto, tolleranza=42):
    """
    Toglie il fondo bianco dei ritratti ufficiali. Parte dai quattro angoli e
    si espande: cosi' una maglia bianca al centro non viene cancellata, perche'
    non e' collegata al bordo.
    """
    rgb = foto.convert("RGB")
    sentinella = (255, 0, 255)
    for angolo in ((0, 0), (rgb.width - 1, 0), (0, rgb.height - 1),
                   (rgb.width - 1, rgb.height - 1)):
        try:
            pixel = rgb.getpixel(angolo)
            if min(pixel) > 200:          # solo se l'angolo e' davvero chiaro
                ImageDraw.floodfill(rgb, angolo, sentinella, thresh=tolleranza)
        except Exception:
            pass

    maschera = Image.new("L", foto.size, 255)
    dati_rgb = rgb.load()
    dati_maschera = maschera.load()
    for y in range(foto.height):
        for x in range(foto.width):
            if dati_rgb[x, y] == sentinella:
                dati_maschera[x, y] = 0

    # bordo sfumato: evita il contorno seghettato del ritaglio
    maschera = maschera.filter(ImageFilter.GaussianBlur(1.6))
    risultato = foto.convert("RGBA")
    risultato.putalpha(maschera)
    return risultato


def _sfuma_in_basso(foto, altezza_sfumatura=140):
    """Dissolve il bordo inferiore nel nero: la figura non sembra incollata."""
    alpha = foto.getchannel("A")
    sfumatura = Image.new("L", foto.size, 255)
    disegno = ImageDraw.Draw(sfumatura)
    for indice in range(altezza_sfumatura):
        y = foto.height - altezza_sfumatura + indice
        disegno.line([(0, y), (foto.width, y)],
                     fill=int(255 * (1 - indice / altezza_sfumatura)))
    foto.putalpha(Image.composite(alpha, Image.new("L", foto.size, 0), sfumatura)
                  if False else ImageChops.multiply(alpha, sfumatura))
    return foto


def carica_foto(url, lato=520):
    """Scarica (o riprende dalla cache) la foto del giocatore. None se non c'e'."""
    if not url or not str(url).startswith("http"):
        return None

    os.makedirs(CARTELLA_FOTO, exist_ok=True)
    nome_file = "".join(c for c in str(url).split("/")[-1].split("?")[0]
                        if c.isalnum() or c in "._-")[:80]
    percorso = os.path.join(CARTELLA_FOTO, nome_file or "foto.png")

    if not os.path.exists(percorso):
        try:
            import requests
            risposta = requests.get(url, timeout=8,
                                    headers={"User-Agent": "Mozilla/5.0"})
            if risposta.status_code != 200 or not risposta.content:
                return None
            with open(percorso, "wb") as f:
                f.write(risposta.content)
        except Exception:
            return None

    try:
        foto = Image.open(percorso).convert("RGBA")
    except Exception:
        return None

    proporzione = lato / max(foto.width, foto.height)
    foto = foto.resize((int(foto.width * proporzione), int(foto.height * proporzione)),
                       Image.LANCZOS)
    try:
        foto = _rimuovi_sfondo_chiaro(foto)
        foto = _sfuma_in_basso(foto)
    except Exception:
        pass
    return foto


def _silhouette(lato=520):
    """Sagoma di ripiego quando la foto manca: meglio di un buco."""
    tela = Image.new("RGBA", (lato, lato), (0, 0, 0, 0))
    disegno = ImageDraw.Draw(tela)
    disegno.ellipse([lato * 0.30, lato * 0.12, lato * 0.70, lato * 0.52], fill=(46, 40, 36, 255))
    disegno.rounded_rectangle([lato * 0.18, lato * 0.52, lato * 0.82, lato], lato * 0.18,
                              fill=(46, 40, 36, 255))
    return tela


def disegna_card_foto(g):
    """Card alleggerita con il campioncino del giocatore sulla destra."""
    immagine = _tela()

    # alone dietro la figura: la stacca dal fondo senza contorni
    alone = Image.new("RGB", (LARGHEZZA, ALTEZZA), (0, 0, 0))
    ImageDraw.Draw(alone).ellipse([560, 120, 1240, 800], fill=(104, 50, 0))
    immagine = Image.blend(immagine, alone.filter(ImageFilter.GaussianBlur(150)), 0.55)

    # Solo il ritratto API-Football: il campioncino di Fantacalcio porta con se'
    # la propria cornice blu e oro e litiga con questa grafica. Meglio la sagoma.
    # Per riattivarlo basta rimettere carica_foto(g.get('foto'), 560) in mezzo.
    foto = carica_foto(g.get('foto_api'), 560) or _silhouette(560)
    immagine.paste(foto, (LARGHEZZA - foto.width - 20, 150), foto)

    disegno = ImageDraw.Draw(immagine)

    disegno.text((72, 96), testo_sicuro(g.get('nome', '').upper()), font=_font(92), fill=TESTO)
    _spaziato(disegno, (76, 202),
              testo_sicuro(f"{g.get('ruolo','')}  ·  {g.get('squadra','')}  ·  {g.get('fascia','')}".upper()),
              _font(26), TESTO_MEDIO, 5)

    prezzo = str(g.get('prezzo', 0))
    font_prezzo = _font(280)
    disegno.text((72, 300), prezzo, font=font_prezzo, fill=ARANCIO)
    lp = disegno.textlength(prezzo, font=font_prezzo)
    fondo_prezzo = _fondo_testo(disegno, (72, 300), prezzo, font_prezzo)

    # "cr" allineato al piede del numero, non a un'altezza indovinata
    font_cr = _font(72)
    disegno.text((84 + lp, fondo_prezzo - _fondo_testo(disegno, (0, 0), "cr", font_cr)),
                 "cr", font=font_cr, fill=ARANCIO_SCURO)

    y_max_stop = fondo_prezzo + 28
    _spaziato(disegno, (76, y_max_stop), f"MAX {g.get('max', 0)}   ·   STOP {g.get('stop', 0)}",
              _font(30), TESTO_MEDIO, 5)

    _linea(disegno, y_max_stop + 92)

    y = y_max_stop + 136
    colonne = g.get('numeri', [])
    passo = (LARGHEZZA - 144) / max(1, len(colonne))
    for indice, (etichetta, valore, evidenzia) in enumerate(colonne):
        x = 72 + passo * indice
        negativo = str(valore).strip().startswith('-')
        colore_valore = ROSSO if negativo else (ARANCIO if evidenzia else TESTO)
        disegno.text((x, y), testo_sicuro(valore), font=_font(62), fill=colore_valore)
        _spaziato(disegno, (x + 2, y + 74), testo_sicuro(etichetta), _font(22), TESTO_DEBOLE, 4)

    avviso = g.get('avviso')
    if avviso:
        livello, testo = avviso
        colore = ROSSO if livello == 'evita' else ARANCIO
        y = 900
        disegno.rounded_rectangle([72, y, 78, y + 72], 3, fill=colore)
        disegno.text((104, y), testo_sicuro(testo.upper()), font=_font(34), fill=colore)
        if g.get('avviso_extra'):
            disegno.text((104, y + 42), testo_sicuro(g['avviso_extra']),
                         font=_font(28), fill=TESTO_DEBOLE)

    _spaziato(disegno, (72, ALTEZZA - 62),
              testo_sicuro(f"CASSA {g.get('cassa', 0)} CR  ·  OFFERTA MAX {g.get('max_bid', 0)}"),
              _font(24), TESTO_DEBOLE, 5)

    buffer = io.BytesIO()
    immagine.convert("RGB").save(buffer, format="PNG")
    return buffer.getvalue()
