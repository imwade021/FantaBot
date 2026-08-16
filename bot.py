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

# URL UFFICIALE DOWNLOAD LISTONE MASTER GENERATO DALL'ENGINE (GitHub)
LISTONE_URL = "https://raw.githubusercontent.com/imwade021/fanta-master-ai/main/Lista_Finale_Master.csv"

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
    print("🔄 Avvio download automatico del Listone Master...")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        res = requests.get(LISTONE_URL, headers=headers, timeout=15)
        if res.status_code == 200:
            with open("Lista_Finale_Master.csv", "wb") as f:
                f.write(res.content)
            print("✅ Listone Master aggiornato con successo da remoto!")
            load_data(force_reload=True)
            return True
        else:
            print(f"⚠️ Errore download listone, status code: {res.status_code}")
            return False
    except Exception as e:
        print(f"❌ Errore durante l'auto-download: {e}")
        return False

def load_data(force_reload=False):
    global DATA_CACHE, STATS_CACHE
    if DATA_CACHE is None or force_reload:
        file_target = "Lista_Finale_Master.csv" if os.path.exists("Lista_Finale_Master.csv") else ("Lista-FantaAsta-Fantacalcio.csv" if os.path.exists("Lista-FantaAsta-Fantacalcio.csv") else None)
        if file_target:
            try:
                try:
                    DATA_CACHE = pd.read_csv(file_target, sep=';')
                    if len(DATA_CACHE.columns) < 3:
                        DATA_CACHE = pd.read_csv(file_target, sep=',')
                except Exception:
                    DATA_CACHE = pd.read_csv(file_target, header=None)
                    DATA_CACHE.columns = [
                        'Id', 'Nome_Breve', 'Nome', 'R', 'Ruolo_Esteso', 'Qt.A', 'Qt.I', 
                        'Qt.M', 'Diff.M', 'Squadra', 'FVM', 'FVM.M', 'Piede', 'Nazionalita', 
                        'DataNascita', 'PhotoURL', 'Extra1', 'Extra2', 'Extra3'
                    ]

                if 'Ruolo' in DATA_CACHE.columns and 'R' not in DATA_CACHE.columns:
                    DATA_CACHE.rename(columns={'Ruolo': 'R'}, inplace=True)
                if 'Valore_Base_Perc' in DATA_CACHE.columns and 'FVM' not in DATA_CACHE.columns:
                    DATA_CACHE['FVM'] = DATA_CACHE['Valore_Base_Perc']

                DATA_CACHE['FVM'] = pd.to_numeric(DATA_CACHE['FVM'], errors='coerce').fillna(0)
                print(f"✅ File {file_target} caricato in memoria!")
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
                print(f"✅ File {stats_file} caricato e indicizzato con successo!")
            except Exception as e: print(f"⚠️ Errore lettura {stats_file}: {e}")

    return DATA_CACHE

# Caricamento iniziale e avvio Pianificatore
load_data()
try:
    scheduler = BackgroundScheduler()
    scheduler.add_job(auto_download_listone, 'cron', hour=4, minute=0)
    scheduler.start()
    print("⏰ Pianificatore Auto-Download attivo")
except Exception: pass

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
            'modificatore_attivo': False,
            'fase_asta': None
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

# =========================================================================
# RICERCA NELLO STORICO RISOLTA (SELEZIONA LA RIGA CON PIÙ PRESENZE)
# =========================================================================
def find_player_in_stats(nome):
    global STATS_CACHE
    if STATS_CACHE is None or STATS_CACHE.empty:
        load_data()
        if STATS_CACHE is None or STATS_CACHE.empty:
            return None
    
    norm_name = normalize_str(nome)
    
    matches = STATS_CACHE[STATS_CACHE['Nome_Norm'] == norm_name]
    if matches.empty:
        matches = STATS_CACHE[STATS_CACHE['Nome_Norm'].str.contains(norm_name, regex=False, na=False)]
    if matches.empty:
        matches = STATS_CACHE[STATS_CACHE['Nome_Norm'].apply(lambda x: norm_name in x or x in norm_name if isinstance(x, str) else False)]
    if matches.empty:
        fw = norm_name.split()[0] if norm_name else ""
        if len(fw) > 2:
            matches = STATS_CACHE[STATS_CACHE['Nome_Norm'].str.contains(fw, regex=False, na=False)]
            
    if not matches.empty:
        df_m = matches.copy()
        # FIX DEFINITIVO NICO PAZ: Ordina sempre per presenze (Pv) decrescenti!
        if 'Pv' in df_m.columns:
            df_m['Pv_Num'] = pd.to_numeric(df_m['Pv'], errors='coerce').fillna(0)
            df_m = df_m.sort_values(by='Pv_Num', ascending=False)
        return df_m.iloc[0]
            
    return None

def get_macellaio_info(nome):
    row = find_player_in_stats(nome)
    if row is not None:
        try:
            amm, esp, pv = int(row.get('Amm', 0)), int(row.get('Esp', 0)), int(row.get('Pv', 1))
            if (amm >= 6 or esp >= 1) and pv > 5:
                return f"\n🪓 <b>ALLARME MACELLAIO:</b> <code>{amm} Gialli</code>, <code>{esp} Rossi</code> in <code>{pv} pres.</code>"
            else:
                return f"\n🛡 <b>Disciplinato:</b> <code>{amm} Gialli</code>, <code>{esp} Rossi</code> in <code>{pv} pres.</code>"
        except Exception: pass
    return ""

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
    query = f'"{nome}" {squadra} statistiche presenze gol assist ammonizioni transfermarkt fantacalcio'
    return f"📊 <b>STORICO WEB REALE: {html.escape(nome.upper())} ({html.escape(squadra)})</b>\n\n{fetch_real_web_data(query, max_results=2)}"

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
    if not output and WEB_SEARCH_ENABLED:
        try:
            for r in DDGS().text(query, max_results=max_results):
                output.append(f"🔎 <i>{html.escape(r['body'])}</i>\n🔗 <a href=\"{html.escape(r['href'])}\">Fonte</a>")
        except Exception: pass
    return "\n\n".join(output) if output else "⚠️ Nessun dettaglio rilevante trovato sul web."

def get_cartella_clinica_reale(nome, squadra=""):
    query = f'"{nome}" {squadra} infortunio tempi recupero rientro partite saltate SOS Fanta'
    return f"🏥 <b>CARTELLA CLINICA REALE: {html.escape(nome.upper())} ({html.escape(squadra)})</b>\n\n{fetch_real_web_data(query, max_results=2)}"

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

def advanced_trade_analyzer_3d(p1, p2, session):
    base_report = f"📊 <b>TRADE ANALYZER:</b>\n{p1['Nome']} ↔️ {p2['Nome']}"
    rosa, r1, r2 = session.get('rosa', []), p1.get('R', 'C'), p2.get('R', 'C')
    c1, c2 = sum(1 for p in rosa if p.get('ruolo') == r1), sum(1 for p in rosa if p.get('ruolo') == r2)
    impatti = []
    if r1 != r2:
        if c1 <= 3 and r1 in ['D', 'C']: impatti.append(f"🚨 <b>RISCHIO VOTI IN {r1}!</b>")
        if c2 >= 8 and r2 in ['D', 'C']: impatti.append(f"⚠️ <b>SOVRACCOPPIAMENTO IN {r2}!</b>")
    return f"{base_report}\n\n📊 <b>IMPATTO SULLA ROSA (3D):</b>\n{chr(10).join(impatti) if impatti else '✅ <b>EQUILIBRIO ROSA OK.</b>'}"

