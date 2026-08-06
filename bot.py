import os
import io
import pandas as pd
import matplotlib
matplotlib.use('Agg') # Fondamentale per i server cloud come Render
import matplotlib.pyplot as plt
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# IL TUO TOKEN TELEGRAM
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

def get_team_icon(squadra): return TEAM_COLORS.get(str(squadra).strip(), '🛡️')

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
        user_sessions[user_id] = {'budget': 500, 'rosa': [], 'selected_for_compare': [], 'wishlist': []}
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
        if r in counts: counts[r] += 1
            
    slot_liberi = max(0, 25 - len(rosa))
    max_bid = max(0, budget - (slot_liberi - 1)) if slot_liberi > 0 else budget
    return {'counts': counts, 'slot_liberi': slot_liberi, 'max_bid': max_bid}

def main_menu_keyboard():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("👕 Esplora", callback_data="sq_start"),
        InlineKeyboardButton("📋 La mia Rosa", callback_data="menu_rosa"),
        InlineKeyboardButton("📊 Area Studio", callback_data="menu_studio"),
        InlineKeyboardButton("🔥 Top Rimasti", callback_data="menu_top")
    )
    markup.add(
        InlineKeyboardButton("⭐ Wishlist", callback_data="menu_wishlist"),
        InlineKeyboardButton("❌ Svincola", callback_data="menu_svincola")
    )
    markup.add(
        InlineKeyboardButton("🔄 Sync Dati", callback_data="reload_excel"),
        InlineKeyboardButton("⚠️ Reset Rosa", callback_data="reset_confirm")
    )
    return markup

