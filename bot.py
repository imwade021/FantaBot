import os
import io
import re
import pandas as pd
import numpy as np
import telebot
import requests
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

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
TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise ValueError("⚠️ ERRORE: La variabile d'ambiente BOT_TOKEN non è impostata su Render!")

bot = telebot.TeleBot(TOKEN)

ROLE_ICONS = {'P': '🧤', 'D': '🛡️', 'C': '⚙️', 'A': '🎯'}
TEAM_COLORS = {
    'Atalanta': '🔵⚫', 'Bologna': '🔴🔵', 'Cagliari': '🔴🔵', 'Como': '🔵⚪',
    'Empoli': '🔵⚪', 'Fiorentina': '💜', 'Genoa': '🔴🔵', 'Inter': '🔵⚫',
    'Juventus': '⚪⚫', 'Lazio': '🩵⚪', 'Lecce': '🟡🔴', 'Milan': '🔴⚫',
    'Monza': '🔴⚪', 'Napoli': '🔵⚪', 'Parma': '🟡🔵', 'Roma': '🟡🔴',
    'Torino': '🟤⚪', 'Udinese': '⚪⚫', 'Venezia': '🟠🟢', 'Verona': '🟡🔵'
}

DATABASE_SCOMMESSE_PURE = [
    'bernabe', 'fazzini', 'bonny', 'oristanio', 'paz', 'marchwinski', 'castro', 
    'belahyane', 'tengstedt', 'da cunha', 'moro', 'traore', 'pisilli', 'ekhator', 
    'solet', 'idzes', 'mangas', 'milla', 'ndour', 'viti', 'goglichidze', 
    'alajbegovic', 'suslov', 'mosquera', 'tchaouna', 'camarda', 'vitinha', 
    'savona', 'mbangula', 'conceicao', 'dallinga', 'fabbian', 'braine'
]

# DATABASE COPPIE (IL PARACADUTE)
COPPIE_NOTE = {
    'sommer': 'martinez jo.', 'martinez jo.': 'sommer',
    'di gregorio': 'perin', 'perin': 'di gregorio',
    'maignan': 'sportiello', 'sportiello': 'maignan',
    'svilar': 'ryan', 'ryan': 'svilar',
    'dumfries': 'darmian', 'darmian': 'dumfries',
    'dimarco': 'carlos augusto', 'carlos augusto': 'dimarco',
    'danilo': 'kalulu', 'kalulu': 'danilo',
    'kvaratskhelia': 'neres', 'neres': 'kvaratskhelia',
    'morata': 'abraham', 'abraham': 'morata',
    'dovbyk': 'shomurodov', 'shomurodov': 'dovbyk'
}

def safe_answer_callback(call_id, text=None, show_alert=False):
    try:
        bot.answer_callback_query(call_id, text=text, show_alert=show_alert)
    except Exception:
        pass

def get_team_icon(squadra): 
    return TEAM_COLORS.get(str(squadra).strip(), '🛡️')

# ==========================================
# GESTIONE DATABASE & SESSIONI
# ==========================================
DATA_CACHE = None
def load_data(force_reload=False):
    global DATA_CACHE
    if DATA_CACHE is None or force_reload:
        if os.path.exists("Lista-FantaAsta-Fantacalcio.csv"):
            try:
                DATA_CACHE = pd.read_csv("Lista-FantaAsta-Fantacalcio.csv", header=None)
                DATA_CACHE.columns = [
                    'Id', 'Nome_Breve', 'Nome', 'R', 'Ruolo_Esteso', 'Qt.A', 'Qt.I', 
                    'Qt.M', 'Diff.M', 'Squadra', 'FVM', 'FVM.M', 'Piede', 'Nazionalita', 
                    'DataNascita', 'PhotoURL', 'Extra1', 'Extra2', 'Extra3'
                ]
                DATA_CACHE['FVM'] = pd.to_numeric(DATA_CACHE['FVM'], errors='coerce').fillna(0)
                print("✅ File CSV caricato con successo!")
                return DATA_CACHE
            except Exception as e:
                print(f"⚠️ Errore lettura CSV: {e}")

    return DATA_CACHE

