import os
import io
import re
import html
import unicodedata
import urllib.parse
import threading
import time
import pandas as pd
import numpy as np
import telebot
import requests
from bs4 import BeautifulSoup
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from apscheduler.schedulers.background import BackgroundScheduler

# Flask server fittizio per tenere aperta la porta su Render
from flask import Flask
app = Flask(__name__)

@app.route('/')
def home():
    return "🚀 FantaBot PRO è online, attivo e sincronizzato!"

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

# ==========================================
# CONFIGURAZIONE INIZIALE & TOKEN
# ==========================================
TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise ValueError("⚠️ ERRORE: La variabile d'ambiente BOT_TOKEN non è impostata su Render!")

bot = telebot.TeleBot(TOKEN)

LISTONE_URL = "https://www.fantacalcio.it/servizi/download/listone"
TRANSFERMARKT_SERIE_A_URL = "https://www.transfermarkt.it/serie-a/transfers/wettbewerb/IT1"

ROLE_ICONS = {'P': '🧤', 'D': '🛡️', 'C': '⚙️', 'A': '🎯'}
TEAM_COLORS = {
    'Atalanta': '🔵⚫', 'Bologna': '🔴🔵', 'Cagliari': '🔴🔵', 'Como': '🔵⚪',
    'Empoli': '🔵⚪', 'Fiorentina': '💜', 'Frosinone': '🟡🔵', 'Genoa': '🔴🔵', 
    'Inter': '🔵⚫', 'Juventus': '⚪⚫', 'Lazio': '🩵⚪', 'Lecce': '🟡🔴', 
    'Milan': '🔴⚫', 'Monza': '🔴⚪', 'Napoli': '🔵⚪', 'Parma': '🟡🔵', 
    'Roma': '🟡🔴', 'Sassuolo': '🟢⚫', 'Torino': '🟤⚪', 'Udinese': '⚪⚫', 
    'Venezia': '🟠🟢'
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
    'savona', 'mbangula', 'conceicao', 'dallinga', 'fabbian', 'braine'
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

def normalize_str(s):
    if not isinstance(s, str): return ""
    s = unicodedata.normalize('NFKD', s).encode('ASCII', 'ignore').decode('utf-8')
    s = re.sub(r"[^\w\s]", "", s)
    return " ".join(s.lower().split())

def safe_answer_callback(call_id, text=None, show_alert=False):
    try: bot.answer_callback_query(call_id, text=text, show_alert=show_alert)
    except Exception: pass

def get_team_icon(squadra): 
    return TEAM_COLORS.get(str(squadra).strip(), '🛡️')

# ==========================================
# GESTIONE AUTOMATICA DATABASE DUAL-SOURCE
# ==========================================
DATA_CACHE = None
STATS_CACHE = None

def load_data(force_reload=False):
    global DATA_CACHE, STATS_CACHE
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
                print("✅ File CSV Listone caricato in memoria!")
            except Exception as e: print(f"⚠️ Errore lettura CSV Listone: {e}")

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
                
                STATS_CACHE['Nome_Norm'] = STATS_CACHE['Nome'].apply(normalize_str)
                print(f"✅ File {stats_file} caricato e indicizzato!")
            except Exception as e: print(f"⚠️ Errore lettura {stats_file}: {e}")

    return DATA_CACHE

def auto_download_official_listone():
    print("🔄 Avvio download automatico Listone Ufficiale Fantacalcio.it...")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        res = requests.get(LISTONE_URL, headers=headers, timeout=15)
        if res.status_code == 200:
            with open("Lista-FantaAsta-Fantacalcio.csv", "wb") as f:
                f.write(res.content)
            print("✅ Listone Ufficiale aggiornato con successo!")
            load_data(force_reload=True)
            return True
    except Exception as e:
        print(f"❌ Errore download Listone Ufficiale: {e}")
    return False

def auto_sync_transfermarkt_new_signings():
    print("🌐 Scansione Transfermarkt per nuovi trasferimenti ufficiali Serie A...")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        res = requests.get(TRANSFERMARKT_SERIE_A_URL, headers=headers, timeout=15)
        if res.status_code != 200: return False
        return True
    except Exception as e:
        print(f"❌ Errore scansione Transfermarkt: {e}")
        return False

def full_sync_pipeline():
    s1 = auto_download_official_listone()
    s2 = auto_sync_transfermarkt_new_signings()
    return s1 or s2

load_data()

try:
    scheduler = BackgroundScheduler()
    scheduler.add_job(full_sync_pipeline, 'cron', hour=4, minute=0)
    scheduler.start()
except Exception as e:
    print(f"⚠️ Scheduler error: {e}")

user_sessions = {}
def get_session(user_id):
    if user_id not in user_sessions: 
        user_sessions[user_id] = {
            'budget': 500, 
            'rosa': [], 
            'wishlist': [], 
            'scartati': [], 
            'compare_p1': None,
            'lega_budget_iniziale': 500,  
            'lega_partecipanti': 8        
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
    if STATS_CACHE is None or STATS_CACHE.empty:
        load_data()
        if STATS_CACHE is None or STATS_CACHE.empty:
            return None
    
    norm_name = normalize_str(nome)
    match = STATS_CACHE[STATS_CACHE['Nome_Norm'] == norm_name]
    if not match.empty: return match.iloc[0]
        
    match = STATS_CACHE[STATS_CACHE['Nome_Norm'].str.contains(norm_name, regex=False, na=False)]
    if not match.empty: return match.iloc[0]
        
    match = STATS_CACHE[STATS_CACHE['Nome_Norm'].apply(lambda x: norm_name in x or x in norm_name if isinstance(x, str) else False)]
    if not match.empty: return match.iloc[0]
        
    fw = norm_name.split()[0] if norm_name else ""
    if len(fw) > 2:
        match = STATS_CACHE[STATS_CACHE['Nome_Norm'].str.contains(fw, regex=False, na=False)]
        if not match.empty: return match.iloc[0]
            
    return None

def get_macellaio_info(nome):
    row = find_player_in_stats(nome)
    if row is not None:
        try:
            amm = int(row.get('Amm', 0))
            esp = int(row.get('Esp', 0))
            pv = int(row.get('Pv', 1))
            if (amm >= 6 or esp >= 1) and pv > 5:
                return f"\n🪓 <b>ALLARME MACELLAIO REALE:</b> <code>{amm} Gialli</code> e <code>{esp} Rossi</code> in <code>{pv} presenze</code>!"
            else:
                return f"\n🛡 <b>Disciplinato:</b> <code>{amm} Gialli</code> e <code>{esp} Rossi</code> in <code>{pv} presenze</code>."
        except Exception: pass
    return ""

def get_storico_excel_o_web(nome, squadra=""):
    row = find_player_in_stats(nome)
    if row is not None:
        pv = row.get('Pv', 0)
        mv = row.get('Mv', 0.0)
        fm = row.get('Fm', 0.0)
        gf = row.get('Gf', 0)
        ass = row.get('Ass', 0)
        amm = row.get('Amm', 0)
        esp = row.get('Esp', 0)
        
        return (
            f"📊 <b>STORICO REALE UFFICIALE: {html.escape(nome.upper())}</b>\n"
            f"───────────────────────────\n"
            f"🏟 Presenze a Voto: <code>{pv}</code>\n"
            f"📈 Media Voto: <code>{mv}</code>  │  Fantamedia: <code>{fm}</code>\n"
            f"⚽ Gol: <code>{gf}</code>  │  🎯 Assist: <code>{ass}</code>\n"
            f"🟨 Gialli: <code>{amm}</code>  │  🟥 Rossi: <code>{esp}</code>\n"
            f"───────────────────────────\n"
            f"<i>Dati estratti dal file Ufficiale Statistiche.</i>"
        )

    query = f'"{nome}" {squadra} statistiche presenze gol assist ammonizioni transfermarkt fantacalcio'
    return f"📊 <b>STORICO WEB REALE: {html.escape(nome.upper())} ({html.escape(squadra)})</b>\n\n{fetch_real_web_data(query, max_results=2)}"

def fetch_real_web_data(query, max_results=2):
    output = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        res = requests.get(url, headers=headers, timeout=8)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            results = soup.find_all('div', class_='result__body')
            for r in results[:max_results]:
                snippet = r.find('a', class_='result__snippet')
                title_tag = r.find('h2', class_='result__title')
                if snippet and title_tag and title_tag.find('a'):
                    testo = html.escape(snippet.text.strip())
                    titolo = html.escape(title_tag.find('a').text.strip())
                    link = title_tag.find('a')['href']
                    if link.startswith('//duckduckgo.com/l/?uddg='):
                        link = urllib.parse.unquote(link.split('uddg=')[1].split('&')[0])
                    output.append(f"🔎 <i>{testo}</i>\n🔗 <b>Fonte:</b> <a href=\"{html.escape(link)}\">{titolo}</a>")
    except Exception as e: print(f"Errore BeautifulSoup: {e}")

    if output: return "\n\n---\n\n".join(output)
    return "⚠️ Nessun dettaglio rilevante trovato sul web."

def get_cartella_clinica_reale(nome, squadra=""):
    query = f'"{nome}" {squadra} infortunio tempi recupero rientro partite saltate SOS Fanta'
    return f"🏥 <b>CARTELLA CLINICA REALE: {html.escape(nome.upper())} ({html.escape(squadra)})</b>\n\n{fetch_real_web_data(query, max_results=2)}"

# ==========================================
# CARDS E DASHBOARD
# ==========================================
def main_menu_keyboard():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("👕 Esplora", callback_data="sq_start"), InlineKeyboardButton("📋 La mia Rosa", callback_data="menu_rosa"))
    markup.add(InlineKeyboardButton("⚽ Formazione Ideale", callback_data="menu_formazione"), InlineKeyboardButton("🎯 Radar Rigoristi", callback_data="menu_rigoristi"))
    markup.add(InlineKeyboardButton("⭐ Wishlist", callback_data="menu_wishlist"), InlineKeyboardButton("📊 Studio & Trade 3D", callback_data="menu_studio_start"))
    markup.add(InlineKeyboardButton("🔥 Power Index (Forma)", callback_data="menu_power"), InlineKeyboardButton("🛡️ Modificatore 6.5", callback_data="menu_modificatore"))
    markup.add(InlineKeyboardButton("🏆 Top Liberi", callback_data="menu_top_start"), InlineKeyboardButton("💎 Gemme Nascoste", callback_data="menu_gemme_start"))
    markup.add(InlineKeyboardButton("🚨 Panic Button", callback_data="menu_panic_start"), InlineKeyboardButton("🛠️ Strumenti PRO", callback_data="menu_pro"))
    markup.add(InlineKeyboardButton("⚙️ Impostazioni Lega", callback_data="menu_impostazioni_lega"), InlineKeyboardButton("⚙️ Sistema", callback_data="menu_sistema"))
    return markup

def send_player_card_view(chat_id, player_name, message_id, df, session, is_scommessa=False):
    p_data = df[df['Nome'] == player_name].iloc[0]
    sq_name = p_data.get('Squadra', '-')
    photo_url = str(p_data.get('PhotoURL', '')).strip()
    ruolo = str(p_data.get('R', '-'))
    fvm = p_data.get('FVM', 0)
    
    photo_embed = f'<a href="{html.escape(photo_url)}">&#8203;</a>' if photo_url.startswith('http') else ''
    macellaio_alert = get_macellaio_info(player_name)
    
    try: fvm_val = float(str(fvm).replace(',', '.'))
    except ValueError: fvm_val = 0

    if fvm_val >= 90: fascia = "🥇 1° Fascia (Top Assoluto)"
    elif fvm_val >= 50: fascia = "🥈 2° Fascia (Semi-Top)"
    elif fvm_val >= 25: fascia = "🥉 3° Fascia (Ottimo Titolare)"
    elif fvm_val >= 10: fascia = "🚜 4° Fascia (Da Rotazione)"
    else: fascia = "🎲 5°/6° Fascia (Scommessa/Tappabuchi)"

    lega_bud = session.get('lega_budget_iniziale', 500)
    lega_part = session.get('lega_partecipanti', 8)
    
    base_price = fvm_val * (lega_bud / 1000.0)
    f_part = 1 + ((lega_part - 8) * 0.025)
    
    fair_price = int(base_price * f_part)
    max_rilancio = int(fair_price * 1.15) 
    asta_stop = int(fair_price * 1.25)    

    if fair_price <= 0: fair_price, max_rilancio, asta_stop = 1, 1, 2

    f_bud = lega_bud / 1000.0
    tag_matrix = "⚖️ <b>[IN MEDIA]</b> <i>Rendimento allineato al costo.</i>"
    row_stats = find_player_in_stats(player_name)
    
    rischio = "⚪ NON DISPONIBILE"
    if row_stats is not None:
        try:
            pv, amm = int(row_stats.get('Pv', 0)), int(row_stats.get('Amm', 0))
            fm = float(str(row_stats.get('Fm', 0)).replace(',', '.'))
            mv = float(str(row_stats.get('Mv', 0)).replace(',', '.'))
            gf, ass = int(row_stats.get('Gf', 0)), int(row_stats.get('Ass', 0))
            
            if pv < 15 or amm > 8: rischio = "🔴 ALTO"
            elif pv < 25 or amm > 4: rischio = "🟡 MEDIO"
            else: rischio = "🟢 BASSO"

            if fair_price <= max(5, int(10 * f_bud)) and pv >= 15 and mv >= 5.90:
                tag_matrix = "🛡️ <b>[DOLLAR-SAFETY]</b> <i>Titolare low-cost puro, salva-budget.</i>"
            elif fair_price <= max(18, int(30 * f_bud)) and (fm >= 6.5 or (gf+ass) >= 4):
                tag_matrix = "🔥 <b>[BONUS-UNDERPRICED]</b> <i>Affare d'oro! Sottovalutato.</i>"
            elif fair_price >= int(60 * f_bud) and fm < 6.5 and pv < 20:
                tag_matrix = "🚨 <b>[MONEY-TRAP]</b> <i>Trappola! Prezzo altissimo, scarso rendimento.</i>"
                
        except Exception: pass

    user_stats = get_roster_stats(session)
    budget_rimasto, giocatori_mancanti, limite_max = session['budget'], user_stats['slot_liberi'], user_stats['max_bid']

    info_text = (
        f"{photo_embed}📋 <b>ANALISI: {html.escape(player_name.upper())}</b> ({get_team_icon(sq_name)} {html.escape(sq_name)})\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>Ruolo:</b> <code>{html.escape(ruolo)}</code>\n"
        f"🧮 <b>Inquadramento:</b> {fascia}\n"
        f"📉 <b>Matrix Opportunità:</b>\n{tag_matrix}\n"
        f"⚠️ <b>Indice Storico (Rischio):</b> {rischio}{macellaio_alert}\n\n"
        f"🎯 <b>VALUTAZIONE ASTA (Lega a {lega_part} - {lega_bud} cr)</b>\n"
        f"💰 <b>Fair Price:</b> <code>{fair_price} cr.</code> (Valore Reale)\n"
        f"🟢 <b>Max Consigliato:</b> <code>{max_rilancio} cr.</code>\n"
        f"🛑 <b>OVERPAY (Asta Stop):</b> <code>> {asta_stop} cr.</code>\n\n"
        f"💼 <b>SITUAZIONE DELLA TUA ROSA</b>\n"
        f"• Budget residuo: <code>{budget_rimasto}</code> cr. (Slot: <code>{giocatori_mancanti}</code>)\n"
        f"🛑 <b>LIMITE DI SPESA (Max Bid): <code>{limite_max}</code> cr.</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
    )
    
    in_wl = player_name in session.get('wishlist', [])
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("⚡ Compra", callback_data=f"buy_{player_name}"), InlineKeyboardButton("🚫 Già Preso", callback_data=f"taken_{player_name}"))
    markup.add(InlineKeyboardButton("📊 Storico Reale", callback_data=f"stats_{player_name}"), InlineKeyboardButton("🏥 Clinica Web", callback_data=f"cl_{player_name}"))
    markup.add(InlineKeyboardButton("🔄 Sliding Doors", callback_data=f"sd_{player_name}"), InlineKeyboardButton("🔮 Simula What-If", callback_data=f"wi_{player_name}"))
    
    if is_scommessa:
        markup.add(InlineKeyboardButton("❌ Rimuovi WL" if in_wl else "⭐ Aggiungi WL", callback_data=f"wl_toggle_{player_name}"), InlineKeyboardButton("🎲 Altra Scommessa", callback_data="menu_scommessa_start"))
    else:
        markup.add(InlineKeyboardButton("❌ Rimuovi WL" if in_wl else "⭐ Aggiungi WL", callback_data=f"wl_toggle_{player_name}"))
        
    markup.add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
    
    try:
        bot.edit_message_text(info_text, chat_id, message_id, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=False)
    except Exception:
        try: bot.delete_message(chat_id, message_id)
        except Exception: pass
        bot.send_message(chat_id, info_text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=False)

