import os
import io
import re
import html
import unicodedata
import urllib.parse
import threading
import pandas as pd
import numpy as np
import telebot
import requests
from bs4 import BeautifulSoup
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
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

# Tenta di importare la libreria per la ricerca web
try:
    from duckduckgo_search import DDGS
    WEB_SEARCH_ENABLED = True
except ImportError:
    WEB_SEARCH_ENABLED = False

# ==========================================
# CONFIGURAZIONE INIZIALE & TOKEN
# ==========================================
TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise ValueError("⚠️ ERRORE: La variabile d'ambiente BOT_TOKEN non è impostata su Render!")

bot = telebot.TeleBot(TOKEN)

# URL RAW GITHUB PER IL DOWNLOAD AUTOMATICO DEL LISTONE
LISTONE_URL = os.getenv("LISTONE_URL", "https://raw.githubusercontent.com/imwade021/fanta-data-bridge/main/Lista-FantaAsta-Fantacalcio.csv")

ROLE_ICONS = {'P': '🧤', 'D': '🛡️', 'C': '⚙️', 'A': '🎯'}
TEAM_COLORS = {
    'Atalanta': '🔵⚫', 'Bologna': '🔴🔵', 'Cagliari': '🔴🔵', 'Como': '🔵⚪',
    'Empoli': '🔵⚪', 'Fiorentina': '💜', 'Frosinone': '🟡🔵', 'Genoa': '🔴🔵', 
    'Inter': '🔵⚫', 'Juventus': '⚪⚫', 'Lazio': '🩵⚪', 'Lecce': '🟡🔴', 
    'Milan': '🔴⚫', 'Monza': '🔴⚪', 'Napoli': '🔵⚪', 'Parma': '🟡🔵', 
    'Roma': '🟡🔴', 'Sassuolo': '🟢⚫', 'Torino': '🟤⚪', 'Udinese': '⚪⚫', 
    'Venezia': '🟠🟢', 'Verona': '🟡🔵'
}

GERARCHIE_RIGORISTI = {
    'Atalanta': {'rigoristi': ['Scamacca', 'Krstovic', 'Samardzic'], 'punizioni': ['De Ketelaere', 'Samardzic', 'Gaetano']},
    'Bologna': {'rigoristi': ['Orsolini', 'Bernardeschi', 'Dovbyk'], 'punizioni': ['Orsolini', 'Bernardeschi', 'Miranda J.']},
    'Cagliari': {'rigoristi': ['Mina', 'Fazzini', 'Borrelli'], 'punizioni': ['Fazzini', 'Winks', 'Mina']},
    'Como': {'rigoristi': ['Da Cunha', 'Douvikas', 'Paz N.'], 'punizioni': ['Paz N.', 'Baturina', 'Da Cunha']},
    'Fiorentina': {'rigoristi': ['Gudmundsson A.', 'Kean', 'Mandragora'], 'punizioni': ['Gudmundsson A.', 'Mastantuono', 'Atta']},
    'Frosinone': {'rigoristi': ['Calò', 'Raimondo', 'Ghedjemis'], 'punizioni': ['Calò', 'Ghedjemis', 'Zerbin']},
    'Genoa': {'rigoristi': ['Colombo', 'Ostigard', 'Vitinha O.'], 'punizioni': ['Baldanzi', 'Martin', 'Vitinha O.']},
    'Inter': {'rigoristi': ['Calhanoglu', 'Zielinski', 'Martinez L.'], 'punizioni': ['Calhanoglu', 'Dimarco', 'Zielinski']},
    'Juventus': {'rigoristi': ['Kolo Muani', 'Yildiz', 'Locatelli'], 'punizioni': ['Locatelli', 'Cambiaso']},
    'Lazio': {'rigoristi': ['Zaccagni', 'Taylor K.', 'Cataldi'], 'punizioni': ['Rovella', 'Zaccagni', 'Cataldi']},
    'Lecce': {'rigoristi': ['Geubbels', 'Stengs', 'Berisha M.'], 'punizioni': ['Pierotti', 'Berisha M.', 'Gandelman']},
    'Milan': {'rigoristi': ['Nkunku', 'Ramos G.', 'Pulisic'], 'punizioni': ['Modric', 'Pulisic', 'Saelemaekers']},
    'Monza': {'rigoristi': ['Pessina', 'Cutrone', 'Petagna'], 'punizioni': ['Pessina', 'Colpani', 'Mota']},
    'Napoli': {'rigoristi': ['De Bruyne', 'Hojlund', 'Politano'], 'punizioni': ['De Bruyne', 'Politano', 'Neres']},
    'Parma': {'rigoristi': ['Pellegrino M.', 'Touré E.', 'Valeri'], 'punizioni': ['Bernabé', 'Nicolussi Caviglia', 'Valeri']},
    'Roma': {'rigoristi': ['Malen', 'Dybala', 'Castro S.'], 'punizioni': ['Dybala', 'Malen', 'Soulé']},
    'Sassuolo': {'rigoristi': ['Berardi', 'Pinamonti', 'Laurienté'], 'punizioni': ['Berardi', 'Laurienté', 'Adzic']},
    'Torino': {'rigoristi': ['Vlasic', 'Kulenovic', 'Simeone'], 'punizioni': ['Vlasic', 'Oristanio', 'Gineitis']},
    'Udinese': {'rigoristi': ['Davis K.', 'Solet', 'Zaniolo'], 'punizioni': ['Zaniolo', 'Ekkelenkamp', 'Unai Gomez']},
    'Venezia': {'rigoristi': ['Adams A.', 'Rrahmani Al.', 'Adorante'], 'punizioni': ['Busio', 'Yeboah J.', 'Perez K.']}
}