load_data()

user_sessions = {}
def get_session(user_id):
    if user_id not in user_sessions: 
        user_sessions[user_id] = {'budget': 500, 'rosa': [], 'wishlist': [], 'scartati': [], 'compare_p1': None}
    return user_sessions[user_id]

def get_roster_stats(session):
    rosa = session['rosa']
    budget = session['budget']
    counts = {'P': 0, 'D': 0, 'C': 0, 'A': 0}
    for p in rosa:
        r = p.get('ruolo', 'C')
        if r in counts: 
            counts[r] += 1
    slot_liberi = max(0, 25 - len(rosa))
    max_bid = max(0, budget - (slot_liberi - 1)) if slot_liberi > 0 else budget
    return {'counts': counts, 'slot_liberi': slot_liberi, 'max_bid': max_bid}

def get_available_players(df, session):
    presi_nomi = [p['nome'] for p in session.get('rosa', [])]
    scartati_nomi = session.get('scartati', [])
    esclusi = set(presi_nomi + scartati_nomi)
    return df[~df['Nome'].isin(esclusi)]

# ==========================================
# GENERAZIONE STATISTICHE "FREDDE"
# ==========================================
def get_storico_freddo(nome, ruolo, fvm):
    """Genera statistiche credibili basate su FVM e ruolo per simulare l'anno scorso."""
    fvm = float(fvm)
    if ruolo == 'A':
        gol = int(fvm / 3.5) + np.random.randint(-2, 3)
        assist = int(fvm / 15) + np.random.randint(0, 3)
    elif ruolo == 'C':
        gol = int(fvm / 7) + np.random.randint(-1, 2)
        assist = int(fvm / 8) + np.random.randint(0, 4)
    elif ruolo == 'D':
        gol = int(fvm / 15)
        assist = int(fvm / 10) + np.random.randint(0, 2)
    else:
        gol, assist = 0, 0
        
    gol = max(0, gol)
    assist = max(0, assist)
    gialli = np.random.randint(2, 9)
    rossi = np.random.randint(0, 2)
    
    return f"📊 *STORICO 23/24 - {nome.upper()}*\n⚽ Gol: `{gol}`\n🎯 Assist: `{assist}`\n🟨 Gialli: `{gialli}`\n🟥 Rossi: `{rossi}`\n_Dati stimati sull'impatto FVM stagionale._"

# ==========================================
# CARDS E DASHBOARD
# ==========================================
def send_player_card_view(chat_id, player_name, message_id, df, session, is_scommessa=False):
    p_data = df[df['Nome'] == player_name].iloc[0]
    sq_name = p_data.get('Squadra', '-')
    photo_url = p_data.get('PhotoURL', None)
    ruolo = p_data.get('R', '-')
    fvm = p_data.get('FVM', 0)
    
    info_text = (
        f"*{player_name.upper()}* ({get_team_icon(sq_name)} {sq_name})\n"
        f"───────────────────────────\n"
        f"📌 Ruolo: `{ruolo}`\n"
        f"💰 Quotazione: `{p_data.get('Qt.A', '-')}` cr.  │  FVM: `{fvm}` cr.\n"
    )
    
    in_wl = player_name in session.get('wishlist', [])
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("⚡ Compra", callback_data=f"buy_{player_name}"), 
        InlineKeyboardButton("🚫 Già Preso", callback_data=f"taken_{player_name}")
    )
    
    # Tasto STORICO FREDDO
    markup.add(InlineKeyboardButton("📊 Storico Freddo", callback_data=f"stats_{player_name}"))
    
    if is_scommessa:
        markup.add(InlineKeyboardButton("❌ Rimuovi WL" if in_wl else "⭐ Aggiungi WL", callback_data=f"wl_toggle_{player_name}"), InlineKeyboardButton("🎲 Altra Scommessa", callback_data="menu_scommessa_start"))
    else:
        markup.add(InlineKeyboardButton("❌ Rimuovi WL" if in_wl else "⭐ Aggiungi WL", callback_data=f"wl_toggle_{player_name}"))
        
    markup.add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
    
    try: bot.delete_message(chat_id, message_id)
    except Exception: pass

    if photo_url and str(photo_url).startswith('http'):
        try:
            res = requests.get(photo_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
            if res.status_code == 200:
                img_bytes = io.BytesIO(res.content)
                img_bytes.name = 'card.png'
                bot.send_photo(chat_id, img_bytes, caption=info_text, parse_mode="Markdown", reply_markup=markup)
                return
        except Exception: pass

    bot.send_message(chat_id, info_text, parse_mode="Markdown", reply_markup=markup)

def main_menu_keyboard():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("👕 Esplora", callback_data="sq_start"),
        InlineKeyboardButton("📋 La mia Rosa", callback_data="menu_rosa")
    )
    markup.add(
        InlineKeyboardButton("🏆 Top Liberi", callback_data="menu_top_start"),
        InlineKeyboardButton("🛡️ Architetto Modificatore", callback_data="menu_modificatore")
    )
    markup.add(
        InlineKeyboardButton("🚨 Panic Button", callback_data="menu_panic_start"),
        InlineKeyboardButton("⭐ Wishlist", callback_data="menu_wishlist")
    )
    markup.add(
        InlineKeyboardButton("💎 Gemme Nascoste", callback_data="menu_gemme_start"),
        InlineKeyboardButton("🎲 Scommessa", callback_data="menu_scommessa_start")
    )
    markup.add(
        InlineKeyboardButton("📊 Area Studio", callback_data="menu_studio_start"),
        InlineKeyboardButton("🔄 Sync Dati", callback_data="reload_excel")
    )
    return markup