def calcola_formazione_ideale(session, df):
    rosa = session.get('rosa', [])
    if not rosa: return "❌ <b>La tua rosa è vuota!</b> Acquista o aggiungi giocatori.", None

    tit, pan = {'P': [], 'D': [], 'C': [], 'A': []}, {'P': [], 'D': [], 'C': [], 'A': []}
    for p in rosa:
        nome, r = p['nome'], p.get('ruolo', 'C')
        stats = find_player_in_stats(nome)
        mv = float(str(stats.get('Mv', 6.0)).replace(',', '.')) if stats is not None else 6.0
        fm = float(str(stats.get('Fm', 6.0)).replace(',', '.')) if stats is not None else 6.0
        pv, amm = (int(stats.get('Pv', 0)), int(stats.get('Amm', 0))) if stats is not None else (0, 0)
        tit[r].append({'nome': nome, 'power': fm + (mv - 6.0) - (amm * 0.05), 'fm': fm, 'amm': amm})

    for r in tit: tit[r] = sorted(tit[r], key=lambda x: x['power'], reverse=True)
    p_t, d_t, c_t, a_t = tit['P'][:1], tit['D'][:3], tit['C'][:4], tit['A'][:3]
    for r in ['P', 'D', 'C', 'A']: pan[r] = [x for x in tit[r] if x['nome'] not in [t['nome'] for t in p_t + d_t + c_t + a_t]]

    testo = "📋 <b>FORMAZIONE CONSIGLIATA (3-4-3)</b>\n━━━━━━━━━━━━━━━━━━━━━━\n<b>TITOLARI:</b>\n"
    testo += f"🧤 <b>P:</b> {p_t[0]['nome'] if p_t else 'Nessuno'}\n🛡️ <b>D:</b> {', '.join([x['nome'] for x in d_t])}\n"
    testo += f"⚙️ <b>C:</b> {', '.join([x['nome'] for x in c_t])}\n🎯 <b>A:</b> {', '.join([x['nome'] for x in a_t])}\n\n<b>PANCHINA:</b>\n"
    for r in ['P', 'D', 'C', 'A']:
        if pan[r]: testo += f"{ROLE_ICONS[r]} <b>{r}:</b> {', '.join([f'{x['nome']} (FM:{x['fm']})' for x in pan[r][:3]])}\n"
    
    diff = [f"⚠️ {x['nome']} ({x['amm']} gialli)" for x in p_t + d_t + c_t + a_t if x['amm'] >= 4]
    if diff: testo += "\n🚨 <b>RADAR DIFFIDATI:</b>\n" + "\n".join(diff)

    return testo, draw_pitch_image({'P': p_t, 'D': d_t, 'C': c_t, 'A': a_t}, "3-4-3")

# ==========================================
# MENU E DASHBOARD
# ==========================================
def main_menu_keyboard(session):
    markup = InlineKeyboardMarkup(row_width=2)
    if session.get('fase_asta'):
        markup.add(InlineKeyboardButton("🔴 RIPRENDI ASTA LIVE", callback_data="asta_resume"))
        markup.add(InlineKeyboardButton("🛑 Termina Asta", callback_data="asta_end"))
    else:
        markup.add(InlineKeyboardButton("🔨 AVVIA ASTA LIVE", callback_data="asta_setup_start"))
        
    markup.add(InlineKeyboardButton("👕 Esplora", callback_data="sq_start"), InlineKeyboardButton("📋 La mia Rosa", callback_data="menu_rosa"))
    markup.add(InlineKeyboardButton("⚽ Formazione", callback_data="menu_formazione"), InlineKeyboardButton("🎯 Rigoristi", callback_data="menu_rigoristi"))
    markup.add(InlineKeyboardButton("⭐ Wishlist", callback_data="menu_wishlist"), InlineKeyboardButton("📊 Trade 3D", callback_data="menu_studio_start"))
    markup.add(InlineKeyboardButton("🔥 Power Index", callback_data="menu_power"), InlineKeyboardButton("🛡️ Modificatore 6.5", callback_data="menu_modificatore"))
    markup.add(InlineKeyboardButton("🏆 Top Liberi", callback_data="menu_top_start"), InlineKeyboardButton("💎 Gemme Nascoste", callback_data="menu_gemme_start"))
    markup.add(InlineKeyboardButton("🚨 Panic Button", callback_data="menu_panic_start"), InlineKeyboardButton("🛠️ Strumenti PRO", callback_data="menu_pro"))
    markup.add(InlineKeyboardButton("⚙️ Impost. Lega", callback_data="menu_impostazioni_lega"), InlineKeyboardButton("⚙️ Sistema", callback_data="menu_sistema"))
    return markup

def send_dashboard(chat_id, user_id, message_id=None):
    session = get_session(user_id)
    stats = get_roster_stats(session)
    c, budget, slot, max_bid = stats['counts'], session['budget'], stats['slot_liberi'], stats['max_bid']
    media_str = f"(Media: {budget/slot:.1f} cr)" if slot > 0 else "✅ ROSA COMPLETA!"
    text = (
        "🏆 <b>FANTABOT PRO DASHBOARD</b> 📊\n━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Cassa:</b> <code> {budget} cr. </code>\n🛍️ <b>Slot Liberi:</b> <code> {slot} </code> <i>{media_str}</i>\n"
        f"🛑 <b>MAX BID CONSENTITO:</b> <code> {max_bid} cr. </code>\n\n"
        f"🧤 P: {c['P']}/3  │ 🛡️ D: {c['D']}/8 \n⚙️ C: {c['C']}/8  │ 🎯 A: {c['A']}/6 \n"
        "━━━━━━━━━━━━━━━━━━━━━━\n💡 <i>Cerca nome o scrivi 'ho preso [nome] a [prezzo]'</i>"
    )
    if message_id:
        try: bot.edit_message_text(text, chat_id, message_id, parse_mode="HTML", reply_markup=main_menu_keyboard(session))
        except Exception: bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=main_menu_keyboard(session))
    else: bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=main_menu_keyboard(session))

def get_strategia_asta(fase, budget, max_iniziale, modificatore_attivo):
    perc = (budget / max_iniziale) * 100 if max_iniziale else 0
    if fase == 'P': return "Lascia scannare gli altri sul primo Top assoluto. Punta al 2° o 3° top, o fai incroci perfetti per risparmiare."
    elif fase == 'D': return "Modificatore ATTIVO: prendi almeno un Top e 2 terzini di spinta." if modificatore_attivo else "Risparmia! Spendi il minimo indispensabile per i titolari e conserva crediti."
    elif fase == 'C': return "Ottimo budget! Assicurati un trequartista/rigorista, poi completa." if perc > 60 else "Budget limitato! Evita rilanci e punta su titolari low-cost o piazzisti di provincia."
    elif fase == 'A': return "ALL-IN! Scegli il tuo Bomber, sparalo alto per tagliare i deboli." if perc >= 40 else "Pochi crediti! Evita i big assoluti e componi un tridente di 2° fascia inamovibile."
    return "Tieni d'occhio i crediti e i giocatori mancanti."

def send_asta_dashboard(chat_id, user_id, message_id=None):
    session = get_session(user_id)
    df = load_data()
    fase, budget, b_iniziale = session.get('fase_asta', 'P'), session['budget'], session.get('lega_budget_iniziale', 500)
    lega_part, modif = session.get('lega_partecipanti', 8), session.get('modificatore_attivo', False)
    
    avail = get_available_players(df, session)
    giocatori = avail[avail['R'] == fase].sort_values(by='FVM', ascending=False)
    
    top_str = ""
    for i, (_, r) in enumerate(giocatori.head(5).iterrows(), 1):
        fvm_clean = str(r.get('FVM', 0)).replace(',', '.')
        fvm_num = pd.to_numeric(fvm_clean, errors='coerce') or 0
        # Scalatura realistica Fair Price Asta
        max_bid = max(1, int(fvm_num * 0.45 * (b_iniziale / 500.0)))
        top_str += f"{i}. <b>{r['Nome']}</b> ({r['Squadra']}) ─ Max: <code>{max_bid} cr.</code>\n"
    
    testo = (f"🔨 <b>ASTA LIVE - FASE: {ROLE_ICONS.get(fase, '')} {fase}</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
             f"⭐ <b>TOP 5 RIMASTI:</b>\n{top_str}\n🧠 <b>STRATEGIA:</b>\n<i>{get_strategia_asta(fase, budget, b_iniziale, modif)}</i>\n"
             f"━━━━━━━━━━━━━━━━━━━━━━\n💰 <b>Cassa:</b> <code>{budget} cr.</code> (Slot liberi: {get_roster_stats(session)['slot_liberi']})\n")
    
    if fase == 'D' and modif:
        mods = avail[(avail['R'] == 'D') & (avail['FVM'] >= 5) & (avail['FVM'] <= 35)].sort_values(by='FVM', ascending=False).head(3)
        testo += "\n🛡️ <b>TOP MODIFICATORE DA PUNTARE:</b>\n" + "\n".join([f"• {r['Nome']} - FVM: {r['FVM']}" for _, r in mods.iterrows()]) + "\n"
        
    testo += "\n💡 <i>Cerca un nome o invia un vocale! (es: + nome prezzo)</i>"
    
    markup = InlineKeyboardMarkup(row_width=2)
    next_fase = {'P': 'D', 'D': 'C', 'C': 'A', 'A': None}
    if next_fase[fase]: markup.add(InlineKeyboardButton(f"⏭️ Passa ai {next_fase[fase]}", callback_data=f"asta_fase_{next_fase[fase]}"))
    markup.add(InlineKeyboardButton("📚 Menu Principale (Studio)", callback_data="go_home"))
    
    if message_id:
        try: bot.edit_message_text(testo, chat_id, message_id, parse_mode="HTML", reply_markup=markup)
        except Exception: bot.send_message(chat_id, testo, parse_mode="HTML", reply_markup=markup)
    else: bot.send_message(chat_id, testo, parse_mode="HTML", reply_markup=markup)