DATABASE_SCOMMESSE_PURE = [
    'bernabe', 'fazzini', 'bonny', 'oristanio', 'paz', 'marchwinski', 'castro', 
    'belahyane', 'tengstedt', 'da cunha', 'moro', 'traore', 'pisilli', 'ekhator', 
    'solet', 'idzes', 'mangas', 'milla', 'ndour', 'viti', 'goglichidze', 
    'alajbegovic', 'suslov', 'mosquera', 'tchaouna', 'camarda', 'vitinha', 
    'savona', 'mbangula', 'conceicao', 'dallinga', 'fabbian', 'braine', 'mastantuono'
]

COPPIE_NOTE = {
    'sommer': 'martinez jo.', 'martinez jo.': 'sommer',
    'di gregorio': 'perin', 'perin': 'di gregorio',
    'maignan': 'sportiello', 'sportiello': 'maignan',
    'svilar': 'ryan', 'ryan': 'svilar',
    'dumfries': 'darmian', 'darmian': 'dumfries',
    'dimarco': 'carlos augusto', 'carlos augusto': 'dimarco',
    'kvaratskhelia': 'neres', 'neres': 'kvaratskhelia'
}

INCROCI_PORTIERI = {
    'Inter': ['Venezia', 'Torino', 'Bologna'],
    'Juventus': ['Lazio', 'Empoli', 'Torino'],
    'Milan': ['Torino', 'Lecce', 'Genoa'],
    'Napoli': ['Roma', 'Parma', 'Verona'],
    'Roma': ['Napoli', 'Fiorentina', 'Lazio'],
    'Atalanta': ['Como', 'Empoli', 'Monza'],
    'Lazio': ['Juventus', 'Roma', 'Bologna'],
    'Fiorentina': ['Roma', 'Venezia', 'Como']
}

def normalize_str(s):
    if not isinstance(s, str):
        return ""
    s = unicodedata.normalize('NFKD', s).encode('ASCII', 'ignore').decode('utf-8')
    s = re.sub(r"[^\w\s]", "", s)
    return " ".join(s.lower().split())

def safe_answer_callback(call_id, text=None, show_alert=False):
    try: bot.answer_callback_query(call_id, text=text, show_alert=show_alert)
    except Exception: pass

def get_team_icon(squadra): 
    return TEAM_COLORS.get(str(squadra).strip(), '🛡️')

# ==========================================
# AUTO-DOWNLOADER & GESTIONE DATABASE
# ==========================================
DATA_CACHE = None
STATS_CACHE = None

def auto_download_listone():
    print("🔄 Avvio download automatico del Listone...")
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(LISTONE_URL, headers=headers, timeout=15)
        if res.status_code == 200 and len(res.content) > 100:
            with open("Lista-FantaAsta-Fantacalcio.csv", "wb") as f:
                f.write(res.content)
            print("✅ Listone scaricato con successo!")
            load_data(force_reload=True)
            return True
        else:
            print(f"⚠️ Errore download, status code: {res.status_code}")
            return False
    except Exception as e:
        print(f"❌ Errore auto-download: {e}")
        return False

