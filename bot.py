import os
import io
import re
import requests
import pandas as pd
import numpy as np
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from PIL import Image, ImageDraw, ImageFont
from duckduckgo_search import DDGS

# Token letto dalle variabili d'ambiente di Render
TOKEN = os.getenv("BOT_TOKEN", "INSERISCI_QUI_IL_NUOVO_TOKEN")
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

DATABASE_SCOMMESSE_PURE = [
    'bernabe', 'fazzini', 'bonny', 'oristanio', 'paz', 'marchwinski', 'castro', 
    'belahyane', 'tengstedt', 'da cunha', 'moro', 'chaka traore', 'pisilli', 'ekhator', 
    'alisson santos', 'solet', 'idzes', 'mangas', 'milla', 'kike perez', 'ndour', 
    'viti', 'goglichidze', 'alajbegovic', 'nico paz', 'suslov', 'mosquera', 'tchaouna',
    'camarda', 'vitinha'
]

# --- FUNZIONE GENERAZIONE/RECUPERO IMMAGINI GARANTITA ---
def get_player_avatar_stream(nome: str, id_val: str = None, ruolo: str = 'C') -> io.BytesIO:
    """Recupera l'immagine del giocatore o genera un avatar colorato in RAM. Non fallisce mai."""
    # 1. Prova tramite ID ufficiale
    if id_val and str(id_val).isdigit():
        url_id = f"https://content.fantacalcio.it/web/immagini/cadres/{id_val}.png"
        try:
            resp = requests.get(url_id, timeout=2)
            if resp.status_code == 200 and len(resp.content) > 1000:
                img = Image.open(io.BytesIO(resp.content)).convert("RGBA")
                buf = io.BytesIO()
                img.save(buf, format='PNG')
                buf.seek(0)
                return buf
        except Exception:
            pass

    # 2. Prova tramite ricerca Web rapida
    try:
        query = f"{nome} calciatore png trasparente face"
        with DDGS() as ddgs:
            results = list(ddgs.images(query, max_results=2))
            for res in results:
                img_url = res.get("image")
                resp = requests.get(img_url, timeout=2)
                if resp.status_code == 200:
                    img = Image.open(io.BytesIO(resp.content)).convert("RGBA")
                    buf = io.BytesIO()
                    img.save(buf, format='PNG')
                    buf.seek(0)
                    return buf
    except Exception:
        pass

    # 3. Fallback: Genera Avatar Colorato in base al Ruolo
    role_colors = {
        'P': (241, 196, 15),  # Giallo
        'D': (46, 204, 113),  # Verde
        'C': (52, 152, 219),  # Blu
        'A': (231, 76, 60)    # Rosso
    }
    bg_color = role_colors.get(ruolo, (149, 165, 166))
    
    img = Image.new('RGBA', (300, 300), color=bg_color)
    draw = ImageDraw.Draw(img)
    
    parti_nome = nome.split()
    iniziali = (parti_nome[0][0] + parti_nome[-1][0]).upper() if len(parti_nome) > 1 else nome[:2].upper()
    
    draw.ellipse((15, 15, 285, 285), outline=(255, 255, 255), width=6)
    
    try:
        font = ImageFont.truetype("arial.ttf", 90)
    except Exception:
        font = ImageFont.load_default()
        
    draw.text((150, 150), iniziali, fill=(255, 255, 255), font=font, anchor="mm")
    
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return buf

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
            for row_h in range(0, 5):
                try:
                    df_test = pd.read_excel("listone.xlsx", header=row_h, engine='openpyxl')
                    cols = [str(c).strip().lower() for c in df_test.columns]
                    if 'nome' in cols or any('id' in c for c in cols):
                        df_test.columns = [str(c).strip() for c in df_test.columns]
                        DATA_CACHE = df_test
                        break
                except Exception:
                    continue
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

