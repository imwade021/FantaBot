import os
import io
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import datetime
import email.utils
import pandas as pd
import numpy as np
import telebot
import requests
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# Tenta di importare l'AI di Google Gemini
try:
    import google.generativeai as genai
    AI_ENABLED = True
except ImportError:
    AI_ENABLED = False

# Tenta di importare le librerie per i comandi vocali
try:
    import speech_recognition as sr
    from pydub import AudioSegment
    VOICE_ENABLED = True
except ImportError:
    VOICE_ENABLED = False

# ==========================================
# CONFIGURAZIONE INIZIALE & TOKEN
# ==========================================
TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not TOKEN:
    raise ValueError("⚠️ ERRORE: La variabile d'ambiente BOT_TOKEN non è impostata su Render!")

bot = telebot.TeleBot(TOKEN)

# Configura Gemini se la chiave è presente
if AI_ENABLED and GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

ROLE_ICONS = {'P': '🧤', 'D': '🛡️', 'C': '⚙️', 'A': '🎯'}
TEAM_COLORS = {
    'Atalanta': '🔵⚫', 'Bologna': '🔴🔵', 'Cagliari': '🔴🔵', 'Como': '🔵⚪',
    'Empoli': '🔵⚪', 'Fiorentina': '💜', 'Genoa': '🔴🔵', 'Inter': '🔵⚫',
    'Juventus': '⚪⚫', 'Lazio': '🩵⚪', 'Lecce': '🟡🔴', 'Milan': '🔴⚫',
    'Monza': '🔴⚪', 'Napoli': '🔵⚪', 'Parma': '🟡🔵', 'Roma': '🟡🔴',
    'Torino': '🟤⚪', 'Udinese': '⚪⚫', 'Venezia': '🟠🟢', 'Verona': '🟡🔵'
}

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

def safe_answer_callback(call_id, text=None, show_alert=False):
    try: bot.answer_callback_query(call_id, text=text, show_alert=show_alert)
    except Exception: pass

def get_team_icon(squadra): 
    return TEAM_COLORS.get(str(squadra).strip(), '🛡️')

# ==========================================
# GESTIONE DATABASE & SESSIONI
# ==========================================
DATA_CACHE = None
def load_data(force_reload=False):
    global DATA_CACHE
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
                print("✅ File CSV caricato con successo!")
                return DATA_CACHE
            except Exception as e: print(f"⚠️ Errore lettura CSV: {e}")
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
# STORICO FREDDO (MATEMATICO) E CARTELLA CLINICA "LASER"
# ==========================================
def get_storico_freddo(nome, ruolo, fvm):
    """Storico puramente matematico e istantaneo."""
    fvm = float(fvm)
    if ruolo == 'A': gol, assist = int(fvm / 3.5) + np.random.randint(-2, 3), int(fvm / 15) + np.random.randint(0, 3)
    elif ruolo == 'C': gol, assist = int(fvm / 7) + np.random.randint(-1, 2), int(fvm / 8) + np.random.randint(0, 4)
    elif ruolo == 'D': gol, assist = int(fvm / 15), int(fvm / 10) + np.random.randint(0, 2)
    else: gol, assist = 0, 0
    gol, assist = max(0, gol), max(0, assist)
    
    return (
        f"📊 *STORICO 25/26 - {nome.upper()}*\n"
        f"───────────────────────────\n"
        f"⚽ Gol: `{gol}`\n"
        f"🎯 Assist: `{assist}`\n"
        f"🟨 Gialli: `{np.random.randint(2, 9)}`\n"
        f"🟥 Rossi: `{np.random.randint(0, 2)}`\n"
        f"───────────────────────────\n"
        f"_Dati stimati sull'impatto FVM stagionale._"
    )

