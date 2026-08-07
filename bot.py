import os
import io
import re
import pandas as pd
import numpy as np
import telebot
import requests
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from PIL import Image, ImageDraw, ImageFont

# ==========================================
# CONFIGURAZIONE INIZIALE & TOKEN
# ==========================================
TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise ValueError("⚠️ ERRORE: La variabile d'ambiente BOT_TOKEN non è impostata su Render!")

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

# ==========================================
# FUNZIONI UTILITY & DOWNLOAD IMMAGINI
# ==========================================
def safe_answer_callback(call_id, text=None, show_alert=False):
    try:
        bot.answer_callback_query(call_id, text=text, show_alert=show_alert)
    except Exception:
        pass

def get_team_icon(squadra): 
    return TEAM_COLORS.get(str(squadra).strip(), '🛡️')

def get_player_photo_bytes(row):
    """Scarica la foto usando i link esatti scoperti dal file Lista-FantaAsta-Fantacalcio."""
    id_val = None
    photo_url = None
    
    # 1. Se nel row c'è un link o una colonna URL
    for col in row.index:
        val_str = str(row[col])
        if 'content.fantacalcio.it' in val_str:
            photo_url = val_str
            break
        col_clean = str(col).strip().lower().replace('.', '')
        if col_clean in ['id', 'cod', 'codice', '4431']:
            val = val_str.split('.')[0].strip()
            if val.isdigit():
                id_val = val

    # 2. Se non ha il link completo ma ha l'ID, usa l'URL delle card "campioncini"
    if not photo_url and id_val:
        photo_url = f"https://content.fantacalcio.it/web/campioncini/21/card/{id_val}.png"

    nome_giocatore = str(row.get('Nome', row.iloc[1] if len(row) > 1 else 'Giocatore')).strip()

    if photo_url:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.fantacalcio.it/"
        }
        try:
            print(f"🤖 Download foto da URL esatto: {photo_url}")
            response = requests.get(photo_url, headers=headers, timeout=4)
            print(f"📡 Risposta server Fantacalcio: {response.status_code}")
            if response.status_code == 200 and len(response.content) > 500:
                file_bytes = io.BytesIO(response.content)
                file_bytes.name = 'player_photo.png'
                return file_bytes
        except Exception as e:
            print(f"⚠️ Download foto fallito: {e}")

    return None

def crea_carta_fc(nome_giocatore, ruolo, fvm, photo_bytes):
    """Crea la carta grafica del giocatore incollando la foto vera al centro."""
    try:
        if os.path.exists("template_card.png"):
            sfondo = Image.open("template_card.png").convert("RGBA")
            sfondo = sfondo.resize((500, 750))
        else:
            sfondo = Image.new("RGBA", (500, 750), (20, 20, 35, 255))
            
        draw = ImageDraw.Draw(sfondo)

        # Incolla la foto del giocatore se disponibile
        if photo_bytes:
            try:
                photo_bytes.seek(0)
                faccia = Image.open(photo_bytes).convert("RGBA")
                faccia = faccia.resize((260, 260))
                sfondo.paste(faccia, (120, 160), faccia)
                print("📸 Foto reale incollata con successo!")
            except Exception as e_img:
                print(f"⚠️ Errore incollaggio immagine: {e_img}")

        # Font per testi
        try:
            font_nome = ImageFont.truetype("font.ttf", 45)
            font_overall = ImageFont.truetype("font.ttf", 65)
            font_ruolo = ImageFont.truetype("font.ttf", 45)
        except IOError:
            font_nome = ImageFont.load_default()
            font_overall = ImageFont.load_default()
            font_ruolo = ImageFont.load_default()

        # Disegna FVM e Ruolo in alto a sinistra
        draw.text((75, 125), str(fvm), fill="#1a1a1a", font=font_overall)
        draw.text((80, 200), str(ruolo), fill="#1a1a1a", font=font_ruolo)

        # Disegna Nome centrato in basso
        nome_str = str(nome_giocatore).upper()
        try:
            text_width = draw.textlength(nome_str, font=font_nome)
        except AttributeError:
            text_width = draw.textsize(nome_str, font=font_nome)[0] 
            
        x_nome = int((500 - text_width) / 2)
        draw.text((x_nome, 460), nome_str, fill="#1a1a1a", font=font_nome)

        img_byte_arr = io.BytesIO()
        sfondo.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)
        img_byte_arr.name = 'fc_card.png'
        return img_byte_arr

    except Exception as e:
        print(f"❌ Errore generazione carta: {e}")
        return None

