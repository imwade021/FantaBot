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
import time
from bs4 import BeautifulSoup
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from apscheduler.schedulers.background import BackgroundScheduler

# Server Flask fittizio per evitare il blocco (Port Timeout) su Render
from flask import Flask
app = Flask(__name__)

@app.route('/')
def home():
    return "🚀 FantaBot PRO è online e pienamente operativo!"

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

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

# Importa la libreria per la ricerca web
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

LISTONE_URL = "https://www.fantacalcio.it/servizi/download/listone" 

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
    'Juventus': {'rigoristi': ['Vlahovic', 'Kolo Muani', 'Yildiz'], 'punizioni': ['Vlahovic', 'Locatelli', 'Cambiaso']},
    'Lazio': {'rigoristi': ['Zaccagni', 'Taylor K.', 'Cataldi'], 'punizioni': ['Rovella', 'Zaccagni', 'Cataldi']},
    'Lecce': {'rigoristi': ['Geubbels', 'Stengs', 'Berisha M.'], 'punizioni': ['Pierotti', 'Berisha M.', 'Gandelman']},
    'Milan': {'rigoristi': ['Pulisic', 'Morata', 'Nkunku'], 'punizioni': ['Modric', 'Pulisic', 'Saelemaekers']},
    'Monza': {'rigoristi': ['Pessina', 'Cutrone', 'Petagna'], 'punizioni': ['Pessina', 'Colpani', 'Mota']},
    'Napoli': {'rigoristi': ['Kvaratskhelia', 'Politano', 'Hojlund'], 'punizioni': ['Kvaratskhelia', 'Politano', 'Neres']},
    'Parma': {'rigoristi': ['Pellegrino M.', 'Touré E.', 'Valeri'], 'punizioni': ['Bernabé', 'Nicolussi Caviglia', 'Valeri']},
    'Roma': {'rigoristi': ['Dybala', 'Pellegrini Lo.', 'Soulé'], 'punizioni': ['Dybala', 'Pellegrini Lo.', 'Soulé']},
    'Sassuolo': {'rigoristi': ['Berardi', 'Pinamonti', 'Laurienté'], 'punizioni': ['Berardi', 'Laurienté', 'Adzic']},
    'Torino': {'rigoristi': ['Vlasic', 'Kulenovic', 'Simeone'], 'punizioni': ['Vlasic', 'Oristanio', 'Gineitis']},
    'Udinese': {'rigoristi': ['Davis K.', 'Solet', 'Zaniolo'], 'punizioni': ['Zaniolo', 'Ekkelenkamp', 'Unai Gomez']},
    'Venezia': {'rigoristi': ['Adams A.', 'Rrahmani Al.', 'Adorante'], 'punizioni': ['Busio', 'Yeboah J.', 'Perez K.']}
}

DATABASE_SCOMMESSE_PURE = ['bernabe', 'fazzini', 'bonny', 'oristanio', 'paz', 'marchwinski', 'castro', 'belahyane', 'tengstedt', 'da cunha', 'moro', 'traore', 'pisilli', 'ekhator', 'solet', 'idzes', 'mangas', 'milla', 'ndour', 'viti', 'goglichidze', 'alajbegovic', 'suslov', 'mosquera', 'tchaouna', 'camarda', 'vitinha', 'savona', 'mbangula', 'conceicao', 'dallinga', 'fabbian', 'braine']
COPPIE_NOTE = {'sommer': 'martinez jo.', 'martinez jo.': 'sommer', 'di gregorio': 'perin', 'perin': 'di gregorio', 'maignan': 'sportiello', 'sportiello': 'maignan', 'svilar': 'ryan', 'ryan': 'svilar', 'dumfries': 'darmian', 'darmian': 'dumfries', 'dimarco': 'carlos augusto', 'carlos augusto': 'dimarco', 'kvaratskhelia': 'neres', 'neres': 'kvaratskhelia'}

def normalize_str(s):
    if not isinstance(s, str): return ""
    s = unicodedata.normalize('NFKD', s).encode('ASCII', 'ignore').decode('utf-8')
    return " ".join(re.sub(r"[^\w\s]", "", s).lower().split())

def safe_answer_callback(call_id, text=None, show_alert=False):
    try: bot.answer_callback_query(call_id, text=text, show_alert=show_alert)
    except Exception: pass

def get_team_icon(squadra): return TEAM_COLORS.get(str(squadra).strip(), '🛡️')

# ==========================================
# GESTIONE DATABASE & PUSH NOTIFICATIONS
# ==========================================
DATA_CACHE = None
STATS_CACHE = None
REGISTERED_CHATS = set() 

def salva_chat_id(chat_id):
    REGISTERED_CHATS.add(chat_id)

def load_data(force_reload=False):
    global DATA_CACHE, STATS_CACHE
    if DATA_CACHE is None or force_reload:
        if os.path.exists("Lista-FantaAsta-Fantacalcio.csv"):
            try:
                DATA_CACHE = pd.read_csv("Lista-FantaAsta-Fantacalcio.csv", header=None)
                DATA_CACHE.columns = ['Id', 'Nome_Breve', 'Nome', 'R', 'Ruolo_Esteso', 'Qt.A', 'Qt.I', 'Qt.M', 'Diff.M', 'Squadra', 'FVM', 'FVM.M', 'Piede', 'Nazionalita', 'DataNascita', 'PhotoURL', 'Extra1', 'Extra2', 'Extra3']
                DATA_CACHE['FVM'] = pd.to_numeric(DATA_CACHE['FVM'], errors='coerce').fillna(0)
            except Exception as e: print(f"⚠️ Errore lettura CSV: {e}")

    if STATS_CACHE is None or force_reload:
        stats_file = None
        for f in os.listdir('.'):
            if 'statistiche' in f.lower() and (f.endswith('.xlsx') or f.endswith('.xls') or f.endswith('.csv')):
                stats_file = f
                break
        if stats_file:
            try:
                STATS_CACHE = pd.read_csv(stats_file) if stats_file.endswith('.csv') else pd.read_excel(stats_file, header=1)
                STATS_CACHE['Nome_Norm'] = STATS_CACHE['Nome'].apply(normalize_str)
            except Exception as e: print(f"⚠️ Errore lettura Statistiche: {e}")
    return DATA_CACHE

def auto_download_and_inject_virtual_players():
    """Scarica il listone, inietta eventuali giocatori mancanti e invia notifiche Push"""
    print("🔄 Avvio sincronizzazione e ricerca di mercato...")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    try:
        res = requests.get(LISTONE_URL, headers=headers, timeout=15)
        if res.status_code == 200:
            with open("Lista-FantaAsta-Fantacalcio.csv", "wb") as f: f.write(res.content)
    except Exception: pass

    df_local = load_data(force_reload=True)
    
    giocatori_virtuali = [
        {'Id': 9999, 'Nome_Breve': 'Mastantuono', 'Nome': 'Franco Mastantuono', 'R': 'A', 'Ruolo_Esteso': 'Ala Destra', 'Qt.A': 15, 'Qt.I': 15, 'Qt.M': 15, 'Diff.M': 0, 'Squadra': 'Fiorentina', 'FVM': 45, 'FVM.M': 45, 'Piede': 'Sinistro', 'Nazionalita': 'Argentina', 'DataNascita': '14/08/2007', 'PhotoURL': 'https://tmssl.akamaized.net/images/portrait/header/1138580-1708518330.jpg'}
    ]

    new_injections = []
    for g in giocatori_virtuali:
        if df_local is not None and not df_local[df_local['Nome'].astype(str).str.contains(g['Nome_Breve'], case=False, na=False)].empty: continue
        riga_csv = f"\n{g['Id']},{g['Nome_Breve']},{g['Nome']},{g['R']},{g['Ruolo_Esteso']},{g['Qt.A']},{g['Qt.I']},{g['Qt.M']},{g['Diff.M']},{g['Squadra']},{g['FVM']},{g['FVM.M']},{g['Piede']},{g['Nazionalita']},{g['DataNascita']},{g['PhotoURL']},,,,"
        with open("Lista-FantaAsta-Fantacalcio.csv", "a", encoding="utf-8") as f: f.write(riga_csv)
        new_injections.append(g)
        
    load_data(force_reload=True)

    for g in new_injections:
        testo_push = (
            f"🚨 <b>NUOVO ACQUISTO UFFICIALE!</b> 🚨\n━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>{html.escape(g['Nome'])}</b> ({get_team_icon(g['Squadra'])} {g['Squadra']})\n"
            f"📌 Ruolo: {ROLE_ICONS.get(g['R'], '')} {g['R']} │ 💰 FVM: ~{g['FVM']} cr.\n"
            f"✅ <i>Giocatore iniettato in memoria!</i>"
        )
        markup = InlineKeyboardMarkup().add(InlineKeyboardButton("🔍 Apri Scheda", callback_data=f"sq_pl_{g['Nome']}"))
        for chat_id in REGISTERED_CHATS:
            try: bot.send_message(chat_id, testo_push, parse_mode="HTML", reply_markup=markup)
            except Exception: pass
    return True