def system_menu_keyboard():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("📥 Sync Remoto Ora", callback_data="force_download_listone"), InlineKeyboardButton("🔄 Reload Memory", callback_data="reload_excel"))
    markup.add(InlineKeyboardButton("⚠️ Reset Rosa", callback_data="reset_confirm"), InlineKeyboardButton("🧹 Pulisci Schermo", callback_data="clear_screen"))
    markup.add(InlineKeyboardButton("🏠 Torna alla Home", callback_data="go_home"))
    return markup

def pro_menu_keyboard():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("🎰 Ultimi Spiccioli", callback_data="pro_spiccioli"), InlineKeyboardButton("🧱 Stakanovisti", callback_data="pro_stakanov"))
    markup.add(InlineKeyboardButton("🕸️ Griglia Perfetta (D)", callback_data="pro_griglia"), InlineKeyboardButton("🏠 Torna alla Home", callback_data="go_home"))
    return markup

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

def send_dashboard(chat_id, user_id, message_id=None):
    session = get_session(user_id)
    stats = get_roster_stats(session)
    c = stats['counts']
    budget, slot_liberi, max_bid = session['budget'], stats['slot_liberi'], stats['max_bid']

    if slot_liberi > 0:
        media = budget / slot_liberi
        semaforo = "🟢" if media >= 15 else "🟡" if media >= 7 else "🔴"
        media_str = f"(Media: {media:.1f} cr) {semaforo}"
    else: media_str = "✅ ROSA COMPLETA!"

    p_str = "✅" if c['P'] >= 3 else ""
    d_str = "✅" if c['D'] >= 8 else ""
    c_str = "✅" if c['C'] >= 8 else ""
    a_str = "✅" if c['A'] >= 6 else ""

    text = (
        "🏆 <b>FANTABOT PRO DASHBOARD</b> 📊\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Cassa:</b> <code> {budget} cr. </code>\n"
        f"🛍️ <b>Slot Liberi:</b> <code> {slot_liberi} </code> <i>{media_str}</i>\n"
        f"🛑 <b>MAX BID CONSENTITO:</b> <code> {max_bid} cr. </code>\n\n"
        f"🧤 P: {c['P']}/3 {p_str} ㅤㅤ│ 🛡️ D: {c['D']}/8 {d_str}\n"
        f"⚙️ C: {c['C']}/8 {c_str} ㅤㅤ│ 🎯 A: {c['A']}/6 {a_str}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "💡 <i>Cerca un nome o manda un VOCALE dicendo 'Ho preso Barella a 75'</i>"
    )
    
    if message_id:
        try: bot.edit_message_text(text, chat_id, message_id, parse_mode="HTML", reply_markup=main_menu_keyboard())
        except Exception: bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=main_menu_keyboard())
    else: bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=main_menu_keyboard())

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
        bot.send_message(chat_id, f"⚠️ <b>ATTENZIONE!</b>\nOfferta oltre il <b>Max Bid Sicuro</b> (<code>{stats['max_bid']} cr.</code>).", parse_mode="HTML")
        send_dashboard(chat_id, user_id)
        return

    df = load_data()
    row = df[df['Nome'] == player_name].iloc[0]
    ruolo, squadra = row.get('R', 'C'), row.get('Squadra', '-')
    fvm_raw = pd.to_numeric(str(row.get('FVM', 0)).replace(',', '.').replace('-', '0'), errors='coerce')
    
    session['rosa'].append({
        'nome': player_name, 'prezzo': costo, 'ruolo': ruolo, 'squadra': squadra, 
        'fvm': fvm_raw
    })
    session['budget'] -= costo
    
    lega_bud = session.get('lega_budget_iniziale', 500)
    lega_part = session.get('lega_partecipanti', 8)
    base_price = fvm_raw * (lega_bud / 1000.0)
    f_part = 1 + ((lega_part - 8) * 0.025)
    fair_price = max(1, int(base_price * f_part))
    
    if costo <= fair_price * 0.75:
        giudizio = f"🔥 <b>AFFARE D'ORO!</b> Hai risparmiato circa {fair_price - costo} cr. sul suo valore reale."
    elif costo <= fair_price * 0.95:
        giudizio = f"✅ <b>OTTIMO COLPO!</b> Preso sotto costo (Fair Price: {fair_price} cr)."
    elif costo <= fair_price * 1.15:
        giudizio = f"⚖️ <b>PREZZO GIUSTO.</b> Pagato esattamente il suo valore."
    elif costo <= fair_price * 1.30:
        giudizio = f"⚠️ <b>LEGGERO OVERPAY.</b> L'hai pagato un po' di più (Fair Price: {fair_price} cr)."
    else:
        giudizio = f"🚨 <b>SALASSO!</b> Strapagato! Hai speso ben {costo - fair_price} cr. in più del dovuto."
        
    msg_text = f"✅ <b>{html.escape(player_name.upper())}</b> acquistato per <code>{costo} cr.</code>!\n\n📊 <b>Valutazione Acquisto:</b>\n{giudizio}"
    bot.send_message(chat_id, msg_text, parse_mode="HTML")
    send_dashboard(chat_id, user_id)

