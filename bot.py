import os
import io
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, InputFile

# TOKEN DEL BOT TELEGRAM
TOKEN = "8969898580:AAHxI0_LK57bhCTP_TNYLKubhEU3a0yEg0Y"
bot = telebot.TeleBot(TOKEN)

# CONFIGURAZIONE ROSTER & ICONE RUOLI
TARGET_ROSTER = {'P': 3, 'D': 8, 'C': 8, 'A': 6}
ROLE_ICONS = {'P': '🧤', 'D': '🛡️', 'C': '⚙️', 'A': '🎯'}

# MAPPATURA COLORI SQUADRE SERIE A
TEAM_COLORS = {
    'Atalanta': '🔵⚫',
    'Bologna': '🔴🔵',
    'Cagliari': '🔴🔵',
    'Como': '🔵⚪',
    'Empoli': '🔵⚪',
    'Fiorentina': '💜',
    'Genoa': '🔴🔵',
    'Inter': '🔵⚫',
    'Juventus': '⚪⚫',
    'Lazio': '🩵⚪',
    'Lecce': '🟡🔴',
    'Milan': '🔴⚫',
    'Monza': '🔴⚪',
    'Napoli': '🔵⚪',
    'Parma': '🟡🔵',
    'Roma': '🟡🔴',
    'Torino': '🟤⚪',
    'Udinese': '⚪⚫',
    'Venezia': '🟠🟢',
    'Verona': '🟡🔵'
}

def get_team_icon(squadra):
    return TEAM_COLORS.get(str(squadra).strip(), '🛡️')

# CACHE RAM
DATA_CACHE = None

def load_data(force_reload=False):
    global DATA_CACHE
    if DATA_CACHE is None or force_reload:
        if os.path.exists("listone.xlsx"):
            print("⚡ Caricamento listone.xlsx in RAM...")
            DATA_CACHE = pd.read_excel("listone.xlsx", header=1, engine='openpyxl')
        else:
            print("⚠️ Attenzione: File listone.xlsx non trovato nella cartella!")
            DATA_CACHE = None
    return DATA_CACHE

# CARICAMENTO INIZIALE
load_data()

# SESSION STORE UTENTI
user_sessions = {}

def get_session(user_id):
    if user_id not in user_sessions:
        user_sessions[user_id] = {
            'budget': 500,
            'rosa': [],
            'selected_for_compare': []
        }
    return user_sessions[user_id]

# PROGRESS BAR IN STILE iOS DARK
def generate_progress_bar(current, target, length=8):
    filled = int(round(length * current / target)) if target > 0 else 0
    filled = min(length, max(0, filled))
    return '■' * filled + '□' * (length - filled)

def get_roster_stats(session):
    rosa = session['rosa']
    budget = session['budget']
    
    counts = {'P': 0, 'D': 0, 'C': 0, 'A': 0}
    for p in rosa:
        r = p.get('ruolo', 'C')
        if r in counts:
            counts[r] += 1
            
    total_players = len(rosa)
    slot_liberi = max(0, 25 - total_players)
    max_bid = max(0, budget - (slot_liberi - 1)) if slot_liberi > 0 else budget
    
    missing = {r: max(0, TARGET_ROSTER[r] - counts[r]) for r in TARGET_ROSTER}
    total_missing = sum(missing.values())
    
    budget_medio_ruolo = {}
    for r in TARGET_ROSTER:
        if missing[r] > 0 and total_missing > 0:
            budget_medio_ruolo[r] = round(budget / total_missing, 1)
        else:
            budget_medio_ruolo[r] = 0.0

    return {
        'counts': counts,
        'missing': missing,
        'slot_liberi': slot_liberi,
        'max_bid': max_bid,
        'budget_medio_ruolo': budget_medio_ruolo,
        'total_missing': total_missing
    }

# MENU PRINCIPALE DESIGN APPLE MINIMAL
def main_menu_keyboard():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("👕 Esplora Squadre", callback_data="sq_start"),
        InlineKeyboardButton("📋 La mia Rosa", callback_data="menu_rosa"),
        InlineKeyboardButton("📊 Area Studio (VS)", callback_data="menu_studio"),
        InlineKeyboardButton("❌ Svincola Giocatore", callback_data="menu_svincola")
    )
    markup.add(
        InlineKeyboardButton("🔄 Sincronizza RAM", callback_data="reload_excel"),
        InlineKeyboardButton("⚠️ Reset Rosa", callback_data="reset_confirm")
    )
    return markup