load_data()
try:
    scheduler = BackgroundScheduler()
    scheduler.add_job(auto_download_and_inject_virtual_players, 'interval', minutes=60)
    scheduler.start()
except Exception as e: print(f"⚠️ Scheduler error: {e}")

# ==========================================
# SESSIONI & NAVIGATORE ASTA LIVE
# ==========================================
user_sessions = {}
def get_session(user_id):
    if user_id not in user_sessions: 
        user_sessions[user_id] = {
            'budget': 500, 'rosa': [], 'wishlist': [], 'scartati': [], 'compare_p1': None,
            'lega_budget_iniziale': 500, 'lega_partecipanti': 12,
            'asta_live': False, 'fase_attiva': None, 
            'budget_reparti': {'P': 30, 'D': 75, 'C': 125, 'A': 270}
        }
    return user_sessions[user_id]

def recalcola_budget_reparti(session):
    cassa = session['budget']
    count_r = {'P': 0, 'D': 0, 'C': 0, 'A': 0}
    for p in session['rosa']: count_r[p.get('ruolo', 'C')] += 1
    
    fasi = []
    if count_r['P'] < 3: fasi.append('P')
    if count_r['D'] < 8: fasi.append('D')
    if count_r['C'] < 8: fasi.append('C')
    if count_r['A'] < 6: fasi.append('A')

    pesi = {'P': 6, 'D': 15, 'C': 25, 'A': 54}
    peso_tot = sum(pesi[r] for r in fasi)
    
    if peso_tot > 0:
        for r in fasi: session['budget_reparti'][r] = int(cassa * (pesi[r] / peso_tot))

def get_roster_stats(session):
    rosa, budget = session['rosa'], session['budget']
    counts = {'P': 0, 'D': 0, 'C': 0, 'A': 0}
    for p in rosa: counts[p.get('ruolo', 'C')] += 1
    slot_liberi = max(0, 25 - len(rosa))
    max_bid = max(0, budget - (slot_liberi - 1)) if slot_liberi > 0 else budget
    return {'counts': counts, 'slot_liberi': slot_liberi, 'max_bid': max_bid}

def get_available_players(df, session):
    esclusi = set([p['nome'] for p in session.get('rosa', [])] + session.get('scartati', []))
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
            if (amm >= 6 or esp >= 1) and pv > 5: return f"\n🪓 <b>ALLARME MACELLAIO:</b> <code>{amm} G</code>, <code>{esp} R</code>!"
        except: pass
    return ""

def get_storico_excel_o_web(nome, squadra=""):
    row = find_player_in_stats(nome)
    if row is not None:
        pv, mv, fm, gf, ass, amm, esp = row.get('Pv', 0), row.get('Mv', 0.0), row.get('Fm', 0.0), row.get('Gf', 0), row.get('Ass', 0), row.get('Amm', 0), row.get('Esp', 0)
        return (f"📊 <b>STORICO REALE: {html.escape(nome.upper())}</b>\n───────────────────────────\n"
                f"🏟 Presenze: <code>{pv}</code> │ 📈 MV: <code>{mv}</code> │ FM: <code>{fm}</code>\n"
                f"⚽ Gol: <code>{gf}</code> │ 🎯 Assist: <code>{ass}</code> │ 🟨 Gialli: <code>{amm}</code>\n───────────────────────────")
    
    query = f'"{nome}" {squadra} statistiche presenze gol assist transfermarkt'
    return f"📊 <b>STORICO WEB REALE: {html.escape(nome.upper())}</b>\n\n{fetch_real_web_data(query, 2)}"

def fetch_real_web_data(query, max_results=2):
    output = []
    try:
        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            for r in soup.find_all('div', class_='result__body')[:max_results]:
                snip = r.find('a', class_='result__snippet')
                tit = r.find('h2', class_='result__title')
                if snip and tit and tit.find('a'):
                    l = tit.find('a')['href']
                    if l.startswith('//duckduckgo.com/l/?uddg='): l = urllib.parse.unquote(l.split('uddg=')[1].split('&')[0])
                    output.append(f"🔎 <i>{html.escape(snip.text.strip())}</i>\n🔗 <b>Fonte:</b> <a href=\"{html.escape(l)}\">{html.escape(tit.find('a').text.strip())}</a>")
    except: pass
    if not output and WEB_SEARCH_ENABLED:
        try:
            for r in DDGS().text(query, max_results=max_results):
                output.append(f"🔎 <i>{html.escape(r['body'])}</i>\n🔗 <b>Fonte:</b> <a href=\"{html.escape(r['href'])}\">{html.escape(r['title'])}</a>")
        except: pass
    return "\n\n---\n\n".join(output) if output else "⚠️ Nessun dettaglio trovato."

def get_cartella_clinica_reale(nome, squadra=""):
    query = f'"{nome}" {squadra} infortunio tempi recupero SOS Fanta'
    return f"🏥 <b>CARTELLA CLINICA REALE: {html.escape(nome.upper())}</b>\n\n{fetch_real_web_data(query, 2)}"

# ==========================================
# FUNZIONI FORMAZIONE & GRAFICA
# ==========================================
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

    try: parts = [int(x) for x in schema.split("-")]; num_d, num_c, num_a = parts[0], parts[1], parts[2]
    except: num_d, num_c, num_a = 3, 4, 3

    y_p, y_d, y_c, y_a = img_h - 60, img_h - 220, img_h - 440, img_h - 660
    def calc_x(count): step = (img_w - 80) // (count + 1); return [40 + step * (i + 1) for i in range(count)]

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

