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








def _barra(disegno, x, y, larghezza, altezza, quota, colore):
    raggio = altezza // 2
    disegno.rounded_rectangle([x, y, x + larghezza, y + altezza], raggio, fill=(38, 35, 34))
    piena = max(0.0, min(1.0, quota)) * larghezza
    if piena > altezza:
        disegno.rounded_rectangle([x, y, x + piena, y + altezza], raggio, fill=colore)






# ----------------------------------------------------------------------
# DASHBOARD
# ----------------------------------------------------------------------


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


# ----------------------------------------------------------------------
# CONFRONTO A DUE COLONNE
# ----------------------------------------------------------------------


# ----------------------------------------------------------------------
# RIEPILOGO FINE ASTA (da condividere nel gruppo della lega)
# ----------------------------------------------------------------------


# ----------------------------------------------------------------------
# ANTEPRIMA INLINE (formato largo, per i gruppi)
# ----------------------------------------------------------------------


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


def disegna_striscia(g):
    """
    Intestazione compatta: foto, nome, prezzo. Nient'altro.

    La card grande da 1080x1080 occupava mezzo schermo del telefono e i numeri
    dentro un'immagine non si possono copiare ne' cercare. Qui l'immagine fa
    solo quello che il testo non sa fare - la faccia e il prezzo a colpo
    d'occhio - e tutto il resto torna nella didascalia.
    """
    altezza = 330
    immagine = Image.new("RGB", (LARGHEZZA, altezza), NERO)

    alone = Image.new("RGB", (LARGHEZZA, altezza), (0, 0, 0))
    ImageDraw.Draw(alone).ellipse([700, -140, 1180, 450], fill=(104, 50, 0))
    immagine = Image.blend(immagine, alone.filter(ImageFilter.GaussianBlur(90)), 0.55)

    foto = carica_foto(g.get('foto_api'), 300) or _silhouette(300)
    immagine.paste(foto, (LARGHEZZA - foto.width - 24, altezza - foto.height), foto)

    disegno = ImageDraw.Draw(immagine)

    disegno.text((56, 24), testo_sicuro(g.get('nome', '').upper()), font=_font(72), fill=TESTO)
    _spaziato(disegno, (60, 110),
              testo_sicuro(f"{g.get('ruolo','')}  ·  {g.get('squadra','')}  ·  "
                           f"{g.get('fascia','')}".upper()),
              _font(24), TESTO_MEDIO, 4)

    prezzo = str(g.get('prezzo', 0))
    font_prezzo = _font(140)
    disegno.text((52, 158), prezzo, font=font_prezzo, fill=ARANCIO)
    larghezza_prezzo = disegno.textlength(prezzo, font=font_prezzo)
    fondo = _fondo_testo(disegno, (52, 158), prezzo, font_prezzo)

    font_cr = _font(44)
    disegno.text((66 + larghezza_prezzo, fondo - _fondo_testo(disegno, (0, 0), "cr", font_cr)),
                 "cr", font=font_cr, fill=ARANCIO_SCURO)

    _spaziato(disegno, (68 + larghezza_prezzo, 176),
              testo_sicuro(f"MAX {g.get('max', 0)}  ·  STOP {g.get('stop', 0)}"),
              _font(24), TESTO_DEBOLE, 4)

    buffer = io.BytesIO()
    immagine.convert("RGB").save(buffer, format="PNG")
    return buffer.getvalue()


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
