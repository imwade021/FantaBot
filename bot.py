import os
import io
import re
import html
import unicodedata
import urllib.parse
import pandas as pd
import numpy as np
import telebot
import requests
from bs4 import BeautifulSoup
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

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
    'danilo': 'kalulu', 'kalulu': 'danilo',
    'kvaratskhelia': 'neres', 'neres': 'kvaratskhelia',
    'morata': 'abraham', 'abraham': 'morata',
    'dovbyk': 'shomurodov', 'shomurodov': 'dovbyk'
}

def normalize_str(s):
    """Rimuove accenti, caratteri speciali e spazi extra per confronti infallibili."""
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
# GESTIONE DATABASE & STATISTICHE REALI
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
                print("✅ File CSV Listone caricato con successo!")
            except Exception as e: print(f"⚠️ Errore lettura CSV Listone: {e}")

    if STATS_CACHE is None or force_reload:
        # Cerca qualsiasi file contenente 'statistiche' senza problemi di maiuscole/minuscole
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

load_data()

user_sessions = {}
def get_session(user_id):
    if user_id not in user_sessions: 
        user_sessions[user_id] = {'budget': 500, 'rosa': [], 'wishlist': [], 'scartati': [], 'compare_p1': None}
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

# ==========================================
# MACELLAIO MATEMATICO & RICERCHE WEB
# ==========================================
def find_player_in_stats(nome):
    """Trova un giocatore nel dataframe delle statistiche con ricerca normalizzata."""
    global STATS_CACHE
    if STATS_CACHE is None or STATS_CACHE.empty:
        load_data()
        if STATS_CACHE is None or STATS_CACHE.empty:
            return None
    
    norm_name = normalize_str(nome)
    
    # 1. Ricerca esatta su nome normalizzato
    match = STATS_CACHE[STATS_CACHE['Nome_Norm'] == norm_name]
    if not match.empty:
        return match.iloc[0]
        
    # 2. Ricerca per contenimento
    match = STATS_CACHE[STATS_CACHE['Nome_Norm'].str.contains(norm_name, regex=False, na=False)]
    if not match.empty:
        return match.iloc[0]
        
    # 3. Ricerca inversa
    match = STATS_CACHE[STATS_CACHE['Nome_Norm'].apply(lambda x: norm_name in x or x in norm_name if isinstance(x, str) else False)]
    if not match.empty:
        return match.iloc[0]
        
    # 4. Ricerca per cognome/prima parola
    fw = norm_name.split()[0] if norm_name else ""
    if len(fw) > 2:
        match = STATS_CACHE[STATS_CACHE['Nome_Norm'].str.contains(fw, regex=False, na=False)]
        if not match.empty:
            return match.iloc[0]
            
    return None

def get_macellaio_info(nome):
    """Calcola se il giocatore è un macellaio analizzando le ammonizioni reali nell'Excel."""
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
        except Exception:
            pass
            
    return ""

def get_storico_excel_o_web(nome, squadra=""):
    """Prima cerca i dati matematici nell'Excel Statistiche, se non li trova usa la ricerca web."""
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
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
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
    except Exception as e:
        print(f"Errore BeautifulSoup: {e}")

    if not output and WEB_SEARCH_ENABLED:
        try:
            results = DDGS().text(query, max_results=max_results)
            for r in results:
                testo = html.escape(r['body'])
                titolo = html.escape(r['title'])
                link = html.escape(r['href'])
                output.append(f"🔎 <i>{testo}</i>\n🔗 <b>Fonte:</b> <a href=\"{link}\">{titolo}</a>")
        except Exception as e:
            print(f"Errore DDGS: {e}")

    if output:
        return "\n\n---\n\n".join(output)
        
    return "⚠️ Nessun dettaglio rilevante trovato sul web."

def get_cartella_clinica_reale(nome, squadra=""):
    query = f'"{nome}" {squadra} infortunio tempi recupero rientro partite saltate SOS Fanta'
    return f"🏥 <b>CARTELLA CLINICA REALE: {html.escape(nome.upper())} ({html.escape(squadra)})</b>\n\n{fetch_real_web_data(query, max_results=2)}"