def send_dashboard(chat_id, user_id, message_id=None):
    session = get_session(user_id)
    stats = get_roster_stats(session)
    
    p_bar = generate_progress_bar(stats['counts']['P'], 3, 6)
    d_bar = generate_progress_bar(stats['counts']['D'], 8, 6)
    c_bar = generate_progress_bar(stats['counts']['C'], 8, 6)
    a_bar = generate_progress_bar(stats['counts']['A'], 6, 6)

    text = (
        f" *FANTABOT PRO DASHBOARD*\n"
        f"───────────────────────────\n\n"
        f"💳 *BILANCIO ASTA*\n"
        f"• Budget Rimanente: `{session['budget']}` cr.\n"
        f"• Giocatori Presi: `{25 - stats['slot_liberi']}/25`\n"
        f"• *Max Bid Sicuro:* `{stats['max_bid']}` cr.\n\n"
        f"📊 *COPERTURA ROSTER*\n"
        f"🧤 `Portieri`   `[{p_bar}]` `{stats['counts']['P']}/3`\n"
        f"🛡️ `Difensori`  `[{d_bar}]` `{stats['counts']['D']}/8`\n"
        f"⚙️ `Centrocampi` `[{c_bar}]` `{stats['counts']['C']}/8`\n"
        f"🎯 `Attaccanti`  `[{a_bar}]` `{stats['counts']['A']}/6`\n\n"
        f"───────────────────────────\n"
        f"👇 *Seleziona un'operazione:*"
    )
    
    if message_id:
        try:
            bot.edit_message_text(text, chat_id, message_id, parse_mode="Markdown", reply_markup=main_menu_keyboard())
        except Exception:
            bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=main_menu_keyboard())
    else:
        bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=main_menu_keyboard())

# --- COMPONENTS SELETTORE GERARCHICO ---

def menu_seleziona_squadra(df, prefisso_callback):
    markup = InlineKeyboardMarkup(row_width=2)
    squadre = sorted(df['Squadra'].dropna().astype(str).unique())
    buttons = [
        InlineKeyboardButton(f"{get_team_icon(sq)} {sq}", callback_data=f"{prefisso_callback}_sq_{sq}") 
        for sq in squadre
    ]
    markup.add(*buttons)
    markup.add(InlineKeyboardButton("🔙 Home", callback_data="go_home"))
    return markup

def menu_seleziona_ruolo(squadra, prefisso_callback):
    markup = InlineKeyboardMarkup(row_width=4)
    ruoli = ['P', 'D', 'C', 'A']
    buttons = [InlineKeyboardButton(f"{ROLE_ICONS[r]} {r}", callback_data=f"{prefisso_callback}_ru_{squadra}_{r}") for r in ruoli]
    markup.add(*buttons)
    markup.add(InlineKeyboardButton("🔙 Squadre", callback_data=f"{prefisso_callback}_start"))
    return markup

def menu_seleziona_giocatore(df, squadra, ruolo, prefisso_callback):
    markup = InlineKeyboardMarkup(row_width=1)
    sub_df = df[(df['Squadra'] == squadra) & (df['R'] == ruolo)]
    
    for _, row in sub_df.iterrows():
        nome = row['Nome']
        fvm = row.get('FVM', '-')
        slot = row.get('Slot', '-')
        fmt_btn = f"{ROLE_ICONS.get(ruolo,'')} {nome}  ──  FVM: {fvm} ({slot})"
        markup.add(InlineKeyboardButton(fmt_btn, callback_data=f"{prefisso_callback}_pl_{nome}"))
        
    markup.add(InlineKeyboardButton("🔙 Cambia Ruolo", callback_data=f"{prefisso_callback}_sq_{squadra}"))
    return markup

# --- HANDLER MESSAGGI E CALLBACK ---