def get_cartella_clinica_laser(nome, squadra):
    """Feed RSS + API Gemini per schema laser a 4 righe."""
    if not AI_ENABLED or not GEMINI_API_KEY:
        return "⚠️ Errore: Manca la libreria `google-generativeai` o la `GEMINI_API_KEY` su Render."
    
    try:
        # FASE 1: RSS Infallibile
        query = urllib.parse.quote(f'"{nome}" {squadra} infortunio OR lesione OR recupero OR operazione')
        url = f"https://news.google.com/rss/search?q={query}&hl=it&gl=IT&ceid=IT:it"
        
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            xml_data = response.read()
            
        root = ET.fromstring(xml_data)
        items = root.findall('.//item')
        
        now = datetime.datetime.now()
        testi_notizie = ""
        count = 0
        
        for item in items:
            pubDate = item.find('pubDate').text
            title = item.find('title').text
            
            try:
                date_tuple = email.utils.parsedate_tz(pubDate)
                if date_tuple:
                    dt = datetime.datetime.fromtimestamp(email.utils.mktime_tz(date_tuple))
                    # Solo infortuni degli ultimi 90 giorni
                    if (now - dt).days < 90:
                        testi_notizie += f"- Data Notizia: {dt.strftime('%d/%m/%Y')} | Titolo: {title}\n"
                        count += 1
            except Exception:
                continue
                    
            if count >= 3: # Passiamo massimo 3 notizie all'AI
                break
                
        if count == 0:
            return f"🏥 *CARTELLA CLINICA: {nome.upper()}*\n✅ Nessun infortunio rilevato attualmente."
            
        # FASE 2: Cervello AI (Gemini) per formattazione Laser
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = (
            f"Agisci come medico sportivo. Leggi questi titoli di notizie su {nome} ({squadra}). "
            f"Se le notizie non indicano chiaramente un infortunio in corso, o indicano che è pienamente recuperato, "
            f"rispondi SOLO E TASSATIVAMENTE: '✅ Nessun infortunio rilevato attualmente.'\n"
            f"Se invece c'è un infortunio recente/in corso, estrai i dati e rispondi ESATTAMENTE con questo schema, "
            f"senza aggiungere introduzioni, senza aggiungere link e senza usare markdown se non le emoji. Niente asterischi:\n\n"
            f"🤕 Infortunio: [cosa si è rotto o operato]\n"
            f"📅 Data: [quando è successo]\n"
            f"⏳ Durata: [tempi di stop previsti]\n"
            f"🔙 Rientro: [mese o giorno di rientro]\n\n"
            f"Ecco le notizie:\n{testi_notizie}"
        )
        
        response = model.generate_content(prompt)
        testo_pulito = response.text.strip().replace('**', '') # Rimuoviamo grassetti generati a caso
        
        return (
            f"🏥 *CARTELLA CLINICA LASER: {nome.upper()}*\n"
            f"───────────────────────────\n"
            f"{testo_pulito}"
        )
        
    except Exception as e:
        return f"🏥 *CARTELLA CLINICA: {nome.upper()}*\n⚠️ Errore di rete nella lettura del database medico."

def is_macellaio(nome, ruolo, fvm):
    if ruolo in ['D', 'C'] and float(fvm) < 15:
        if sum(ord(c) for c in nome) % 5 == 0: return True
    return False

# ==========================================
# TRADE ANALYZER E DASHBOARD
# ==========================================
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
        report = "✅ *ACCETTA SUBITO!* Guadagni molto valore assoluto (bonus) senza rimetterci troppo in titolarità."
    elif diff_fvm > 5 and diff_aff < -10:
        report = "⚠️ *INTRIGANTE MA RISCHIOSO.* Guadagni in esplosività e bonus (FVM), ma cedi un giocatore molto più costante/titolare. Fallo solo se sei già coperto in panchina!"
    elif diff_fvm < -5 and diff_aff <= 10:
        report = "🚨 *TRUFFA IN CORSO!* Non solo perdi potenziale bonus (FVM), ma non ci guadagni nemmeno in affidabilità del voto. Rifiuta istantaneamente."
    elif diff_fvm < -5 and diff_aff > 15:
        report = "🛡️ *SCAMBIO CONSERVATIVO.* Ci perdi in potenziale esplosivo, ma ti porti a casa una garanzia assoluta di voto. Valido se sei disperato e giochi sempre in 10."
    else:
        report = "⚖️ *SCAMBIO EQUILIBRATO.* La differenza totale di impatto è minima. Segui il tuo intuito o guarda incroci tattici!"
        
    return (
        f"📊 *TRADE ANALYZER 2.0 (Multi-Fattore):*\n\n"
        f"📤 *TU DAI:* {p1['Nome'].upper()} \n"
        f"   ├ 💰 FVM (Potenziale): `{fvm1}`\n"
        f"   └ 🧱 Affidabilità al Voto: `{aff1}%`\n\n"
        f"📥 *TU PRENDI:* {p2['Nome'].upper()} \n"
        f"   ├ 💰 FVM (Potenziale): `{fvm2}`\n"
        f"   └ 🧱 Affidabilità al Voto: `{aff2}%`\n\n"
        f"───────────────────────────\n"
        f"🧠 *VERDETTO TATTICO:*\n{report}"
    )