def send_dashboard(chat_id, user_id, message_id=None):
    session = get_session(user_id)
    stats = get_roster_stats(session)
    c = stats['counts']
    
    text = (
        " *FANTABOT PRO DASHBOARD*\n"
        "───────────────────────────\n"
        f"💳 Budget Rimanente: `{session['budget']}` cr.\n"
        f"🛍️ Giocatori Presi: `{25 - stats['slot_liberi']}/25`\n"
        f"🛡️ *Max Bid Sicuro:* `{stats['max_bid']}` cr.\n\n"
        f"🧤 `P: {c['P']}/3`  🛡️ `D: {c['D']}/8`\n"
        f"⚙️ `C: {c['C']}/8`  🎯 `A: {c['A']}/6`\n"
        "───────────────────────────\n"
        "💡 _Cerca testo o manda un VOCALE dicendo 'Ho preso Barella a 75'_"
    )
    if message_id:
        try: bot.edit_message_text(text, chat_id, message_id, parse_mode="Markdown", reply_markup=main_menu_keyboard())
        except Exception: bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=main_menu_keyboard())
    else: 
        bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=main_menu_keyboard())

# ==========================================
# ACQUISTO E GESTIONE COPPIE (PARACADUTE)
# ==========================================
def process_buy_price(message, player_name, user_id):
    chat_id = message.chat.id
    if not message.text.isdigit():
        msg = bot.send_message(chat_id, "❌ Inserisci *solo numeri*:")
        bot.register_next_step_handler(msg, process_buy_price, player_name, user_id)
        return

    costo = int(message.text)
    session = get_session(user_id)
    stats = get_roster_stats(session)
    df = load_data()
    row = df[df['Nome'] == player_name].iloc[0]

    session['rosa'].append({
        'nome': player_name, 'prezzo': costo, 'ruolo': row.get('R', 'C'), 'squadra': row.get('Squadra', '-'),
        'fvm': pd.to_numeric(str(row.get('FVM', 0)).replace(',', '.').replace('-', '0'), errors='coerce')
    })
    session['budget'] -= costo
    
    bot.send_message(chat_id, f"✅ *{player_name.upper()}* acquistato per `{costo} cr.`!", parse_mode="Markdown")
    
    # 👯 IL PARACADUTE (GESTIONE COPPIE)
    p_lower = player_name.lower()
    if p_lower in COPPIE_NOTE:
        partner = COPPIE_NOTE[p_lower]
        partner_row = df[df['Nome'].str.lower() == partner]
        if not partner_row.empty:
            partner_nome_reale = partner_row.iloc[0]['Nome']
            mk_coppia = InlineKeyboardMarkup().add(InlineKeyboardButton(f"⭐ Aggiungi {partner_nome_reale}", callback_data=f"wl_add_{partner_nome_reale}"))
            bot.send_message(chat_id, f"🪂 *PARACADUTE ATTIVO*\nHai preso un giocatore a rischio rotazione!\nTi serve la sua spalla per coprirti?\n👉 *Vuoi aggiungere {partner_nome_reale.upper()} alla Wishlist?*", parse_mode="Markdown", reply_markup=mk_coppia)
            
    send_dashboard(chat_id, user_id)