def calcola_formazione_ideale(session, df):
    rosa = session.get('rosa', [])
    if not rosa: return "❌ <b>La tua rosa è vuota!</b>", None

    titolari = {'P': [], 'D': [], 'C': [], 'A': []}
    panchina = {'P': [], 'D': [], 'C': [], 'A': []}

    for p in rosa:
        st = find_player_in_stats(p['nome'])
        mv = float(str(st.get('Mv', 6.0)).replace(',','.')) if st is not None else 6.0
        fm = float(str(st.get('Fm', 6.0)).replace(',','.')) if st is not None else 6.0
        amm = int(st.get('Amm', 0)) if st is not None else 0
        power = fm + (mv - 6.0) - (amm * 0.05)
        if p.get('ruolo', 'C') in titolari:
            titolari[p.get('ruolo')].append({'nome': p['nome'], 'ruolo': p.get('ruolo'), 'power': power, 'fm': fm, 'amm': amm})

    for r in titolari: titolari[r] = sorted(titolari[r], key=lambda x: x['power'], reverse=True)

    p_tit, d_tit, c_tit, a_tit = titolari['P'][:1], titolari['D'][:3], titolari['C'][:4], titolari['A'][:3]
    for r in ['P', 'D', 'C', 'A']:
        used = [x['nome'] for x in p_tit + d_tit + c_tit + a_tit]
        panchina[r] = [x for x in titolari[r] if x['nome'] not in used]

    testo = "📋 <b>FORMAZIONE CONSIGLIATA (3-4-3)</b>\n━━━━━━━━━━━━━━━━━━━━━━\n<b>TITOLARI:</b>\n"
    testo += f"🧤 <b>P:</b> {p_tit[0]['nome'] if p_tit else 'Nessuno'}\n"
    testo += f"🛡️ <b>D:</b> {', '.join([x['nome'] for x in d_tit])}\n"
    testo += f"⚙️ <b>C:</b> {', '.join([x['nome'] for x in c_tit])}\n"
    testo += f"🎯 <b>A:</b> {', '.join([x['nome'] for x in a_tit])}\n\n<b>PANCHINA:</b>\n"
    
    for r in ['P', 'D', 'C', 'A']:
        if panchina[r]: testo += f"{ROLE_ICONS[r]} <b>{r}:</b> {', '.join([f'{x['nome']} (FM:{x['fm']})' for x in panchina[r][:3]])}\n"

    diff_alert = [f"⚠️ {x['nome']} ({x['amm']} gialli)" for x in p_tit + d_tit + c_tit + a_tit if x['amm'] >= 4]
    if diff_alert: testo += "\n🚨 <b>RADAR DIFFIDATI:</b>\n" + "\n".join(diff_alert)

    return testo, draw_pitch_image({'P': p_tit, 'D': d_tit, 'C': c_tit, 'A': a_tit}, "3-4-3")

def advanced_trade_analyzer_3d(p1, p2, session):
    base_report = f"📊 <b>TRADE ANALYZER:</b>\n{p1['Nome']} ↔️ {p2['Nome']}"
    r1, r2 = p1.get('R', 'C'), p2.get('R', 'C')
    count_r1 = sum(1 for p in session.get('rosa', []) if p.get('ruolo') == r1)
    count_r2 = sum(1 for p in session.get('rosa', []) if p.get('ruolo') == r2)
    
    impatti = []
    if r1 != r2:
        if count_r1 <= 3 and r1 in ['D', 'C']: impatti.append(f"🚨 <b>RISCHIO VOTI IN {r1}!</b> Rimarresti scoperto.")
        if count_r2 >= 8 and r2 in ['D', 'C']: impatti.append(f"⚠️ <b>SOVRACCOPPIAMENTO IN {r2}!</b>")
            
    return f"{base_report}\n\n📊 <b>IMPATTO SULLA ROSA (3D):</b>\n" + ("\n".join(impatti) if impatti else "✅ <b>EQUILIBRIO ROSA OK.</b>")

# ==========================================
# MENÙ PRINCIPALI & DASHBOARD
# ==========================================
def main_menu_keyboard(session):
    markup = InlineKeyboardMarkup(row_width=2)
    if session.get('asta_live'):
        markup.add(InlineKeyboardButton(f"🔴 TORNA ALL'ASTA (Fase {session.get('fase_attiva','P')})", callback_data=f"view_fase_{session.get('fase_attiva','P')}"))
        markup.add(InlineKeyboardButton("🛑 Termina Asta Live", callback_data="termina_asta_live"))
    else:
        markup.add(InlineKeyboardButton("🚀 INIZIO ASTA LIVE", callback_data="inizio_asta_live"))
        
    markup.add(InlineKeyboardButton("👕 Esplora", callback_data="sq_start"), InlineKeyboardButton("📋 La mia Rosa", callback_data="menu_rosa"))
    markup.add(InlineKeyboardButton("⚽ Formazione Ideale", callback_data="menu_formazione"), InlineKeyboardButton("🎯 Radar Rigoristi", callback_data="menu_rigoristi"))
    markup.add(InlineKeyboardButton("⭐ Wishlist", callback_data="menu_wishlist"), InlineKeyboardButton("📊 Trade 3D", callback_data="menu_studio_start"))
    markup.add(InlineKeyboardButton("🔥 Power Index (Forma)", callback_data="menu_power"), InlineKeyboardButton("🛡️ Modificatore 6.5", callback_data="menu_modificatore"))
    markup.add(InlineKeyboardButton("🏆 Top Liberi", callback_data="menu_top_start"), InlineKeyboardButton("💎 Gemme Nascoste", callback_data="menu_gemme_start"))
    markup.add(InlineKeyboardButton("🚨 Panic Button", callback_data="menu_panic_start"), InlineKeyboardButton("🛠️ Strumenti PRO", callback_data="menu_pro"))
    markup.add(InlineKeyboardButton("⚙️ Impostazioni Lega", callback_data="menu_impostazioni_lega"), InlineKeyboardButton("⚙️ Sistema", callback_data="menu_sistema"))
    return markup

def send_dashboard(chat_id, user_id, message_id=None):
    session = get_session(user_id)
    stats = get_roster_stats(session)
    salva_chat_id(chat_id)

    c, budget, slot = stats['counts'], session['budget'], stats['slot_liberi']
    media_str = f"(Media: {budget/slot:.1f} cr)" if slot > 0 else "✅ ROSA COMPLETA!"
    text = (
        "🏆 <b>FANTABOT PRO DASHBOARD</b> 📊\n━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Cassa:</b> <code> {budget} cr. </code>\n"
        f"🛍️ <b>Slot Liberi:</b> <code> {slot} </code> <i>{media_str}</i>\n"
        f"🛑 <b>MAX BID:</b> <code> {stats['max_bid']} cr. </code>\n\n"
        f"🧤 P: {c['P']}/3 │ 🛡️ D: {c['D']}/8\n⚙️ C: {c['C']}/8 │ 🎯 A: {c['A']}/6\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n💡 <i>Cerca un nome o manda un vocale per comprare!</i>"
    )
    if message_id:
        try: bot.edit_message_text(text, chat_id, message_id, parse_mode="HTML", reply_markup=main_menu_keyboard(session))
        except: bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=main_menu_keyboard(session))
    else: bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=main_menu_keyboard(session))

def send_player_card_view(chat_id, player_name, message_id, df, session):
    p_data = df[df['Nome'] == player_name].iloc[0]
    ruolo, fvm, sq = str(p_data.get('R', '-')), p_data.get('FVM', 0), p_data.get('Squadra', '-')
    
    try: fvm_val = float(str(fvm).replace(',', '.'))
    except ValueError: fvm_val = 0

    base_p = fvm_val * (session['lega_budget_iniziale'] / 1000.0)
    fair_price = max(1, int(base_p * (1 + ((session['lega_partecipanti'] - 8) * 0.025))))
    
    alert_rep = ""
    if session.get('asta_live'):
        bud_rep = session['budget_reparti'].get(ruolo, 0)
        slot_man = {'P':3, 'D':8, 'C':8, 'A':6}[ruolo] - get_roster_stats(session)['counts'][ruolo]
        if slot_man > 0:
            alert_rep = f"\n🛑 <b>SOGLIA SICUREZZA REPARTO ({ruolo}):</b> Max <code>{bud_rep - (slot_man - 1)} cr.</code>"

    text = (f"📋 <b>{html.escape(player_name.upper())}</b> ({get_team_icon(sq)} {sq})\n"
            f"📌 Ruolo: <code>{ruolo}</code> | FVM Base: {fvm}\n"
            f"💰 <b>Fair Price:</b> <code>{fair_price} cr.</code>{alert_rep}{get_macellaio_info(player_name)}\n\n"
            f"💼 <b>Tua Cassa:</b> <code>{session['budget']} cr.</code>")
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("⚡ Compra", callback_data=f"buy_{player_name}"), InlineKeyboardButton("🚫 Già Preso", callback_data=f"taken_{player_name}"))
    markup.add(InlineKeyboardButton("📊 Storico Reale", callback_data=f"stats_{player_name}"), InlineKeyboardButton("🏥 Clinica Web", callback_data=f"cl_{player_name}"))
    markup.add(InlineKeyboardButton("🔄 Sliding Doors", callback_data=f"sd_{player_name}"), InlineKeyboardButton("🔮 Simula What-If", callback_data=f"wi_{player_name}"))
    
    star = "❌ Rimuovi WL" if player_name in session.get('wishlist',[]) else "⭐ Aggiungi WL"
    markup.add(InlineKeyboardButton(star, callback_data=f"wl_toggle_{player_name}"), InlineKeyboardButton("🏠 Home", callback_data="go_home"))
    
    try: bot.edit_message_text(text, chat_id, message_id, parse_mode="HTML", reply_markup=markup)
    except: bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=markup)

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
    markup.add(*[InlineKeyboardButton(f"{get_team_icon(sq)} {sq}", callback_data=f"{prefisso}_sq_{sq}") for sq in sorted(df['Squadra'].dropna().astype(str).unique())])
    markup.add(InlineKeyboardButton("🔙 Home", callback_data="go_home"))
    return markup