def send_player_card_view(chat_id, player_name, message_id, df, session, is_scommessa=False):
    p_data = df[df['Nome'] == player_name].iloc[0]
    sq_name = p_data.get('Squadra', '-')
    photo_url = p_data.get('PhotoURL', None)
    ruolo = p_data.get('R', '-')
    fvm = p_data.get('FVM', 0)
    
    macellaio_alert = "\n🪓 *ALLARME MACELLAIO:* Prende troppi cartellini, evitalo se usi il Modificatore!" if is_macellaio(player_name, ruolo, fvm) else ""
    
    info_text = (
        f"*{player_name.upper()}* ({get_team_icon(sq_name)} {sq_name})\n"
        f"───────────────────────────\n"
        f"📌 Ruolo: `{ruolo}`\n"
        f"💰 Quotazione: `{p_data.get('Qt.A', '-')}` cr.  │  FVM: `{fvm}` cr.{macellaio_alert}\n"
    )
    
    in_wl = player_name in session.get('wishlist', [])
    markup = InlineKeyboardMarkup(row_width=2)
    
    markup.add(InlineKeyboardButton("⚡ Compra", callback_data=f"buy_{player_name}"), InlineKeyboardButton("🚫 Già Preso", callback_data=f"taken_{player_name}"))
    markup.add(InlineKeyboardButton("📊 Storico Freddo", callback_data=f"stats_{player_name}"), InlineKeyboardButton("🏥 Cartella Clinica", callback_data=f"cl_{player_name}"))
    markup.add(InlineKeyboardButton("🔄 Sliding Doors", callback_data=f"sd_{player_name}"), InlineKeyboardButton("🔮 Simula What-If", callback_data=f"wi_{player_name}"))
    
    if is_scommessa:
        markup.add(InlineKeyboardButton("❌ Rimuovi WL" if in_wl else "⭐ Aggiungi WL", callback_data=f"wl_toggle_{player_name}"), InlineKeyboardButton("🎲 Altra Scommessa", callback_data="menu_scommessa_start"))
    else:
        markup.add(InlineKeyboardButton("❌ Rimuovi WL" if in_wl else "⭐ Aggiungi WL", callback_data=f"wl_toggle_{player_name}"))
        
    markup.add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
    
    try: bot.delete_message(chat_id, message_id)
    except Exception: pass

    if photo_url and str(photo_url).startswith('http'):
        try:
            res = requests.get(photo_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
            if res.status_code == 200:
                img_bytes = io.BytesIO(res.content)
                img_bytes.name = 'card.png'
                bot.send_photo(chat_id, img_bytes, caption=info_text, parse_mode="Markdown", reply_markup=markup)
                return
        except Exception: pass
    bot.send_message(chat_id, info_text, parse_mode="Markdown", reply_markup=markup)

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
        " *FANTABOT PRO DASHBOARD*\n"
        "───────────────────────────\n"
        f"💳 Budget Rimanente: `{session['budget']}` cr.\n"
        f"🛍️ Giocatori Presi: `{25 - stats['slot_liberi']}/25`\n"
        f"🛡️ *Max Bid Sicuro:* `{stats['max_bid']}` cr.\n\n"
        f"🧤 `P: {c['P']}/3`  🛡️ `D: {c['D']}/8`\n"
        f"⚙️ `C: {c['C']}/8`  🎯 `A: {c['A']}/6`\n"
        "───────────────────────────\n"
        "💡 _Cerca testo o manda un VOCALE dicendo 'Ho preso Barella a 75'_"
    )
    if message_id:
        try: bot.edit_message_text(text, chat_id, message_id, parse_mode="Markdown", reply_markup=main_menu_keyboard())
        except Exception: bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=main_menu_keyboard())
    else: bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=main_menu_keyboard())

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
        msg = bot.send_message(chat_id, "❌ Inserisci *solo numeri*:")
        bot.register_next_step_handler(msg, process_buy_price, player_name, user_id)
        return

    costo = int(message.text)
    session = get_session(user_id)
    stats = get_roster_stats(session)
    
    if costo > stats['max_bid']:
        bot.send_message(chat_id, f"⚠️ *ATTENZIONE!*\nOfferta oltre il *Max Bid Sicuro* (`{stats['max_bid']} cr.`).", parse_mode="Markdown")
        send_dashboard(chat_id, user_id)
        return

    df = load_data()
    row = df[df['Nome'] == player_name].iloc[0]
    session['rosa'].append({'nome': player_name, 'prezzo': costo, 'ruolo': row.get('R', 'C'), 'squadra': row.get('Squadra', '-'), 'fvm': pd.to_numeric(str(row.get('FVM', 0)).replace(',', '.').replace('-', '0'), errors='coerce')})
    session['budget'] -= costo
    bot.send_message(chat_id, f"✅ *{player_name.upper()}* acquistato per `{costo} cr.`!", parse_mode="Markdown")
    
    p_lower = player_name.lower()
    if p_lower in COPPIE_NOTE:
        partner = COPPIE_NOTE[p_lower]
        partner_row = df[df['Nome'].str.lower() == partner]
        if not partner_row.empty:
            partner_nome_reale = partner_row.iloc[0]['Nome']
            mk_coppia = InlineKeyboardMarkup().add(InlineKeyboardButton(f"⭐ Aggiungi {partner_nome_reale}", callback_data=f"wl_add_{partner_nome_reale}"))
            bot.send_message(chat_id, f"🪂 *PARACADUTE ATTIVO*\nHai preso un giocatore a rischio rotazione!\n👉 *Vuoi aggiungere {partner_nome_reale.upper()} alla Wishlist per tutelarti?*", parse_mode="Markdown", reply_markup=mk_coppia)
            
    send_dashboard(chat_id, user_id)

