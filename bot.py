import os
import io
import time
import re
import sys
import html
import json
import threading
import pandas as pd
import analisi
import config
import dati
import interfaccia
import piano
import registro as reg
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from telebot.apihelper import ApiTelegramException
from apscheduler.schedulers.background import BackgroundScheduler

# Tenta di importare la libreria per la grafica del campo
try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_ENABLED = True
except ImportError:
    PIL_ENABLED = False

# Tenta di importare le librerie per i comandi vocali
try:
    import speech_recognition as sr
    from pydub import AudioSegment
    VOICE_ENABLED = True
except ImportError:
    VOICE_ENABLED = False

# ==========================================
# CONFIGURAZIONE INIZIALE & TOKEN
# ==========================================
TOKEN = config.TOKEN

if not TOKEN:
    raise ValueError("⚠️ ERRORE: La variabile d'ambiente BOT_TOKEN non è impostata!")

bot = telebot.TeleBot(TOKEN)

# Alias verso config.py: le costanti stanno tutte la'
LISTONE_URL = config.LISTONE_URL
ROLE_ICONS = config.ROLE_ICONS
TEAM_COLORS = config.TEAM_COLORS
SLOT_PER_RUOLO = config.SLOT_PER_RUOLO

# Sessioni utente. Stanno in memoria per velocita', ma vengono salvate su disco:
# durante un'asta dal vivo un riavvio di Render azzerava rosa, cassa e scartati.
user_sessions = {}
_sessioni_lock = threading.Lock()


def carica_sessioni():
    """Ripristina le sessioni salvate. Un file corrotto non blocca l'avvio."""
    if not os.path.exists(config.FILE_SESSIONI):
        return
    try:
        with open(config.FILE_SESSIONI, 'r', encoding='utf-8') as f:
            salvate = json.load(f)
        for chiave, sessione in salvate.items():
            user_sessions[int(chiave)] = sessione
        print(f"✅ Sessioni ripristinate: {len(user_sessions)}.")
    except Exception as e:
        print(f"⚠️ Sessioni non ripristinate ({e}): si riparte da zero.")


def salva_sessioni():
    """Scrittura atomica: se il processo muore a meta', il file resta valido."""
    try:
        with _sessioni_lock:
            istantanea = {str(k): v for k, v in user_sessions.items()}
        temporaneo = config.FILE_SESSIONI + ".tmp"
        with open(temporaneo, 'w', encoding='utf-8') as f:
            json.dump(istantanea, f, ensure_ascii=False)
        os.replace(temporaneo, config.FILE_SESSIONI)
    except Exception as e:
        print(f"⚠️ Salvataggio sessioni fallito: {e}")

# Rigoristi, coppie di portieri e scommesse NON sono piu' liste scritte a mano:
# si ricavano dalle colonne del Lista_Finale_Master.csv (Rc = rigori calciati,
# R+ = segnati, Pv = presenze). Cosi' restano allineate a ogni aggiornamento.

def _num(v, default=0.0):
    try:
        n = pd.to_numeric(str(v).replace(',', '.'), errors='coerce')
        return default if pd.isna(n) else float(n)
    except Exception:
        return default


def fair_price(row, session):
    return dati.prezzo_consigliato(row, session)


def gerarchie_rigoristi(df, squadra=None):
    """Chi ha calciato rigori la scorsa stagione, per squadra, dal piu' usato."""
    if df is None or df.empty or 'Rc' not in df.columns:
        return {}

    gerarchie = {}
    squadre = [squadra] if squadra else sorted(df['Squadra'].dropna().astype(str).unique())
    for sq in squadre:
        rosa = df[df['Squadra'].astype(str) == str(sq)].copy()
        if rosa.empty:
            continue
        rosa['_rc'] = rosa['Rc'].apply(_num)
        tiratori = rosa[rosa['_rc'] > 0].sort_values('_rc', ascending=False)
        if tiratori.empty:
            continue
        gerarchie[sq] = {
            'rigoristi': [
                f"{r['Nome']} ({int(r['_rc'])})" for _, r in tiratori.head(3).iterrows()
            ]
        }
    return gerarchie


def trova_partner_portiere(nome, df):
    """Il vice (o titolare) della stessa squadra: il 'paracadute' da abbinare."""
    if df is None or df.empty:
        return None
    riga = get_player_stats(nome, df)
    if riga is None or str(riga.get('R', '')).upper() != 'P':
        return None

    compagni = df[(df['R'].astype(str).str.upper() == 'P') &
                  (df['Squadra'].astype(str) == str(riga.get('Squadra', ''))) &
                  (df['Nome'].astype(str) != str(riga.get('Nome', '')))]
    if compagni.empty:
        return None
    compagni = compagni.assign(_fvm=compagni['FVM'].apply(_num)).sort_values('_fvm', ascending=False)
    return str(compagni.iloc[0]['Nome'])


def safe_answer_callback(call_id, text=None, show_alert=False):
    try: bot.answer_callback_query(call_id, text=text, show_alert=show_alert)
    except Exception: pass

def get_team_icon(squadra):
    return dati.icona_squadra(squadra)


def auto_download_listone_raw():
    return dati.scarica_master()


def auto_download_listone():
    if auto_download_listone_raw():
        load_data(force_reload=True)
        return True
    return False

def load_data(force_reload=False):
    return dati.carica(forza=force_reload)


def get_session(user_id):
    if user_id not in user_sessions: 
        user_sessions[user_id] = {
            'budget': 500, 
            'rosa': [], 
            'wishlist': [], 
            'scartati': [], 
            'compare_p1': None,
            'lega_budget_iniziale': 500,  
            'lega_partecipanti': 8,
            'modificatore_attivo': False,
            'fase_asta': None,
            'registro': {'voci': [], 'avversari': [],
                         'budget_iniziale': 500, 'partecipanti': 8},
            'strategia': 'equilibrata',
        }
    return user_sessions[user_id]


def get_registro(session):
    """Il taccuino della sessione. Si ricostruisce dal dizionario ogni volta:
    e' poca roba e cosi' non esistono due copie che possono divergere."""
    dati_registro = session.setdefault('registro', {})
    dati_registro.setdefault('budget_iniziale', session.get('lega_budget_iniziale', 500))
    dati_registro.setdefault('partecipanti', session.get('lega_partecipanti', 8))
    return reg.Registro(dati_registro)


def salva_registro(registro_asta, session):
    """Scrive il registro e riallinea le chiavi che il resto del bot legge."""
    reg.sincronizza(registro_asta, session)
    salva_sessioni()
    return session

def get_roster_stats(session):
    return dati.stato_rosa(session)


def get_available_players(df, session):
    return dati.disponibili(df, session)


def get_player_stats(nome, df):
    return dati.cerca_giocatore(nome, df)


def get_macellaio_info(nome, df):
    row = get_player_stats(nome, df)
    if row is not None:
        try:
            amm = int(pd.to_numeric(row.get('Amm', 0), errors='coerce'))
            esp = int(pd.to_numeric(row.get('Esp', 0), errors='coerce'))
            pv = int(pd.to_numeric(row.get('Pv', row.get('Pres', 1)), errors='coerce'))
            
            if (amm >= 6 or esp >= 1) and pv > 5:
                return f"\n🪓 <b>ALLARME MACELLAIO:</b> <code>{amm} Gialli</code>, <code>{esp} Rossi</code>"
            else:
                return f"\n🛡 <b>Disciplinato:</b> <code>{amm} Gialli</code>, <code>{esp} Rossi</code>"
        except Exception: pass
    return "\n🛡 <b>Dati Cartellini assenti nel Master.</b>"

def get_storico(nome, df):
    row = get_player_stats(nome, df)
    if row is None:
        return "⚠️ Nessun dato presente nel file Master per questo giocatore."

    prof = analisi.profilo(row, analisi.statistiche_squadre(df), analisi.baseline_ruoli(df))
    titolo = f"📊 <b>STORICO (Dal file Master): {html.escape(prof['nome'].upper())}</b>\n───────────────────────────\n"

    # Tre casi distinti: storico vero, proiezione su dati esteri, nessun dato.
    if prof['senza_dati']:
        return (titolo +
                "❔ <b>Nessuno storico disponibile.</b>\n"
                "Non ha giocato in Serie A e le fonti esterne non lo coprono.\n"
                f"La valutazione si basa solo sulla quotazione ufficiale "
                f"(<code>{prof['quotazione']:.0f}</code>).\n")

    if prof['proiezione']:
        return (titolo +
                "🆕 <b>Nuovo in Serie A</b> — nessuna presenza nel campionato italiano.\n"
                f"🔮 Fantamedia <b>proiettata</b> dai dati esteri: <code>{prof['fantamedia']:.2f}</code>\n"
                "<i>È una stima, non un rendimento reale: pesala di conseguenza.</i>\n")

    testo = (titolo +
        f"🏟 Pres: <code>{prof['presenze']}</code> ({prof['etichetta_titolarita']}) │ "
        f"📈 MV: <code>{prof['voto_puro']:.2f}</code> │ FM: <code>{prof['fantamedia']:.2f}</code>\n"
        f"🎁 Bonus a partita: <code>{prof['bonus_partita']:+.2f}</code>\n"
        f"⚽ Gol: <code>{prof['gol']}</code> │ 🎯 Ass: <code>{prof['assist']}</code> │ "
        f"🟨 <code>{prof['ammonizioni']}</code> │ 🟥 <code>{prof['espulsioni']}</code>\n"
    )
    if prof['rigorista']:
        testo += f"⚪ <b>Rigorista</b>: {prof['rigori_calciati']} rigori calciati\n"
    if prof.get('gol_subiti_partita') is not None and prof['ruolo'] in ('P', 'D'):
        testo += f"🛡 Gol subiti dalla squadra: <code>{prof['gol_subiti_partita']}</code> a partita\n"
    if prof['presenze'] < 10:
        testo += "\n⚠️ <i>Poche presenze: le medie non sono affidabili.</i>\n"
    return testo