def menu_seleziona_ruolo(squadra, prefisso):
    markup = InlineKeyboardMarkup(row_width=4)
    markup.add(*[InlineKeyboardButton(f"{ROLE_ICONS[r]} {r}", callback_data=f"{prefisso}_ru_{squadra}_{r}") for r in ['P', 'D', 'C', 'A']])
    markup.add(InlineKeyboardButton("🔙 Squadre", callback_data=f"{prefisso}_start"))
    return markup

def menu_seleziona_giocatore(df, squadra, ruolo, prefisso, user_id):
    markup = InlineKeyboardMarkup(row_width=1)
    for _, row in df[(df['Squadra'] == squadra) & (df['R'] == ruolo)].iterrows():
        star = "⭐ " if row['Nome'] in get_session(user_id).get('wishlist', []) else ""
        markup.add(InlineKeyboardButton(f"{star}{ROLE_ICONS.get(ruolo,'')} {row['Nome']} ─ FVM:{row.get('FVM', '-')}", callback_data=f"{prefisso}_pl_{row['Nome']}"))
    markup.add(InlineKeyboardButton("🔙 Cambia Ruolo", callback_data=f"{prefisso}_sq_{squadra}"))
    return markup

# ==========================================
# GESTIONE ASTA LIVE (NAVIGATORE TATTICO)
# ==========================================
def view_fase_portieri(chat_id, msg_id, df, session):
    session['fase_attiva'] = 'P'
    budget_p = session['budget_reparti']['P']
    
    top_p = []
    if STATS_CACHE is not None:
        for _, row in get_available_players(df[df['R']=='P'], session).iterrows():
            st = find_player_in_stats(row['Nome'])
            if st is not None:
                pv, mv, fm = int(st.get('Pv',0)), float(str(st.get('Mv',0)).replace(',','.')), float(str(st.get('Fm',0)).replace(',','.'))
                if pv >= 15 and fm > 5.0: top_p.append((row['Nome'], row['Squadra'], mv, fm))
    
    top_p = sorted(top_p, key=lambda x: x[3], reverse=True)[:5]
    
    txt = (f"🧤 <b>FASE PORTIERI ACTIVE</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
           f"💰 <b>Budget Reparto P:</b> <code>{budget_p} cr.</code> (su {session['budget']} tot)\n\n"
           "🏆 <b>TOP RENDIMENTO REALE (Dati Excel):</b>\n")
    markup = InlineKeyboardMarkup(row_width=1)
    for nome, sq, mv, fm in top_p:
        txt += f"• <b>{nome}</b> ({sq}) ─ MV: {mv} │ FM: {fm}\n"
        markup.add(InlineKeyboardButton(f"🧤 Analizza {nome} (Riserve/Incroci)", callback_data=f"p_strat_{nome}"))
        
    markup.add(InlineKeyboardButton("⏩ Chiudi Reparto Portieri", callback_data="chiudi_reparto_P"))
    markup.add(InlineKeyboardButton("🏠 Menu Principale (Lascia in Background)", callback_data="go_home"))
    bot.edit_message_text(txt, chat_id, msg_id, parse_mode="HTML", reply_markup=markup)

def view_p_strategia(chat_id, msg_id, nome_p, df, session):
    row = df[df['Nome'] == nome_p].iloc[0]
    sq = row['Squadra'].lower()
    
    txt = f"🛡️ <b>STRATEGIA COMPLETA: {nome_p.upper()}</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
    riserve = df[(df['Squadra'].str.lower() == sq) & (df['R'] == 'P') & (df['Nome'] != nome_p)]['Nome'].tolist()
    txt += f"🔒 <b>BLOCCO {sq.upper()}:</b> {' / '.join(riserve) if riserve else 'Nessuna'} (Consigliato: 1 cr. cad.)\n"
    
    incroci = {'inter': 'milan', 'milan': 'inter', 'roma': 'lazio', 'lazio': 'roma', 'juventus': 'torino', 'torino': 'juventus'}
    txt += f"🔀 <b>INCROCIO CASA/FUORI:</b> Portieri del <b>{incroci.get(sq, 'Sassuolo / Empoli').upper()}</b>\n"

    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton(f"⚡ Compra {nome_p}", callback_data=f"buy_{nome_p}"))
    markup.add(InlineKeyboardButton("🔙 Torna a Lista Portieri", callback_data="view_fase_P"))
    bot.edit_message_text(txt, chat_id, msg_id, parse_mode="HTML", reply_markup=markup)

def view_fase_generica(chat_id, msg_id, reparto, df, session):
    session['fase_attiva'] = reparto
    budget_rep = session['budget_reparti'][reparto]
    
    nomi_estesi = {'D': 'DIFENSORI (Modificatore)', 'C': 'CENTROCAMPISTI', 'A': 'ATTACCANTI'}
    txt = (f"{ROLE_ICONS[reparto]} <b>FASE {nomi_estesi[reparto]} ACTIVE</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
           f"💰 <b>Budget Reparto {reparto}:</b> <code>{budget_rep} cr.</code> (su {session['budget']} tot)\n\n"
           f"👉 Scegli lo strumento per dominare questo reparto:")
    
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton(f"🏆 Top Liberi {reparto}", callback_data=f"menu_top_ru_{reparto}"))
    if reparto == 'D': markup.add(InlineKeyboardButton("🛡️ Analizza Modificatore 6.5", callback_data="menu_modificatore"))
    markup.add(InlineKeyboardButton(f"💎 Gemme Nascoste {reparto}", callback_data=f"menu_gemme_ru_{reparto}"))
    markup.add(InlineKeyboardButton(f"🚨 Panic Button {reparto} (Tappabuchi)", callback_data=f"menu_panic_ru_{reparto}"))
    markup.add(InlineKeyboardButton(f"⏩ Chiudi Reparto {reparto}", callback_data=f"chiudi_reparto_{reparto}"))
    markup.add(InlineKeyboardButton("🏠 Menu Principale (Lascia in Background)", callback_data="go_home"))
    
    try: bot.edit_message_text(txt, chat_id, msg_id, parse_mode="HTML", reply_markup=markup)
    except: bot.send_message(chat_id, txt, parse_mode="HTML", reply_markup=markup)