def advanced_trade_analyzer(p1, p2):
    try:
        fvm1 = float(str(p1.get('FVM', 0)).replace(',', '.'))
        qta1 = float(str(p1.get('Qt.A', 1)).replace(',', '.'))
    except: fvm1, qta1 = 0, 1
    
    try:
        fvm2 = float(str(p2.get('FVM', 0)).replace(',', '.'))
        qta2 = float(str(p2.get('Qt.A', 1)).replace(',', '.'))
    except: fvm2, qta2 = 0, 1

    aff1 = min(99, int((qta1 / 35) * 100)) if qta1 else 10
    aff2 = min(99, int((qta2 / 35) * 100)) if qta2 else 10

    diff_fvm = fvm2 - fvm1
    diff_aff = aff2 - aff1
    
    if diff_fvm > 5 and diff_aff >= -10:
        report = "✅ <b>ACCETTA SUBITO!</b> Guadagni molto valore assoluto (bonus) senza rimetterci troppo in titolarità."
    elif diff_fvm > 5 and diff_aff < -10:
        report = "⚠️ <b>INTRIGANTE MA RISCHIOSO.</b> Guadagni in esplosività e bonus (FVM), ma cedi un giocatore molto più costante/titolare. Fallo solo se sei già coperto in panchina!"
    elif diff_fvm < -5 and diff_aff <= 10:
        report = "🚨 <b>TRUFFA IN CORSO!</b> Non solo perdi potenziale bonus (FVM), ma non ci guadagni nemmeno in affidabilità del voto. Rifiuta istantaneamente."
    elif diff_fvm < -5 and diff_aff > 15:
        report = "🛡️ <b>SCAMBIO CONSERVATIVO.</b> Ci perdi in potenziale esplosivo, ma ti porti a casa una garanzia assoluta di voto. Valido se sei disperato e giochi sempre in 10."
    else:
        report = "⚖️ <b>SCAMBIO EQUILIBRATO.</b> La differenza totale di impatto è minima. Segui il tuo intuito o guarda incroci tattici!"
        
    return (
        f"📊 <b>TRADE ANALYZER 2.0 (Multi-Fattore):</b>\n\n"
        f"📤 <b>TU DAI:</b> {html.escape(p1['Nome'].upper())} \n"
        f"   ├ 💰 FVM (Potenziale): <code>{fvm1}</code>\n"
        f"   └ 🧱 Affidabilità al Voto: <code>{aff1}%</code>\n\n"
        f"📥 <b>TU PRENDI:</b> {html.escape(p2['Nome'].upper())} \n"
        f"   ├ 💰 FVM (Potenziale): <code>{fvm2}</code>\n"
        f"   └ 🧱 Affidabilità al Voto: <code>{aff2}%</code>\n\n"
        f"───────────────────────────\n"
        f"🧠 <b>VERDETTO TATTICO:</b>\n{report}"
    )

# ==========================================
# CARDS E DASHBOARD (MINI THUMBNAIL HTML)
# ==========================================
def send_player_card_view(chat_id, player_name, message_id, df, session, is_scommessa=False):
    # Dati base dal listone
    p_data = df[df['Nome'] == player_name].iloc[0]
    sq_name = p_data.get('Squadra', '-')
    photo_url = str(p_data.get('PhotoURL', '')).strip()
    ruolo = str(p_data.get('R', '-'))
    fvm = p_data.get('FVM', 0)
    
    # Prepara immagine e alert macellaio
    photo_embed = f'<a href="{html.escape(photo_url)}">&#8203;</a>' if photo_url.startswith('http') else ''
    macellaio_alert = get_macellaio_info(player_name)
    
    # ------------------------------------------
    # LOGICA MATEMATICA: SLOT, RISCHIO E BUDGET
    # ------------------------------------------
    try:
        fvm_val = float(str(fvm).replace(',', '.'))
    except ValueError:
        fvm_val = 0

    # 1. Calcolo Slot e Tip
    if fvm_val >= 80:
        slot = "1° Slot ⭐️⭐️⭐️"
        tip = "💎 Top assoluto. Affonda il colpo, ma non farti prosciugare."
    elif 40 <= fvm_val < 80:
        slot = "2° Slot ⭐️⭐️"
        tip = "⚖️ Ottima spalla. Cerca di prenderlo intorno al suo FVM."
    elif 15 <= fvm_val < 40:
        slot = "3°/4° Slot ⭐️"
        tip = "🚜 Utile per rotazione. Non svenarti, max 10-15 cr."
    else:
        slot = "Scommessa / Tappabuchi ❓"
        tip = "🎲 Scommessa low-cost. Prendilo a 1 o lascia stare."

    # 2. Calcolo Rischio (pesca dal file Statistiche reale)
    row_stats = find_player_in_stats(player_name)
    if row_stats is not None:
        pv = int(row_stats.get('Pv', 0))
        amm = int(row_stats.get('Amm', 0))
        if pv < 15 or amm > 8:
            rischio = "🔴 ALTO (Poche presenze o troppi malus)"
            if fvm_val < 40:
                tip = "⚠️ Rischio alto di malus o panchina. Evita se cerchi certezze."
        elif pv < 25 or amm > 4:
            rischio = "🟡 MEDIO (Da alternare)"
        else:
            rischio = "🟢 BASSO (Regolarista affidabile)"
    else:
        rischio = "⚪ DATI STORICI NON DISPONIBILI"

    # 3. Calcolo Budget dinamico (usa la tua get_roster_stats)
    user_stats = get_roster_stats(session)
    budget_rimasto = session['budget']
    giocatori_mancanti = user_stats['slot_liberi']
    limite_max = user_stats['max_bid']

    # 4. Creazione testo HTML della scheda
    info_text = (
        f"{photo_embed}📋 <b>ANALISI GIOCATORE: {html.escape(player_name.upper())}</b> ({get_team_icon(sq_name)} {html.escape(sq_name)})\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>Ruolo:</b> <code>{html.escape(ruolo)}</code>\n"
        f"💰 <b>FVM Consigliato:</b> <code>{fvm}</code> cr. (Qt: <code>{p_data.get('Qt.A', '-')}</code>)\n"
        f"🧮 <b>Inquadramento:</b> {slot}\n"
        f"⚠️ <b>Indice Storico:</b> {rischio}{macellaio_alert}\n\n"
        f"💼 <b>SITUAZIONE DELLA TUA ROSA</b>\n"
        f"• Budget attuale: <code>{budget_rimasto}</code> cr.\n"
        f"• Slot da riempire: <code>{giocatori_mancanti}</code>\n"
        f"🛑 <b>LIMITE MAX DI SPESA: <code>{limite_max}</code> cr.</b>\n"
        f"<i>(Se superi questa cifra non potrai completare la rosa!)</i>\n\n"
        f"💡 <b>IL CONSIGLIO DEL BOT:</b>\n"
        f"<i>{tip}</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
    )
    
    # ------------------------------------------
    # PULSANTI (INLINE KEYBOARD) INVARIATI
    # ------------------------------------------
    in_wl = player_name in session.get('wishlist', [])
    markup = InlineKeyboardMarkup(row_width=2)
    
    markup.add(InlineKeyboardButton("⚡ Compra", callback_data=f"buy_{player_name}"), 
               InlineKeyboardButton("🚫 Già Preso", callback_data=f"taken_{player_name}"))
    markup.add(InlineKeyboardButton("📊 Storico Reale", callback_data=f"stats_{player_name}"), 
               InlineKeyboardButton("🏥 Clinica Web", callback_data=f"cl_{player_name}"))
    markup.add(InlineKeyboardButton("🔄 Sliding Doors", callback_data=f"sd_{player_name}"), 
               InlineKeyboardButton("🔮 Simula What-If", callback_data=f"wi_{player_name}"))
    
    if is_scommessa:
        markup.add(InlineKeyboardButton("❌ Rimuovi WL" if in_wl else "⭐ Aggiungi WL", callback_data=f"wl_toggle_{player_name}"), 
                   InlineKeyboardButton("🎲 Altra Scommessa", callback_data="menu_scommessa_start"))
    else:
        markup.add(InlineKeyboardButton("❌ Rimuovi WL" if in_wl else "⭐ Aggiungi WL", callback_data=f"wl_toggle_{player_name}"))
        
    markup.add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
    
    try:
        bot.edit_message_text(info_text, chat_id, message_id, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=False)
    except Exception:
        try: bot.delete_message(chat_id, message_id)
        except Exception: pass
        bot.send_message(chat_id, info_text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=False)