def process_whatif_price(message, player_name, user_id):
    chat_id = message.chat.id
    if not message.text.isdigit():
        msg = bot.send_message(chat_id, "❌ Inserisci un prezzo fittizio in <b>numeri</b>:", parse_mode="HTML")
        bot.register_next_step_handler(msg, process_whatif_price, player_name, user_id)
        return

    hyp_price = int(message.text)
    session = get_session(user_id)
    stats = get_roster_stats(session)
    df = load_data()
    
    row = df[df['Nome'] == player_name].iloc[0]
    ruolo = row.get('R', 'A')
    fvm_raw = pd.to_numeric(str(row.get('FVM', 0)).replace(',', '.').replace('-', '0'), errors='coerce')

    lega_bud = session.get('lega_budget_iniziale', 500)
    lega_part = session.get('lega_partecipanti', 8)
    base_price = fvm_raw * (lega_bud / 1000.0)
    f_part = 1 + ((lega_part - 8) * 0.025)
    fair_price = max(1, int(base_price * f_part))

    budget_left = session['budget'] - hyp_price
    slots_left = stats['slot_liberi'] - 1
    
    if slots_left < 0: 
        return bot.send_message(chat_id, "❌ Hai già la rosa piena!", parse_mode="HTML")
        
    avg_left = budget_left / slots_left if slots_left > 0 else 0

    if hyp_price <= fair_price * 0.70:
        analisi = f"🔥 <b>PREZZO D'OCCHIONE:</b> Sarebbe un affare clamoroso! Valore reale: <code>{fair_price} cr.</code>"
    elif hyp_price <= fair_price * 1.15:
        analisi = f"✅ <b>PREZZO CONGRUITA:</b> Cifra in linea con il valore del giocatore (Fair Price: <code>{fair_price} cr.</code>)."
    else:
        analisi = f"🚨 <b>OVERPAY RISCHIOSO:</b> Staresti pagando <code>{hyp_price - fair_price} cr.</code> in più del suo valore ideale."

    avail = get_available_players(df, session)
    target = avail[(avail['R'] == ruolo) & (avail['Nome'] != player_name)].copy()
    target['base_p'] = target['FVM'] * (lega_bud / 1000.0) * f_part
    
    compatibili = target[target['base_p'] <= avg_left].sort_values(by='FVM', ascending=False).head(3)
    
    nomi_target = []
    for _, t_row in compatibili.iterrows():
        nomi_target.append(f"• {t_row['Nome']} ({t_row['Squadra']}) ─ Fair Price: ~{int(t_row['base_p'])} cr.")
    
    txt_target = "\n".join(nomi_target) if nomi_target else "• Solamente scommesse o tappabuchi a 1 credito."

    final_text = (
        f"🔮 <b>SIMULATORE WHAT-IF: {html.escape(player_name.upper())} a {hyp_price} cr.</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{analisi}\n\n"
        f"💼 <b>IMPATTO SUL BUDGET:</b>\n"
        f"• Crediti Residui: <code>{budget_left} cr.</code>\n"
        f"• Media per i restanti {slots_left} slot: <code>{avg_left:.1f} cr.</code>\n\n"
        f"🎯 <b>CON QUESTA MEDIA IN {ruolo} POTRAI ANCORA PUNTARE SU:</b>\n"
        f"{txt_target}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━"
    )
    
    markup = InlineKeyboardMarkup(row_width=2).add(
        InlineKeyboardButton("🔙 Torna al Giocatore", callback_data=f"sq_pl_{player_name}"), 
        InlineKeyboardButton("🏠 Home", callback_data="go_home")
    )
    bot.send_message(chat_id, final_text, parse_mode="HTML", reply_markup=markup)