def load_data(force_reload=False):
    global DATA_CACHE, STATS_CACHE
    if DATA_CACHE is None or force_reload:
        if os.path.exists("Lista-FantaAsta-Fantacalcio.csv"):
            try:
                # Prova prima leggendo con la prima riga come header
                df_temp = pd.read_csv("Lista-FantaAsta-Fantacalcio.csv")
                df_temp.columns = df_temp.columns.str.strip()
                
                # Se la colonna 'Nome' o 'Squadra' manca, riprova senza header
                if 'Nome' not in df_temp.columns or 'Squadra' not in df_temp.columns:
                    df_temp = pd.read_csv("Lista-FantaAsta-Fantacalcio.csv", header=None)
                    cols = ['Id', 'Nome_Breve', 'Nome', 'R', 'Ruolo_Esteso', 'Qt.A', 'Qt.I', 'Qt.M', 'Diff.M', 'Squadra', 'FVM']
                    df_temp.columns = cols + list(range(len(cols), df_temp.shape[1]))
                
                # Pulizia campi
                DATA_CACHE = df_temp
                if 'Nome' in DATA_CACHE.columns: DATA_CACHE['Nome'] = DATA_CACHE['Nome'].astype(str).str.strip()
                if 'Squadra' in DATA_CACHE.columns: DATA_CACHE['Squadra'] = DATA_CACHE['Squadra'].astype(str).str.strip()
                if 'R' in DATA_CACHE.columns: DATA_CACHE['R'] = DATA_CACHE['R'].astype(str).str.strip()
                
                DATA_CACHE['FVM'] = pd.to_numeric(DATA_CACHE['FVM'], errors='coerce').fillna(0)
                print(f"✅ CSV Caricato. Totale Giocatori: {len(DATA_CACHE)}")
            except Exception as e: 
                print(f"⚠️ Errore lettura CSV: {e}")

    if STATS_CACHE is None or force_reload:
        stats_file = None
        for f in os.listdir('.'):
            if 'statistiche' in f.lower() and (f.endswith('.xlsx') or f.endswith('.xls') or f.endswith('.csv')):
                stats_file = f
                break
                
        if stats_file:
            try:
                if stats_file.endswith('.csv'):
                    STATS_CACHE = pd.read_csv(stats_file)
                else:
                    STATS_CACHE = pd.read_excel(stats_file, header=1)
                
                if 'Nome' in STATS_CACHE.columns:
                    STATS_CACHE['Nome_Norm'] = STATS_CACHE['Nome'].apply(normalize_str)
                    print(f"✅ Excel Statistiche caricato!")
            except Exception as e: print(f"⚠️ Errore lettura statistiche: {e}")

    return DATA_CACHE

# Caricamento iniziale
load_data()
try:
    scheduler = BackgroundScheduler()
    scheduler.add_job(auto_download_listone, 'cron', hour=4, minute=0)
    scheduler.start()
except Exception: pass

user_sessions = {}
def get_session(user_id):
    if user_id not in user_sessions: 
        user_sessions[user_id] = {
            'budget': 500, 'rosa': [], 'wishlist': [], 'scartati': [], 
            'compare_p1': None, 'lega_budget_iniziale': 500, 'lega_partecipanti': 8,
            'modificatore_attivo': False, 'fase_asta': None
        }
    return user_sessions[user_id]

def get_roster_stats(session):
    rosa = session['rosa']
    budget = session['budget']
    counts = {'P': 0, 'D': 0, 'C': 0, 'A': 0}
    for p in rosa:
        r = p.get('ruolo', 'C')
        if r in counts: counts[r] += 1
    slot_liberi = max(0, 25 - len(rosa))
    max_bid = max(0, budget - (slot_liberi - 1)) if slot_liberi > 0 else budget
    return {'counts': counts, 'slot_liberi': slot_liberi, 'max_bid': max_bid}

def get_available_players(df, session):
    presi_nomi = [p['nome'] for p in session.get('rosa', [])]
    scartati_nomi = session.get('scartati', [])
    esclusi = set(presi_nomi + scartati_nomi)
    return df[~df['Nome'].isin(esclusi)]

def find_player_in_stats(nome):
    global STATS_CACHE
    if STATS_CACHE is None or STATS_CACHE.empty: return None
    norm_name = normalize_str(nome)
    match = STATS_CACHE[STATS_CACHE['Nome_Norm'] == norm_name]
    if not match.empty: return match.iloc[0]
    match = STATS_CACHE[STATS_CACHE['Nome_Norm'].str.contains(norm_name, regex=False, na=False)]
    if not match.empty: return match.iloc[0]
    return None