# =========================================================================
# SCHEDA GIOCATORE CON PREZZI E FASCE REALI RISOLTI (LEAO, MASTANTUONO, PAZ)
# =========================================================================
def send_player_card_view(chat_id, player_name, message_id, df, session, is_scommessa=False):
    p_data = df[df['Nome'] == player_name].iloc[0]
    sq_name, ruolo, fvm = p_data.get('Squadra', '-'), str(p_data.get('R', '-')), p_data.get('FVM', 0)
    photo_embed = f'<a href="{html.escape(str(p_data.get("PhotoURL", "")).strip())}">&#8203;</a>' if str(p_data.get("PhotoURL", "")).strip().startswith('http') else ''
    
    try: fvm_val = float(str(fvm).replace(',', '.'))
    except ValueError: fvm_val = 0.0

    lega_bud = session.get('lega_budget_iniziale', 500)
    lega_part = session.get('lega_partecipanti', 8)
    part_factor = 1 + ((lega_part - 8) * 0.025)

    # CALCOLO FAIR PRICE CON CURVA ESPONENZIALE REALE PER RUOLO
    if ruolo == 'A':
        if fvm_val >= 250:   fair_price = int(fvm_val * 0.50)  # Top Assoluti (Lautaro ~180-220cr)
        elif fvm_val >= 70:  fair_price = int(fvm_val * 1.40)  # Top / Semi-Top (Leao ~120-140cr)
        elif fvm_val >= 25:  fair_price = int(fvm_val * 0.80)  # 2°/3° Fascia
        else:                fair_price = max(1, int(fvm_val * 0.40))
    elif ruolo == 'C':
        if fvm_val >= 120:   fair_price = int(fvm_val * 0.65)  # Top Centrocampo
        elif fvm_val >= 35:  fair_price = int(fvm_val * 0.85)  # Semi-Top (Mastantuono, Nico Paz ~30-45cr)
        else:                fair_price = max(1, int(fvm_val * 0.40))
    elif ruolo == 'D':
        fair_price = max(1, int(fvm_val * 0.45))
    else: # Portieri
        fair_price = max(1, int(fvm_val * 0.50))

    # Adattamento al budget e partecipanti
    fair_price = int(fair_price * (lega_bud / 500.0) * part_factor)
    fair_price = max(1, fair_price)

    max_rilancio = int(fair_price * 1.15)
    asta_stop = int(fair_price * 1.25)

    # ASSEGNAZIONE FASCE COERENTI CON I VALORI REALI
    if ruolo == 'A':
        if fair_price >= 110:   fascia = "🥇 1° Fascia 👑"
        elif fair_price >= 40:  fascia = "🥈 2° Fascia 🥇"
        elif fair_price >= 15:  fascia = "🥉 3° Fascia 🥈"
        elif fair_price >= 5:   fascia = "🚜 4° Fascia (Rotazione)"
        else:                   fascia = "🎲 Scommessa 🎲"
    elif ruolo == 'C':
        if fair_price >= 50:    fascia = "🥇 1° Fascia 👑"
        elif fair_price >= 25:  fascia = "🥈 2° Fascia 🥇"
        elif fair_price >= 10:  fascia = "🥉 3° Fascia 🥈"
        else:                   fascia = "🎲 4°/5° Fascia 🎲"
    else:
        if fair_price >= 25:    fascia = "🥇 1° Fascia 👑"
        elif fair_price >= 12:  fascia = "🥈 2° Fascia 🥇"
        else:                   fascia = "🥉 3°/4° Fascia 🥈"

    stats = get_roster_stats(session)
    info_text = (
        f"{photo_embed}📋 <b>ANALISI: {html.escape(player_name.upper())}</b> ({get_team_icon(sq_name)} {html.escape(sq_name)})\n━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>Ruolo:</b> <code>{html.escape(ruolo)}</code>\n🧮 <b>Fascia:</b> {fascia}\n⚠️ <b>Rischio/Macellaio:</b> {get_macellaio_info(player_name)}\n\n"
        f"🎯 <b>VALUTAZIONE (Lega a {lega_part} - {lega_bud} cr)</b>\n💰 <b>Fair Price:</b> <code>{fair_price} cr.</code>\n"
        f"🟢 <b>Max Consigliato:</b> <code>{max_rilancio} cr.</code>\n🛑 <b>OVERPAY:</b> <code>> {asta_stop} cr.</code>\n\n"
        f"💼 Budget residuo: <code>{session['budget']}</code> cr. (Max Bid: <code>{stats['max_bid']}</code>)\n━━━━━━━━━━━━━━━━━━━━━━\n"
    )
    
    is_asta = session.get('fase_asta') is not None
    markup = InlineKeyboardMarkup(row_width=2)
    if is_asta:
        markup.add(InlineKeyboardButton("🙋‍♂️ L'ho preso IO!", callback_data=f"buy_{player_name}"), InlineKeyboardButton("👥 Preso da ALTRI", callback_data=f"taken_{player_name}"))
        markup.add(InlineKeyboardButton("🔙 Torna alla Dashboard Asta", callback_data="asta_resume"))
    else:
        markup.add(InlineKeyboardButton("⚡ Compra (Test)", callback_data=f"buy_{player_name}"), InlineKeyboardButton("🚫 Scarta", callback_data=f"taken_{player_name}"))

    markup.add(InlineKeyboardButton("📊 Storico Reale", callback_data=f"stats_{player_name}"), InlineKeyboardButton("🏥 Clinica Web", callback_data=f"cl_{player_name}"))
    markup.add(InlineKeyboardButton("🔄 Sliding Doors", callback_data=f"sd_{player_name}"), InlineKeyboardButton("🔮 Simula What-If", callback_data=f"wi_{player_name}"))
    
    in_wl = player_name in session.get('wishlist', [])
    if is_scommessa:
        markup.add(InlineKeyboardButton("❌ Rimuovi WL" if in_wl else "⭐ Aggiungi WL", callback_data=f"wl_toggle_{player_name}"), InlineKeyboardButton("🎲 Altra Scommessa", callback_data="menu_scommessa_start"))
    else:
        markup.add(InlineKeyboardButton("❌ Rimuovi WL" if in_wl else "⭐ Aggiungi WL", callback_data=f"wl_toggle_{player_name}"))
        
    if not is_asta: markup.add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
    
    try: bot.edit_message_text(info_text, chat_id, message_id, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=False)
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