def process_whatif_price(message, player_name, user_id):
    chat_id = message.chat.id
    if not message.text.isdigit(): return bot.register_next_step_handler(bot.send_message(chat_id, "❌ Inserisci un prezzo in <b>numeri</b>:", parse_mode="HTML"), process_whatif_price, player_name, user_id)

    hyp_price = int(message.text)
    session, df = get_session(user_id), load_data()
    row = df[df['Nome'] == player_name].iloc[0]
    ruolo = row.get('R', 'A')
    
    base_p = float(str(row.get('FVM', 0)).replace(',', '.')) * (session['lega_budget_iniziale'] / 1000.0)
    fair_price = max(1, int(base_p * (1 + ((session['lega_partecipanti'] - 8) * 0.025))))
    
    stats = get_roster_stats(session)
    budget_left = session['budget'] - hyp_price
    slots_left = stats['slot_liberi'] - 1
    if slots_left < 0: return bot.send_message(chat_id, "❌ Hai già la rosa piena!", parse_mode="HTML")
        
    analisi = f"🔥 <b>PREZZO D'OCCHIONE:</b> Valore reale: <code>{fair_price} cr.</code>" if hyp_price <= fair_price * 0.70 else (f"✅ <b>PREZZO CONGRUITA:</b> Fair Price: <code>{fair_price} cr.</code>" if hyp_price <= fair_price * 1.15 else f"🚨 <b>OVERPAY RISCHIOSO:</b> Sovrapprezzo di <code>{hyp_price - fair_price} cr.</code>")

    txt = (f"🔮 <b>WHAT-IF: {html.escape(player_name.upper())} a {hyp_price} cr.</b>\n━━━━━━━━━━━━━━━━━━━━━━\n{analisi}\n\n"
           f"💼 <b>IMPATTO BUDGET:</b>\n• Crediti Residui: <code>{budget_left} cr.</code>\n• Media rimanente: <code>{budget_left/slots_left if slots_left>0 else 0:.1f} cr.</code>")
    markup = InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 Indietro", callback_data=f"sq_pl_{player_name}"), InlineKeyboardButton("🏠 Home", callback_data="go_home"))
    bot.send_message(chat_id, txt, parse_mode="HTML", reply_markup=markup)

def process_buy_price(message, player_name, user_id):
    chat_id = message.chat.id
    if not message.text.isdigit(): return bot.register_next_step_handler(bot.send_message(chat_id, "❌ Inserisci <b>solo numeri</b>:", parse_mode="HTML"), process_buy_price, player_name, user_id)

    costo = int(message.text)
    session, df = get_session(user_id), load_data()
    if costo > get_roster_stats(session)['max_bid']:
        bot.send_message(chat_id, f"⚠️ <b>ALLARME!</b> Offerta oltre il Max Bid.", parse_mode="HTML")
        return send_dashboard(chat_id, user_id)

    row = df[df['Nome'] == player_name].iloc[0]
    ruolo = row.get('R', 'C')
    session['rosa'].append({'nome': player_name, 'prezzo': costo, 'ruolo': ruolo, 'squadra': row.get('Squadra', '-')})
    session['budget'] -= costo
    if session.get('asta_live'): session['budget_reparti'][ruolo] = max(0, session['budget_reparti'][ruolo] - costo)

    bot.send_message(chat_id, f"✅ <b>{html.escape(player_name.upper())}</b> preso a <code>{costo} cr.</code>!", parse_mode="HTML")
    
    if session.get('asta_live') and session.get('fase_attiva'):
        markup = InlineKeyboardMarkup().add(InlineKeyboardButton(f"🔙 Torna a Fase {session['fase_attiva']}", callback_data=f"view_fase_{session['fase_attiva']}"))
        bot.send_message(chat_id, "Navigatore Asta Live:", reply_markup=markup)
    else: send_dashboard(chat_id, user_id)

# ==========================================
# HANDLERS COMANDI DIRETTI E FILE
# ==========================================
@bot.message_handler(commands=['clean', 'pulisci'])
def cmd_clean(m):
    chat_id = m.chat.id
    for i in range(m.message_id, max(0, m.message_id - 80), -1):
        try: bot.delete_message(chat_id, i)
        except: pass
    send_dashboard(chat_id, m.from_user.id)

@bot.message_handler(commands=['start', 'menu'])
def cmd_start(m): 
    try: bot.delete_message(m.chat.id, m.message_id)
    except: pass
    send_dashboard(m.chat.id, m.from_user.id)

@bot.message_handler(content_types=['voice'])
def handle_voice(message):
    if not VOICE_ENABLED: return bot.reply_to(message, "❌ <b>Comandi Vocali disattivati.</b>", parse_mode="HTML")
    chat_id = message.chat.id
    bot.reply_to(message, "🎙️ Ascolto il vocale e traduco...")
    try:
        f_info = bot.get_file(message.voice.file_id)
        with open("voice.ogg", 'wb') as f: f.write(bot.download_file(f_info.file_path))
        AudioSegment.from_ogg("voice.ogg").export("voice.wav", format="wav")
        with sr.AudioFile("voice.wav") as source: testo = sr.Recognizer().recognize_google(sr.Recognizer().record(source), language="it-IT").lower()
        bot.send_message(chat_id, f"🗣️ Hai detto: <i>'{html.escape(testo)}'</i>", parse_mode="HTML")
        match = re.search(r'(?:preso|comprato|ho preso)?\s*([a-zA-Z\s]+)\s*(?:a|per)?\s*(\d+)', testo)
        if match:
            nome_voc, costo = match.group(1).strip(), int(match.group(2))
            df = load_data()
            matches = df[df['Nome'].astype(str).str.lower().str.contains(nome_voc, na=False)]
            if not matches.empty:
                bot.register_next_step_handler(bot.send_message(chat_id, f"🎯 Trovato: <b>{matches.iloc[0]['Nome']}</b>. Confermi a <code>{costo} cr.</code>?", parse_mode="HTML"), process_buy_price, matches.iloc[0]['Nome'], message.from_user.id)
            else: bot.send_message(chat_id, "❌ Nessun giocatore trovato.")
    except: bot.reply_to(message, "❌ Errore traduzione vocale.")

@bot.message_handler(func=lambda m: m.text.strip().startswith('+'))
def modalita_cecchino(message):
    chat_id, user_id = message.chat.id, message.from_user.id
    try:
        parts = message.text.strip()[1:].strip().rsplit(' ', 1)
        if len(parts) != 2 or not parts[1].isdigit(): return bot.reply_to(message, "❌ Usa: `+ nome prezzo`", parse_mode="Markdown")
        query_nome, costo = parts[0].lower(), int(parts[1])
        df = load_data()
        matches = df[df['Nome'].astype(str).str.lower().str.contains(query_nome, na=False)]
        if matches.empty: return bot.reply_to(message, "❌ Nessun giocatore trovato.")
        
        row = matches.iloc[0]
        player_name, ruolo = row['Nome'], row.get('R', 'C')
        session = get_session(user_id)
        if costo > get_roster_stats(session)['max_bid']: return bot.reply_to(message, "⚠️ Max Bid Superato!")
        
        session['rosa'].append({'nome': player_name, 'prezzo': costo, 'ruolo': ruolo, 'squadra': row.get('Squadra', '-')})
        session['budget'] -= costo
        if session.get('asta_live'): session['budget_reparti'][ruolo] = max(0, session['budget_reparti'][ruolo] - costo)

        bot.reply_to(message, f"🎯 <b>CECCHINO:</b> Acquistato <b>{html.escape(player_name.upper())}</b> a <code>{costo} cr.</code>", parse_mode="HTML")
    except: pass

@bot.message_handler(func=lambda m: not m.text.startswith('/') and not m.text.startswith('+') and not m.text.isdigit())
def search_player(message):
    query, df = message.text.strip().lower(), load_data()
    if df is None or len(query) < 2: return
    matches = df[df['Nome'].astype(str).str.lower().str.contains(query, na=False)].head(10)
    if matches.empty: return bot.reply_to(message, "❌ Nessun giocatore trovato.")
    markup = InlineKeyboardMarkup(row_width=1)
    for _, row in matches.iterrows(): markup.add(InlineKeyboardButton(f"{ROLE_ICONS.get(row['R'],'')} {row['Nome']} ({row['Squadra']})", callback_data=f"sq_pl_{row['Nome']}"))
    bot.reply_to(message, f"🔍 Risultati per <b>{html.escape(query)}</b>:", parse_mode="HTML", reply_markup=markup)