def get_macellaio_info(nome):
    row = find_player_in_stats(nome)
    if row is not None:
        try:
            amm, esp, pv = int(row.get('Amm', 0)), int(row.get('Esp', 0)), int(row.get('Pv', 1))
            if (amm >= 6 or esp >= 1) and pv > 5:
                return f"\n🪓 <b>ALLARME MACELLAIO:</b> <code>{amm} Gialli</code>, <code>{esp} Rossi</code>"
            else:
                return f"\n🛡 <b>Disciplinato:</b> <code>{amm} Gialli</code>, <code>{esp} Rossi</code>"
        except Exception: pass
    return "\n🆕 <i>Nuovo Arrivo / Nessuno storico disciplinare</i>"

def get_storico_excel_o_web(nome, squadra=""):
    row = find_player_in_stats(nome)
    if row is not None:
        pv, mv, fm = row.get('Pv', 0), row.get('Mv', 0.0), row.get('Fm', 0.0)
        gf, ass, amm, esp = row.get('Gf', 0), row.get('Ass', 0), row.get('Amm', 0), row.get('Esp', 0)
        return (
            f"📊 <b>STORICO REALE: {html.escape(nome.upper())}</b>\n───────────────────────────\n"
            f"🏟 Pres: <code>{pv}</code> │ 📈 MV: <code>{mv}</code> │ FM: <code>{fm}</code>\n"
            f"⚽ Gol: <code>{gf}</code> │ 🎯 Ass: <code>{ass}</code> │ 🟨 Gialli: <code>{amm}</code>\n"
        )
    query = f'"{nome}" {squadra} statistiche presenze gol assist transfermarkt fantacalcio'
    return f"🆕 <b>NUOVO ARRIVO IN SERIE A: {html.escape(nome.upper())} ({html.escape(squadra)})</b>\n\n{fetch_real_web_data(query, max_results=2)}"

def fetch_real_web_data(query, max_results=2):
    output = []
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}", headers=headers, timeout=8)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            for r in soup.find_all('div', class_='result__body')[:max_results]:
                snippet, title_tag = r.find('a', class_='result__snippet'), r.find('h2', class_='result__title')
                if snippet and title_tag and title_tag.find('a'):
                    link = title_tag.find('a')['href']
                    if link.startswith('//duckduckgo.com/l/?uddg='): link = urllib.parse.unquote(link.split('uddg=')[1].split('&')[0])
                    output.append(f"🔎 <i>{html.escape(snippet.text.strip())}</i>\n🔗 <a href=\"{html.escape(link)}\">Fonte</a>")
    except Exception: pass
    return "\n\n".join(output) if output else "⚠️ Nessun dettaglio rilevante trovato sul web."

def get_cartella_clinica_reale(nome, squadra=""):
    query = f'"{nome}" {squadra} infortunio tempi recupero rientro SOS Fanta'
    return f"🏥 <b>CARTELLA CLINICA: {html.escape(nome.upper())} ({html.escape(squadra)})</b>\n\n{fetch_real_web_data(query, max_results=2)}"