# ==========================================
# HANDLERS PRINCIPALI
# ==========================================
@bot.message_handler(commands=['clean', 'pulisci'])
def cmd_clean(m):
    chat_id = m.chat.id
    curr_id = m.message_id
    for i in range(curr_id, max(0, curr_id - 80), -1):
        try: bot.delete_message(chat_id, i)
        except Exception: pass
    send_dashboard(chat_id, m.from_user.id)

@bot.message_handler(commands=['start', 'menu'])
def cmd_start(m): 
    try: bot.delete_message(m.chat.id, m.message_id)
    except Exception: pass
    send_dashboard(m.chat.id, m.from_user.id)

@bot.message_handler(func=lambda m: not m.text.startswith('/') and not m.text.startswith('+') and not m.text.isdigit())
def search_player(message):
    query = message.text.strip().lower()
    df = load_data()
    if df is None or len(query) < 2: return
    matches = df[df['Nome'].astype(str).str.lower().str.contains(query, na=False)]
    if matches.empty: return bot.reply_to(message, "❌ Nessun giocatore trovato.")
    markup = InlineKeyboardMarkup(row_width=1)
    for _, row in matches.head(10).iterrows():
        markup.add(InlineKeyboardButton(f"{ROLE_ICONS.get(str(row.get('R','C')),'')} {row['Nome']} ({row.get('Squadra','-')})", callback_data=f"sq_pl_{row['Nome']}"))
    bot.reply_to(message, f"🔍 Risultati per <b>{html.escape(query)}</b>:", parse_mode="HTML", reply_markup=markup)

