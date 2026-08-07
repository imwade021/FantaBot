import os
import io
import re
import pandas as pd
import numpy as np
import requests
from bs4 import BeautifulSoup
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = os.getenv("BOT_TOKEN", "8969898580:AAHxI0_LK57bhCTP_TNYLKubhEU3a0yEg0Y")
bot = telebot.TeleBot(TOKEN)

TARGET_ROSTER = {'P': 3, 'D': 8, 'C': 8, 'A': 6}
ROLE_ICONS = {'P': '🧤', 'D': '🛡️', 'C': '⚙️', 'A': '🎯'}
TEAM_COLORS = {
    'Atalanta': '🔵⚫', 'Bologna': '🔴🔵', 'Cagliari': '🔴🔵', 'Como': '🔵⚪',
    'Empoli': '🔵⚪', 'Fiorentina': '💜', 'Genoa': '🔴🔵', 'Inter': '🔵⚫',
    'Juventus': '⚪⚫', 'Lazio': '🩵⚪', 'Lecce': '🟡🔴', 'Milan': '🔴⚫',
    'Monza': '🔴⚪', 'Napoli': '🔵⚪', 'Parma': '🟡🔵', 'Roma': '🟡🔴',
    'Torino': '🟤⚪', 'Udinese': '⚪⚫', 'Venezia': '🟠🟢', 'Verona': '🟡🔵'
}

BEST_PAIRS = {
    'Inter': ['Venezia', 'Napoli', 'Lecce'], 'Juventus': ['Torino', 'Empoli', 'Parma'],
    'Milan': ['Monza', 'Como', 'Genoa'], 'Atalanta': ['Bologna', 'Udinese', 'Verona'],
    'Napoli': ['Inter', 'Roma', 'Fiorentina'], 'Roma': ['Lazio', 'Napoli'],
    'Lazio': ['Roma', 'Milan'], 'Fiorentina': ['Empoli', 'Bologna', 'Napoli'],
    'Torino': ['Juventus', 'Genoa', 'Como'], 'Bologna': ['Atalanta', 'Fiorentina']
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

DATA_CACHE = None
def load_data(force_reload=False):
    global DATA_CACHE
    if DATA_CACHE is None or force_reload:
        if os.path.exists("listone.xlsx"): 
            DATA_CACHE = pd.read_excel("listone.xlsx", header=1, engine='openpyxl')
        else: 
            DATA_CACHE = None
    return DATA_CACHE
load_data()

user_sessions = {}
def get_session(user_id):
    if user_id not in user_sessions: 
        user_sessions[user_id] = {'budget': 500, 'rosa': [], 'selected_for_compare': [], 'wishlist': [], 'scartati': []}
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

def fetch_online_gems():
    gems_found = set()
    keywords = [r'scommessa', r'rivelazione', r'low-cost', r'crack', r'sorpresa', r'titolare a 1', r'prospetto', r'pupillo']
    urls = [
        "https://www.sosfanta.com/guida-asta-fantacalcio/",
        "https://www.fantacalcio.it/consigli-fantacalcio"
    ]
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    
    for url in urls:
        try:
            resp = requests.get(url, headers=headers, timeout=4)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'html.parser')
                text = soup.get_text()
                for line in text.split('\n'):
                    if any(re.search(kw, line, re.IGNORECASE) for kw in keywords):
                        names = re.findall(r'\b[A-Z][a-z]{2,}(?:\s[A-Z][a-z]{2,})?\b', line)
                        gems_found.update(names)
        except Exception:
            continue
    return list(gems_found)

