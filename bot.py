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
        user_sessions[user_id] = {'budget': 500, 'rosa': [], 'wishlist': []}
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

def main_menu_keyboard():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📋 La mia Rosa", callback_data="menu_rosa"),
        InlineKeyboardButton("⭐ Wishlist", callback_data="menu_wishlist")
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
    
    text = (
        " *FANTABOT PRO DASHBOARD*\n"
        "───────────────────────────\n"
        "💳 *BILANCIO ASTA*\n"
        f"• Budget Rimanente: `{session['budget']}` cr.\n"
        f"• Giocatori Presi: `{25 - stats['slot_liberi']}/25`\n"
        f"• *Max Bid Sicuro:* `{stats['max_bid']}` cr.\n\n"
        "💡 _Cerca nome o scrivi `+ nome prezzo` per comprare al volo!_\n"
    )
    if message_id:
        try: bot.edit_message_text(text, chat_id, message_id, parse_mode="Markdown", reply_markup=main_menu_keyboard())
        except Exception: bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=main_menu_keyboard())
    else: 
        bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=main_menu_keyboard())

# ==========================================
# HANDLERS MESSAGGI & RICERCA
# ==========================================
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

        # Scarica l'immagine dal server Fantacalcio e la invia direttamente a Telegram
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

    print("🚀 Bot in ascolto con card ufficiale Fantacalcio!")
    bot.infinity_polling(timeout=10, long_polling_timeout=5, skip_pending=True)
