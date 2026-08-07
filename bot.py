import os
import io
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ⚠️ IL TUO TOKEN TELEGRAM ⚠️ (Inserisci il tuo vero token qui)
TOKEN = "8969898580:AAHxI0_LK57bhCTP_TNYLKubhEU3a0yEg0Y"
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

# Algoritmo incroci Casa/Trasferta perfetti
BEST_PAIRS = {
    'Inter': ['Venezia', 'Napoli', 'Lecce'], 'Juventus': ['Torino', 'Empoli', 'Parma'],
    'Milan': ['Monza', 'Como', 'Genoa'], 'Atalanta': ['Bologna', 'Udinese', 'Verona'],
    'Napoli': ['Inter', 'Roma', 'Fiorentina'], 'Roma': ['Lazio', 'Napoli'],
    'Lazio': ['Roma', 'Milan'], 'Fiorentina': ['Empoli', 'Bologna', 'Napoli'],
    'Torino': ['Juventus', 'Genoa', 'Como'], 'Bologna': ['Atalanta', 'Fiorentina']
}

def get_team_icon(squadra): 
    return TEAM_COLORS.get(str(squadra).strip(), '🛡️')

DATA_CACHE = None
def load_data(force_reload=False):
    global DATA_CACHE
    if DATA_CACHE is None or force_reload:
        if os.path.exists("listone.xlsx"): 
            DATA_CACHE = pd.read_excel("listone.xlsx", header=1, engine='openpyxl')
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
        InlineKeyboardButton("✂️ Svincola", callback_data="menu_svincola")
    )
    markup.add(
        InlineKeyboardButton("📊 Area Studio", callback_data="menu_studio"),
        InlineKeyboardButton("🔄 Sync Dati", callback_data="reload_excel")
    )
    markup.add(
        InlineKeyboardButton("⚠️ Reset Rosa", callback_data="reset_confirm"),
        InlineKeyboardButton("🧹 Pulisci", callback_data="clear_screen")
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
        f" *FANTABOT PRO DASHBOARD*\n───────────────────────────\n"
        f"💳 *BILANCIO ASTA*\n"
        f"• Budget Rimanente: `{session['budget']}` cr.\n"
        f"• Giocatori Presi: `{25 - stats['slot_liberi']}/25`\n"
        f"• *Max Bid Sicuro:* `{stats['max_bid']}` cr.\n"
        f"• Termometro Asta: {termometro}\n\n"
        f"📊 *COPERTURA ROSTER*\n"
        f"🧤 `Portieri`   `[{generate_progress_bar(c['P'], 3, 6)}]` `{c['P']}/3`\n"
        f"🛡️ `Difensori`  `[{generate_progress_bar(c['D'], 8, 6)}]` `{c['D']}/8`\n"
        f"⚙️ `Centrocampi` `[{generate_progress_bar(c['C'], 8, 6)}]` `{c['C']}/8`\n"
        f"🎯 `Attaccanti`  `[{generate_progress_bar(c['A'], 6, 6)}]` `{c['A']}/6`\n"
        f"───────────────────────────\n💡 _Cerca nome o scrivi `+ nome prezzo` per comprare al volo!_\n"
    )
    if message_id:
        try: bot.edit_message_text(text, chat_id, message_id, parse_mode="Markdown", reply_markup=main_menu_keyboard())
        except Exception: bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=main_menu_keyboard())
    else: 
        bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=main_menu_keyboard())