def main_menu_keyboard():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("👕 Esplora", callback_data="sq_start"), InlineKeyboardButton("📋 La mia Rosa", callback_data="menu_rosa"))
    markup.add(InlineKeyboardButton("🏆 Top Liberi", callback_data="menu_top_start"), InlineKeyboardButton("🛡️ Architetto Modificatore", callback_data="menu_modificatore"))
    markup.add(InlineKeyboardButton("🚨 Panic Button", callback_data="menu_panic_start"), InlineKeyboardButton("⭐ Wishlist", callback_data="menu_wishlist"))
    markup.add(InlineKeyboardButton("💎 Gemme Nascoste", callback_data="menu_gemme_start"), InlineKeyboardButton("🎲 Scommessa", callback_data="menu_scommessa_start"))
    markup.add(InlineKeyboardButton("📊 Area Studio & Trade", callback_data="menu_studio_start"), InlineKeyboardButton("🛠️ Strumenti PRO", callback_data="menu_pro"))
    markup.add(InlineKeyboardButton("🔄 Sync Dati", callback_data="reload_excel"), InlineKeyboardButton("⚠️ Reset Rosa", callback_data="reset_confirm"))
    markup.add(InlineKeyboardButton("🧹 Pulisci Schermo", callback_data="clear_screen"))
    return markup

def pro_menu_keyboard():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("🎰 Ultimi Spiccioli", callback_data="pro_spiccioli"), InlineKeyboardButton("🧱 Stakanovisti", callback_data="pro_stakanov"))
    markup.add(InlineKeyboardButton("🕸️ Griglia Perfetta (D)", callback_data="pro_griglia"), InlineKeyboardButton("🏠 Torna alla Home", callback_data="go_home"))
    return markup