# ==========================================
# HANDLERS: ACQUISTO E VALUTAZIONE
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
        bot.send_message(chat_id, f"⚠️ <b>ALLARME!</b> Offerta oltre il <b>Max Bid</b> (<code>{stats['max_bid']}</code>).", parse_mode="HTML")
        return send_dashboard(chat_id, user_id) if not session.get('fase_asta') else send_asta_dashboard(chat_id, user_id)

    df = load_data()
    row = df[df['Nome'] == player_name].iloc[0]
    ruolo, squadra = row.get('R', 'C'), row.get('Squadra', '-')
    fvm_raw = pd.to_numeric(str(row.get('FVM', 0)).replace(',', '.').replace('-', '0'), errors='coerce')
    
    is_asta = session.get('fase_asta') is not None
    if is_asta:
        session['rosa'].append({'nome': player_name, 'prezzo': costo, 'ruolo': ruolo, 'squadra': squadra, 'fvm': fvm_raw})
        session['budget'] -= costo
        titolo_acquisto = f"✅ <b>{html.escape(player_name.upper())}</b> acquistato per <code>{costo} cr.</code>!"
    else:
        titolo_acquisto = f"🧪 <b>SIMULAZIONE: {html.escape(player_name.upper())} a {costo} cr.</b>\n<i>(Non salvato in Rosa)</i>"
    
    lega_bud, lega_part = session.get('lega_budget_iniziale', 500), session.get('lega_partecipanti', 8)
    fair_price = max(1, int((fvm_raw * (lega_bud / 1000.0)) * (1 + ((lega_part - 8) * 0.025))))
    
    if costo <= fair_price * 0.75: giudizio = f"🔥 <b>AFFARE D'ORO!</b> Hai risparmiato circa {fair_price - costo} cr."
    elif costo <= fair_price * 0.95: giudizio = f"✅ <b>OTTIMO COLPO!</b> Preso sotto costo (Fair Price: {fair_price} cr)."
    elif costo <= fair_price * 1.15: giudizio = f"⚖️ <b>PREZZO GIUSTO.</b> Pagato esattamente il suo valore."
    elif costo <= fair_price * 1.30: giudizio = f"⚠️ <b>LEGGERO OVERPAY.</b> Pagato un po' di più (Fair Price: {fair_price} cr)."
    else: giudizio = f"🚨 <b>SALASSO!</b> Strapagato! Hai speso ben {costo - fair_price} cr. in più."
        
    bot.send_message(chat_id, f"{titolo_acquisto}\n\n📊 <b>Valutazione Acquisto:</b>\n{giudizio}", parse_mode="HTML")
    
    if ruolo == 'P':
        riserve = df[(df['R'] == 'P') & (df['Squadra'] == squadra) & (df['Nome'] != player_name)].sort_values(by='FVM', ascending=False).head(2)
        r_nomi = [r['Nome'] for _, r in riserve.iterrows()]
        s_incrocio = INCROCI_PORTIERI.get(squadra, [])
        
        testo_p = f"🧤 <b>HAI PRESO UN PORTIERE! Completa il reparto:</b>\n\n"
        if r_nomi: testo_p += f"🔒 <b>Riserve {squadra}:</b> (da 1 cr): <code>{', '.join(r_nomi)}</code>\n\n"
        if s_incrocio: testo_p += f"🔄 <b>Migliori Incroci:</b> Punta sui portieri di: <b>{', '.join(s_incrocio)}</b>"
        
        mk_port = InlineKeyboardMarkup(row_width=1)
        for r_n in r_nomi: mk_port.add(InlineKeyboardButton(f"⭐ Aggiungi {r_n} a Wishlist", callback_data=f"wl_add_{r_n}"))
        bot.send_message(chat_id, testo_p, parse_mode="HTML", reply_markup=mk_port if r_nomi else None)
            
    p_lower = player_name.lower()
    if p_lower in COPPIE_NOTE:
        partner_row = df[df['Nome'].str.lower() == COPPIE_NOTE[p_lower]]
        if not partner_row.empty:
            p_n = partner_row.iloc[0]['Nome']
            mk_c = InlineKeyboardMarkup().add(InlineKeyboardButton(f"⭐ Aggiungi {p_n}", callback_data=f"wl_add_{p_n}"))
            bot.send_message(chat_id, f"🪂 <b>PARACADUTE ATTIVO</b>\nVuoi aggiungere {html.escape(p_n.upper())} alla WL?", parse_mode="HTML", reply_markup=mk_c)
            
    if is_asta: send_asta_dashboard(chat_id, user_id)
    else: send_dashboard(chat_id, user_id)

def process_whatif_price(message, player_name, user_id):
    chat_id = message.chat.id
    if not message.text.isdigit():
        msg = bot.send_message(chat_id, "❌ Inserisci un prezzo fittizio in <b>numeri</b>:", parse_mode="HTML")
        bot.register_next_step_handler(msg, process_whatif_price, player_name, user_id)
        return

    hyp_price, session, df = int(message.text), get_session(user_id), load_data()
    row = df[df['Nome'] == player_name].iloc[0]
    ruolo, fvm_raw = row.get('R', 'A'), pd.to_numeric(str(row.get('FVM', 0)).replace(',', '.').replace('-', '0'), errors='coerce')
    lega_bud, lega_part = session.get('lega_budget_iniziale', 500), session.get('lega_partecipanti', 8)
    f_part = 1 + ((lega_part - 8) * 0.025)
    fair_price = max(1, int((fvm_raw * (lega_bud / 1000.0)) * f_part))

    budget_left, slots_left = session['budget'] - hyp_price, get_roster_stats(session)['slot_liberi'] - 1
    if slots_left < 0: return bot.send_message(chat_id, "❌ Hai già la rosa piena!", parse_mode="HTML")
        
    avg_left = budget_left / slots_left if slots_left > 0 else 0
    analisi = f"🔥 <b>PREZZO D'OCCASIONE!</b> Valore: <code>{fair_price}</code>" if hyp_price <= fair_price * 0.70 else f"✅ <b>CONGRUITA:</b> Linea con il Fair Price (<code>{fair_price}</code>)." if hyp_price <= fair_price * 1.15 else f"🚨 <b>OVERPAY RISCHIOSO:</b> +<code>{hyp_price - fair_price}</code> cr. del valore ideale."

    avail = get_available_players(df, session)
    target = avail[(avail['R'] == ruolo) & (avail['Nome'] != player_name)].copy()
    target['base_p'] = target['FVM'] * (lega_bud / 1000.0) * f_part
    compatibili = target[target['base_p'] <= avg_left].sort_values(by='FVM', ascending=False).head(3)
    txt_target = "\n".join([f"• {t['Nome']} ({t['Squadra']}) ─ Fair Price: ~{int(t['base_p'])} cr." for _, t in compatibili.iterrows()]) or "• Solo scommesse o tappabuchi a 1 credito."

    final_text = (f"🔮 <b>SIMULATORE WHAT-IF: {html.escape(player_name.upper())} a {hyp_price} cr.</b>\n━━━━━━━━━━━━━━━━━━━━━━\n{analisi}\n\n"
                  f"💼 <b>IMPATTO BUDGET:</b>\n• Residuo: <code>{budget_left} cr.</code>\n• Media ({slots_left} slot): <code>{avg_left:.1f} cr.</code>\n\n"
                  f"🎯 <b>CON QUESTA MEDIA POTRAI PUNTARE SU:</b>\n{txt_target}\n━━━━━━━━━━━━━━━━━━━━━━")
    markup = InlineKeyboardMarkup(row_width=2).add(InlineKeyboardButton("🔙 Indietro", callback_data=f"sq_pl_{player_name}"), InlineKeyboardButton("🏠 Home", callback_data="go_home"))
    bot.send_message(chat_id, final_text, parse_mode="HTML", reply_markup=markup)

# ==========================================
# MESSAGGI DI CHAT (Comandi, Vocali, Testo)
# ==========================================
@bot.message_handler(commands=['clean', 'pulisci'])
def cmd_clean(m):
    for i in range(m.message_id, max(0, m.message_id - 80), -1):
        try: bot.delete_message(m.chat.id, i)
        except Exception: pass
    session = get_session(m.from_user.id)
    send_asta_dashboard(m.chat.id, m.from_user.id) if session.get('fase_asta') else send_dashboard(m.chat.id, m.from_user.id)

@bot.message_handler(commands=['start', 'menu'])
def cmd_start(m): 
    try: bot.delete_message(m.chat.id, m.message_id)
    except Exception: pass
    session = get_session(m.from_user.id)
    send_asta_dashboard(m.chat.id, m.from_user.id) if session.get('fase_asta') else send_dashboard(m.chat.id, m.from_user.id)

