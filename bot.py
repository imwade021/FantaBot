import os
import pandas as pd
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# TOKEN
TOKEN = os.getenv("BOT_TOKEN", "8969898580:AAHxI0_LK57bhCTP_TNYLKubhEU3a0yEg0Y")
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

DATA_CACHE = None
def load_data(force_reload=False):
    global DATA_CACHE
    if DATA_CACHE is None or force_reload:
        if os.path.exists("listone.xlsx"): 
            for row_h in range(0, 5):
                try:
                    df_test = pd.read_excel("listone.xlsx", header=row_h, engine='openpyxl')
                    cols = [str(c).strip().lower() for c in df_test.columns]
                    if 'nome' in cols or any('id' in c for c in cols):
                        df_test.columns = [str(c).strip() for c in df_test.columns]
                        DATA_CACHE = df_test
                        break
                except Exception:
                    continue
        else: 
            DATA_CACHE = None
    return DATA_CACHE

load_data()

user_sessions = {}
def get_session(user_id):
    if user_id not in user_sessions: 
        user_sessions[user_id] = {'budget': 500, 'rosa': [], 'selected_for_compare': [], 'wishlist': [], 'scartati': []}
    return user_sessions[user_id]

def get_team_icon(squadra): 
    return TEAM_COLORS.get(str(squadra).strip(), '🛡️')

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
    
    text = (
        " *FANTABOT PRO DASHBOARD*\n"
        "───────────────────────────\n"
        "💳 *BILANCIO ASTA*\n"
        f"• Budget Rimanente: `{session['budget']}` cr.\n"
        f"• Giocatori Presi: `{25 - stats['slot_liberi']}/25`\n"
        f"• *Max Bid Sicuro:* `{stats['max_bid']}` cr.\n\n"
        "📊 *COPERTURA ROSTER*\n"
        f"🧤 Portieri: `{c['P']}/3`\n"
        f"🛡️ Difensori: `{c['D']}/8`\n"
        f"⚙️ Centrocampisti: `{c['C']}/8`\n"
        f"🎯 Attaccanti: `{c['A']}/6`\n"
        "───────────────────────────\n"
        "💡 _Usa il menu sotto per gestire l'asta!_\n"
    )
    if message_id:
        try:
            bot.edit_message_text(text, chat_id, message_id, parse_mode="Markdown", reply_markup=main_menu_keyboard())
            return
        except Exception:
            pass
    bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=main_menu_keyboard())

@bot.message_handler(commands=['start', 'menu'])
def cmd_start(m): 
    send_dashboard(m.chat.id, m.from_user.id)

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    # Rispondi SUBITO a Telegram per sbloccare la rotellina "Carico..."
    try:
        bot.answer_callback_query(call.id)
    except Exception:
        pass

    user_id = call.from_user.id
    chat_id = call.message.chat.id
    session = get_session(user_id)
    df = load_data()

    if call.data == "go_home": 
        send_dashboard(chat_id, user_id, call.message.message_id)

    elif call.data == "reload_excel":
        load_data(force_reload=True)
        bot.send_message(chat_id, "⚡ *Dati sincronizzati dall'Excel!*", parse_mode="Markdown")

    elif call.data in ["menu_scommessa", "pesca_card_scommessa"]:
        if df is None:
            bot.send_message(chat_id, "❌ *Carica prima il file listone.xlsx!*", parse_mode="Markdown")
            return

        nomi_in_rosa = [p['nome'] for p in session['rosa']]
        scartati = session.get('scartati', [])
        
        df_liberi = df[(~df['Nome'].isin(nomi_in_rosa)) & (~df['Nome'].isin(scartati))].copy()
        df_scommesse = df_liberi[df_liberi['Nome'].apply(lambda x: any(g in str(x).lower() for g in DATABASE_SCOMMESSE_PURE))].copy()

        if call.data == "pesca_card_scommessa":
            if df_scommesse.empty:
                bot.send_message(chat_id, "❌ *Nessuna scommessa rimasta disponibile!*", parse_mode="Markdown")
                return
                
            scommessa = df_scommesse.sample(n=1).iloc[0]
            nome_p = str(scommessa['Nome']).upper()
            sq_p = str(scommessa.get('Squadra', '-'))
            r_p = str(scommessa.get('R', 'C'))
            fvm_p = str(scommessa.get('FVM', scommessa.get('Qt.A', '1-3')))
            
            id_val = None
            for col in scommessa.index:
                if str(col).strip().lower() in ['id', 'cod', 'codice']:
                    val_str = str(scommessa[col]).split('.')[0].strip()
                    if val_str.isdigit():
                        id_val = val_str
                        break
            
            photo_url = f"https://content.fantacalcio.it/web/immagini/cadres/{id_val}.png" if id_val else None

            testo_card = (
                f"🎴 *SPECIAL CARD: SCOMMESSA 2026/27*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 *{nome_p}*\n"
                f"🛡️ Squadra: {get_team_icon(sq_p)} *{sq_p}*\n"
                f"📌 Ruolo: `{ROLE_ICONS.get(r_p, '')} {r_p}`\n"
                f"💰 Costo FVM: `{fvm_p}` cr.\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🔥 *SENTENZA:* _Puntalo a 1 credito prima degli altri!_"
            )

            markup = InlineKeyboardMarkup(row_width=2)
            markup.add(
                InlineKeyboardButton("🎲 Rilancia Card", callback_data="pesca_card_scommessa"),
                InlineKeyboardButton("🏠 Home", callback_data="go_home")
            )

            if photo_url:
                try:
                    bot.send_photo(chat_id, photo_url, caption=testo_card, parse_mode="Markdown", reply_markup=markup)
                    return
                except Exception:
                    pass

            bot.send_message(chat_id, testo_card, parse_mode="Markdown", reply_markup=markup)

        else:
            testo = "🎲 *LE VERE SCOMMESSE*\nSeleziona un'opzione:\n"
            markup = InlineKeyboardMarkup(row_width=1)
            markup.add(InlineKeyboardButton("🎴 Pesca una Card Scommessa", callback_data="pesca_card_scommessa"))
            markup.add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
            
            try:
                bot.edit_message_text(testo, chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
            except Exception:
                bot.send_message(chat_id, testo, parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(content_types=['document'])
def handle_document(message):
    chat_id = message.chat.id
    if not message.document.file_name.endswith('.xlsx'):
        bot.reply_to(message, "❌ Invia solo file in formato `.xlsx`!", parse_mode="Markdown")
        return
    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        with open("listone.xlsx", 'wb') as new_file:
            new_file.write(downloaded_file)
        load_data(force_reload=True)
        bot.reply_to(message, "✅ *DATABASE AGGIORNATO CON SUCCESSO!*", parse_mode="Markdown")
    except Exception as e:
        bot.send_message(chat_id, f"❌ Errore durante l'aggiornamento: {str(e)}")

if __name__ == '__main__':
    try:
        bot.remove_webhook()
    except Exception:
        pass
    bot.infinity_polling(timeout=10, long_polling_timeout=5, skip_pending=True)
