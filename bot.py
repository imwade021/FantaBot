import os
import io
import re
import html
import json
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
    return "🚀 FantaBot PRO (Asta Live & Push Notifications) è online!"

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

# Import opzionali
try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_ENABLED = True
except ImportError:
    PIL_ENABLED = False

try:
    import speech_recognition as sr
    from pydub import AudioSegment
    VOICE_ENABLED = True
except ImportError:
    VOICE_ENABLED = False

try:
    from duckduckgo_search import DDGS
    WEB_SEARCH_ENABLED = True
except ImportError:
    WEB_SEARCH_ENABLED = False

# ==========================================
# CONFIGURAZIONE & TOKEN
# ==========================================
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("⚠️ ERRORE: La variabile d'ambiente BOT_TOKEN non è impostata!")

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
    'Fiorentina': {'rigoristi': ['Gudmundsson A.', 'Kean', 'Mandragora'], 'punizioni': ['Gudmundsson A.', 'Mastantuono', 'Atta']},
    'Inter': {'rigoristi': ['Calhanoglu', 'Zielinski', 'Martinez L.'], 'punizioni': ['Calhanoglu', 'Dimarco', 'Zielinski']},
    'Juventus': {'rigoristi': ['Vlahovic', 'Kolo Muani', 'Yildiz'], 'punizioni': ['Vlahovic', 'Locatelli', 'Cambiaso']},
    'Milan': {'rigoristi': ['Pulisic', 'Morata', 'Nkunku'], 'punizioni': ['Modric', 'Pulisic', 'Saelemaekers']},
    'Napoli': {'rigoristi': ['Kvaratskhelia', 'Politano', 'Hojlund'], 'punizioni': ['Kvaratskhelia', 'Politano', 'Neres']},
    'Roma': {'rigoristi': ['Dybala', 'Pellegrini Lo.', 'Soulé'], 'punizioni': ['Dybala', 'Pellegrini Lo.', 'Soulé']},
}

DATABASE_SCOMMESSE_PURE = ['bernabe', 'fazzini', 'bonny', 'oristanio', 'paz', 'marchwinski', 'castro', 'belahyane', 'conceicao', 'savona', 'mbangula']
COPPIE_NOTE = {'sommer': 'martinez jo.', 'martinez jo.': 'sommer', 'di gregorio': 'perin', 'perin': 'di gregorio', 'maignan': 'sportiello', 'sportiello': 'maignan', 'svilar': 'ryan', 'ryan': 'svilar'}

def normalize_str(s):
    if not isinstance(s, str): return ""
    s = unicodedata.normalize('NFKD', s).encode('ASCII', 'ignore').decode('utf-8')
    return " ".join(re.sub(r"[^\w\s]", "", s).lower().split())

def safe_answer_callback(call_id, text=None, show_alert=False):
    try: bot.answer_callback_query(call_id, text=text, show_alert=show_alert)
    except Exception: pass

def get_team_icon(squadra): return TEAM_COLORS.get(str(squadra).strip(), '🛡️')

# ==========================================
# DATABASE & PUSH NOTIFICATIONS
# ==========================================
DATA_CACHE = None
STATS_CACHE = None
REGISTERED_CHATS = set() # Per le notifiche PUSH

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
            except Exception as e: print(f"⚠️ Errore CSV: {e}")

    if STATS_CACHE is None or force_reload:
        stats_file = next((f for f in os.listdir('.') if 'statistiche' in f.lower() and f.endswith(('.xlsx', '.xls', '.csv'))), None)
        if stats_file:
            try:
                STATS_CACHE = pd.read_csv(stats_file) if stats_file.endswith('.csv') else pd.read_excel(stats_file, header=1)
                STATS_CACHE['Nome_Norm'] = STATS_CACHE['Nome'].apply(normalize_str)
            except Exception as e: print(f"⚠️ Errore Statistiche: {e}")
    return DATA_CACHE