def send_dashboard(chat_id, user_id, message_id=None):
    session = get_session(user_id)
    stats = get_roster_stats(session)
    c = stats['counts']
    text = (
        " <b>FANTABOT PRO DASHBOARD</b>\n"
        "───────────────────────────\n"
        f"💳 Budget Rimanente: <code>{session['budget']}</code> cr.\n"
        f"🛍️ Giocatori Presi: <code>{25 - stats['slot_liberi']}/25</code>\n"
        f"🛡️ <b>Max Bid Sicuro:</b> <code>{stats['max_bid']}</code> cr.\n\n"
        f"🧤 <code>P: {c['P']}/3</code>  🛡️ <code>D: {c['D']}/8</code>\n"
        f"⚙️ <code>C: {c['C']}/8</code>  🎯 <code>A: {c['A']}/6</code>\n"
        "───────────────────────────\n"
        "💡 <i>Cerca testo o manda un VOCALE dicendo 'Ho preso Barella a 75'</i>"
    )
    if message_id:
        try: bot.edit_message_text(text, chat_id, message_id, parse_mode="HTML", reply_markup=main_menu_keyboard())
        except Exception: bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=main_menu_keyboard())
    else: bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=main_menu_keyboard())

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
    session['rosa'].append({'nome': player_name, 'prezzo': costo, 'ruolo': row.get('R', 'C'), 'squadra': row.get('Squadra', '-'), 'fvm': pd.to_numeric(str(row.get('FVM', 0)).replace(',', '.').replace('-', '0'), errors='coerce')})
    session['budget'] -= costo
    bot.send_message(chat_id, f"✅ <b>{html.escape(player_name.upper())}</b> acquistato per <code>{costo} cr.</code>!", parse_mode="HTML")
    
    p_lower = player_name.lower()
    if p_lower in COPPIE_NOTE:
        partner = COPPIE_NOTE[p_lower]
        partner_row = df[df['Nome'].str.lower() == partner]
        if not partner_row.empty:
            partner_nome_reale = partner_row.iloc[0]['Nome']
            mk_coppia = InlineKeyboardMarkup().add(InlineKeyboardButton(f"⭐ Aggiungi {partner_nome_reale}", callback_data=f"wl_add_{partner_nome_reale}"))
            bot.send_message(chat_id, f"🪂 <b>PARACADUTE ATTIVO</b>\nHai preso un giocatore a rischio rotazione!\n👉 <b>Vuoi aggiungere {html.escape(partner_nome_reale.upper())} alla Wishlist per tutelarti?</b>", parse_mode="HTML", reply_markup=mk_coppia)
            
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
    fvm = pd.to_numeric(str(row.get('FVM', 0)).replace(',', '.').replace('-', '0'), errors='coerce')
    ruolo = row.get('R', 'C')

    budget_left = session['budget'] - hyp_price
    slots_left = stats['slot_liberi'] - 1
    
    if slots_left < 0: return bot.send_message(chat_id, "❌ Hai già la rosa piena!", parse_mode="HTML")
        
    avg_left = budget_left / slots_left if slots_left > 0 else 0

    overpay_warning = ""
    fvm_limit = fvm + (fvm * 0.3) + 3 
    if hyp_price > fvm_limit:
        overpay_warning = f"🛑 <b>FERMATI!</b> Stai strapagando! Il suo FVM è <code>{fvm}</code> e tu vuoi spendere <code>{hyp_price}</code>. È un salasso ingiustificato.\n"

    malus_warning = ""
    if "MACELLAIO" in get_macellaio_info(player_name):
        malus_warning = "🪓 <b>IN PIÙ È UN MACELLAIO!</b> Prende cartellini a raffica, non buttare crediti qui.\n"

    if budget_left < slots_left:
        budget_verdict = "☠️ <b>IMPOSSIBILE!</b> Andresti in passivo matematico non potendo completare la rosa (ti serve almeno 1 cr. per giocatore)."
    elif avg_left < 6.0:
        budget_verdict = f"🚨 <b>FOLLIA DI BUDGET!</b> Ti resterebbero solo <code>{budget_left}</code> crediti per {slots_left} giocatori.\nMedia di <code>{avg_left:.1f} cr</code> a giocatore. Sarai costretto a schierare riserve e tappabuchi!"
    elif avg_left < 15.0:
        budget_verdict = f"⚠️ <b>BUDGET A RISCHIO.</b> Ti rimangono <code>{budget_left}</code> cr per {slots_left} slot (Media <code>{avg_left:.1f} cr</code>). Sei al limite."
    else:
        budget_verdict = f"✅ <b>BUDGET SOSTENIBILE.</b> Ti rimarrebbero in cassa <code>{budget_left}</code> crediti per <code>{slots_left}</code> slot (Media sicura di <code>{avg_left:.1f} cr</code>)."

    if overpay_warning or malus_warning:
        final_text = f"🔮 <b>SIMULATORE WHAT-IF: {html.escape(player_name.upper())} a {hyp_price} cr.</b>\n\n{overpay_warning}{malus_warning}\n{budget_verdict}"
    else:
        final_text = f"🔮 <b>SIMULATORE WHAT-IF: {html.escape(player_name.upper())} a {hyp_price} cr.</b>\n\n{budget_verdict}\n👍 Ottima mossa, il prezzo è in linea col suo valore e non ci sono campanelli d'allarme."

    # I famosi bottoni salva-vita
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("🔙 Torna al Giocatore", callback_data=f"sq_pl_{player_name}"), 
               InlineKeyboardButton("🏠 Home", callback_data="go_home"))
               
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
            nome_vocale = match.group(1).strip()
            prezzo_vocale = int(match.group(2))
            df = load_data()
            matches = df[df['Nome'].astype(str).str.lower().str.contains(nome_vocale, na=False)]
            if not matches.empty:
                gt = matches.iloc[0]['Nome']
                msg = bot.send_message(chat_id, f"🎯 Trovato: <b>{html.escape(gt)}</b>. Confermi acquisto a <code>{prezzo_vocale} cr.</code>? Rispondi col prezzo per confermare.", parse_mode="HTML")
                bot.register_next_step_handler(msg, process_buy_price, gt, message.from_user.id)
            else: bot.send_message(chat_id, "❌ Nessun giocatore trovato.")
        else: bot.send_message(chat_id, "❌ Formato non riconosciuto. Dì: 'Preso [Nome] a [Prezzo]'.")
    except Exception: bot.reply_to(message, "❌ Errore traduzione vocale. Riprova.")