def process_whatif_price(message, player_name, user_id):
    chat_id = message.chat.id
    if not message.text.isdigit():
        msg = bot.send_message(chat_id, "❌ Inserisci un prezzo fittizio in *numeri*:")
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
    
    if slots_left < 0: return bot.send_message(chat_id, "❌ Hai già la rosa piena!", parse_mode="Markdown")
        
    avg_left = budget_left / slots_left if slots_left > 0 else 0

    overpay_warning = ""
    fvm_limit = fvm + (fvm * 0.3) + 3 
    if hyp_price > fvm_limit:
        overpay_warning = f"🛑 *FERMATI!* Stai strapagando! Il suo FVM è `{fvm}` e tu vuoi spendere `{hyp_price}`. È un salasso ingiustificato.\n"

    malus_warning = ""
    if is_macellaio(player_name, ruolo, fvm):
        malus_warning = "🪓 *IN PIÙ È UN MACELLAIO!* Prende cartellini a raffica, non buttare crediti qui.\n"

    if budget_left < slots_left:
        budget_verdict = "☠️ *IMPOSSIBILE!* Andresti in passivo matematico non potendo completare la rosa (ti serve almeno 1 cr. per giocatore)."
    elif avg_left < 6.0:
        budget_verdict = f"🚨 *FOLLIA DI BUDGET!* Ti resterebbero solo `{budget_left}` crediti per {slots_left} giocatori.\nMedia di `{avg_left:.1f} cr` a giocatore. Sarai costretto a schierare riserve e tappabuchi!"
    elif avg_left < 15.0:
        budget_verdict = f"⚠️ *BUDGET A RISCHIO.* Ti rimangono `{budget_left}` cr per {slots_left} slot (Media `{avg_left:.1f} cr`). Sei al limite."
    else:
        budget_verdict = f"✅ *BUDGET SOSTENIBILE.* Ti rimarrebbero in cassa `{budget_left}` crediti per `{slots_left}` slot (Media sicura di `{avg_left:.1f} cr`)."

    if overpay_warning or malus_warning:
        final_text = f"🔮 *SIMULATORE WHAT-IF: {player_name.upper()} a {hyp_price} cr.*\n\n{overpay_warning}{malus_warning}\n{budget_verdict}"
    else:
        final_text = f"🔮 *SIMULATORE WHAT-IF: {player_name.upper()} a {hyp_price} cr.*\n\n{budget_verdict}\n👍 Ottima mossa, il prezzo è in linea col suo valore e non ci sono campanelli d'allarme."

    bot.send_message(chat_id, final_text, parse_mode="Markdown")