@bot.message_handler(content_types=['voice'])
def handle_voice(message):
    if not VOICE_ENABLED: return bot.reply_to(message, "❌ <b>Comandi Vocali disattivati.</b>", parse_mode="HTML")
    bot.reply_to(message, "🎙️ Ascolto il vocale...")
    try:
        f_info = bot.get_file(message.voice.file_id)
        with open("voice.ogg", 'wb') as f: f.write(bot.download_file(f_info.file_path))
        AudioSegment.from_ogg("voice.ogg").export("voice.wav", format="wav")
        with sr.AudioFile("voice.wav") as source: testo = sr.Recognizer().recognize_google(sr.Recognizer().record(source), language="it-IT").lower()
        bot.send_message(message.chat.id, f"🗣️ Hai detto: <i>'{html.escape(testo)}'</i>", parse_mode="HTML")
        match = re.search(r'(?:preso|comprato|ho preso)?\s*([a-zA-Z\s]+)\s*(?:a|per)?\s*(\d+)', testo)
        if match:
            n_voc, p_voc = match.group(1).strip(), int(match.group(2))
            df = load_data()
            matches = df[df['Nome'].astype(str).str.lower().str.contains(n_voc, na=False)]
            if not matches.empty:
                msg = bot.send_message(message.chat.id, f"🎯 Trovato: <b>{html.escape(matches.iloc[0]['Nome'])}</b>. Confermi a <code>{p_voc} cr.</code>?", parse_mode="HTML")
                bot.register_next_step_handler(msg, process_buy_price, matches.iloc[0]['Nome'], message.from_user.id)
            else: bot.send_message(message.chat.id, "❌ Giocatore non trovato.")
        else: bot.send_message(message.chat.id, "❌ Formato errato. Dì: 'Preso [Nome] a [Prezzo]'.")
    except Exception: bot.reply_to(message, "❌ Errore traduzione vocale.")

@bot.message_handler(func=lambda m: m.text.strip().startswith('+'))
def modalita_cecchino(message):
    try:
        parts = message.text.strip()[1:].strip().rsplit(' ', 1)
        if len(parts) != 2 or not parts[1].isdigit(): return bot.reply_to(message, "❌ Usa: <code>+ nome prezzo</code>", parse_mode="HTML")
        q_nome, costo = parts[0].strip().lower(), int(parts[1])
        df, session = load_data(), get_session(message.from_user.id)
        matches = df[df['Nome'].astype(str).str.lower().str.contains(q_nome, na=False)]
        if matches.empty: return bot.reply_to(message, f"❌ Nessun giocatore trovato per '{html.escape(q_nome)}'.", parse_mode="HTML")
        
        row, p_name = matches.iloc[0], matches.iloc[0]['Nome']
        if costo > get_roster_stats(session)['max_bid']: return bot.reply_to(message, f"⚠️ <b>ALLARME!</b> Max Bid: <code>{get_roster_stats(session)['max_bid']}</code>.", parse_mode="HTML")
        
        is_asta = session.get('fase_asta') is not None
        if is_asta:
            session['rosa'].append({'nome': p_name, 'prezzo': costo, 'ruolo': row.get('R', 'C'), 'squadra': row.get('Squadra', '-'), 'fvm': pd.to_numeric(str(row.get('FVM', 0)).replace(',', '.').replace('-', '0'), errors='coerce')})
            session['budget'] -= costo
            titolo = f"🎯 <b>CECCHINO A BERSAGLIO!</b>\n✅ Acquistato <b>{html.escape(p_name.upper())}</b> a <code>{costo} cr.</code>"
        else: titolo = f"🧪 <b>SIMULAZIONE CECCHINO: {html.escape(p_name.upper())} a {costo} cr.</b>\n<i>(Non salvato)</i>"
        
        fvm_clean = str(row.get('FVM', 0)).replace(',', '.')
        fvm_val = pd.to_numeric(fvm_clean, errors='coerce') or 0
        fair_price = max(1, int((fvm_val * (session.get('lega_budget_iniziale', 500) / 1000.0)) * (1 + ((session.get('lega_partecipanti', 8) - 8) * 0.025))))
        giudizio = f"🔥 <b>AFFARE!</b>" if costo <= fair_price * 0.75 else f"✅ <b>OTTIMO!</b>" if costo <= fair_price * 0.95 else f"⚖️ <b>GIUSTO.</b>" if costo <= fair_price * 1.15 else f"🚨 <b>SALASSO!</b>"
        
        bot.reply_to(message, f"{titolo}\n\n📊 <b>Valutazione:</b>\n{giudizio}", parse_mode="HTML")
        send_asta_dashboard(message.chat.id, message.from_user.id) if is_asta else send_dashboard(message.chat.id, message.from_user.id)
    except Exception: bot.reply_to(message, "❌ Errore acquisto rapido.")

@bot.message_handler(func=lambda m: not m.text.startswith('/') and not m.text.startswith('+') and not m.text.isdigit())
def search_player(message):
    query, df, session = message.text.strip().lower(), load_data(), get_session(message.from_user.id)
    if df is None or len(query) < 2: return
    matches = df[df['Nome'].astype(str).str.lower().str.contains(query, na=False)]
    if matches.empty: return bot.reply_to(message, "❌ Nessun giocatore trovato.")
    
    if len(matches) == 1:
        return send_player_card_view(message.chat.id, matches.iloc[0]['Nome'], None, df, session)

    markup = InlineKeyboardMarkup(row_width=1)
    for _, row in matches.head(10).iterrows(): markup.add(InlineKeyboardButton(f"{ROLE_ICONS.get(str(row.get('R','C')),'')} {row['Nome']} ({row.get('Squadra','-')})", callback_data=f"sq_pl_{row['Nome']}"))
    bot.reply_to(message, f"🔍 Scegli il giocatore esatto per <b>{html.escape(query)}</b>:", parse_mode="HTML", reply_markup=markup)

@bot.message_handler(content_types=['document'])
def handle_document(message):
    fname = message.document.file_name.lower()
    if not (fname.endswith('.csv') or fname.endswith('.xlsx') or fname.endswith('.xls')): return bot.reply_to(message, "❌ Invia solo file <code>.csv</code> o <code>.xlsx</code>!", parse_mode="HTML")
    try:
        f_data = bot.download_file(bot.get_file(message.document.file_id).file_path)
        if "statistiche" in fname:
            with open("Statistiche.xlsx", 'wb') as f: f.write(f_data)
            load_data(force_reload=True)
            bot.reply_to(message, "✅ <b>STATISTICHE SINCRONIZZATE!</b>", parse_mode="HTML")
        else:
            with open("Lista_Finale_Master.csv" if fname.endswith('.csv') else "listone.xlsx", 'wb') as f: f.write(f_data)
            load_data(force_reload=True)
            bot.reply_to(message, "✅ <b>DATABASE LISTONE AGGIORNATO!</b>", parse_mode="HTML")
    except Exception as e: bot.send_message(message.chat.id, f"❌ Errore caricamento: {str(e)}")