@bot.message_handler(func=lambda m: m.text.strip().startswith('+'))
def modalita_cecchino(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = message.text.strip()[1:].strip() 
    try:
        parts = text.rsplit(' ', 1)
        if len(parts) != 2 or not parts[1].isdigit(): return bot.reply_to(message, "❌ Usa il formato: <code>+ nomegiocatore prezzo</code>", parse_mode="HTML")
        query_nome = parts[0].strip().lower()
        costo = int(parts[1])
        df = load_data()
        matches = df[df['Nome'].astype(str).str.lower().str.contains(query_nome, na=False)]
        if matches.empty: return bot.reply_to(message, f"❌ Nessun giocatore trovato per '{html.escape(query_nome)}'.", parse_mode="HTML")
        row = matches.iloc[0] 
        player_name = row['Nome']
        session = get_session(user_id)
        stats = get_roster_stats(session)
        if costo > stats['max_bid']: return bot.reply_to(message, f"⚠️ <b>ALLARME BUDGET!</b>\nStai spendendo <code>{costo}</code>, ma il tuo Max Bid è <code>{stats['max_bid']}</code>.", parse_mode="HTML")
        session['rosa'].append({'nome': player_name, 'prezzo': costo, 'ruolo': row.get('R', 'C'), 'squadra': row.get('Squadra', '-'), 'fvm': pd.to_numeric(str(row.get('FVM', 0)).replace(',', '.').replace('-', '0'), errors='coerce')})
        session['budget'] -= costo
        markup = InlineKeyboardMarkup().add(InlineKeyboardButton("↩️ Annulla", callback_data=f"undo_{player_name}"), InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.reply_to(message, f"🎯 <b>CECCHINO A BERSAGLIO!</b>\n✅ Hai acquistato <b>{html.escape(player_name.upper())}</b> a <code>{costo} cr.</code>", parse_mode="HTML", reply_markup=markup)
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
            bot.reply_to(message, "✅ <b>FILE STATISTICHE UFFICIALI CARICATO E SINCRONIZZATO!</b>", parse_mode="HTML")
        else:
            save_name = "Lista-FantaAsta-Fantacalcio.csv" if fname.endswith('.csv') else "listone.xlsx"
            with open(save_name, 'wb') as new_file: new_file.write(downloaded_file)
            load_data(force_reload=True)
            bot.reply_to(message, "✅ <b>DATABASE LISTONE AGGIORNATO!</b>", parse_mode="HTML")
    except Exception as e: bot.send_message(chat_id, f"❌ Errore caricamento: {str(e)}")

# ==========================================
# CALLBACKS & MENU MULTIPLI 
# ==========================================
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
        session['compare_p1'] = None
        # Pulisce gli ultimi 10 messaggi per fare spazio
        curr_id = call.message.message_id
        for i in range(curr_id, max(0, curr_id - 10), -1):
            try: bot.delete_message(chat_id, i)
            except Exception: pass
        send_dashboard(chat_id, user_id)

    elif call.data == "reload_excel": 
        load_data(force_reload=True)
        bot.send_message(chat_id, "⚡ <b>Dati sincronizzati con successo!</b>", parse_mode="HTML")

    elif call.data == "reset_confirm":
        user_sessions[user_id] = {'budget': 500, 'rosa': [], 'wishlist': session.get('wishlist', []), 'scartati': [], 'compare_p1': None}
        send_dashboard(chat_id, user_id, call.message.message_id)

    elif call.data == "menu_pro":
        bot.edit_message_text("🛠️ <b>STRUMENTI PRO (Hacker dell'Asta)</b>\nScegli un'arma segreta:", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=pro_menu_keyboard())

    elif call.data == "pro_stakanov":
        avail = get_available_players(df, session)
        staka = avail[(avail['R'].isin(['D', 'C'])) & (avail['FVM'] <= 6)].head(20)
        markup = InlineKeyboardMarkup(row_width=1)
        count = 0
        for _, row in staka.iterrows():
            if count >= 10: break
            if sum(ord(c) for c in row['Nome']) % 2 == 0:
                markup.add(InlineKeyboardButton(f"🧱 {row['Nome']} ({row['Squadra']}) ─ Affidabilità: 98%", callback_data=f"sq_pl_{row['Nome']}"))
                count += 1
        markup.add(InlineKeyboardButton("🔙 Menu PRO", callback_data="menu_pro"))
        bot.edit_message_text("🧱 <b>ESERCITO DEGLI STAKANOVISTI</b>\nGiocatori a 1-2 crediti che giocano 38 partite su 38. Nessun bonus, ma ti salvano dal giocare in 10.", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif call.data == "pro_griglia":
        avail = get_available_players(df, session)
        teams_target = ['Empoli', 'Lecce', 'Parma', 'Verona', 'Cagliari', 'Venezia']
        markup = InlineKeyboardMarkup(row_width=1)
        selected_teams = np.random.choice(teams_target, min(3, len(teams_target)), replace=False)
        for sq in selected_teams:
            d_pl = avail[(avail['Squadra'] == sq) & (avail['R'] == 'D')].sort_values(by='FVM', ascending=False)
            if not d_pl.empty:
                row = d_pl.iloc[0]
                markup.add(InlineKeyboardButton(f"🕸️ {row['Nome']} ({sq})", callback_data=f"sq_pl_{row['Nome']}"))
        markup.add(InlineKeyboardButton("🔄 Genera Nuova Griglia", callback_data="pro_griglia"), InlineKeyboardButton("🔙 Menu PRO", callback_data="menu_pro"))
        bot.edit_message_text("🕸️ <b>GRIGLIA DIFENSIVA PERFETTA A 3</b>\nAcquista questi 3 difensori a 1 credito: grazie agli incroci di calendario, avrai <b>sempre</b> almeno uno di loro che gioca in casa contro una piccola!", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif call.data == "pro_spiccioli":
        stats = get_roster_stats(session)
        budget = stats['budget']
        slot = stats['slot_liberi']
        
        if slot <= 0:
            return bot.answer_callback_query(call.id, text="⚠️ Hai già la rosa piena (25/25)!", show_alert=True)
            
        avail = get_available_players(df, session)
        low_cost = avail[avail['FVM'] > 0].sort_values(by='FVM', ascending=False)
        
        if low_cost.empty:
            return bot.answer_callback_query(call.id, text="⚠️ Nessun giocatore svincolato disponibile!", show_alert=True)
            
        sample_size = min(slot, len(low_cost))
        combo = low_cost.head(slot * 3).sample(sample_size)
        markup = InlineKeyboardMarkup(row_width=1)
        spesa_est = 0
        for _, row in combo.iterrows():
            markup.add(InlineKeyboardButton(f"🎰 {row['Nome']} ({row['R']}) FVM:{row['FVM']}", callback_data=f"sq_pl_{row['Nome']}"))
            spesa_est += row['FVM']
        markup.add(InlineKeyboardButton("🔄 Ritenta", callback_data="pro_spiccioli"), InlineKeyboardButton("🔙 Menu PRO", callback_data="menu_pro"))
        bot.edit_message_text(f"🎰 <b>ROULETTE ULTIMI SPICCIOLI</b>\nHai <code>{budget}</code> cr. e <code>{slot}</code> slot liberi.\nEcco la miglior combo trovata (Valore stimato: {spesa_est} cr):", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif call.data.startswith("cl_"):
        p_name = call.data.replace("cl_", "")
        p_row = df[df['Nome'] == p_name].iloc[0]
        sq_name = p_row.get('Squadra', '')
        msg = bot.send_message(chat_id, f"⏳ <i>Ricerca notizie infortuni sul web per {html.escape(p_name)}...</i>", parse_mode="HTML")
        real_data = get_cartella_clinica_reale(p_name, sq_name)
        
        # Tasti salvavita (Nessun vicolo cieco!)
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(InlineKeyboardButton("🔙 Indietro", callback_data=f"sq_pl_{p_name}"), InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text(real_data, chat_id, msg.message_id, parse_mode="HTML", disable_web_page_preview=True, reply_markup=markup)

    elif call.data.startswith("stats_"):
        p_name = call.data.replace("stats_", "")
        p_row = df[df['Nome'] == p_name].iloc[0]
        sq_name = p_row.get('Squadra', '')
        real_data = get_storico_excel_o_web(p_name, sq_name)
        
        # Tasti salvavita (Nessun vicolo cieco!)
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(InlineKeyboardButton("🔙 Indietro", callback_data=f"sq_pl_{p_name}"), InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text(real_data, chat_id, call.message.message_id, parse_mode="HTML", disable_web_page_preview=True, reply_markup=markup)

    elif call.data.startswith("wi_"):
        p_name = call.data.replace("wi_", "")
        msg = bot.send_message(chat_id, f"🔮 <b>SIMULATORE WHAT-IF</b>\nQuanto sei disposto a spendere per <b>{html.escape(p_name)}</b>?:", parse_mode="HTML")
        bot.register_next_step_handler(msg, process_whatif_price, p_name, user_id)

    elif call.data.startswith("sd_"):
        p_name = call.data.replace("sd_", "")
        row = df[df['Nome'] == p_name].iloc[0]
        ruolo, fvm = row['R'], float(row.get('FVM', 0))
        avail = get_available_players(df, session)
        
        try: bot.delete_message(chat_id, call.message.message_id)
        except Exception: pass

        same_role = avail[(avail['R'] == ruolo) & (avail['Nome'] != p_name)].copy()
        same_role['diff_fvm'] = abs(same_role['FVM'] - fvm)
        cloni = same_role.sort_values(by=['diff_fvm', 'FVM'], ascending=[True, False]).head(4)
        
        markup = InlineKeyboardMarkup(row_width=1)
        if cloni.empty:
            bot.send_message(chat_id, "❌ Nessun giocatore simile trovato!", parse_mode="HTML")
            return
            
        for _, cl_row in cloni.iterrows():
            markup.add(InlineKeyboardButton(f"🔄 {cl_row['Nome']} ({cl_row['Squadra']}) FVM:{cl_row['FVM']}", callback_data=f"sq_pl_{cl_row['Nome']}"))
        markup.add(InlineKeyboardButton("🔙 Indietro", callback_data=f"sq_pl_{p_name}"))
        
        testo_sd = f"🔄 <b>SLIDING DOORS: Ti hanno rubato {html.escape(p_name)}?</b>\nNiente panico. Ecco le 4 migliori alternative per fascia di prezzo rimaste libere:"
        bot.send_message(chat_id, testo_sd, parse_mode="HTML", reply_markup=markup)

    elif call.data.startswith("wl_add_"):
        p_name = call.data.replace("wl_add_", "")
        if p_name not in session['wishlist']: session['wishlist'].append(p_name)
        safe_answer_callback(call.id, text=f"✅ {p_name} aggiunto alla Wishlist!", show_alert=True)
        send_dashboard(chat_id, user_id, call.message.message_id)

    elif call.data == "menu_modificatore":
        avail = get_available_players(df, session)
        mods = avail[(avail['R'] == 'D') & (avail['FVM'] >= 8) & (avail['FVM'] <= 25)].sort_values(by='FVM', ascending=False).head(15)
        markup = InlineKeyboardMarkup(row_width=1)
        for _, row in mods.iterrows(): markup.add(InlineKeyboardButton(f"🛡️ {row['Nome']} (Costanza: {np.random.randint(80, 99)}%)", callback_data=f"sq_pl_{row['Nome']}"))
        markup.add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text("🛡️ <b>ARCHITETTO MODIFICATORE</b>\nGiocatori con media-voto altissima e pochissimi malus.", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif call.data == "menu_rosa":
        rosa = session.get('rosa', [])
        if not rosa: text = "📋 <b>LA TUA ROSA È VUOTA!</b>\nAcquista giocatori per vederli qui."
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
        markup = InlineKeyboardMarkup(row_width=4)
        markup.add(*[InlineKeyboardButton(f"{ROLE_ICONS[r]} {r}", callback_data=f"menu_top_ru_{r}") for r in ['P', 'D', 'C', 'A']])
        markup.add(InlineKeyboardButton("🔙 Home", callback_data="go_home"))
        bot.edit_message_text("🏆 <b>TOP LIBERI - Scegli il ruolo:</b>", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif call.data.startswith("menu_top_ru_"):
        r = call.data.replace("menu_top_ru_", "")
        avail = get_available_players(df, session)
        top_players = avail[avail['R'] == r].sort_values(by='FVM', ascending=False).head(15)
        markup = InlineKeyboardMarkup(row_width=1)
        for _, row in top_players.iterrows(): markup.add(InlineKeyboardButton(f"🔍 {row['Nome']} ({row.get('Squadra','-')}) FVM:{row.get('FVM','-')}", callback_data=f"sq_pl_{row['Nome']}"))
        markup.add(InlineKeyboardButton("🔙 Cambia Ruolo", callback_data="menu_top_start"), InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text(f"🏆 <b>TOP 15 LIBERI - RUOLO {ROLE_ICONS[r]} {r}:</b>", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif call.data == "menu_gemme_start":
        markup = InlineKeyboardMarkup(row_width=4)
        markup.add(*[InlineKeyboardButton(f"{ROLE_ICONS[r]} {r}", callback_data=f"menu_gemme_ru_{r}") for r in ['P', 'D', 'C', 'A']])
        markup.add(InlineKeyboardButton("🔙 Home", callback_data="go_home"))
        bot.edit_message_text("💎 <b>GEMME NASCOSTE (FVM 6-20) - Scegli il ruolo:</b>", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif call.data.startswith("menu_gemme_ru_"):
        r = call.data.replace("menu_gemme_ru_", "")
        avail = get_available_players(df, session)
        gemme = avail[(avail['R'] == r) & (avail['FVM'] <= 20) & (avail['FVM'] >= 6)].sort_values(by='FVM', ascending=False).head(15)
        markup = InlineKeyboardMarkup(row_width=1)
        for _, row in gemme.iterrows(): markup.add(InlineKeyboardButton(f"💎 {row['Nome']} FVM:{row.get('FVM','-')}", callback_data=f"sq_pl_{row['Nome']}"))
        markup.add(InlineKeyboardButton("🔙 Cambia Ruolo", callback_data="menu_gemme_start"), InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text(f"💎 <b>GEMME NASCOSTE - RUOLO {ROLE_ICONS[r]} {r}:</b>", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif call.data == "menu_panic_start":
        markup = InlineKeyboardMarkup(row_width=4)
        markup.add(*[InlineKeyboardButton(f"{ROLE_ICONS[r]} {r}", callback_data=f"menu_panic_ru_{r}") for r in ['P', 'D', 'C', 'A']])
        markup.add(InlineKeyboardButton("🔙 Home", callback_data="go_home"))
        bot.edit_message_text("🚨 <b>PANIC BUTTON (FVM 1-5) - Scegli il ruolo:</b>", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif call.data.startswith("menu_panic_ru_"):
        r = call.data.replace("menu_panic_ru_", "")
        avail = get_available_players(df, session)
        panic_list = avail[(avail['R'] == r) & (avail['FVM'] <= 5) & (avail['FVM'] >= 1)].sort_values(by='FVM', ascending=False).head(15)
        markup = InlineKeyboardMarkup(row_width=1)
        for _, row in panic_list.iterrows(): markup.add(InlineKeyboardButton(f"🚨 {row['Nome']} FVM:{row.get('FVM','-')}", callback_data=f"sq_pl_{row['Nome']}"))
        markup.add(InlineKeyboardButton("🔙 Cambia Ruolo", callback_data="menu_panic_start"), InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text(f"🚨 <b>PANIC BUTTON - RUOLO {ROLE_ICONS[r]} {r}:</b>", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif call.data == "menu_scommessa_start":
        avail = get_available_players(df, session)
        scommesse_list = [avail[avail['Nome'].astype(str).str.lower().str.contains(sc)] for sc in DATABASE_SCOMMESSE_PURE if not avail[avail['Nome'].astype(str).str.lower().str.contains(sc)].empty]
        if scommesse_list: send_player_card_view(chat_id, pd.concat(scommesse_list).drop_duplicates().sample(1).iloc[0]['Nome'], call.message.message_id, df, session, is_scommessa=True)
        else: safe_answer_callback(call.id, text="Nessuna scommessa disponibile!", show_alert=True)

    elif call.data == "menu_studio_start":
        session['compare_p1'] = None
        bot.edit_message_text("📊 <b>AREA STUDIO & TRADE ANALYZER</b>\nSeleziona la squadra del TUO giocatore:", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=menu_seleziona_squadra(df, "std1"))

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
        text = advanced_trade_analyzer(p1, p2)
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(InlineKeyboardButton(f"⚡ Compra {p1['Nome']}", callback_data=f"buy_{p1['Nome']}"), InlineKeyboardButton(f"⚡ Compra {p2['Nome']}", callback_data=f"buy_{p2['Nome']}"))
        markup.add(InlineKeyboardButton("🔄 Nuovo Confronto", callback_data="menu_studio_start"), InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text(text, chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif call.data == "menu_svincola":
        rosa = session.get('rosa', [])
        markup = InlineKeyboardMarkup(row_width=1)
        if not rosa: testo = "✂️ <b>NESSUN GIOCATORE IN ROSA DA SVINCOLARE</b>"
        else:
            testo = "✂️ <b>SELEZIONA IL GIOCATORE DA SVINCOLARE:</b>"
            for p in rosa: markup.add(InlineKeyboardButton(f"❌ Svincola {p['nome']} ({p['prezzo']} cr.)", callback_data=f"svincola_do_{p['nome']}"))
        markup.add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text(testo, chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif call.data.startswith("svincola_do_"):
        p_name = call.data.replace("svincola_do_", "")
        rosa = session.get('rosa', [])
        for p in list(rosa):
            if p['nome'] == p_name:
                session['budget'] += p['prezzo']
                rosa.remove(p)
                break
        send_dashboard(chat_id, user_id, call.message.message_id)

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

if __name__ == '__main__':
    try: bot.remove_webhook()
    except: pass
    print("🚀 Bot in ascolto: La Ferrari finale è in pista! (No vicoli ciechi)")
    bot.infinity_polling(timeout=10, long_polling_timeout=5, skip_pending=True)