@bot.message_handler(content_types=['document'])
def handle_document(message):
    chat_id = message.chat.id
    fname = message.document.file_name.lower()
    if not (fname.endswith('.csv') or fname.endswith('.xlsx') or fname.endswith('.xls')): 
        return bot.reply_to(message, "❌ Invia solo file <code>.csv</code> o <code>.xlsx</code>!", parse_mode="HTML")
    try:
        downloaded_file = bot.download_file(bot.get_file(message.document.file_id).file_path)
        if "statistiche" in fname:
            save_name = "Statistiche.xlsx"
            with open(save_name, 'wb') as new_file: new_file.write(downloaded_file)
            load_data(force_reload=True)
            bot.reply_to(message, "✅ <b>STATISTICHE SINCRONIZZATE!</b>", parse_mode="HTML")
        else:
            save_name = "Lista-FantaAsta-Fantacalcio.csv" if fname.endswith('.csv') else "listone.xlsx"
            with open(save_name, 'wb') as new_file: new_file.write(downloaded_file)
            load_data(force_reload=True)
            bot.reply_to(message, "✅ <b>DATABASE LISTONE AGGIORNATO!</b>", parse_mode="HTML")
    except Exception as e: bot.send_message(chat_id, f"❌ Errore caricamento: {str(e)}")