def auto_download_and_inject_virtual_players():
    """Scarica il listone, inietta giocatori da TM e MANDA NOTIFICHE PUSH!"""
    print("🔄 Avvio sincronizzazione e ricerca di mercato...")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    try:
        res = requests.get(LISTONE_URL, headers=headers, timeout=15)
        if res.status_code == 200:
            with open("Lista-FantaAsta-Fantacalcio.csv", "wb") as f: f.write(res.content)
    except Exception: pass

    df_local = load_data(force_reload=True)
    
    # Simulazione Scraping Transfermarkt 
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

    # 🚨 NOTIFICHE PUSH AGLI UTENTI
    for g in new_injections:
        testo_push = (
            f"🚨 <b>NUOVO ACQUISTO UFFICIALE!</b> 🚨\n━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>{html.escape(g['Nome'])}</b>\n"
            f"🛡️ <b>Squadra:</b> {get_team_icon(g['Squadra'])} {g['Squadra']}\n"
            f"📌 <b>Ruolo:</b> {ROLE_ICONS.get(g['R'], '')} {g['R']}\n"
            f"💰 <b>FVM Stimato:</b> <code>~{g['FVM']} cr.</code>\n\n"
            f"✅ <i>Giocatore già iniettato in memoria! Pronto all'uso.</i>"
        )
        markup = InlineKeyboardMarkup().add(InlineKeyboardButton("🔍 Apri Scheda", callback_data=f"sq_pl_{g['Nome']}"))
        for chat_id in REGISTERED_CHATS:
            try: bot.send_message(chat_id, testo_push, parse_mode="HTML", reply_markup=markup)
            except Exception: pass
    return True

load_data()
try:
    scheduler = BackgroundScheduler()
    scheduler.add_job(auto_download_and_inject_virtual_players, 'interval', minutes=60) # Esegue ogni ora
    scheduler.start()
except Exception as e: print(f"⚠️ Scheduler error: {e}")

# ==========================================
# GESTIONE SESSIONE & ASTA LIVE BUDGET
# ==========================================
user_sessions = {}
def get_session(user_id):
    if user_id not in user_sessions: 
        user_sessions[user_id] = {
            'budget': 500, 'rosa': [], 'wishlist': [], 'scartati': [], 'compare_p1': None,
            'lega_budget_iniziale': 500, 'lega_partecipanti': 12, # Target Lega 12
            'asta_live': False, 'fase_attiva': None, 
            'budget_reparti': {'P': 30, 'D': 75, 'C': 125, 'A': 270} # Ripartizione Modificatore
        }
    return user_sessions[user_id]

def recalcola_budget_reparti(session):
    """Ricalcola il tesoretto per i ruoli successivi quando si chiude un reparto"""
    cassa_rimasta = session['budget']
    fasi_rimaste = []
    
    # Valuta in base a cosa manca da chiudere
    count_r = {'P': 0, 'D': 0, 'C': 0, 'A': 0}
    for p in session['rosa']: count_r[p.get('ruolo', 'C')] += 1
    
    if count_r['P'] < 3: fasi_rimaste.append('P')
    if count_r['D'] < 8: fasi_rimaste.append('D')
    if count_r['C'] < 8: fasi_rimaste.append('C')
    if count_r['A'] < 6: fasi_rimaste.append('A')

    # Pesi per Lega 12 con Modificatore (P:6, D:15, C:25, A:54)
    pesi_base = {'P': 6, 'D': 15, 'C': 25, 'A': 54}
    peso_totale_rimasto = sum(pesi_base[r] for r in fasi_rimaste)
    
    if peso_totale_rimasto > 0:
        for r in fasi_rimaste:
            nuovo_target = int(cassa_rimasta * (pesi_base[r] / peso_totale_rimasto))
            session['budget_reparti'][r] = nuovo_target

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
            if (amm >= 6 or esp >= 1) and pv > 5: return f"\n🪓 <b>ALLARME MACELLAIO:</b> <code>{amm} Gialli</code>, <code>{esp} Rossi</code>!"
        except Exception: pass
    return ""

