import os
import io
import pandas as pd
import numpy as np
import telebot
import requests
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

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

        if os.path.exists("listone.xlsx"): 
            for row_h in range(0, 5):
                try:
                    df_test = pd.read_excel("listone.xlsx", header=row_h, engine='openpyxl')
                    cols = [str(c).strip().lower() for c in df_test.columns]
                    if 'nome' in cols or 'id' in cols or 'cod' in cols:
                        df_test.columns = [str(c).strip() for c in df_test.columns]
                        if 'FVM' in df_test.columns:
                            df_test['FVM'] = pd.to_numeric(df_test['FVM'], errors='coerce').fillna(0)
                        DATA_CACHE = df_test
                        print("✅ File listone.xlsx caricato correttamente!")
                        break
                except Exception:
                    continue

    return DATA_CACHE

load_data()

user_sessions = {}
def get_session(user_id):
    if user_id not in user_sessions: 
        user_sessions[user_id] = {
            'budget': 500, 
            'rosa': [], 
            'wishlist': [], 
            'scartati': [],
            'compare_p1': None
        }
    return user_sessions[user_id]

def generate_progress_bar(current, target, length=8):
    filled = min(length, max(0, int(round(length * current / target)))) if target > 0 else 0
    return '■' * filled + '□' * (length - filled)

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
# FUNZIONE UNICA PER GENERARE LE CARD 
# ==========================================
def send_player_card_view(chat_id, player_name, message_id, df, session, is_scommessa=False):
    p_data = df[df['Nome'] == player_name].iloc[0]
    sq_name = p_data.get('Squadra', '-')
    photo_url = p_data.get('PhotoURL', None)
    
    info_text = (
        f"*{player_name.upper()}* ({get_team_icon(sq_name)} {sq_name})\n"
        f"───────────────────────────\n"
        f"📌 Ruolo: `{p_data.get('R', '-')}`\n"
        f"💰 Quotazione: `{p_data.get('Qt.A', '-')}` cr.  │  FVM: `{p_data.get('FVM', '-')}` cr.\n"
    )
    
    in_wl = player_name in session.get('wishlist', [])
    wl_text = "❌ Rimuovi Wishlist" if in_wl else "⭐ Aggiungi Wishlist"
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("⚡ Compra", callback_data=f"buy_{player_name}"), 
        InlineKeyboardButton("🚫 Già Preso", callback_data=f"taken_{player_name}")
    )
    
    if is_scommessa:
        markup.add(InlineKeyboardButton(wl_text, callback_data=f"wl_toggle_{player_name}"), InlineKeyboardButton("🎲 Altra Scommessa", callback_data="menu_scommessa_start"))
    else:
        markup.add(InlineKeyboardButton(wl_text, callback_data=f"wl_toggle_{player_name}"))
        
    markup.add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
    
    try: bot.delete_message(chat_id, message_id)
    except Exception: pass

    if photo_url and str(photo_url).startswith('http'):
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            res = requests.get(photo_url, headers=headers, timeout=5)
            if res.status_code == 200:
                img_bytes = io.BytesIO(res.content)
                img_bytes.name = 'card.png'
                bot.send_photo(chat_id, img_bytes, caption=info_text, parse_mode="Markdown", reply_markup=markup)
                return
        except Exception:
            pass

    bot.send_message(chat_id, info_text, parse_mode="Markdown", reply_markup=markup)

# ==========================================
# KEYBOARD & DASHBOARD
# ==========================================
def main_menu_keyboard():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("👕 Esplora", callback_data="sq_start"),
        InlineKeyboardButton("📋 La mia Rosa", callback_data="menu_rosa")
    )
    markup.add(
        InlineKeyboardButton("🏆 Top Liberi", callback_data="menu_top_start"),
        InlineKeyboardButton("⚽ Formazione", callback_data="menu_formazione")
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
        InlineKeyboardButton("✂️ Svincola", callback_data="menu_svincola"),
        InlineKeyboardButton("📊 Area Studio", callback_data="menu_studio_start")
    )
    markup.add(
        InlineKeyboardButton("🔄 Sync Dati", callback_data="reload_excel"),
        InlineKeyboardButton("⚠️ Reset Rosa", callback_data="reset_confirm")
    )
    markup.add(
        InlineKeyboardButton("🧹 Pulisci Schermo", callback_data="clear_screen")
    )
    return markup