@bot.message_handler(commands=['start', 'menu'])
def cmd_start(m): 
    send_dashboard(m.chat.id, m.from_user.id)

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    session = get_session(user_id)
    df = load_data()

    if call.data == "clear_screen":
        safe_answer_callback(call.id, "🧹 Pulizia in corso...")
        curr_id = call.message.message_id
        for i in range(curr_id, max(0, curr_id - 80), -1):
            try: bot.delete_message(chat_id, i)
            except Exception: pass
        send_dashboard(chat_id, user_id)

    elif call.data == "go_home": 
        safe_answer_callback(call.id)
        send_dashboard(chat_id, user_id, call.message.message_id)

    elif call.data in ["menu_scommessa", "pesca_card_scommessa"]:
        nomi_in_rosa = [p['nome'] for p in session['rosa']]
        scartati = session.get('scartati', [])
        
        df_liberi = df[(~df['Nome'].isin(nomi_in_rosa)) & (~df['Nome'].isin(scartati))].copy()
        online_gems = fetch_online_gems()
        all_gems = set([g.lower() for g in online_gems] + DATABASE_SCOMMESSE_PURE)
        
        df_scommesse = df_liberi[df_liberi['Nome'].apply(lambda x: any(g in str(x).lower() for g in all_gems))].copy()

        if call.data == "pesca_card_scommessa":
            safe_answer_callback(call.id, "🃏 Generazione Card con Foto...")
            if df_scommesse.empty:
                safe_answer_callback(call.id, "❌ Nessuna scommessa disponibile!", show_alert=True)
                return
                
            scommessa = df_scommesse.sample(n=1).iloc[0]
            nome_p = str(scommessa['Nome']).upper()
            sq_p = str(scommessa.get('Squadra', '-'))
            r_p = str(scommessa.get('R', 'C'))
            fvm_p = str(scommessa.get('FVM', scommessa.get('Qt.A', '1-3')))
            slot_p = str(scommessa.get('Slot', 'Scommessa / Ultimo Slot'))
            
            # Recupero ID per la foto ufficiale Fantacalcio
            id_player = str(scommessa.get('Id', scommessa.get('ID', '')))
            photo_url = f"https://s3.eu-west-1.amazonaws.com/fantacalcio.it/calciatori/2026/200x200/{id_player}.png" if id_player and id_player.isdigit() else None

            testo_card = (
                f"🎴 *SPECIAL CARD: SCOMMESSA 2026/27*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 *{nome_p}*\n"
                f"🛡️ Squadra: {get_team_icon(sq_p)} *{sq_p}*\n"
                f"📌 Ruolo: `{ROLE_ICONS.get(r_p, '')} {r_p}`\n"
                f"⭐ Slot Consigliato: `{slot_p}`\n"
                f"💰 Costo FVM: `{fvm_p}` cr.\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🔥 *SENTENZA ORACOLO:* _\"Chiamalo subito a 1 credito prima che gli altri lo notino!\"_"
            )

            markup = InlineKeyboardMarkup(row_width=2)
            markup.add(
                InlineKeyboardButton("⚡ Compra a 1 cr", callback_data=f"buy_{scommessa['Nome']}"),
                InlineKeyboardButton("🎲 Rilancia Card", callback_data="pesca_card_scommessa")
            )
            markup.add(InlineKeyboardButton("📋 Torna alla Lista", callback_data="menu_scommessa"), InlineKeyboardButton("🏠 Home", callback_data="go_home"))
            
            try:
                bot.delete_message(chat_id, call.message.message_id)
            except Exception:
                pass

            if photo_url:
                try:
                    bot.send_photo(chat_id, photo_url, caption=testo_card, parse_mode="Markdown", reply_markup=markup)
                    return
                except Exception:
                    pass

            # Fallback immediato se la foto non è trovata
            bot.send_message(chat_id, testo_card, parse_mode="Markdown", reply_markup=markup)

        else:
            safe_answer_callback(call.id, "🔎 Filtraggio scommesse reali...")
            testo = "🎲 *LE VERE SCOMMESSE 2026/27*\nSolo profili ad alto potenziale raggruppati per ruolo:\n\n"
            markup = InlineKeyboardMarkup(row_width=1)
            markup.add(InlineKeyboardButton("🎴 Pesca una Card Visiva HD", callback_data="pesca_card_scommessa"))
            
            ruoli_order = [('P', '🧤 PORTIERI'), ('D', '🛡️ DIFENSORI'), ('C', '⚙️ CENTROCAMPISTI'), ('A', '🎯 ATTACCANTI')]
            trovato = False
            for r_code, r_title in ruoli_order:
                sub_r = df_scommesse[df_scommesse['R'] == r_code].head(4)
                if not sub_r.empty:
                    trovato = True
                    testo += f"\n*{r_title}*\n"
                    for _, row in sub_r.iterrows():
                        fvm_val = row.get('FVM', row.get('Qt.A', '1-3'))
                        testo += f"🔹 *{row['Nome']}* ({row.get('Squadra','-')}) ─ FVM: `{fvm_val}`\n"
                        markup.add(InlineKeyboardButton(f"🔍 Info {row['Nome']}", callback_data=f"sq_pl_{row['Nome']}"))
                        
            if not trovato:
                testo += "_Tutte le scommesse principali sono state già prese o scartate!_"
                
            markup.add(InlineKeyboardButton("🏠 Torna alla Home", callback_data="go_home"))
            try:
                bot.edit_message_text(testo, chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
            except Exception:
                bot.send_message(chat_id, testo, parse_mode="Markdown", reply_markup=markup)

if __name__ == '__main__':
    try: bot.remove_webhook() 
    except Exception: pass
    bot.infinity_polling(timeout=10, long_polling_timeout=5, skip_pending=True)