# ==========================================
# CARDS E DASHBOARD
# ==========================================
def main_menu_keyboard():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("🚀 INIZIO ASTA LIVE", callback_data="inizio_asta_live"))
    markup.add(InlineKeyboardButton("👕 Esplora", callback_data="sq_start"), InlineKeyboardButton("📋 La mia Rosa", callback_data="menu_rosa"))
    markup.add(InlineKeyboardButton("⭐ Wishlist", callback_data="menu_wishlist"), InlineKeyboardButton("📊 Trade 3D", callback_data="menu_studio_start"))
    markup.add(InlineKeyboardButton("🏆 Top Liberi", callback_data="menu_top_start"), InlineKeyboardButton("🛠️ Tool PRO", callback_data="menu_pro"))
    markup.add(InlineKeyboardButton("⚙️ Impostazioni Lega", callback_data="menu_impostazioni_lega"), InlineKeyboardButton("⚙️ Sistema", callback_data="menu_sistema"))
    return markup

def send_dashboard(chat_id, user_id, message_id=None):
    session = get_session(user_id)
    stats = get_roster_stats(session)
    c, budget, slot_liberi, max_bid = stats['counts'], session['budget'], stats['slot_liberi'], stats['max_bid']
    salva_chat_id(chat_id) # Registra l'utente per le notifiche push

    media_str = f"(Media: {budget/slot_liberi:.1f} cr)" if slot_liberi > 0 else "✅ ROSA COMPLETA!"
    text = (
        "🏆 <b>FANTABOT PRO DASHBOARD</b> 📊\n━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Cassa:</b> <code> {budget} cr. </code>\n"
        f"🛍️ <b>Slot Liberi:</b> <code> {slot_liberi} </code> <i>{media_str}</i>\n"
        f"🛑 <b>MAX BID CONSENTITO:</b> <code> {max_bid} cr. </code>\n\n"
        f"🧤 P: {c['P']}/3 │ 🛡️ D: {c['D']}/8\n⚙️ C: {c['C']}/8 │ 🎯 A: {c['A']}/6\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n💡 <i>Premi 'Inizio Asta Live' per il navigatore tattico!</i>"
    )
    if message_id:
        try: bot.edit_message_text(text, chat_id, message_id, parse_mode="HTML", reply_markup=main_menu_keyboard())
        except: bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=main_menu_keyboard())
    else: bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=main_menu_keyboard())

def send_player_card_view(chat_id, player_name, message_id, df, session):
    p_data = df[df['Nome'] == player_name].iloc[0]
    ruolo, fvm = str(p_data.get('R', '-')), p_data.get('FVM', 0)
    try: fvm_val = float(str(fvm).replace(',', '.'))
    except ValueError: fvm_val = 0

    base_price = fvm_val * (session['lega_budget_iniziale'] / 1000.0)
    f_part = 1 + ((session['lega_partecipanti'] - 8) * 0.025)
    fair_price = max(1, int(base_price * f_part))
    
    u_stats = get_roster_stats(session)
    
    # Soglia Sicurezza Reparto (Asta Live)
    alert_reparto = ""
    if session.get('asta_live'):
        budget_reparto_corrente = session['budget_reparti'].get(ruolo, 0)
        slot_mancanti_reparto = {'P': 3, 'D': 8, 'C': 8, 'A': 6}[ruolo] - u_stats['counts'][ruolo]
        if slot_mancanti_reparto > 0:
            soglia_sicurezza = budget_reparto_corrente - (slot_mancanti_reparto - 1)
            alert_reparto = f"\n🛑 <b>SOGLIA SICUREZZA REPARTO ({ruolo}):</b> Max <code>{soglia_sicurezza} cr.</code>"

    info_text = (
        f"📋 <b>{html.escape(player_name.upper())}</b> ({get_team_icon(p_data.get('Squadra', '-'))} {p_data.get('Squadra', '-')})\n"
        f"📌 Ruolo: <code>{ruolo}</code> | FVM Base: {fvm}\n"
        f"💰 <b>Fair Price Stimato:</b> <code>{fair_price} cr.</code>{alert_reparto}\n\n"
        f"💼 <b>Tua Cassa:</b> <code>{session['budget']} cr.</code> (Max Bid: <code>{u_stats['max_bid']}</code>)"
    )
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("⚡ Compra", callback_data=f"buy_{player_name}"), InlineKeyboardButton("🚫 Già Preso", callback_data=f"taken_{player_name}"))
    markup.add(InlineKeyboardButton("🔄 Sliding Doors", callback_data=f"sd_{player_name}"), InlineKeyboardButton("🏠 Home", callback_data="go_home"))
    
    try: bot.edit_message_text(info_text, chat_id, message_id, parse_mode="HTML", reply_markup=markup)
    except: bot.send_message(chat_id, info_text, parse_mode="HTML", reply_markup=markup)

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
    bot.edit_message_text(txt, chat_id, msg_id, parse_mode="HTML", reply_markup=markup)