def send_dashboard(chat_id, user_id, message_id=None):
    session = get_session(user_id)
    stats = get_roster_stats(session)
    c = stats['counts']
    
    text = (
        " *FANTABOT PRO DASHBOARD*\n"
        "───────────────────────────\n"
        "💳 *BILANCIO ASTA*\n"
        f"• Budget Rimanente: `{session['budget']}` cr.\n"
        f"• Giocatori Presi: `{25 - stats['slot_liberi']}/25`\n"
        f"• *Max Bid Sicuro:* `{stats['max_bid']}` cr.\n\n"
        "📊 *COPERTURA ROSTER*\n"
        f"🧤 `Portieri`   `[{generate_progress_bar(c['P'], 3, 6)}]` `{c['P']}/3`\n"
        f"🛡️ `Difensori`  `[{generate_progress_bar(c['D'], 8, 6)}]` `{c['D']}/8`\n"
        f"⚙️ `Centrocampi` `[{generate_progress_bar(c['C'], 8, 6)}]` `{c['C']}/8`\n"
        f"🎯 `Attaccanti`  `[{generate_progress_bar(c['A'], 6, 6)}]` `{c['A']}/6`\n"
        "───────────────────────────\n"
        "💡 _Cerca nome o scrivi `+ nome prezzo` per comprare al volo!_\n"
    )
    if message_id:
        try: bot.edit_message_text(text, chat_id, message_id, parse_mode="Markdown", reply_markup=main_menu_keyboard())
        except Exception: bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=main_menu_keyboard())
    else: 
        bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=main_menu_keyboard())

def menu_seleziona_squadra(df, prefisso):
    markup = InlineKeyboardMarkup(row_width=2)
    squadre = sorted(df['Squadra'].dropna().astype(str).unique())
    markup.add(*[InlineKeyboardButton(f"{get_team_icon(sq)} {sq}", callback_data=f"{prefisso}_sq_{sq}") for sq in squadre])
    markup.add(InlineKeyboardButton("🔙 Home", callback_data="go_home"))
    return markup

def menu_seleziona_ruolo(squadra, prefisso):
    markup = InlineKeyboardMarkup(row_width=4)
    markup.add(*[InlineKeyboardButton(f"{ROLE_ICONS[r]} {r}", callback_data=f"{prefisso}_ru_{squadra}_{r}") for r in ['P', 'D', 'C', 'A']])
    markup.add(InlineKeyboardButton("🔙 Squadre", callback_data=f"{prefisso}_start"))
    return markup

def menu_seleziona_giocatore(df, squadra, ruolo, prefisso, user_id):
    markup = InlineKeyboardMarkup(row_width=1)
    sub = df[(df['Squadra'] == squadra) & (df['R'] == ruolo)]
    for _, row in sub.iterrows():
        star = "⭐ " if row['Nome'] in get_session(user_id).get('wishlist', []) else ""
        markup.add(InlineKeyboardButton(f"{star}{ROLE_ICONS.get(ruolo,'')} {row['Nome']} ─ FVM:{row.get('FVM', '-')}", callback_data=f"{prefisso}_pl_{row['Nome']}"))
    markup.add(InlineKeyboardButton("🔙 Cambia Ruolo", callback_data=f"{prefisso}_sq_{squadra}"))
    return markup