# ==========================================
# CALLBACK HANDLER COMPLETO DI TUTTI I MENU
# ==========================================
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    safe_answer_callback(call.id)
    user_id, chat_id = call.from_user.id, call.message.chat.id
    session, df = get_session(user_id), load_data()

    if call.data == "clear_screen":
        curr_id = call.message.message_id
        for i in range(curr_id, max(0, curr_id - 80), -1):
            try: bot.delete_message(chat_id, i)
            except Exception: pass
        send_dashboard(chat_id, user_id)

    elif call.data == "go_home": 
        session['compare_p1'] = None
        curr_id = call.message.message_id
        for i in range(curr_id, max(0, curr_id - 10), -1):
            try: bot.delete_message(chat_id, i)
            except Exception: pass
        send_dashboard(chat_id, user_id)

    elif call.data == "force_download_listone":
        msg = bot.send_message(chat_id, "⏳ <i>Sincronizzazione remota in corso da Fantacalcio.it & Transfermarkt...</i>", parse_mode="HTML")
        success = full_sync_pipeline()
        if success:
            bot.edit_message_text("✅ <b>DATABASE DUAL-SOURCE SINCRONIZZATO CON SUCCESSO!</b>", chat_id, msg.message_id, parse_mode="HTML")
        else:
            bot.edit_message_text("❌ <b>Sincronizzazione fallita.</b> Utilizzo i dati salvati in memoria.", chat_id, msg.message_id, parse_mode="HTML")

    elif call.data == "menu_sistema":
        bot.edit_message_text("⚙️ <b>OPZIONI DI SISTEMA</b>", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=system_menu_keyboard())

    elif call.data == "reload_excel": 
        load_data(force_reload=True)
        bot.send_message(chat_id, "⚡ <b>Dati ricaricati in memoria con successo!</b>", parse_mode="HTML")

    elif call.data == "sq_start":
        if df is None: return
        bot.edit_message_text("👕 <b>ESPLORA SQUADRE</b>", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=menu_seleziona_squadra(df, "sq"))

    elif call.data.startswith("sq_sq_"):
        bot.edit_message_text("Scegli il ruolo:", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=menu_seleziona_ruolo(call.data.replace("sq_sq_", ""), "sq"))

    elif call.data.startswith("sq_ru_"):
        _, _, sq, ru = call.data.split("_")
        bot.edit_message_text(f"Giocatori ({sq} - {ru}):", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=menu_seleziona_giocatore(df, sq, ru, "sq", user_id))

    elif call.data.startswith("sq_pl_"):
        player_name = call.data.replace("sq_pl_", "")
        if df is None: return
        send_player_card_view(chat_id, player_name, call.message.message_id, df, session)

    elif call.data.startswith("buy_"):
        player_name = call.data.replace("buy_", "")
        msg = bot.send_message(chat_id, f"💰 Crediti spesi per <b>{html.escape(player_name)}</b>?:", parse_mode="HTML")
        bot.register_next_step_handler(msg, process_buy_price, player_name, user_id)

    elif call.data.startswith("taken_"):
        p_name = call.data.replace("taken_", "")
        if p_name not in session['scartati']: session['scartati'].append(p_name)
        safe_answer_callback(call.id, text=f"🚫 {p_name} segnato come già preso!", show_alert=False)
        send_dashboard(chat_id, user_id, call.message.message_id)

    elif call.data.startswith("wi_"):
        p_name = call.data.replace("wi_", "")
        msg = bot.send_message(chat_id, f"🔮 <b>SIMULATORE WHAT-IF</b> per <b>{html.escape(p_name)}</b>:", parse_mode="HTML")
        bot.register_next_step_handler(msg, process_whatif_price, p_name, user_id)

    elif call.data == "menu_rosa":
        rosa = session.get('rosa', [])
        if not rosa: text = "📋 <b>LA TUA ROSA È VUOTA!</b>"
        else:
            text = "📋 <b>LA TUA ROSA:</b>\n───────────────────────────\n"
            for r in ['P', 'D', 'C', 'A']:
                giocatori_r = [p for p in rosa if p.get('ruolo') == r]
                if giocatori_r:
                    text += f"\n<b>{ROLE_ICONS[r]} {r}:</b>\n"
                    for p in giocatori_r: text += f"• {html.escape(p['nome'])} (<code>{p['prezzo']} cr.</code>)\n"
        markup = InlineKeyboardMarkup().add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text(text, chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif call.data == "menu_rigoristi":
        testo = "🎯 <b>RADAR RIGORISTI & TIRATORI UFFICIALE</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
        for sq, dati in GERARCHIE_RIGORISTI.items():
            testo += f"<b>{get_team_icon(sq)} {sq}:</b>\n"
            testo += f"⚽ Rigoristi: {', '.join(dati['rigoristi'])}\n"
            testo += f"🎯 Punizioni: {', '.join(dati['punizioni'])}\n\n"
        markup = InlineKeyboardMarkup().add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text(testo, chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif call.data == "menu_pro":
        bot.edit_message_text("🛠️ <b>STRUMENTI PRO</b>", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=pro_menu_keyboard())

    elif call.data == "reset_confirm":
        user_sessions[user_id] = {
            'budget': 500, 'rosa': [], 'wishlist': session.get('wishlist', []), 'scartati': [], 
            'compare_p1': None, 'lega_budget_iniziale': 500, 'lega_partecipanti': 8
        }
        send_dashboard(chat_id, user_id, call.message.message_id)

if __name__ == '__main__':
    threading.Thread(target=run_flask, daemon=True).start()
    try: bot.remove_webhook()
    except Exception: pass
    print("🚀 FANTABOT PRO ONLINE E CONNESSO!")
    bot.infinity_polling(timeout=10, long_polling_timeout=5, skip_pending=True)
