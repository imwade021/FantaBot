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
    'belahyane', 'tengstedt', 'da cunha', 'moro', 'chaka traore', 'pisilli', 'ekhator', 
    'alisson santos', 'solet', 'idzes', 'mangas', 'milla', 'kike perez', 'ndour', 
    'viti', 'goglichidze', 'alajbegovic', 'nico paz', 'suslov', 'mosquera', 'tchaouna',
    'camarda', 'vitinha'
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
        user_sessions[user_id] = {'budget': 500, 'rosa': [], 'wishlist': [], 'scartati': []}
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
        InlineKeyboardButton("🏆 Top Liberi", callback_data="menu_top"),
        InlineKeyboardButton("⚽ Formazione", callback_data="menu_formazione")
    )
    markup.add(
        InlineKeyboardButton("🚨 Panic Button", callback_data="menu_panic"),
        InlineKeyboardButton("⭐ Wishlist", callback_data="menu_wishlist")
    )
    markup.add(
        InlineKeyboardButton("💎 Gemme Nascoste", callback_data="menu_gemme"),
        InlineKeyboardButton("🎲 Scommessa", callback_data="menu_scommessa")
    )
    markup.add(
        InlineKeyboardButton("✂️ Svincola", callback_data="menu_svincola"),
        InlineKeyboardButton("📊 Area Studio", callback_data="menu_studio")
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
    
    spesa_tot = sum(p['prezzo'] for p in session['rosa'])
    fvm_tot = sum(p.get('fvm', 0) for p in session['rosa'])
    termometro = "⚖️ _Equilibrata_"
    if spesa_tot > 0 and fvm_tot > 0:
        diff_perc = ((spesa_tot - fvm_tot) / fvm_tot) * 100
        if diff_perc > 15: termometro = "🔥 _Asta Calda_ (Stai pagando troppo!)"
        elif diff_perc < -10: termometro = "❄️ _Asta Fredda_ (Ottimi affari!)"
    
    text = (
        " *FANTABOT PRO DASHBOARD*\n"
        "───────────────────────────\n"
        "💳 *BILANCIO ASTA*\n"
        f"• Budget Rimanente: `{session['budget']}` cr.\n"
        f"• Giocatori Presi: `{25 - stats['slot_liberi']}/25`\n"
        f"• *Max Bid Sicuro:* `{stats['max_bid']}` cr.\n"
        f"• Termometro Asta: {termometro}\n\n"
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
        send_dashboard(chat_id, user_id, call.message.message_id)

    elif call.data == "reload_excel": 
        load_data(force_reload=True)
        bot.send_message(chat_id, "⚡ *Dati sincronizzati con successo!*", parse_mode="Markdown")

    elif call.data == "reset_confirm":
        user_sessions[user_id] = {'budget': 500, 'rosa': [], 'wishlist': session.get('wishlist', []), 'scartati': []}
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

    elif call.data == "sq_start":
        if df is None:
            bot.send_message(chat_id, "❌ Database non caricato su Render!")
            return
        bot.edit_message_text("👕 *ESPLORA SQUADRE*", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=menu_seleziona_squadra(df, "sq"))

    elif call.data.startswith("sq_sq_"):
        bot.edit_message_text("Scegli il ruolo:", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=menu_seleziona_ruolo(call.data.replace("sq_sq_", ""), "sq"))

    elif call.data.startswith("sq_ru_"):
        _, _, sq, ru = call.data.split("_")
        bot.edit_message_text(f"Giocatori ({sq} - {ru}):", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=menu_seleziona_giocatore(df, sq, ru, "sq", user_id))

    elif call.data == "menu_top":
        if df is None: return
        top_players = df.sort_values(by='FVM', ascending=False).head(10)
        markup = InlineKeyboardMarkup(row_width=1)
        for _, row in top_players.iterrows():
            markup.add(InlineKeyboardButton(f"{ROLE_ICONS.get(row.get('R','C'),'')} {row['Nome']} ({row.get('Squadra','-')}) ─ FVM:{row.get('FVM','-')}", callback_data=f"sq_pl_{row['Nome']}"))
        markup.add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text("🏆 *TOP GIOCATORI LIBERI:*", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "menu_gemme":
        if df is None: return
        gemme = df[(df['FVM'] < 15) & (df['FVM'] > 2)].head(10)
        markup = InlineKeyboardMarkup(row_width=1)
        for _, row in gemme.iterrows():
            markup.add(InlineKeyboardButton(f"💎 {row['Nome']} ({row.get('Squadra','-')}) ─ FVM:{row.get('FVM','-')}", callback_data=f"sq_pl_{row['Nome']}"))
        markup.add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text("💎 *GEMME NASCOSTE (Low Cost):*", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "menu_scommessa":
        if df is None: return
        scommessa = df[df['Nome'].str.lower().isin(DATABASE_SCOMMESSE_PURE)].head(10)
        markup = InlineKeyboardMarkup(row_width=1)
        if scommessa.empty:
            scommessa = df.sample(5)
        for _, row in scommessa.iterrows():
            markup.add(InlineKeyboardButton(f"🎲 {row['Nome']} ({row.get('Squadra','-')})", callback_data=f"sq_pl_{row['Nome']}"))
        markup.add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text("🎲 *SCOMMESSE CONSIGLIATE:*", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "menu_panic":
        text = (
            "🚨 *PANIC BUTTON - GUIDA RAPIDA*\n"
            "───────────────────────────\n"
            "• Per acquistare al volo scrivi in chat: `+ nome prezzo`\n"
            "  Es: `+ neres 35`\n"
            "• Controlla sempre il Max Bid nella Dashboard per non sforare!"
        )
        markup = InlineKeyboardMarkup().add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text(text, chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "menu_formazione" or call.data == "menu_studio":
        text = "📊 *AREA STUDIO & FORMAZIONE*\nFunzionalità in aggiornamento con le ultime statistiche."
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

    elif call.data.startswith("sq_pl_"):
        player_name = call.data.replace("sq_pl_", "")
        
        if df is None:
            bot.send_message(chat_id, "❌ Database non trovato. Assicurati che il file CSV sia su GitHub!")
            return

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
        markup.add(InlineKeyboardButton("⚡ Compra", callback_data=f"buy_{player_name}"), InlineKeyboardButton(wl_text, callback_data=f"wl_toggle_{player_name}"))
        markup.add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        
        try: bot.delete_message(chat_id, call.message.message_id)
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
            except Exception as e:
                print(f"⚠️ Download foto fallito: {e}")

        bot.send_message(chat_id, info_text, parse_mode="Markdown", reply_markup=markup)

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