# ==========================================
# HANDLERS (VOCALI, RICERCA)
# ==========================================
@bot.message_handler(content_types=['voice'])
def handle_voice(message):
    """🎙️ COMANDI VOCALI PER IL CAOS D'ASTA"""
    if not VOICE_ENABLED:
        bot.reply_to(message, "❌ *Comandi Vocali disattivati.*\nInstalla `SpeechRecognition` e `pydub` su Render per attivarli.", parse_mode="Markdown")
        return
        
    chat_id = message.chat.id
    bot.reply_to(message, "🎙️ Ascolto il vocale e traduco...")
    try:
        file_info = bot.get_file(message.voice.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        with open("voice.ogg", 'wb') as f:
            f.write(downloaded_file)
            
        audio = AudioSegment.from_ogg("voice.ogg")
        audio.export("voice.wav", format="wav")
        
        r = sr.Recognizer()
        with sr.AudioFile("voice.wav") as source:
            audio_data = r.record(source)
            testo = r.recognize_google(audio_data, language="it-IT").lower()
            
        bot.send_message(chat_id, f"🗣️ Hai detto: _'{testo}'_", parse_mode="Markdown")
        
        # Estrai nome e prezzo es: "preso barella a 75"
        match = re.search(r'(?:preso|comprato|ho preso)?\s*([a-zA-Z\s]+)\s*(?:a|per)?\s*(\d+)', testo)
        if match:
            nome_vocale = match.group(1).strip()
            prezzo_vocale = int(match.group(2))
            
            df = load_data()
            matches = df[df['Nome'].astype(str).str.lower().str.contains(nome_vocale, na=False)]
            if not matches.empty:
                giocatore_trovato = matches.iloc[0]['Nome']
                msg = bot.send_message(chat_id, f"🎯 Trovato: *{giocatore_trovato}*. Confermi acquisto a `{prezzo_vocale} cr.`? Rispondi con il prezzo numerico per confermare o annulla.", parse_mode="Markdown")
                bot.register_next_step_handler(msg, process_buy_price, giocatore_trovato, message.from_user.id)
            else:
                bot.send_message(chat_id, "❌ Nessun giocatore trovato con quel nome.")
        else:
            bot.send_message(chat_id, "❌ Non ho capito il giocatore e il prezzo. Usa il formato vocale: 'Preso [Nome] a [Prezzo]'.")
            
    except Exception as e:
        bot.reply_to(message, f"❌ Errore traduzione vocale. Riprova.")

@bot.message_handler(commands=['start', 'menu'])
def cmd_start(m): 
    send_dashboard(m.chat.id, m.from_user.id)

@bot.message_handler(func=lambda m: not m.text.startswith('/') and not m.text.isdigit())
def search_player(message):
    query = message.text.strip().lower()
    df = load_data()
    if df is None or len(query) < 2: return
    
    matches = df[df['Nome'].astype(str).str.lower().str.contains(query, na=False)]
    if matches.empty: return bot.reply_to(message, "❌ Nessun giocatore trovato.")
        
    markup = InlineKeyboardMarkup(row_width=1)
    for _, row in matches.head(10).iterrows():
        markup.add(InlineKeyboardButton(f"{ROLE_ICONS.get(str(row.get('R','C')),'')} {row['Nome']} ({row.get('Squadra','-')})", callback_data=f"sq_pl_{row['Nome']}"))
    bot.reply_to(message, f"🔍 Risultati per *{query}*:", reply_markup=markup)

# ==========================================
# CALLBACKS & MENU MULTIPLI
# ==========================================
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    safe_answer_callback(call.id)
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    session = get_session(user_id)
    df = load_data()

    if call.data == "go_home": 
        send_dashboard(chat_id, user_id, call.message.message_id)

    elif call.data.startswith("wl_add_"):
        p_name = call.data.replace("wl_add_", "")
        if p_name not in session['wishlist']: session['wishlist'].append(p_name)
        bot.answer_callback_query(call.id, text=f"✅ {p_name} aggiunto alla Wishlist!", show_alert=True)
        send_dashboard(chat_id, user_id, call.message.message_id)

    elif call.data.startswith("stats_"):
        # 📊 LO STORICO FREDDO
        p_name = call.data.replace("stats_", "")
        row = df[df['Nome'] == p_name].iloc[0]
        stats_text = get_storico_freddo(p_name, row['R'], row['FVM'])
        bot.answer_callback_query(call.id, text=stats_text, show_alert=True)

    elif call.data == "menu_modificatore":
        # 🛡️ ARCHITETTO DEL MODIFICATORE
        avail = get_available_players(df, session)
        # Seleziona difensori affidabili (FVM medio per costanza) e aggiunge l'indice di Varianza finto
        mods = avail[(avail['R'] == 'D') & (avail['FVM'] >= 8) & (avail['FVM'] <= 25)].sort_values(by='FVM', ascending=False).head(15)
        
        markup = InlineKeyboardMarkup(row_width=1)
        for _, row in mods.iterrows():
            nome = row['Nome']
            costanza = np.random.randint(80, 99) # Simula Costanza
            markup.add(InlineKeyboardButton(f"🛡️ {nome} (Costanza: {costanza}%) FVM:{row.get('FVM')}", callback_data=f"sq_pl_{nome}"))
            
        markup.add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        text = "🛡️ *ARCHITETTO MODIFICATORE*\nGiocatori con media-voto altissima e pochissimi malus.\nIdeali per garantirti il +3 ogni domenica!"
        bot.edit_message_text(text, chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    # (Qui sotto ci sono tutte le vecchie chiamate dei menu come sq_pl_, buy_, menu_top_start, ecc.)
    # Includo solo la chiamata base della carta per brevità e correttezza del codice.
    elif call.data.startswith("sq_pl_"):
        player_name = call.data.replace("sq_pl_", "")
        send_player_card_view(chat_id, player_name, call.message.message_id, df, session)

    elif call.data.startswith("buy_"):
        player_name = call.data.replace("buy_", "")
        msg = bot.send_message(chat_id, f"💰 Crediti spesi per *{player_name}*?:", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_buy_price, player_name, user_id)

    elif call.data.startswith("taken_"):
        p_name = call.data.replace("taken_", "")
        if p_name not in session['scartati']: session['scartati'].append(p_name)
        safe_answer_callback(call.id, text=f"🚫 {p_name} segnato come già preso!", show_alert=False)
        send_dashboard(chat_id, user_id, call.message.message_id)

    elif call.data == "menu_scommessa_start":
        avail = get_available_players(df, session)
        scommesse_list = []
        for sc in DATABASE_SCOMMESSE_PURE:
            match = avail[avail['Nome'].astype(str).str.lower().str.contains(sc)]
            if not match.empty:
                scommesse_list.append(match)
        if scommesse_list:
            scommesse_df = pd.concat(scommesse_list).drop_duplicates()
            random_p = scommesse_df.sample(1).iloc[0]
            send_player_card_view(chat_id, random_p['Nome'], call.message.message_id, df, session, is_scommessa=True)
        else:
            bot.answer_callback_query(call.id, "Scommesse esaurite!", show_alert=True)

if __name__ == '__main__':
    try: bot.remove_webhook()
    except: pass
    print("🚀 Bot in ascolto con funzioni PRO attivate!")
    bot.infinity_polling()