def process_buy_price(message, player_name, user_id):
    chat_id = message.chat.id
    if not message.text or not message.text.isdigit():
        msg = bot.send_message(chat_id, "❌ Inserisci *solo numeri interi*:", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_buy_price, player_name, user_id)
        return

    costo = int(message.text)
    session = get_session(user_id)
    stats = get_roster_stats(session)

    if costo > stats['max_bid']:
        bot.send_message(chat_id, f"⚠️ *ATTENZIONE!*\nOfferta oltre il *Max Bid Sicuro* (`{stats['max_bid']} cr.`).", parse_mode="Markdown")
        send_dashboard(chat_id, user_id)
        return

    df = load_data()
    try: row = df[df['Nome'] == player_name].iloc[0]
    except: return

    squadra_acquistata = row.get('Squadra', '-')
    ruolo_acquistato = row.get('R', 'C')
    fvm = pd.to_numeric(str(row.get('FVM', 0)).replace(',', '.').replace('-', '0'), errors='coerce')

    session['rosa'].append({
        'nome': player_name, 'prezzo': costo, 'ruolo': ruolo_acquistato, 'squadra': squadra_acquistata,
        'fvm': 0 if pd.isna(fvm) else fvm
    })
    session['budget'] -= costo
    
    markup = InlineKeyboardMarkup().add(InlineKeyboardButton("↩️ Annulla", callback_data=f"undo_{player_name}"), InlineKeyboardButton("🏠 Home", callback_data="go_home"))
    bot.send_message(chat_id, f"✅ *{player_name.upper()}* acquistato per `{costo} cr.`!", parse_mode="Markdown", reply_markup=markup)