def view_p_strategia(chat_id, msg_id, nome_p, df, session):
    row = df[df['Nome'] == nome_p].iloc[0]
    sq = row['Squadra'].lower()
    
    txt = f"🛡️ <b>STRATEGIA COMPLETA: {nome_p.upper()}</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
    
    # 1. Blocco Riserve
    riserve = df[(df['Squadra'].str.lower() == sq) & (df['R'] == 'P') & (df['Nome'] != nome_p)]['Nome'].tolist()
    ris_txt = " / ".join(riserve) if riserve else "Nessuna trovata"
    txt += f"🔒 <b>BLOCCO {sq.upper()}:</b> {ris_txt} (Consigliato: 1 cr. cad.)\n"
    
    # Incroci Fittizi (Per brevità esecutiva, logica mock base incroci classici)
    incroci = {'inter': 'milan', 'milan': 'inter', 'roma': 'lazio', 'lazio': 'roma', 'juventus': 'torino', 'torino': 'juventus'}
    partner = incroci.get(sq, 'Sassuolo / Empoli')
    txt += f"🔀 <b>INCROCIO CASA/FUORI:</b> Portieri del <b>{partner.upper()}</b>\n"

    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton(f"⚡ Compra {nome_p}", callback_data=f"buy_{nome_p}"))
    markup.add(InlineKeyboardButton("🔙 Torna a Lista Portieri", callback_data="view_fase_P"))
    bot.edit_message_text(txt, chat_id, msg_id, parse_mode="HTML", reply_markup=markup)

def process_buy_price(message, player_name, user_id):
    chat_id = message.chat.id
    if not message.text.isdigit():
        return bot.register_next_step_handler(bot.send_message(chat_id, "❌ Inserisci <b>solo numeri</b>:", parse_mode="HTML"), process_buy_price, player_name, user_id)

    costo = int(message.text)
    session, df = get_session(user_id), load_data()
    stats = get_roster_stats(session)
    
    if costo > stats['max_bid']:
        bot.send_message(chat_id, f"⚠️ <b>ALLARME!</b> Offerta oltre il Max Bid ({stats['max_bid']} cr).", parse_mode="HTML")
        return send_dashboard(chat_id, user_id)

    row = df[df['Nome'] == player_name].iloc[0]
    ruolo = row.get('R', 'C')
    
    session['rosa'].append({'nome': player_name, 'prezzo': costo, 'ruolo': ruolo, 'squadra': row.get('Squadra', '-')})
    session['budget'] -= costo
    
    # Detrae dal budget di reparto se live
    if session.get('asta_live'): session['budget_reparti'][ruolo] = max(0, session['budget_reparti'][ruolo] - costo)

    bot.send_message(chat_id, f"✅ <b>{html.escape(player_name.upper())}</b> preso a <code>{costo} cr.</code>!", parse_mode="HTML")
    
    if session.get('asta_live') and session.get('fase_attiva'):
        # Ritorna al menu fase live
        markup = InlineKeyboardMarkup().add(InlineKeyboardButton(f"🔙 Torna a Fase {session['fase_attiva']}", callback_data=f"view_fase_{session['fase_attiva']}"))
        bot.send_message(chat_id, "Navigatore Asta Live:", reply_markup=markup)
    else: send_dashboard(chat_id, user_id)