# ==========================================
# GESTIONE CALLBACKS (Bottoni Inline)
# ==========================================
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    safe_answer_callback(call.id)
    user_id, chat_id = call.from_user.id, call.message.chat.id
    session, df = get_session(user_id), load_data()

    if call.data == "clear_screen":
        for i in range(call.message.message_id, max(0, call.message.message_id - 80), -1):
            try: bot.delete_message(chat_id, i)
            except Exception: pass
        send_asta_dashboard(chat_id, user_id) if session.get('fase_asta') else send_dashboard(chat_id, user_id)

    elif call.data == "go_home": 
        session['compare_p1'] = None
        for i in range(call.message.message_id, max(0, call.message.message_id - 10), -1):
            try: bot.delete_message(chat_id, i)
            except Exception: pass
        send_dashboard(chat_id, user_id)
        
    elif call.data == "asta_setup_start":
        markup = InlineKeyboardMarkup(row_width=3)
        markup.add(InlineKeyboardButton("6", callback_data="astap_6"), InlineKeyboardButton("8", callback_data="astap_8"), InlineKeyboardButton("10", callback_data="astap_10"), InlineKeyboardButton("12", callback_data="astap_12"))
        bot.edit_message_text("🔨 <b>SETUP ASTA</b>\nQuanti partecipanti ci sono nella lega?", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif call.data.startswith("astap_"):
        session['lega_partecipanti'] = int(call.data.split("_")[1])
        markup = InlineKeyboardMarkup(row_width=3).add(InlineKeyboardButton("300", callback_data="astab_300"), InlineKeyboardButton("500", callback_data="astab_500"), InlineKeyboardButton("1000", callback_data="astab_1000"))
        bot.edit_message_text("💰 Qual è il budget iniziale?", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif call.data.startswith("astab_"):
        session['lega_budget_iniziale'] = session['budget'] = int(call.data.split("_")[1])
        markup = InlineKeyboardMarkup(row_width=2).add(InlineKeyboardButton("✅ SÌ (Voti alti)", callback_data="astam_si"), InlineKeyboardButton("❌ NO (Classic)", callback_data="astam_no"))
        bot.edit_message_text("🛡️ Utilizzate il <b>Modificatore Difesa</b>?", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif call.data.startswith("astam_"):
        session['modificatore_attivo'], session['fase_asta'], session['rosa'] = (call.data == "astam_si"), 'P', []
        send_asta_dashboard(chat_id, user_id, call.message.message_id)

    elif call.data.startswith("asta_fase_"):
        session['fase_asta'] = call.data.split("_")[2]
        send_asta_dashboard(chat_id, user_id, call.message.message_id)
        
    elif call.data == "asta_resume": send_asta_dashboard(chat_id, user_id, call.message.message_id)
    elif call.data == "asta_end":
        session['fase_asta'] = None
        safe_answer_callback(call.id, "Asta terminata! Rosa confermata.", show_alert=True)
        send_dashboard(chat_id, user_id, call.message.message_id)

    elif call.data == "force_download_listone":
        msg = bot.send_message(chat_id, "⏳ <i>Collegamento ai server ufficiali per il download...</i>", parse_mode="HTML")
        bot.edit_message_text("✅ <b>LISTONE AGGIORNATO CON SUCCESSO!</b>" if auto_download_listone() else "❌ <b>Download fallito.</b>", chat_id, msg.message_id, parse_mode="HTML")

    elif call.data == "menu_impostazioni_lega":
        markup = InlineKeyboardMarkup(row_width=3)
        markup.row(InlineKeyboardButton("💰 Bud: 300", callback_data="imposta_bud_300"), InlineKeyboardButton("💰 500", callback_data="imposta_bud_500"), InlineKeyboardButton("💰 1000", callback_data="imposta_bud_1000"))
        markup.row(InlineKeyboardButton("👥 Lega: 8", callback_data="imposta_part_8"), InlineKeyboardButton("👥 a 10", callback_data="imposta_part_10"), InlineKeyboardButton("👥 a 12", callback_data="imposta_part_12"))
        markup.add(InlineKeyboardButton("🔄 Reset (500 cr - 8 sq)", callback_data="imposta_reset"), InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text(f"⚙️ <b>IMPOSTAZIONI</b>\n💰 Budget: <code>{session.get('lega_budget_iniziale', 500)} cr.</code>\n👥 Partecipanti: <code>{session.get('lega_partecipanti', 8)} squadre</code>", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif call.data.startswith("imposta_bud_"):
        session['lega_budget_iniziale'] = session['budget'] = int(call.data.replace("imposta_bud_", ""))
        safe_answer_callback(call.id, f"✅ Budget: {session['budget']} cr!", True)
        call.data = "menu_impostazioni_lega"
        handle_callbacks(call)

    elif call.data.startswith("imposta_part_"):
        session['lega_partecipanti'] = int(call.data.replace("imposta_part_", ""))
        safe_answer_callback(call.id, f"✅ Partecipanti: {session['lega_partecipanti']}!", True)
        call.data = "menu_impostazioni_lega"
        handle_callbacks(call)

    elif call.data == "imposta_reset":
        session['lega_budget_iniziale'], session['lega_partecipanti'], session['budget'] = 500, 8, 500
        safe_answer_callback(call.id, "✅ Lega resettata!", True)
        call.data = "menu_impostazioni_lega"
        handle_callbacks(call)

    elif call.data == "menu_formazione":
        t, img = calcola_formazione_ideale(session, df)
        markup = InlineKeyboardMarkup().add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.send_photo(chat_id, img, caption=t, parse_mode="HTML", reply_markup=markup) if img else bot.send_message(chat_id, t, parse_mode="HTML", reply_markup=markup)

    elif call.data == "menu_rigoristi":
        t = "🎯 <b>RADAR RIGORISTI</b>\n━━━━━━━━━━━━━━━━━━━━━━\n" + "".join([f"<b>{get_team_icon(sq)} {sq}:</b>\n⚽ Rig: {', '.join(d['rigoristi'])}\n🎯 Puniz: {', '.join(d['punizioni'])}\n\n" for sq, d in GERARCHIE_RIGORISTI.items()])
        bot.edit_message_text(t, chat_id, call.message.message_id, parse_mode="HTML", reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🏠 Home", callback_data="go_home")))

    elif call.data == "menu_power":
        hot = [f"🔥 <b>{p['nome']}</b> (FM: <code>{fm}</code>)" for p in session.get('rosa', []) if (stats := find_player_in_stats(p['nome'])) is not None and (fm := float(str(stats.get('Fm', 6.0)).replace(',', '.'))) >= 6.8]
        t = "🔥 <b>POWER INDEX</b>\n━━━━━━━━━━━━━━━━━━━━━━\n" + ("\n".join(hot) if hot else "<i>Nessuno in stato di grazia.</i>")
        bot.edit_message_text(t, chat_id, call.message.message_id, parse_mode="HTML", reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🏠 Home", callback_data="go_home")))

    elif call.data == "menu_sistema": bot.edit_message_text("⚙️ <b>SISTEMA</b>", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=system_menu_keyboard())
    elif call.data == "reload_excel": 
        load_data(force_reload=True)
        bot.send_message(chat_id, "⚡ <b>Dati sincronizzati!</b>", parse_mode="HTML")
    elif call.data == "reset_confirm":
        user_sessions[user_id] = {'budget': session.get('lega_budget_iniziale', 500), 'rosa': [], 'wishlist': session.get('wishlist', []), 'scartati': [], 'compare_p1': None, 'lega_budget_iniziale': session.get('lega_budget_iniziale', 500), 'lega_partecipanti': session.get('lega_partecipanti', 8), 'modificatore_attivo': session.get('modificatore_attivo', False), 'fase_asta': None}
        send_dashboard(chat_id, user_id, call.message.message_id)

    elif call.data == "menu_pro": bot.edit_message_text("🛠️ <b>STRUMENTI PRO</b>", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=pro_menu_keyboard())
    elif call.data == "pro_stakanov":
        markup = InlineKeyboardMarkup(row_width=1)
        for _, r in get_available_players(df, session)[(get_available_players(df, session)['R'].isin(['D', 'C'])) & (get_available_players(df, session)['FVM'] <= 6)].head(10).iterrows(): markup.add(InlineKeyboardButton(f"🧱 {r['Nome']} ({r['Squadra']})", callback_data=f"sq_pl_{r['Nome']}"))
        markup.add(InlineKeyboardButton("🔙 Menu PRO", callback_data="menu_pro"))
        bot.edit_message_text("🧱 <b>STAKANOVISTI</b>", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif call.data == "pro_griglia":
        d_liberi = get_available_players(df, session)[(get_available_players(df, session)['R'] == 'D') & (get_available_players(df, session)['FVM'] <= 20)]
        trio = []
        for subset in [d_liberi[d_liberi['Squadra'].isin(['Empoli', 'Lecce', 'Parma', 'Verona', 'Cagliari', 'Venezia', 'Como', 'Monza', 'Frosinone', 'Sassuolo'])], d_liberi[(d_liberi['Squadra'].isin(['Empoli', 'Lecce', 'Parma', 'Verona', 'Cagliari', 'Venezia', 'Como', 'Monza', 'Frosinone', 'Sassuolo']))], d_liberi[d_liberi['Squadra'].isin(['Fiorentina', 'Bologna', 'Torino', 'Lazio', 'Atalanta', 'Genoa', 'Udinese'])]]:
            if not subset.empty: trio.append(subset.sample(1).iloc[0])
        markup = InlineKeyboardMarkup(row_width=1)
        for r in set([t['Nome'] for t in trio]):
            row = df[df['Nome'] == r].iloc[0]
            markup.add(InlineKeyboardButton(f"🛡️ {row['Nome']} ({row['Squadra']}) ─ FVM: {row['FVM']}", callback_data=f"sq_pl_{row['Nome']}"))
        markup.add(InlineKeyboardButton("🔄 Genera Altro Trio", callback_data="pro_griglia"), InlineKeyboardButton("🔙 Menu PRO", callback_data="menu_pro"))
        bot.edit_message_text("🕸️ <b>GRIGLIA TATTICA (TRIO)</b>\n2 difensori piccole + 1 fascia media:", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif call.data == "pro_spiccioli":
        avail = get_available_players(df, session)
        low = avail[pd.to_numeric(avail['FVM'], errors='coerce').fillna(0) <= 5]
        markup = InlineKeyboardMarkup(row_width=1)
        for _, r in (low.sample(min(10, len(low))) if not low.empty else avail.head(10)).iterrows(): markup.add(InlineKeyboardButton(f"🎰 {r['Nome']} ({r['R']} - {r['Squadra']})", callback_data=f"sq_pl_{r['Nome']}"))
        markup.add(InlineKeyboardButton("🔄 Aggiorna", callback_data="pro_spiccioli"), InlineKeyboardButton("🔙 Menu PRO", callback_data="menu_pro"))
        bot.edit_message_text(f"🎰 <b>TAPPABUCHI LOW-COST</b>", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif call.data.startswith("cl_"):
        p = call.data.replace("cl_", "")
        bot.edit_message_text(get_cartella_clinica_reale(p, df[df['Nome'] == p].iloc[0].get('Squadra', '')), chat_id, bot.send_message(chat_id, "⏳ <i>Ricerca notizie...</i>", parse_mode="HTML").message_id, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(row_width=2).add(InlineKeyboardButton("🔙 Indietro", callback_data=f"sq_pl_{p}"), InlineKeyboardButton("🏠 Home", callback_data="go_home")))

    elif call.data.startswith("stats_"):
        p = call.data.replace("stats_", "")
        bot.edit_message_text(get_storico_excel_o_web(p, df[df['Nome'] == p].iloc[0].get('Squadra', '')), chat_id, call.message.message_id, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(row_width=2).add(InlineKeyboardButton("🔙 Indietro", callback_data=f"sq_pl_{p}"), InlineKeyboardButton("🏠 Home", callback_data="go_home")))

    elif call.data.startswith("wi_"): bot.register_next_step_handler(bot.send_message(chat_id, f"🔮 <b>SIMULATORE WHAT-IF</b> per <b>{html.escape(call.data.replace('wi_', ''))}</b>:", parse_mode="HTML"), process_whatif_price, call.data.replace("wi_", ""), user_id)

    elif call.data.startswith("sd_"):
        p, avail = call.data.replace("sd_", ""), get_available_players(df, session)
        cloni = avail[(avail['R'] == df[df['Nome'] == p].iloc[0]['R']) & (avail['Nome'] != p)].copy()
        cloni['d'] = abs(cloni['FVM'] - float(df[df['Nome'] == p].iloc[0].get('FVM', 0)))
        markup = InlineKeyboardMarkup(row_width=1)
        for _, c in cloni.sort_values(by=['d', 'FVM'], ascending=[True, False]).head(4).iterrows(): markup.add(InlineKeyboardButton(f"🔄 {c['Nome']} ({c['Squadra']})", callback_data=f"sq_pl_{c['Nome']}"))
        markup.add(InlineKeyboardButton("🔙 Indietro", callback_data=f"sq_pl_{p}"))
        bot.send_message(chat_id, f"🔄 <b>SLIDING DOORS per {html.escape(p)}:</b>", parse_mode="HTML", reply_markup=markup)

    elif call.data.startswith("wl_add_"):
        if call.data.replace("wl_add_", "") not in session['wishlist']: session['wishlist'].append(call.data.replace("wl_add_", ""))
        safe_answer_callback(call.id, f"✅ {call.data.replace('wl_add_', '')} in Wishlist!", True)
        send_asta_dashboard(chat_id, user_id, call.message.message_id) if session.get('fase_asta') else send_dashboard(chat_id, user_id, call.message.message_id)

    elif call.data.startswith("menu_modificatore"):
        p, mods = int(call.data.split("_page_")[1]) if "_page_" in call.data else 1, get_available_players(df, session)[(get_available_players(df, session)['R'] == 'D') & (get_available_players(df, session)['FVM'] <= 35)].sort_values(by='FVM', ascending=False)
        markup, nav = InlineKeyboardMarkup(row_width=1), []
        for _, r in mods.iloc[(p-1)*15:p*15].iterrows(): markup.add(InlineKeyboardButton(f"🛡️ {r['Nome']} (FVM: {r['FVM']})", callback_data=f"sq_pl_{r['Nome']}"))
        if p > 1: nav.append(InlineKeyboardButton("◀️ Precedenti", callback_data=f"menu_modificatore_page_{p - 1}"))
        if len(mods) > p*15: nav.append(InlineKeyboardButton(f"➕ Altri", callback_data=f"menu_modificatore_page_{p + 1}"))
        if nav: markup.row(*nav)
        markup.add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text(f"🛡️ <b>MODIFICATORE 6.5</b> (Pag. {p})", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif call.data == "menu_rosa":
        r = "\n".join([f"<b>{ROLE_ICONS[ru]} {ru}:</b>\n" + "".join([f"• {html.escape(p['nome'])} (<code>{p['prezzo']} cr.</code>)\n" for p in session.get('rosa', []) if p.get('ruolo') == ru]) for ru in ['P', 'D', 'C', 'A'] if any(p.get('ruolo') == ru for p in session.get('rosa', []))])
        bot.edit_message_text(f"📋 <b>LA TUA ROSA:</b>\n───────────────────────────\n{r}" if r else "📋 <b>ROSA VUOTA!</b>", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🏠 Home", callback_data="go_home")))

    elif call.data == "sq_start":
        markup = InlineKeyboardMarkup(row_width=2).add(*[InlineKeyboardButton(f"{get_team_icon(s)} {s}", callback_data=f"sq_sq_{s}") for s in sorted(df['Squadra'].dropna().astype(str).unique())]).add(InlineKeyboardButton("🔙 Home", callback_data="go_home"))
        bot.edit_message_text("👕 <b>ESPLORA SQUADRE</b>", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif call.data.startswith("sq_sq_"): bot.edit_message_text("Scegli ruolo:", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(row_width=4).add(*[InlineKeyboardButton(f"{ROLE_ICONS[r]} {r}", callback_data=f"sq_ru_{call.data.replace('sq_sq_', '')}_{r}") for r in ['P', 'D', 'C', 'A']]).add(InlineKeyboardButton("🔙 Squadre", callback_data="sq_start")))
    elif call.data.startswith("sq_ru_"):
        sq, ru = call.data.split("_")[2], call.data.split("_")[3]
        markup = InlineKeyboardMarkup(row_width=1).add(*[InlineKeyboardButton(f"{'⭐ ' if r['Nome'] in session.get('wishlist', []) else ''}{ROLE_ICONS.get(ru,'')} {r['Nome']} ─ FVM:{r.get('FVM', '-')}", callback_data=f"sq_pl_{r['Nome']}") for _, r in df[(df['Squadra'] == sq) & (df['R'] == ru)].iterrows()]).add(InlineKeyboardButton("🔙 Cambia Ruolo", callback_data=f"sq_sq_{sq}"))
        bot.edit_message_text(f"Giocatori ({sq} - {ru}):", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif call.data == "menu_top_start" or call.data == "menu_gemme_start" or call.data == "menu_panic_start":
        pfx = call.data.split("_")[1]
        t = {"top": "🏆 TOP LIBERI", "gemme": "💎 GEMME NASCOSTE (FVM 6-20)", "panic": "🚨 PANIC BUTTON (FVM 1-5)"}[pfx]
        bot.edit_message_text(f"{t} - Scegli ruolo:", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(row_width=4).add(*[InlineKeyboardButton(f"{ROLE_ICONS[r]} {r}", callback_data=f"menu_{pfx}_ru_{r}") for r in ['P', 'D', 'C', 'A']]).add(InlineKeyboardButton("🔙 Home", callback_data="go_home")))

    elif call.data.startswith("menu_top_ru_") or call.data.startswith("menu_gemme_ru_") or call.data.startswith("menu_panic_ru_"):
        pfx, raw = call.data.split("_")[1], call.data.split("_ru_")[1]
        r, p = (raw.split("_page_")[0], int(raw.split("_page_")[1])) if "_page_" in raw else (raw, 1)
        avail = get_available_players(df, session)
        lst = avail[avail['R'] == r]
        if pfx == "gemme": lst = lst[(lst['FVM'] <= 20) & (lst['FVM'] >= 6)]
        elif pfx == "panic": lst = lst[(lst['FVM'] <= 5) & (lst['FVM'] >= 1)]
        lst = lst.sort_values(by='FVM', ascending=False)
        
        markup, nav = InlineKeyboardMarkup(row_width=1), []
        for _, row in lst.iloc[(p-1)*15:p*15].iterrows(): markup.add(InlineKeyboardButton(f"🔍 {row['Nome']} ({row.get('Squadra','-')}) FVM:{row.get('FVM','-')}", callback_data=f"sq_pl_{row['Nome']}"))
        if p > 1: nav.append(InlineKeyboardButton("◀️", callback_data=f"menu_{pfx}_ru_{r}_page_{p - 1}"))
        if len(lst) > p*15: nav.append(InlineKeyboardButton("➕", callback_data=f"menu_{pfx}_ru_{r}_page_{p + 1}"))
        if nav: markup.row(*nav)
        markup.add(InlineKeyboardButton("🔙 Cambia Ruolo", callback_data=f"menu_{pfx}_start"), InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text(f"{pfx.upper()} - {ROLE_ICONS[r]} {r} (Pag. {p}):", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif call.data == "menu_scommessa_start":
        avail = get_available_players(df, session)
        sl = [avail[avail['Nome'].astype(str).str.lower().str.contains(sc)] for sc in DATABASE_SCOMMESSE_PURE if not avail[avail['Nome'].astype(str).str.lower().str.contains(sc)].empty]
        send_player_card_view(chat_id, pd.concat(sl).drop_duplicates().sample(1).iloc[0]['Nome'], call.message.message_id, df, session, True) if sl else safe_answer_callback(call.id, "Nessuna scommessa!", True)

    elif call.data == "menu_studio_start":
        session['compare_p1'] = None
        bot.edit_message_text("📊 <b>STUDIO 3D</b>\nSquadra TUO giocatore:", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(row_width=2).add(*[InlineKeyboardButton(f"{get_team_icon(s)} {s}", callback_data=f"std1_sq_{s}") for s in sorted(df['Squadra'].dropna().astype(str).unique())]).add(InlineKeyboardButton("🔙 Home", callback_data="go_home")))

    elif call.data.startswith("std1_sq_"): bot.edit_message_text("Scegli ruolo:", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(row_width=4).add(*[InlineKeyboardButton(f"{ROLE_ICONS[r]} {r}", callback_data=f"std1_ru_{call.data.replace('std1_sq_', '')}_{r}") for r in ['P', 'D', 'C', 'A']]).add(InlineKeyboardButton("🔙", callback_data="menu_studio_start")))
    elif call.data.startswith("std1_ru_"): bot.edit_message_text("Seleziona:", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(row_width=1).add(*[InlineKeyboardButton(f"{r['Nome']}", callback_data=f"std1_pl_{r['Nome']}") for _, r in df[(df['Squadra'] == call.data.split('_')[2]) & (df['R'] == call.data.split('_')[3])].iterrows()]).add(InlineKeyboardButton("🔙", callback_data=f"std1_sq_{call.data.split('_')[2]}")))
    elif call.data.startswith("std1_pl_"):
        session['compare_p1'] = df[df['Nome'] == call.data.replace("std1_pl_", "")].iloc[0].to_dict()
        bot.edit_message_text(f"📊 <b>Hai scelto {html.escape(session['compare_p1']['Nome'].upper())}</b>\nSquadra PROPOSTO:", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(row_width=2).add(*[InlineKeyboardButton(f"{get_team_icon(s)} {s}", callback_data=f"std2_sq_{s}") for s in sorted(df['Squadra'].dropna().astype(str).unique())]).add(InlineKeyboardButton("🔙 Reset", callback_data="menu_studio_start")))
    elif call.data.startswith("std2_sq_"): bot.edit_message_text("Scegli:", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(row_width=1).add(*[InlineKeyboardButton(f"🆚 {r['Nome']}", callback_data=f"std2_pl_{r['Nome']}") for _, r in df[(df['Squadra'] == call.data.replace("std2_sq_", "")) & (df['R'] == session['compare_p1']['R']) & (df['Nome'] != session['compare_p1']['Nome'])].iterrows()]).add(InlineKeyboardButton("🔙", callback_data=f"std1_pl_{session['compare_p1']['Nome']}")))
    elif call.data.startswith("std2_pl_"): bot.edit_message_text(advanced_trade_analyzer_3d(session['compare_p1'], df[df['Nome'] == call.data.replace("std2_pl_", "")].iloc[0].to_dict(), session), chat_id, call.message.message_id, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(row_width=2).add(InlineKeyboardButton(f"⚡ Compra {session['compare_p1']['Nome']}", callback_data=f"buy_{session['compare_p1']['Nome']}"), InlineKeyboardButton(f"⚡ Compra {call.data.replace('std2_pl_', '')}", callback_data=f"buy_{call.data.replace('std2_pl_', '')}")).add(InlineKeyboardButton("🔄 Nuovo", callback_data="menu_studio_start"), InlineKeyboardButton("🏠 Home", callback_data="go_home")))

    elif call.data.startswith("sq_pl_"): send_player_card_view(chat_id, call.data.replace("sq_pl_", ""), call.message.message_id, df, session)
    elif call.data.startswith("buy_"): bot.register_next_step_handler(bot.send_message(chat_id, f"💰 Crediti spesi per <b>{html.escape(call.data.replace('buy_', ''))}</b>?:", parse_mode="HTML"), process_buy_price, call.data.replace("buy_", ""), user_id)
    
    elif call.data.startswith("taken_"):
        if call.data.replace("taken_", "") not in session['scartati']: session['scartati'].append(call.data.replace("taken_", ""))
        safe_answer_callback(call.id, text=f"🚫 Rimosso (preso da altri)!", show_alert=False)
        send_asta_dashboard(chat_id, user_id, call.message.message_id) if session.get('fase_asta') else send_dashboard(chat_id, user_id, call.message.message_id)

    elif call.data.startswith("wl_toggle_"):
        if call.data.replace("wl_toggle_", "") in session.get('wishlist', []): session['wishlist'].remove(call.data.replace("wl_toggle_", ""))
        else: session.setdefault('wishlist', []).append(call.data.replace("wl_toggle_", ""))
        send_player_card_view(chat_id, call.data.replace("wl_toggle_", ""), call.message.message_id, df, session)

    elif call.data == "menu_wishlist": bot.edit_message_text("⭐ <b>WISHLIST:</b>\n" if session.get('wishlist') else "⭐ <b>VUOTA</b>", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(row_width=1).add(*[InlineKeyboardButton(f"🔍 {n}", callback_data=f"sq_pl_{n}") for n in session.get('wishlist', [])]).add(InlineKeyboardButton("🏠 Home", callback_data="go_home")))

if __name__ == '__main__':
    try: bot.remove_webhook()
    except: pass
    print("🚀 FANTABOT PRO ASTA LIVE In Ascolto!")
    bot.infinity_polling(timeout=10, long_polling_timeout=5, skip_pending=True)