@bot.message_handler(commands=['start', 'menu'])
def cmd_start(message):
    send_dashboard(message.chat.id, message.from_user.id)

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    session = get_session(user_id)
    df = load_data()

    if df is None:
        bot.answer_callback_query(call.id, "❌ File listone.xlsx non caricato!")
        return

    if call.data == "go_home":
        session['selected_for_compare'] = []
        send_dashboard(chat_id, user_id, call.message.message_id)

    elif call.data == "reload_excel":
        load_data(force_reload=True)
        bot.answer_callback_query(call.id, "⚡ Dati sincronizzati in RAM!")

    elif call.data == "reset_confirm":
        user_sessions[user_id] = {'budget': 500, 'rosa': [], 'selected_for_compare': []}
        bot.answer_callback_query(call.id, "🔄 Dati resettati!")
        send_dashboard(chat_id, user_id, call.message.message_id)

    # ROSA & MONITOR DETTAGLIATO
    elif call.data == "menu_rosa":
        rosa = session['rosa']
        stats = get_roster_stats(session)
        
        text = (
            f"📋 *LA MIA ROSA & ANALISI BUDGET*\n"
            f"───────────────────────────\n"
            f"💰 *Budget Residuo:* `{session['budget']}` cr.\n"
            f"🧮 *Max Bid Sicuro:* `{stats['max_bid']}` cr.\n\n"
            f"📈 *DISPONIBILITÀ MEDIA PER RUOLO*\n"
        )
        for r, name in [('P', 'Portieri'), ('D', 'Difensori'), ('C', 'Centrocampisti'), ('A', 'Attaccanti')]:
            cov = f"{stats['counts'][r]}/{TARGET_ROSTER[r]}"
            avg = f"{stats['budget_medio_ruolo'][r]} cr/slot" if stats['missing'][r] > 0 else "Completo ✅"
            text += f"• *{name} ({r}):* `{cov}` ➔ Media: `{avg}`\n"
        
        text += f"───────────────────────────\n"
        if not rosa:
            text += "\n_Nessun calciatore in rosa._"
        else:
            text += "\n"
            totale_speso = 0
            for idx, p in enumerate(rosa, start=1):
                icon = ROLE_ICONS.get(p.get('ruolo','C'), '👤')
                sq_icon = get_team_icon(p.get('squadra',''))
                text += f"`{idx:02d}.` {icon} *{p['nome']}* ({sq_icon} {p.get('squadra','-')}) ── `{p['prezzo']} cr.`\n"
                totale_speso += int(p['prezzo']) if str(p['prezzo']).isdigit() else 0
            text += f"\n💰 *Totale Speso:* `{totale_speso}` cr."
            
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("💬 Export WhatsApp", callback_data="export_wa"),
            InlineKeyboardButton("📊 Export Excel", callback_data="export_excel")
        )
        markup.add(InlineKeyboardButton("🔙 Home", callback_data="go_home"))
        bot.edit_message_text(text, chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    # EXPORT WHATSAPP (SOLUZIONE DEFINITIVA A PROVA DI ERRORE DI SINTASSI)
    elif call.data == "export_wa":
        rosa = session['rosa']
        if not rosa:
            bot.answer_callback_query(call.id, "❌ Rosa vuota!")
            return
            
        lines = ["🟢 *ROSA FANTACALCIO 2026/2027*\n"]
        for r in ['P', 'D', 'C', 'A']:
            subset = [p for p in rosa if p.get('ruolo') == r]
            if subset:
                plist = ", ".join([f"{p['nome']} ({p['prezzo']}cr)" for p in subset])
                lines.append(f"*{r}*: {plist}")
            else:
                lines.append(f"*{r}*: -")
        
        lines.append(f"\n💰 *Crediti Rimanenti:* {session['budget']} cr.")
        wa_string = "\n".join(lines)
        
        display_text = "📝 *Copia e incolla nella tua chat:*\n\n```text\n" + wa_string + "\n```"
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔙 Indietro", callback_data="menu_rosa"))
        bot.edit_message_text(display_text, chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    # EXPORT EXCEL
    elif call.data == "export_excel":
        rosa = session['rosa']
        if not rosa:
            bot.answer_callback_query(call.id, "❌ Rosa vuota!")
            return
            
        df_export = pd.DataFrame(rosa)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_export.to_excel(writer, index=False, sheet_name='La_Mia_Rosa')
        output.seek(0)
        
        bot.send_document(chat_id, document=InputFile(output, filename="La_Mia_Rosa.xlsx"), caption="📊 Report Excel della tua rosa!")

    # ESPLORA SQUADRE
    elif call.data in ["menu_squadre", "sq_start"]:
        markup = menu_seleziona_squadra(df, "sq")
        bot.edit_message_text("👕 *ESPLORA SQUADRE*\n\nSeleziona un club:", 
                              chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data.startswith("sq_sq_"):
        squadra = call.data.replace("sq_sq_", "")
        markup = menu_seleziona_ruolo(squadra, "sq")
        bot.edit_message_text(f"{get_team_icon(squadra)} *{squadra}*\nSeleziona il reparto:", 
                              chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data.startswith("sq_ru_"):
        _, _, squadra, ruolo = call.data.split("_")
        markup = menu_seleziona_giocatore(df, squadra, ruolo, "sq")
        bot.edit_message_text(f"{get_team_icon(squadra)} *{squadra}*  │  Reparto: *{ruolo}*\nScegli un calciatore:", 
                              chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data.startswith("sq_pl_"):
        player_name = call.data.replace("sq_pl_", "")
        p_data = df[df['Nome'] == player_name].iloc[0]
        stats = get_roster_stats(session)
        sq_name = p_data.get('Squadra', '-')
        sq_icon = get_team_icon(sq_name)
        rig = "🎯 Rigorista Ufficiale" if str(p_data.get('Rigorista', '')).strip().lower() == 'sì' else "❌ No Rigori"
        
        info_text = (
            f"👤 *{player_name.upper()}* ({sq_icon} {sq_name})\n"
            f"───────────────────────────\n"
            f"📌 Ruolo: `{p_data.get('R', '-')}`  │  ⭐ Slot: `{p_data.get('Slot', '-')}`\n"
            f"📈 Fantamedia: `{p_data.get('FM', '-')}`\n"
            f"💰 Quotazione: `{p_data.get('Qt.A', '-')}` cr.  │  FVM: `{p_data.get('FVM', '-')}` cr.\n"
            f"Status: `{rig}`\n"
            f"🎯 *Target Max Consigliato:* `{p_data.get('Target_Max', '-')} cr.`\n\n"
            f"🧮 *Max Bid Sicuro Consentito:* `{stats['max_bid']} cr.`\n"
            f"📝 *Note Tattiche:* _{p_data.get('Note', '-')}_"
        )
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(f"⚡ Acquista ({p_data.get('Target_Max', 1)} cr.)", callback_data=f"buy_{player_name}"))
        markup.add(InlineKeyboardButton("🔙 Cambia Ruolo", callback_data=f"sq_sq_{sq_name}"))
        markup.add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text(info_text, chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    # AREA STUDIO COMPARATIVA
    elif call.data in ["menu_studio", "cmp1_start"]:
        session['selected_for_compare'] = []
        markup = menu_seleziona_squadra(df, "cmp1")
        bot.edit_message_text("📊 *AREA STUDIO COMPARATIVA*\n\nSeleziona la squadra del *1° Giocatore*:", 
                              chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data.startswith("cmp1_sq_"):
        squadra = call.data.replace("cmp1_sq_", "")
        markup = menu_seleziona_ruolo(squadra, "cmp1")
        bot.edit_message_text(f"{get_team_icon(squadra)} *{squadra}*\nScegli il ruolo del *1° Giocatore*:", 
                              chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data.startswith("cmp1_ru_"):
        _, _, squadra, ruolo = call.data.split("_")
        markup = menu_seleziona_giocatore(df, squadra, ruolo, "cmp1")
        bot.edit_message_text(f"{get_team_icon(squadra)} *{squadra}*  │  Ruolo: *{ruolo}*\nSeleziona il *1° Giocatore*:", 
                              chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data.startswith("cmp1_pl_"):
        player_name = call.data.replace("cmp1_pl_", "")
        session['selected_for_compare'] = [player_name]
        markup = menu_seleziona_squadra(df, "cmp2")
        bot.edit_message_text(f"✅ 1° Giocatore: *{player_name}*\n\nOra seleziona la squadra del *2° Giocatore*:", 
                              chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data.startswith("cmp2_sq_"):
        squadra = call.data.replace("cmp2_sq_", "")
        markup = menu_seleziona_ruolo(squadra, "cmp2")
        bot.edit_message_text(f"{get_team_icon(squadra)} *{squadra}*\nScegli il ruolo del *2° Giocatore*:", 
                              chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data.startswith("cmp2_ru_"):
        _, _, squadra, ruolo = call.data.split("_")
        markup = menu_seleziona_giocatore(df, squadra, ruolo, "cmp2")
        bot.edit_message_text(f"{get_team_icon(squadra)} *{squadra}*  │  Ruolo: *{ruolo}*\nSeleziona il *2° Giocatore*:", 
                              chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data.startswith("cmp2_pl_"):
        p2_name = call.data.replace("cmp2_pl_", "")
        p1_name = session['selected_for_compare'][0]
        session['selected_for_compare'] = []

        p1_data = df[df['Nome'] == p1_name].iloc[0]
        p2_data = df[df['Nome'] == p2_name].iloc[0]
        stats = get_roster_stats(session)

        # STILE GRAFICO APPLE DARK
        plt.rcParams['font.sans-serif'] = ['SF Pro Text', 'Helvetica Neue', 'Helvetica', 'Arial', 'DejaVu Sans']
        fig, ax1 = plt.subplots(figsize=(7, 4.5), facecolor='#161618')
        ax1.set_facecolor('#1E1E22')
        
        names = [p1_name, p2_name]
        qta_vals = [float(p1_data.get('Qt.A', 0)), float(p2_data.get('Qt.A', 0))]
        fvm_vals = [float(p1_data.get('FVM', 0)), float(p2_data.get('FVM', 0))]
        fm_vals = [float(p1_data.get('FM', 0)), float(p2_data.get('FM', 0))]
        
        x = range(len(names))
        width = 0.22

        b1 = ax1.bar([i - width/2 for i in x], qta_vals, width, label='Qt.A', color='#0A84FF', edgecolor='none', zorder=3, alpha=0.95)
        b2 = ax1.bar([i + width/2 for i in x], fvm_vals, width, label='FVM', color='#64D2FF', edgecolor='none', zorder=3, alpha=0.95)
        
        ax1.set_ylabel('Crediti', color='#8E8E93', fontsize=10, fontweight='500')
        ax1.set_xticks(x)
        ax1.set_xticklabels([n.upper() for n in names], fontweight='600', fontsize=11, color='#F2F2F7')
        ax1.tick_params(colors='#8E8E93')
        ax1.grid(axis='y', color='#2C2C2E', linestyle='-', linewidth=0.7, zorder=0)
        
        ax1.bar_label(b1, padding=5, fmt='%.0f cr', color='#0A84FF', fontweight='600', fontsize=9)
        ax1.bar_label(b2, padding=5, fmt='%.0f cr', color='#64D2FF', fontweight='600', fontsize=9)

        ax2 = ax1.twinx()
        l1 = ax2.plot(x, fm_vals, color='#30D158', marker='o', markersize=8, markerfacecolor='#161618', markeredgewidth=2.5, linewidth=2.5, label='Fantamedia (FM)', zorder=4)
        ax2.set_ylabel('Fantamedia (FM)', color='#30D158', fontsize=10, fontweight='600')
        ax2.tick_params(colors='#30D158')
        ax2.set_ylim(4, 10)

        for i, txt in enumerate(fm_vals):
            ax2.annotate(f"FM: {txt}", (x[i], fm_vals[i] + 0.18), ha='center', fontweight='600', color='#F2F2F7', fontsize=9,
                          bbox=dict(boxstyle="round,pad=0.4,rounding_size=0.6", fc="#2C2C2E", ec="#30D158", lw=1.2))

        for spine in ax1.spines.values():
            spine.set_color('#2C2C2E')

        plt.title(f"{p1_name.upper()}  vs  {p2_name.upper()}", color='#F2F2F7', fontsize=13, fontweight='700', pad=15)
        fig.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=140, facecolor=fig.get_facecolor(), edgecolor='none')
        buf.seek(0)
        plt.close()

        sq1_icon = get_team_icon(p1_data.get('Squadra', ''))
        sq2_icon = get_team_icon(p2_data.get('Squadra', ''))
        rig1 = "🎯 Rigorista" if str(p1_data.get('Rigorista', '')).strip().lower() == 'sì' else "❌ No Rigori"
        rig2 = "🎯 Rigorista" if str(p2_data.get('Rigorista', '')).strip().lower() == 'sì' else "❌ No Rigori"

        caption = (
            f"📊 *ANALISI COMPARATIVA HEAD-TO-HEAD*\n"
            f"───────────────────────────\n"
            f"🧮 *Max Bid Sicuro Disponibile:* `{stats['max_bid']} cr.`\n\n"
            f"🔹 *{p1_name.upper()}* ({sq1_icon} {p1_data.get('Squadra', '-')})\n"
            f"• Ruolo: `{p1_data.get('R', '-')}` │ Slot: `{p1_data.get('Slot', '-')}`\n"
            f"• FM: `{p1_data.get('FM', '-')}` │ Status: `{rig1}`\n"
            f"• Target Max: `{p1_data.get('Target_Max', '-')} cr.`\n\n"
            f"🔸 *{p2_name.upper()}* ({sq2_icon} {p2_data.get('Squadra', '-')})\n"
            f"• Ruolo: `{p2_data.get('R', '-')}` │ Slot: `{p2_data.get('Slot', '-')}`\n"
            f"• FM: `{p2_data.get('FM', '-')}` │ Status: `{rig2}`\n"
            f"• Target Max: `{p2_data.get('Target_Max', '-')} cr.`"
        )

        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(f"➕ Prendi {p1_name} ({p1_data.get('Target_Max', 1)}cr)", callback_data=f"buy_{p1_name}"))
        markup.add(InlineKeyboardButton(f"➕ Prendi {p2_name} ({p2_data.get('Target_Max', 1)}cr)", callback_data=f"buy_{p2_name}"))
        markup.add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))

        bot.send_photo(chat_id, photo=buf, caption=caption, parse_mode="Markdown", reply_markup=markup)

    # ACQUISTO RAPIDO
    elif call.data.startswith("buy_"):
        player_name = call.data.replace("buy_", "")
        player_row = df[df['Nome'] == player_name].iloc[0]
        target = player_row.get('Target_Max', 1)
        ruolo = player_row.get('R', 'C')
        squadra = player_row.get('Squadra', '-')
        
        try:
            costo = int(target)
        except Exception:
            costo = 1

        stats = get_roster_stats(session)
        if costo > stats['max_bid']:
            bot.answer_callback_query(call.id, f"⚠️ Attenzione! {costo} cr. supera il Max Bid Sicuro ({stats['max_bid']} cr.)!", show_alert=True)
            return

        session['rosa'].append({
            'nome': player_name, 
            'prezzo': costo, 
            'ruolo': ruolo, 
            'squadra': squadra
        })
        session['budget'] -= costo
        
        bot.answer_callback_query(call.id, f"✅ {player_name} ({ruolo}) preso a {costo} cr.!")
        send_dashboard(chat_id, user_id)

    # SVINCOLA GIOCATORE
    elif call.data == "menu_svincola":
        rosa = session['rosa']
        if not rosa:
            bot.answer_callback_query(call.id, "❌ Nessun calciatore in rosa!")
            return
            
        markup = InlineKeyboardMarkup(row_width=1)
        for idx, p in enumerate(rosa):
            markup.add(InlineKeyboardButton(f"❌ Svincola {p['nome']} (+{p['prezzo']} cr.)", callback_data=f"del_{idx}"))
        markup.add(InlineKeyboardButton("🔙 Home", callback_data="go_home"))
        bot.edit_message_text("❌ *SELEZIONA IL GIOCATORE DA SVINCOLARE:*", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data.startswith("del_"):
        idx = int(call.data.replace("del_", ""))
        rosa = session['rosa']
        if 0 <= idx < len(rosa):
            removed = rosa.pop(idx)
            session['budget'] += int(removed['prezzo']) if str(removed['prezzo']).isdigit() else 0
            bot.answer_callback_query(call.id, f"🗑️ {removed['nome']} svincolato!")
        send_dashboard(chat_id, user_id, call.message.message_id)

# AVVIO BOT
if __name__ == '__main__':
    print("🤖 FantaBot Pro Ready (Apple Dark Aesthetics + Team Colors Active)...")
    print("📡 In ascolto dei comandi Telegram...")
    try:
        bot.infinity_polling(timeout=10, long_polling_timeout=5)
    except Exception as e:
        print(f"❌ Errore durante il polling: {e}")