def send_dashboard(chat_id, user_id, message_id=None):
    session = get_session(user_id)
    stats = get_roster_stats(session)
    c = stats['counts']
    
    text = (
        f" *FANTABOT PRO DASHBOARD*\n───────────────────────────\n"
        f"💳 *BILANCIO ASTA*\n"
        f"• Budget Rimanente: `{session['budget']}` cr.\n"
        f"• Giocatori Presi: `{25 - stats['slot_liberi']}/25`\n"
        f"• *Max Bid Sicuro:* `{stats['max_bid']}` cr.\n\n"
        f"📊 *COPERTURA ROSTER*\n"
        f"🧤 `Portieri`   `[{generate_progress_bar(c['P'], 3, 6)}]` `{c['P']}/3`\n"
        f"🛡️ `Difensori`  `[{generate_progress_bar(c['D'], 8, 6)}]` `{c['D']}/8`\n"
        f"⚙️ `Centrocampi` `[{generate_progress_bar(c['C'], 8, 6)}]` `{c['C']}/8`\n"
        f"🎯 `Attaccanti`  `[{generate_progress_bar(c['A'], 6, 6)}]` `{c['A']}/6`\n"
        f"───────────────────────────\n💡 _Scrivi il nome di un giocatore in chat per cercarlo!_\n"
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
        star = "⭐ " if row['Nome'] in get_session(user_id)['wishlist'] else ""
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

    session['rosa'].append({'nome': player_name, 'prezzo': costo, 'ruolo': row.get('R', 'C'), 'squadra': row.get('Squadra', '-')})
    session['budget'] -= costo
    
    markup = InlineKeyboardMarkup().add(InlineKeyboardButton("↩️ Annulla Acquisto", callback_data=f"undo_{player_name}"), InlineKeyboardButton("🏠 Torna alla Home", callback_data="go_home"))
    bot.send_message(chat_id, f"✅ *{player_name.upper()}* acquistato per `{costo} cr.`!", parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(commands=['start', 'menu'])
def cmd_start(m): send_dashboard(m.chat.id, m.from_user.id)

@bot.message_handler(func=lambda m: not m.text.startswith('/') and not m.text.isdigit())
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

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    session = get_session(user_id)
    df = load_data()

    if call.data == "go_home":
        send_dashboard(chat_id, user_id, call.message.message_id)

    elif call.data == "reload_excel":
        load_data(force_reload=True)
        bot.answer_callback_query(call.id, "⚡ Dati sincronizzati!")

    elif call.data == "reset_confirm":
        user_sessions[user_id] = {'budget': 500, 'rosa': [], 'selected_for_compare': [], 'wishlist': session['wishlist']}
        send_dashboard(chat_id, user_id, call.message.message_id)

    elif call.data == "menu_rosa":
        rosa = session['rosa']
        text = f"📋 *LA MIA ROSA*\n───────────────────────────\n💰 *Budget Residuo:* `{session['budget']}` cr.\n\n"
        if not rosa: text += "_Nessun calciatore in rosa._"
        else:
            for idx, p in enumerate(rosa, 1):
                text += f"`{idx:02d}.` {ROLE_ICONS.get(p.get('ruolo','C'), '👤')} *{p['nome']}* ── `{p['prezzo']} cr.`\n"
        
        markup = InlineKeyboardMarkup(row_width=2)
        if rosa:
            markup.add(
                InlineKeyboardButton("🥧 Grafico Spese", callback_data="chart_budget"),
                InlineKeyboardButton("📸 Esporta Recap", callback_data="export_roster")
            )
        markup.add(InlineKeyboardButton("🔙 Home", callback_data="go_home"))
        bot.edit_message_text(text, chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    # GRAFICO A TORTA
    elif call.data == "chart_budget":
        if not session['rosa']: return bot.answer_callback_query(call.id, "Rosa vuota!")
        spese = {'P': 0, 'D': 0, 'C': 0, 'A': 0}
        for p in session['rosa']: spese[p['ruolo']] += p['prezzo']
        
        labels = ['Portieri', 'Difensori', 'Centrocampisti', 'Attaccanti', 'Residuo']
        sizes = [spese['P'], spese['D'], spese['C'], spese['A'], session['budget']]
        colors = ['#f39c12', '#3498db', '#2ecc71', '#e74c3c', '#95a5a6']
        lbl_f, sz_f, col_f = zip(*[(l, s, c) for l, s, c in zip(labels, sizes, colors) if s > 0])
        
        fig, ax = plt.subplots(figsize=(6, 6))
        ax.pie(sz_f, labels=lbl_f, colors=col_f, autopct='%1.1f%%', startangle=140, wedgeprops={'edgecolor': 'white', 'linewidth': 2})
        ax.set_title('Distribuzione Budget Fantacalcio', fontweight='bold')
        
        buf = io.BytesIO(); plt.savefig(buf, format='png', bbox_inches='tight', dpi=120); buf.seek(0); plt.close(fig)
        bot.send_photo(chat_id, buf, caption="📊 *Ecco come hai distribuito i tuoi crediti finora!*", parse_mode="Markdown")

    # RECAP IMMAGINE ROSA
    elif call.data == "export_roster":
        if not session['rosa']: return bot.answer_callback_query(call.id, "Rosa vuota!")
        rosa = session['rosa']
        
        fig, ax = plt.subplots(figsize=(8, 10))
        ax.axis('off')
        
        y_pos = 0.95
        ax.text(0.5, y_pos, "LA MIA ROSA - FANTACALCIO", fontsize=22, weight='bold', ha='center', color='#2c3e50')
        y_pos -= 0.05
        ax.text(0.5, y_pos, f"Budget Rimanente: {session['budget']} cr. | Giocatori: {len(rosa)}/25", fontsize=14, ha='center', color='#7f8c8d')
        
        roles_order = ['P', 'D', 'C', 'A']
        role_colors = {'P': '#f39c12', 'D': '#3498db', 'C': '#2ecc71', 'A': '#e74c3c'}
        role_names = {'P': 'PORTIERI', 'D': 'DIFENSORI', 'C': 'CENTROCAMPISTI', 'A': 'ATTACCANTI'}
        
        y_pos -= 0.08
        for r in roles_order:
            giocatori = [p for p in rosa if p['ruolo'] == r]
            if giocatori:
                ax.text(0.1, y_pos, role_names[r], fontsize=15, weight='bold', color=role_colors[r])
                y_pos -= 0.035
                for p in giocatori:
                    ax.text(0.15, y_pos, f"• {p['nome']} ({p['squadra']})", fontsize=13)
                    ax.text(0.85, y_pos, f"{p['prezzo']} cr.", fontsize=13, ha='right', weight='bold')
                    y_pos -= 0.03
                y_pos -= 0.02
                
        buf = io.BytesIO(); plt.savefig(buf, format='png', bbox_inches='tight', dpi=150, facecolor='#f8f9fa'); buf.seek(0); plt.close(fig)
        bot.send_photo(chat_id, buf, caption="📸 *Roster Ufficiale Generato!*\nInoltralo sul gruppo WhatsApp per bullarti! 😎", parse_mode="Markdown")

    # SCOUTING SINGOLO GIOCATORE
    elif call.data.startswith("sq_pl_"):
        player_name = call.data.replace("sq_pl_", "")
        p_data = df[df['Nome'] == player_name].iloc[0]
        sq_name = p_data.get('Squadra', '-')
        
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
        )
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("⚡ Acquista (Inserisci Prezzo)", callback_data=f"buy_{player_name}"))
        markup.add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text(info_text, chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    # AREA STUDIO COMPARATIVA
    elif call.data in ["menu_studio", "cmp1_start"]: bot.edit_message_text("📊 *AREA STUDIO*\n\nSeleziona la squadra del *1° Giocatore*:", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=menu_seleziona_squadra(df, "cmp1"))
    elif call.data.startswith("cmp1_sq_"): bot.edit_message_text("Scegli il ruolo del *1° Giocatore*:", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=menu_seleziona_ruolo(call.data.replace("cmp1_sq_", ""), "cmp1"))
    elif call.data.startswith("cmp1_ru_"): _, _, sq, ru = call.data.split("_"); bot.edit_message_text(f"Seleziona il *1° Giocatore* ({ru}):", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=menu_seleziona_giocatore(df, sq, ru, "cmp1", user_id))
    elif call.data.startswith("cmp1_pl_"):
        session['selected_for_compare'] = [call.data.replace("cmp1_pl_", "")]
        bot.edit_message_text(f"✅ 1° Gioc: *{session['selected_for_compare'][0]}*\n\nSeleziona la squadra del *2° Giocatore*:", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=menu_seleziona_squadra(df, "cmp2"))
    elif call.data.startswith("cmp2_sq_"):
        ruolo_p1 = df[df['Nome'] == session['selected_for_compare'][0]].iloc[0].get('R', 'C')
        bot.edit_message_text(f"Seleziona il *2° Giocatore* (Filtro Ruolo: {ruolo_p1}):", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=menu_seleziona_giocatore(df, call.data.replace("cmp2_sq_", ""), ruolo_p1, "cmp2", user_id))
    
    # LA COMPARAZIONE FINALE (AGGIORNATA CON TUTTI I DATI E GRAFICO 3 COLONNE)
    elif call.data.startswith("cmp2_pl_"):
        p2_name = call.data.replace("cmp2_pl_", "")
        p1_name = session['selected_for_compare'][0]
        p1_data = df[df['Nome'] == p1_name].iloc[0]
        p2_data = df[df['Nome'] == p2_name].iloc[0]
        session['selected_for_compare'] = []

        testo_confronto = (
            f"📊 *COMPARAZIONE DIRETTA*\n🏆 *{p1_name.upper()}* vs *{p2_name.upper()}*\n───────────────────────────\n"
            f"📈 *FantaMedia:* `{p1_data.get('FM', '-')}` 🆚 `{p2_data.get('FM', '-')}`\n\n"
            f"🏅 *Fascia:*\n• {p1_name}: {get_team_icon(p1_data.get('Squadra',''))} `{p1_data.get('Fascia', '-')}`\n• {p2_name}: {get_team_icon(p2_data.get('Squadra',''))} `{p2_data.get('Fascia', '-')}`\n\n"
            f"🪖 *Titolarità:*\n• {p1_name}: `{p1_data.get('Titolarita', '-')}`\n• {p2_name}: `{p2_data.get('Titolarita', '-')}`\n\n"
            f"👟 *Rigori/Piazzati:*\n• {p1_name}: `{p1_data.get('Rigori_Piazzati', '-')}`\n• {p2_name}: `{p2_data.get('Rigori_Piazzati', '-')}`\n\n"
            f"🏥 *Infortuni:*\n• {p1_name}: `{p1_data.get('Infortuni', '-')}`\n• {p2_name}: `{p2_data.get('Infortuni', '-')}`\n\n"
            f"🟨 *Malus:*\n• {p1_name}: `{p1_data.get('Malus', '-')}`\n• {p2_name}: `{p2_data.get('Malus', '-')}`\n"
            f"───────────────────────────\nChi acquisti?"
        )
        
        fig, ax = plt.subplots(figsize=(8, 5))
        
        target1 = float(p1_data.get('Target Max', p1_data.get('FVM', 0)) or 0)
        target2 = float(p2_data.get('Target Max', p2_data.get('FVM', 0)) or 0)
        
        metrics = ['Quotazione', 'FVM', 'Target Max']
        p1_vals = [float(p1_data.get('Qt.A', 0) or 0), float(p1_data.get('FVM', 0) or 0), target1]
        p2_vals = [float(p2_data.get('Qt.A', 0) or 0), float(p2_data.get('FVM', 0) or 0), target2]
        
        x, width = range(len(metrics)), 0.35
        ax.bar([i - width/2 for i in x], p1_vals, width, label=p1_name, color='#1f77b4')
        ax.bar([i + width/2 for i in x], p2_vals, width, label=p2_name, color='#ff7f0e')
        ax.set_ylabel('Crediti')
        ax.set_title(f'{p1_name} vs {p2_name}')
        ax.set_xticks(x)
        ax.set_xticklabels(metrics)
        ax.legend()
        plt.grid(axis='y', alpha=0.7)
        
        buf = io.BytesIO(); plt.savefig(buf, format='png', bbox_inches='tight', dpi=100); buf.seek(0); plt.close(fig)
        
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton(f"➕ Prendi {p1_name[:8]}", callback_data=f"buy_{p1_name}"), 
            InlineKeyboardButton(f"➕ Prendi {p2_name[:8]}", callback_data=f"buy_{p2_name}")
        )
        markup.add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        
        bot.delete_message(chat_id, call.message.message_id)
        bot.send_photo(chat_id, buf, caption=testo_confronto, parse_mode="Markdown", reply_markup=markup)

    # ACQUISTO E VARIE
    elif call.data == "menu_wishlist": bot.edit_message_text("⭐ *WISHLIST*\n_Funzionalità in arrivo!_", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 Home", callback_data="go_home")))
    elif call.data.startswith("buy_"):
        player_name = call.data.replace("buy_", "")
        msg = bot.send_message(chat_id, f"💰 A quanti crediti hai acquistato *{player_name}*?\n_Scrivi un numero (es. 15):_", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_buy_price, player_name, user_id)
    elif call.data.startswith("undo_"):
        player_name = call.data.replace("undo_", "")
        for idx, p in enumerate(session['rosa']):
            if p['nome'] == player_name: session['budget'] += session['rosa'].pop(idx)['prezzo']; send_dashboard(chat_id, user_id); return
    elif call.data in ["menu_top", "menu_svincola", "sq_start"]: 
        if call.data == "sq_start": bot.edit_message_text("👕 *ESPLORA SQUADRE*", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=menu_seleziona_squadra(df, "sq"))
        else: bot.answer_callback_query(call.id, "In lavorazione... 🛠️")

if __name__ == '__main__':
    print("🤖 FantaBot Pro Ready (Full Features)...")
    bot.infinity_polling(timeout=10, long_polling_timeout=5)