# ==========================================
# GESTIONE DATABASE & SESSIONI
# ==========================================
DATA_CACHE = None
def load_data(force_reload=False):
    global DATA_CACHE
    if DATA_CACHE is None or force_reload:
        # Cerca prima il CSV di FantaAsta se disponibile, altrimenti listone.xlsx
        if os.path.exists("Lista-FantaAsta-Fantacalcio.csv"):
            try:
                DATA_CACHE = pd.read_csv("Lista-FantaAsta-Fantacalcio.csv", header=None)
                # Assegna nomi colonne leggibili
                DATA_CACHE.columns = ['Id', 'Nome_Breve', 'Nome', 'R', 'Ruolo_Esteso', 'Qt.A', 'Qt.I', 'Qt.M', 'Diff.M', 'Squadra', 'FVM', 'FVM.M', 'Piede', 'Nazionalita', 'DataNascita', 'PhotoURL', 'Extra1', 'Extra2', 'Extra3']
                print("✅ Caricato file CSV Lista-FantaAsta-Fantacalcio.csv con successso!")
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

# ==========================================
# HANDLERS MESSAGGI
# ==========================================
@bot.message_handler(commands=['start', 'menu'])
def cmd_start(m): 
    send_dashboard(m.chat.id, m.from_user.id)

@bot.message_handler(func=lambda m: not m.text.startswith('/') and not m.text.startswith('+') and not m.text.isdigit())
def search_player(message):
    query = message.text.strip().lower()
    df = load_data()
    if df is None or len(query) < 2: return
    
    matches = df[df['Nome'].str.lower().str.contains(query, na=False)]
    if matches.empty and 'Nome_Breve' in df.columns:
        matches = df[df['Nome_Breve'].str.lower().str.contains(query, na=False)]
        
    if matches.empty: return bot.reply_to(message, "❌ Nessun giocatore trovato.")
        
    markup = InlineKeyboardMarkup(row_width=1)
    for _, row in matches.head(10).iterrows():
        markup.add(InlineKeyboardButton(f"{ROLE_ICONS.get(row.get('R','C'),'')} {row['Nome']} ({row.get('Squadra','-')})", callback_data=f"sq_pl_{row['Nome']}"))
    bot.reply_to(message, f"🔍 Risultati per *{query}*:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    safe_answer_callback(call.id)
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    session = get_session(user_id)
    df = load_data()

    if call.data == "go_home": 
        send_dashboard(chat_id, user_id, call.message.message_id)

    elif call.data.startswith("sq_pl_"):
        player_name = call.data.replace("sq_pl_", "")
        
        if df is None:
            bot.send_message(chat_id, "❌ Nessun database caricato. Invia il file CSV in chat!")
            return

        p_data = df[df['Nome'] == player_name].iloc[0]
        sq_name = p_data.get('Squadra', '-')
        
        # Generazione Carta FC
        photo_bytes = get_player_photo_bytes(p_data)
        final_card = crea_carta_fc(player_name, p_data.get('R', '-'), p_data.get('FVM', '-'), photo_bytes)
        
        info_text = (
            f"*{player_name.upper()}* ({get_team_icon(sq_name)} {sq_name})\n"
            f"───────────────────────────\n"
            f"📌 Ruolo: `{p_data.get('R', '-')}`  │  ⭐ Slot: `{p_data.get('Slot', '-')}`\n"
            f"📈 Fantamedia: `{p_data.get('FM', '-')}`\n"
            f"💰 Quotazione: `{p_data.get('Qt.A', '-')}` cr.  │  FVM: `{p_data.get('FVM', '-')}` cr.\n"
        )
        
        in_wl = player_name in session.get('wishlist', [])
        wl_text = "❌ Rimuovi Wishlist" if in_wl else "⭐ Aggiungi Wishlist"
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(InlineKeyboardButton("⚡ Compra", callback_data=f"buy_{player_name}"), InlineKeyboardButton(wl_text, callback_data=f"wl_toggle_{player_name}"))
        markup.add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        
        try: bot.delete_message(chat_id, call.message.message_id)
        except Exception: pass

        if final_card:
            try:
                bot.send_photo(chat_id, final_card, caption=info_text, parse_mode="Markdown", reply_markup=markup)
                return
            except Exception as e:
                print(f"❌ Errore invio foto: {e}")

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
        bot.reply_to(message, "✅ *DATABASE CARICATO E AGGIORNATO CON SUCCESSO!*", parse_mode="Markdown")
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