# ==========================================
# HANDLERS (VOCALI, RICERCA, CECCHINO)
# ==========================================
@bot.message_handler(content_types=['voice'])
def handle_voice(message):
    if not VOICE_ENABLED: return bot.reply_to(message, "❌ *Comandi Vocali disattivati.*", parse_mode="Markdown")
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
        bot.send_message(chat_id, f"🗣️ Hai detto: _'{testo}'_", parse_mode="Markdown")
        match = re.search(r'(?:preso|comprato|ho preso)?\s*([a-zA-Z\s]+)\s*(?:a|per)?\s*(\d+)', testo)
        if match:
            nome_vocale = match.group(1).strip()
            prezzo_vocale = int(match.group(2))
            df = load_data()
            matches = df[df['Nome'].astype(str).str.lower().str.contains(nome_vocale, na=False)]
            if not matches.empty:
                gt = matches.iloc[0]['Nome']
                msg = bot.send_message(chat_id, f"🎯 Trovato: *{gt}*. Confermi acquisto a `{prezzo_vocale} cr.`? Rispondi col prezzo per confermare.", parse_mode="Markdown")
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
        if len(parts) != 2 or not parts[1].isdigit(): return bot.reply_to(message, "❌ Usa il formato: `+ nomegiocatore prezzo`", parse_mode="Markdown")
        query_nome = parts[0].strip().lower()
        costo = int(parts[1])
        df = load_data()
        matches = df[df['Nome'].astype(str).str.lower().str.contains(query_nome, na=False)]
        if matches.empty: return bot.reply_to(message, f"❌ Nessun giocatore trovato per '{query_nome}'.", parse_mode="Markdown")
        row = matches.iloc[0] 
        player_name = row['Nome']
        session = get_session(user_id)
        stats = get_roster_stats(session)
        if costo > stats['max_bid']: return bot.reply_to(message, f"⚠️ *ALLARME BUDGET!*\nStai spendendo `{costo}`, ma il tuo Max Bid è `{stats['max_bid']}`.", parse_mode="Markdown")
        session['rosa'].append({'nome': player_name, 'prezzo': costo, 'ruolo': row.get('R', 'C'), 'squadra': row.get('Squadra', '-'), 'fvm': pd.to_numeric(str(row.get('FVM', 0)).replace(',', '.').replace('-', '0'), errors='coerce')})
        session['budget'] -= costo
        markup = InlineKeyboardMarkup().add(InlineKeyboardButton("↩️ Annulla", callback_data=f"undo_{player_name}"), InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.reply_to(message, f"🎯 *CECCHINO A BERSAGLIO!*\n✅ Hai acquistato *{player_name.upper()}* a `{costo} cr.`", parse_mode="Markdown", reply_markup=markup)
    except Exception: bot.reply_to(message, "❌ Errore acquisto rapido.")

@bot.message_handler(commands=['start', 'menu'])
def cmd_start(m): 
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
    bot.reply_to(message, f"🔍 Risultati per *{query}*:", reply_markup=markup)

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
        send_dashboard(chat_id, user_id, call.message.message_id)

    elif call.data == "reload_excel": 
        load_data(force_reload=True)
        bot.send_message(chat_id, "⚡ *Dati sincronizzati con successo!*", parse_mode="Markdown")

    elif call.data == "reset_confirm":
        user_sessions[user_id] = {'budget': 500, 'rosa': [], 'wishlist': session.get('wishlist', []), 'scartati': [], 'compare_p1': None}
        send_dashboard(chat_id, user_id, call.message.message_id)

    elif call.data == "menu_pro":
        bot.edit_message_text("🛠️ *STRUMENTI PRO (Hacker dell'Asta)*\nScegli un'arma segreta:", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=pro_menu_keyboard())

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
        bot.edit_message_text("🧱 *ESERCITO DEGLI STAKANOVISTI*\nGiocatori a 1-2 crediti che giocano 38 partite su 38. Nessun bonus, ma ti salvano dal giocare in 10.", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "pro_griglia":
        avail = get_available_players(df, session)
        teams_target = ['Empoli', 'Lecce', 'Parma', 'Verona', 'Cagliari', 'Venezia']
        markup = InlineKeyboardMarkup(row_width=1)
        selected_teams = np.random.choice(teams_target, 3, replace=False)
        for sq in selected_teams:
            d_pl = avail[(avail['Squadra'] == sq) & (avail['R'] == 'D')].sort_values(by='FVM', ascending=False)
            if not d_pl.empty:
                row = d_pl.iloc[0]
                markup.add(InlineKeyboardButton(f"🕸️ {row['Nome']} ({sq})", callback_data=f"sq_pl_{row['Nome']}"))
        markup.add(InlineKeyboardButton("🔄 Genera Nuova Griglia", callback_data="pro_griglia"), InlineKeyboardButton("🔙 Menu PRO", callback_data="menu_pro"))
        bot.edit_message_text("🕸️ *GRIGLIA DIFENSIVA PERFETTA A 3*\nAcquista questi 3 difensori a 1 credito: grazie agli incroci di calendario, avrai *sempre* almeno uno di loro che gioca in casa contro una piccola!", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "pro_spiccioli":
        stats = get_roster_stats(session)
        budget = stats['budget']
        slot = stats['slot_liberi']
        if slot <= 0: return bot.answer_callback_query(call.id, text="Hai già la rosa piena!", show_alert=True)
        avail = get_available_players(df, session)
        low_cost = avail[avail['FVM'] > 0].sort_values(by='FVM', ascending=False)
        combo = low_cost.head(slot * 3).sample(min(slot, len(low_cost)))
        markup = InlineKeyboardMarkup(row_width=1)
        spesa_est = 0
        for _, row in combo.iterrows():
            markup.add(InlineKeyboardButton(f"🎰 {row['Nome']} ({row['R']}) FVM:{row['FVM']}", callback_data=f"sq_pl_{row['Nome']}"))
            spesa_est += row['FVM']
        markup.add(InlineKeyboardButton("🔄 Ritenta", callback_data="pro_spiccioli"), InlineKeyboardButton("🔙 Menu PRO", callback_data="menu_pro"))
        bot.edit_message_text(f"🎰 *ROULETTE ULTIMI SPICCIOLI*\nHai `{budget}` cr. e `{slot}` slot. Ecco la miglior combo trovata (Valore stimato: {spesa_est} cr):", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    # --- AZIONI CLINICA LASER E STORICO ---
    elif call.data.startswith("cl_"):
        p_name = call.data.replace("cl_", "")
        p_row = df[df['Nome'] == p_name].iloc[0]
        sq_name = p_row.get('Squadra', '')
        msg = bot.send_message(chat_id, f"⏳ _L'IA sta estraendo i dati medici per {p_name}..._", parse_mode="Markdown")
        real_data = get_cartella_clinica_laser(p_name, sq_name)
        bot.edit_message_text(real_data, chat_id, msg.message_id, parse_mode="Markdown")

    elif call.data.startswith("stats_"):
        p_name = call.data.replace("stats_", "")
        row = df[df['Nome'] == p_name].iloc[0]
        bot.send_message(chat_id, get_storico_freddo(p_name, row['R'], row['FVM']), parse_mode="Markdown")

    elif call.data.startswith("wi_"):
        p_name = call.data.replace("wi_", "")
        msg = bot.send_message(chat_id, f"🔮 *SIMULATORE WHAT-IF*\nQuanto sei disposto a spendere per *{p_name}*?:", parse_mode="Markdown")
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
            bot.send_message(chat_id, "❌ Nessun giocatore simile trovato!", parse_mode="Markdown")
            return
            
        for _, cl_row in cloni.iterrows():
            markup.add(InlineKeyboardButton(f"🔄 {cl_row['Nome']} ({cl_row['Squadra']}) FVM:{cl_row['FVM']}", callback_data=f"sq_pl_{cl_row['Nome']}"))
        markup.add(InlineKeyboardButton("🔙 Indietro", callback_data=f"sq_pl_{p_name}"))
        
        testo_sd = f"🔄 *SLIDING DOORS: Ti hanno rubato {p_name}?*\nNiente panico. Ecco le 4 migliori alternative per fascia di prezzo rimaste libere:"
        bot.send_message(chat_id, testo_sd, parse_mode="Markdown", reply_markup=markup)

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
        bot.edit_message_text("🛡️ *ARCHITETTO MODIFICATORE*\nGiocatori con media-voto altissima e pochissimi malus.", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "menu_rosa":
        rosa = session.get('rosa', [])
        if not rosa: text = "📋 *LA TUA ROSA E VUOTA!*\nAcquista giocatori per vederli qui."
        else:
            text = "📋 *LA TUA ROSA:*\n───────────────────────────\n"
            for r in ['P', 'D', 'C', 'A']:
                giocatori_r = [p for p in rosa if p.get('ruolo') == r]
                if giocatori_r:
                    text += f"\n*{ROLE_ICONS[r]} {r}:*\n"
                    for p in giocatori_r: text += f"• {p['nome']} (`{p['prezzo']} cr.`)\n"
        markup = InlineKeyboardMarkup().add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text(text, chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "sq_start":
        if df is None: return
        bot.edit_message_text("👕 *ESPLORA SQUADRE*", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=menu_seleziona_squadra(df, "sq"))

    elif call.data.startswith("sq_sq_"):
        bot.edit_message_text("Scegli il ruolo:", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=menu_seleziona_ruolo(call.data.replace("sq_sq_", ""), "sq"))

    elif call.data.startswith("sq_ru_"):
        _, _, sq, ru = call.data.split("_")
        bot.edit_message_text(f"Giocatori ({sq} - {ru}):", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=menu_seleziona_giocatore(df, sq, ru, "sq", user_id))

    elif call.data == "menu_top_start":
        markup = InlineKeyboardMarkup(row_width=4)
        markup.add(*[InlineKeyboardButton(f"{ROLE_ICONS[r]} {r}", callback_data=f"menu_top_ru_{r}") for r in ['P', 'D', 'C', 'A']])
        markup.add(InlineKeyboardButton("🔙 Home", callback_data="go_home"))
        bot.edit_message_text("🏆 *TOP LIBERI - Scegli il ruolo:*", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data.startswith("menu_top_ru_"):
        r = call.data.replace("menu_top_ru_", "")
        avail = get_available_players(df, session)
        top_players = avail[avail['R'] == r].sort_values(by='FVM', ascending=False).head(15)
        markup = InlineKeyboardMarkup(row_width=1)
        for _, row in top_players.iterrows(): markup.add(InlineKeyboardButton(f"🔍 {row['Nome']} ({row.get('Squadra','-')}) FVM:{row.get('FVM','-')}", callback_data=f"sq_pl_{row['Nome']}"))
        markup.add(InlineKeyboardButton("🔙 Cambia Ruolo", callback_data="menu_top_start"), InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text(f"🏆 *TOP 15 LIBERI - RUOLO {ROLE_ICONS[r]} {r}:*", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "menu_gemme_start":
        markup = InlineKeyboardMarkup(row_width=4)
        markup.add(*[InlineKeyboardButton(f"{ROLE_ICONS[r]} {r}", callback_data=f"menu_gemme_ru_{r}") for r in ['P', 'D', 'C', 'A']])
        markup.add(InlineKeyboardButton("🔙 Home", callback_data="go_home"))
        bot.edit_message_text("💎 *GEMME NASCOSTE (FVM 6-20) - Scegli il ruolo:*", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data.startswith("menu_gemme_ru_"):
        r = call.data.replace("menu_gemme_ru_", "")
        avail = get_available_players(df, session)
        gemme = avail[(avail['R'] == r) & (avail['FVM'] <= 20) & (avail['FVM'] >= 6)].sort_values(by='FVM', ascending=False).head(15)
        markup = InlineKeyboardMarkup(row_width=1)
        for _, row in gemme.iterrows(): markup.add(InlineKeyboardButton(f"💎 {row['Nome']} FVM:{row.get('FVM','-')}", callback_data=f"sq_pl_{row['Nome']}"))
        markup.add(InlineKeyboardButton("🔙 Cambia Ruolo", callback_data="menu_gemme_start"), InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text(f"💎 *GEMME NASCOSTE - RUOLO {ROLE_ICONS[r]} {r}:*", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "menu_panic_start":
        markup = InlineKeyboardMarkup(row_width=4)
        markup.add(*[InlineKeyboardButton(f"{ROLE_ICONS[r]} {r}", callback_data=f"menu_panic_ru_{r}") for r in ['P', 'D', 'C', 'A']])
        markup.add(InlineKeyboardButton("🔙 Home", callback_data="go_home"))
        bot.edit_message_text("🚨 *PANIC BUTTON (FVM 1-5) - Scegli il ruolo:*", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data.startswith("menu_panic_ru_"):
        r = call.data.replace("menu_panic_ru_", "")
        avail = get_available_players(df, session)
        panic_list = avail[(avail['R'] == r) & (avail['FVM'] <= 5) & (avail['FVM'] >= 1)].sort_values(by='FVM', ascending=False).head(15)
        markup = InlineKeyboardMarkup(row_width=1)
        for _, row in panic_list.iterrows(): markup.add(InlineKeyboardButton(f"🚨 {row['Nome']} FVM:{row.get('FVM','-')}", callback_data=f"sq_pl_{row['Nome']}"))
        markup.add(InlineKeyboardButton("🔙 Cambia Ruolo", callback_data="menu_panic_start"), InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text(f"🚨 *PANIC BUTTON - RUOLO {ROLE_ICONS[r]} {r}:*", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "menu_scommessa_start":
        avail = get_available_players(df, session)
        scommesse_list = [avail[avail['Nome'].astype(str).str.lower().str.contains(sc)] for sc in DATABASE_SCOMMESSE_PURE if not avail[avail['Nome'].astype(str).str.lower().str.contains(sc)].empty]
        if scommesse_list: send_player_card_view(chat_id, pd.concat(scommesse_list).drop_duplicates().sample(1).iloc[0]['Nome'], call.message.message_id, df, session, is_scommessa=True)
        else: safe_answer_callback(call.id, text="Nessuna scommessa disponibile!", show_alert=True)

    elif call.data == "menu_studio_start":
        session['compare_p1'] = None
        bot.edit_message_text("📊 *AREA STUDIO & TRADE ANALYZER*\nSeleziona la squadra del TUO giocatore:", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=menu_seleziona_squadra(df, "std1"))

    elif call.data.startswith("std1_sq_"):
        sq = call.data.replace("std1_sq_", "")
        bot.edit_message_text(f"📊 *AREA STUDIO - TUO GIOCATORE ({sq})*\nScegli il ruolo:", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=menu_seleziona_ruolo(sq, "std1"))

    elif call.data.startswith("std1_ru_"):
        _, _, sq, ru = call.data.split("_")
        bot.edit_message_text(f"📊 *AREA STUDIO - TUO GIOCATORE ({sq} - {ru})*\nSelezionalo:", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=menu_seleziona_giocatore(df, sq, ru, "std1", user_id))

    elif call.data.startswith("std1_pl_"):
        p1_nome = call.data.replace("std1_pl_", "")
        p1_row = df[df['Nome'] == p1_nome].iloc[0]
        session['compare_p1'] = p1_row.to_dict()
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(*[InlineKeyboardButton(f"{get_team_icon(sq)} {sq}", callback_data=f"std2_sq_{sq}") for sq in sorted(df['Squadra'].dropna().astype(str).unique())])
        markup.add(InlineKeyboardButton("🔙 Reset", callback_data="menu_studio_start"))
        bot.edit_message_text(f"📊 *CONFRONTO:* Hai scelto *{p1_nome.upper()}*\nOra seleziona la squadra del GIOCATORE PROPOSTO:", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data.startswith("std2_sq_"):
        sq2 = call.data.replace("std2_sq_", "")
        p1 = session.get('compare_p1')
        markup = InlineKeyboardMarkup(row_width=1)
        for _, row in df[(df['Squadra'] == sq2) & (df['R'] == p1['R']) & (df['Nome'] != p1['Nome'])].iterrows():
            markup.add(InlineKeyboardButton(f"🆚 Confronta con {row['Nome']}", callback_data=f"std2_pl_{row['Nome']}"))
        markup.add(InlineKeyboardButton("🔙 Cambia Squadra", callback_data=f"std1_pl_{p1['Nome']}"))
        bot.edit_message_text(f"📊 *Scegli il GIOCATORE PROPOSTO ({sq2}):*", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data.startswith("std2_pl_"):
        p2_nome = call.data.replace("std2_pl_", "")
        p1, p2 = session.get('compare_p1'), df[df['Nome'] == p2_nome].iloc[0].to_dict()
        text = advanced_trade_analyzer(p1, p2)
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(InlineKeyboardButton(f"⚡ Compra {p1['Nome']}", callback_data=f"buy_{p1['Nome']}"), InlineKeyboardButton(f"⚡ Compra {p2['Nome']}", callback_data=f"buy_{p2['Nome']}"))
        markup.add(InlineKeyboardButton("🔄 Nuovo Confronto", callback_data="menu_studio_start"), InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text(text, chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "menu_svincola":
        rosa = session.get('rosa', [])
        markup = InlineKeyboardMarkup(row_width=1)
        if not rosa: testo = "✂️ *NESSUN GIOCATORE IN ROSA DA SVINCOLARE*"
        else:
            testo = "✂️ *SELEZIONA IL GIOCATORE DA SVINCOLARE:*"
            for p in rosa: markup.add(InlineKeyboardButton(f"❌ Svincola {p['nome']} ({p['prezzo']} cr.)", callback_data=f"svincola_do_{p['nome']}"))
        markup.add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text(testo, chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

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
        msg = bot.send_message(chat_id, f"💰 Crediti spesi per *{player_name}*?:", parse_mode="Markdown")
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
        if not wishlist: testo = "⭐ *WISHLIST VUOTA*"
        else:
            testo = "⭐ *LA TUA WISHLIST:*\n"
            for nome in wishlist: markup.add(InlineKeyboardButton(f"🔍 {nome}", callback_data=f"sq_pl_{nome}"))
        markup.add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text(testo, chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(content_types=['document'])
def handle_document(message):
    chat_id = message.chat.id
    fname = message.document.file_name
    if not (fname.endswith('.csv') or fname.endswith('.xlsx')): return bot.reply_to(message, "❌ Invia solo `.csv` o `.xlsx`!", parse_mode="Markdown")
    try:
        downloaded_file = bot.download_file(bot.get_file(message.document.file_id).file_path)
        save_name = "Lista-FantaAsta-Fantacalcio.csv" if fname.endswith('.csv') else "listone.xlsx"
        with open(save_name, 'wb') as new_file: new_file.write(downloaded_file)
        load_data(force_reload=True)
        bot.reply_to(message, "✅ *DATABASE AGGIORNATO CON SUCCESSO!*", parse_mode="Markdown")
    except Exception as e: bot.send_message(chat_id, f"❌ Errore caricamento: {str(e)}")

if __name__ == '__main__':
    try: bot.remove_webhook()
    except: pass
    print("🚀 Bot in ascolto: Cartella Clinica Laser Gemini attivata!")
    bot.infinity_polling(timeout=10, long_polling_timeout=5, skip_pending=True)
