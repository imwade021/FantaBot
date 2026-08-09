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

# URL UFFICIALE DOWNLOAD LISTONE FANTACALCIO (Excel/CSV)
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

GIOCATORI_VIRTUALI = [
    {'Id': 9999, 'Nome_Breve': 'Mastantuono', 'Nome': 'Franco Mastantuono', 'R': 'A', 'Ruolo_Esteso': 'Ala Destra', 'Qt.A': 15, 'Qt.I': 15, 'Qt.M': 15, 'Diff.M': 0, 'Squadra': 'Fiorentina', 'FVM': 45, 'FVM.M': 45, 'Piede': 'Sinistro', 'Nazionalita': 'Argentina', 'DataNascita': '14/08/2007', 'PhotoURL': 'https://tmssl.akamaized.net/images/portrait/header/1138580-1708518330.jpg'}
]

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
# AUTO-DOWNLOADER, PUSH & GESTIONE DATABASE
# ==========================================
DATA_CACHE = None
STATS_CACHE = None
REGISTERED_CHATS = set()
NOTIFIED_VIRTUALS = set()

def salva_chat_id(chat_id):
    REGISTERED_CHATS.add(chat_id)

def auto_download_and_inject_virtual_players():
    """Scarica in automatico il listone aggiornato, inietta virtuali e notifica via push."""
    global NOTIFIED_VIRTUALS
    print("🔄 Avvio download automatico del Listone e ricerca di mercato...")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        res = requests.get(LISTONE_URL, headers=headers, timeout=15)
        if res.status_code == 200:
            with open("Lista-FantaAsta-Fantacalcio.csv", "wb") as f:
                f.write(res.content)
            print("✅ Listone aggiornato con successo da remoto!")
    except Exception as e:
        print(f"❌ Errore durante l'auto-download: {e}")

    load_data(force_reload=True)

    # Notifiche Push
    for g in GIOCATORI_VIRTUALI:
        if g['Nome'] not in NOTIFIED_VIRTUALS:
            NOTIFIED_VIRTUALS.add(g['Nome'])
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

def load_data(force_reload=False):
    global DATA_CACHE, STATS_CACHE
    if DATA_CACHE is None or force_reload:
        df_temp = None
        if os.path.exists("Lista-FantaAsta-Fantacalcio.csv"):
            try:
                df_temp = pd.read_csv("Lista-FantaAsta-Fantacalcio.csv", header=None)
                df_temp.columns = [
                    'Id', 'Nome_Breve', 'Nome', 'R', 'Ruolo_Esteso', 'Qt.A', 'Qt.I', 
                    'Qt.M', 'Diff.M', 'Squadra', 'FVM', 'FVM.M', 'Piede', 'Nazionalita', 
                    'DataNascita', 'PhotoURL', 'Extra1', 'Extra2', 'Extra3'
                ]
                df_temp['FVM'] = pd.to_numeric(df_temp['FVM'], errors='coerce').fillna(0)
                print("✅ File CSV Listone caricato in memoria!")
            except Exception as e: print(f"⚠️ Errore lettura CSV Listone: {e}")

        if df_temp is not None:
            to_add = []
            for g in GIOCATORI_VIRTUALI:
                if df_temp[df_temp['Nome'].astype(str).str.contains(g['Nome_Breve'], case=False, na=False)].empty:
                    to_add.append(g)
            
            if to_add:
                df_temp = pd.concat([df_temp, pd.DataFrame(to_add)], ignore_index=True)
            
            DATA_CACHE = df_temp

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
                print(f"✅ File {stats_file} caricato e indicizzato con successo!")
            except Exception as e: print(f"⚠️ Errore lettura {stats_file}: {e}")

    return DATA_CACHE

# Caricamento iniziale e avvio Pianificatore
load_data()
try:
    scheduler = BackgroundScheduler()
    scheduler.add_job(auto_download_and_inject_virtual_players, 'interval', minutes=60)
    scheduler.start()
    print("⏰ Pianificatore Auto-Download attivo (Esecuzione ogni 60 minuti)")
except Exception as e:
    print(f"⚠️ Impossibile avviare il pianificatore: {e}")

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
            'lega_partecipanti': 8,
            'asta_live': False, 
            'fase_attiva': None,
            'usa_modificatore': False,
            'pesi_reparti': {'P': 8, 'D': 10, 'C': 28, 'A': 54},
            'budget_reparti': {'P': 40, 'D': 50, 'C': 140, 'A': 270}
        }
    return user_sessions[user_id]

def recalcola_budget_reparti(session):
    cassa = session['budget']
    count_r = {'P': 0, 'D': 0, 'C': 0, 'A': 0}
    for p in session.get('rosa', []): count_r[p.get('ruolo', 'C')] += 1
    
    fasi = []
    if count_r['P'] < 3: fasi.append('P')
    if count_r['D'] < 8: fasi.append('D')
    if count_r['C'] < 8: fasi.append('C')
    if count_r['A'] < 6: fasi.append('A')

    pesi = session.get('pesi_reparti', {'P': 8, 'D': 10, 'C': 28, 'A': 54})
    peso_tot = sum(pesi[r] for r in fasi)
    
    if peso_tot > 0:
        for r in fasi: session['budget_reparti'][r] = int(cassa * (pesi[r] / peso_tot))

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

    if not output and WEB_SEARCH_ENABLED:
        try:
            results = DDGS().text(query, max_results=max_results)
            for r in results:
                testo = html.escape(r['body'])
                titolo = html.escape(r['title'])
                link = html.escape(r['href'])
                output.append(f"🔎 <i>{testo}</i>\n🔗 <b>Fonte:</b> <a href=\"{link}\">{titolo}</a>")
        except Exception as e: print(f"Errore DDGS: {e}")

    if output: return "\n\n---\n\n".join(output)
    return "⚠️ Nessun dettaglio rilevante trovato sul web."

def get_cartella_clinica_reale(nome, squadra=""):
    query = f'"{nome}" {squadra} infortunio tempi recupero rientro partite saltate SOS Fanta'
    return f"🏥 <b>CARTELLA CLINICA REALE: {html.escape(nome.upper())} ({html.escape(squadra)})</b>\n\n{fetch_real_web_data(query, max_results=2)}"