# ==========================================
# HANDLERS (COMANDI & VOCALE & CECCHINO)
# ==========================================
@bot.message_handler(commands=['start', 'menu'])
def cmd_start(m): send_dashboard(m.chat.id, m.from_user.id)

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

# ==========================================
# MAIN CALLBACK HANDLER
# ==========================================
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    safe_answer_callback(call.id)
    user_id, chat_id, data = call.from_user.id, call.message.chat.id, call.data
    session, df = get_session(user_id), load_data()

    if data == "go_home": send_dashboard(chat_id, user_id, call.message.message_id)

    elif data == "inizio_asta_live":
        session['asta_live'] = True
        recalcola_budget_reparti(session) # Inizializza i pesi
        view_fase_portieri(chat_id, call.message.message_id, df, session)

    elif data == "view_fase_P": view_fase_portieri(chat_id, call.message.message_id, df, session)
    
    elif data.startswith("p_strat_"):
        nome_p = data.replace("p_strat_", "")
        view_p_strategia(chat_id, call.message.message_id, nome_p, df, session)

    elif data.startswith("chiudi_reparto_"):
        rep_chiuso = data[-1]
        recalcola_budget_reparti(session) # Riversa avanzi ai prossimi reparti
        
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
            markup = InlineKeyboardMarkup().add(InlineKeyboardButton(f"Vai al Reparto {prossimo_rep}", callback_data="menu_top_start")) # Collega alla ricerca classica per brevità o implementa view_fase_D
            bot.edit_message_text(txt, chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif data.startswith("sq_pl_"):
        send_player_card_view(chat_id, data.replace("sq_pl_", ""), call.message.message_id, df, session)

    elif data.startswith("buy_"):
        nome = data.replace("buy_", "")
        bot.register_next_step_handler(bot.send_message(chat_id, f"💰 Costo per <b>{nome}</b>?:", parse_mode="HTML"), process_buy_price, nome, user_id)

    elif data.startswith("taken_"):
        p_name = data.replace("taken_", "")
        session['scartati'].append(p_name)
        safe_answer_callback(call.id, text=f"🚫 {p_name} segnato preso!", show_alert=True)
        if session.get('asta_live') and session.get('fase_attiva'):
            bot.edit_message_text(f"✔️ {p_name} rimosso dai radar.", chat_id, call.message.message_id)

    elif data == "menu_top_start": # Sfruttiamo il tuo menu Top per navigare nei ruoli
        markup = InlineKeyboardMarkup(row_width=4).add(*[InlineKeyboardButton(f"{ROLE_ICONS[r]} {r}", callback_data=f"menu_top_ru_{r}") for r in ['P', 'D', 'C', 'A']])
        markup.add(InlineKeyboardButton("🔙 Home", callback_data="go_home"))
        bot.edit_message_text("🏆 <b>TOP LIBERI - Scegli il ruolo:</b>", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif data.startswith("menu_top_ru_"):
        r = data.split("_")[-1]
        avail = get_available_players(df, session)
        top = avail[avail['R'] == r].sort_values(by='FVM', ascending=False).head(15)
        markup = InlineKeyboardMarkup(row_width=1)
        for _, row in top.iterrows(): markup.add(InlineKeyboardButton(f"🔍 {row['Nome']} ({row['Squadra']}) FVM:{row['FVM']}", callback_data=f"sq_pl_{row['Nome']}"))
        
        if session.get('asta_live'):
            markup.add(InlineKeyboardButton(f"⏩ Chiudi Reparto {r}", callback_data=f"chiudi_reparto_{r}"))
        markup.add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        
        txt = f"🏆 <b>TOP LIBERI {ROLE_ICONS[r]} {r}</b>\n"
        if session.get('asta_live'): txt += f"💰 <b>Budget {r}:</b> {session['budget_reparti'].get(r,0)} cr."
        bot.edit_message_text(txt, chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

if __name__ == '__main__':
    threading.Thread(target=run_flask, daemon=True).start()
    try: bot.remove_webhook()
    except: pass
    print("🚀 FANTABOT PRO LIVE ONLINE!")
    bot.infinity_polling(timeout=10, long_polling_timeout=5, skip_pending=True)