# ==========================================
# HANDLERS MESSAGGI & CECCHINO
# ==========================================
@bot.message_handler(func=lambda m: m.text.strip().startswith('+'))
def modalita_cecchino(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = message.text.strip()[1:].strip() 
    
    try:
        parts = text.rsplit(' ', 1)
        if len(parts) != 2 or not parts[1].isdigit():
            bot.reply_to(message, "❌ *Errore Cecchino!*\nUsa il formato: `+ nomegiocatore prezzo`\nEsempio: `+ neres 35`", parse_mode="Markdown")
            return
            
        query_nome = parts[0].strip().lower()
        costo = int(parts[1])
        
        df = load_data()
        if df is None:
            bot.reply_to(message, "❌ Carica prima il file database!")
            return

        matches = df[df['Nome'].astype(str).str.lower().str.contains(query_nome, na=False)]
        if matches.empty:
            bot.reply_to(message, f"❌ Nessun giocatore trovato per '{query_nome}'.", parse_mode="Markdown")
            return
            
        row = matches.iloc[0] 
        player_name = row['Nome']
        
        session = get_session(user_id)
        stats = get_roster_stats(session)
        
        if costo > stats['max_bid']:
            bot.reply_to(message, f"⚠️ *ALLARME BUDGET!*\nStai spendendo `{costo}`, ma il tuo Max Bid è `{stats['max_bid']}`.", parse_mode="Markdown")
            return
            
        ruolo_acquistato = row.get('R', 'C')
        sq_acquistata = row.get('Squadra', '-')
        fvm = pd.to_numeric(str(row.get('FVM', 0)).replace(',', '.').replace('-', '0'), errors='coerce')
        
        session['rosa'].append({
            'nome': player_name, 'prezzo': costo, 'ruolo': ruolo_acquistato, 'squadra': sq_acquistata,
            'fvm': 0 if pd.isna(fvm) else fvm
        })
        session['budget'] -= costo
        
        markup = InlineKeyboardMarkup().add(InlineKeyboardButton("↩️ Annulla", callback_data=f"undo_{player_name}"), InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.reply_to(message, f"🎯 *CECCHINO A BERSAGLIO!*\n✅ Hai acquistato *{player_name.upper()}* a `{costo} cr.`\nRimangono {session['budget']} crediti.", parse_mode="Markdown", reply_markup=markup)
        
    except Exception:
        bot.reply_to(message, "❌ Errore durante l'acquisto rapido.")

@bot.message_handler(commands=['start', 'menu'])
def cmd_start(m): 
    send_dashboard(m.chat.id, m.from_user.id)

@bot.message_handler(func=lambda m: not m.text.startswith('/') and not m.text.startswith('+') and not m.text.isdigit())
def search_player(message):
    query = message.text.strip().lower()
    df = load_data()
    if df is None or len(query) < 2: return
    
    matches = df[df['Nome'].astype(str).str.lower().str.contains(query, na=False)]
    if matches.empty and 'Nome_Breve' in df.columns:
        matches = df[df['Nome_Breve'].astype(str).str.lower().str.contains(query, na=False)]
        
    if matches.empty: return bot.reply_to(message, "❌ Nessun giocatore trovato.")
        
    markup = InlineKeyboardMarkup(row_width=1)
    for _, row in matches.head(10).iterrows():
        markup.add(InlineKeyboardButton(f"{ROLE_ICONS.get(str(row.get('R','C')),'')} {row['Nome']} ({row.get('Squadra','-')})", callback_data=f"sq_pl_{row['Nome']}"))
    bot.reply_to(message, f"🔍 Risultati per *{query}*:", reply_markup=markup)

# ==========================================
# ROUTING & GESTIONE CLICK PULSANTI
# ==========================================
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    safe_answer_callback(call.id)
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    session = get_session(user_id)
    df = load_data()

    if call.data == "clear_screen":
        curr_id = call.message.message_id
        for i in range(curr_id, max(0, curr_id - 80), -1):
            try: bot.delete_message(chat_id, i)
            except Exception: pass
        send_dashboard(chat_id, user_id)

    elif call.data == "go_home": 
        session['compare_p1'] = None
        send_dashboard(chat_id, user_id, call.message.message_id)

    elif call.data == "reload_excel": 
        load_data(force_reload=True)
        bot.send_message(chat_id, "⚡ *Dati sincronizzati con successo!*", parse_mode="Markdown")

    elif call.data == "reset_confirm":
        user_sessions[user_id] = {'budget': 500, 'rosa': [], 'wishlist': session.get('wishlist', []), 'scartati': [], 'compare_p1': None}
        send_dashboard(chat_id, user_id, call.message.message_id)

    elif call.data.startswith("taken_"):
        p_name = call.data.replace("taken_", "")
        if 'scartati' not in session: session['scartati'] = []
        if p_name not in session['scartati']: session['scartati'].append(p_name)
        safe_answer_callback(call.id, text=f"🚫 {p_name} segnato come già preso!", show_alert=False)
        send_dashboard(chat_id, user_id, call.message.message_id)

    elif call.data == "menu_rosa":
        rosa = session.get('rosa', [])
        if not rosa:
            text = "📋 *LA TUA ROSA E VUOTA!*\nAcquista giocatori per vederli qui."
        else:
            text = "📋 *LA TUA ROSA:*\n───────────────────────────\n"
            for r in ['P', 'D', 'C', 'A']:
                giocatori_r = [p for p in rosa if p.get('ruolo') == r]
                if giocatori_r:
                    text += f"\n*{ROLE_ICONS[r]} {r}:*\n"
                    for p in giocatori_r:
                        text += f"• {p['nome']} (`{p['prezzo']} cr.`)\n"
        markup = InlineKeyboardMarkup().add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text(text, chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    # --- ESPLORA SQUADRE ---
    elif call.data == "sq_start":
        if df is None: return
        bot.edit_message_text("👕 *ESPLORA SQUADRE*", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=menu_seleziona_squadra(df, "sq"))

    elif call.data.startswith("sq_sq_"):
        bot.edit_message_text("Scegli il ruolo:", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=menu_seleziona_ruolo(call.data.replace("sq_sq_", ""), "sq"))

    elif call.data.startswith("sq_ru_"):
        _, _, sq, ru = call.data.split("_")
        bot.edit_message_text(f"Giocatori ({sq} - {ru}):", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=menu_seleziona_giocatore(df, sq, ru, "sq", user_id))

    # --- SEZIONE TOP LIBERI (I Campioni) ---
    elif call.data == "menu_top_start":
        markup = InlineKeyboardMarkup(row_width=4)
        markup.add(*[InlineKeyboardButton(f"{ROLE_ICONS[r]} {r}", callback_data=f"menu_top_ru_{r}") for r in ['P', 'D', 'C', 'A']])
        markup.add(InlineKeyboardButton("🔙 Home", callback_data="go_home"))
        bot.edit_message_text("🏆 *TOP LIBERI (I Big rimasti) - Scegli il ruolo:*", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data.startswith("menu_top_ru_"):
        r = call.data.replace("menu_top_ru_", "")
        if df is None: return
        avail = get_available_players(df, session)
        # Non ci sono limiti di FVM, prende semplicemente i più alti in assoluto rimasti
        top_players = avail[avail['R'] == r].sort_values(by='FVM', ascending=False).head(15)
        
        markup = InlineKeyboardMarkup(row_width=1)
        for _, row in top_players.iterrows():
            nome = row['Nome']
            markup.add(InlineKeyboardButton(f"🔍 {nome} ({row.get('Squadra','-')}) FVM:{row.get('FVM','-')}", callback_data=f"sq_pl_{nome}"))
            
        markup.add(InlineKeyboardButton("🔙 Cambia Ruolo", callback_data="menu_top_start"), InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text(f"🏆 *TOP 15 LIBERI - RUOLO {ROLE_ICONS[r]} {r}:*\nClicca sul giocatore per vederlo e acquistarlo.", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    # --- SEZIONE GEMME NASCOSTE (I Low Cost di Lusso, FVM 6-20) ---
    elif call.data == "menu_gemme_start":
        markup = InlineKeyboardMarkup(row_width=4)
        markup.add(*[InlineKeyboardButton(f"{ROLE_ICONS[r]} {r}", callback_data=f"menu_gemme_ru_{r}") for r in ['P', 'D', 'C', 'A']])
        markup.add(InlineKeyboardButton("🔙 Home", callback_data="go_home"))
        bot.edit_message_text("💎 *GEMME NASCOSTE (FVM 6-20) - Scegli il ruolo:*", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data.startswith("menu_gemme_ru_"):
        r = call.data.replace("menu_gemme_ru_", "")
        if df is None: return
        avail = get_available_players(df, session)
        # Limite di FVM per i giocatori da 3/4 slot
        gemme = avail[(avail['R'] == r) & (avail['FVM'] <= 20) & (avail['FVM'] >= 6)].sort_values(by='FVM', ascending=False).head(15)
        
        markup = InlineKeyboardMarkup(row_width=1)
        for _, row in gemme.iterrows():
            nome = row['Nome']
            markup.add(InlineKeyboardButton(f"💎 {nome} ({row.get('Squadra','-')}) FVM:{row.get('FVM','-')}", callback_data=f"sq_pl_{nome}"))
            
        markup.add(InlineKeyboardButton("🔙 Cambia Ruolo", callback_data="menu_gemme_start"), InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text(f"💎 *GEMME NASCOSTE - RUOLO {ROLE_ICONS[r]} {r}:*\nOttime occasioni a medio prezzo.", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    # --- SEZIONE PANIC BUTTON (Tappabuchi a 1 credito, FVM 1-5) ---
    elif call.data == "menu_panic_start":
        markup = InlineKeyboardMarkup(row_width=4)
        markup.add(*[InlineKeyboardButton(f"{ROLE_ICONS[r]} {r}", callback_data=f"menu_panic_ru_{r}") for r in ['P', 'D', 'C', 'A']])
        markup.add(InlineKeyboardButton("🔙 Home", callback_data="go_home"))
        bot.edit_message_text("🚨 *PANIC BUTTON (FVM 1-5) - Scegli il ruolo di emergenza:*", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data.startswith("menu_panic_ru_"):
        r = call.data.replace("menu_panic_ru_", "")
        if df is None: return
        avail = get_available_players(df, session)
        # Filtra solo i giocatori con FVM tra 1 e 5 (I Tappabuchi a 1 credito)
        panic_list = avail[(avail['R'] == r) & (avail['FVM'] <= 5) & (avail['FVM'] >= 1)].sort_values(by='FVM', ascending=False).head(15)
        
        markup = InlineKeyboardMarkup(row_width=1)
        for _, row in panic_list.iterrows():
            nome = row['Nome']
            markup.add(InlineKeyboardButton(f"🚨 {nome} ({row.get('Squadra','-')}) FVM:{row.get('FVM','-')}", callback_data=f"sq_pl_{nome}"))
            
        markup.add(InlineKeyboardButton("🔙 Cambia Ruolo", callback_data="menu_panic_start"), InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text(f"🚨 *PANIC BUTTON - RUOLO {ROLE_ICONS[r]} {r}:*\nTappabuchi perfetti per chiudere la rosa a 1 credito!", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    # --- SEZIONE SCOMMESSE (SLOT MACHINE CARD) ---
    elif call.data == "menu_scommessa_start":
        if df is None: return
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
            safe_answer_callback(call.id, text="Nessuna scommessa disponibile o sono già state prese tutte!", show_alert=True)

    # --- AREA STUDIO (COMPARATORE SQUADRA -> RUOLO -> GIOCATORE CONSERVA RUOLO) ---
    elif call.data == "menu_studio_start":
        session['compare_p1'] = None
        if df is None: return
        bot.edit_message_text("📊 *AREA STUDIO - Selezione GIOCATORE 1*\nScegli la squadra del primo giocatore:", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=menu_seleziona_squadra(df, "std1"))

    elif call.data.startswith("std1_sq_"):
        sq = call.data.replace("std1_sq_", "")
        bot.edit_message_text(f"📊 *AREA STUDIO - GIOCATORE 1 ({sq})*\nScegli il ruolo:", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=menu_seleziona_ruolo(sq, "std1"))

    elif call.data.startswith("std1_ru_"):
        _, _, sq, ru = call.data.split("_")
        bot.edit_message_text(f"📊 *AREA STUDIO - GIOCATORE 1 ({sq} - {ru})*\nScegli il primo giocatore:", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=menu_seleziona_giocatore(df, sq, ru, "std1", user_id))

    elif call.data.startswith("std1_pl_"):
        p1_nome = call.data.replace("std1_pl_", "")
        p1_row = df[df['Nome'] == p1_nome].iloc[0]
        session['compare_p1'] = p1_row.to_dict()
        ruolo_p1 = p1_row['R']
        
        markup = InlineKeyboardMarkup(row_width=2)
        squadre = sorted(df['Squadra'].dropna().astype(str).unique())
        markup.add(*[InlineKeyboardButton(f"{get_team_icon(sq)} {sq}", callback_data=f"std2_sq_{sq}") for sq in squadre])
        markup.add(InlineKeyboardButton("🔙 Reset Confronto", callback_data="menu_studio_start"))
        
        bot.edit_message_text(
            f"📊 *CONFRONTO:* Hai selezionato *{p1_nome.upper()}* ({ROLE_ICONS[ruolo_p1]} {ruolo_p1})\n\n"
            f"Ora seleziona la squadra del *SECONDO GIOCATORE* (vedrai solo i giocatori del ruolo {ruolo_p1}):",
            chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup
        )

    elif call.data.startswith("std2_sq_"):
        sq2 = call.data.replace("std2_sq_", "")
        p1 = session.get('compare_p1')
        if not p1: return
        ruolo_p1 = p1['R']
        
        # Filtra i giocatori della squadra 2 che hanno lo STESSO RUOLO di P1
        markup = InlineKeyboardMarkup(row_width=1)
        sub = df[(df['Squadra'] == sq2) & (df['R'] == ruolo_p1) & (df['Nome'] != p1['Nome'])]
        
        for _, row in sub.iterrows():
            markup.add(InlineKeyboardButton(f"🆚 Confronta con {row['Nome']} (FVM:{row.get('FVM','-')})", callback_data=f"std2_pl_{row['Nome']}"))
            
        markup.add(InlineKeyboardButton("🔙 Cambia Squadra", callback_data=f"std1_pl_{p1['Nome']}"))
        bot.edit_message_text(f"📊 *Scegli il SECONDO GIOCATORE ({sq2} - {ROLE_ICONS[ruolo_p1]} {ruolo_p1}):*", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data.startswith("std2_pl_"):
        p2_nome = call.data.replace("std2_pl_", "")
        p1 = session.get('compare_p1')
        p2 = df[df['Nome'] == p2_nome].iloc[0].to_dict()
        
        text = (
            f"📊 *CONFRONTO DIRETTO:*\n\n"
            f"👤 *{p1['Nome'].upper()}* vs 👤 *{p2['Nome'].upper()}*\n"
            f"───────────────────────────\n"
            f"📌 Ruolo: `{p1.get('R','-')}` vs `{p2.get('R','-')}`\n"
            f"👕 Squadra: `{p1.get('Squadra','-')}` vs `{p2.get('Squadra','-')}`\n"
            f"💰 Quotazione: `{p1.get('Qt.A','-')}` vs `{p2.get('Qt.A','-')}` cr.\n"
            f"⭐ FVM: `{p1.get('FVM','-')}` vs `{p2.get('FVM','-')}` cr.\n"
        )
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton(f"⚡ Compra {p1['Nome']}", callback_data=f"buy_{p1['Nome']}"),
            InlineKeyboardButton(f"⚡ Compra {p2['Nome']}", callback_data=f"buy_{p2['Nome']}")
        )
        markup.add(InlineKeyboardButton("🔄 Nuovo Confronto", callback_data="menu_studio_start"), InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text(text, chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "menu_formazione":
        text = "⚽ *SCHIERA FORMAZIONE*\nFunzionalità di modulo e formazione in caricamento."
        markup = InlineKeyboardMarkup().add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text(text, chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "menu_svincola":
        rosa = session.get('rosa', [])
        markup = InlineKeyboardMarkup(row_width=1)
        if not rosa:
            testo = "✂️ *NESSUN GIOCATORE IN ROSA DA SVINCOLARE*"
        else:
            testo = "✂️ *SELEZIONA IL GIOCATORE DA SVINCOLARE:*"
            for p in rosa:
                markup.add(InlineKeyboardButton(f"❌ Svincola {p['nome']} ({p['prezzo']} cr.)", callback_data=f"svincola_do_{p['nome']}"))
        markup.add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text(testo, chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data.startswith("svincola_do_"):
        p_name = call.data.replace("svincola_do_", "")
        rosa = session.get('rosa', [])
        for p in list(rosa):
            if p['nome'] == p_name:
                session['budget'] += p['prezzo']
                rosa.remove(p)
                break
        send_dashboard(chat_id, user_id, call.message.message_id)

    # --- CLICK SULLA CARD DEL GIOCATORE ---
    elif call.data.startswith("sq_pl_"):
        player_name = call.data.replace("sq_pl_", "")
        if df is None: return
        send_player_card_view(chat_id, player_name, call.message.message_id, df, session)

    elif call.data.startswith("buy_"):
        player_name = call.data.replace("buy_", "")
        msg = bot.send_message(chat_id, f"💰 Crediti spesi per *{player_name}*?:", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_buy_price, player_name, user_id)

    elif call.data.startswith("wl_toggle_"):
        player_name = call.data.replace("wl_toggle_", "")
        if 'wishlist' not in session: session['wishlist'] = []
        if player_name in session['wishlist']: session['wishlist'].remove(player_name)
        else: session['wishlist'].append(player_name)
        send_dashboard(chat_id, user_id, call.message.message_id)

    elif call.data == "menu_wishlist":
        wishlist = session.get('wishlist', [])
        markup = InlineKeyboardMarkup(row_width=1)
        if not wishlist: testo = "⭐ *WISHLIST VUOTA*"
        else:
            testo = "⭐ *LA TUA WISHLIST:*\n"
            for nome in wishlist: markup.add(InlineKeyboardButton(f"🔍 {nome}", callback_data=f"sq_pl_{nome}"))
        markup.add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text(testo, chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(content_types=['document'])
def handle_document(message):
    chat_id = message.chat.id
    fname = message.document.file_name
    if not (fname.endswith('.csv') or fname.endswith('.xlsx')):
        bot.reply_to(message, "❌ Invia solo file `.csv` o `.xlsx`!", parse_mode="Markdown")
        return
    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        save_name = "Lista-FantaAsta-Fantacalcio.csv" if fname.endswith('.csv') else "listone.xlsx"
        with open(save_name, 'wb') as new_file:
            new_file.write(downloaded_file)
        load_data(force_reload=True)
        bot.reply_to(message, "✅ *DATABASE AGGIORNATO CON SUCCESSO!*", parse_mode="Markdown")
    except Exception as e:
        bot.send_message(chat_id, f"❌ Errore caricamento: {str(e)}")

# ==========================================
# AVVIO BOT
# ==========================================
if __name__ == '__main__':
    try: 
        bot.remove_webhook()
    except Exception:
        pass

    print("🚀 Bot avviato e in ascolto!")
    bot.infinity_polling(timeout=10, long_polling_timeout=5, skip_pending=True)