# ==========================================
# GENERATORE GRAFICO DEL CAMPO (PILLOW)
# ==========================================
def draw_pitch_image(titolari_by_role, schema="3-4-3"):
    if not PIL_ENABLED:
        return None
    
    img_w, img_h = 600, 800
    image = Image.new("RGB", (img_w, img_h), "#2e7d32")
    draw = ImageDraw.Draw(image)
    
    draw.rectangle([20, 20, img_w - 20, img_h - 20], outline="white", width=3)
    draw.line([20, img_h // 2, img_w - 20, img_h // 2], fill="white", width=2)
    draw.ellipse([img_w // 2 - 60, img_h // 2 - 60, img_w // 2 + 60, img_h // 2 + 60], outline="white", width=2)
    draw.rectangle([150, 20, img_w - 150, 140], outline="white", width=2)
    draw.rectangle([150, img_h - 140, img_w - 150, img_h - 20], outline="white", width=2)

    try:
        parts = [int(x) for x in schema.split("-")]
        num_d, num_c, num_a = parts[0], parts[1], parts[2]
    except Exception:
        num_d, num_c, num_a = 3, 4, 3

    y_p, y_d, y_c, y_a = img_h - 60, img_h - 220, img_h - 440, img_h - 660

    def calc_x_positions(count):
        step = (img_w - 80) // (count + 1)
        return [40 + step * (i + 1) for i in range(count)]

    coords = []
    if titolari_by_role.get('P'):
        coords.append((titolari_by_role['P'][0]['nome'], img_w // 2, y_p, "🧤"))
        
    d_x = calc_x_positions(num_d)
    for i, p in enumerate(titolari_by_role.get('D', [])[:num_d]):
        coords.append((p['nome'], d_x[i], y_d, "🛡️"))

    c_x = calc_x_positions(num_c)
    for i, p in enumerate(titolari_by_role.get('C', [])[:num_c]):
        coords.append((p['nome'], c_x[i], y_c, "⚙️"))

    a_x = calc_x_positions(num_a)
    for i, p in enumerate(titolari_by_role.get('A', [])[:num_a]):
        coords.append((p['nome'], a_x[i], y_a, "🎯"))

    for nome, x, y, icon in coords:
        draw.ellipse([x - 22, y - 22, x + 22, y + 22], fill="#1b5e20", outline="white", width=2)
        draw.text((x - 8, y - 10), icon, fill="white")
        display_name = nome.split()[0][:8]
        draw.rectangle([x - 35, y + 24, x + 35, y + 40], fill="black")
        draw.text((x - 30, y + 26), display_name, fill="white")

    buf = io.BytesIO()
    image.save(buf, format='PNG')
    buf.seek(0)
    return buf

# ==========================================
# TRADE ANALYZER 3D & FORMAZIONE
# ==========================================
def advanced_trade_analyzer_3d(p1, p2, session):
    base_report = f"📊 <b>TRADE ANALYZER:</b>\n{p1['Nome']} ↔️ {p2['Nome']}"
    rosa = session.get('rosa', [])
    r1, r2 = p1.get('R', 'C'), p2.get('R', 'C')
    count_r1 = sum(1 for p in rosa if p.get('ruolo') == r1)
    count_r2 = sum(1 for p in rosa if p.get('ruolo') == r2)
    
    fvm1 = pd.to_numeric(p1.get('FVM', 0), errors='coerce')
    fvm2 = pd.to_numeric(p2.get('FVM', 0), errors='coerce')
    if pd.isna(fvm1): fvm1 = 0
    if pd.isna(fvm2): fvm2 = 0
    
    impatti_rosa = []
    
    # Analisi Strutturale Reparto
    if r1 != r2:
        if count_r1 <= 3 and r1 in ['D', 'C']:
            impatti_rosa.append(f"🚨 <b>RISCHIO NUMERICO IN {r1}!</b> Rimarresti troppo scoperto nel ruolo.")
        if count_r2 >= 8 and r2 in ['D', 'C']:
            impatti_rosa.append(f"⚠️ <b>SOVRACCOPPIAMENTO IN {r2}!</b> Hai già molti giocatori in questo reparto.")
            
    # Analisi FVM (Valore di mercato intelligente)
    diff_fvm = fvm1 - fvm2
    if diff_fvm > 12:
        impatti_rosa.append(f"🛑 <b>SCAMBIO A PERDERE:</b> Stai regalando un giocatore che vale molto di più ({fvm1} cr. vs {fvm2} cr.).")
    elif diff_fvm < -12:
        impatti_rosa.append(f"🔥 <b>AFFARE D'ORO:</b> Accetta subito! Guadagni nettamente in valore assoluto ({fvm1} cr. vs {fvm2} cr.).")
    else:
        impatti_rosa.append(f"⚖️ <b>VALORE EQUILIBRATO:</b> I due giocatori hanno un FVM simile ({fvm1} cr. vs {fvm2} cr.).")
            
    impatti_txt = "\n".join(impatti_rosa) if impatti_rosa else "✅ <b>EQUILIBRIO ROSA OK.</b>"
    return f"{base_report}\n\n📊 <b>IMPATTO SULLA ROSA (3D):</b>\n{impatti_txt}"

def calcola_formazione_ideale(session, df):
    rosa = session.get('rosa', [])
    if not rosa:
        return "❌ <b>La tua rosa è vuota!</b> Acquista o aggiungi giocatori.", None

    titolari_by_role = {'P': [], 'D': [], 'C': [], 'A': []}
    panchina_by_role = {'P': [], 'D': [], 'C': [], 'A': []}

    for p in rosa:
        nome = p['nome']
        r = p.get('ruolo', 'C')
        stats = find_player_in_stats(nome)
        
        mv = float(str(stats.get('Mv', 6.0)).replace(',', '.')) if stats is not None else 6.0
        fm = float(str(stats.get('Fm', 6.0)).replace(',', '.')) if stats is not None else 6.0
        pv = int(stats.get('Pv', 0)) if stats is not None else 0
        amm = int(stats.get('Amm', 0)) if stats is not None else 0
        
        power_index = fm + (mv - 6.0) - (amm * 0.05)
        p_obj = {'nome': nome, 'ruolo': r, 'squadra': p.get('squadra', '-'), 'power': power_index, 'mv': mv, 'fm': fm, 'pv': pv, 'amm': amm}
        if r in titolari_by_role: titolari_by_role[r].append(p_obj)

    for r in titolari_by_role:
        titolari_by_role[r] = sorted(titolari_by_role[r], key=lambda x: x['power'], reverse=True)

    p_tit, d_tit = titolari_by_role['P'][:1], titolari_by_role['D'][:3]
    c_tit, a_tit = titolari_by_role['C'][:4], titolari_by_role['A'][:3]

    for r in ['P', 'D', 'C', 'A']:
        used_names = [x['nome'] for x in p_tit + d_tit + c_tit + a_tit]
        panchina_by_role[r] = [x for x in titolari_by_role[r] if x['nome'] not in used_names]

    tit_dict = {'P': p_tit, 'D': d_tit, 'C': c_tit, 'A': a_tit}
    
    testo = "📋 <b>FORMAZIONE CONSIGLIATA (3-4-3)</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
    testo += "<b>TITOLARI:</b>\n"
    testo += f"🧤 <b>P:</b> {p_tit[0]['nome'] if p_tit else 'Nessuno'}\n"
    testo += f"🛡️ <b>D:</b> {', '.join([x['nome'] for x in d_tit])}\n"
    testo += f"⚙️ <b>C:</b> {', '.join([x['nome'] for x in c_tit])}\n"
    testo += f"🎯 <b>A:</b> {', '.join([x['nome'] for x in a_tit])}\n\n"
    
    testo += "<b>PANCHINA (Copertura Garantita):</b>\n"
    for r in ['P', 'D', 'C', 'A']:
        if panchina_by_role[r]:
            p_names = [f"{x['nome']} (FM:{x['fm']})" for x in panchina_by_role[r][:3]]
            testo += f"{ROLE_ICONS[r]} <b>{r}:</b> {', '.join(p_names)}\n"

    diffidati_alert = [f"⚠️ {x['nome']} ({x['amm']} gialli)" for x in p_tit + d_tit + c_tit + a_tit if x['amm'] >= 4]
    if diffidati_alert:
        testo += "\n🚨 <b>RADAR DIFFIDATI:</b>\n" + "\n".join(diffidati_alert)

    img_buf = draw_pitch_image(tit_dict, "3-4-3")
    return testo, img_buf

# ==========================================
# CARDS E DASHBOARD
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
    markup.add(InlineKeyboardButton("⭐ Wishlist", callback_data="menu_wishlist"), InlineKeyboardButton("📊 Studio & Trade 3D", callback_data="menu_studio_start"))
    markup.add(InlineKeyboardButton("🔥 Power Index (Forma)", callback_data="menu_power"), InlineKeyboardButton("🛡️ Modificatore 6.5", callback_data="menu_modificatore"))
    markup.add(InlineKeyboardButton("🏆 Top Liberi", callback_data="menu_top_start"), InlineKeyboardButton("💎 Gemme Nascoste", callback_data="menu_gemme_start"))
    markup.add(InlineKeyboardButton("🚨 Panic Button", callback_data="menu_panic_start"), InlineKeyboardButton("🛠️ Strumenti PRO", callback_data="menu_pro"))
    markup.add(InlineKeyboardButton("⚙️ Impostazioni Lega", callback_data="menu_impostazioni_lega"), InlineKeyboardButton("⚙️ Sistema", callback_data="menu_sistema"))
    return markup

def send_player_card_view(chat_id, player_name, message_id, df, session, is_scommessa=False):
    try: p_data = df[df['Nome'] == player_name].iloc[0]
    except Exception: return bot.send_message(chat_id, "❌ Giocatore non trovato nel database.", parse_mode="HTML")

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

    alert_reparto = ""
    if session.get('asta_live'):
        budget_reparto_corrente = session['budget_reparti'].get(ruolo, 0)
        slot_mancanti_reparto = {'P': 3, 'D': 8, 'C': 8, 'A': 6}[ruolo] - user_stats['counts'].get(ruolo, 0)
        if slot_mancanti_reparto > 0:
            soglia_sicurezza = budget_reparto_corrente - (slot_mancanti_reparto - 1)
            alert_reparto = f"\n🛑 <b>SOGLIA SICUREZZA REPARTO ({ruolo}):</b> Max <code>{soglia_sicurezza} cr.</code>"

    info_text = (
        f"{photo_embed}📋 <b>ANALISI: {html.escape(player_name.upper())}</b> ({get_team_icon(sq_name)} {html.escape(sq_name)})\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>Ruolo:</b> <code>{html.escape(ruolo)}</code>\n"
        f"🧮 <b>Inquadramento:</b> {fascia}\n"
        f"📉 <b>Matrix Opportunità:</b>\n{tag_matrix}\n"
        f"⚠️ <b>Indice Storico (Rischio):</b> {rischio}{macellaio_alert}\n\n"
        f"🎯 <b>VALUTAZIONE ASTA (Lega a {lega_part} - {lega_bud} cr)</b>\n"
        f"💰 <b>Fair Price:</b> <code>{fair_price} cr.</code> (Valore Reale)\n"
        f"🟢 <b>Max Consigliato:</b> <code>{max_rilancio} cr.</code>{alert_reparto}\n"
        f"🛑 <b>OVERPAY (Asta Stop):</b> <code>> {asta_stop} cr.</code>\n\n"
        f"💼 <b>SITUAZIONE DELLA TUA ROSA</b>\n"
        f"• Budget residuo: <code>{budget_rimasto}</code> cr. (Slot: <code>{giocatori_mancanti}</code>)\n"
        f"🛑 <b>LIMITE DI SPESA (Max Bid): <code>{limite_max}</code> cr.</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
    )
    
    in_wl = player_name in session.get('wishlist', [])
    markup = InlineKeyboardMarkup(row_width=2)
    star = "❌ Rimuovi WL" if in_wl else "⭐ Aggiungi WL"

    if session.get('asta_live'):
        markup.add(InlineKeyboardButton("⚡ Compra", callback_data=f"buy_{player_name}"), InlineKeyboardButton("🚫 Già Preso", callback_data=f"taken_{player_name}"))
        markup.add(InlineKeyboardButton("📊 Storico Reale", callback_data=f"stats_{player_name}"), InlineKeyboardButton("🏥 Clinica Web", callback_data=f"cl_{player_name}"))
        markup.add(InlineKeyboardButton("🔄 Sliding Doors", callback_data=f"sd_{player_name}"), InlineKeyboardButton(star, callback_data=f"wl_toggle_{player_name}"))
    else:
        if is_scommessa:
            markup.add(InlineKeyboardButton(star, callback_data=f"wl_toggle_{player_name}"), InlineKeyboardButton("🎲 Altra Scommessa", callback_data="menu_scommessa_start"))
        else:
            markup.add(InlineKeyboardButton(star, callback_data=f"wl_toggle_{player_name}"), InlineKeyboardButton("🔮 Simula What-If", callback_data=f"wi_{player_name}"))
        markup.add(InlineKeyboardButton("📊 Storico Reale", callback_data=f"stats_{player_name}"), InlineKeyboardButton("🏥 Clinica Web", callback_data=f"cl_{player_name}"))
        markup.add(InlineKeyboardButton("🔄 Sliding Doors", callback_data=f"sd_{player_name}"))
        
    markup.add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
    
    try:
        bot.edit_message_text(info_text, chat_id, message_id, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=False)
    except Exception:
        try: bot.delete_message(chat_id, message_id)
        except Exception: pass
        bot.send_message(chat_id, info_text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=False)

def system_menu_keyboard():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("📥 Download Remoto", callback_data="force_download_listone"), InlineKeyboardButton("🔄 Sync Dati", callback_data="reload_excel"))
    markup.add(InlineKeyboardButton("⚠️ Reset Rosa", callback_data="reset_confirm"), InlineKeyboardButton("🧹 Pulisci Schermo", callback_data="clear_screen"))
    markup.add(InlineKeyboardButton("🏠 Torna alla Home", callback_data="go_home"))
    return markup

def pro_menu_keyboard():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("🎰 Ultimi Spiccioli", callback_data="pro_spiccioli"), InlineKeyboardButton("🧱 Stakanovisti", callback_data="pro_stakanov"))
    markup.add(InlineKeyboardButton("🕸️ Griglia Perfetta (D)", callback_data="pro_griglia"), InlineKeyboardButton("🏠 Torna alla Home", callback_data="go_home"))
    return markup

def send_dashboard(chat_id, user_id, message_id=None):
    salva_chat_id(chat_id)
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
        try: bot.edit_message_text(text, chat_id, message_id, parse_mode="HTML", reply_markup=main_menu_keyboard(session))
        except Exception: bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=main_menu_keyboard(session))
    else: bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=main_menu_keyboard(session))

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

# ==========================================
# GESTIONE ASTA LIVE (NAVIGAZIONE TATTICA)
# ==========================================
def view_fase_portieri(chat_id, msg_id, df, session):
    session['fase_attiva'] = 'P'
    budget_p = session['budget_reparti'].get('P', 0)
    avail_p = get_available_players(df[df['R']=='P'], session)
    
    # Prende ESCLUSIVAMENTE la FVM Ufficiale per i Portieri
    top_csv = avail_p.sort_values(by='FVM', ascending=False).head(5)
    
    txt = (f"🧤 <b>FASE PORTIERI ACTIVE</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
           f"💰 <b>Budget Reparto P:</b> <code>{budget_p} cr.</code> (su {session['budget']} tot)\n\n"
           f"🏆 <b>TOP FVM UFFICIALE:</b>\n")
    
    markup = InlineKeyboardMarkup(row_width=1)
    for _, row in top_csv.iterrows():
        nome, sq, fvm = row['Nome'], row['Squadra'], row.get('FVM', 0)
        txt += f"• <b>{nome}</b> ({sq}) ─ FVM: {fvm}\n"
        markup.add(InlineKeyboardButton(f"🧤 Analizza {nome} (Riserve/Incroci)", callback_data=f"p_strat_{nome}"))
        
    markup.add(InlineKeyboardButton("⏩ Chiudi Reparto Portieri", callback_data="chiudi_reparto_P"))
    markup.add(InlineKeyboardButton("🏠 Menu Principale (Lascia in Background)", callback_data="go_home"))
    
    try: bot.edit_message_text(txt, chat_id, msg_id, parse_mode="HTML", reply_markup=markup)
    except: bot.send_message(chat_id, txt, parse_mode="HTML", reply_markup=markup)

def view_p_strategia(chat_id, msg_id, nome_p, df, session):
    try: row = df[df['Nome'] == nome_p].iloc[0]
    except Exception: return
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
    nomi_estesi = {'D': 'DIFENSORI', 'C': 'CENTROCAMPISTI', 'A': 'ATTACCANTI'}
    txt = (f"{ROLE_ICONS[reparto]} <b>FASE {nomi_estesi[reparto]} ACTIVE</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
           f"💰 <b>Budget Reparto {reparto}:</b> <code>{budget_rep} cr.</code> (su {session['budget']} tot)\n\n👉 Scegli lo strumento per dominare questo reparto:")
    
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton(f"🏆 Top Liberi {reparto}", callback_data=f"menu_top_ru_{reparto}"))
    if reparto == 'D': markup.add(InlineKeyboardButton("🛡️ Analizza Modificatore 6.5", callback_data="menu_modificatore"))
    markup.add(InlineKeyboardButton(f"💎 Gemme Nascoste {reparto}", callback_data=f"menu_gemme_ru_{reparto}"))
    markup.add(InlineKeyboardButton(f"🚨 Panic Button {reparto} (Tappabuchi)", callback_data=f"menu_panic_ru_{reparto}"))
    markup.add(InlineKeyboardButton(f"⏩ Chiudi Reparto {reparto}", callback_data=f"chiudi_reparto_{reparto}"))
    markup.add(InlineKeyboardButton("🏠 Menu Principale (Lascia in Background)", callback_data="go_home"))
    
    try: bot.edit_message_text(txt, chat_id, msg_id, parse_mode="HTML", reply_markup=markup)
    except: bot.send_message(chat_id, txt, parse_mode="HTML", reply_markup=markup)


# ==========================================
# GESTIONE ACQUISTI E WHAT-IF
# ==========================================
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
    if session.get('asta_live'): 
        session['budget_reparti'][ruolo] = max(0, session['budget_reparti'].get(ruolo, 0) - costo)

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
    
    if ruolo == 'P':
        riserve = df[(df['Squadra'].str.lower() == squadra.lower()) & (df['R'] == 'P') & (df['Nome'] != player_name)]['Nome'].tolist()
        if riserve:
            mk_riserve = InlineKeyboardMarkup(row_width=1)
            for r in riserve: mk_riserve.add(InlineKeyboardButton(f"⭐ Metti {r} in Wishlist", callback_data=f"wl_add_{r}"))
            bot.send_message(chat_id, f"🛡️ <b>BLOCCO {squadra.upper()}:</b>\nI secondi/terzi sono <b>{' / '.join(riserve)}</b>.\nVuoi metterli in Wishlist per non dimenticarli?", parse_mode="HTML", reply_markup=mk_riserve)
            
    if session.get('asta_live') and session.get('fase_attiva'):
        markup = InlineKeyboardMarkup().add(InlineKeyboardButton(f"🔙 Torna a Fase {session['fase_attiva']}", callback_data=f"view_fase_{session['fase_attiva']}"))
        bot.send_message(chat_id, "Navigatore Asta Live:", reply_markup=markup)
    else: 
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
        analisi = f"✅ <b>PREZZO CONGRUITA:</b> Cifra perfettamente in linea con il valore del giocatore (Fair Price: <code>{fair_price} cr.</code>)."
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
# HANDLERS (COMANDI, VOCALI E FILE)
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

@bot.message_handler(content_types=['voice'])
def handle_voice(message):
    if not VOICE_ENABLED: return bot.reply_to(message, "❌ <b>Comandi Vocali disattivati.</b>", parse_mode="HTML")
    chat_id = message.chat.id
    session = get_session(message.from_user.id)
    bot.reply_to(message, "🎙️ Ascolto il vocale e traduco...")
    try:
        file_info = bot.get_file(message.voice.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        with open("voice.ogg", 'wb') as f: f.write(downloaded_file)
        audio = AudioSegment.from_ogg("voice.ogg")
        audio.export("voice.wav", format="wav")
        r = sr.Recognizer()
        with sr.AudioFile("voice.wav") as source:
            audio_data = r.record(source)
            testo = r.recognize_google(audio_data, language="it-IT").lower()
        bot.send_message(chat_id, f"🗣️ Hai detto: <i>'{html.escape(testo)}'</i>", parse_mode="HTML")
        match = re.search(r'(?:preso|comprato|ho preso)?\s*([a-zA-Z\s]+)\s*(?:a|per)?\s*(\d+)', testo)
        if match:
            nome_vocale, prezzo_vocale = match.group(1).strip(), int(match.group(2))
            df = load_data()
            matches = df[df['Nome'].astype(str).str.lower().str.contains(nome_vocale, na=False)]
            if not matches.empty:
                gt = matches.iloc[0]['Nome']
                if not session.get('asta_live'):
                    bot.send_message(chat_id, f"🔮 <b>SIMULAZIONE (Asta Disattivata)</b>\nHai simulato <b>{gt}</b> a {prezzo_vocale} cr.\n⚠️ <i>La rosa non è aggiornata.</i>", parse_mode="HTML")
                else:
                    msg = bot.send_message(chat_id, f"🎯 Trovato: <b>{html.escape(gt)}</b>. Confermi acquisto a <code>{prezzo_vocale} cr.</code>?", parse_mode="HTML")
                    bot.register_next_step_handler(msg, process_buy_price, gt, message.from_user.id)
            else: bot.send_message(chat_id, "❌ Nessun giocatore trovato.")
        else: bot.send_message(chat_id, "❌ Formato non riconosciuto. Dì: 'Preso [Nome] a [Prezzo]'.")
    except Exception: bot.reply_to(message, "❌ Errore traduzione vocale. Riprova.")

@bot.message_handler(func=lambda m: m.text.strip().startswith('+'))
def modalita_cecchino(message):
    chat_id, user_id = message.chat.id, message.from_user.id
    text = message.text.strip()[1:].strip() 
    try:
        parts = text.rsplit(' ', 1)
        if len(parts) != 2 or not parts[1].isdigit(): return bot.reply_to(message, "❌ Usa: <code>+ nomegiocatore prezzo</code>", parse_mode="HTML")
        query_nome, costo = parts[0].strip().lower(), int(parts[1])
        df = load_data()
        matches = df[df['Nome'].astype(str).str.lower().str.contains(query_nome, na=False)]
        if matches.empty: return bot.reply_to(message, f"❌ Nessun giocatore trovato per '{html.escape(query_nome)}'.", parse_mode="HTML")
        row = matches.iloc[0] 
        player_name = row['Nome']
        session = get_session(user_id)

        if not session.get('asta_live'):
            return bot.reply_to(message, f"🔮 <b>SIMULAZIONE (Asta Disattivata)</b>\nHai simulato <b>{player_name.upper()}</b> a {costo} cr.\n⚠️ <i>Avvia l'asta per registrare in rosa.</i>", parse_mode="HTML")

        stats = get_roster_stats(session)
        if costo > stats['max_bid']: return bot.reply_to(message, f"⚠️ <b>ALLARME BUDGET!</b> Max Bid: <code>{stats['max_bid']}</code>.", parse_mode="HTML")
        
        session['rosa'].append({
            'nome': player_name, 'prezzo': costo, 'ruolo': row.get('R', 'C'), 'squadra': row.get('Squadra', '-'), 
            'fvm': pd.to_numeric(str(row.get('FVM', 0)).replace(',', '.').replace('-', '0'), errors='coerce')
        })
        session['budget'] -= costo
        if session.get('asta_live'): session['budget_reparti'][row.get('R', 'C')] = max(0, session['budget_reparti'].get(row.get('R', 'C'), 0) - costo)
        
        lega_bud = session.get('lega_budget_iniziale', 500)
        lega_part = session.get('lega_partecipanti', 8)
        fvm_raw = pd.to_numeric(str(row.get('FVM', 0)).replace(',', '.').replace('-', '0'), errors='coerce')
        base_price = fvm_raw * (lega_bud / 1000.0)
        f_part = 1 + ((lega_part - 8) * 0.025)
        fair_price = max(1, int(base_price * f_part))
        
        if costo <= fair_price * 0.75: giudizio = f"🔥 <b>AFFARE D'ORO!</b> Hai risparmiato circa {fair_price - costo} cr."
        elif costo <= fair_price * 0.95: giudizio = f"✅ <b>OTTIMO COLPO!</b> Preso sotto costo (Fair Price: {fair_price})."
        elif costo <= fair_price * 1.15: giudizio = f"⚖️ <b>PREZZO GIUSTO.</b> Pagato il suo reale valore."
        elif costo <= fair_price * 1.30: giudizio = f"⚠️ <b>LEGGERO OVERPAY.</b> Pagato un po' di più (Fair Price: {fair_price})."
        else: giudizio = f"🚨 <b>SALASSO!</b> Strapagato! Hai speso ben {costo - fair_price} cr. in più."

        markup = InlineKeyboardMarkup().add(InlineKeyboardButton("↩️ Annulla", callback_data=f"undo_{player_name}"), InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.reply_to(message, f"🎯 <b>CECCHINO A BERSAGLIO!</b>\n✅ Acquistato <b>{html.escape(player_name.upper())}</b> a <code>{costo} cr.</code>\n\n📊 <b>Valutazione Acquisto:</b>\n{giudizio}", parse_mode="HTML", reply_markup=markup)
    except Exception: bot.reply_to(message, "❌ Errore acquisto rapido.")

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
# CALLBACKS E MENU PAGINATI (INTATTI AL 100%)
# ==========================================
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    try:
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
            msg = bot.send_message(chat_id, "⏳ <i>Collegamento ai server ufficiali per il download...</i>", parse_mode="HTML")
            success = auto_download_and_inject_virtual_players()
            if success:
                bot.edit_message_text("✅ <b>LISTONE AGGIORNATO E VIRTUALI INIETTATI!</b>", chat_id, msg.message_id, parse_mode="HTML")
            else:
                bot.edit_message_text("❌ <b>Download fallito.</b> Utilizzo il file locale.", chat_id, msg.message_id, parse_mode="HTML")

        # --- WIZARD ASTA LIVE ---
        elif call.data == "inizio_asta_live":
            markup = InlineKeyboardMarkup(row_width=3)
            markup.add(InlineKeyboardButton("💰 300", callback_data="setup_bud_300"), InlineKeyboardButton("💰 500", callback_data="setup_bud_500"), InlineKeyboardButton("💰 1000", callback_data="setup_bud_1000"))
            markup.add(InlineKeyboardButton("❌ Annulla", callback_data="go_home"))
            bot.edit_message_text("⚙️ <b>WIZARD ASTA LIVE (1/3)</b>\nQual è il Budget Iniziale della tua Lega?", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

        elif call.data.startswith("setup_bud_"):
            session['lega_budget_iniziale'] = int(call.data.split("_")[2])
            markup = InlineKeyboardMarkup(row_width=3)
            markup.add(InlineKeyboardButton("👥 8 sq", callback_data="setup_part_8"), InlineKeyboardButton("👥 10 sq", callback_data="setup_part_10"), InlineKeyboardButton("👥 12 sq", callback_data="setup_part_12"))
            bot.edit_message_text("⚙️ <b>WIZARD ASTA LIVE (2/3)</b>\nIn quanti Partecipanti siete?", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

        elif call.data.startswith("setup_part_"):
            session['lega_partecipanti'] = int(call.data.split("_")[2])
            markup = InlineKeyboardMarkup(row_width=2)
            markup.add(InlineKeyboardButton("✅ Sì", callback_data="setup_mod_1"), InlineKeyboardButton("❌ No", callback_data="setup_mod_0"))
            bot.edit_message_text("⚙️ <b>WIZARD ASTA LIVE (3/3)</b>\nUtilizzerete il <b>Modificatore di Difesa</b>?\n<i>(Seleziona 'Sì' per assegnare più budget strategico ai difensori)</i>", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

        elif call.data.startswith("setup_mod_"):
            usa_mod = (call.data.split("_")[2] == "1")
            session['usa_modificatore'] = usa_mod
            session['asta_live'] = True
            
            session['budget'] = session['lega_budget_iniziale']
            session['rosa'] = [] 
            session['scartati'] = []

            if usa_mod: session['pesi_reparti'] = {'P': 6, 'D': 15, 'C': 25, 'A': 54}
            else: session['pesi_reparti'] = {'P': 8, 'D': 10, 'C': 28, 'A': 54}

            recalcola_budget_reparti(session)
            view_fase_portieri(chat_id, call.message.message_id, df, session)

        elif call.data == "termina_asta_live":
            session['asta_live'] = False
            bot.edit_message_text("🏁 <b>ASTA LIVE DISATTIVATA!</b>", chat_id, call.message.message_id, parse_mode="HTML")
            send_dashboard(chat_id, user_id)
            
        elif call.data.startswith("view_fase_"):
            rep = call.data[-1]
            if rep == 'P': view_fase_portieri(chat_id, call.message.message_id, df, session)
            else: view_fase_generica(chat_id, call.message.message_id, rep, df, session)
            
        elif call.data.startswith("p_strat_"):
            view_p_strategia(chat_id, call.message.message_id, call.data.replace("p_strat_", ""), df, session)
            
        elif call.data.startswith("chiudi_reparto_"):
            rep_chiuso = call.data[-1]
            recalcola_budget_reparti(session) 
            prossimo_rep = {'P': 'D', 'D': 'C', 'C': 'A', 'A': 'Fine'}.get(rep_chiuso)
            session['fase_attiva'] = prossimo_rep
            
            if prossimo_rep == 'Fine':
                session['asta_live'] = False
                bot.edit_message_text("🏁 <b>ASTA CONCLUSA!</b> Tornando alla Home...", chat_id, call.message.message_id, parse_mode="HTML")
                send_dashboard(chat_id, user_id)
            else:
                txt = (f"⏩ <b>REPARTO {rep_chiuso} CHIUSO.</b> Ricalcolo completato!\n"
                       f"Passiamo al reparto <b>{prossimo_rep}</b>.\n"
                       f"💰 <b>Budget {prossimo_rep} Aggiornato:</b> <code>{session['budget_reparti'][prossimo_rep]} cr.</code>")
                markup = InlineKeyboardMarkup().add(InlineKeyboardButton(f"Vai al Reparto {prossimo_rep}", callback_data=f"view_fase_{prossimo_rep}"))
                bot.edit_message_text(txt, chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

        # --- IMPOSTAZIONI LEGA (Manuali da Menu) ---
        elif call.data == "menu_impostazioni_lega":
            b_iniziale = session.get('lega_budget_iniziale', 500)
            part = session.get('lega_partecipanti', 8)
            
            markup = InlineKeyboardMarkup(row_width=3)
            markup.row(
                InlineKeyboardButton("💰 Bud: 300", callback_data="imposta_bud_300"),
                InlineKeyboardButton("💰 500", callback_data="imposta_bud_500"),
                InlineKeyboardButton("💰 1000", callback_data="imposta_bud_1000")
            )
            markup.row(
                InlineKeyboardButton("👥 Lega: 8", callback_data="imposta_part_8"),
                InlineKeyboardButton("👥 a 10", callback_data="imposta_part_10"),
                InlineKeyboardButton("👥 a 12", callback_data="imposta_part_12")
            )
            markup.add(InlineKeyboardButton("🔄 Reset (500 cr - 8 sq)", callback_data="imposta_reset"))
            markup.add(InlineKeyboardButton("🏠 Torna alla Home", callback_data="go_home"))
            
            testo = (
                "⚙️ <b>IMPOSTAZIONI DELLA TUA LEGA</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💰 <b>Budget Iniziale:</b> <code>{b_iniziale} cr.</code>\n"
                f"👥 <b>Partecipanti:</b> <code>{part} squadre</code>\n\n"
                "<i>Il bot applicherà in automatico questi parametri per calcolare le valutazioni d'asta reali.</i>"
            )
            bot.edit_message_text(testo, chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

        elif call.data.startswith("imposta_bud_"):
            val = int(call.data.replace("imposta_bud_", ""))
            session['lega_budget_iniziale'] = val
            session['budget'] = val
            safe_answer_callback(call.id, text=f"✅ Budget impostato a {val} cr!", show_alert=True)
            call.data = "menu_impostazioni_lega"
            handle_callbacks(call)

        elif call.data.startswith("imposta_part_"):
            val = int(call.data.replace("imposta_part_", ""))
            session['lega_partecipanti'] = val
            safe_answer_callback(call.id, text=f"✅ Partecipanti impostati a {val}!", show_alert=True)
            call.data = "menu_impostazioni_lega"
            handle_callbacks(call)

        elif call.data == "imposta_reset":
            session['lega_budget_iniziale'] = 500
            session['lega_partecipanti'] = 8
            session['budget'] = 500
            safe_answer_callback(call.id, text="✅ Lega resettata ai valori standard!", show_alert=True)
            call.data = "menu_impostazioni_lega"
            handle_callbacks(call)

        elif call.data == "menu_formazione":
            testo_form, img_buf = calcola_formazione_ideale(session, df)
            markup = InlineKeyboardMarkup().add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
            if img_buf: bot.send_photo(chat_id, img_buf, caption=testo_form, parse_mode="HTML", reply_markup=markup)
            else: bot.send_message(chat_id, testo_form, parse_mode="HTML", reply_markup=markup)

        elif call.data == "menu_rigoristi":
            testo = "🎯 <b>RADAR RIGORISTI & TIRATORI UFFICIALE</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
            for sq, dati in GERARCHIE_RIGORISTI.items():
                testo += f"<b>{get_team_icon(sq)} {sq}:</b>\n"
                testo += f"⚽ Rigoristi: {', '.join(dati['rigoristi'])}\n"
                testo += f"🎯 Punizioni: {', '.join(dati['punizioni'])}\n\n"
            markup = InlineKeyboardMarkup().add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
            bot.edit_message_text(testo, chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

        elif call.data == "menu_power":
            rosa = session.get('rosa', [])
            testo = "🔥 <b>POWER INDEX & TREND DI FORMA</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
            hot_players = []
            for p in rosa:
                stats = find_player_in_stats(p['nome'])
                if stats is not None:
                    fm = float(str(stats.get('Fm', 6.0)).replace(',', '.'))
                    if fm >= 6.8: hot_players.append(f"🔥 <b>{p['nome']}</b> (FM: <code>{fm}</code>)")
            
            testo += "\n".join(hot_players) if hot_players else "<i>Nessun giocatore in stato di grazia al momento.</i>"
            markup = InlineKeyboardMarkup().add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
            bot.edit_message_text(testo, chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

        elif call.data == "menu_sistema":
            bot.edit_message_text("⚙️ <b>OPZIONI DI SISTEMA</b>", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=system_menu_keyboard())

        elif call.data == "reload_excel": 
            load_data(force_reload=True)
            bot.send_message(chat_id, "⚡ <b>Dati sincronizzati con successo!</b>", parse_mode="HTML")

        elif call.data == "reset_confirm":
            lega_bud = session.get('lega_budget_iniziale', 500)
            lega_part = session.get('lega_partecipanti', 8)
            user_sessions[user_id] = {
                'budget': lega_bud, 'rosa': [], 'wishlist': session.get('wishlist', []), 'scartati': [], 
                'compare_p1': None, 'lega_budget_iniziale': lega_bud, 'lega_partecipanti': lega_part,
                'asta_live': False, 'fase_attiva': None, 'usa_modificatore': session.get('usa_modificatore', False),
                'pesi_reparti': session.get('pesi_reparti', {'P': 8, 'D': 10, 'C': 28, 'A': 54}),
                'budget_reparti': {'P': 40, 'D': 50, 'C': 140, 'A': 270}
            }
            send_dashboard(chat_id, user_id, call.message.message_id)

        elif call.data == "menu_pro":
            bot.edit_message_text("🛠️ <b>STRUMENTI PRO</b>", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=pro_menu_keyboard())

        elif call.data == "pro_stakanov":
            avail = get_available_players(df, session)
            staka = avail[(avail['R'].isin(['D', 'C'])) & (avail['FVM'] <= 6)].head(20)
            markup = InlineKeyboardMarkup(row_width=1)
            count = 0
            for _, row in staka.iterrows():
                if count >= 10: break
                if sum(ord(c) for c in row['Nome']) % 2 == 0:
                    markup.add(InlineKeyboardButton(f"🧱 {row['Nome']} ({row['Squadra']})", callback_data=f"sq_pl_{row['Nome']}"))
                    count += 1
            markup.add(InlineKeyboardButton("🔙 Menu PRO", callback_data="menu_pro"))
            bot.edit_message_text("🧱 <b>STAKANOVISTI</b>", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

        elif call.data == "pro_griglia":
            avail = get_available_players(df, session)
            squadre_abbordabili = ['Empoli', 'Lecce', 'Parma', 'Verona', 'Cagliari', 'Venezia', 'Como', 'Monza', 'Frosinone', 'Sassuolo']
            squadre_medio_alte = ['Fiorentina', 'Bologna', 'Torino', 'Lazio', 'Atalanta', 'Genoa', 'Udinese']
            
            d_liberi = avail[(avail['R'] == 'D') & (avail['FVM'] >= 1) & (avail['FVM'] <= 20)].copy()
            trio_tattico = []
            
            d_abb1 = d_liberi[d_liberi['Squadra'].isin(squadre_abbordabili)].sort_values(by='FVM', ascending=False)
            if not d_abb1.empty:
                p1 = d_abb1.sample(1).iloc[0]
                trio_tattico.append(p1)
                
            sq_usate = [p['Squadra'] for p in trio_tattico]
            d_abb2 = d_liberi[(d_liberi['Squadra'].isin(squadre_abbordabili)) & (~d_liberi['Squadra'].isin(sq_usate))].sort_values(by='FVM', ascending=False)
            if not d_abb2.empty:
                p2 = d_abb2.sample(1).iloc[0]
                trio_tattico.append(p2)
                
            d_media = d_liberi[d_liberi['Squadra'].isin(squadre_medio_alte)].sort_values(by='FVM', ascending=False)
            if not d_media.empty:
                p3 = d_media.sample(1).iloc[0]
                trio_tattico.append(p3)
                
            markup = InlineKeyboardMarkup(row_width=1)
            for row in trio_tattico:
                markup.add(InlineKeyboardButton(f"🛡️ {row['Nome']} ({row['Squadra']}) ─ FVM: {row['FVM']}", callback_data=f"sq_pl_{row['Nome']}"))

            markup.add(InlineKeyboardButton("🔄 Genera Altro Trio Tattico", callback_data="pro_griglia"), 
                       InlineKeyboardButton("🔙 Menu PRO", callback_data="menu_pro"))
            
            testo = (
                "🕸️ <b>GRIGLIA TATTICA \"PARTITE FACILI\" (TRIO IDEALE)</b>\n\n"
                "Questo trio combina <b>2 difensori da squadre piccole</b> (per sfruttare le sfide dirette in casa) "
                "e <b>1 difensore da squadra di fascia media</b> per darti sempre almeno una copertura da 6.5 in pagella:\n"
            )
            bot.edit_message_text(testo, chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

        elif call.data == "pro_spiccioli":
            stats = get_roster_stats(session)
            budget, slot = stats['budget'], stats['slot_liberi']
            
            if slot <= 0: 
                return safe_answer_callback(call.id, text="⚠️ Hai già la rosa piena (25/25)!", show_alert=True)
                
            avail = get_available_players(df, session)
            if avail.empty:
                return safe_answer_callback(call.id, text="⚠️ Nessun giocatore disponibile nel listone!", show_alert=True)

            low_cost = avail[pd.to_numeric(avail['FVM'], errors='coerce').fillna(0) <= 5].copy()
            if low_cost.empty:
                low_cost = avail.sort_values(by='FVM', ascending=True).head(20)

            spiccioli_top = []
            if STATS_CACHE is not None and not STATS_CACHE.empty:
                for _, row in low_cost.iterrows():
                    nome = row['Nome']
                    st = find_player_in_stats(nome)
                    if st is not None:
                        try:
                            pv = int(pd.to_numeric(st.get('Pv', 0), errors='coerce'))
                            mv = float(str(st.get('Mv', 0)).replace(',', '.'))
                            fm = float(str(st.get('Fm', 0)).replace(',', '.'))
                            
                            if pv >= 1 or fm > 0:
                                spiccioli_top.append({
                                    'nome': nome,
                                    'ruolo': row['R'],
                                    'squadra': row['Squadra'],
                                    'fvm': row.get('FVM', 1),
                                    'fm': fm if fm > 0 else mv,
                                    'pv': pv
                                })
                        except Exception: pass

            markup = InlineKeyboardMarkup(row_width=1)
            if spiccioli_top:
                spiccioli_top = sorted(spiccioli_top, key=lambda x: (x['pv'], x['fm']), reverse=True)
                for p in spiccioli_top[:10]:
                    markup.add(InlineKeyboardButton(f"🎰 {p['nome']} ({p['ruolo']} - {p['squadra']}) ─ FM:{p['fm']:.1f} | Pres:{p['pv']}", callback_data=f"sq_pl_{p['nome']}"))
                testo_header = "🎰 <b>TAPPABUCHI LOW-COST (ORDINATI PER PRESENZE E FM)</b>\nI migliori calciatori economici con minutaggio reale:"
            else:
                sample_players = low_cost.sample(min(10, len(low_cost))) if len(low_cost) >= 10 else low_cost
                for _, row in sample_players.iterrows():
                    markup.add(InlineKeyboardButton(f"🎰 {row['Nome']} ({row['R']} - {row['Squadra']}) ─ FVM: {row.get('FVM', 1)}", callback_data=f"sq_pl_{row['Nome']}"))
                testo_header = "🎰 <b>ULTIMI SPICCIOLI LOW-COST</b>\nGiocatori economici ancora disponibili nel Listone:"

            markup.add(InlineKeyboardButton("🔄 Aggiorna / Altri Nomi", callback_data="pro_spiccioli"), 
                       InlineKeyboardButton("🔙 Menu PRO", callback_data="menu_pro"))

            try:
                bot.edit_message_text(f"{testo_header}\n<i>(Budget residuo: {budget} cr. per {slot} slot)</i>", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)
            except Exception:
                bot.send_message(chat_id, f"{testo_header}\n<i>(Budget residuo: {budget} cr. per {slot} slot)</i>", parse_mode="HTML", reply_markup=markup)

        elif call.data.startswith("cl_"):
            p_name = call.data.replace("cl_", "")
            p_row = df[df['Nome'] == p_name].iloc[0]
            msg = bot.send_message(chat_id, f"⏳ <i>Ricerca notizie per {html.escape(p_name)}...</i>", parse_mode="HTML")
            real_data = get_cartella_clinica_reale(p_name, p_row.get('Squadra', ''))
            markup = InlineKeyboardMarkup(row_width=2).add(InlineKeyboardButton("🔙 Indietro", callback_data=f"sq_pl_{p_name}"), InlineKeyboardButton("🏠 Home", callback_data="go_home"))
            bot.edit_message_text(real_data, chat_id, msg.message_id, parse_mode="HTML", disable_web_page_preview=True, reply_markup=markup)

        elif call.data.startswith("stats_"):
            p_name = call.data.replace("stats_", "")
            p_row = df[df['Nome'] == p_name].iloc[0]
            real_data = get_storico_excel_o_web(p_name, p_row.get('Squadra', ''))
            markup = InlineKeyboardMarkup(row_width=2).add(InlineKeyboardButton("🔙 Indietro", callback_data=f"sq_pl_{p_name}"), InlineKeyboardButton("🏠 Home", callback_data="go_home"))
            bot.edit_message_text(real_data, chat_id, call.message.message_id, parse_mode="HTML", disable_web_page_preview=True, reply_markup=markup)

        elif call.data.startswith("wi_"):
            p_name = call.data.replace("wi_", "")
            msg = bot.send_message(chat_id, f"🔮 <b>SIMULATORE WHAT-IF</b> per <b>{html.escape(p_name)}</b>:", parse_mode="HTML")
            bot.register_next_step_handler(msg, process_whatif_price, p_name, user_id)

        elif call.data.startswith("sd_"):
            p_name = call.data.replace("sd_", "")
            row = df[df['Nome'] == p_name].iloc[0]
            ruolo, fvm = row['R'], float(row.get('FVM', 0))
            avail = get_available_players(df, session)
            
            try: bot.delete_message(chat_id, call.message.message_id)
            except Exception: pass

            same_role = avail[(avail['R'] == ruolo) & (avail['Nome'] != p_name)].copy()
            same_role['diff_fvm'] = abs(pd.to_numeric(same_role['FVM'], errors='coerce').fillna(0) - fvm)
            cloni = same_role.sort_values(by=['diff_fvm', 'FVM'], ascending=[True, False]).head(4)
            
            markup = InlineKeyboardMarkup(row_width=1)
            for _, cl_row in cloni.iterrows():
                markup.add(InlineKeyboardButton(f"🔄 {cl_row['Nome']} ({cl_row['Squadra']}) FVM:{cl_row['FVM']}", callback_data=f"sq_pl_{cl_row['Nome']}"))
            markup.add(InlineKeyboardButton("🔙 Indietro", callback_data=f"sq_pl_{p_name}"))
            bot.send_message(chat_id, f"🔄 <b>SLIDING DOORS per {html.escape(p_name)}:</b>", parse_mode="HTML", reply_markup=markup)

        elif call.data.startswith("wl_add_"):
            p_name = call.data.replace("wl_add_", "")
            if p_name not in session['wishlist']: session['wishlist'].append(p_name)
            safe_answer_callback(call.id, text=f"✅ {p_name} aggiunto alla Wishlist!", show_alert=True)

        elif call.data.startswith("menu_modificatore"):
            parts = call.data.split("_page_")
            page = int(parts[1]) if len(parts) > 1 else 1
            per_page = 15
            avail = get_available_players(df, session)
            mod_players = []
            
            if STATS_CACHE is not None and not STATS_CACHE.empty:
                for _, row in avail[avail['R'] == 'D'].iterrows():
                    nome = row['Nome']
                    fvm = row.get('FVM', 0)
                    stats = find_player_in_stats(nome)
                    if stats is not None:
                        try:
                            mv = float(str(stats.get('Mv', 0)).replace(',', '.'))
                            pv, amm = int(stats.get('Pv', 0)), int(stats.get('Amm', 0))
                            if pv >= 15 and mv >= 6.00 and fvm <= 35:
                                indice_pulizia = mv - (amm * 0.02) 
                                mod_players.append({'nome': nome, 'fvm': fvm, 'mv': mv, 'amm': amm, 'pv': pv, 'indice': indice_pulizia, 'squadra': row.get('Squadra', '-')})
                        except Exception: pass
            
            markup = InlineKeyboardMarkup(row_width=1)
            if mod_players:
                sorted_players = sorted(mod_players, key=lambda x: x['indice'], reverse=True)
                start_idx, end_idx = (page - 1) * per_page, page * per_page
                for p in sorted_players[start_idx:end_idx]:
                    markup.add(InlineKeyboardButton(f"🛡️ {p['nome']} (MV:{p['mv']} | 🟨{p['amm']}) ─ {p['fvm']} cr.", callback_data=f"sq_pl_{p['nome']}"))
                
                nav_buttons = []
                if page > 1: nav_buttons.append(InlineKeyboardButton("◀️ Precedenti", callback_data=f"menu_modificatore_page_{page - 1}"))
                if len(sorted_players) > end_idx: nav_buttons.append(InlineKeyboardButton(f"➕ Altri {min(15, len(sorted_players) - end_idx)}", callback_data=f"menu_modificatore_page_{page + 1}"))
                if nav_buttons: markup.row(*nav_buttons)
                testo = f"🛡️ <b>MODIFICATORE 6.5</b> (Pag. {page})"
            else:
                mods = avail[(avail['R'] == 'D') & (avail['FVM'] >= 5) & (avail['FVM'] <= 35)].sort_values(by='FVM', ascending=False)
                start_idx, end_idx = (page - 1) * per_page, page * per_page
                for _, row in mods.iloc[start_idx:end_idx].iterrows():
                    markup.add(InlineKeyboardButton(f"🛡️ {row['Nome']} (FVM: {row['FVM']})", callback_data=f"sq_pl_{row['Nome']}"))
                
                nav_buttons = []
                if page > 1: nav_buttons.append(InlineKeyboardButton("◀️ Precedenti", callback_data=f"menu_modificatore_page_{page - 1}"))
                if len(mods) > end_idx: nav_buttons.append(InlineKeyboardButton(f"➕ Altri {min(15, len(mods) - end_idx)}", callback_data=f"menu_modificatore_page_{page + 1}"))
                if nav_buttons: markup.row(*nav_buttons)
                testo = f"🛡️ <b>MODIFICATORE 6.5</b> (Pag. {page})"

            if session.get('asta_live'): markup.add(InlineKeyboardButton("🔙 Torna a Fase D", callback_data="view_fase_D"))
            markup.add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
            bot.edit_message_text(testo, chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

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

        elif call.data == "sq_start":
            if df is None: return
            bot.edit_message_text("👕 <b>ESPLORA SQUADRE</b>", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=menu_seleziona_squadra(df, "sq"))

        elif call.data.startswith("sq_sq_"):
            bot.edit_message_text("Scegli il ruolo:", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=menu_seleziona_ruolo(call.data.replace("sq_sq_", ""), "sq"))

        elif call.data.startswith("sq_ru_"):
            _, _, sq, ru = call.data.split("_")
            bot.edit_message_text(f"Giocatori ({sq} - {ru}):", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=menu_seleziona_giocatore(df, sq, ru, "sq", user_id))

        elif call.data == "menu_top_start":
            markup = InlineKeyboardMarkup(row_width=4).add(*[InlineKeyboardButton(f"{ROLE_ICONS[r]} {r}", callback_data=f"menu_top_ru_{r}") for r in ['P', 'D', 'C', 'A']])
            markup.add(InlineKeyboardButton("🔙 Home", callback_data="go_home"))
            bot.edit_message_text("🏆 <b>TOP LIBERI - Scegli il ruolo:</b>", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

        elif call.data.startswith("menu_top_ru_"):
            raw_data = call.data.replace("menu_top_ru_", "")
            r, page = (raw_data.split("_page_")[0], int(raw_data.split("_page_")[1])) if "_page_" in raw_data else (raw_data, 1)
            per_page = 15
            avail = get_available_players(df, session)
            top_players = avail[avail['R'] == r].sort_values(by='FVM', ascending=False)
            
            start_idx, end_idx = (page - 1) * per_page, page * per_page
            markup = InlineKeyboardMarkup(row_width=1)
            for _, row in top_players.iloc[start_idx:end_idx].iterrows(): 
                markup.add(InlineKeyboardButton(f"🔍 {row['Nome']} ({row.get('Squadra','-')}) FVM:{row.get('FVM','-')}", callback_data=f"sq_pl_{row['Nome']}"))
                
            nav_buttons = []
            if page > 1: nav_buttons.append(InlineKeyboardButton("◀️ Precedenti", callback_data=f"menu_top_ru_{r}_page_{page - 1}"))
            if len(top_players) > end_idx: nav_buttons.append(InlineKeyboardButton(f"➕ Altri {min(15, len(top_players) - end_idx)}", callback_data=f"menu_top_ru_{r}_page_{page + 1}"))
            if nav_buttons: markup.row(*nav_buttons)
                
            if session.get('asta_live'): markup.add(InlineKeyboardButton(f"🔙 Torna a Fase {r}", callback_data=f"view_fase_{r}"))
            markup.add(InlineKeyboardButton("🔙 Cambia Ruolo", callback_data="menu_top_start"), InlineKeyboardButton("🏠 Home", callback_data="go_home"))
            bot.edit_message_text(f"🏆 <b>TOP LIBERI - RUOLO {ROLE_ICONS[r]} {r}</b> (Pag. {page}):", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

        elif call.data == "menu_gemme_start":
            markup = InlineKeyboardMarkup(row_width=4).add(*[InlineKeyboardButton(f"{ROLE_ICONS[r]} {r}", callback_data=f"menu_gemme_ru_{r}") for r in ['P', 'D', 'C', 'A']])
            markup.add(InlineKeyboardButton("🔙 Home", callback_data="go_home"))
            bot.edit_message_text("💎 <b>GEMME NASCOSTE (FVM 6-20) - Scegli il ruolo:</b>", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

        elif call.data.startswith("menu_gemme_ru_"):
            raw_data = call.data.replace("menu_gemme_ru_", "")
            r, page = (raw_data.split("_page_")[0], int(raw_data.split("_page_")[1])) if "_page_" in raw_data else (raw_data, 1)
            per_page = 15
            avail = get_available_players(df, session)
            gemme = avail[(avail['R'] == r) & (avail['FVM'] <= 20) & (avail['FVM'] >= 6)].sort_values(by='FVM', ascending=False)
            
            start_idx, end_idx = (page - 1) * per_page, page * per_page
            markup = InlineKeyboardMarkup(row_width=1)
            for _, row in gemme.iloc[start_idx:end_idx].iterrows():
                markup.add(InlineKeyboardButton(f"💎 {row['Nome']} ({row.get('Squadra','-')}) FVM:{row.get('FVM','-')}", callback_data=f"sq_pl_{row['Nome']}"))
                
            nav_buttons = []
            if page > 1: nav_buttons.append(InlineKeyboardButton("◀️ Precedenti", callback_data=f"menu_gemme_ru_{r}_page_{page - 1}"))
            if len(gemme) > end_idx: nav_buttons.append(InlineKeyboardButton(f"➕ Altri {min(15, len(gemme) - end_idx)}", callback_data=f"menu_gemme_ru_{r}_page_{page + 1}"))
            if nav_buttons: markup.row(*nav_buttons)
                
            if session.get('asta_live'): markup.add(InlineKeyboardButton(f"🔙 Torna a Fase {r}", callback_data=f"view_fase_{r}"))
            markup.add(InlineKeyboardButton("🔙 Cambia Ruolo", callback_data="menu_gemme_start"), InlineKeyboardButton("🏠 Home", callback_data="go_home"))
            bot.edit_message_text(f"💎 <b>GEMME NASCOSTE - {ROLE_ICONS[r]} {r}</b> (Pag. {page}):", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

        elif call.data == "menu_panic_start":
            markup = InlineKeyboardMarkup(row_width=4).add(*[InlineKeyboardButton(f"{ROLE_ICONS[r]} {r}", callback_data=f"menu_panic_ru_{r}") for r in ['P', 'D', 'C', 'A']])
            markup.add(InlineKeyboardButton("🔙 Home", callback_data="go_home"))
            bot.edit_message_text("🚨 <b>PANIC BUTTON (FVM 1-5) - Scegli il ruolo:</b>", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

        elif call.data.startswith("menu_panic_ru_"):
            raw_data = call.data.replace("menu_panic_ru_", "")
            r, page = (raw_data.split("_page_")[0], int(raw_data.split("_page_")[1])) if "_page_" in raw_data else (raw_data, 1)
            per_page = 15
            avail = get_available_players(df, session)
            panic_list = avail[(avail['R'] == r) & (avail['FVM'] <= 5) & (avail['FVM'] >= 1)].sort_values(by='FVM', ascending=False)
            
            start_idx, end_idx = (page - 1) * per_page, page * per_page
            markup = InlineKeyboardMarkup(row_width=1)
            for _, row in panic_list.iloc[start_idx:end_idx].iterrows():
                markup.add(InlineKeyboardButton(f"🚨 {row['Nome']} ({row.get('Squadra','-')}) FVM:{row.get('FVM','-')}", callback_data=f"sq_pl_{row['Nome']}"))
                
            nav_buttons = []
            if page > 1: nav_buttons.append(InlineKeyboardButton("◀️ Precedenti", callback_data=f"menu_panic_ru_{r}_page_{page - 1}"))
            if len(panic_list) > end_idx: nav_buttons.append(InlineKeyboardButton(f"➕ Altri {min(15, len(panic_list) - end_idx)}", callback_data=f"menu_panic_ru_{r}_page_{page + 1}"))
            if nav_buttons: markup.row(*nav_buttons)
                
            if session.get('asta_live'): markup.add(InlineKeyboardButton(f"🔙 Torna a Fase {r}", callback_data=f"view_fase_{r}"))
            markup.add(InlineKeyboardButton("🔙 Cambia Ruolo", callback_data="menu_panic_start"), InlineKeyboardButton("🏠 Home", callback_data="go_home"))
            bot.edit_message_text(f"🚨 <b>PANIC BUTTON - {ROLE_ICONS[r]} {r}</b> (Pag. {page}):", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

        elif call.data == "menu_scommessa_start":
            avail = get_available_players(df, session)
            scommesse_list = [avail[avail['Nome'].astype(str).str.lower().str.contains(sc)] for sc in DATABASE_SCOMMESSE_PURE if not avail[avail['Nome'].astype(str).str.lower().str.contains(sc)].empty]
            if scommesse_list: send_player_card_view(chat_id, pd.concat(scommesse_list).drop_duplicates().sample(1).iloc[0]['Nome'], call.message.message_id, df, session, is_scommessa=True)
            else: safe_answer_callback(call.id, text="Nessuna scommessa disponibile!", show_alert=True)

        elif call.data == "menu_studio_start":
            session['compare_p1'] = None
            bot.edit_message_text("📊 <b>STUDIO & TRADE ANALYZER 3D</b>\nSeleziona la squadra del TUO giocatore:", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=menu_seleziona_squadra(df, "std1"))

        elif call.data.startswith("std1_sq_"):
            sq = call.data.replace("std1_sq_", "")
            bot.edit_message_text(f"📊 <b>AREA STUDIO - TUO GIOCATORE ({sq})</b>\nScegli il ruolo:", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=menu_seleziona_ruolo(sq, "std1"))

        elif call.data.startswith("std1_ru_"):
            _, _, sq, ru = call.data.split("_")
            bot.edit_message_text(f"📊 <b>AREA STUDIO - TUO GIOCATORE ({sq} - {ru})</b>\nSelezionalo:", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=menu_seleziona_giocatore(df, sq, ru, "std1", user_id))

        elif call.data.startswith("std1_pl_"):
            p1_nome = call.data.replace("std1_pl_", "")
            p1_row = df[df['Nome'] == p1_nome].iloc[0]
            session['compare_p1'] = p1_row.to_dict()
            markup = InlineKeyboardMarkup(row_width=2)
            markup.add(*[InlineKeyboardButton(f"{get_team_icon(sq)} {sq}", callback_data=f"std2_sq_{sq}") for sq in sorted(df['Squadra'].dropna().astype(str).unique())])
            markup.add(InlineKeyboardButton("🔙 Reset", callback_data="menu_studio_start"))
            bot.edit_message_text(f"📊 <b>CONFRONTO:</b> Hai scelto <b>{html.escape(p1_nome.upper())}</b>\nOra seleziona la squadra del GIOCATORE PROPOSTO:", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

        elif call.data.startswith("std2_sq_"):
            sq2 = call.data.replace("std2_sq_", "")
            p1 = session.get('compare_p1')
            markup = InlineKeyboardMarkup(row_width=1)
            for _, row in df[(df['Squadra'] == sq2) & (df['R'] == p1['R']) & (df['Nome'] != p1['Nome'])].iterrows():
                markup.add(InlineKeyboardButton(f"🆚 Confronta con {row['Nome']}", callback_data=f"std2_pl_{row['Nome']}"))
            markup.add(InlineKeyboardButton("🔙 Cambia Squadra", callback_data=f"std1_pl_{p1['Nome']}"))
            bot.edit_message_text(f"📊 <b>Scegli il GIOCATORE PROPOSTO ({sq2}):</b>", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

        elif call.data.startswith("std2_pl_"):
            p2_nome = call.data.replace("std2_pl_", "")
            p1, p2 = session.get('compare_p1'), df[df['Nome'] == p2_nome].iloc[0].to_dict()
            text = advanced_trade_analyzer_3d(p1, p2, session)
            markup = InlineKeyboardMarkup(row_width=2)
            if session.get('asta_live'):
                markup.add(InlineKeyboardButton(f"⚡ Compra {p1['Nome']}", callback_data=f"buy_{p1['Nome']}"), InlineKeyboardButton(f"⚡ Compra {p2['Nome']}", callback_data=f"buy_{p2['Nome']}"))
            markup.add(InlineKeyboardButton("🔄 Nuovo Confronto", callback_data="menu_studio_start"), InlineKeyboardButton("🏠 Home", callback_data="go_home"))
            bot.edit_message_text(text, chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

        elif call.data.startswith("buy_"):
            player_name = call.data.replace("buy_", "")
            msg = bot.send_message(chat_id, f"💰 Crediti spesi per <b>{html.escape(player_name)}</b>?:", parse_mode="HTML")
            bot.register_next_step_handler(msg, process_buy_price, player_name, user_id)

        elif call.data.startswith("taken_"):
            p_name = call.data.replace("taken_", "")
            if p_name not in session['scartati']: session['scartati'].append(p_name)
            safe_answer_callback(call.id, text=f"🚫 {p_name} segnato come già preso!", show_alert=False)
            if session.get('asta_live') and session.get('fase_attiva'): view_fase_generica(chat_id, call.message.message_id, session['fase_attiva'], df, session)
            else: send_dashboard(chat_id, user_id, call.message.message_id)

        elif call.data.startswith("wl_toggle_"):
            player_name = call.data.replace("wl_toggle_", "")
            if 'wishlist' not in session: session['wishlist'] = []
            if player_name in session['wishlist']: session['wishlist'].remove(player_name)
            else: session['wishlist'].append(player_name)
            send_player_card_view(chat_id, player_name, call.message.message_id, df, session)

        elif call.data == "menu_wishlist":
            wishlist = session.get('wishlist', [])
            markup = InlineKeyboardMarkup(row_width=1)
            if not wishlist: testo = "⭐ <b>WISHLIST VUOTA</b>"
            else:
                testo = "⭐ <b>LA TUA WISHLIST:</b>\n"
                for nome in wishlist: markup.add(InlineKeyboardButton(f"🔍 {nome}", callback_data=f"sq_pl_{nome}"))
            markup.add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
            bot.edit_message_text(testo, chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    except Exception as e:
        bot.send_message(call.message.chat.id, "❌ Errore in questa funzione. Riprova ricaricando il Listone o la Home.", parse_mode="HTML")
        print(f"Errore catturato: {str(e)}")

if __name__ == '__main__':
    try: bot.remove_webhook()
    except: pass
    print("🚀 FANTABOT PRO (Asta & Campionato) In Ascolto!")
    bot.infinity_polling(timeout=10, long_polling_timeout=5, skip_pending=True)