@bot.message_handler(content_types=['document'])
def handle_document(message):
    chat_id, fname = message.chat.id, message.document.file_name.lower()
    if not fname.endswith(('.csv', '.xlsx', '.xls')): return bot.reply_to(message, "❌ Invia solo `.csv` o `.xlsx`!", parse_mode="Markdown")
    try:
        f_info = bot.get_file(message.document.file_id)
        downloaded = bot.download_file(f_info.file_path)
        with open("Statistiche.xlsx" if "statistiche" in fname else "Lista-FantaAsta-Fantacalcio.csv", 'wb') as f: f.write(downloaded)
        load_data(force_reload=True)
        bot.reply_to(message, "✅ <b>DATI AGGIORNATI!</b>", parse_mode="HTML")
    except Exception as e: bot.send_message(chat_id, f"❌ Errore caricamento: {e}")

# ==========================================
# MAIN CALLBACK HANDLER (TUTTI I MENU RIATTIVATI)
# ==========================================
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    safe_answer_callback(call.id)
    user_id, chat_id, data = call.from_user.id, call.message.chat.id, call.data
    session, df = get_session(user_id), load_data()

    # --- COMANDI BASE ---
    if data == "clear_screen":
        curr_id = call.message.message_id
        for i in range(curr_id, max(0, curr_id - 80), -1):
            try: bot.delete_message(chat_id, i)
            except: pass
        send_dashboard(chat_id, user_id)
    elif data == "go_home": 
        session['compare_p1'] = None
        send_dashboard(chat_id, user_id, call.message.message_id)
    elif data == "force_download_listone":
        msg = bot.send_message(chat_id, "⏳ <i>Ricerca di mercato in corso...</i>", parse_mode="HTML")
        success = auto_download_and_inject_virtual_players()
        if success: bot.edit_message_text("✅ <b>DATABASE SINCRONIZZATO! Notifiche inviate.</b>", chat_id, msg.message_id, parse_mode="HTML")
        else: bot.edit_message_text("❌ <b>Sincronizzazione fallita.</b>", chat_id, msg.message_id, parse_mode="HTML")

    # --- MENU IMPOSTAZIONI LEGA ---
    elif data == "menu_impostazioni_lega":
        b_iniziale, part = session.get('lega_budget_iniziale', 500), session.get('lega_partecipanti', 12)
        markup = InlineKeyboardMarkup(row_width=3)
        markup.row(InlineKeyboardButton("💰 300", callback_data="imposta_bud_300"), InlineKeyboardButton("💰 500", callback_data="imposta_bud_500"), InlineKeyboardButton("💰 1000", callback_data="imposta_bud_1000"))
        markup.row(InlineKeyboardButton("👥 8 sq", callback_data="imposta_part_8"), InlineKeyboardButton("👥 10 sq", callback_data="imposta_part_10"), InlineKeyboardButton("👥 12 sq", callback_data="imposta_part_12"))
        markup.add(InlineKeyboardButton("🔄 Reset", callback_data="imposta_reset"), InlineKeyboardButton("🏠 Torna alla Home", callback_data="go_home"))
        bot.edit_message_text(f"⚙️ <b>IMPOSTAZIONI LEGA</b>\n💰 Budget: <code>{b_iniziale} cr.</code>\n👥 Partecipanti: <code>{part} squadre</code>", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)
    elif data.startswith("imposta_bud_"):
        val = int(data.replace("imposta_bud_", ""))
        session['lega_budget_iniziale'], session['budget'] = val, val
        safe_answer_callback(call.id, text=f"✅ Budget: {val} cr!", show_alert=True)
        call.data = "menu_impostazioni_lega"; handle_callbacks(call)
    elif data.startswith("imposta_part_"):
        val = int(data.replace("imposta_part_", ""))
        session['lega_partecipanti'] = val
        safe_answer_callback(call.id, text=f"✅ Partecipanti: {val}!", show_alert=True)
        call.data = "menu_impostazioni_lega"; handle_callbacks(call)
    elif data == "imposta_reset":
        session['lega_budget_iniziale'], session['lega_partecipanti'], session['budget'] = 500, 12, 500
        safe_answer_callback(call.id, text="✅ Lega resettata!", show_alert=True)
        call.data = "menu_impostazioni_lega"; handle_callbacks(call)

    # --- MODALITÀ ASTA LIVE ---
    elif data == "inizio_asta_live":
        session['asta_live'] = True
        recalcola_budget_reparti(session)
        view_fase_portieri(chat_id, call.message.message_id, df, session)
    elif data == "termina_asta_live":
        session['asta_live'] = False
        bot.edit_message_text("🏁 <b>ASTA LIVE DISATTIVATA!</b>", chat_id, call.message.message_id, parse_mode="HTML")
        send_dashboard(chat_id, user_id)
    elif data.startswith("view_fase_"):
        rep = data[-1]
        if rep == 'P': view_fase_portieri(chat_id, call.message.message_id, df, session)
        else: view_fase_generica(chat_id, call.message.message_id, rep, df, session)
    elif data.startswith("p_strat_"):
        view_p_strategia(chat_id, call.message.message_id, data.replace("p_strat_", ""), df, session)
    elif data.startswith("chiudi_reparto_"):
        rep_chiuso = data[-1]
        recalcola_budget_reparti(session) 
        prossimo_rep = {'P': 'D', 'D': 'C', 'C': 'A', 'A': 'Fine'}.get(rep_chiuso)
        session['fase_attiva'] = prossimo_rep
        if prossimo_rep == 'Fine':
            session['asta_live'] = False
            bot.edit_message_text("🏁 <b>ASTA CONCLUSA!</b> Tornando alla Home...", chat_id, call.message.message_id, parse_mode="HTML")
            send_dashboard(chat_id, user_id)
        else:
            txt = (f"⏩ <b>REPARTO {rep_chiuso} CHIUSO.</b> Ricalcolo completato!\nPassiamo al reparto <b>{prossimo_rep}</b>.\n"
                   f"💰 <b>Budget {prossimo_rep} Aggiornato:</b> <code>{session['budget_reparti'][prossimo_rep]} cr.</code>")
            markup = InlineKeyboardMarkup().add(InlineKeyboardButton(f"Vai alla Fase {prossimo_rep}", callback_data=f"view_fase_{prossimo_rep}")) 
            bot.edit_message_text(txt, chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    # --- VECCHI MENU RECUPERATI AL 100% ---
    elif data == "menu_formazione":
        testo_form, img_buf = calcola_formazione_ideale(session, df)
        markup = InlineKeyboardMarkup().add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        if img_buf: bot.send_photo(chat_id, img_buf, caption=testo_form, parse_mode="HTML", reply_markup=markup)
        else: bot.send_message(chat_id, testo_form, parse_mode="HTML", reply_markup=markup)
    elif data == "menu_rigoristi":
        testo = "🎯 <b>RADAR RIGORISTI</b>\n"
        for sq, dati in GERARCHIE_RIGORISTI.items(): testo += f"<b>{sq}:</b> Rig: {', '.join(dati['rigoristi'])}\n"
        bot.edit_message_text(testo, chat_id, call.message.message_id, parse_mode="HTML", reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🏠 Home", callback_data="go_home")))
    elif data == "menu_power":
        rosa, hot_players = session.get('rosa', []), []
        for p in rosa:
            st = find_player_in_stats(p['nome'])
            if st is not None and float(str(st.get('Fm', 6.0)).replace(',', '.')) >= 6.8: hot_players.append(f"🔥 <b>{p['nome']}</b>")
        testo = "🔥 <b>POWER INDEX</b>\n" + ("\n".join(hot_players) if hot_players else "Nessun giocatore in stato di grazia.")
        bot.edit_message_text(testo, chat_id, call.message.message_id, parse_mode="HTML", reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🏠 Home", callback_data="go_home")))
    elif data == "menu_sistema": bot.edit_message_text("⚙️ <b>OPZIONI SISTEMA</b>", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=system_menu_keyboard())
    elif data == "reload_excel": 
        load_data(force_reload=True); bot.send_message(chat_id, "⚡ Dati sincronizzati!", parse_mode="HTML")
    elif data == "reset_confirm":
        b_in, part = session.get('lega_budget_iniziale', 500), session.get('lega_partecipanti', 12)
        user_sessions[user_id] = {'budget': b_in, 'rosa': [], 'wishlist': session.get('wishlist', []), 'scartati': [], 'compare_p1': None, 'lega_budget_iniziale': b_in, 'lega_partecipanti': part, 'asta_live': False, 'budget_reparti': {'P': 30, 'D': 75, 'C': 125, 'A': 270}}
        send_dashboard(chat_id, user_id, call.message.message_id)
    elif data == "menu_pro": bot.edit_message_text("🛠️ <b>STRUMENTI PRO</b>", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=pro_menu_keyboard())

    # --- STRUMENTI PRO ---
    elif data == "pro_stakanov":
        staka = get_available_players(df, session)[get_available_players(df, session)['R'].isin(['D', 'C'])].sort_values(by='FVM', ascending=True).head(15)
        markup = InlineKeyboardMarkup(row_width=1)
        for _, row in staka.iterrows(): markup.add(InlineKeyboardButton(f"🧱 {row['Nome']} ({row['Squadra']})", callback_data=f"sq_pl_{row['Nome']}"))
        markup.add(InlineKeyboardButton("🔙 Menu PRO", callback_data="menu_pro"))
        bot.edit_message_text("🧱 <b>STAKANOVISTI (Low Cost sicuri)</b>", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)
    elif data == "pro_griglia":
        markup = InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 Menu PRO", callback_data="menu_pro"))
        bot.edit_message_text("🕸️ <b>GRIGLIA PERFETTA DIFESA</b>\nIl bot suggerisce incroci per il Modificatore.", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)
    elif data == "pro_spiccioli":
        avail = get_available_players(df, session).sort_values(by='FVM', ascending=True).head(15)
        markup = InlineKeyboardMarkup(row_width=1)
        for _, row in avail.iterrows(): markup.add(InlineKeyboardButton(f"🎰 {row['Nome']} ({row['R']} - {row['Squadra']})", callback_data=f"sq_pl_{row['Nome']}"))
        markup.add(InlineKeyboardButton("🔙 Menu PRO", callback_data="menu_pro"))
        bot.edit_message_text("🎰 <b>ULTIMI SPICCIOLI LOW-COST</b>", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    # --- ESPLORA, MENU ROSE E WISHLIST ---
    elif data == "menu_rosa":
        rosa = session.get('rosa', [])
        if not rosa: text = "📋 <b>LA TUA ROSA È VUOTA!</b>"
        else:
            text = "📋 <b>LA TUA ROSA:</b>\n"
            for r in ['P', 'D', 'C', 'A']:
                giocatori_r = [p for p in rosa if p.get('ruolo') == r]
                if giocatori_r:
                    text += f"\n<b>{ROLE_ICONS[r]} {r}:</b>\n"
                    for p in giocatori_r: text += f"• {html.escape(p['nome'])} (<code>{p['prezzo']} cr.</code>)\n"
        bot.edit_message_text(text, chat_id, call.message.message_id, parse_mode="HTML", reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🏠 Home", callback_data="go_home")))
    elif data == "menu_wishlist":
        wishlist = session.get('wishlist', [])
        markup = InlineKeyboardMarkup(row_width=1)
        if not wishlist: testo = "⭐ <b>WISHLIST VUOTA</b>"
        else:
            testo = "⭐ <b>LA TUA WISHLIST:</b>\n"
            for nome in wishlist: markup.add(InlineKeyboardButton(f"🔍 {nome}", callback_data=f"sq_pl_{nome}"))
        markup.add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text(testo, chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)
    
    elif data == "sq_start": bot.edit_message_text("👕 <b>ESPLORA SQUADRE</b>", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=menu_seleziona_squadra(df, "sq"))
    elif data.startswith("sq_sq_"): bot.edit_message_text("Scegli il ruolo:", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=menu_seleziona_ruolo(data.replace("sq_sq_", ""), "sq"))
    elif data.startswith("sq_ru_"):
        _, _, sq, ru = data.split("_")
        bot.edit_message_text(f"Giocatori ({sq} - {ru}):", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=menu_seleziona_giocatore(df, sq, ru, "sq", user_id))

    # --- TOP, GEMME, PANIC, MODIFICATORE ---
    elif data == "menu_top_start":
        markup = InlineKeyboardMarkup(row_width=4).add(*[InlineKeyboardButton(f"{ROLE_ICONS[r]} {r}", callback_data=f"menu_top_ru_{r}") for r in ['P', 'D', 'C', 'A']])
        markup.add(InlineKeyboardButton("🔙 Home", callback_data="go_home"))
        bot.edit_message_text("🏆 <b>TOP LIBERI - Scegli il ruolo:</b>", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)
    elif data.startswith("menu_top_ru_"):
        r = data.split("_")[-1]
        avail = get_available_players(df, session)
        top = avail[avail['R'] == r].sort_values(by='FVM', ascending=False).head(15)
        markup = InlineKeyboardMarkup(row_width=1)
        for _, row in top.iterrows(): markup.add(InlineKeyboardButton(f"🔍 {row['Nome']} ({row['Squadra']}) FVM:{row['FVM']}", callback_data=f"sq_pl_{row['Nome']}"))
        if session.get('asta_live'): markup.add(InlineKeyboardButton(f"🔙 Torna a Fase {r}", callback_data=f"view_fase_{r}"))
        markup.add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text(f"🏆 <b>TOP LIBERI {ROLE_ICONS[r]} {r}</b>\n", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif data == "menu_gemme_start":
        markup = InlineKeyboardMarkup(row_width=4).add(*[InlineKeyboardButton(f"{ROLE_ICONS[r]} {r}", callback_data=f"menu_gemme_ru_{r}") for r in ['P', 'D', 'C', 'A']])
        markup.add(InlineKeyboardButton("🔙 Home", callback_data="go_home"))
        bot.edit_message_text("💎 <b>GEMME NASCOSTE - Scegli il ruolo:</b>", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)
    elif data.startswith("menu_gemme_ru_"):
        r = data.split("_")[-1]
        gemme = get_available_players(df, session)[(get_available_players(df, session)['R'] == r) & (get_available_players(df, session)['FVM'] <= 20) & (get_available_players(df, session)['FVM'] >= 6)].sort_values(by='FVM', ascending=False).head(15)
        markup = InlineKeyboardMarkup(row_width=1)
        for _, row in gemme.iterrows(): markup.add(InlineKeyboardButton(f"💎 {row['Nome']} ({row.get('Squadra','-')}) FVM:{row.get('FVM','-')}", callback_data=f"sq_pl_{row['Nome']}"))
        if session.get('asta_live'): markup.add(InlineKeyboardButton(f"🔙 Torna a Fase {r}", callback_data=f"view_fase_{r}"))
        markup.add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text(f"💎 <b>GEMME NASCOSTE {ROLE_ICONS[r]} {r}</b>", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif data == "menu_panic_start":
        markup = InlineKeyboardMarkup(row_width=4).add(*[InlineKeyboardButton(f"{ROLE_ICONS[r]} {r}", callback_data=f"menu_panic_ru_{r}") for r in ['P', 'D', 'C', 'A']])
        markup.add(InlineKeyboardButton("🔙 Home", callback_data="go_home"))
        bot.edit_message_text("🚨 <b>PANIC BUTTON - Scegli il ruolo:</b>", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)
    elif data.startswith("menu_panic_ru_"):
        r = data.split("_")[-1]
        panic = get_available_players(df, session)[(get_available_players(df, session)['R'] == r) & (get_available_players(df, session)['FVM'] <= 5)].sort_values(by='FVM', ascending=False).head(15)
        markup = InlineKeyboardMarkup(row_width=1)
        for _, row in panic.iterrows(): markup.add(InlineKeyboardButton(f"🚨 {row['Nome']} ({row.get('Squadra','-')}) FVM:{row.get('FVM','-')}", callback_data=f"sq_pl_{row['Nome']}"))
        if session.get('asta_live'): markup.add(InlineKeyboardButton(f"🔙 Torna a Fase {r}", callback_data=f"view_fase_{r}"))
        markup.add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text(f"🚨 <b>PANIC BUTTON {ROLE_ICONS[r]} {r}</b>", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif data == "menu_modificatore":
        mods = get_available_players(df, session)[get_available_players(df, session)['R'] == 'D'].sort_values(by='FVM', ascending=False).head(15)
        markup = InlineKeyboardMarkup(row_width=1)
        for _, row in mods.iterrows(): markup.add(InlineKeyboardButton(f"🛡️ {row['Nome']} (FVM: {row['FVM']})", callback_data=f"sq_pl_{row['Nome']}"))
        if session.get('asta_live'): markup.add(InlineKeyboardButton("🔙 Torna a Fase D", callback_data="view_fase_D"))
        markup.add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text("🛡️ <b>MODIFICATORE 6.5</b>", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    # --- AZIONI GIOCATORE, SCHEDE E WHAT-IF ---
    elif data.startswith("sq_pl_"): send_player_card_view(chat_id, data.replace("sq_pl_", ""), call.message.message_id, df, session)
    elif data.startswith("buy_"): bot.register_next_step_handler(bot.send_message(chat_id, f"💰 Costo per <b>{data.replace('buy_', '')}</b>?:", parse_mode="HTML"), process_buy_price, data.replace("buy_", ""), user_id)
    elif data.startswith("taken_"):
        session['scartati'].append(data.replace("taken_", ""))
        safe_answer_callback(call.id, text="🚫 Rimosso!", show_alert=True)
        if session.get('asta_live') and session.get('fase_attiva'): view_fase_generica(chat_id, call.message.message_id, session['fase_attiva'], df, session)
    
    elif data.startswith("stats_"):
        p_name = data.replace("stats_", "")
        p_row = df[df['Nome'] == p_name].iloc[0]
        markup = InlineKeyboardMarkup(row_width=2).add(InlineKeyboardButton("🔙 Indietro", callback_data=f"sq_pl_{p_name}"), InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text(get_storico_excel_o_web(p_name, p_row.get('Squadra', '')), chat_id, call.message.message_id, parse_mode="HTML", disable_web_page_preview=True, reply_markup=markup)
    
    elif data.startswith("cl_"):
        p_name = data.replace("cl_", "")
        p_row = df[df['Nome'] == p_name].iloc[0]
        bot.edit_message_text(get_cartella_clinica_reale(p_name, p_row.get('Squadra', '')), chat_id, call.message.message_id, parse_mode="HTML", disable_web_page_preview=True, reply_markup=InlineKeyboardMarkup(row_width=2).add(InlineKeyboardButton("🔙 Indietro", callback_data=f"sq_pl_{p_name}"), InlineKeyboardButton("🏠 Home", callback_data="go_home")))
    
    elif data.startswith("sd_"):
        p_name = data.replace("sd_", "")
        row = df[df['Nome'] == p_name].iloc[0]
        avail = get_available_players(df, session)
        same_role = avail[(avail['R'] == row['R']) & (avail['Nome'] != p_name)].copy()
        same_role['diff_fvm'] = abs(same_role['FVM'] - float(row.get('FVM', 0)))
        markup = InlineKeyboardMarkup(row_width=1)
        for _, cl_row in same_role.sort_values(by=['diff_fvm', 'FVM'], ascending=[True, False]).head(4).iterrows():
            markup.add(InlineKeyboardButton(f"🔄 {cl_row['Nome']} ({cl_row['Squadra']}) FVM:{cl_row['FVM']}", callback_data=f"sq_pl_{cl_row['Nome']}"))
        markup.add(InlineKeyboardButton("🔙 Indietro", callback_data=f"sq_pl_{p_name}"))
        try: bot.delete_message(chat_id, call.message.message_id)
        except: pass
        bot.send_message(chat_id, f"🔄 <b>SLIDING DOORS per {html.escape(p_name)}:</b>", parse_mode="HTML", reply_markup=markup)

    elif data.startswith("wi_"):
        bot.register_next_step_handler(bot.send_message(chat_id, f"🔮 Simulatore WHAT-IF per {data.replace('wi_', '')}. Che prezzo fittizio inserisco?", parse_mode="HTML"), process_whatif_price, data.replace("wi_", ""), user_id)

    elif data.startswith("wl_toggle_"):
        p_name = data.replace("wl_toggle_", "")
        if p_name in session['wishlist']: session['wishlist'].remove(p_name)
        else: session['wishlist'].append(p_name)
        send_player_card_view(chat_id, p_name, call.message.message_id, df, session)

    # --- STUDIO E TRADE 3D ---
    elif data == "menu_studio_start":
        session['compare_p1'] = None
        bot.edit_message_text("📊 <b>STUDIO & TRADE ANALYZER 3D</b>\nSeleziona la squadra del TUO giocatore:", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=menu_seleziona_squadra(df, "std1"))
    elif data.startswith("std1_sq_"): bot.edit_message_text("Scegli il ruolo:", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=menu_seleziona_ruolo(data.replace("std1_sq_", ""), "std1"))
    elif data.startswith("std1_ru_"): _, _, sq, ru = data.split("_"); bot.edit_message_text("Selezionalo:", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=menu_seleziona_giocatore(df, sq, ru, "std1", user_id))
    elif data.startswith("std1_pl_"):
        session['compare_p1'] = df[df['Nome'] == data.replace("std1_pl_", "")].iloc[0].to_dict()
        markup = InlineKeyboardMarkup(row_width=2).add(*[InlineKeyboardButton(f"{get_team_icon(sq)} {sq}", callback_data=f"std2_sq_{sq}") for sq in sorted(df['Squadra'].dropna().astype(str).unique())])
        bot.edit_message_text("📊 Ora seleziona la squadra del GIOCATORE PROPOSTO:", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)
    elif data.startswith("std2_sq_"):
        sq2, p1 = data.replace("std2_sq_", ""), session.get('compare_p1')
        markup = InlineKeyboardMarkup(row_width=1)
        for _, row in df[(df['Squadra'] == sq2) & (df['R'] == p1['R']) & (df['Nome'] != p1['Nome'])].iterrows(): markup.add(InlineKeyboardButton(f"🆚 Confronta con {row['Nome']}", callback_data=f"std2_pl_{row['Nome']}"))
        bot.edit_message_text("📊 Scegli il GIOCATORE PROPOSTO:", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)
    elif data.startswith("std2_pl_"):
        p1, p2 = session.get('compare_p1'), df[df['Nome'] == data.replace("std2_pl_", "")].iloc[0].to_dict()
        markup = InlineKeyboardMarkup(row_width=2).add(InlineKeyboardButton(f"⚡ Compra {p1['Nome']}", callback_data=f"buy_{p1['Nome']}"), InlineKeyboardButton(f"⚡ Compra {p2['Nome']}", callback_data=f"buy_{p2['Nome']}"))
        markup.add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text(advanced_trade_analyzer_3d(p1, p2, session), chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

if __name__ == '__main__':
    threading.Thread(target=run_flask, daemon=True).start()
    try: bot.remove_webhook()
    except: pass
    print("🚀 FANTABOT PRO LIVE ONLINE!")
    bot.infinity_polling(timeout=10, long_polling_timeout=5, skip_pending=True)