# --- MODALITÀ CECCHINO (ACQUISTO INLINE VELOCE) ---
@bot.message_handler(func=lambda m: m.text.strip().startswith('+'))
def modalita_cecchino(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = message.text.strip()[1:].strip() # Rimuove il '+'
    
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
            
        row = matches.iloc[0] # Prende il miglior match
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
        
        # Oracolo Incroci per P e D
        if ruolo_acquistato in ['P', 'D']:
            accoppiamenti = BEST_PAIRS.get(sq_acquistata, [])
            if accoppiamenti:
                bot.send_message(chat_id, f"💡 **L'ORACOLO DELLA DIFESA** 💡\nHai preso un {ruolo_acquistato} del *{sq_acquistata}*.\nIncroci casa/trasferta perfetti: **{', '.join(accoppiamenti)}**.", parse_mode="Markdown")
                
    except Exception as e:
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

    if ruolo_acquistato in ['P', 'D']:
        accoppiamenti = BEST_PAIRS.get(squadra_acquistata, [])
        if accoppiamenti:
            bot.send_message(chat_id, f"💡 **L'ORACOLO DELLA DIFESA** 💡\nHai preso un {ruolo_acquistato} del *{squadra_acquistata}*.\nIncroci casa/trasferta perfetti: **{', '.join(accoppiamenti)}**.", parse_mode="Markdown")


@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    session = get_session(user_id)
    df = load_data()

    if call.data == "clear_screen":
        bot.answer_callback_query(call.id, "🧹 Pulizia in corso...")
        curr_id = call.message.message_id
        for i in range(curr_id, max(0, curr_id - 80), -1):
            try: bot.delete_message(chat_id, i)
            except Exception: pass
        send_dashboard(chat_id, user_id)

    elif call.data == "go_home": 
        bot.answer_callback_query(call.id)
        send_dashboard(chat_id, user_id, call.message.message_id)
        
    elif call.data == "reload_excel": 
        load_data(force_reload=True)
        bot.answer_callback_query(call.id, "⚡ Dati sincronizzati!")
        
    elif call.data == "reset_confirm":
        bot.answer_callback_query(call.id)
        user_sessions[user_id] = {'budget': 500, 'rosa': [], 'selected_for_compare': [], 'wishlist': session.get('wishlist', []), 'scartati': []}
        send_dashboard(chat_id, user_id, call.message.message_id)

    # --- PANIC BUTTON (SCARTI TITOLARI A 1-2 CR) ---
    elif call.data == "menu_panic":
        bot.answer_callback_query(call.id)
        markup = InlineKeyboardMarkup(row_width=4)
        markup.add(
            InlineKeyboardButton("🧤 P", callback_data="panic_ruolo_P"),
            InlineKeyboardButton("🛡️ D", callback_data="panic_ruolo_D"),
            InlineKeyboardButton("⚙️ C", callback_data="panic_ruolo_C"),
            InlineKeyboardButton("🎯 A", callback_data="panic_ruolo_A")
        )
        markup.add(InlineKeyboardButton("🔙 Home", callback_data="go_home"))
        bot.edit_message_text("🚨 *PANIC BUTTON ATTIVATO*\nTi mancano crediti? Scegli un ruolo per trovare i migliori disperati a bassissimo costo!", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data.startswith("panic_ruolo_"):
        bot.answer_callback_query(call.id)
        ruolo = call.data.split("_")[-1]
        
        nomi_in_rosa = [p['nome'] for p in session['rosa']]
        scartati = session.get('scartati', [])
        
        df['Valore_Ord'] = pd.to_numeric(df['FVM' if 'FVM' in df.columns else 'Qt.A'].astype(str).str.replace(',', '.').str.replace('-', '0'), errors='coerce').fillna(0)
        df['FM_Ord'] = pd.to_numeric(df['FM'].astype(str).str.replace(',', '.').str.replace('-', '0'), errors='coerce').fillna(0)
        
        # Cerca giocatori economici (FVM <= 3) non presi, ordinati per fanta media
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

    # --- SIMULATORE FORMAZIONE TIPO ---
    elif call.data == "menu_formazione":
        bot.answer_callback_query(call.id, "Simulazione tattica in corso...")
        rosa = session['rosa']
        if len(rosa) < 11:
            return bot.answer_callback_query(call.id, "Acquista almeno 11 giocatori prima di schierare la formazione!", show_alert=True)
            
        por = sorted([p for p in rosa if p['ruolo'] == 'P'], key=lambda x: x['fm'], reverse=True)
        dif = sorted([p for p in rosa if p['ruolo'] == 'D'], key=lambda x: x['fm'], reverse=True)
        cen = sorted([p for p in rosa if p['ruolo'] == 'C'], key=lambda x: x['fm'], reverse=True)
        att = sorted([p for p in rosa if p['ruolo'] == 'A'], key=lambda x: x['fm'], reverse=True)
        
        if not por or len(dif) < 3 or len(cen) < 3 or len(att) < 1:
            bot.edit_message_text("❌ *Impossibile calcolare il Modulo*\nTi mancano giocatori fondamentali in qualche reparto.", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🏠 Home", callback_data="go_home")))
            return

        # Proviamo il 3-4-3 standard, o ci adattiamo
        schema = f"3-{min(4, len(cen))}-{min(3, len(att))}"
        
        testo = f"⚽ *LA TUA FORMAZIONE TIPO ({schema})*\nCalcolata in base alla FantaMedia attuale:\n\n"
        testo += f"🧤 *P:* {por[0]['nome']} ({por[0]['squadra']})\n"
        testo += f"🛡️ *D:* " + " - ".join([p['nome'] for p in dif[:3]]) + "\n"
        testo += f"⚙️ *C:* " + " - ".join([p['nome'] for p in cen[:int(schema.split('-')[1])]]) + "\n"
        testo += f"🎯 *A:* " + " - ".join([p['nome'] for p in att[:int(schema.split('-')[2])]]) + "\n\n"
        
        # Consigli tattici
        if len(att) < 3: testo += "⚠️ *Allarme:* Ti mancano punte per un tridente, compra attaccanti!\n"
        if len(dif) > 0 and dif[0]['fm'] < 6: testo += "⚠️ *Allarme:* La tua difesa ha una fanta-media troppo bassa.\n"
        
        bot.edit_message_text(testo, chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🏠 Home", callback_data="go_home")))

    # --- MATRICE PERFETTA (IN LA MIA ROSA) ---
    elif call.data == "menu_rosa":
        bot.answer_callback_query(call.id)
        rosa = session['rosa']
        
        slot_counters = {'1': 0, '2': 0, '3': 0, '4+': 0}
        rigoristi = 0
        difensori_fm = []
        for p in rosa:
            if 'R1' in p.get('rigori', '') or 'R2' in p.get('rigori', ''): rigoristi += 1
            if p['ruolo'] == 'D' and p.get('fm', 0) > 0: difensori_fm.append(p['fm'])
            
            s = str(p.get('slot', '8'))
            if '1' in s: slot_counters['1'] += 1
            elif '2' in s: slot_counters['2'] += 1
            elif '3' in s: slot_counters['3'] += 1
            else: slot_counters['4+'] += 1
            
        media_dif = np.mean(difensori_fm) if difensori_fm else 0

        text = (
            f"📋 *LA MIA ROSA (MATRICE)*\n───────────────────────────\n"
            f"💰 *Budget Residuo:* `{session['budget']}` cr.\n"
            f"⚽ *Rigoristi presi:* `{rigoristi}`\n"
            f"🧱 *FM Media Difesa:* `{media_dif:.2f}`\n\n"
            f"🧩 *ANALISI SLOT:*\n"
            f"🥇 1° Slot (Top): `{slot_counters['1']}`\n"
            f"🥈 2° Slot (Semi-Top): `{slot_counters['2']}`\n"
            f"🥉 3° Slot (Titolari): `{slot_counters['3']}`\n"
            f"📦 4+ Slot (Scommesse): `{slot_counters['4+']}`\n\n"
        )
        if not rosa: text += "_Nessun calciatore in rosa._"
        else:
            for idx, p in enumerate(rosa, 1): text += f"`{idx:02d}.` {ROLE_ICONS.get(p.get('ruolo','C'), '👤')} *{p['nome']}* ── `{p['prezzo']} cr.`\n"
        
        markup = InlineKeyboardMarkup(row_width=2)
        if rosa:
            markup.add(InlineKeyboardButton("🥧 Torta Budget", callback_data="chart_budget"), InlineKeyboardButton("🕸️ Radar Rosa", callback_data="radar_rosa"))
            markup.add(InlineKeyboardButton("📸 Esporta Recap", callback_data="export_roster"))
        markup.add(InlineKeyboardButton("🔙 Home", callback_data="go_home"))
        bot.edit_message_text(text, chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    # --- TOP LIBERI (METODO TINDER) AUMENTATI A 15 ---
    elif call.data == "menu_top":
        bot.answer_callback_query(call.id)
        markup = InlineKeyboardMarkup(row_width=4)
        markup.add(
            InlineKeyboardButton("🧤 P", callback_data="top_ruolo_P"),
            InlineKeyboardButton("🛡️ D", callback_data="top_ruolo_D"),
            InlineKeyboardButton("⚙️ C", callback_data="top_ruolo_C"),
            InlineKeyboardButton("🎯 A", callback_data="top_ruolo_A")
        )
        markup.add(InlineKeyboardButton("🔙 Home", callback_data="go_home"))
        bot.edit_message_text("🏆 *TOP LIBERI*\nDi quale ruolo vuoi vedere i migliori giocatori ancora disponibili?", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data.startswith("top_ruolo_"):
        bot.answer_callback_query(call.id)
        ruolo = call.data.split("_")[-1]
        
        nomi_in_rosa = [p['nome'] for p in session['rosa']]
        scartati = session.get('scartati', [])
        
        colonna_base = 'FVM' if 'FVM' in df.columns else 'Qt.A'
        df['Valore_Ord'] = df[colonna_base].astype(str).str.replace(',', '.').str.replace('-', '0')
        df['Valore_Ord'] = pd.to_numeric(df['Valore_Ord'], errors='coerce').fillna(0)
        
        df_liberi = df[(df['R'] == ruolo) & (~df['Nome'].isin(nomi_in_rosa)) & (~df['Nome'].isin(scartati))]
        df_top = df_liberi.sort_values(by='Valore_Ord', ascending=False).head(15)
        
        testo = f"🏆 *MIGLIORI {ROLE_ICONS.get(ruolo, '')} ANCORA LIBERI*\n\n"
        markup = InlineKeyboardMarkup(row_width=2)
        
        if df_top.empty: 
            testo += "_Nessun giocatore rimasto in questo ruolo._"
        else:
            for _, row in df_top.iterrows():
                nome = row['Nome']
                testo += f"🔹 *{nome}* ({row.get('Squadra','-')}) ─ FVM: `{row['Valore_Ord']}`\n"
                markup.row(
                    InlineKeyboardButton(f"🔍 Info {nome[:10]}", callback_data=f"sq_pl_{nome}"),
                    InlineKeyboardButton(f"❌ Scarta", callback_data=f"dsc_{ruolo}_{nome[:20]}")
                )
                
        markup.add(InlineKeyboardButton("🔙 Torna ai Ruoli", callback_data="menu_top"))
        markup.add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text(testo, chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data.startswith("dsc_"):
        parts = call.data.split("_")
        ruolo = parts[1]
        nome_troncato = "_".join(parts[2:])
        
        if 'scartati' not in session: session['scartati'] = []
            
        for n in df['Nome'].dropna().unique():
            if str(n).startswith(nome_troncato):
                if n not in session['scartati']:
                    session['scartati'].append(n)
                break
                
        bot.answer_callback_query(call.id, "❌ Giocatore scartato! Rimosso dalla lista.")
        call.data = f"top_ruolo_{ruolo}"
        return handle_callbacks(call)

    # --- GEMME NASCOSTE AUMENTATE A 15 ---
    elif call.data == "menu_gemme":
        bot.answer_callback_query(call.id)
        nomi_in_rosa = [p['nome'] for p in session['rosa']]
        scartati = session.get('scartati', [])
        
        colonna_base = 'FVM' if 'FVM' in df.columns else 'Qt.A'
        df['Valore_Gemma'] = df[colonna_base].astype(str)
        df['Valore_Gemma'] = df['Valore_Gemma'].str.replace(',', '.').str.replace('-', '0')
        df['Valore_Gemma'] = pd.to_numeric(df['Valore_Gemma'], errors='coerce').fillna(0)
        
        df_gemme = df[(~df['Nome'].isin(nomi_in_rosa)) & (~df['Nome'].isin(scartati)) & (df['Valore_Gemma'] > 0) & (df['Valore_Gemma'] <= 5)]
        df_gemme = df_gemme.sort_values(by='Valore_Gemma', ascending=False).head(15)
        
        testo_gemme = "💎 *GEMME NASCOSTE*\nGiocatori a 5 crediti o meno, ideali per completare la rosa:\n\n"
        markup = InlineKeyboardMarkup(row_width=1)
        
        if df_gemme.empty: 
            testo_gemme += "_Nessuna gemma trovata. I valori nel tuo Excel superano tutti i 5 crediti._"
        else:
            for _, row in df_gemme.iterrows():
                testo_gemme += f"🔹 {ROLE_ICONS.get(row.get('R','C'),'')} *{row['Nome']}* ({row.get('Squadra','-')}) ─ Valore: `{row['Valore_Gemma']}`\n"
                markup.add(InlineKeyboardButton(f"🔍 Info {row['Nome']}", callback_data=f"sq_pl_{row['Nome']}"))
                
        markup.add(InlineKeyboardButton("🏠 Torna alla Home", callback_data="go_home"))
        bot.edit_message_text(testo_gemme, chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "radar_rosa":
        bot.answer_callback_query(call.id)
        if not session['rosa']: return
        spese = {'P': 0, 'D': 0, 'C': 0, 'A': 0}
        for p in session['rosa']: spese[p['ruolo']] += p['prezzo']
        
        p_score, d_score = min(10, max(1, (spese['P'] / 40) * 10)), min(10, max(1, (spese['D'] / 80) * 10))
        c_score, a_score = min(10, max(1, (spese['C'] / 150) * 10)), min(10, max(1, (spese['A'] / 230) * 10))
        b_score = min(10, max(1, (session['budget'] / max(1, ((25 - len(session['rosa'])) * 20))) * 5))
        
        labels, stats = np.array(['Attacco', 'Centrocampo', 'Difesa', 'Porta', 'Salute Budget']), np.array([a_score, c_score, d_score, p_score, b_score])
        angles = np.linspace(0, 2*np.pi, len(labels), endpoint=False).tolist()
        stats, angles = np.concatenate((stats,[stats[0]])), angles + angles[:1]
        
        fig, ax = plt.subplots(figsize=(6, 6), subplot_kw=dict(polar=True))
        ax.fill(angles, stats, color='#3498db', alpha=0.4); ax.plot(angles, stats, color='#2980b9', linewidth=2)
        ax.set_yticklabels([]); ax.set_xticks(angles[:-1]); ax.set_xticklabels(labels, fontsize=12, fontweight='bold', color='#2c3e50')
        ax.set_ylim(0, 10); ax.set_title("Scout Report: Potenza della Rosa", y=1.1, fontsize=15, fontweight='bold')
        
        buf = io.BytesIO(); plt.savefig(buf, format='png', bbox_inches='tight', dpi=120); buf.seek(0); plt.close(fig)
        bot.send_photo(chat_id, buf, caption="🕸️ *Analisi Radar della tua Rosa*", parse_mode="Markdown")

    elif call.data == "chart_budget":
        bot.answer_callback_query(call.id)
        if not session['rosa']: return
        spese = {'P': 0, 'D': 0, 'C': 0, 'A': 0}
        for p in session['rosa']: spese[p['ruolo']] += p['prezzo']
        
        labels, sizes, colors = ['Portieri', 'Difensori', 'Centrocampisti', 'Attaccanti', 'Residuo'], [spese['P'], spese['D'], spese['C'], spese['A'], session['budget']], ['#f39c12', '#3498db', '#2ecc71', '#e74c3c', '#95a5a6']
        lbl_f, sz_f, col_f = zip(*[(l, s, c) for l, s, c in zip(labels, sizes, colors) if s > 0])
        
        fig, ax = plt.subplots(figsize=(6, 6))
        ax.pie(sz_f, labels=lbl_f, colors=col_f, autopct='%1.1f%%', startangle=140, wedgeprops={'edgecolor': 'white', 'linewidth': 2})
        ax.set_title('Distribuzione Budget Fantacalcio', fontweight='bold')
        
        buf = io.BytesIO(); plt.savefig(buf, format='png', bbox_inches='tight', dpi=120); buf.seek(0); plt.close(fig)
        bot.send_photo(chat_id, buf, caption="📊 *Distribuzione Budget*", parse_mode="Markdown")

    elif call.data == "export_roster":
        bot.answer_callback_query(call.id)
        if not session['rosa']: return
        rosa = session['rosa']
        fig, ax = plt.subplots(figsize=(8, 10)); ax.axis('off')
        
        y_pos = 0.95
        ax.text(0.5, y_pos, "LA MIA ROSA - FANTACALCIO", fontsize=22, weight='bold', ha='center', color='#2c3e50')
        y_pos -= 0.05
        ax.text(0.5, y_pos, f"Budget Rimanente: {session['budget']} cr. | Giocatori: {len(rosa)}/25", fontsize=14, ha='center', color='#7f8c8d')
        
        role_colors, role_names = {'P': '#f39c12', 'D': '#3498db', 'C': '#2ecc71', 'A': '#e74c3c'}, {'P': 'PORTIERI', 'D': 'DIFENSORI', 'C': 'CENTROCAMPISTI', 'A': 'ATTACCANTI'}
        
        y_pos -= 0.08
        for r in ['P', 'D', 'C', 'A']:
            giocatori = [p for p in rosa if p['ruolo'] == r]
            if giocatori:
                ax.text(0.1, y_pos, role_names[r], fontsize=15, weight='bold', color=role_colors[r]); y_pos -= 0.035
                for p in giocatori:
                    ax.text(0.15, y_pos, f"• {p['nome']} ({p['squadra']})", fontsize=13)
                    ax.text(0.85, y_pos, f"{p['prezzo']} cr.", fontsize=13, ha='right', weight='bold')
                    y_pos -= 0.03
                y_pos -= 0.02
                
        buf = io.BytesIO(); plt.savefig(buf, format='png', bbox_inches='tight', dpi=150, facecolor='#f8f9fa'); buf.seek(0); plt.close(fig)
        bot.send_photo(chat_id, buf, caption="📸 *Roster Ufficiale Generato!*", parse_mode="Markdown")

    # --- SCHEDA GIOCATORE CON TASTO WISHLIST E SLOTS ---
    elif call.data.startswith("sq_pl_"):
        bot.answer_callback_query(call.id)
        player_name = call.data.replace("sq_pl_", "")
        p_data = df[df['Nome'] == player_name].iloc[0]
        
        fvm_str = str(p_data.get('FVM', '0')).replace(',', '.').replace('-', '0')
        fvm = pd.to_numeric(fvm_str, errors='coerce')
        if pd.isna(fvm): fvm = 0
            
        sq_name = p_data.get('Squadra', '-')
        stats = get_roster_stats(session)
        consiglio_bid = min(stats['max_bid'], int((session['budget'] * 0.3) + (fvm * 0.7)))
        
        info_text = (
            f"👤 *{player_name.upper()}* ({get_team_icon(sq_name)} {sq_name})\n"
            f"───────────────────────────\n"
            f"📌 Ruolo: `{p_data.get('R', '-')}`  │  ⭐ Slot: `{p_data.get('Slot', '-')}`\n"
            f"🏅 *Fascia:* `{p_data.get('Fascia', '-')}`\n"
            f"📈 Fantamedia: `{p_data.get('FM', '-')}`\n"
            f"💰 Quotazione: `{p_data.get('Qt.A', '-')}` cr.  │  FVM: `{p_data.get('FVM', '-')}` cr.\n\n"
            f"🔬 *SCOUTING REPORT*\n"
            f"🪖 Titolarità: `{p_data.get('Titolarita', '-')}`\n"
            f"👟 Rigori/Piazzati: `{p_data.get('Rigori_Piazzati', '-')}`\n"
            f"🏥 Infortuni: `{p_data.get('Infortuni', '-')}`\n"
            f"🟨 Malus: `{p_data.get('Malus', '-')}`\n"
            f"───────────────────────────\n"
            f"💡 *Consiglio Bid:* Non superare i `{consiglio_bid}` cr.\n"
        )
        
        in_wishlist = player_name in session.get('wishlist', [])
        wl_text = "❌ Rimuovi da Wishlist" if in_wishlist else "⭐ Aggiungi a Wishlist"
        
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("⚡ Compra", callback_data=f"buy_{player_name}"), 
            InlineKeyboardButton("🔄 Piano B", callback_data=f"alt_{player_name}")
        )
        markup.add(InlineKeyboardButton(wl_text, callback_data=f"wl_toggle_{player_name}"))
        markup.add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        
        bot.edit_message_text(info_text, chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    # --- TOGGLE WISHLIST ---
    elif call.data.startswith("wl_toggle_"):
        player_name = call.data.replace("wl_toggle_", "")
        if 'wishlist' not in session: session['wishlist'] = []
            
        if player_name in session['wishlist']:
            session['wishlist'].remove(player_name)
            bot.answer_callback_query(call.id, f"🗑️ {player_name} rimosso dalla Wishlist!", show_alert=True)
        else:
            session['wishlist'].append(player_name)
            bot.answer_callback_query(call.id, f"⭐ {player_name} aggiunto alla Wishlist!", show_alert=True)
        send_dashboard(chat_id, user_id, call.message.message_id)

    elif call.data.startswith("alt_"):
        bot.answer_callback_query(call.id)
        player_name = call.data.replace("alt_", "")
        try:
            p_data = df[df['Nome'] == player_name].iloc[0]
            ruolo = p_data.get('R', 'C')
            fvm_str = str(p_data.get('FVM', '10')).replace(',', '.').replace('-', '0')
            fvm_target = pd.to_numeric(fvm_str, errors='coerce')
            
            nomi_in_rosa = [p['nome'] for p in session['rosa']]
            scartati = session.get('scartati', [])
            
            alternative = df[(df['R'] == ruolo) & (~df['Nome'].isin(nomi_in_rosa)) & (~df['Nome'].isin(scartati)) & (df['Nome'] != player_name)].copy()
            alternative['FVM_num'] = pd.to_numeric(alternative['FVM'].astype(str).str.replace(',', '.').str.replace('-', '0'), errors='coerce').fillna(0)
            migliori_alternative = alternative[alternative['FVM_num'] <= (fvm_target + 5)].sort_values(by='FVM_num', ascending=False).head(3)
            
            if migliori_alternative.empty: 
                return bot.answer_callback_query(call.id, "Nessuna alternativa trovata!", show_alert=True)
            
            testo_alt = f"🚨 *PIANO B INNESCATO*\nEcco le migliori 3 alternative libere nello stesso ruolo:\n\n"
            markup = InlineKeyboardMarkup(row_width=1)
            for _, row in migliori_alternative.iterrows():
                testo_alt += f"🔹 {ROLE_ICONS.get(ruolo,'')} *{row['Nome']}* ({row['Squadra']}) ─ FVM: `{row['FVM']}`\n"
                markup.add(InlineKeyboardButton(f"🔍 Analizza {row['Nome']}", callback_data=f"sq_pl_{row['Nome']}"))
            markup.add(InlineKeyboardButton("🏠 Torna alla Home", callback_data="go_home"))
            bot.edit_message_text(testo_alt, chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
        except Exception: 
            bot.answer_callback_query(call.id, "Errore nel calcolo delle alternative.")

    elif call.data == "sq_start": 
        bot.answer_callback_query(call.id)
        bot.edit_message_text("👕 *ESPLORA SQUADRE*", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=menu_seleziona_squadra(df, "sq"))
    elif call.data.startswith("sq_sq_"): 
        bot.answer_callback_query(call.id)
        bot.edit_message_text("Scegli il ruolo da esplorare:", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=menu_seleziona_ruolo(call.data.replace("sq_sq_", ""), "sq"))
    elif call.data.startswith("sq_ru_"): 
        bot.answer_callback_query(call.id)
        _, _, sq, ru = call.data.split("_")
        bot.edit_message_text(f"Seleziona un giocatore ({sq} - {ru}):", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=menu_seleziona_giocatore(df, sq, ru, "sq", user_id))

    elif call.data in ["menu_studio", "cmp1_start"]: 
        bot.answer_callback_query(call.id)
        bot.edit_message_text("📊 *AREA STUDIO*\n\nSeleziona la squadra del *1° Giocatore*:", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=menu_seleziona_squadra(df, "cmp1"))
    elif call.data.startswith("cmp1_sq_"): 
        bot.answer_callback_query(call.id)
        bot.edit_message_text("Scegli il ruolo del *1° Giocatore*:", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=menu_seleziona_ruolo(call.data.replace("cmp1_sq_", ""), "cmp1"))
    elif call.data.startswith("cmp1_ru_"): 
        bot.answer_callback_query(call.id)
        _, _, sq, ru = call.data.split("_")
        bot.edit_message_text(f"Seleziona il *1° Giocatore* ({ru}):", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=menu_seleziona_giocatore(df, sq, ru, "cmp1", user_id))
    elif call.data.startswith("cmp1_pl_"):
        bot.answer_callback_query(call.id)
        session['selected_for_compare'] = [call.data.replace("cmp1_pl_", "")]
        bot.edit_message_text(f"✅ 1° Gioc: *{session['selected_for_compare'][0]}*\n\nSeleziona la squadra del *2° Giocatore*:", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=menu_seleziona_squadra(df, "cmp2"))
    elif call.data.startswith("cmp2_sq_"):
        bot.answer_callback_query(call.id)
        ruolo_p1 = df[df['Nome'] == session['selected_for_compare'][0]].iloc[0].get('R', 'C')
        bot.edit_message_text(f"Seleziona il *2° Giocatore* (Filtro Ruolo: {ruolo_p1}):", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=menu_seleziona_giocatore(df, call.data.replace("cmp2_sq_", ""), ruolo_p1, "cmp2", user_id))
    elif call.data.startswith("cmp2_pl_"):
        bot.answer_callback_query(call.id)
        p2_name, p1_name = call.data.replace("cmp2_pl_", ""), session['selected_for_compare'][0]
        p1_data, p2_data = df[df['Nome'] == p1_name].iloc[0], df[df['Nome'] == p2_name].iloc[0]
        session['selected_for_compare'] = []

        testo_confronto = (
            f"📊 *COMPARAZIONE DIRETTA*\n🏆 *{p1_name.upper()}* vs *{p2_name.upper()}*\n───────────────────────────\n"
            f"📈 *FantaMedia:* `{p1_data.get('FM', '-')}` 🆚 `{p2_data.get('FM', '-')}`\n\n"
            f"🏅 *Fascia:*\n• {p1_name}: {get_team_icon(p1_data.get('Squadra',''))} `{p1_data.get('Fascia', '-')}`\n• {p2_name}: {get_team_icon(p2_data.get('Squadra',''))} `{p2_data.get('Fascia', '-')}`\n\n"
        )
        
        fig, ax = plt.subplots(figsize=(8, 5))
        
        p1_qta = pd.to_numeric(str(p1_data.get('Qt.A', '0')).replace(',', '.').replace('-', '0'), errors='coerce')
        p1_fvm = pd.to_numeric(str(p1_data.get('FVM', '0')).replace(',', '.').replace('-', '0'), errors='coerce')
        p2_qta = pd.to_numeric(str(p2_data.get('Qt.A', '0')).replace(',', '.').replace('-', '0'), errors='coerce')
        p2_fvm = pd.to_numeric(str(p2_data.get('FVM', '0')).replace(',', '.').replace('-', '0'), errors='coerce')
        
        p1_vals = [float(p1_qta or 0), float(p1_fvm or 0)]
        p2_vals = [float(p2_qta or 0), float(p2_fvm or 0)]
        
        x, width = range(len(p1_vals)), 0.35
        ax.bar([i - width/2 for i in x], p1_vals, width, label=p1_name, color='#1f77b4')
        ax.bar([i + width/2 for i in x], p2_vals, width, label=p2_name, color='#ff7f0e')
        ax.set_ylabel('Crediti'); ax.set_title(f'{p1_name} vs {p2_name}')
        ax.set_xticks(x); ax.set_xticklabels(['Quotazione', 'FVM'])
        ax.legend(); plt.grid(axis='y', alpha=0.7)
        
        buf = io.BytesIO(); plt.savefig(buf, format='png', bbox_inches='tight', dpi=100); buf.seek(0); plt.close(fig)
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(f"➕ Prendi {p1_name[:8]}", callback_data=f"buy_{p1_name}"), InlineKeyboardButton(f"➕ Prendi {p2_name[:8]}", callback_data=f"buy_{p2_name}"))
        markup.add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        
        bot.delete_message(chat_id, call.message.message_id)
        bot.send_photo(chat_id, buf, caption=testo_confronto, parse_mode="Markdown", reply_markup=markup)

    elif call.data.startswith("buy_"):
        bot.answer_callback_query(call.id) 
        player_name = call.data.replace("buy_", "")
        msg = bot.send_message(chat_id, f"💰 A quanti crediti hai acquistato *{player_name}*?\n_Scrivi un numero (es. 15):_", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_buy_price, player_name, user_id)
        
    elif call.data.startswith("undo_"):
        bot.answer_callback_query(call.id)
        player_name = call.data.replace("undo_", "")
        for idx, p in enumerate(session['rosa']):
            if p['nome'] == player_name: 
                session['budget'] += session['rosa'].pop(idx)['prezzo']
                send_dashboard(chat_id, user_id)
                return

    # --- MENU SVINCOLI ---
    elif call.data == "menu_svincola":
        if not session['rosa']: 
            return bot.answer_callback_query(call.id, "❌ La tua rosa è vuota!", show_alert=True)
            
        bot.answer_callback_query(call.id)
        markup = InlineKeyboardMarkup(row_width=1)
        for p in session['rosa']:
            markup.add(InlineKeyboardButton(f"✂️ Svincola {p['nome']} (+{p['prezzo']} cr)", callback_data=f"sv_{p['nome'][:20]}"))
        markup.add(InlineKeyboardButton("🔙 Home", callback_data="go_home"))
        
        bot.edit_message_text("✂️ *AREA SVINCOLI*\nClicca su un giocatore per tagliarlo e recuperare i crediti spesi:", 
                              chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data.startswith("sv_"):
        nome_cercato = call.data.replace("sv_", "")
        for idx, p in enumerate(session['rosa']):
            if p['nome'].startswith(nome_cercato): 
                session['budget'] += p['prezzo']
                session['rosa'].pop(idx)
                bot.answer_callback_query(call.id, f"✅ Svincolato! Recuperati {p['prezzo']} cr.", show_alert=True)
                send_dashboard(chat_id, user_id, call.message.message_id)
                return

    # --- MENU WISHLIST ---
    elif call.data == "menu_wishlist":
        bot.answer_callback_query(call.id)
        wishlist = session.get('wishlist', [])
        markup = InlineKeyboardMarkup(row_width=1)
        
        if not wishlist:
            testo = "⭐ *LA TUA WISHLIST È VUOTA*\n\n_Cerca un giocatore nella chat e clicca su 'Aggiungi a Wishlist' nella sua scheda per tenerlo d'occhio durante l'asta!_"
        else:
            testo = "⭐ *LA TUA WISHLIST*\nClicca su un giocatore per aprire la sua scheda e acquistarlo:\n"
            for nome in wishlist:
                markup.add(InlineKeyboardButton(f"🔍 Scheda di {nome}", callback_data=f"sq_pl_{nome}"))
                
        markup.add(InlineKeyboardButton("🔙 Home", callback_data="go_home"))
        bot.edit_message_text(testo, chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

if __name__ == '__main__':
    print("🤖 Pulizia vecchie connessioni in corso...")
    try: 
        bot.remove_webhook() 
    except Exception: 
        pass
    print("🚀 FantaBot Pro Ready (God Mode v4.0)...")
    bot.infinity_polling(timeout=10, long_polling_timeout=5, skip_pending=True)