def draw_pitch_image(titolari_by_role, schema="3-4-3"):
    if not PIL_ENABLED: return None
    img_w, img_h = 600, 800
    image = Image.new("RGB", (img_w, img_h), "#2e7d32")
    draw = ImageDraw.Draw(image)
    draw.rectangle([20, 20, img_w - 20, img_h - 20], outline="white", width=3)
    draw.line([20, img_h // 2, img_w - 20, img_h // 2], fill="white", width=2)
    draw.ellipse([img_w // 2 - 60, img_h // 2 - 60, img_w // 2 + 60, img_h // 2 + 60], outline="white", width=2)

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

def main_menu_keyboard(session):
    markup = InlineKeyboardMarkup(row_width=2)
    if session.get('fase_asta'):
        markup.add(InlineKeyboardButton("🔴 RIPRENDI ASTA LIVE", callback_data="asta_resume"))
        markup.add(InlineKeyboardButton("🛑 Termina Asta", callback_data="asta_end"))
    else:
        markup.add(InlineKeyboardButton("🔨 AVVIA ASTA LIVE", callback_data="asta_setup_start"))
        
    markup.add(InlineKeyboardButton("👕 Esplora Squadre", callback_data="sq_start"), InlineKeyboardButton("📋 La mia Rosa", callback_data="menu_rosa"))
    markup.add(InlineKeyboardButton("⚽ Formazione", callback_data="menu_formazione"), InlineKeyboardButton("🎯 Rigoristi", callback_data="menu_rigoristi"))
    markup.add(InlineKeyboardButton("⭐ Wishlist", callback_data="menu_wishlist"), InlineKeyboardButton("🏆 Top Liberi", callback_data="menu_top_start"))
    markup.add(InlineKeyboardButton("⚙️ Impostazioni", callback_data="menu_impostazioni_lega"), InlineKeyboardButton("⚙️ Sistema", callback_data="menu_sistema"))
    return markup

def send_dashboard(chat_id, user_id, message_id=None):
    session = get_session(user_id)
    stats = get_roster_stats(session)
    c, budget, slot, max_bid = stats['counts'], session['budget'], stats['slot_liberi'], stats['max_bid']
    text = (
        "🏆 <b>FANTABOT PRO DASHBOARD</b> 📊\n━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Cassa:</b> <code> {budget} cr. </code>\n🛍️ <b>Slot Liberi:</b> <code> {slot} </code>\n"
        f"🛑 <b>MAX BID:</b> <code> {max_bid} cr. </code>\n\n"
        f"🧤 P: {c['P']}/3  │ 🛡️ D: {c['D']}/8 \n⚙️ C: {c['C']}/8  │ 🎯 A: {c['A']}/6 \n"
        "━━━━━━━━━━━━━━━━━━━━━━\n💡 <i>Cerca un giocatore digitando il nome in chat!</i>"
    )
    if message_id:
        try: bot.edit_message_text(text, chat_id, message_id, parse_mode="HTML", reply_markup=main_menu_keyboard(session))
        except Exception: bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=main_menu_keyboard(session))
    else: bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=main_menu_keyboard(session))

def send_player_card_view(chat_id, player_name, message_id, df, session):
    matches = df[df['Nome'].astype(str).str.strip() == player_name.strip()]
    if matches.empty:
        return bot.send_message(chat_id, "❌ Giocatore non trovato.")
    
    p_data = matches.iloc[0]
    sq_name, ruolo, fvm = str(p_data.get('Squadra', '-')).strip(), str(p_data.get('R', '-')).strip(), p_data.get('FVM', 0)
    
    try: fvm_val = float(str(fvm).replace(',', '.'))
    except ValueError: fvm_val = 0

    lega_bud, lega_part = session.get('lega_budget_iniziale', 500), session.get('lega_partecipanti', 8)
    fair_price = max(1, int((fvm_val * (lega_bud / 1000.0)) * (1 + ((lega_part - 8) * 0.025))))
    
    info_text = (
        f"📋 <b>ANALISI: {html.escape(player_name.upper())}</b> ({get_team_icon(sq_name)} {html.escape(sq_name)})\n━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>Ruolo:</b> <code>{html.escape(ruolo)}</code>\n"
        f"💰 <b>Fair Price:</b> <code>{fair_price} cr.</code>\n"
        f"⚠️ <b>Info:</b> {get_macellaio_info(player_name)}\n━━━━━━━━━━━━━━━━━━━━━━\n"
    )
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("⚡ Compra", callback_data=f"buy_{player_name}"), InlineKeyboardButton("🚫 Scarta", callback_data=f"taken_{player_name}"))
    markup.add(InlineKeyboardButton("📊 Storico Reale", callback_data=f"stats_{player_name}"), InlineKeyboardButton("🏥 Clinica Web", callback_data=f"cl_{player_name}"))
    markup.add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
    
    if message_id:
        try: bot.edit_message_text(info_text, chat_id, message_id, parse_mode="HTML", reply_markup=markup)
        except Exception: bot.send_message(chat_id, info_text, parse_mode="HTML", reply_markup=markup)
    else:
        bot.send_message(chat_id, info_text, parse_mode="HTML", reply_markup=markup)

@bot.message_handler(commands=['start', 'menu'])
def cmd_start(m): 
    send_dashboard(m.chat.id, m.from_user.id)

@bot.message_handler(func=lambda m: not m.text.startswith('/') and not m.text.isdigit())
def search_player(message):
    query, df, session = message.text.strip().lower(), load_data(), get_session(message.from_user.id)
    if df is None or len(query) < 2: return
    matches = df[df['Nome'].astype(str).str.lower().str.contains(query, na=False)]
    if matches.empty: return bot.reply_to(message, "❌ Nessun giocatore trovato.")
    
    if len(matches) == 1:
        return send_player_card_view(message.chat.id, matches.iloc[0]['Nome'], None, df, session)

    markup = InlineKeyboardMarkup(row_width=1)
    for _, row in matches.head(10).iterrows(): 
        markup.add(InlineKeyboardButton(f"{ROLE_ICONS.get(str(row.get('R','C')).strip(),'')} {row['Nome']} ({row.get('Squadra','-')})", callback_data=f"sq_pl_{row['Nome']}"))
    bot.reply_to(message, f"🔍 Risultati per <b>{html.escape(query)}</b>:", parse_mode="HTML", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    safe_answer_callback(call.id)
    user_id, chat_id = call.from_user.id, call.message.chat.id
    session, df = get_session(user_id), load_data()

    if call.data == "go_home": 
        send_dashboard(chat_id, user_id, call.message.message_id)

    elif call.data == "force_download_listone":
        msg = bot.send_message(chat_id, "⏳ <i>Scaricamento in corso...</i>", parse_mode="HTML")
        if auto_download_listone():
            bot.edit_message_text("✅ <b>LISTONE AGGIORNATO!</b>", chat_id, msg.message_id, parse_mode="HTML")
        else:
            bot.edit_message_text("❌ <b>Download fallito.</b> Controlla il link GitHub.", chat_id, msg.message_id, parse_mode="HTML")

    elif call.data == "sq_start":
        # Estrazione pulita e senza duplicati di tutte le squadre reali dal Listone
        squadre = sorted(list(set(df['Squadra'].dropna().astype(str).str.strip().unique())))
        squadre = [s for s in squadre if len(s) > 1]
        
        markup = InlineKeyboardMarkup(row_width=2)
        buttons = [InlineKeyboardButton(f"{get_team_icon(s)} {s}", callback_data=f"sq_sq_{s}") for s in squadre]
        markup.add(*buttons)
        markup.add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text("👕 <b>SELEZIONA SQUADRA</b>", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif call.data.startswith("sq_sq_"):
        sq = call.data.replace("sq_sq_", "").strip()
        markup = InlineKeyboardMarkup(row_width=4)
        markup.add(*[InlineKeyboardButton(f"{ROLE_ICONS[r]} {r}", callback_data=f"sq_ru_{sq}_{r}") for r in ['P', 'D', 'C', 'A']])
        markup.add(InlineKeyboardButton("🔙 Squadre", callback_data="sq_start"))
        bot.edit_message_text(f"Squadra: <b>{sq}</b>\nScegli il ruolo:", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif call.data.startswith("sq_ru_"):
        parts = call.data.split("_")
        sq = parts[2].strip()
        ru = parts[3].strip()
        
        # FILTRO RIGOROSO SULLA SQUADRA DAL LISTONE
        giocatori = df[(df['Squadra'].astype(str).str.strip().str.lower() == sq.lower()) & 
                       (df['R'].astype(str).str.strip().str.upper() == ru.upper())].sort_values(by='FVM', ascending=False)
        
        markup = InlineKeyboardMarkup(row_width=1)
        for _, r in giocatori.iterrows():
            markup.add(InlineKeyboardButton(f"{ROLE_ICONS.get(ru,'')} {r['Nome']} ─ FVM:{r.get('FVM', 0)}", callback_data=f"sq_pl_{r['Nome']}"))
        markup.add(InlineKeyboardButton("🔙 Cambia Ruolo", callback_data=f"sq_sq_{sq}"))
        
        bot.edit_message_text(f"Giocatori <b>{sq}</b> ({ru}):", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif call.data.startswith("sq_pl_"):
        p_name = call.data.replace("sq_pl_", "").strip()
        send_player_card_view(chat_id, p_name, call.message.message_id, df, session)

    elif call.data.startswith("stats_"):
        p = call.data.replace("stats_", "")
        bot.edit_message_text(get_storico_excel_o_web(p), chat_id, call.message.message_id, parse_mode="HTML", reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🏠 Home", callback_data="go_home")))

    elif call.data.startswith("cl_"):
        p = call.data.replace("cl_", "")
        bot.edit_message_text(get_cartella_clinica_reale(p), chat_id, call.message.message_id, parse_mode="HTML", reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🏠 Home", callback_data="go_home")))

if __name__ == '__main__':
    try: bot.remove_webhook()
    except: pass
    print("🚀 FANTABOT PRO In Ascolto!")
    bot.infinity_polling(timeout=10, long_polling_timeout=5, skip_pending=True)