def draw_pitch_image(titolari_by_role, schema="3-4-3"):
    if not PIL_ENABLED: return None
    img_w, img_h = 600, 800
    image = Image.new("RGB", (img_w, img_h), "#2e7d32")
    draw = ImageDraw.Draw(image)
    draw.rectangle([20, 20, img_w - 20, img_h - 20], outline="white", width=3)
    draw.line([20, img_h // 2, img_w - 20, img_h // 2], fill="white", width=2)
    draw.ellipse([img_w // 2 - 60, img_h // 2 - 60, img_w // 2 + 60, img_h // 2 + 60], outline="white", width=2)
    draw.rectangle([150, 20, img_w - 150, 140], outline="white", width=2)
    draw.rectangle([150, img_h - 140, img_w - 150, img_h - 20], outline="white", width=2)

    parts = [int(x) for x in schema.split("-")] if "-" in schema else [3, 4, 3]
    num_d, num_c, num_a = parts[0], parts[1], parts[2]
    y_p, y_d, y_c, y_a = img_h - 60, img_h - 220, img_h - 440, img_h - 660

    def calc_x(count): return [40 + ((img_w - 80) // (count + 1)) * (i + 1) for i in range(count)]

    coords = []
    if titolari_by_role.get('P'): coords.append((titolari_by_role['P'][0]['nome'], img_w // 2, y_p, "🧤"))
    for i, p in enumerate(titolari_by_role.get('D', [])[:num_d]): coords.append((p['nome'], calc_x(num_d)[i], y_d, "🛡️"))
    for i, p in enumerate(titolari_by_role.get('C', [])[:num_c]): coords.append((p['nome'], calc_x(num_c)[i], y_c, "⚙️"))
    for i, p in enumerate(titolari_by_role.get('A', [])[:num_a]): coords.append((p['nome'], calc_x(num_a)[i], y_a, "🎯"))

    for nome, x, y, icon in coords:
        draw.ellipse([x - 22, y - 22, x + 22, y + 22], fill="#1b5e20", outline="white", width=2)
        draw.text((x - 8, y - 10), icon, fill="white")
        draw.rectangle([x - 35, y + 24, x + 35, y + 40], fill="black")
        draw.text((x - 30, y + 26), nome.split()[0][:8], fill="white")

    buf = io.BytesIO()
    image.save(buf, format='PNG')
    buf.seek(0)
    return buf

def advanced_trade_analyzer_3d(p1, p2, session, df=None):
    """Confronto voce per voce (analisi.confronta) + impatto sulla rosa."""
    esito = analisi.confronta(p1, p2, df, modificatore_difesa=session.get('modificatore_attivo', False))
    testo = analisi.formatta_confronto(esito)

    rosa = session.get('rosa', [])
    r1, r2 = p1.get('R', 'C'), p2.get('R', 'C')
    c1 = sum(1 for p in rosa if p.get('ruolo') == r1)
    c2 = sum(1 for p in rosa if p.get('ruolo') == r2)
    avvisi = []
    if r1 != r2:
        if c1 <= 3 and r1 in ['D', 'C']: avvisi.append(f"🚨 Sei corto in <b>{r1}</b> ({c1} in rosa)")
        if c2 >= 8 and r2 in ['D', 'C']: avvisi.append(f"⚠️ Sei gia' pieno in <b>{r2}</b> ({c2} in rosa)")

    budget = session.get('budget', 0)
    for profilo_g in (esito['p1'], esito['p2']):
        if profilo_g['prezzo'] > budget:
            avvisi.append(f"💸 {profilo_g['nome']} costa piu' del budget residuo ({budget} cr)")

    if avvisi:
        testo += "\n\n" + "\n".join(avvisi)
    return testo


def calcola_formazione_ideale(session, df):
    """
    Schieramento consigliato. Il 'power' non somma piu' fantamedia e voto
    (che si contavano due volte): usa la fantamedia ponderata per presenze,
    con un bonus per chi e' titolare fisso e un malus per i cartellini.
    """
    rosa = session.get('rosa', [])
    if not rosa:
        return "❌ <b>La tua rosa è vuota!</b> Acquista o aggiungi giocatori.", None

    baseline = analisi.baseline_ruoli(df)
    per_ruolo = {'P': [], 'D': [], 'C': [], 'A': []}

    for p in rosa:
        ruolo = p.get('ruolo', 'C')
        if ruolo not in per_ruolo:
            continue
        row = get_player_stats(p['nome'], df)
        if row is None:
            per_ruolo[ruolo].append({'nome': p['nome'], 'power': 0.0, 'fm': 0.0,
                                     'amm': 0, 'pres': 0, 'nota': 'senza dati'})
            continue

        prof = analisi.profilo(row, None, baseline)
        power = prof['fantamedia_ponderata'] + (prof['titolarita'] * 0.5) - (prof['ammonizioni'] * 0.02)
        per_ruolo[ruolo].append({
            'nome': prof['nome'], 'power': round(power, 3), 'fm': prof['fantamedia'],
            'amm': prof['ammonizioni'], 'pres': prof['presenze'],
            'nota': prof['etichetta_titolarita'],
        })

    for ruolo in per_ruolo:
        per_ruolo[ruolo].sort(key=lambda x: x['power'], reverse=True)

    # Il modulo si adatta a chi hai davvero in rosa
    moduli = [(3, 4, 3), (3, 5, 2), (4, 4, 2), (4, 3, 3), (4, 5, 1), (5, 3, 2), (5, 4, 1)]
    disponibili = {r: len(per_ruolo[r]) for r in per_ruolo}
    schema = next((m for m in moduli
                   if disponibili['D'] >= m[0] and disponibili['C'] >= m[1] and disponibili['A'] >= m[2]),
                  None)
    if schema is None:
        schema = (min(disponibili['D'], 3), min(disponibili['C'], 4), min(disponibili['A'], 3))

    titolari = {
        'P': per_ruolo['P'][:1],
        'D': per_ruolo['D'][:schema[0]],
        'C': per_ruolo['C'][:schema[1]],
        'A': per_ruolo['A'][:schema[2]],
    }
    nomi_titolari = {x['nome'] for gruppo in titolari.values() for x in gruppo}
    panchina = {r: [x for x in per_ruolo[r] if x['nome'] not in nomi_titolari] for r in per_ruolo}

    modulo = f"{schema[0]}-{schema[1]}-{schema[2]}"
    testo = f"📋 <b>FORMAZIONE CONSIGLIATA ({modulo})</b>\n━━━━━━━━━━━━━━━━━━━━━━\n<b>TITOLARI:</b>\n"
    for ruolo in ['P', 'D', 'C', 'A']:
        elenco = ", ".join(x['nome'] for x in titolari[ruolo]) or "—"
        testo += f"{ROLE_ICONS[ruolo]} <b>{ruolo}:</b> {elenco}\n"

    voci_panchina = []
    for ruolo in ['P', 'D', 'C', 'A']:
        if panchina[ruolo]:
            nomi = ", ".join(f"{x['nome']} ({x['fm']:.2f})" for x in panchina[ruolo][:3])
            voci_panchina.append(f"{ROLE_ICONS[ruolo]} <b>{ruolo}:</b> {nomi}")
    if voci_panchina:
        testo += "\n<b>PANCHINA:</b>\n" + "\n".join(voci_panchina) + "\n"

    if disponibili['P'] == 0:
        testo += "\n🚨 <b>Manca il portiere!</b>\n"

    rischi = [f"⚠️ {x['nome']} ({x['amm']} gialli)"
              for gruppo in titolari.values() for x in gruppo if x['amm'] >= 4]
    panchinari = [f"🪑 {x['nome']} è un {x['nota']} ({x['pres']} pres.)"
                  for gruppo in titolari.values() for x in gruppo
                  if x['nota'] in ('riserva', 'alternanza')]
    if rischi:
        testo += "\n🚨 <b>RADAR DIFFIDATI:</b>\n" + "\n".join(rischi) + "\n"
    if panchinari:
        testo += "\n<b>ATTENZIONE ALLA TITOLARITÀ:</b>\n" + "\n".join(panchinari)

    return testo, draw_pitch_image(titolari, modulo)


# ==========================================
# MENU E DASHBOARD
# ==========================================
SLOT_PER_RUOLO_HOME = {'P': 3, 'D': 8, 'C': 8, 'A': 6}


def main_menu_keyboard(session):
    """Poche voci in home: gli strumenti di scouting stanno in un sottomenu."""
    markup = InlineKeyboardMarkup(row_width=2)
    if session.get('fase_asta'):
        markup.add(InlineKeyboardButton("🔴  RIPRENDI ASTA", callback_data="asta_resume"))
        markup.add(InlineKeyboardButton("🛑  Termina asta", callback_data="asta_end"))
    else:
        markup.add(InlineKeyboardButton("🔨  AVVIA ASTA LIVE", callback_data="asta_setup_start"))

    markup.add(InlineKeyboardButton("👕  Esplora", callback_data="sq_start"),
               InlineKeyboardButton("📋  La mia rosa", callback_data="menu_rosa"))
    markup.add(InlineKeyboardButton("🔎  Scouting", callback_data="menu_scouting"),
               InlineKeyboardButton("⚖️  Confronta", callback_data="menu_studio_start"))
    markup.add(InlineKeyboardButton("⭐  Wishlist", callback_data="menu_wishlist"),
               InlineKeyboardButton("⚽  Formazione", callback_data="menu_formazione"))
    markup.add(InlineKeyboardButton("⚙️  Lega", callback_data="menu_impostazioni_lega"),
               InlineKeyboardButton("🧰  Sistema", callback_data="menu_sistema"))
    return markup


def mostra_panic(chat_id, message_id, df, session, ruolo_forzato=None):
    """
    Come spartire i crediti che restano fra le caselle che mancano.

    I giocatori stanno SOLO nei pulsanti: elencarli anche nel testo faceva
    scorrere mezzo schermo prima di arrivare a qualcosa di cliccabile, e
    all'asta il tempo per scorrere non c'e'.
    """
    stato = dati.stato_rosa(session)
    avail = get_available_players(df, session)
    mancanti = {r: SLOT_PER_RUOLO[r] - stato['counts'].get(r, 0) for r in SLOT_PER_RUOLO}

    piano = analisi.piano_emergenza(
        df, avail, mancanti, session.get('budget', 0), SLOT_PER_RUOLO,
        ordine=config.ORDINE_ASTA, quote=config.QUOTE_REPARTO,
        ruolo_forzato=ruolo_forzato)

    markup = InlineKeyboardMarkup(row_width=1)

    if not piano or piano.get('reparti_finiti'):
        bot.edit_message_text(
            "🚨 <b>PANIC BUTTON</b>\n\nRosa completa: non ti serve nessuno.",
            chat_id, message_id, parse_mode="HTML",
            reply_markup=markup.add(
                InlineKeyboardButton("🏠 Home", callback_data="go_home")))
        return

    ruolo = piano['ruolo']
    tetti = "  ".join(str(b['tetto']) for b in piano['fasce'])

    righe = [f"🚨 <b>PANIC BUTTON</b>  ·  {ROLE_ICONS[ruolo]} reparto <b>{ruolo}</b>",
             f"💼 <b>{piano['disponibile']} cr</b> per <b>{piano['mancanti']}</b> slot"]
    if piano['riserva'] > 0:
        dopo = "".join(ROLE_ICONS[r] for r in piano['scoperti'] if r != ruolo)
        righe.append(f"🔒 <b>{piano['riserva']}</b> da tenere per {dopo}")
    righe.append(f"📉 come dividerli:  <b>{tetti}</b>")

    vuote = 0
    for blocco in piano['fasce']:
        if blocco['candidati'] is None:
            vuote += 1
            continue
        for _, riga in blocco['candidati'].iterrows():
            prezzo = int(_num(riga.get('Prezzo'), 1))
            presenze = int(_num(riga.get('Pv')))
            segno = "⚠️" if presenze < blocco['presenze_minime'] else "·"
            markup.add(InlineKeyboardButton(
                f"{blocco['posto']}º ≤{blocco['tetto']}  {riga['Nome']}  "
                f"{prezzo}cr {segno} {presenze}pres",
                callback_data=f"sq_pl_{riga['Nome']}"))
    if vuote:
        righe.append(f"<i>{vuote} caselle senza candidati entro la cifra</i>")

    altri = [r for r in piano['scoperti'] if r != ruolo]
    if altri:
        markup.row(*[InlineKeyboardButton(f"{ROLE_ICONS[r]} {r}",
                                          callback_data=f"panic_ru_{r}")
                     for r in altri])
    markup.add(InlineKeyboardButton("🔙 Scouting", callback_data="menu_scouting"),
               InlineKeyboardButton("🏠 Home", callback_data="go_home"))
    bot.edit_message_text("\n".join(righe), chat_id, message_id,
                          parse_mode="HTML", reply_markup=markup)


def scouting_menu_keyboard():
    """Tutti gli strumenti di ricerca giocatori, in un posto solo."""
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("👑  Top liberi", callback_data="menu_top_start"),
               InlineKeyboardButton("💎  Gemme", callback_data="menu_gemme_start"))
    markup.add(InlineKeyboardButton("🎯  Rigoristi", callback_data="menu_rigoristi"),
               InlineKeyboardButton("🛡️  Modificatore", callback_data="menu_modificatore"))
    markup.add(InlineKeyboardButton("🔥  Power index", callback_data="menu_power"),
               InlineKeyboardButton("🧱  Stakanovisti", callback_data="pro_stakanov"))
    markup.add(InlineKeyboardButton("🎰  Tappabuchi", callback_data="pro_spiccioli"),
               InlineKeyboardButton("🧤  Griglia difesa", callback_data="pro_griglia"))
    markup.add(InlineKeyboardButton("🚨  Panic button", callback_data="menu_panic_start"),
               InlineKeyboardButton("⚖️  Confronta", callback_data="menu_studio_start"))
    markup.add(InlineKeyboardButton("🔙  Indietro", callback_data="go_home"))
    return markup


# Telegram non trasforma una foto in testo: se il messaggio corrente e'
# un'immagine, edit_message_text fallisce. Invece di correggere quaranta
# chiamate, si rende tollerante quella una volta sola.
_edit_testo_originale = bot.edit_message_text


def _edit_testo_tollerante(text, chat_id=None, message_id=None, **extra):
    try:
        return _edit_testo_originale(text, chat_id=chat_id, message_id=message_id, **extra)
    except Exception:
        pass

    # secondo tentativo: forse e' una foto e basta cambiare la didascalia
    try:
        return bot.edit_message_caption(
            caption=text, chat_id=chat_id, message_id=message_id,
            parse_mode=extra.get('parse_mode'), reply_markup=extra.get('reply_markup'))
    except Exception:
        pass

    # ultimo: si sostituisce il messaggio
    try:
        bot.delete_message(chat_id, message_id)
    except Exception:
        pass
    return bot.send_message(
        chat_id, text, parse_mode=extra.get('parse_mode'),
        reply_markup=extra.get('reply_markup'),
        disable_web_page_preview=extra.get('disable_web_page_preview'))


bot.edit_message_text = _edit_testo_tollerante


def invia_immagine(chat_id, immagine, message_id=None, markup=None, didascalia=None):
    """
    Manda un PNG, sostituendo il messaggio precedente quando possibile.
    Telegram non converte un messaggio di testo in foto: se l'edit fallisce
    si cancella il vecchio e se ne manda uno nuovo, cosi' la chat resta pulita.
    """
    foto = io.BytesIO(immagine)
    foto.name = "fantahub.png"
    if message_id:
        try:
            bot.edit_message_media(
                media=InputMediaPhoto(foto, caption=didascalia, parse_mode="HTML"),
                chat_id=chat_id, message_id=message_id, reply_markup=markup)
            return
        except Exception:
            try:
                bot.delete_message(chat_id, message_id)
            except Exception:
                pass
            foto = io.BytesIO(immagine)
            foto.name = "fantahub.png"
    bot.send_photo(chat_id, foto, caption=didascalia, parse_mode="HTML", reply_markup=markup)


def taglia_didascalia(testo, limite=1024):
    """
    Telegram rifiuta le didascalie oltre 1024 caratteri e il messaggio non parte
    affatto. Si tagliano le righe dal fondo del blocco rischio, che e' l'unico
    di lunghezza imprevedibile, tenendo prezzo e cassa che stanno in fondo.
    """
    if len(testo) <= limite:
        return testo

    righe = testo.split("\n")
    # Le righe di dettaglio del rischio iniziano con l'indentazione a "└"
    while len(("\n".join(righe))) > limite and any("└" in r for r in righe):
        for indice in range(len(righe) - 1, -1, -1):
            if "└" in righe[indice]:
                righe.pop(indice)
                break

    testo = "\n".join(righe)
    return testo if len(testo) <= limite else testo[:limite - 1] + "…"


def barra(valore, totale, caselle=6):
    """Barra proporzionale: la lunghezza si legge prima della cifra."""
    try:
        if totale <= 0:
            return "▱" * caselle
        piene = max(0, min(caselle, round((float(valore) / float(totale)) * caselle)))
    except Exception:
        piene = 0
    return "▰" * piene + "▱" * (caselle - piene)


def send_dashboard(chat_id, user_id, message_id=None):
    session = get_session(user_id)
    stats = get_roster_stats(session)
    markup = main_menu_keyboard(session)

    dati = {
        'budget': session['budget'],
        'budget_iniziale': session.get('lega_budget_iniziale', 500),
        'slot_liberi': stats['slot_liberi'],
        'max_bid': stats['max_bid'],
        'conteggi': stats['counts'],
        'slot_totali': SLOT_PER_RUOLO_HOME,
        'stato': 'asta live' if session.get('fase_asta') else 'pre-asta',
    }

    try:
        invia_immagine(chat_id, interfaccia.disegna_dashboard_v2(dati), message_id, markup)
        return
    except Exception as e:
        print(f"⚠️ Dashboard grafica non disponibile ({e}): uso il testo.")

    # Ripiego testuale: il bot deve funzionare anche se il disegno fallisce
    conteggi = stats['counts']
    testo = (f"<b>FANTAHUB</b>\n💰 <b>{session['budget']}</b> cr · {stats['slot_liberi']} slot\n"
             f"🛑 offerta massima <b>{stats['max_bid']}</b> cr\n\n"
             + "  ·  ".join(f"{ROLE_ICONS[r]} {conteggi[r]}/{SLOT_PER_RUOLO_HOME[r]}"
                            for r in ('P', 'D', 'C', 'A')))
    if message_id:
        try:
            bot.edit_message_text(testo, chat_id, message_id, parse_mode="HTML", reply_markup=markup)
            return
        except Exception:
            pass
    bot.send_message(chat_id, testo, parse_mode="HTML", reply_markup=markup)


SLOT_PER_RUOLO = {'P': 3, 'D': 8, 'C': 8, 'A': 6}


def get_strategia_asta(fase, session, df=None):
    """Consiglio costruito sulla rosa vera, non un testo fisso per fase."""
    stats = get_roster_stats(session)
    avuti = stats['counts'].get(fase, 0)
    mancanti = max(0, SLOT_PER_RUOLO.get(fase, 0) - avuti)
    budget = session.get('budget', 0)
    slot_liberi = stats['slot_liberi']
    media_slot = (budget / slot_liberi) if slot_liberi > 0 else 0
    modificatore = session.get('modificatore_attivo', False)

    righe = [f"Ti mancano <b>{mancanti}</b> giocatori in {fase} "
             f"(hai {avuti}/{SLOT_PER_RUOLO.get(fase, 0)}). "
             f"Con {budget} cr e {slot_liberi} slot, la media e' <b>{media_slot:.0f} cr</b> a giocatore."]

    if df is not None and not df.empty:
        disponibili = get_available_players(df, session)
        nel_ruolo = disponibili[disponibili['R'] == fase].copy()
        if not nel_ruolo.empty:
            nel_ruolo['_prezzo'] = [fair_price(r, session) for _, r in nel_ruolo.iterrows()]
            nel_ruolo['_pv'] = nel_ruolo['Pv'].apply(_num) if 'Pv' in nel_ruolo.columns else 0
            alla_portata = nel_ruolo[nel_ruolo['_prezzo'] <= max(1, media_slot)]
            titolari_portata = alla_portata[alla_portata['_pv'] >= 25]

            migliore = nel_ruolo.sort_values('_prezzo', ascending=False).iloc[0]
            if migliore['_prezzo'] > budget:
                righe.append(f"⛔ Il migliore rimasto ({migliore['Nome']}, {int(migliore['_prezzo'])} cr) "
                             f"e' fuori dal tuo budget: punta sulla fascia sotto.")
            elif migliore['_prezzo'] > media_slot * 2.5 and mancanti > 2:
                righe.append(f"⚠️ {migliore['Nome']} costa {int(migliore['_prezzo'])} cr: "
                             f"prenderlo ti lascia {(budget - int(migliore['_prezzo'])) // max(1, slot_liberi - 1)} cr "
                             f"a slot per gli altri {slot_liberi - 1}.")

            righe.append(f"Alla tua media ci sono <b>{len(titolari_portata)}</b> titolari "
                         f"(25+ presenze) ancora liberi in {fase}.")
            if len(titolari_portata) <= mancanti and mancanti > 0:
                righe.append("🚨 Sono pochi per coprire gli slot: muoviti adesso o resterai coi fondi di magazzino.")

    if fase == 'D' and modificatore:
        righe.append("Modificatore attivo: conta il <b>voto puro</b>, non i bonus. "
                     "Guarda la lista Modificatore 6.5.")
    elif fase == 'P':
        righe.append("Sui portieri l'incrocio con il vice della stessa squadra vale piu' del nome.")

    return " ".join(righe)


def send_asta_dashboard(chat_id, user_id, message_id=None):
    session = get_session(user_id)
    df = load_data()
    fase, budget, b_iniziale = session.get('fase_asta', 'P'), session['budget'], session.get('lega_budget_iniziale', 500)
    lega_part, modif = session.get('lega_partecipanti', 8), session.get('modificatore_attivo', False)
    
    avail = get_available_players(df, session)
    giocatori = avail[avail['R'] == fase].copy()
    giocatori['_p'] = [fair_price(r, session) for _, r in giocatori.iterrows()]
    giocatori = giocatori.sort_values('_p', ascending=False)
    
    top_str = ""
    for i, (_, r) in enumerate(giocatori.head(5).iterrows(), 1):
        max_bid = fair_price(r, session)
        pres = int(_num(r.get('Pv')))
        top_str += f"{i}. <b>{r['Nome']}</b> ({r['Squadra']}) ─ <code>{max_bid} cr.</code> · {pres} pres\n"
    
    testo = (f"🔨 <b>ASTA LIVE - FASE: {ROLE_ICONS.get(fase, '')} {fase}</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
             f"⭐ <b>TOP 5 RIMASTI:</b>\n{top_str}\n🧠 <b>STRATEGIA:</b>\n<i>{get_strategia_asta(fase, session, df)}</i>\n"
             f"━━━━━━━━━━━━━━━━━━━━━━\n💰 <b>Cassa:</b> <code>{budget} cr.</code> (Slot liberi: {get_roster_stats(session)['slot_liberi']})\n")
    
    if fase == 'D' and modif:
        mods = analisi.candidati_modificatore(avail, limite=3)
        if mods is not None and not mods.empty:
            testo += "\n🛡️ <b>TOP MODIFICATORE DA PUNTARE:</b>\n" + "\n".join(
                [f"• {r['Nome']} ({r['Squadra']}) - MV {_num(r.get('Mv')):.2f} · {fair_price(r, session)} cr"
                 for _, r in mods.iterrows()]) + "\n"
        
    testo += "\n💡 <i>Cerca un nome o invia un vocale! (es: + nome prezzo)</i>"
    
    markup = InlineKeyboardMarkup(row_width=2)
    next_fase = {'P': 'D', 'D': 'C', 'C': 'A', 'A': None}
    if next_fase[fase]: markup.add(InlineKeyboardButton(f"⏭️ Passa ai {next_fase[fase]}", callback_data=f"asta_fase_{next_fase[fase]}"))
    markup.add(InlineKeyboardButton("📚 Menu Principale (Studio)", callback_data="go_home"))
    
    if message_id:
        try: bot.edit_message_text(testo, chat_id, message_id, parse_mode="HTML", reply_markup=markup)
        except Exception: bot.send_message(chat_id, testo, parse_mode="HTML", reply_markup=markup)
    else: bot.send_message(chat_id, testo, parse_mode="HTML", reply_markup=markup)

# =========================================================================
# SCHEDA GIOCATORE CON PREZZI E FASCE REALI
# =========================================================================
def send_player_card_view(chat_id, player_name, message_id, df, session, is_scommessa=False):
    p_data = df[df['Nome'] == player_name].iloc[0]
    sq_name, ruolo, fvm = p_data.get('Squadra', '-'), str(p_data.get('R', '-')), p_data.get('FVM', 0)
    photo_embed = f'<a href="{html.escape(str(p_data.get("PhotoURL", "")).strip())}">&#8203;</a>' if str(p_data.get("PhotoURL", "")).strip().startswith('http') else ''
    
    try: fvm_val = float(str(fvm).replace(',', '.'))
    except ValueError: fvm_val = 0.0

    lega_bud = session.get('lega_budget_iniziale', 500)
    lega_part = session.get('lega_partecipanti', 8)
    part_factor = 1 + ((lega_part - 8) * 0.025)

    # Il prezzo lo calcola il Master (colonna Prezzo, tarata su 8 squadre/500 crediti).
    # Qui si riscala solo su budget e numero di partecipanti della lega.
    fair_price_val = fair_price(p_data, session)

    max_rilancio = int(fair_price_val * 1.15)
    asta_stop = int(fair_price_val * 1.25)

    # Fascia = posizione nel proprio ruolo, non soglia in crediti: cosi' resta
    # valida anche cambiando budget o numero di partecipanti.
    # Il rango da solo non basta: "TOP" non dice se ne restano cinque o uno.
    disponibili = get_available_players(df, session)
    nomi_liberi = set(disponibili['Nome'].astype(str)) if disponibili is not None else None
    contesto = analisi.contesto_asta(player_name, df, nomi_liberi, lega_part)
    if contesto:
        # Una riga sola: fascia, posizione e quanti ne restano. Prima erano
        # due righe che sul telefono andavano a capo e si leggevano male.
        liberi = contesto['rimasti_fascia']
        fascia = (f"{contesto['etichetta']}  ·  <b>#{contesto['posizione']}</b> "
                  f"di {contesto['totale_ruolo']} {ruolo}")
        if contesto['totale_fascia']:
            fascia += (f"  ·  <b>{liberi}</b> liber{'o' if liberi == 1 else 'i'} "
                       f"in fascia")
    else:
        fascia = "—"

    stats = get_roster_stats(session)
    prof = analisi.profilo(p_data, analisi.statistiche_squadre(df),
                           analisi.baseline_ruoli(df), analisi.gerarchia_rigori(df))
    rischio = analisi.valuta_rischio(p_data, df, lega_part)
    banner = analisi.banner_infortunio(p_data)

    # Barre: la lunghezza si legge prima della cifra
    riga_titolarita = (f"Titolarità  <code>{barra(prof['presenze'], 38)}</code>  "
                       f"{prof['presenze']}/38" if prof['presenze'] else "")
    riga_bonus = (f"Bonus       <code>{barra(prof['bonus_partita'], 1.2)}</code>  "
                  f"{prof['bonus_partita']:+.2f}" if prof['fantamedia'] else "")
    saltate = prof.get('gare_saltate', 0)
    riga_integrita = (f"Integrità   <code>{barra(max(0, 38 - saltate), 38)}</code>  "
                      f"{saltate} salt." if saltate else "")
    barre = "\n".join(r for r in (riga_titolarita, riga_bonus, riga_integrita) if r)

    avvisi = analisi.formatta_rischio(rischio, compatto=False)
    macellaio = get_macellaio_info(player_name, df).strip()
    mostra_macellaio = macellaio and 'ALLARME' in macellaio

    # Da dove viene il bonus, e se e' davvero lui a tirare i rigori.
    riga_gol = analisi.riga_bonus(prof, analisi.gerarchia_rigori(df))

    # Modello e listino in disaccordo: detto a parole, non in percentuale.
    nota = analisi.nota_valore(prof)

    # Dove sta dentro il suo ruolo: un numero assoluto non si giudica da solo.
    riga_confronto = analisi.righe_percentili(analisi.percentili_ruolo(p_data, df))

    # Su difensori e portieri la fantamedia inganna: il modificatore si calcola
    # sui VOTI, e i gol subiti dalla squadra li abbassano. Si mostrano solo a
    # chi servono, e solo quando ci sono davvero.
    riga_difesa = ""
    if ruolo in ('P', 'D') and prof['voto_puro'] > 0:
        pezzi_difesa = [f"voto puro <b>{prof['voto_puro']:.2f}</b>"]
        subiti = prof.get('gol_subiti_partita')
        if subiti:
            pezzi_difesa.append(f"{html.escape(str(sq_name))} subisce "
                                f"<b>{subiti:.2f}</b> gol a partita")
        riga_difesa = "🛡️ " + "  ·  ".join(pezzi_difesa)

    # Il portiere si compra in coppia: il vice della stessa squadra e' il
    # paracadute, e il suo prezzo va saputo PRIMA di aprire l'asta sul titolare.
    riga_partner = ""
    if ruolo == 'P':
        partner = trova_partner_portiere(player_name, df)
        if partner:
            riga_altro = get_player_stats(partner, df)
            costo = fair_price(riga_altro, session) if riga_altro is not None else 1
            riga_partner = f"🧤 in coppia con <b>{html.escape(partner)}</b> ({costo} cr)"

    # Ti serve davvero? E' la domanda che viene prima del prezzo.
    slot_ruolo = SLOT_PER_RUOLO.get(ruolo, 0)
    presi = stats['counts'].get(ruolo, 0)
    mancanti = slot_ruolo - presi
    riga_slot = ""
    if slot_ruolo and mancanti > 0:
        media_slot = max(1, int(stats['max_bid'] / max(1, stats['slot_liberi'])))
        quanti = (f"<b>{mancanti} {ruolo}</b> da prendere" if presi == 0
                  else f"ne mancano <b>{mancanti}</b> su {slot_ruolo} {ruolo}")
        riga_slot = f"🎯 {quanti}  ·  ~{media_slot} cr a slot"
    elif slot_ruolo:
        riga_slot = f"🎯 reparto <b>{ruolo}</b> già completo"

    info_text = (
        f"{photo_embed}<b>{html.escape(player_name.upper())}</b>  ·  "
        f"{get_team_icon(sq_name)} {html.escape(sq_name)}  ·  <code>{html.escape(ruolo)}</code>\n"
        f"{fascia}\n"
        + (f"\n{banner}\n" if banner else "")
        + (f"\n{barre}\n" if barre else "")
        + (f"{riga_gol}\n" if riga_gol else "")
        + (f"{riga_difesa}\n" if riga_difesa else "")
        + (f"{riga_partner}\n" if riga_partner else "")
        + (f"\n{riga_confronto}\n" if riga_confronto else "")
        + f"\n{avvisi}\n"
        + (f"{macellaio}\n" if mostra_macellaio else "")
        + f"\n💰 <b>{fair_price_val} cr</b>  ·  max <b>{max_rilancio}</b>  ·  stop <b>{asta_stop}</b>\n"
        + (f"{nota}\n" if nota else "")
        + (f"{riga_slot}\n" if riga_slot else "")
        + f"💼 cassa <b>{session['budget']}</b> cr  ·  offerta max <b>{stats['max_bid']}</b>\n"
    )

    is_asta = session.get('fase_asta') is not None
    markup = InlineKeyboardMarkup(row_width=2)
    if is_asta:
        markup.add(InlineKeyboardButton("🙋‍♂️ L'ho preso IO!", callback_data=f"buy_{player_name}"), InlineKeyboardButton("👥 Preso da ALTRI", callback_data=f"taken_{player_name}"))
        markup.add(InlineKeyboardButton("🔙 Torna alla Dashboard Asta", callback_data="asta_resume"))
    else:
        markup.add(InlineKeyboardButton("⚡ Compra (Test)", callback_data=f"buy_{player_name}"), InlineKeyboardButton("🚫 Scarta", callback_data=f"taken_{player_name}"))

    markup.add(InlineKeyboardButton("📊 Storico (Master)", callback_data=f"stats_{player_name}"), InlineKeyboardButton("🔄 Sliding Doors", callback_data=f"sd_{player_name}"))
    markup.add(InlineKeyboardButton("🔮 Simula What-If", callback_data=f"wi_{player_name}"))
    
    in_wl = player_name in session.get('wishlist', [])
    if is_scommessa:
        markup.add(InlineKeyboardButton("❌ Rimuovi WL" if in_wl else "⭐ Aggiungi WL", callback_data=f"wl_toggle_{player_name}"), InlineKeyboardButton("🎲 Altra Scommessa", callback_data="menu_scommessa_start"))
    else:
        markup.add(InlineKeyboardButton("❌ Rimuovi WL" if in_wl else "⭐ Aggiungi WL", callback_data=f"wl_toggle_{player_name}"))
        
    if not is_asta:
        # "Indietro" riporta alla lista da cui si e' arrivati (squadra, fascia,
        # rigoristi...): il contesto viene salvato dalle liste stesse.
        ritorno = session.get('ritorno')
        if ritorno and ritorno != "go_home":
            markup.add(InlineKeyboardButton("🔙 Indietro", callback_data=ritorno),
                       InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        else:
            markup.add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
    
    # Immagine piccola + testo: l'immagine fa solo la faccia e il prezzo,
    # i numeri stanno nella didascalia dove si possono leggere e copiare.
    dati_striscia = {
        'nome': player_name,
        'squadra': str(sq_name),
        'ruolo': ruolo,
        'fascia': (f"{contesto['etichetta'].split(maxsplit=1)[-1]}  #{contesto['posizione']} "
                   f"di {contesto['totale_ruolo']}" if contesto else ''),
        'prezzo': fair_price_val, 'max': max_rilancio, 'stop': asta_stop,
        'foto_api': str(p_data.get('FotoAPI', '') or ''),
        'foto': str(p_data.get('PhotoURL', '') or ''),
    }

    try:
        invia_immagine(chat_id, interfaccia.disegna_striscia(dati_striscia),
                       message_id, markup, didascalia=taglia_didascalia(info_text))
        return
    except Exception as e:
        print(f"⚠️ Striscia grafica non disponibile ({e}): uso il solo testo.")

    try:
        bot.edit_message_text(info_text, chat_id, message_id, parse_mode="HTML",
                              reply_markup=markup, disable_web_page_preview=False)
    except Exception:
        try:
            bot.delete_message(chat_id, message_id)
        except Exception:
            pass
        bot.send_message(chat_id, info_text, parse_mode="HTML", reply_markup=markup,
                         disable_web_page_preview=False)


def system_menu_keyboard():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("📥 Download Remoto", callback_data="force_download_listone"), InlineKeyboardButton("🔄 Sync Dati", callback_data="reload_excel"))
    markup.add(InlineKeyboardButton("⚠️ Reset Rosa", callback_data="reset_confirm"), InlineKeyboardButton("🧹 Pulisci Schermo", callback_data="clear_screen"))
    markup.add(InlineKeyboardButton("🔙 Indietro", callback_data="go_home"))
    return markup

def pro_menu_keyboard():
    """Il vecchio menu PRO e' confluito nello scouting: si evita il doppione."""
    return scouting_menu_keyboard()

# ==========================================
# HANDLERS: ACQUISTO E VALUTAZIONE
# ==========================================
def process_buy_price(message, player_name, user_id):
    chat_id = message.chat.id
    if not message.text.isdigit():
        msg = bot.send_message(chat_id, "❌ Inserisci <b>solo numeri</b>:", parse_mode="HTML")
        bot.register_next_step_handler(msg, process_buy_price, player_name, user_id)
        return

    costo = int(message.text)
    session = get_session(user_id)
    stats = get_roster_stats(session)
    
    if costo > stats['max_bid']:
        bot.send_message(chat_id, f"⚠️ <b>ALLARME!</b> Offerta oltre il <b>Max Bid</b> (<code>{stats['max_bid']}</code>).", parse_mode="HTML")
        return send_dashboard(chat_id, user_id) if not session.get('fase_asta') else send_asta_dashboard(chat_id, user_id)

    df = load_data()
    row = df[df['Nome'] == player_name].iloc[0]
    ruolo, squadra = row.get('R', 'C'), row.get('Squadra', '-')
    fvm_raw = pd.to_numeric(str(row.get('FVM', 0)).replace(',', '.').replace('-', '0'), errors='coerce')
    
    is_asta = session.get('fase_asta') is not None
    if is_asta:
        registro_asta = get_registro(session)
        registro_asta.segna(player_name, costo, str(ruolo), str(squadra), reg.IO)
        salva_registro(registro_asta, session)
        titolo_acquisto = f"✅ <b>{html.escape(player_name.upper())}</b> acquistato per <code>{costo} cr.</code>!"
    else:
        titolo_acquisto = f"🧪 <b>SIMULAZIONE: {html.escape(player_name.upper())} a {costo} cr.</b>\n<i>(Non salvato in Rosa)</i>"
    
    lega_bud, lega_part = session.get('lega_budget_iniziale', 500), session.get('lega_partecipanti', 8)
    fair_price_val = fair_price(row, session)
    
    if costo <= fair_price_val * 0.75: giudizio = f"🔥 <b>AFFARE D'ORO!</b> Hai risparmiato circa {fair_price_val - costo} cr."
    elif costo <= fair_price_val * 0.95: giudizio = f"✅ <b>OTTIMO COLPO!</b> Preso sotto costo (Fair Price: {fair_price_val} cr)."
    elif costo <= fair_price_val * 1.15: giudizio = f"⚖️ <b>PREZZO GIUSTO.</b> Pagato esattamente il suo valore."
    elif costo <= fair_price_val * 1.30: giudizio = f"⚠️ <b>LEGGERO OVERPAY.</b> Pagato un po' di più (Fair Price: {fair_price_val} cr)."
    else: giudizio = f"🚨 <b>SALASSO!</b> Strapagato! Hai speso ben {costo - fair_price_val} cr. in più."
        
    bot.send_message(chat_id, f"{titolo_acquisto}\n\n📊 <b>Valutazione Acquisto:</b>\n{giudizio}", parse_mode="HTML")
    
    if ruolo == 'P':
        riserve = df[(df['R'] == 'P') & (df['Squadra'] == squadra) & (df['Nome'] != player_name)].sort_values(by='FVM', ascending=False).head(2)
        r_nomi = [r['Nome'] for _, r in riserve.iterrows()]
        
        testo_p = f"🧤 <b>HAI PRESO UN PORTIERE! Completa il reparto:</b>\n\n"
        if r_nomi: testo_p += f"🔒 <b>Riserve {squadra}:</b> (da 1 cr): <code>{', '.join(r_nomi)}</code>\n\n"
        
        mk_port = InlineKeyboardMarkup(row_width=1)
        for r_n in r_nomi: mk_port.add(InlineKeyboardButton(f"⭐ Aggiungi {r_n} a Wishlist", callback_data=f"wl_add_{r_n}"))
        bot.send_message(chat_id, testo_p, parse_mode="HTML", reply_markup=mk_port if r_nomi else None)
            
    p_n = trova_partner_portiere(player_name, df)
    if p_n:
        mk_c = InlineKeyboardMarkup().add(InlineKeyboardButton(f"⭐ Aggiungi {p_n}", callback_data=f"wl_add_{p_n}"))
        bot.send_message(chat_id, f"🪂 <b>PARACADUTE ATTIVO</b>\nVuoi aggiungere {html.escape(p_n.upper())} alla WL?", parse_mode="HTML", reply_markup=mk_c)
            
    if is_asta: send_asta_dashboard(chat_id, user_id)
    else: send_dashboard(chat_id, user_id)

def process_whatif_price(message, player_name, user_id):
    chat_id = message.chat.id
    if not message.text.isdigit():
        msg = bot.send_message(chat_id, "❌ Inserisci un prezzo fittizio in <b>numeri</b>:", parse_mode="HTML")
        bot.register_next_step_handler(msg, process_whatif_price, player_name, user_id)
        return

    hyp_price, session, df = int(message.text), get_session(user_id), load_data()
    row = df[df['Nome'] == player_name].iloc[0]
    ruolo, fvm_raw = row.get('R', 'A'), pd.to_numeric(str(row.get('FVM', 0)).replace(',', '.').replace('-', '0'), errors='coerce')
    lega_bud, lega_part = session.get('lega_budget_iniziale', 500), session.get('lega_partecipanti', 8)
    f_part = 1 + ((lega_part - 8) * 0.025)
    fair_price_val = fair_price(row, session)

    budget_left, slots_left = session['budget'] - hyp_price, get_roster_stats(session)['slot_liberi'] - 1
    if slots_left < 0: return bot.send_message(chat_id, "❌ Hai già la rosa piena!", parse_mode="HTML")
        
    avg_left = budget_left / slots_left if slots_left > 0 else 0
    analisi = f"🔥 <b>PREZZO D'OCCASIONE!</b> Valore: <code>{fair_price_val}</code>" if hyp_price <= fair_price_val * 0.70 else f"✅ <b>CONGRUITA:</b> Linea con il Fair Price (<code>{fair_price_val}</code>)." if hyp_price <= fair_price_val * 1.15 else f"🚨 <b>OVERPAY RISCHIOSO:</b> +<code>{hyp_price - fair_price_val}</code> cr. del valore ideale."

    avail = get_available_players(df, session)
    target = avail[(avail['R'] == ruolo) & (avail['Nome'] != player_name)].copy()
    target['base_p'] = [fair_price(t, session) for _, t in target.iterrows()]
    compatibili = target[target['base_p'] <= avg_left].sort_values(by='FVM', ascending=False).head(3)
    txt_target = "\n".join([f"• {t['Nome']} ({t['Squadra']}) ─ Fair Price: ~{int(t['base_p'])} cr." for _, t in compatibili.iterrows()]) or "• Solo scommesse o tappabuchi a 1 credito."

    final_text = (f"🔮 <b>SIMULATORE WHAT-IF: {html.escape(player_name.upper())} a {hyp_price} cr.</b>\n━━━━━━━━━━━━━━━━━━━━━━\n{analisi}\n\n"
                  f"💼 <b>IMPATTO BUDGET:</b>\n• Residuo: <code>{budget_left} cr.</code>\n• Media ({slots_left} slot): <code>{avg_left:.1f} cr.</code>\n\n"
                  f"🎯 <b>CON QUESTA MEDIA POTRAI PUNTARE SU:</b>\n{txt_target}\n━━━━━━━━━━━━━━━━━━━━━━")
    markup = InlineKeyboardMarkup(row_width=2).add(InlineKeyboardButton("🔙 Indietro", callback_data=f"sq_pl_{player_name}"), InlineKeyboardButton("🏠 Home", callback_data="go_home"))
    bot.send_message(chat_id, final_text, parse_mode="HTML", reply_markup=markup)

# ==========================================
# MESSAGGI DI CHAT (Comandi, Vocali, Testo)
# ==========================================
@bot.message_handler(commands=['clean', 'pulisci'])
def cmd_clean(m):
    for i in range(m.message_id, max(0, m.message_id - 80), -1):
        try: bot.delete_message(m.chat.id, i)
        except Exception: pass
    session = get_session(m.from_user.id)
    send_asta_dashboard(m.chat.id, m.from_user.id) if session.get('fase_asta') else send_dashboard(m.chat.id, m.from_user.id)

@bot.message_handler(commands=['start', 'menu'])
def cmd_start(m): 
    try: bot.delete_message(m.chat.id, m.message_id)
    except Exception: pass
    session = get_session(m.from_user.id)
    send_asta_dashboard(m.chat.id, m.from_user.id) if session.get('fase_asta') else send_dashboard(m.chat.id, m.from_user.id)

@bot.message_handler(content_types=['voice'])
def handle_voice(message):
    if not VOICE_ENABLED: return bot.reply_to(message, "❌ <b>Comandi Vocali disattivati.</b>", parse_mode="HTML")
    bot.reply_to(message, "🎙️ Ascolto il vocale...")
    try:
        f_info = bot.get_file(message.voice.file_id)
        with open("voice.ogg", 'wb') as f: f.write(bot.download_file(f_info.file_path))
        AudioSegment.from_ogg("voice.ogg").export("voice.wav", format="wav")
        with sr.AudioFile("voice.wav") as source: testo = sr.Recognizer().recognize_google(sr.Recognizer().record(source), language="it-IT").lower()
        bot.send_message(message.chat.id, f"🗣️ Hai detto: <i>'{html.escape(testo)}'</i>", parse_mode="HTML")
        # I nomi con accenti o apostrofi (Ndicka, Perez, Dell'Orco) non passavano
        match = re.search(r"(?:preso|comprato|ho preso|aggiudicato)?\s*([^\d]+?)\s*(?:a|per)?\s*(\d+)",
                          testo, re.UNICODE)
        if match:
            n_voc, p_voc = match.group(1).strip(), int(match.group(2))
            df = load_data()
            matches = df[df['Nome'].astype(str).str.lower().str.contains(n_voc, na=False)]
            if not matches.empty:
                msg = bot.send_message(message.chat.id, f"🎯 Trovato: <b>{html.escape(matches.iloc[0]['Nome'])}</b>. Confermi a <code>{p_voc} cr.</code>?", parse_mode="HTML")
                bot.register_next_step_handler(msg, process_buy_price, matches.iloc[0]['Nome'], message.from_user.id)
            else: bot.send_message(message.chat.id, "❌ Giocatore non trovato.")
        else: bot.send_message(message.chat.id, "❌ Formato errato. Dì: 'Preso [Nome] a [Prezzo]'.")
    except Exception: bot.reply_to(message, "❌ Errore traduzione vocale.")

@bot.message_handler(func=lambda m: m.text.strip().startswith('+'))
def modalita_cecchino(message):
    try:
        parts = message.text.strip()[1:].strip().rsplit(' ', 1)
        if len(parts) != 2 or not parts[1].isdigit(): return bot.reply_to(message, "❌ Usa: <code>+ nome prezzo</code>", parse_mode="HTML")
        q_nome, costo = parts[0].strip().lower(), int(parts[1])
        df, session = load_data(), get_session(message.from_user.id)
        matches = df[df['Nome'].astype(str).str.lower().str.contains(q_nome, na=False)]
        if matches.empty: return bot.reply_to(message, f"❌ Nessun giocatore trovato per '{html.escape(q_nome)}'.", parse_mode="HTML")
        
        row, p_name = matches.iloc[0], matches.iloc[0]['Nome']
        if costo > get_roster_stats(session)['max_bid']: return bot.reply_to(message, f"⚠️ <b>ALLARME!</b> Max Bid: <code>{get_roster_stats(session)['max_bid']}</code>.", parse_mode="HTML")
        
        is_asta = session.get('fase_asta') is not None
        if is_asta:
            session['rosa'].append({'nome': p_name, 'prezzo': costo, 'ruolo': row.get('R', 'C'), 'squadra': row.get('Squadra', '-'), 'fvm': pd.to_numeric(str(row.get('FVM', 0)).replace(',', '.').replace('-', '0'), errors='coerce')})
            session['budget'] -= costo
            titolo = f"🎯 <b>CECCHINO A BERSAGLIO!</b>\n✅ Acquistato <b>{html.escape(p_name.upper())}</b> a <code>{costo} cr.</code>"
        else: titolo = f"🧪 <b>SIMULAZIONE CECCHINO: {html.escape(p_name.upper())} a {costo} cr.</b>\n<i>(Non salvato)</i>"
        
        fvm_clean = str(row.get('FVM', 0)).replace(',', '.')
        fvm_val = pd.to_numeric(fvm_clean, errors='coerce') or 0
        fair_price_val = fair_price(row, session)
        giudizio = f"🔥 <b>AFFARE!</b>" if costo <= fair_price_val * 0.75 else f"✅ <b>OTTIMO!</b>" if costo <= fair_price_val * 0.95 else f"⚖️ <b>GIUSTO.</b>" if costo <= fair_price_val * 1.15 else f"🚨 <b>SALASSO!</b>"
        
        bot.reply_to(message, f"{titolo}\n\n📊 <b>Valutazione:</b>\n{giudizio}", parse_mode="HTML")
        send_asta_dashboard(message.chat.id, message.from_user.id) if is_asta else send_dashboard(message.chat.id, message.from_user.id)
    except Exception: bot.reply_to(message, "❌ Errore acquisto rapido.")

@bot.message_handler(func=lambda m: m.text and not m.text.startswith('/'))
def testo_libero(message):
    """
    Una riga di testo puo' voler dire due cose: "segna questo acquisto" oppure
    "cercami questo giocatore". Le si distingue dal prezzo.

        dimarco 90       -> venduto agli altri a 90
        dimarco 90 io    -> l'ho preso io a 90
        dimarco          -> cercalo

    Il marcatore sta solo sul MIO acquisto perche' in una lega da 8 squadre
    nove vendite su dieci non sono mie: il caso frequente non deve costare
    neanche un carattere.
    """
    testo = (message.text or "").strip()
    df, session = load_data(), get_session(message.from_user.id)
    if df is None or len(testo) < 2:
        return

    nome, prezzo, acquirente = reg.interpreta(testo)
    if nome and prezzo is not None:
        return segna_vendita(message, nome, prezzo, acquirente, df, session)

    matches = df[df['Nome'].astype(str).str.lower().str.contains(testo.lower(), na=False)]
    if matches.empty:
        return bot.reply_to(message, "❌ Nessun giocatore trovato.")
    if len(matches) == 1:
        return send_player_card_view(message.chat.id, matches.iloc[0]['Nome'], None, df, session)

    markup = InlineKeyboardMarkup(row_width=1)
    for _, row in matches.head(10).iterrows():
        markup.add(InlineKeyboardButton(
            f"{ROLE_ICONS.get(str(row.get('R','C')),'')} {row['Nome']} ({row.get('Squadra','-')})",
            callback_data=f"sq_pl_{row['Nome']}"))
    bot.reply_to(message, f"🔍 Scegli il giocatore esatto per <b>{html.escape(testo)}</b>:",
                 parse_mode="HTML", reply_markup=markup)


def segna_vendita(message, nome, prezzo, acquirente, df, session):
    """Scrive nel taccuino e risponde con una riga sola piu' il tasto annulla."""
    riga = dati.cerca_giocatore(nome, df)
    if riga is None:
        return bot.reply_to(message, f"❌ <b>{html.escape(nome)}</b> non e' nel listone.",
                            parse_mode="HTML")

    nome_vero = str(riga['Nome'])
    registro_asta = get_registro(session)
    mio = acquirente == reg.IO

    if mio:
        stato = dati.stato_rosa(session)
        if prezzo > stato['max_bid']:
            return bot.reply_to(
                message,
                f"⚠️ <b>{prezzo} cr</b> supera la tua offerta massima "
                f"(<b>{stato['max_bid']}</b>): con {stato['slot_liberi']} slot da "
                f"riempire non ti resterebbe un credito a casella.",
                parse_mode="HTML")

    registro_asta.segna(nome_vero, prezzo, str(riga.get('R', 'C')),
                        str(riga.get('Squadra', '')), reg.IO if mio else "altri")
    salva_registro(registro_asta, session)

    destinazione = "🟢 <b>preso da te</b>" if mio else "⚪ agli altri"
    listino = int(_num(riga.get('Prezzo'), 1))
    confronto = ""
    if listino >= 5 and prezzo:
        scarto = round((prezzo / listino - 1) * 100)
        if abs(scarto) >= 15:
            confronto = f"  ·  {scarto:+d}% sul listino ({listino})"

    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("↩︎ Annulla", callback_data="reg_annulla"),
               InlineKeyboardButton("🔨 Piano", callback_data="menu_panic_start"))
    bot.reply_to(message,
                 f"✓ <b>{html.escape(nome_vero)}</b> {prezzo} cr → {destinazione}{confronto}\n"
                 f"💰 cassa <b>{session['budget']}</b>  ·  "
                 f"{dati.stato_rosa(session)['slot_liberi']} slot da fare",
                 parse_mode="HTML", reply_markup=markup)


@bot.message_handler(content_types=['document'])
def handle_document(message):
    fname = message.document.file_name.lower()
    if not fname.endswith(('.csv', '.xlsx', '.xls')):
        return bot.reply_to(message, "❌ Invia solo file <code>.csv</code> o <code>.xlsx</code>!", parse_mode="HTML")

    temporaneo = "upload_temp" + os.path.splitext(fname)[1]
    try:
        with open(temporaneo, 'wb') as f:
            f.write(bot.download_file(bot.get_file(message.document.file_id).file_path))

        # Un .xlsx va convertito, non rinominato: salvarlo come .csv rompeva il bot.
        # I file di Fantacalcio hanno una riga di titolo prima delle intestazioni:
        # si prova header=0 e, se le colonne non tornano, header=1.
        if fname.endswith(('.xlsx', '.xls')):
            nuovo = pd.read_excel(temporaneo)
            if 'Nome' not in nuovo.columns:
                nuovo = pd.read_excel(temporaneo, header=1)
        else:
            try:
                nuovo = pd.read_csv(temporaneo, sep=';', on_bad_lines='skip')
            except Exception:
                nuovo = pd.read_csv(temporaneo, sep=',', on_bad_lines='skip')

        # Il listone delle quotazioni NON e' il Master: non ha FVM, Prezzo,
        # infortuni e foto. Accettarlo qui significava buttare via meta' dei dati
        # fino al download successivo. Le quotazioni vanno nel repo del motore.
        if 'Prezzo' not in nuovo.columns and 'FVM' not in nuovo.columns:
            return bot.reply_to(
                message,
                "❌ <b>Questo sembra il listone quotazioni</b>, non il Master.\n"
                "Caricarlo qui cancellerebbe FVM, prezzi e infortuni.\n\n"
                "Mettilo invece nel repository <code>fanta-master-ai</code>: "
                "il motore lo userà al prossimo giro notturno e il bot scaricherà "
                "il Master aggiornato da solo.", parse_mode="HTML")

        ok, mancanti = dati.salva_da_dataframe(nuovo)
        if not ok:
            return bot.reply_to(
                message,
                f"❌ <b>File non valido</b>: mancano {', '.join(mancanti)}.\n"
                f"Il listone precedente NON è stato toccato.", parse_mode="HTML")

        avviso = "" if 'Prezzo' in nuovo.columns else "\n⚠️ <i>Manca la colonna Prezzo: i valori saranno stimati.</i>"
        bot.reply_to(message, f"✅ <b>LISTONE AGGIORNATO</b>: {len(nuovo)} giocatori.{avviso}", parse_mode="HTML")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Errore caricamento: {str(e)}")
    finally:
        if os.path.exists(temporaneo):
            try:
                os.remove(temporaneo)
            except Exception:
                pass


# ==========================================
# GESTIONE CALLBACKS (Bottoni Inline)
# ==========================================
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    safe_answer_callback(call.id)
    user_id, chat_id = call.from_user.id, call.message.chat.id
    session, df = get_session(user_id), load_data()

    # Le schermate-elenco diventano il punto di ritorno della card giocatore:
    # cosi' "Indietro" riporta alla lista giusta invece che alla Home.
    if (call.data.startswith(("sq_ru_", "rig_sq_", "menu_top_ru_", "menu_gemme_ru_",
                              "menu_modificatore"))
            or call.data in ("pro_spiccioli", "pro_stakanov", "pro_griglia",
                             "menu_wishlist", "menu_rosa", "menu_rigoristi",
                             "sq_start", "menu_power")):
        session['ritorno'] = call.data
    elif call.data == "go_home":
        session['ritorno'] = None

    if call.data == "clear_screen":
        for i in range(call.message.message_id, max(0, call.message.message_id - 80), -1):
            try: bot.delete_message(chat_id, i)
            except Exception: pass
        send_asta_dashboard(chat_id, user_id) if session.get('fase_asta') else send_dashboard(chat_id, user_id)

    elif call.data == "go_home": 
        session['compare_p1'] = None
        for i in range(call.message.message_id, max(0, call.message.message_id - 10), -1):
            try: bot.delete_message(chat_id, i)
            except Exception: pass
        send_dashboard(chat_id, user_id)
        
    elif call.data == "asta_setup_start":
        markup = InlineKeyboardMarkup(row_width=3)
        markup.add(InlineKeyboardButton("6", callback_data="astap_6"), InlineKeyboardButton("8", callback_data="astap_8"), InlineKeyboardButton("10", callback_data="astap_10"), InlineKeyboardButton("12", callback_data="astap_12"))
        bot.edit_message_text("🔨 <b>SETUP ASTA</b>\nQuanti partecipanti ci sono nella lega?", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif call.data.startswith("astap_"):
        session['lega_partecipanti'] = int(call.data.split("_")[1])
        markup = InlineKeyboardMarkup(row_width=3).add(InlineKeyboardButton("300", callback_data="astab_300"), InlineKeyboardButton("500", callback_data="astab_500"), InlineKeyboardButton("1000", callback_data="astab_1000"))
        bot.edit_message_text("💰 Qual è il budget iniziale?", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif call.data.startswith("astab_"):
        session['lega_budget_iniziale'] = session['budget'] = int(call.data.split("_")[1])
        markup = InlineKeyboardMarkup(row_width=2).add(InlineKeyboardButton("✅ SÌ (Voti alti)", callback_data="astam_si"), InlineKeyboardButton("❌ NO (Classic)", callback_data="astam_no"))
        bot.edit_message_text("🛡️ Utilizzate il <b>Modificatore Difesa</b>?", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif call.data.startswith("astam_"):
        session['modificatore_attivo'], session['fase_asta'], session['rosa'] = (call.data == "astam_si"), 'P', []
        send_asta_dashboard(chat_id, user_id, call.message.message_id)

    elif call.data.startswith("asta_fase_"):
        session['fase_asta'] = call.data.split("_")[2]
        send_asta_dashboard(chat_id, user_id, call.message.message_id)
        
    elif call.data == "asta_resume": send_asta_dashboard(chat_id, user_id, call.message.message_id)
    elif call.data == "asta_end":
        session['fase_asta'] = None
        safe_answer_callback(call.id, "Asta terminata! Rosa confermata.", show_alert=True)
        send_dashboard(chat_id, user_id, call.message.message_id)

    elif call.data == "force_download_listone":
        msg = bot.send_message(chat_id, "⏳ <i>Collegamento ai server ufficiali per il download...</i>", parse_mode="HTML")
        bot.edit_message_text("✅ <b>LISTONE AGGIORNATO CON SUCCESSO!</b>" if auto_download_listone() else "❌ <b>Download fallito.</b>", chat_id, msg.message_id, parse_mode="HTML")

    elif call.data == "menu_impostazioni_lega":
        markup = InlineKeyboardMarkup(row_width=3)
        markup.row(InlineKeyboardButton("💰 Bud: 300", callback_data="imposta_bud_300"), InlineKeyboardButton("💰 500", callback_data="imposta_bud_500"), InlineKeyboardButton("💰 1000", callback_data="imposta_bud_1000"))
        markup.row(InlineKeyboardButton("👥 Lega: 8", callback_data="imposta_part_8"), InlineKeyboardButton("👥 a 10", callback_data="imposta_part_10"), InlineKeyboardButton("👥 a 12", callback_data="imposta_part_12"))
        markup.add(InlineKeyboardButton("🔄 Reset (500 cr - 8 sq)", callback_data="imposta_reset"), InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text(f"⚙️ <b>IMPOSTAZIONI</b>\n💰 Budget: <code>{session.get('lega_budget_iniziale', 500)} cr.</code>\n👥 Partecipanti: <code>{session.get('lega_partecipanti', 8)} squadre</code>", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif call.data.startswith("imposta_bud_"):
        # Si sposta il tetto, non la cassa: se hai gia' comprato, quello che hai
        # speso resta speso. Prima cambiare budget a meta' asta te lo azzerava.
        nuovo_budget = int(call.data.replace("imposta_bud_", ""))
        speso = session.get('lega_budget_iniziale', 500) - session.get('budget', 500)
        session['lega_budget_iniziale'] = nuovo_budget
        session['budget'] = max(0, nuovo_budget - speso)
        safe_answer_callback(call.id, f"✅ Budget: {nuovo_budget} cr (cassa {session['budget']})!", True)
        call.data = "menu_impostazioni_lega"
        handle_callbacks(call)

    elif call.data.startswith("imposta_part_"):
        session['lega_partecipanti'] = int(call.data.replace("imposta_part_", ""))
        safe_answer_callback(call.id, f"✅ Partecipanti: {session['lega_partecipanti']}!", True)
        call.data = "menu_impostazioni_lega"
        handle_callbacks(call)

    elif call.data == "imposta_reset":
        session['lega_budget_iniziale'], session['lega_partecipanti'], session['budget'] = 500, 8, 500
        safe_answer_callback(call.id, "✅ Lega resettata!", True)
        call.data = "menu_impostazioni_lega"
        handle_callbacks(call)

    elif call.data == "menu_formazione":
        t, img = calcola_formazione_ideale(session, df)
        markup = InlineKeyboardMarkup().add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.send_photo(chat_id, img, caption=t, parse_mode="HTML", reply_markup=markup) if img else bot.send_message(chat_id, t, parse_mode="HTML", reply_markup=markup)

    elif call.data == "menu_rigoristi":
        gerarchie = gerarchie_rigoristi(df)
        if not gerarchie:
            bot.edit_message_text("🎯 <b>RADAR RIGORISTI</b>\n\n⚠️ Il Master non contiene la colonna <code>Rc</code>: aggiorna il listone.",
                                  chat_id, call.message.message_id, parse_mode="HTML",
                                  reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🏠 Home", callback_data="go_home")))
        else:
            markup = InlineKeyboardMarkup(row_width=2)
            for sq in sorted(gerarchie):
                markup.add(InlineKeyboardButton(f"{get_team_icon(sq)} {sq}", callback_data=f"rig_sq_{sq}"))
            markup.add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
            bot.edit_message_text("🎯 <b>RADAR RIGORISTI</b>\n<i>Rigori calciati nella scorsa stagione. Scegli la squadra:</i>",
                                  chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif call.data.startswith("rig_sq_"):
        squadra = call.data.replace("rig_sq_", "")
        dati = gerarchie_rigoristi(df, squadra).get(squadra, {})
        markup = InlineKeyboardMarkup(row_width=1)
        for voce in dati.get('rigoristi', []):
            nome = voce.rsplit(" (", 1)[0]
            markup.add(InlineKeyboardButton(f"⚽ {voce}", callback_data=f"sq_pl_{nome}"))
        markup.add(InlineKeyboardButton("🔙 Squadre", callback_data="menu_rigoristi"),
                   InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text(f"🎯 <b>{get_team_icon(squadra)} {squadra}</b>\n<i>Fra parentesi i rigori calciati. Tocca per la card:</i>",
                              chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif call.data == "menu_power":
        baseline = analisi.baseline_ruoli(df)
        hot, freddi = [], []
        for p in session.get('rosa', []):
            row = get_player_stats(p['nome'], df)
            if row is None:
                continue
            prof = analisi.profilo(row, None, baseline)
            riferimento = baseline.get(prof['ruolo'], (6.0, 0.3))[0]
            scarto = prof['fantamedia_ponderata'] - riferimento
            voce = f"{ROLE_ICONS.get(prof['ruolo'], '')} {prof['nome']}: {prof['fantamedia']:.2f} ({scarto:+.2f} sul ruolo)"
            (hot if scarto >= 0.15 else freddi).append((scarto, voce))
        hot.sort(reverse=True); freddi.sort(reverse=True)
        testo = "⚡ <b>POWER RANKING ROSA</b>\n<i>Confronto con la media del proprio ruolo</i>\n━━━━━━━━━━━━━━━━━━━━\n"
        testo += ("<b>Sopra la media:</b>\n" + "\n".join(v for _, v in hot) + "\n\n") if hot else ""
        testo += ("<b>Sotto la media:</b>\n" + "\n".join(v for _, v in freddi)) if freddi else ""
        if not hot and not freddi:
            testo = "⚡ <b>POWER RANKING</b>\n\nRosa vuota: compra qualcuno e torna qui."
        bot.edit_message_text(testo, chat_id, call.message.message_id, parse_mode="HTML",
                              reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🏠 Home", callback_data="go_home")))

    elif call.data == "menu_sistema": bot.edit_message_text("⚙️ <b>SISTEMA</b>", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=system_menu_keyboard())
    elif call.data == "reload_excel": 
        load_data(force_reload=True)
        bot.send_message(chat_id, "⚡ <b>Dati dal Master sincronizzati!</b>", parse_mode="HTML")
    elif call.data == "reset_confirm":
        user_sessions[user_id] = {'budget': session.get('lega_budget_iniziale', 500), 'rosa': [], 'wishlist': session.get('wishlist', []), 'scartati': [], 'compare_p1': None, 'lega_budget_iniziale': session.get('lega_budget_iniziale', 500), 'lega_partecipanti': session.get('lega_partecipanti', 8), 'modificatore_attivo': session.get('modificatore_attivo', False), 'fase_asta': None}
        send_dashboard(chat_id, user_id, call.message.message_id)

    elif call.data == "menu_scouting":
        bot.edit_message_text(
            "🔎 <b>SCOUTING</b>\n<i>Trova i giocatori giusti per il tuo budget</i>",
            chat_id, call.message.message_id, parse_mode="HTML",
            reply_markup=scouting_menu_keyboard())

    elif call.data == "menu_pro": bot.edit_message_text("🛠️ <b>STRUMENTI PRO</b>", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=pro_menu_keyboard())
    elif call.data == "pro_stakanov":
        lst = analisi.stakanovisti(get_available_players(df, session), limite=10)
        markup = InlineKeyboardMarkup(row_width=1)
        if lst is not None and not lst.empty:
            for _, r in lst.iterrows():
                markup.add(InlineKeyboardButton(
                    f"🧱 {r['Nome']} ({r['Squadra']}) · {int(_num(r.get('Pv')))} pres · {int(_num(r.get('Prezzo'), 1))} cr",
                    callback_data=f"sq_pl_{r['Nome']}"))
        markup.add(InlineKeyboardButton("🔙 Menu PRO", callback_data="menu_pro"))
        bot.edit_message_text("🧱 <b>STAKANOVISTI</b>\n<i>Chi non salta una partita: ordinati per presenze</i>",
                              chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif call.data == "pro_griglia":
        avail = get_available_players(df, session)
        griglia = analisi.griglia_difensiva(avail)
        classifica = analisi.classifica_difensiva(avail)[:6]
        markup = InlineKeyboardMarkup(row_width=1)
        if griglia is not None and not griglia.empty:
            for _, r in griglia.head(10).iterrows():
                markup.add(InlineKeyboardButton(
                    f"🛡️ {r['Nome']} ({r['Squadra']}) · Fm {_num(r.get('Fm')):.2f} · {int(_num(r.get('Prezzo'), 1))} cr",
                    callback_data=f"sq_pl_{r['Nome']}"))
        markup.add(InlineKeyboardButton("🔙 Menu PRO", callback_data="menu_pro"))
        elenco = ", ".join(f"{sq} ({d['gol_subiti_partita']})" for sq, d in classifica)
        bot.edit_message_text(
            f"🛡️ <b>GRIGLIA DIFENSIVA</b>\n<i>Difensori piu' impiegati delle squadre meno battute</i>\n\n"
            f"<b>Gol subiti a partita:</b> {elenco}",
            chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif call.data == "pro_spiccioli":
        low = analisi.migliori_per_resa(get_available_players(df, session), limite=10, prezzo_massimo=10)
        markup = InlineKeyboardMarkup(row_width=1)
        if low is not None and not low.empty:
            for _, r in low.iterrows():
                markup.add(InlineKeyboardButton(
                    f"🎰 {r['Nome']} ({r['R']} - {r['Squadra']}) · {int(_num(r.get('Prezzo'), 1))} cr",
                    callback_data=f"sq_pl_{r['Nome']}"))
        markup.add(InlineKeyboardButton("🔙 Menu PRO", callback_data="menu_pro"))
        bot.edit_message_text("🎰 <b>TAPPABUCHI LOW-COST</b>\n<i>Ordinati per resa per credito speso</i>",
                              chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif call.data.startswith("stats_"):
        p = call.data.replace("stats_", "")
        tastiera = InlineKeyboardMarkup(row_width=2).add(
            InlineKeyboardButton("🔙 Scheda", callback_data=f"sq_pl_{p}"),
            InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        if session.get('ritorno'):
            tastiera.add(InlineKeyboardButton("↩️ Torna alla lista", callback_data=session['ritorno']))
        bot.edit_message_text(get_storico(p, df), chat_id, call.message.message_id, parse_mode="HTML", reply_markup=tastiera)

    elif call.data.startswith("wi_"): bot.register_next_step_handler(bot.send_message(chat_id, f"🔮 <b>SIMULATORE WHAT-IF</b> per <b>{html.escape(call.data.replace('wi_', ''))}</b>:", parse_mode="HTML"), process_whatif_price, call.data.replace("wi_", ""), user_id)

    elif call.data.startswith("sd_"):
        p, avail = call.data.replace("sd_", ""), get_available_players(df, session)
        cloni = avail[(avail['R'] == df[df['Nome'] == p].iloc[0]['R']) & (avail['Nome'] != p)].copy()
        cloni['d'] = abs(cloni['FVM'] - float(df[df['Nome'] == p].iloc[0].get('FVM', 0)))
        markup = InlineKeyboardMarkup(row_width=1)
        for _, c in cloni.sort_values(by=['d', 'FVM'], ascending=[True, False]).head(4).iterrows(): markup.add(InlineKeyboardButton(f"🔄 {c['Nome']} ({c['Squadra']})", callback_data=f"sq_pl_{c['Nome']}"))
        markup.add(InlineKeyboardButton("🔙 Indietro", callback_data=f"sq_pl_{p}"))
        bot.send_message(chat_id, f"🔄 <b>SLIDING DOORS per {html.escape(p)}:</b>", parse_mode="HTML", reply_markup=markup)

    elif call.data.startswith("wl_add_"):
        if call.data.replace("wl_add_", "") not in session['wishlist']: session['wishlist'].append(call.data.replace("wl_add_", ""))
        safe_answer_callback(call.id, f"✅ {call.data.replace('wl_add_', '')} in Wishlist!", True)
        send_asta_dashboard(chat_id, user_id, call.message.message_id) if session.get('fase_asta') else send_dashboard(chat_id, user_id, call.message.message_id)

    elif call.data.startswith("menu_modificatore"):
        p = int(call.data.split("_page_")[1]) if "_page_" in call.data else 1
        mods = analisi.candidati_modificatore(get_available_players(df, session), limite=45)
        markup, nav = InlineKeyboardMarkup(row_width=1), []
        if mods is not None and not mods.empty:
            for _, r in mods.iloc[(p - 1) * 15:p * 15].iterrows():
                markup.add(InlineKeyboardButton(
                    f"🛡️ {r['Nome']} ({r['Squadra']}) · MV {_num(r.get('Mv')):.2f} · {int(_num(r.get('Pv')))} pres",
                    callback_data=f"sq_pl_{r['Nome']}"))
            if p > 1:
                nav.append(InlineKeyboardButton("◀️ Precedenti", callback_data=f"menu_modificatore_page_{p - 1}"))
            if len(mods) > p * 15:
                nav.append(InlineKeyboardButton("➕ Altri", callback_data=f"menu_modificatore_page_{p + 1}"))
        if nav: markup.row(*nav)
        markup.add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text(
            f"🛡️ <b>MODIFICATORE 6.5</b> (Pag. {p})\n"
            f"<i>Conta il voto puro, non la fantamedia: ordinati per MV ponderata e solidita' della difesa</i>",
            chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif call.data == "menu_rosa":
        r = "\n".join([f"<b>{ROLE_ICONS[ru]} {ru}:</b>\n" + "".join([f"• {html.escape(p['nome'])} (<code>{p['prezzo']} cr.</code>)\n" for p in session.get('rosa', []) if p.get('ruolo') == ru]) for ru in ['P', 'D', 'C', 'A'] if any(p.get('ruolo') == ru for p in session.get('rosa', []))])
        bot.edit_message_text(f"📋 <b>LA TUA ROSA:</b>\n───────────────────────────\n{r}" if r else "📋 <b>ROSA VUOTA!</b>", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🏠 Home", callback_data="go_home")))

    elif call.data == "sq_start":
        markup = InlineKeyboardMarkup(row_width=2).add(*[InlineKeyboardButton(f"{get_team_icon(s)} {s}", callback_data=f"sq_sq_{s}") for s in sorted(df['Squadra'].dropna().astype(str).unique())]).add(InlineKeyboardButton("🔙 Home", callback_data="go_home"))
        bot.edit_message_text("👕 <b>ESPLORA SQUADRE</b>", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif call.data.startswith("sq_sq_"): bot.edit_message_text("Scegli ruolo:", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(row_width=4).add(*[InlineKeyboardButton(f"{ROLE_ICONS[r]} {r}", callback_data=f"sq_ru_{call.data.replace('sq_sq_', '')}_{r}") for r in ['P', 'D', 'C', 'A']]).add(InlineKeyboardButton("🔙 Squadre", callback_data="sq_start")))
    elif call.data.startswith("sq_ru_"):
        sq, ru = call.data.split("_")[2], call.data.split("_")[3]
        markup = InlineKeyboardMarkup(row_width=1).add(*[InlineKeyboardButton(f"{'⭐ ' if r['Nome'] in session.get('wishlist', []) else ''}{ROLE_ICONS.get(ru,'')} {r['Nome']} ─ {fair_price(r, session)} cr", callback_data=f"sq_pl_{r['Nome']}") for _, r in df[(df['Squadra'] == sq) & (df['R'] == ru)].iterrows()]).add(InlineKeyboardButton("🔙 Cambia Ruolo", callback_data=f"sq_sq_{sq}"),
             InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text(f"Giocatori ({sq} - {ru}):", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif call.data == "menu_panic_start":
        mostra_panic(chat_id, call.message.message_id, df, session)

    elif call.data.startswith("panic_ru_"):
        mostra_panic(chat_id, call.message.message_id, df, session,
                     ruolo_forzato=call.data.split("_")[-1])

    elif call.data == "menu_top_start" or call.data == "menu_gemme_start":
        pfx = call.data.split("_")[1]
        t = {"top": "👑 TOP LIBERI", "gemme": "🔧 4ª/5ª FASCIA"}[pfx]
        bot.edit_message_text(f"{t} - Scegli ruolo:", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(row_width=4).add(*[InlineKeyboardButton(f"{ROLE_ICONS[r]} {r}", callback_data=f"menu_{pfx}_ru_{r}") for r in ['P', 'D', 'C', 'A']]).add(InlineKeyboardButton("🔙 Scouting", callback_data="menu_scouting"),
     InlineKeyboardButton("🏠 Home", callback_data="go_home")))

    elif call.data.startswith("menu_top_ru_") or call.data.startswith("menu_gemme_ru_"):
        pfx, raw = call.data.split("_")[1], call.data.split("_ru_")[1]
        r, p = (raw.split("_page_")[0], int(raw.split("_page_")[1])) if "_page_" in raw else (raw, 1)
        avail = get_available_players(df, session)
        # La fascia si calcola SEMPRE sul listone intero, altrimenti lo stesso
        # giocatore risulta TOP nella sua card e di un'altra fascia nell'elenco,
        # perche' i compagni gia' comprati sparivano dalla classifica di ruolo.
        # Chi e' gia' stato preso lo si toglie dopo, solo dalla visualizzazione.
        mappa_fasce = {'gemme': 'quarta', 'top': 'top'}
        lst = analisi.fascia(df, r, mappa_fasce.get(pfx, 'top'),
                             session.get('lega_partecipanti', 8))
        if lst is not None and not lst.empty:
            lst = lst[lst['Nome'].isin(avail['Nome'])]
        if lst is None or lst.empty:
            lst = avail[avail['R'] == r].sort_values(by='FVM', ascending=False)
        
        markup, nav = InlineKeyboardMarkup(row_width=1), []
        for _, row in lst.iloc[(p-1)*15:p*15].iterrows(): markup.add(InlineKeyboardButton(f"🔍 {row['Nome']} ({row.get('Squadra','-')}) · {int(_num(row.get('Prezzo'), 1))} cr", callback_data=f"sq_pl_{row['Nome']}"))
        if p > 1: nav.append(InlineKeyboardButton("◀️", callback_data=f"menu_{pfx}_ru_{r}_page_{p - 1}"))
        if len(lst) > p*15: nav.append(InlineKeyboardButton("➕", callback_data=f"menu_{pfx}_ru_{r}_page_{p + 1}"))
        if nav: markup.row(*nav)
        markup.add(InlineKeyboardButton("🔙 Cambia Ruolo", callback_data=f"menu_{pfx}_start"), InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text(f"{pfx.upper()} - {ROLE_ICONS[r]} {r} (Pag. {p}):", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif call.data == "menu_scommessa_start":
        avail = get_available_players(df, session)
        sl = analisi.scommesse(avail, squadre=session.get('lega_partecipanti', 8))
        send_player_card_view(chat_id, sl.sample(1).iloc[0]['Nome'], call.message.message_id, df, session, True) if sl is not None and not sl.empty else safe_answer_callback(call.id, "Nessuna scommessa!", True)

    elif call.data == "menu_studio_start":
        session['compare_p1'] = None
        bot.edit_message_text("📊 <b>STUDIO 3D</b>\nSquadra TUO giocatore:", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(row_width=2).add(*[InlineKeyboardButton(f"{get_team_icon(s)} {s}", callback_data=f"std1_sq_{s}") for s in sorted(df['Squadra'].dropna().astype(str).unique())]).add(InlineKeyboardButton("🔙 Home", callback_data="go_home")))

    elif call.data.startswith("std1_sq_"): bot.edit_message_text("Scegli ruolo:", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(row_width=4).add(*[InlineKeyboardButton(f"{ROLE_ICONS[r]} {r}", callback_data=f"std1_ru_{call.data.replace('std1_sq_', '')}_{r}") for r in ['P', 'D', 'C', 'A']]).add(InlineKeyboardButton("🔙 Indietro", callback_data="menu_studio_start"),
     InlineKeyboardButton("🏠 Home", callback_data="go_home")))
    elif call.data.startswith("std1_ru_"): bot.edit_message_text("Seleziona:", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(row_width=1).add(*[InlineKeyboardButton(f"{r['Nome']}", callback_data=f"std1_pl_{r['Nome']}") for _, r in df[(df['Squadra'] == call.data.split('_')[2]) & (df['R'] == call.data.split('_')[3])].iterrows()]).add(InlineKeyboardButton("🔙", callback_data=f"std1_sq_{call.data.split('_')[2]}")))
    elif call.data.startswith("std1_pl_"):
        session['compare_p1'] = df[df['Nome'] == call.data.replace("std1_pl_", "")].iloc[0].to_dict()
        bot.edit_message_text(f"📊 <b>Hai scelto {html.escape(session['compare_p1']['Nome'].upper())}</b>\nSquadra PROPOSTO:", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(row_width=2).add(*[InlineKeyboardButton(f"{get_team_icon(s)} {s}", callback_data=f"std2_sq_{s}") for s in sorted(df['Squadra'].dropna().astype(str).unique())]).add(InlineKeyboardButton("🔙 Ricomincia", callback_data="menu_studio_start"),
     InlineKeyboardButton("🏠 Home", callback_data="go_home")))
    elif call.data.startswith("std2_sq_"): bot.edit_message_text("Scegli:", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(row_width=1).add(*[InlineKeyboardButton(f"🆚 {r['Nome']}", callback_data=f"std2_pl_{r['Nome']}") for _, r in df[(df['Squadra'] == call.data.replace("std2_sq_", "")) & (df['R'] == session['compare_p1']['R']) & (df['Nome'] != session['compare_p1']['Nome'])].iterrows()]).add(InlineKeyboardButton("🔙", callback_data=f"std1_pl_{session['compare_p1']['Nome']}")))
    elif call.data.startswith("std2_pl_"): bot.edit_message_text(advanced_trade_analyzer_3d(session['compare_p1'], df[df['Nome'] == call.data.replace("std2_pl_", "")].iloc[0].to_dict(), session, df), chat_id, call.message.message_id, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(row_width=2).add(InlineKeyboardButton(f"⚡ Compra {session['compare_p1']['Nome']}", callback_data=f"buy_{session['compare_p1']['Nome']}"), InlineKeyboardButton(f"⚡ Compra {call.data.replace('std2_pl_', '')}", callback_data=f"buy_{call.data.replace('std2_pl_', '')}")).add(InlineKeyboardButton("🔄 Nuovo", callback_data="menu_studio_start"), InlineKeyboardButton("🏠 Home", callback_data="go_home")))

    elif call.data.startswith("sq_pl_"): send_player_card_view(chat_id, call.data.replace("sq_pl_", ""), call.message.message_id, df, session)
    elif call.data.startswith("buy_"): bot.register_next_step_handler(bot.send_message(chat_id, f"💰 Crediti spesi per <b>{html.escape(call.data.replace('buy_', ''))}</b>?:", parse_mode="HTML"), process_buy_price, call.data.replace("buy_", ""), user_id)
    
    elif call.data.startswith("taken_"):
        # Passa dal registro: cosi' esiste una sola fonte di verita' e
        # l'annulla funziona anche su quello che segni coi pulsanti.
        nome_venduto = call.data.replace("taken_", "")
        riga_venduta = get_player_stats(nome_venduto, df)
        registro_asta = get_registro(session)
        registro_asta.segna(nome_venduto, 0,
                            str(riga_venduta.get('R', 'C')) if riga_venduta is not None else 'C',
                            str(riga_venduta.get('Squadra', '')) if riga_venduta is not None else '',
                            "altri")
        salva_registro(registro_asta, session)
        safe_answer_callback(call.id, text="🚫 Segnato: preso dagli altri", show_alert=False)
        send_asta_dashboard(chat_id, user_id, call.message.message_id) if session.get('fase_asta') else send_dashboard(chat_id, user_id, call.message.message_id)

    elif call.data.startswith("wl_toggle_"):
        if call.data.replace("wl_toggle_", "") in session.get('wishlist', []): session['wishlist'].remove(call.data.replace("wl_toggle_", ""))
        else: session.setdefault('wishlist', []).append(call.data.replace("wl_toggle_", ""))
        send_player_card_view(chat_id, call.data.replace("wl_toggle_", ""), call.message.message_id, df, session)

    elif call.data == "reg_annulla":
        registro_asta = get_registro(session)
        tolta = registro_asta.annulla_ultima()
        if tolta is None:
            safe_answer_callback(call.id, "Niente da annullare.", True)
        else:
            salva_registro(registro_asta, session)
            safe_answer_callback(call.id, f"↩︎ Annullato: {tolta['nome']}", False)
            try:
                bot.edit_message_text(
                    f"↩︎ <b>Annullato</b>: {html.escape(tolta['nome'])} "
                    f"({tolta['prezzo']} cr)\n💰 cassa <b>{session['budget']}</b>",
                    chat_id, call.message.message_id, parse_mode="HTML")
            except Exception:
                pass

    elif call.data == "menu_wishlist": bot.edit_message_text("⭐ <b>WISHLIST:</b>\n" if session.get('wishlist') else "⭐ <b>VUOTA</b>", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(row_width=1).add(*[InlineKeyboardButton(f"🔍 {n}", callback_data=f"sq_pl_{n}") for n in session.get('wishlist', [])]).add(InlineKeyboardButton("🏠 Home", callback_data="go_home")))

def verifica_istanza_unica(tentativi=6, attesa=10):
    """
    Una chiamata a getUpdates prima di partire: se un'altra istanza sta gia'
    leggendo, Telegram risponde 409. Serve perche' infinity_polling intercetta
    gli errori e ritenta all'infinito, lasciando il bot muto senza spiegazioni.

    Si riprova per un minuto prima di arrendersi: durante un deploy il processo
    precedente puo' impiegare qualche secondo a mollare il token, e uscire
    subito farebbe ripartire Render in un ciclo di riavvii.
    """
    for numero in range(1, tentativi + 1):
        try:
            bot.get_updates(offset=-1, timeout=1)
            if numero > 1:
                print(f"✅ Token libero al tentativo {numero}.")
            return True
        except ApiTelegramException as e:
            if getattr(e, 'error_code', None) != 409:
                print(f"⚠️ Telegram ha risposto {getattr(e, 'error_code', '?')}: proseguo comunque.")
                return True
            if numero < tentativi:
                print(f"⏳ Token occupato (409), tentativo {numero}/{tentativi}: "
                      f"riprovo fra {attesa}s...")
                time.sleep(attesa)
        except Exception as e:
            print(f"⚠️ Controllo istanza non riuscito ({e}): proseguo comunque.")
            return True

    print("🛑 HTTP 409 dopo {} tentativi: un'altra istanza del bot è in ascolto.\n"
          "   Da controllare: un solo servizio su Render con questo BOT_TOKEN,\n"
          "   Instances = 1, nessun deploy vecchio ancora vivo, nessuna copia in locale.\n"
          "   Verifica dall'esterno: apri nel browser\n"
          "   https://api.telegram.org/bot<TOKEN>/getUpdates\n"
          "   con il servizio Render sospeso. Se risponde 409, il fantasma è altrove."
          .format(tentativi))
    return False


def avvia_pianificatore():
    """
    Download notturno del Master e salvataggio periodico delle sessioni.
    Prima lo scheduler era importato ma mai istanziato: il listone si aggiornava
    solo per caso, quando Render riavviava il servizio.
    """
    pianificatore = BackgroundScheduler(timezone="Europe/Rome")
    pianificatore.add_job(auto_download_listone, 'cron',
                          hour=config.ORA_DOWNLOAD, minute=0,
                          id='download_master', replace_existing=True)
    pianificatore.add_job(salva_sessioni, 'interval', seconds=30,
                          id='salva_sessioni', replace_existing=True)
    pianificatore.start()
    print(f"⏰ Download del Master pianificato ogni giorno alle "
          f"{config.ORA_DOWNLOAD:02d}:00 (Europe/Rome).")
    return pianificatore


if __name__ == '__main__':
    carica_sessioni()
    load_data()

    try:
        bot.remove_webhook()
    except Exception:
        pass

    if not verifica_istanza_unica():
        sys.exit(1)

    pianificatore = avvia_pianificatore()
    print("🚀 FANTABOT PRO ASTA LIVE In Ascolto!")

    try:
        bot.infinity_polling(timeout=10, long_polling_timeout=5, skip_pending=True)
    except ApiTelegramException as e:
        if getattr(e, 'error_code', None) == 409:
            print("🛑 HTTP 409 durante il polling: è comparsa una seconda istanza.")
            salva_sessioni()
            sys.exit(1)
        raise
    except KeyboardInterrupt:
        pass
    finally:
        salva_sessioni()
        try:
            pianificatore.shutdown(wait=False)
        except Exception:
            pass