# Modalità Cecchino
@bot.message_handler(func=lambda m: m.text.strip().startswith('+'))
def modalita_cecchino(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = message.text.strip()[1:].strip() 
    
    try:
        parts = text.rsplit(' ', 1)
        if len(parts) != 2 or not parts[1].isdigit():
            bot.reply_to(message, "❌ *Errore Cecchino!*\nUsa il formato: `+ nomegiocatore prezzo`\nEsempio: `+ neres 35`", parse_mode="Markdown")
            return
            
        query_nome = parts[0].strip().lower()
        costo = int(parts[1])
        
        df = load_data()
        matches = df[df['Nome'].str.lower().str.contains(query_nome, na=False)]
        
        if matches.empty:
            bot.reply_to(message, f"❌ Nessun giocatore trovato per '{query_nome}'.", parse_mode="Markdown")
            return
            
        row = matches.iloc[0] 
        player_name = row['Nome']
        
        session = get_session(user_id)
        stats = get_roster_stats(session)
        
        if costo > stats['max_bid']:
            bot.reply_to(message, f"⚠️ *ALLARME BUDGET!*\nStai spendendo `{costo}`, ma il tuo Max Bid è `{stats['max_bid']}`.", parse_mode="Markdown")
            return
            
        ruolo_acquistato = row.get('R', 'C')
        sq_acquistata = row.get('Squadra', '-')
        fvm = pd.to_numeric(str(row.get('FVM', 0)).replace(',', '.').replace('-', '0'), errors='coerce')
        fm = pd.to_numeric(str(row.get('FM', 0)).replace(',', '.').replace('-', '0'), errors='coerce')
        slot = str(row.get('Slot', '-'))
        
        session['rosa'].append({
            'nome': player_name, 'prezzo': costo, 'ruolo': ruolo_acquistato, 'squadra': sq_acquistata,
            'fvm': 0 if pd.isna(fvm) else fvm, 'fm': 0 if pd.isna(fm) else fm, 'rigori': str(row.get('Rigori_Piazzati', '')), 'slot': slot
        })
        session['budget'] -= costo
        
        markup = InlineKeyboardMarkup().add(InlineKeyboardButton("↩️ Annulla", callback_data=f"undo_{player_name}"), InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.reply_to(message, f"🎯 *CECCHINO A BERSAGLIO!*\n✅ Hai acquistato *{player_name.upper()}* a `{costo} cr.`\nRimangono {session['budget']} crediti.", parse_mode="Markdown", reply_markup=markup)
        
    except Exception:
        bot.reply_to(message, "❌ Errore durante l'acquisto rapido.")

@bot.message_handler(commands=['start', 'menu'])
def cmd_start(m): 
    send_dashboard(m.chat.id, m.from_user.id)

@bot.message_handler(func=lambda m: not m.text.startswith('/') and not m.text.startswith('+') and not m.text.isdigit())
def search_player(message):
    query = message.text.strip().lower()
    df = load_data()
    if df is None or len(query) < 3: return
    matches = df[df['Nome'].str.lower().str.contains(query, na=False)]
    if matches.empty: return bot.reply_to(message, "❌ Nessun giocatore trovato.")
        
    markup = InlineKeyboardMarkup(row_width=1)
    for _, row in matches.head(10).iterrows():
        markup.add(InlineKeyboardButton(f"{ROLE_ICONS.get(row.get('R','C'),'')} {row['Nome']} ({row.get('Squadra','-')})", callback_data=f"sq_pl_{row['Nome']}"))
    bot.reply_to(message, f"🔍 Risultati per *{query}*:", reply_markup=markup)

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

def process_buy_price(message, player_name, user_id):
    chat_id = message.chat.id
    if not message.text or not message.text.isdigit():
        msg = bot.send_message(chat_id, "❌ Inserisci *solo numeri interi*:", parse_mode="Markdown")
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
    try: row = df[df['Nome'] == player_name].iloc[0]
    except: return

    squadra_acquistata = row.get('Squadra', '-')
    ruolo_acquistato = row.get('R', 'C')
    fvm = pd.to_numeric(str(row.get('FVM', 0)).replace(',', '.').replace('-', '0'), errors='coerce')
    fm = pd.to_numeric(str(row.get('FM', 0)).replace(',', '.').replace('-', '0'), errors='coerce')
    slot = str(row.get('Slot', '-'))

    session['rosa'].append({
        'nome': player_name, 'prezzo': costo, 'ruolo': ruolo_acquistato, 'squadra': squadra_acquistata,
        'fvm': 0 if pd.isna(fvm) else fvm, 'fm': 0 if pd.isna(fm) else fm, 'rigori': str(row.get('Rigori_Piazzati', '')), 'slot': slot
    })
    session['budget'] -= costo
    
    markup = InlineKeyboardMarkup().add(InlineKeyboardButton("↩️ Annulla", callback_data=f"undo_{player_name}"), InlineKeyboardButton("🏠 Home", callback_data="go_home"))
    bot.send_message(chat_id, f"✅ *{player_name.upper()}* acquistato per `{costo} cr.`!", parse_mode="Markdown", reply_markup=markup)

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
        send_dashboard(chat_id, user_id, call.message.message_id)

    elif call.data == "reload_excel": 
        load_data(force_reload=True)
        bot.send_message(chat_id, "⚡ *Dati sincronizzati con successo!*", parse_mode="Markdown")

    elif call.data == "reset_confirm":
        user_sessions[user_id] = {'budget': 500, 'rosa': [], 'selected_for_compare': [], 'wishlist': session.get('wishlist', []), 'scartati': []}
        send_dashboard(chat_id, user_id, call.message.message_id)

    # Panic Button
    elif call.data == "menu_panic":
        markup = InlineKeyboardMarkup(row_width=4)
        markup.add(
            InlineKeyboardButton("🧤 P", callback_data="panic_ruolo_P"),
            InlineKeyboardButton("🛡️ D", callback_data="panic_ruolo_D"),
            InlineKeyboardButton("⚙️ C", callback_data="panic_ruolo_C"),
            InlineKeyboardButton("🎯 A", callback_data="panic_ruolo_A")
        )
        markup.add(InlineKeyboardButton("🔙 Home", callback_data="go_home"))
        bot.edit_message_text("🚨 *PANIC BUTTON ATTIVATO*\nScegli un ruolo per trovare i migliori disperati a bassissimo costo!", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data.startswith("panic_ruolo_"):
        ruolo = call.data.split("_")[-1]
        nomi_in_rosa = [p['nome'] for p in session['rosa']]
        scartati = session.get('scartati', [])
        
        col_base = 'FVM' if 'FVM' in df.columns else 'Qt.A'
        df['Valore_Ord'] = pd.to_numeric(df[col_base].astype(str).str.replace(',', '.').str.replace('-', '0'), errors='coerce').fillna(0)
        df['FM_Ord'] = pd.to_numeric(df['FM'].astype(str).str.replace(',', '.').str.replace('-', '0'), errors='coerce').fillna(0)
        
        df_liberi = df[(df['R'] == ruolo) & (~df['Nome'].isin(nomi_in_rosa)) & (~df['Nome'].isin(scartati)) & (df['Valore_Ord'] > 0) & (df['Valore_Ord'] <= 3)]
        df_top = df_liberi.sort_values(by=['FM_Ord', 'Valore_Ord'], ascending=[False, True]).head(5)
        
        testo = f"🚨 *SALVAGENTE {ROLE_ICONS.get(ruolo, '')} (1-3 Cr.)*\nI migliori scarti per FM e Titolarità:\n\n"
        markup = InlineKeyboardMarkup(row_width=1)
        
        if df_top.empty: testo += "_Purtroppo non c'è più nulla di salvabile a così poco..._"
        else:
            for _, row in df_top.iterrows():
                testo += f"🆘 *{row['Nome']}* ({row.get('Squadra','-')}) ─ FM: `{row['FM_Ord']}`\n"
                markup.add(InlineKeyboardButton(f"🔍 Prendi {row['Nome']} (1 cr)", callback_data=f"sq_pl_{row['Nome']}"))
                
        markup.add(InlineKeyboardButton("🔙 Indietro", callback_data="menu_panic"), InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text(testo, chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    # Formazione
    elif call.data == "menu_formazione":
        rosa = session['rosa']
        if len(rosa) < 11:
            bot.send_message(chat_id, "❌ Acquista almeno 11 giocatori prima di schierare la formazione!")
            return
            
        por = sorted([p for p in rosa if p['ruolo'] == 'P'], key=lambda x: x['fm'], reverse=True)
        dif = sorted([p for p in rosa if p['ruolo'] == 'D'], key=lambda x: x['fm'], reverse=True)
        cen = sorted([p for p in rosa if p['ruolo'] == 'C'], key=lambda x: x['fm'], reverse=True)
        att = sorted([p for p in rosa if p['ruolo'] == 'A'], key=lambda x: x['fm'], reverse=True)
        
        if not por or len(dif) < 3 or len(cen) < 3 or len(att) < 1:
            bot.edit_message_text("❌ *Impossibile calcolare il Modulo*\nTi mancano giocatori in alcuni ruoli.", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🏠 Home", callback_data="go_home")))
            return

        schema = f"3-{min(4, len(cen))}-{min(3, len(att))}"
        testo = f"⚽ *LA TUA FORMAZIONE TIPO ({schema})*\n\n"
        testo += f"🧤 *P:* {por[0]['nome']} ({por[0]['squadra']})\n"
        testo += f"🛡️ *D:* " + " - ".join([p['nome'] for p in dif[:3]]) + "\n"
        testo += f"⚙️ *C:* " + " - ".join([p['nome'] for p in cen[:int(schema.split('-')[1])]]) + "\n"
        testo += f"🎯 *A:* " + " - ".join([p['nome'] for p in att[:int(schema.split('-')[2])]]) + "\n"
        
        bot.edit_message_text(testo, chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🏠 Home", callback_data="go_home")))

    # Rosa
    elif call.data == "menu_rosa":
        rosa = session['rosa']
        text = f"📋 *LA MIA ROSA*\n───────────────────────────\n💰 *Budget Residuo:* `{session['budget']}` cr.\n\n"
        if not rosa: text += "_Nessun calciatore in rosa._"
        else:
            for idx, p in enumerate(rosa, 1):
                text += f"`{idx:02d}.` {ROLE_ICONS.get(p.get('ruolo','C'), '👤')} *{p['nome']}* ── `{p['prezzo']} cr.`\n"
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔙 Home", callback_data="go_home"))
        bot.edit_message_text(text, chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    # Top Liberi
    elif call.data == "menu_top":
        markup = InlineKeyboardMarkup(row_width=4)
        markup.add(
            InlineKeyboardButton("🧤 P", callback_data="top_ruolo_P"),
            InlineKeyboardButton("🛡️ D", callback_data="top_ruolo_D"),
            InlineKeyboardButton("⚙️ C", callback_data="top_ruolo_C"),
            InlineKeyboardButton("🎯 A", callback_data="top_ruolo_A")
        )
        markup.add(InlineKeyboardButton("🔙 Home", callback_data="go_home"))
        bot.edit_message_text("🏆 *TOP LIBERI*\nScegli un ruolo:", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data.startswith("top_ruolo_"):
        ruolo = call.data.split("_")[-1]
        nomi_in_rosa = [p['nome'] for p in session['rosa']]
        scartati = session.get('scartati', [])
        
        col_base = 'FVM' if 'FVM' in df.columns else 'Qt.A'
        df['Valore_Ord'] = pd.to_numeric(df[col_base].astype(str).str.replace(',', '.').str.replace('-', '0'), errors='coerce').fillna(0)
        df_liberi = df[(df['R'] == ruolo) & (~df['Nome'].isin(nomi_in_rosa)) & (~df['Nome'].isin(scartati))]
        df_top = df_liberi.sort_values(by='Valore_Ord', ascending=False).head(10)
        
        testo = f"🏆 *TOP {ROLE_ICONS.get(ruolo, '')} LIBERI*\n\n"
        markup = InlineKeyboardMarkup(row_width=2)
        if df_top.empty: testo += "_Nessun giocatore disponibile._"
        else:
            for _, row in df_top.iterrows():
                nome = row['Nome']
                testo += f"🔹 *{nome}* ({row.get('Squadra','-')}) ─ FVM: `{row['Valore_Ord']}`\n"
                markup.row(InlineKeyboardButton(f"🔍 Info {nome[:10]}", callback_data=f"sq_pl_{nome}"), InlineKeyboardButton("❌ Scarta", callback_data=f"dsc_{ruolo}_{nome[:15]}"))
                
        markup.add(InlineKeyboardButton("🔙 Ruoli", callback_data="menu_top"), InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text(testo, chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data.startswith("dsc_"):
        parts = call.data.split("_")
        ruolo = parts[1]
        nome_t = "_".join(parts[2:])
        if 'scartati' not in session: session['scartati'] = []
        for n in df['Nome'].dropna().unique():
            if str(n).startswith(nome_t):
                if n not in session['scartati']: session['scartati'].append(n)
                break
        call.data = f"top_ruolo_{ruolo}"
        return handle_callbacks(call)

    # Gemme
    elif call.data == "menu_gemme":
        nomi_in_rosa = [p['nome'] for p in session['rosa']]
        scartati = session.get('scartati', [])
        
        df_liberi = df[(~df['Nome'].isin(nomi_in_rosa)) & (~df['Nome'].isin(scartati))].copy()
        col_base = 'FVM' if 'FVM' in df.columns else 'Qt.A'
        df_liberi['FVM_num'] = pd.to_numeric(df_liberi[col_base].astype(str).str.replace(',', '.').str.replace('-', '0'), errors='coerce').fillna(0)
        
        df_gemme = df_liberi[(df_liberi['FVM_num'] > 0) & (df_liberi['FVM_num'] <= 5)].sort_values(by='FVM_num', ascending=False).head(10)
        testo = "💎 *GEMME NASCOSTE LOW-COST*\n\n"
        markup = InlineKeyboardMarkup(row_width=1)
        for _, row in df_gemme.iterrows():
            testo += f"🔹 {ROLE_ICONS.get(row.get('R','C'),'')} *{row['Nome']}* ({row.get('Squadra','-')}) ─ FVM: `{row['FVM_num']}`\n"
            markup.add(InlineKeyboardButton(f"🔍 Info {row['Nome']}", callback_data=f"sq_pl_{row['Nome']}"))
        markup.add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text(testo, chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    # Scommesse & Cards
    elif call.data in ["menu_scommessa", "pesca_card_scommessa"]:
        nomi_in_rosa = [p['nome'] for p in session['rosa']]
        scartati = session.get('scartati', [])
        
        df_liberi = df[(~df['Nome'].isin(nomi_in_rosa)) & (~df['Nome'].isin(scartati))].copy()
        df_scommesse = df_liberi[df_liberi['Nome'].apply(lambda x: any(g in str(x).lower() for g in DATABASE_SCOMMESSE_PURE))].copy()

        if call.data == "pesca_card_scommessa":
            if df_scommesse.empty:
                bot.send_message(chat_id, "❌ Nessuna scommessa rimasta!")
                return
                
            scommessa = df_scommesse.sample(n=1).iloc[0]
            nome_p = str(scommessa['Nome']).upper()
            sq_p = str(scommessa.get('Squadra', '-'))
            r_p = str(scommessa.get('R', 'C'))
            fvm_p = str(scommessa.get('FVM', scommessa.get('Qt.A', '1-3')))
            
            id_val = None
            for col in scommessa.index:
                if str(col).strip().lower() in ['id', 'cod', 'codice']:
                    val_str = str(scommessa[col]).split('.')[0].strip()
                    if val_str.isdigit():
                        id_val = val_str
                        break

            testo_card = (
                f"🎴 *SPECIAL CARD: SCOMMESSA*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 *{nome_p}*\n"
                f"🛡️ Squadra: {get_team_icon(sq_p)} *{sq_p}*\n"
                f"📌 Ruolo: `{ROLE_ICONS.get(r_p, '')} {r_p}`\n"
                f"💰 Costo FVM: `{fvm_p}` cr.\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🔥 *SENTENZA:* _Puntalo a 1 credito prima degli altri!_"
            )

            markup = InlineKeyboardMarkup(row_width=2)
            markup.add(
                InlineKeyboardButton("⚡ Compra a 1 cr", callback_data=f"buy_{scommessa['Nome']}"),
                InlineKeyboardButton("🎲 Rilancia Card", callback_data="pesca_card_scommessa")
            )
            markup.add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))

            try: bot.delete_message(chat_id, call.message.message_id)
            except Exception: pass

            # Ottieni immagine garantita
            photo_stream = get_player_avatar_stream(nome_p, id_val, r_p)
            bot.send_photo(chat_id, photo_stream, caption=testo_card, parse_mode="Markdown", reply_markup=markup)

        else:
            testo = "🎲 *LE VERE SCOMMESSE*\nSolo profili ad alto potenziale:\n"
            markup = InlineKeyboardMarkup(row_width=1)
            markup.add(InlineKeyboardButton("🎴 Pesca una Card Scommessa", callback_data="pesca_card_scommessa"))
            markup.add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
            bot.edit_message_text(testo, chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    # Scheda Giocatore
    elif call.data.startswith("sq_pl_"):
        player_name = call.data.replace("sq_pl_", "")
        p_data = df[df['Nome'] == player_name].iloc[0]
        sq_name = p_data.get('Squadra', '-')
        r_p = p_data.get('R', 'C')
        
        id_val = None
        for col in p_data.index:
            if str(col).strip().lower() in ['id', 'cod', 'codice']:
                val_str = str(p_data[col]).split('.')[0].strip()
                if val_str.isdigit():
                    id_val = val_str
                    break
        
        info_text = (
            f"👤 *{player_name.upper()}* ({get_team_icon(sq_name)} {sq_name})\n"
            f"───────────────────────────\n"
            f"📌 Ruolo: `{r_p}`  │  ⭐ Slot: `{p_data.get('Slot', '-')}`\n"
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

        # Invia foto garantita + scheda
        photo_stream = get_player_avatar_stream(player_name, id_val, r_p)
        bot.send_photo(chat_id, photo_stream, caption=info_text, parse_mode="Markdown", reply_markup=markup)

    elif call.data.startswith("wl_toggle_"):
        player_name = call.data.replace("wl_toggle_", "")
        if 'wishlist' not in session: session['wishlist'] = []
        if player_name in session['wishlist']: session['wishlist'].remove(player_name)
        else: session['wishlist'].append(player_name)
        send_dashboard(chat_id, user_id, call.message.message_id)

    elif call.data == "menu_wishlist":
        wishlist = session.get('wishlist', [])
        markup = InlineKeyboardMarkup(row_width=1)
        if not wishlist: testo = "⭐ *WISHLIST VUOTA*"
        else:
            testo = "⭐ *LA TUA WISHLIST:*\n"
            for nome in wishlist: markup.add(InlineKeyboardButton(f"🔍 {nome}", callback_data=f"sq_pl_{nome}"))
        markup.add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text(testo, chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    # Esplora Squadre
    elif call.data == "sq_start":
        bot.edit_message_text("👕 *ESPLORA SQUADRE*", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=menu_seleziona_squadra(df, "sq"))
    elif call.data.startswith("sq_sq_"):
        bot.edit_message_text("Scegli il ruolo:", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=menu_seleziona_ruolo(call.data.replace("sq_sq_", ""), "sq"))
    elif call.data.startswith("sq_ru_"):
        _, _, sq, ru = call.data.split("_")
        bot.edit_message_text(f"Giocatori ({sq} - {ru}):", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=menu_seleziona_giocatore(df, sq, ru, "sq", user_id))

    # Area Svincoli
    elif call.data == "menu_svincola":
        if not session['rosa']:
            bot.send_message(chat_id, "❌ La tua rosa è vuota!")
            return
        markup = InlineKeyboardMarkup(row_width=1)
        for p in session['rosa']:
            markup.add(InlineKeyboardButton(f"✂️ Svincola {p['nome']} (+{p['prezzo']} cr)", callback_data=f"sv_{p['nome'][:20]}"))
        markup.add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text("✂️ *AREA SVINCOLI*\nClicca su un giocatore da tagliare:", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data.startswith("sv_"):
        nome_c = call.data.replace("sv_", "")
        for idx, p in enumerate(session['rosa']):
            if p['nome'].startswith(nome_c):
                session['budget'] += p['prezzo']
                session['rosa'].pop(idx)
                send_dashboard(chat_id, user_id, call.message.message_id)
                return

    elif call.data.startswith("buy_"):
        player_name = call.data.replace("buy_", "")
        msg = bot.send_message(chat_id, f"💰 Crediti spesi per *{player_name}*?:", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_buy_price, player_name, user_id)

@bot.message_handler(content_types=['document'])
def handle_document(message):
    chat_id = message.chat.id
    if not message.document.file_name.endswith('.xlsx'):
        bot.reply_to(message, "❌ Invia solo file `.xlsx`!", parse_mode="Markdown")
        return
    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        with open("listone.xlsx", 'wb') as new_file:
            new_file.write(downloaded_file)
        load_data(force_reload=True)
        bot.reply_to(message, "✅ *DATABASE AGGIORNATO CON SUCCESSO!*", parse_mode="Markdown")
    except Exception as e:
        bot.send_message(chat_id, f"❌ Errore durante l'aggiornamento: {str(e)}")

if __name__ == '__main__':
    try: bot.remove_webhook()
    except Exception: pass
    bot.infinity_polling(timeout=10, long_polling_timeout=5, skip_pending=True)
