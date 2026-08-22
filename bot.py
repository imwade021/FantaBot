import os
import io
import time
import re
import sys
import html
import json
import threading
import pandas as pd
import analisi
import config
import dati
import interfaccia
import modificatore
import consiglio
import piano
import pronostici
import registro as reg
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from telebot.apihelper import ApiTelegramException
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

# ==========================================
# CONFIGURAZIONE INIZIALE & TOKEN
# ==========================================
TOKEN = config.TOKEN

if not TOKEN:
    raise ValueError("⚠️ ERRORE: La variabile d'ambiente BOT_TOKEN non è impostata!")

bot = telebot.TeleBot(TOKEN)

# Alias verso config.py: le costanti stanno tutte la'
LISTONE_URL = config.LISTONE_URL
ROLE_ICONS = config.ROLE_ICONS
TEAM_COLORS = config.TEAM_COLORS
SLOT_PER_RUOLO = config.SLOT_PER_RUOLO

# Sessioni utente. Stanno in memoria per velocita', ma vengono salvate su disco:
# durante un'asta dal vivo un riavvio di Render azzerava rosa, cassa e scartati.
user_sessions = {}
_sessioni_lock = threading.Lock()


def carica_sessioni():
    """Ripristina le sessioni salvate. Un file corrotto non blocca l'avvio."""
    if not os.path.exists(config.FILE_SESSIONI):
        return
    try:
        with open(config.FILE_SESSIONI, 'r', encoding='utf-8') as f:
            salvate = json.load(f)
        for chiave, sessione in salvate.items():
            user_sessions[int(chiave)] = sessione
        print(f"✅ Sessioni ripristinate: {len(user_sessions)}.")
    except Exception as e:
        print(f"⚠️ Sessioni non ripristinate ({e}): si riparte da zero.")


def salva_sessioni():
    """Scrittura atomica: se il processo muore a meta', il file resta valido."""
    try:
        with _sessioni_lock:
            istantanea = {str(k): v for k, v in user_sessions.items()}
        temporaneo = config.FILE_SESSIONI + ".tmp"
        with open(temporaneo, 'w', encoding='utf-8') as f:
            json.dump(istantanea, f, ensure_ascii=False)
        os.replace(temporaneo, config.FILE_SESSIONI)
    except Exception as e:
        print(f"⚠️ Salvataggio sessioni fallito: {e}")

# Rigoristi, coppie di portieri e scommesse NON sono piu' liste scritte a mano:
# si ricavano dalle colonne del Lista_Finale_Master.csv (Rc = rigori calciati,
# R+ = segnati, Pv = presenze). Cosi' restano allineate a ogni aggiornamento.

def _num(v, default=0.0):
    try:
        n = pd.to_numeric(str(v).replace(',', '.'), errors='coerce')
        return default if pd.isna(n) else float(n)
    except Exception:
        return default


def fair_price(row, session):
    return dati.prezzo_consigliato(row, session)


def gerarchie_rigoristi(df, squadra=None):
    """Chi ha calciato rigori la scorsa stagione, per squadra, dal piu' usato."""
    if df is None or df.empty or 'Rc' not in df.columns:
        return {}

    gerarchie = {}
    squadre = [squadra] if squadra else sorted(df['Squadra'].dropna().astype(str).unique())
    for sq in squadre:
        rosa = df[df['Squadra'].astype(str) == str(sq)].copy()
        if rosa.empty:
            continue
        rosa['_rc'] = rosa['Rc'].apply(_num)
        tiratori = rosa[rosa['_rc'] > 0].sort_values('_rc', ascending=False)
        if tiratori.empty:
            continue
        gerarchie[sq] = {
            'rigoristi': [
                f"{r['Nome']} ({int(r['_rc'])})" for _, r in tiratori.head(3).iterrows()
            ]
        }
    return gerarchie


def trova_partner_portiere(nome, df):
    """Il vice (o titolare) della stessa squadra: il 'paracadute' da abbinare."""
    if df is None or df.empty:
        return None
    riga = get_player_stats(nome, df)
    if riga is None or str(riga.get('R', '')).upper() != 'P':
        return None

    compagni = df[(df['R'].astype(str).str.upper() == 'P') &
                  (df['Squadra'].astype(str) == str(riga.get('Squadra', ''))) &
                  (df['Nome'].astype(str) != str(riga.get('Nome', '')))]
    if compagni.empty:
        return None
    compagni = compagni.assign(_fvm=compagni['FVM'].apply(_num)).sort_values('_fvm', ascending=False)
    return str(compagni.iloc[0]['Nome'])


def safe_answer_callback(call_id, text=None, show_alert=False):
    try: bot.answer_callback_query(call_id, text=text, show_alert=show_alert)
    except Exception: pass

def get_team_icon(squadra):
    return dati.icona_squadra(squadra)


def auto_download_listone_raw():
    return dati.scarica_master()


def auto_download_listone():
    if auto_download_listone_raw():
        load_data(force_reload=True)
        return True
    return False

def load_data(force_reload=False):
    return dati.carica(forza=force_reload)


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
            'tabella_modificatore': None,
            'fase_asta': None,
            'registro': {'voci': [], 'avversari': [],
                         'budget_iniziale': 500, 'partecipanti': 8},
            'strategia': 'equilibrata',
        }
    return user_sessions[user_id]


def get_registro(session):
    """Il taccuino della sessione. Si ricostruisce dal dizionario ogni volta:
    e' poca roba e cosi' non esistono due copie che possono divergere."""
    dati_registro = session.setdefault('registro', {})
    dati_registro.setdefault('budget_iniziale', session.get('lega_budget_iniziale', 500))
    dati_registro.setdefault('partecipanti', session.get('lega_partecipanti', 8))
    return reg.Registro(dati_registro)


def salva_registro(registro_asta, session, chat_id=None):
    """
    Scrive il registro, riallinea le chiavi del bot e lo copia su Telegram.

    Il file su disco non basta: Render lo azzera a ogni deploy. La copia
    fissata in cima alla chat sopravvive a tutto, e ricostruire da li' e'
    questione di un secondo.
    """
    reg.sincronizza(registro_asta, session)
    salva_sessioni()
    if chat_id is not None:
        copia_su_telegram(chat_id, registro_asta, session)
    return session


def copia_su_telegram(chat_id, registro_asta, session):
    """
    Riscrive il messaggio fissato col taccuino aggiornato.

    Non deve MAI far fallire una registrazione: se Telegram non risponde, la
    vendita resta comunque segnata su disco e si riprovera' alla prossima.
    """
    testo = reg.serializza(registro_asta)
    id_messaggio = session.get('id_taccuino')
    try:
        if id_messaggio:
            bot.edit_message_text(testo, chat_id, id_messaggio)
            return
        messaggio = bot.send_message(chat_id, testo)
        session['id_taccuino'] = messaggio.message_id
        try:
            bot.pin_chat_message(chat_id, messaggio.message_id,
                                 disable_notification=True)
        except Exception:
            pass          # se non si puo' fissare, il messaggio resta comunque
        salva_sessioni()
    except Exception as errore:
        testo_errore = str(errore)
        if "message is not modified" in testo_errore:
            return
        # Il messaggio potrebbe essere stato cancellato a mano: si riparte.
        if "message to edit not found" in testo_errore:
            session['id_taccuino'] = None
            return copia_su_telegram(chat_id, registro_asta, session)
        print(f"⚠️ Taccuino non copiato su Telegram: {errore}")


def recupera_taccuino(chat_id, session, df):
    """
    Rimette in piedi il registro dal messaggio fissato, dopo un riavvio.

    Si prova solo quando il registro in memoria e' vuoto: se c'e' gia'
    qualcosa, quella e' piu' recente e non va toccata.
    """
    registro_attuale = get_registro(session)
    if registro_attuale.voci:
        return None
    try:
        fissato = getattr(bot.get_chat(chat_id), 'pinned_message', None)
        testo = getattr(fissato, 'text', None) if fissato else None
    except Exception:
        return None
    if not testo:
        return None

    def cerca(nome):
        riga = df[df['Nome'].astype(str).str.lower() == str(nome).lower()]
        if riga.empty:
            return None
        return (str(riga.iloc[0].get('R', 'C'))[:1].upper(),
                str(riga.iloc[0].get('Squadra', '')))

    recuperato = reg.deserializza(testo, cerca,
                                  session.get('lega_budget_iniziale', 500),
                                  session.get('lega_partecipanti', 8))
    if not recuperato:
        return None
    session['id_taccuino'] = getattr(fissato, 'message_id', None)
    salva_registro(recuperato, session)
    return recuperato

def get_roster_stats(session):
    return dati.stato_rosa(session)


def get_available_players(df, session):
    return dati.disponibili(df, session)


def get_player_stats(nome, df):
    return dati.cerca_giocatore(nome, df)


def get_macellaio_info(nome, df):
    row = get_player_stats(nome, df)
    if row is not None:
        try:
            amm = int(pd.to_numeric(row.get('Amm', 0), errors='coerce'))
            esp = int(pd.to_numeric(row.get('Esp', 0), errors='coerce'))
            pv = int(pd.to_numeric(row.get('Pv', row.get('Pres', 1)), errors='coerce'))
            
            if (amm >= 6 or esp >= 1) and pv > 5:
                return f"\n🪓 <b>ALLARME MACELLAIO:</b> <code>{amm} Gialli</code>, <code>{esp} Rossi</code>"
            else:
                return f"\n🛡 <b>Disciplinato:</b> <code>{amm} Gialli</code>, <code>{esp} Rossi</code>"
        except Exception: pass
    return "\n🛡 <b>Dati Cartellini assenti nel Master.</b>"

def get_storico(nome, df):
    row = get_player_stats(nome, df)
    if row is None:
        return "⚠️ Nessun dato presente nel file Master per questo giocatore."

    prof = analisi.profilo(row, analisi.statistiche_squadre(df), analisi.baseline_ruoli(df))
    titolo = f"📊 <b>STORICO (Dal file Master): {html.escape(prof['nome'].upper())}</b>\n───────────────────────────\n"

    # Tre casi distinti: storico vero, proiezione su dati esteri, nessun dato.
    if prof['senza_dati']:
        return (titolo +
                "❔ <b>Nessuno storico disponibile.</b>\n"
                "Non ha giocato in Serie A e le fonti esterne non lo coprono.\n"
                f"La valutazione si basa solo sulla quotazione ufficiale "
                f"(<code>{prof['quotazione']:.0f}</code>).\n")

    if prof['proiezione']:
        return (titolo +
                "🆕 <b>Nuovo in Serie A</b> — nessuna presenza nel campionato italiano.\n"
                f"🔮 Fantamedia <b>proiettata</b> dai dati esteri: <code>{prof['fantamedia']:.2f}</code>\n"
                "<i>È una stima, non un rendimento reale: pesala di conseguenza.</i>\n")

    testo = (titolo +
        f"🏟 Pres: <code>{prof['presenze']}</code> ({prof['etichetta_titolarita']}) │ "
        f"📈 MV: <code>{prof['voto_puro']:.2f}</code> │ FM: <code>{prof['fantamedia']:.2f}</code>\n"
        f"🎁 Bonus a partita: <code>{prof['bonus_partita']:+.2f}</code>\n"
        f"⚽ Gol: <code>{prof['gol']}</code> │ 🎯 Ass: <code>{prof['assist']}</code> │ "
        f"🟨 <code>{prof['ammonizioni']}</code> │ 🟥 <code>{prof['espulsioni']}</code>\n"
    )
    if prof['rigorista']:
        testo += f"⚪ <b>Rigorista</b>: {prof['rigori_calciati']} rigori calciati\n"
    if prof.get('gol_subiti_partita') is not None and prof['ruolo'] in ('P', 'D'):
        testo += f"🛡 Gol subiti dalla squadra: <code>{prof['gol_subiti_partita']}</code> a partita\n"
    if prof['presenze'] < 10:
        testo += "\n⚠️ <i>Poche presenze: le medie non sono affidabili.</i>\n"
    return testo


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

def advanced_trade_analyzer_3d(p1, p2, session, df=None):
    """Confronto voce per voce (analisi.confronta) + impatto sulla rosa."""
    esito = analisi.confronta(p1, p2, df, modificatore_difesa=session.get('modificatore_attivo', False))
    testo = analisi.formatta_confronto(esito)

    rosa = session.get('rosa', [])
    r1, r2 = p1.get('R', 'C'), p2.get('R', 'C')
    c1 = sum(1 for p in rosa if p.get('ruolo') == r1)
    c2 = sum(1 for p in rosa if p.get('ruolo') == r2)
    avvisi = []
    if r1 != r2:
        if c1 <= 3 and r1 in ['D', 'C']: avvisi.append(f"🚨 Sei corto in <b>{r1}</b> ({c1} in rosa)")
        if c2 >= 8 and r2 in ['D', 'C']: avvisi.append(f"⚠️ Sei gia' pieno in <b>{r2}</b> ({c2} in rosa)")

    budget = session.get('budget', 0)
    for profilo_g in (esito['p1'], esito['p2']):
        if profilo_g['prezzo'] > budget:
            avvisi.append(f"💸 {profilo_g['nome']} costa piu' del budget residuo ({budget} cr)")

    if avvisi:
        testo += "\n\n" + "\n".join(avvisi)
    return testo


def calcola_formazione_ideale(session, df):
    """
    Schieramento consigliato. Il 'power' non somma piu' fantamedia e voto
    (che si contavano due volte): usa la fantamedia ponderata per presenze,
    con un bonus per chi e' titolare fisso e un malus per i cartellini.
    """
    rosa = session.get('rosa', [])
    if not rosa:
        return "❌ <b>La tua rosa è vuota!</b> Acquista o aggiungi giocatori.", None

    baseline = analisi.baseline_ruoli(df)
    per_ruolo = {'P': [], 'D': [], 'C': [], 'A': []}

    for p in rosa:
        ruolo = p.get('ruolo', 'C')
        if ruolo not in per_ruolo:
            continue
        row = get_player_stats(p['nome'], df)
        if row is None:
            per_ruolo[ruolo].append({'nome': p['nome'], 'power': 0.0, 'fm': 0.0,
                                     'amm': 0, 'pres': 0, 'nota': 'senza dati'})
            continue

        prof = analisi.profilo(row, None, baseline)
        power = prof['fantamedia_ponderata'] + (prof['titolarita'] * 0.5) - (prof['ammonizioni'] * 0.02)
        per_ruolo[ruolo].append({
            'nome': prof['nome'], 'power': round(power, 3), 'fm': prof['fantamedia'],
            'amm': prof['ammonizioni'], 'pres': prof['presenze'],
            'nota': prof['etichetta_titolarita'],
        })

    for ruolo in per_ruolo:
        per_ruolo[ruolo].sort(key=lambda x: x['power'], reverse=True)

    # Il modulo si adatta a chi hai davvero in rosa
    moduli = [(3, 4, 3), (3, 5, 2), (4, 4, 2), (4, 3, 3), (4, 5, 1), (5, 3, 2), (5, 4, 1)]
    disponibili = {r: len(per_ruolo[r]) for r in per_ruolo}
    schema = next((m for m in moduli
                   if disponibili['D'] >= m[0] and disponibili['C'] >= m[1] and disponibili['A'] >= m[2]),
                  None)
    if schema is None:
        schema = (min(disponibili['D'], 3), min(disponibili['C'], 4), min(disponibili['A'], 3))

    titolari = {
        'P': per_ruolo['P'][:1],
        'D': per_ruolo['D'][:schema[0]],
        'C': per_ruolo['C'][:schema[1]],
        'A': per_ruolo['A'][:schema[2]],
    }
    nomi_titolari = {x['nome'] for gruppo in titolari.values() for x in gruppo}
    panchina = {r: [x for x in per_ruolo[r] if x['nome'] not in nomi_titolari] for r in per_ruolo}

    modulo = f"{schema[0]}-{schema[1]}-{schema[2]}"
    testo = f"📋 <b>FORMAZIONE CONSIGLIATA ({modulo})</b>\n━━━━━━━━━━━━━━━━━━━━━━\n<b>TITOLARI:</b>\n"
    for ruolo in ['P', 'D', 'C', 'A']:
        elenco = ", ".join(x['nome'] for x in titolari[ruolo]) or "—"
        testo += f"{ROLE_ICONS[ruolo]} <b>{ruolo}:</b> {elenco}\n"

    voci_panchina = []
    for ruolo in ['P', 'D', 'C', 'A']:
        if panchina[ruolo]:
            nomi = ", ".join(f"{x['nome']} ({x['fm']:.2f})" for x in panchina[ruolo][:3])
            voci_panchina.append(f"{ROLE_ICONS[ruolo]} <b>{ruolo}:</b> {nomi}")
    if voci_panchina:
        testo += "\n<b>PANCHINA:</b>\n" + "\n".join(voci_panchina) + "\n"

    if disponibili['P'] == 0:
        testo += "\n🚨 <b>Manca il portiere!</b>\n"

    rischi = [f"⚠️ {x['nome']} ({x['amm']} gialli)"
              for gruppo in titolari.values() for x in gruppo if x['amm'] >= 4]
    panchinari = [f"🪑 {x['nome']} è un {x['nota']} ({x['pres']} pres.)"
                  for gruppo in titolari.values() for x in gruppo
                  if x['nota'] in ('riserva', 'alternanza')]
    if rischi:
        testo += "\n🚨 <b>RADAR DIFFIDATI:</b>\n" + "\n".join(rischi) + "\n"
    if panchinari:
        testo += "\n<b>ATTENZIONE ALLA TITOLARITÀ:</b>\n" + "\n".join(panchinari)

    return testo, draw_pitch_image(titolari, modulo)


# ==========================================
# MENU E DASHBOARD
# ==========================================
SLOT_PER_RUOLO_HOME = {'P': 3, 'D': 8, 'C': 8, 'A': 6}


def main_menu_keyboard(session):
    """Poche voci in home: gli strumenti di scouting stanno in un sottomenu."""
    markup = InlineKeyboardMarkup(row_width=2)
    if session.get('fase_asta'):
        markup.add(InlineKeyboardButton("🔴  RIPRENDI ASTA", callback_data="asta_resume"))
        markup.add(InlineKeyboardButton("🛑  Termina asta", callback_data="asta_end"))
    else:
        markup.add(InlineKeyboardButton("🔨  AVVIA ASTA LIVE", callback_data="asta_setup_start"))

    # Le tre domande che ci si fa davvero durante un'asta, in cima e da sole.
    # Sotto, gli attrezzi. Piu' in basso, le impostazioni che si toccano una
    # volta e mai piu'. La regola e' che scendendo cala l'urgenza: chi apre il
    # bot mentre qualcuno rilancia trova subito la risposta, non un catalogo.
    markup.add(InlineKeyboardButton("🚨  Chi prendo adesso", callback_data="menu_panic_start"))
    markup.add(InlineKeyboardButton("📊  Come sto andando", callback_data="menu_andamento"),
               InlineKeyboardButton("🎯  Pronostici", callback_data="menu_scommessa_start"))
    markup.add(InlineKeyboardButton("📋  La mia rosa", callback_data="menu_rosa"),
               InlineKeyboardButton("⭐  Wishlist", callback_data="menu_wishlist"))
    markup.add(InlineKeyboardButton("👕  Esplora", callback_data="sq_start"),
               InlineKeyboardButton("⚖️  Confronta", callback_data="menu_studio_start"))
    markup.add(InlineKeyboardButton("🔎  Altri strumenti", callback_data="menu_scouting"))
    markup.add(InlineKeyboardButton("⚙️  Lega", callback_data="menu_impostazioni_lega"),
               InlineKeyboardButton("🧰  Sistema", callback_data="menu_sistema"))
    return markup


def _quadro_piano(df, session):
    """Il piano di spesa, calcolato in un posto solo e usato da tutte le
    schermate: Panic, suggerimenti dopo una vendita, Come sto andando."""
    registro_asta = get_registro(session)
    disponibili = get_available_players(df, session)
    listino = {str(r['Nome']): _num(r.get('Prezzo'), 1) for _, r in df.iterrows()}
    inflazione, campione = registro_asta.inflazione(listino)
    quadro = piano.stato(registro_asta, disponibili, SLOT_PER_RUOLO,
                         config.QUOTE_REPARTO, inflazione)
    return registro_asta, disponibili, quadro, inflazione, campione


ETICHETTE_PRONOSTICI = [
    ('entrava', '🎲 SE GIOCANO, ESPLODONO',
     'pochi minuti ma tanti bonus dentro quei minuti'),
    ('rotti', '🚑 STAGIONE PERSA PER INFORTUNIO',
     'titolari quando stavano bene: il prezzo lo sconta, il rendimento no'),
    ('garantiti', '🧱 NON LI TOGLIE NESSUNO',
     'minuti garantiti a prezzo di saldo'),
]


def metti_in_asta(message, riga, df, session):
    """
    Il giocatore chiamato finisce sotto il semaforo, col suo tetto personale.

    Il tetto e' lo stesso del Panic, calcolato dallo stesso posto: sarebbe
    assurdo che il bot dicesse 22 in una schermata e 30 in un'altra sullo
    stesso giocatore nello stesso istante.
    """
    _, disponibili, quadro, inflazione, _ = _quadro_piano(df, session)
    ruolo = str(riga.get('R', 'C')).upper()[:1]
    contesto = contesto_valori(df, session)

    conti = piano.disponibile(quadro, ruolo)
    fasce = piano.fasce_di_spesa(conti['disponibile'], conti['mancanti'],
                                 session.get('strategia', 'equilibrata'))
    tetto_reparto = fasce[0] if fasce else conti['disponibile']

    gruppo = consiglio.classifica(disponibili, ruolo, contesto)
    punteggio = consiglio.valuta(riga, contesto)
    prezzo = int(_num(riga.get('Prezzo'), 1))
    if gruppo is not None and not gruppo.empty:
        migliore = float(gruppo.iloc[0]['_valore'])
        posizione = min(len(gruppo) - 1, max(1, session.get('lega_partecipanti', 8) - 1))
        rif = gruppo.iloc[posizione]
        tetto = consiglio.tetto_personale(
            punteggio['totale'], prezzo, migliore, float(rif['_valore']),
            int(rif['_prezzo']), tetto_reparto, inflazione,
            punteggio.get('ballottaggio', False))
    else:
        tetto = min(prezzo, tetto_reparto)

    session['in_asta'] = {
        'nome': str(riga['Nome']), 'ruolo': ruolo, 'prezzo': prezzo,
        'squadra': str(riga.get('Squadra', '')), 'tetto': int(tetto), 'offerta': None,
        'motivo': consiglio.motivo(riga, punteggio, prezzo, contesto),
    }
    salva_sessioni()
    try:
        bot.delete_message(message.chat.id, message.message_id)
    except Exception:
        pass
    return mostra_plancia(message.chat.id, session.get('id_plancia'), df, session)


def turno_di_chi(session, registro_asta):
    """
    Di chi e' il turno di chiamare, e fra quanto tocca a te.

    Si chiama a rotazione e ogni chiamata finisce con una vendita: quindi il
    numero di vendite E' il numero di turni passati. Non serve segnare niente
    in piu' - il taccuino che tieni gia' basta a saperlo.
    """
    partecipanti = max(2, session.get('lega_partecipanti', 8))
    scostamento = session.get('turno_offset')
    if scostamento is None:
        return {'noto': False, 'mancano': None, 'partecipanti': partecipanti}
    passati = len(registro_asta.voci)
    mancano = (scostamento - passati) % partecipanti
    return {'noto': True, 'mancano': mancano, 'tocca_a_me': mancano == 0,
            'partecipanti': partecipanti}


def scarsita(disponibili, ruolo, session, registro_asta, contesto):
    """
    Quanti giocatori validi restano, contro quanti ne servono a tutta la lega.

    E' l'informazione che fa anticipare invece di inseguire: quando i buoni
    scendono sotto le squadre che li cercano, il prezzo esplode e chi aspetta
    paga il doppio.
    """
    gruppo = consiglio.classifica(disponibili, ruolo, contesto)
    if gruppo is None or gruppo.empty:
        return None
    # "Valido" = sopra la media del ruolo, cioe' con valore positivo.
    validi = int((gruppo['_valore'] > 0).sum())
    partecipanti = session.get('lega_partecipanti', 8)
    presi_da_tutti = sum(1 for v in registro_asta.voci if v.get('ruolo') == ruolo)
    servono = max(0, partecipanti * SLOT_PER_RUOLO.get(ruolo, 0) - presi_da_tutti)
    return {'validi': validi, 'servono': servono,
            'stretta': validi <= partecipanti and servono > 0}


def mostra_wishlist(chat_id, message_id, df, session):
    """
    La wishlist non e' un elenco di preferiti: e' un cruscotto.

    L'elenco dei nomi che ti sei salvato non ti dice niente che non sapessi
    gia'. Quello che serve sapere e' se sono ancora liberi, quanto puoi
    spingerti su ciascuno, e - per quelli andati - chi prendere al loro posto.
    """
    desiderati = list(session.get('wishlist', []))
    markup = InlineKeyboardMarkup(row_width=1)
    if not desiderati:
        markup.add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        return bot.edit_message_text(
            "⭐ <b>WISHLIST VUOTA</b>\n\n<i>Aggiungi un giocatore dalla sua "
            "scheda: qui vedrai se e' ancora libero e fin dove spingerti.</i>",
            chat_id, message_id, parse_mode="HTML", reply_markup=markup)

    registro_asta, disponibili, quadro, inflazione, _ = _quadro_piano(df, session)
    contesto = contesto_valori(df, session)
    venduti = set(n.lower() for n in registro_asta.venduti())

    liberi, andati = [], []
    for nome in desiderati:
        riga = df[df['Nome'].astype(str).str.lower() == str(nome).lower()]
        if riga.empty:
            continue
        riga = riga.iloc[0]
        (andati if str(nome).lower() in venduti else liberi).append(riga)

    righe = ["⭐ <b>WISHLIST</b>", ""]

    for riga in liberi:
        ruolo = str(riga.get('R', 'C')).upper()[:1]
        conti = piano.disponibile(quadro, ruolo)
        fasce = piano.fasce_di_spesa(conti['disponibile'], conti['mancanti'],
                                     session.get('strategia', 'equilibrata'))
        tetto_reparto = fasce[0] if fasce else conti['disponibile']
        scelte = consiglio.consiglia(disponibili, ruolo, contesto, tetto_reparto,
                                     conti['mancanti'], inflazione,
                                     session.get('lega_partecipanti', 8))
        suo = next((s for s in scelte if s['nome'] == str(riga['Nome'])), None)
        prezzo = int(_num(riga.get('Prezzo'), 1))
        tetto = suo['tetto'] if suo else min(prezzo, tetto_reparto)
        righe.append(f"🟢 <b>{html.escape(str(riga['Nome']))}</b> "
                     f"{ROLE_ICONS.get(ruolo, '')} · libero · vale {prezzo}, "
                     f"fino a <b>{tetto}</b>")
        markup.add(InlineKeyboardButton(f"🔍 {riga['Nome']} · fino a {tetto}",
                                        callback_data=f"sq_pl_{riga['Nome']}"))

    for riga in andati:
        ruolo = str(riga.get('R', 'C')).upper()[:1]
        conti = piano.disponibile(quadro, ruolo)
        fasce = piano.fasce_di_spesa(conti['disponibile'], conti['mancanti'],
                                     session.get('strategia', 'equilibrata'))
        scelte = consiglio.consiglia(disponibili, ruolo, contesto,
                                     fasce[0] if fasce else conti['disponibile'],
                                     conti['mancanti'], inflazione,
                                     session.get('lega_partecipanti', 8))
        # Un nome cancellato e' una perdita; un nome cancellato con accanto chi
        # prendere al suo posto e' una decisione gia' presa.
        if scelte and conti['mancanti'] > 0:
            sostituto = scelte[0]
            righe.append(f"⚫️ <s>{html.escape(str(riga['Nome']))}</s> · andato → "
                         f"al suo posto <b>{html.escape(sostituto['nome'])}</b> "
                         f"({sostituto['prezzo']} cr, fino a {sostituto['tetto']})")
            markup.add(InlineKeyboardButton(
                f"🔍 {sostituto['nome']} · al posto di {riga['Nome']}",
                callback_data=f"sq_pl_{sostituto['nome']}"))
        else:
            righe.append(f"⚫️ <s>{html.escape(str(riga['Nome']))}</s> · andato")

    if liberi:
        righe.append(f"\n<i>{len(liberi)} ancora liberi su {len(desiderati)}</i>")

    markup.row(InlineKeyboardButton("🚨 Chi prendo adesso",
                                    callback_data="menu_panic_start"),
               InlineKeyboardButton("🏠 Home", callback_data="go_home"))
    bot.edit_message_text("\n".join(righe), chat_id, message_id,
                          parse_mode="HTML", reply_markup=markup)


def mostra_plancia(chat_id, message_id, df, session):
    """
    La plancia dell'asta: un messaggio solo, che si riscrive.

    Prima ogni azione generava un messaggio nuovo e dopo mezz'ora si scorreva
    all'infinito per ritrovare il proprio budget. Qui la chat serve solo a
    far entrare i dati; l'unica uscita e' questa, sempre nello stesso posto.
    """
    registro_asta, disponibili, quadro, inflazione, campione = _quadro_piano(df, session)
    contesto = contesto_valori(df, session)

    # La fase non si imposta a mano: e' il primo reparto ancora scoperto.
    ruolo = quadro['scoperti'][0] if quadro['scoperti'] else None
    precedente = session.get('fase_asta')
    session['fase_asta'] = ruolo or 'A'

    # Reparto appena chiuso: il verdetto va dato UNA volta, subito, mentre hai
    # ancora in mente cosa hai speso. Dopo tre giocatori del reparto seguente
    # non interessa piu' a nessuno.
    if precedente and precedente != ruolo and precedente in quadro['reparti']:
        chiuso = quadro['reparti'][precedente]
        differenza = chiuso['speso'] - chiuso['previsto']
        # Tre casi, non due: dire "in linea col piano" e subito sotto "hai
        # sforato" e' il modo piu' rapido per far smettere di leggere.
        if abs(differenza) <= max(5, chiuso['previsto'] * 0.15):
            giudizio = "in linea col piano"
            avanzo = "niente da correggere: prosegui cosi'"
        elif differenza < 0:
            giudizio = f"<b>{differenza:+d}</b> rispetto al previsto"
            avanzo = "hai risparmiato: quei crediti valgono per i reparti che restano"
        else:
            giudizio = f"<b>{differenza:+d}</b> rispetto al previsto"
            avanzo = "hai sforato: da qui in avanti tocca stringere"
        bot.send_message(
            chat_id,
            f"{ROLE_ICONS[precedente]} <b>{consiglio.PLURALE_RUOLO[precedente].upper()} "
            f"CHIUSI</b>\nspesi <b>{chiuso['speso']}</b> cr · {giudizio}\n"
            f"<i>{avanzo}</i>\ncassa: <b>{registro_asta.budget()}</b> cr",
            parse_mode="HTML")

    righe = [f"🔨 <b>ASTA LIVE</b>"]
    if ruolo is None:
        righe.append("\n✅ Rosa completa. Puoi chiudere.")
    else:
        conti = piano.disponibile(quadro, ruolo)
        righe.append(f"{ROLE_ICONS[ruolo]} <b>{consiglio.PLURALE_RUOLO[ruolo]}</b> · "
                     f"te ne mancano <b>{conti['mancanti']}</b>")
        righe.append(f"💰 cassa <b>{registro_asta.budget()}</b> · "
                     f"per questo reparto <b>{conti['disponibile']}</b>")

    turno = turno_di_chi(session, registro_asta)
    if turno['noto']:
        righe.append("🔔 <b>TOCCA A TE: chiama</b>" if turno['tocca_a_me']
                     else f"⏳ tocca a te fra <b>{turno['mancano']}</b> chiamate")

    # Il giocatore su cui si sta rilanciando adesso
    in_asta = session.get('in_asta')
    if in_asta and ruolo:
        righe.append("")
        righe.append(_riga_semaforo(in_asta, session))

    if ruolo:
        stretta = scarsita(disponibili, ruolo, session, registro_asta, contesto)
        if stretta and stretta['stretta']:
            righe.append(f"\n⚠️ restano <b>{stretta['validi']}</b> "
                         f"{consiglio.PLURALE_RUOLO[ruolo]} buoni e ne servono "
                         f"<b>{stretta['servono']}</b> a tutta la lega: o compri "
                         f"adesso o paghi il doppio")
        if campione >= 8 and abs(inflazione - 1) >= 0.08:
            verso = "sopra" if inflazione > 1 else "sotto"
            righe.append(f"📈 stasera si paga il <b>"
                         f"{abs(round((inflazione - 1) * 100))}% {verso}</b> il listino")

    righe.append("\n<i>scrivi il nome per metterlo in asta · "
                 "poi solo la cifra per sapere se continuare</i>")

    markup = InlineKeyboardMarkup(row_width=2)
    if in_asta:
        markup.add(InlineKeyboardButton(f"✅ Preso io", callback_data="asta_preso_io"),
                   InlineKeyboardButton("🚫 L'ha preso un altro",
                                        callback_data="asta_preso_altri"))
    markup.row(InlineKeyboardButton("🚨 Chi chiamo", callback_data="menu_panic_start"),
               InlineKeyboardButton("🔔 Tocca a me", callback_data="asta_turno_mio"))
    markup.row(InlineKeyboardButton("📊 Come sto andando", callback_data="menu_andamento"),
               InlineKeyboardButton("🛑 Chiudi asta", callback_data="asta_end"))

    testo = "\n".join(righe)
    try:
        if not message_id:
            raise ValueError("nessuna plancia ancora aperta")
        bot.edit_message_text(testo, chat_id, message_id, parse_mode="HTML",
                              reply_markup=markup)
        session['id_plancia'] = message_id
    except Exception:
        messaggio = bot.send_message(chat_id, testo, parse_mode="HTML",
                                     reply_markup=markup)
        session['id_plancia'] = messaggio.message_id
    salva_sessioni()


def _riga_semaforo(in_asta, session):
    """Continua o molla, con il motivo in mezza riga."""
    nome = in_asta.get('nome', '?')
    tetto = int(in_asta.get('tetto', 0))
    offerta = in_asta.get('offerta')
    testa = (f"🎯 in asta: <b>{html.escape(str(nome))}</b> · "
             f"vale {in_asta.get('prezzo', '?')}, spingiti fino a <b>{tetto}</b>")
    if offerta is None:
        return testa + f"\n<i>{html.escape(str(in_asta.get('motivo', '')), quote=False)}</i>"
    if offerta < tetto:
        return testa + f"\n🟢 siamo a {offerta}: <b>CONTINUA</b> (ancora {tetto - offerta})"
    if offerta == tetto:
        return testa + f"\n🟡 siamo a {offerta}: <b>ULTIMO RILANCIO</b>"
    return testa + (f"\n🔴 siamo a {offerta}: <b>MOLLA</b>, "
                    f"sono {offerta - tetto} sopra quanto vale per te")


def mostra_pronostici(chat_id, message_id, df, session):
    """
    Le scommesse, con il fatto che le giustifica.

    Prima questo pulsante pescava un giocatore a caso da una lista e ne
    mostrava la figurina: una lotteria, non un consiglio. Adesso sono tre
    categorie separate, perche' rispondono a tre situazioni diverse - chi puo'
    esplodere, chi torna da un infortunio, chi ti garantisce i minuti - e
    mescolarle le renderebbe di nuovo un elenco.
    """
    disponibili = get_available_players(df, session)
    registro_asta = get_registro(session)

    # Quanto si puo' spendere per una scommessa: una frazione di quello che
    # resta per casella, non un numero fisso.
    slot_liberi = max(1, sum(SLOT_PER_RUOLO.values()) - len(registro_asta.rosa()))
    tetto = max(4, min(15, round(registro_asta.budget() / slot_liberi)))

    gruppi = pronostici.pronostici(disponibili, prezzo_massimo=tetto, limite=2)
    copertura = pronostici.copertura(disponibili) if hasattr(pronostici, 'copertura') else None

    righe = [f"🎯 <b>PRONOSTICI</b>  ·  fino a <b>{tetto} cr</b>", ""]
    markup = InlineKeyboardMarkup(row_width=1)
    trovati = 0

    for chiave, titolo, sottotitolo in ETICHETTE_PRONOSTICI:
        elenco = gruppi.get(chiave) or []
        if not elenco:
            continue
        trovati += len(elenco)
        righe.append(f"<b>{titolo}</b>\n<i>{sottotitolo}</i>")
        for g in elenco:
            righe.append(f"<b>{html.escape(g['nome'])}</b> "
                         f"({html.escape(g['squadra'])}) · {g['prezzo']} cr\n"
                         # quote=False: il motivo lo scriviamo noi e contiene
                         # apostrofi, che altrimenti escono come &#x27;
                         f"<i>{html.escape(g['motivo'], quote=False)}</i>")
            markup.add(InlineKeyboardButton(
                f"🔍 {g['nome']}  ·  {g['prezzo']} cr",
                callback_data=f"sq_pl_{g['nome']}"))
        righe.append("")

    if not trovati:
        righe.append("Nessun nome regge il confronto entro questo tetto: "
                     "meglio un titolare qualsiasi che una scommessa cara.")

    markup.row(InlineKeyboardButton("🚨 Panic", callback_data="menu_panic_start"),
               InlineKeyboardButton("🏠 Home", callback_data="go_home"))
    bot.edit_message_text("\n".join(righe).strip(), chat_id, message_id,
                          parse_mode="HTML", reply_markup=markup)


def mostra_andamento(chat_id, message_id, df, session):
    """
    Non una tabella: un giudizio. Il Panic risponde in dieci secondi mentre
    qualcuno rilancia; questo lo guardi nella pausa fra un reparto e l'altro,
    e vuoi sapere una cosa sola - se stai andando bene.
    """
    registro_asta, disponibili, quadro, inflazione, campione = _quadro_piano(df, session)
    contesto = contesto_valori(df, session)
    indice = {str(r['Nome']): r for _, r in df.iterrows()}

    punti_rosa, voti_p, voti_d, spesa_ruolo = 0.0, [], [], {'P': 0, 'D': 0, 'C': 0, 'A': 0}
    for voce in registro_asta.rosa():
        riga = indice.get(voce['nome'])
        spesa_ruolo[voce['ruolo']] = spesa_ruolo.get(voce['ruolo'], 0) + voce['prezzo']
        if riga is None:
            continue
        punti_rosa += consiglio.valuta(riga, contesto)['totale']
        if voce['ruolo'] == 'P':
            voti_p.append(_num(riga.get('Mv')))
        elif voce['ruolo'] == 'D':
            voti_d.append(_num(riga.get('Mv')))

    righe = ["📊 <b>COME STO ANDANDO</b>", ""]

    # 1. i reparti, uno per riga, col confronto sul previsto
    for ruolo in config.ORDINE_ASTA:
        dati_reparto = quadro['reparti'][ruolo]
        icona = ROLE_ICONS[ruolo]
        if dati_reparto['mancanti'] == 0:
            differenza = dati_reparto['speso'] - dati_reparto['previsto']
            giudizio = ("in linea" if abs(differenza) <= dati_reparto['previsto'] * 0.15
                        else (f"<b>{differenza:+d}</b> sul previsto"))
            righe.append(f"{icona} chiuso a <b>{dati_reparto['speso']}</b> cr · {giudizio}")
        elif dati_reparto['presi']:
            righe.append(f"{icona} {dati_reparto['presi']}/{dati_reparto['slot']} presi · "
                         f"<b>{dati_reparto['speso']}</b> cr spesi · "
                         f"finirlo costa ~<b>{dati_reparto['mercato']}</b>")
        else:
            righe.append(f"{icona} da fare · costa ~<b>{dati_reparto['mercato']}</b> cr")

    # 2. quanto rende quello che hai comprato
    righe.append("")
    if punti_rosa > 0:
        righe.append(f"⚽ la tua rosa vale <b>{punti_rosa:+.2f} punti a partita</b> "
                     f"in piu' di una rosa qualsiasi")
    if voti_p or voti_d:
        reparto = modificatore.valuta_reparto(voti_p, voti_d,
                                              session.get('tabella_modificatore'))
        if session.get('modificatore_attivo'):
            stato_reparto = ("completo" if reparto['completo']
                             else f"su {reparto['voti_contati']} voti su 4")
            righe.append(f"🛡️ modificatore: media <b>{reparto['media']:.2f}</b> → "
                         f"<b>+{reparto['punti']:g}</b> a partita <i>({stato_reparto})</i>")
            manca = modificatore.quanto_manca(reparto['media'],
                                              session.get('tabella_modificatore'))
            if manca and manca['guadagno'] > 0:
                righe.append(f"   └ con <b>{manca['distanza']:.2f}</b> di media in piu' "
                             f"guadagni <b>+{manca['guadagno']:g}</b> a partita")

    # 3. cosa mi aspetta
    righe.append("")
    da_finire = sum(quadro['reparti'][r]['mercato'] for r in quadro['scoperti'])
    cassa = registro_asta.budget()
    if not quadro['scoperti']:
        righe.append("✅ <b>rosa completa</b>: hai finito.")
    elif da_finire > cassa:
        righe.append(f"⚠️ finire costa ~<b>{da_finire}</b> cr e ne hai <b>{cassa}</b>: "
                     f"da qui in avanti tocca risparmiare.")
    else:
        margine = cassa - da_finire
        righe.append(f"✅ finire costa ~<b>{da_finire}</b> cr, ne hai <b>{cassa}</b>: "
                     f"<b>{margine}</b> di margine per alzare su chi ti serve.")
    if campione >= 8 and abs(inflazione - 1) >= 0.08:
        verso = "sopra" if inflazione > 1 else "sotto"
        righe.append(f"📈 stasera si paga il <b>{abs(round((inflazione-1)*100))}% {verso}</b> "
                     f"il listino, su {campione} vendite.")

    markup = InlineKeyboardMarkup(row_width=2)
    markup.row(InlineKeyboardButton("🚨 Panic", callback_data="menu_panic_start"),
               InlineKeyboardButton("🏠 Home", callback_data="go_home"))
    bot.edit_message_text("\n".join(righe), chat_id, message_id,
                          parse_mode="HTML", reply_markup=markup)


def mostra_panic(chat_id, message_id, df, session, ruolo_forzato=None):
    """
    Il Panic e' un verdetto, non un catalogo.

    Lo premi mentre qualcuno rilancia e hai dieci secondi: quello che serve e'
    un nome, un tetto e il motivo. Le alternative ci sono - per quando te lo
    soffiano o quando i crediti finiscono - ma sono risposte a situazioni
    diverse, non tre opzioni fra cui rimettersi a scegliere.
    """
    registro_asta, disponibili, quadro, inflazione, campione = _quadro_piano(df, session)
    markup = InlineKeyboardMarkup(row_width=1)

    if not quadro['scoperti']:
        markup.add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        return bot.edit_message_text(
            "🚨 <b>PANIC BUTTON</b>\n\nRosa completa: non ti serve nessuno.",
            chat_id, message_id, parse_mode="HTML", reply_markup=markup)

    ruolo = ruolo_forzato if ruolo_forzato in quadro['scoperti'] else quadro['scoperti'][0]
    conti = piano.disponibile(quadro, ruolo)
    fasce = piano.fasce_di_spesa(conti['disponibile'], conti['mancanti'],
                                 session.get('strategia', 'equilibrata'))
    tetto = fasce[0] if fasce else conti['disponibile']

    contesto = contesto_valori(df, session)
    scelte = consiglio.consiglia(disponibili, ruolo, contesto, tetto, conti['mancanti'],
                                 inflazione, session.get('lega_partecipanti', 8))

    intestazione = [
        f"🚨 <b>PANIC BUTTON</b>  ·  {ROLE_ICONS[ruolo]} {consiglio.PLURALE_RUOLO[ruolo]}",
        f"te ne mancano <b>{conti['mancanti']}</b>  ·  hai <b>{conti['disponibile']} cr</b> "
        f"per questo reparto",
    ]
    if conti['riserva'] > 0:
        dopo = "".join(ROLE_ICONS[r] for r in conti['successivi'])
        intestazione.append(f"🔒 <b>{conti['riserva']}</b> servono per {dopo}")
    if conti['in_rosso']:
        intestazione.append("⚠️ <b>sei in ritardo</b>: ai prezzi di adesso non basta "
                            "per finire, taglia su questo reparto")
    if campione >= 8 and abs(inflazione - 1) >= 0.08:
        verso = "sopra" if inflazione > 1 else "sotto"
        intestazione.append(f"📈 stasera si paga il <b>{abs(round((inflazione-1)*100))}% "
                            f"{verso}</b> il listino ({campione} vendite)")

    if not scelte:
        intestazione.append("\nNessuno disponibile entro il tetto: tocca prendere "
                            "a un credito quello che passa.")
    else:
        for scelta in scelte:
            intestazione.append(
                f"\n<b>{ETICHETTE_CONSIGLIO.get(scelta['etichetta'], scelta['etichetta'].upper())}</b>  "
                f"→  <b>{html.escape(scelta['nome'])}</b> "
                f"<i>({html.escape(scelta['squadra'])})</i>\n"
                f"vale <b>{scelta['prezzo']}</b>, spingiti fino a <b>{scelta['tetto']}</b>  ·  "
                f"{scelta['valore']:+.2f} punti a partita\n"
                f"<i>{scelta['motivo']}</i>")
            markup.add(InlineKeyboardButton(
                f"🔍 {scelta['nome']}  ·  vale {scelta['prezzo']}, "
                f"fino a {scelta['tetto']}" + (" ⚠️" if scelta['ballottaggio'] else ""),
                callback_data=f"sq_pl_{scelta['nome']}"))

    altri = [r for r in quadro['scoperti'] if r != ruolo]
    if altri:
        markup.row(*[InlineKeyboardButton(f"{ROLE_ICONS[r]} {r}",
                                          callback_data=f"panic_ru_{r}") for r in altri])
    markup.row(InlineKeyboardButton("📊 Come sto andando", callback_data="menu_andamento"),
               InlineKeyboardButton("🏠 Home", callback_data="go_home"))
    bot.edit_message_text("\n".join(intestazione), chat_id, message_id,
                          parse_mode="HTML", reply_markup=markup)

ETICHETTE_CONSIGLIO = {
    'prendi': '✅ PRENDI',
    'se lo perdi': '🔁 SE LO PERDI',
    'se resti a secco': '🪙 SE RESTI A SECCO',
}


def process_tabella_modificatore(message):
    """
    Legge la tabella scritta a mano: "6=1 6.5=3 7=6". Formato libero, perche'
    una tabella si imposta una volta e non deve richiedere un manuale.
    """
    session = get_session(message.from_user.id)
    coppie = []
    for pezzo in re.split(r"[\s,;]+", (message.text or "").replace(",", ".")):
        if "=" not in pezzo:
            continue
        media, _, punti = pezzo.partition("=")
        try:
            coppie.append((float(media), float(punti)))
        except ValueError:
            continue

    if not coppie:
        return bot.reply_to(
            message, "❌ Non ho capito. Serve <b>media=punti</b>, per esempio:\n"
            "<code>6=1  6.5=3  7=6  7.5=8</code>", parse_mode="HTML")

    session['tabella_modificatore'] = modificatore.normalizza_tabella(coppie)
    session['modificatore_attivo'] = True
    salva_sessioni()
    bot.reply_to(message,
                 "✅ <b>Tabella salvata</b>\n"
                 f"{modificatore.descrivi_tabella(session['tabella_modificatore'])}",
                 parse_mode="HTML")


def contesto_valori(df, session):
    """Il contesto di valutazione della lega: un solo posto, per tutte le
    schermate. Prima ogni pulsante si calcolava i riferimenti per conto suo e
    i numeri non coincidevano mai."""
    return consiglio.contesto_valutazione(
        df, session.get('modificatore_attivo', False),
        session.get('tabella_modificatore'))


def scouting_menu_keyboard():
    """Tutti gli strumenti di ricerca giocatori, in un posto solo."""
    markup = InlineKeyboardMarkup(row_width=2)
    # Gemme, Stakanovisti e Tappabuchi rispondevano tutti e tre alla stessa
    # domanda - "chi rende piu' di quanto costa" - con tre criteri diversi e
    # nessuno scritto da nessuna parte. Ora quella domanda ha una risposta
    # sola, i Pronostici, e qui restano solo gli attrezzi che cercano
    # qualcosa di specifico.
    markup.add(InlineKeyboardButton("👑  Top liberi", callback_data="menu_top_start"),
               InlineKeyboardButton("🎯  Rigoristi", callback_data="menu_rigoristi"))
    markup.add(InlineKeyboardButton("🛡️  Griglia difesa", callback_data="pro_griglia"),
               InlineKeyboardButton("🔥  Power index", callback_data="menu_power"))
    markup.add(InlineKeyboardButton("⚽  Formazione", callback_data="menu_formazione"))
    markup.add(InlineKeyboardButton("🔙  Indietro", callback_data="go_home"))
    return markup


# Telegram non trasforma una foto in testo: se il messaggio corrente e'
# un'immagine, edit_message_text fallisce. Invece di correggere quaranta
# chiamate, si rende tollerante quella una volta sola.
_edit_testo_originale = bot.edit_message_text


def _edit_testo_tollerante(text, chat_id=None, message_id=None, **extra):
    try:
        return _edit_testo_originale(text, chat_id=chat_id, message_id=message_id, **extra)
    except Exception:
        pass

    # secondo tentativo: forse e' una foto e basta cambiare la didascalia
    try:
        return bot.edit_message_caption(
            caption=text, chat_id=chat_id, message_id=message_id,
            parse_mode=extra.get('parse_mode'), reply_markup=extra.get('reply_markup'))
    except Exception:
        pass

    # ultimo: si sostituisce il messaggio
    try:
        bot.delete_message(chat_id, message_id)
    except Exception:
        pass
    return bot.send_message(
        chat_id, text, parse_mode=extra.get('parse_mode'),
        reply_markup=extra.get('reply_markup'),
        disable_web_page_preview=extra.get('disable_web_page_preview'))


bot.edit_message_text = _edit_testo_tollerante


def invia_immagine(chat_id, immagine, message_id=None, markup=None, didascalia=None):
    """
    Manda un PNG, sostituendo il messaggio precedente quando possibile.
    Telegram non converte un messaggio di testo in foto: se l'edit fallisce
    si cancella il vecchio e se ne manda uno nuovo, cosi' la chat resta pulita.
    """
    foto = io.BytesIO(immagine)
    foto.name = "fantahub.png"
    if message_id:
        try:
            bot.edit_message_media(
                media=InputMediaPhoto(foto, caption=didascalia, parse_mode="HTML"),
                chat_id=chat_id, message_id=message_id, reply_markup=markup)
            return
        except Exception:
            try:
                bot.delete_message(chat_id, message_id)
            except Exception:
                pass
            foto = io.BytesIO(immagine)
            foto.name = "fantahub.png"
    bot.send_photo(chat_id, foto, caption=didascalia, parse_mode="HTML", reply_markup=markup)


def taglia_didascalia(testo, limite=1024):
    """
    Telegram rifiuta le didascalie oltre 1024 caratteri e il messaggio non parte
    affatto. Si tagliano le righe dal fondo del blocco rischio, che e' l'unico
    di lunghezza imprevedibile, tenendo prezzo e cassa che stanno in fondo.
    """
    if len(testo) <= limite:
        return testo

    righe = testo.split("\n")
    # Le righe di dettaglio del rischio iniziano con l'indentazione a "└"
    while len(("\n".join(righe))) > limite and any("└" in r for r in righe):
        for indice in range(len(righe) - 1, -1, -1):
            if "└" in righe[indice]:
                righe.pop(indice)
                break

    testo = "\n".join(righe)
    return testo if len(testo) <= limite else testo[:limite - 1] + "…"


def barra(valore, totale, caselle=6):
    """Barra proporzionale: la lunghezza si legge prima della cifra."""
    try:
        if totale <= 0:
            return "▱" * caselle
        piene = max(0, min(caselle, round((float(valore) / float(totale)) * caselle)))
    except Exception:
        piene = 0
    return "▰" * piene + "▱" * (caselle - piene)


def send_dashboard(chat_id, user_id, message_id=None):
    session = get_session(user_id)
    stats = get_roster_stats(session)
    markup = main_menu_keyboard(session)

    dati = {
        'budget': session['budget'],
        'budget_iniziale': session.get('lega_budget_iniziale', 500),
        'slot_liberi': stats['slot_liberi'],
        'max_bid': stats['max_bid'],
        'conteggi': stats['counts'],
        'slot_totali': SLOT_PER_RUOLO_HOME,
        'stato': 'asta live' if session.get('fase_asta') else 'pre-asta',
    }

    try:
        invia_immagine(chat_id, interfaccia.disegna_dashboard_v2(dati), message_id, markup)
        return
    except Exception as e:
        print(f"⚠️ Dashboard grafica non disponibile ({e}): uso il testo.")

    # Ripiego testuale: il bot deve funzionare anche se il disegno fallisce
    conteggi = stats['counts']
    testo = (f"<b>FANTAHUB</b>\n💰 <b>{session['budget']}</b> cr · {stats['slot_liberi']} slot\n"
             f"🛑 offerta massima <b>{stats['max_bid']}</b> cr\n\n"
             + "  ·  ".join(f"{ROLE_ICONS[r]} {conteggi[r]}/{SLOT_PER_RUOLO_HOME[r]}"
                            for r in ('P', 'D', 'C', 'A')))
    if message_id:
        try:
            bot.edit_message_text(testo, chat_id, message_id, parse_mode="HTML", reply_markup=markup)
            return
        except Exception:
            pass
    bot.send_message(chat_id, testo, parse_mode="HTML", reply_markup=markup)


SLOT_PER_RUOLO = {'P': 3, 'D': 8, 'C': 8, 'A': 6}


def get_strategia_asta(fase, session, df=None):
    """Consiglio costruito sulla rosa vera, non un testo fisso per fase."""
    stats = get_roster_stats(session)
    avuti = stats['counts'].get(fase, 0)
    mancanti = max(0, SLOT_PER_RUOLO.get(fase, 0) - avuti)
    budget = session.get('budget', 0)
    slot_liberi = stats['slot_liberi']
    media_slot = (budget / slot_liberi) if slot_liberi > 0 else 0
    modificatore = session.get('modificatore_attivo', False)

    righe = [f"Ti mancano <b>{mancanti}</b> giocatori in {fase} "
             f"(hai {avuti}/{SLOT_PER_RUOLO.get(fase, 0)}). "
             f"Con {budget} cr e {slot_liberi} slot, la media e' <b>{media_slot:.0f} cr</b> a giocatore."]

    if df is not None and not df.empty:
        disponibili = get_available_players(df, session)
        nel_ruolo = disponibili[disponibili['R'] == fase].copy()
        if not nel_ruolo.empty:
            nel_ruolo['_prezzo'] = [fair_price(r, session) for _, r in nel_ruolo.iterrows()]
            nel_ruolo['_pv'] = nel_ruolo['Pv'].apply(_num) if 'Pv' in nel_ruolo.columns else 0
            alla_portata = nel_ruolo[nel_ruolo['_prezzo'] <= max(1, media_slot)]
            titolari_portata = alla_portata[alla_portata['_pv'] >= 25]

            migliore = nel_ruolo.sort_values('_prezzo', ascending=False).iloc[0]
            if migliore['_prezzo'] > budget:
                righe.append(f"⛔ Il migliore rimasto ({migliore['Nome']}, {int(migliore['_prezzo'])} cr) "
                             f"e' fuori dal tuo budget: punta sulla fascia sotto.")
            elif migliore['_prezzo'] > media_slot * 2.5 and mancanti > 2:
                righe.append(f"⚠️ {migliore['Nome']} costa {int(migliore['_prezzo'])} cr: "
                             f"prenderlo ti lascia {(budget - int(migliore['_prezzo'])) // max(1, slot_liberi - 1)} cr "
                             f"a slot per gli altri {slot_liberi - 1}.")

            righe.append(f"Alla tua media ci sono <b>{len(titolari_portata)}</b> titolari "
                         f"(25+ presenze) ancora liberi in {fase}.")
            if len(titolari_portata) <= mancanti and mancanti > 0:
                righe.append("🚨 Sono pochi per coprire gli slot: muoviti adesso o resterai coi fondi di magazzino.")

    if fase == 'D' and modificatore:
        righe.append("Modificatore attivo: conta il <b>voto puro</b>, non i bonus. "
                     "Guarda la lista Modificatore 6.5.")
    elif fase == 'P':
        righe.append("Sui portieri l'incrocio con il vice della stessa squadra vale piu' del nome.")

    return " ".join(righe)


def send_asta_dashboard(chat_id, user_id, message_id=None):
    """
    L'ingresso in asta mostra subito la plancia.

    Prima il wizard di setup finiva su una schermata diversa e la plancia
    compariva solo dopo aver scritto qualcosa: assurdo, perche' il momento in
    cui premi "avvia asta" e' esattamente quello in cui vuoi vedere dove sei.
    """
    session = get_session(user_id)
    df = load_data()
    if df is None:
        return bot.send_message(chat_id, "❌ Listone non disponibile.")
    if message_id:
        session['id_plancia'] = message_id
    mostra_plancia(chat_id, session.get('id_plancia'), df, session)

def send_player_card_view(chat_id, player_name, message_id, df, session, is_scommessa=False):
    p_data = df[df['Nome'] == player_name].iloc[0]
    sq_name, ruolo, fvm = p_data.get('Squadra', '-'), str(p_data.get('R', '-')), p_data.get('FVM', 0)
    photo_embed = f'<a href="{html.escape(str(p_data.get("PhotoURL", "")).strip())}">&#8203;</a>' if str(p_data.get("PhotoURL", "")).strip().startswith('http') else ''
    
    try: fvm_val = float(str(fvm).replace(',', '.'))
    except ValueError: fvm_val = 0.0

    lega_bud = session.get('lega_budget_iniziale', 500)
    lega_part = session.get('lega_partecipanti', 8)
    part_factor = 1 + ((lega_part - 8) * 0.025)

    # Il prezzo lo calcola il Master (colonna Prezzo, tarata su 8 squadre/500 crediti).
    # Qui si riscala solo su budget e numero di partecipanti della lega.
    fair_price_val = fair_price(p_data, session)

    max_rilancio = int(fair_price_val * 1.15)
    asta_stop = int(fair_price_val * 1.25)

    # Fascia = posizione nel proprio ruolo, non soglia in crediti: cosi' resta
    # valida anche cambiando budget o numero di partecipanti.
    # Il rango da solo non basta: "TOP" non dice se ne restano cinque o uno.
    disponibili = get_available_players(df, session)
    nomi_liberi = set(disponibili['Nome'].astype(str)) if disponibili is not None else None
    contesto = analisi.contesto_asta(player_name, df, nomi_liberi, lega_part)
    if contesto:
        # Una riga sola: fascia, posizione e quanti ne restano. Prima erano
        # due righe che sul telefono andavano a capo e si leggevano male.
        liberi = contesto['rimasti_fascia']
        fascia = (f"{contesto['etichetta']}  ·  <b>#{contesto['posizione']}</b> "
                  f"di {contesto['totale_ruolo']} {ruolo}")
        if contesto['totale_fascia']:
            fascia += (f"  ·  <b>{liberi}</b> liber{'o' if liberi == 1 else 'i'} "
                       f"in fascia")
    else:
        fascia = "—"

    stats = get_roster_stats(session)
    prof = analisi.profilo(p_data, analisi.statistiche_squadre(df),
                           analisi.baseline_ruoli(df), analisi.gerarchia_rigori(df))
    rischio = analisi.valuta_rischio(p_data, df, lega_part)
    banner = analisi.banner_infortunio(p_data)

    # Barre: la lunghezza si legge prima della cifra
    riga_titolarita = (f"Titolarità  <code>{barra(prof['presenze'], 38)}</code>  "
                       f"{prof['presenze']}/38" if prof['presenze'] else "")
    riga_bonus = (f"Bonus       <code>{barra(prof['bonus_partita'], 1.2)}</code>  "
                  f"{prof['bonus_partita']:+.2f}" if prof['fantamedia'] else "")
    saltate = prof.get('gare_saltate', 0)
    riga_integrita = (f"Integrità   <code>{barra(max(0, 38 - saltate), 38)}</code>  "
                      f"{saltate} salt." if saltate else "")
    barre = "\n".join(r for r in (riga_titolarita, riga_bonus, riga_integrita) if r)

    avvisi = analisi.formatta_rischio(rischio, compatto=False)
    macellaio = get_macellaio_info(player_name, df).strip()
    mostra_macellaio = macellaio and 'ALLARME' in macellaio

    # Da dove viene il bonus, e se e' davvero lui a tirare i rigori.
    riga_gol = analisi.riga_bonus(prof, analisi.gerarchia_rigori(df))

    # Modello e listino in disaccordo: detto a parole, non in percentuale.
    nota = analisi.nota_valore(prof)

    # Dove sta dentro il suo ruolo: un numero assoluto non si giudica da solo.
    riga_confronto = analisi.righe_percentili(analisi.percentili_ruolo(p_data, df))

    # Su difensori e portieri la fantamedia inganna: il modificatore si calcola
    # sui VOTI, e i gol subiti dalla squadra li abbassano. Si mostrano solo a
    # chi servono, e solo quando ci sono davvero.
    riga_difesa = ""
    if ruolo in ('P', 'D') and prof['voto_puro'] > 0:
        pezzi_difesa = [f"voto puro <b>{prof['voto_puro']:.2f}</b>"]
        subiti = prof.get('gol_subiti_partita')
        if subiti:
            pezzi_difesa.append(f"{html.escape(str(sq_name))} subisce "
                                f"<b>{subiti:.2f}</b> gol a partita")
        riga_difesa = "🛡️ " + "  ·  ".join(pezzi_difesa)

    # Il portiere si compra in coppia: il vice della stessa squadra e' il
    # paracadute, e il suo prezzo va saputo PRIMA di aprire l'asta sul titolare.
    riga_partner = ""
    if ruolo == 'P':
        partner = trova_partner_portiere(player_name, df)
        if partner:
            riga_altro = get_player_stats(partner, df)
            costo = fair_price(riga_altro, session) if riga_altro is not None else 1
            riga_partner = f"🧤 in coppia con <b>{html.escape(partner)}</b> ({costo} cr)"

    # Ti serve davvero? E' la domanda che viene prima del prezzo.
    slot_ruolo = SLOT_PER_RUOLO.get(ruolo, 0)
    presi = stats['counts'].get(ruolo, 0)
    mancanti = slot_ruolo - presi
    riga_slot = ""
    if slot_ruolo and mancanti > 0:
        media_slot = max(1, int(stats['max_bid'] / max(1, stats['slot_liberi'])))
        quanti = (f"<b>{mancanti} {ruolo}</b> da prendere" if presi == 0
                  else f"ne mancano <b>{mancanti}</b> su {slot_ruolo} {ruolo}")
        riga_slot = f"🎯 {quanti}  ·  ~{media_slot} cr a slot"
    elif slot_ruolo:
        riga_slot = f"🎯 reparto <b>{ruolo}</b> già completo"

    info_text = (
        f"{photo_embed}<b>{html.escape(player_name.upper())}</b>  ·  "
        f"{get_team_icon(sq_name)} {html.escape(sq_name)}  ·  <code>{html.escape(ruolo)}</code>\n"
        f"{fascia}\n"
        + (f"\n{banner}\n" if banner else "")
        + (f"\n{barre}\n" if barre else "")
        + (f"{riga_gol}\n" if riga_gol else "")
        + (f"{riga_difesa}\n" if riga_difesa else "")
        + (f"{riga_partner}\n" if riga_partner else "")
        + (f"\n{riga_confronto}\n" if riga_confronto else "")
        + f"\n{avvisi}\n"
        + (f"{macellaio}\n" if mostra_macellaio else "")
        + f"\n💰 <b>{fair_price_val} cr</b>  ·  max <b>{max_rilancio}</b>  ·  stop <b>{asta_stop}</b>\n"
        + (f"{nota}\n" if nota else "")
        + (f"{riga_slot}\n" if riga_slot else "")
        + f"💼 cassa <b>{session['budget']}</b> cr  ·  offerta max <b>{stats['max_bid']}</b>\n"
    )

    is_asta = session.get('fase_asta') is not None
    markup = InlineKeyboardMarkup(row_width=2)
    if is_asta:
        markup.add(InlineKeyboardButton("🙋‍♂️ L'ho preso IO!", callback_data=f"buy_{player_name}"), InlineKeyboardButton("👥 Preso da ALTRI", callback_data=f"taken_{player_name}"))
        markup.add(InlineKeyboardButton("🔙 Torna alla Dashboard Asta", callback_data="asta_resume"))
    else:
        markup.add(InlineKeyboardButton("⚡ Compra (Test)", callback_data=f"buy_{player_name}"), InlineKeyboardButton("🚫 Scarta", callback_data=f"taken_{player_name}"))

    markup.add(InlineKeyboardButton("📊 Storico (Master)", callback_data=f"stats_{player_name}"), InlineKeyboardButton("🔄 Sliding Doors", callback_data=f"sd_{player_name}"))
    markup.add(InlineKeyboardButton("🔮 Simula What-If", callback_data=f"wi_{player_name}"))
    
    in_wl = player_name in session.get('wishlist', [])
    if is_scommessa:
        markup.add(InlineKeyboardButton("❌ Rimuovi WL" if in_wl else "⭐ Aggiungi WL", callback_data=f"wl_toggle_{player_name}"), InlineKeyboardButton("🎯 Pronostici", callback_data="menu_scommessa_start"))
    else:
        markup.add(InlineKeyboardButton("❌ Rimuovi WL" if in_wl else "⭐ Aggiungi WL", callback_data=f"wl_toggle_{player_name}"))
        
    if not is_asta:
        # "Indietro" riporta alla lista da cui si e' arrivati (squadra, fascia,
        # rigoristi...): il contesto viene salvato dalle liste stesse.
        ritorno = session.get('ritorno')
        if ritorno and ritorno != "go_home":
            markup.add(InlineKeyboardButton("🔙 Indietro", callback_data=ritorno),
                       InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        else:
            markup.add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
    
    # Immagine piccola + testo: l'immagine fa solo la faccia e il prezzo,
    # i numeri stanno nella didascalia dove si possono leggere e copiare.
    dati_striscia = {
        'nome': player_name,
        'squadra': str(sq_name),
        'ruolo': ruolo,
        'fascia': (f"{contesto['etichetta'].split(maxsplit=1)[-1]}  #{contesto['posizione']} "
                   f"di {contesto['totale_ruolo']}" if contesto else ''),
        'prezzo': fair_price_val, 'max': max_rilancio, 'stop': asta_stop,
        'foto_api': str(p_data.get('FotoAPI', '') or ''),
        'foto': str(p_data.get('PhotoURL', '') or ''),
    }

    try:
        invia_immagine(chat_id, interfaccia.disegna_striscia(dati_striscia),
                       message_id, markup, didascalia=taglia_didascalia(info_text))
        return
    except Exception as e:
        print(f"⚠️ Striscia grafica non disponibile ({e}): uso il solo testo.")

    try:
        bot.edit_message_text(info_text, chat_id, message_id, parse_mode="HTML",
                              reply_markup=markup, disable_web_page_preview=False)
    except Exception:
        try:
            bot.delete_message(chat_id, message_id)
        except Exception:
            pass
        bot.send_message(chat_id, info_text, parse_mode="HTML", reply_markup=markup,
                         disable_web_page_preview=False)


def system_menu_keyboard():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("📥 Download Remoto", callback_data="force_download_listone"), InlineKeyboardButton("🔄 Sync Dati", callback_data="reload_excel"))
    markup.add(InlineKeyboardButton("⚠️ Reset Rosa", callback_data="reset_confirm"), InlineKeyboardButton("🧹 Pulisci Schermo", callback_data="clear_screen"))
    markup.add(InlineKeyboardButton("🔙 Indietro", callback_data="go_home"))
    return markup

def pro_menu_keyboard():
    """Il vecchio menu PRO e' confluito nello scouting: si evita il doppione."""
    return scouting_menu_keyboard()

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
        registro_asta = get_registro(session)
        registro_asta.segna(player_name, costo, str(ruolo), str(squadra), reg.IO)
        salva_registro(registro_asta, session, chat_id)
        titolo_acquisto = f"✅ <b>{html.escape(player_name.upper())}</b> acquistato per <code>{costo} cr.</code>!"
    else:
        titolo_acquisto = f"🧪 <b>SIMULAZIONE: {html.escape(player_name.upper())} a {costo} cr.</b>\n<i>(Non salvato in Rosa)</i>"
    
    lega_bud, lega_part = session.get('lega_budget_iniziale', 500), session.get('lega_partecipanti', 8)
    fair_price_val = fair_price(row, session)
    
    if costo <= fair_price_val * 0.75: giudizio = f"🔥 <b>AFFARE D'ORO!</b> Hai risparmiato circa {fair_price_val - costo} cr."
    elif costo <= fair_price_val * 0.95: giudizio = f"✅ <b>OTTIMO COLPO!</b> Preso sotto costo (Fair Price: {fair_price_val} cr)."
    elif costo <= fair_price_val * 1.15: giudizio = f"⚖️ <b>PREZZO GIUSTO.</b> Pagato esattamente il suo valore."
    elif costo <= fair_price_val * 1.30: giudizio = f"⚠️ <b>LEGGERO OVERPAY.</b> Pagato un po' di più (Fair Price: {fair_price_val} cr)."
    else: giudizio = f"🚨 <b>SALASSO!</b> Strapagato! Hai speso ben {costo - fair_price_val} cr. in più."
        
    bot.send_message(chat_id, f"{titolo_acquisto}\n\n📊 <b>Valutazione Acquisto:</b>\n{giudizio}", parse_mode="HTML")
    
    if ruolo == 'P':
        riserve = df[(df['R'] == 'P') & (df['Squadra'] == squadra) & (df['Nome'] != player_name)].sort_values(by='FVM', ascending=False).head(2)
        r_nomi = [r['Nome'] for _, r in riserve.iterrows()]
        
        testo_p = f"🧤 <b>HAI PRESO UN PORTIERE! Completa il reparto:</b>\n\n"
        if r_nomi: testo_p += f"🔒 <b>Riserve {squadra}:</b> (da 1 cr): <code>{', '.join(r_nomi)}</code>\n\n"
        
        mk_port = InlineKeyboardMarkup(row_width=1)
        for r_n in r_nomi: mk_port.add(InlineKeyboardButton(f"⭐ Aggiungi {r_n} a Wishlist", callback_data=f"wl_add_{r_n}"))
        bot.send_message(chat_id, testo_p, parse_mode="HTML", reply_markup=mk_port if r_nomi else None)
            
    p_n = trova_partner_portiere(player_name, df)
    if p_n:
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
    fair_price_val = fair_price(row, session)

    budget_left, slots_left = session['budget'] - hyp_price, get_roster_stats(session)['slot_liberi'] - 1
    if slots_left < 0: return bot.send_message(chat_id, "❌ Hai già la rosa piena!", parse_mode="HTML")
        
    avg_left = budget_left / slots_left if slots_left > 0 else 0
    analisi = f"🔥 <b>PREZZO D'OCCASIONE!</b> Valore: <code>{fair_price_val}</code>" if hyp_price <= fair_price_val * 0.70 else f"✅ <b>CONGRUITA:</b> Linea con il Fair Price (<code>{fair_price_val}</code>)." if hyp_price <= fair_price_val * 1.15 else f"🚨 <b>OVERPAY RISCHIOSO:</b> +<code>{hyp_price - fair_price_val}</code> cr. del valore ideale."

    avail = get_available_players(df, session)
    target = avail[(avail['R'] == ruolo) & (avail['Nome'] != player_name)].copy()
    target['base_p'] = [fair_price(t, session) for _, t in target.iterrows()]
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

    # Dopo un riavvio di Render il file delle sessioni e' sparito, ma il
    # taccuino fissato in chat no: si rimette in piedi da li' prima di
    # mostrare qualunque cosa, altrimenti la dashboard direbbe 500 crediti
    # e rosa vuota a chi ne ha gia' comprati dieci.
    listone = load_data()
    if listone is not None:
        recuperato = recupera_taccuino(m.chat.id, session, listone)
        if recuperato:
            bot.send_message(
                m.chat.id,
                f"\U0001F4D3 <b>Taccuino ritrovato</b>\n"
                f"{len(recuperato.voci)} vendite, {len(recuperato.rosa())} tuoi, "
                f"cassa <b>{recuperato.budget()}</b> cr.",
                parse_mode="HTML")

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
        # I nomi con accenti o apostrofi (Ndicka, Perez, Dell'Orco) non passavano
        match = re.search(r"(?:preso|comprato|ho preso|aggiudicato)?\s*([^\d]+?)\s*(?:a|per)?\s*(\d+)",
                          testo, re.UNICODE)
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
        fair_price_val = fair_price(row, session)
        giudizio = f"🔥 <b>AFFARE!</b>" if costo <= fair_price_val * 0.75 else f"✅ <b>OTTIMO!</b>" if costo <= fair_price_val * 0.95 else f"⚖️ <b>GIUSTO.</b>" if costo <= fair_price_val * 1.15 else f"🚨 <b>SALASSO!</b>"
        
        bot.reply_to(message, f"{titolo}\n\n📊 <b>Valutazione:</b>\n{giudizio}", parse_mode="HTML")
        send_asta_dashboard(message.chat.id, message.from_user.id) if is_asta else send_dashboard(message.chat.id, message.from_user.id)
    except Exception: bot.reply_to(message, "❌ Errore acquisto rapido.")

@bot.message_handler(func=lambda m: m.text and not m.text.startswith('/'))
def testo_libero(message):
    """
    Una riga di testo puo' voler dire due cose: "segna questo acquisto" oppure
    "cercami questo giocatore". Le si distingue dal prezzo.

        dimarco 90       -> venduto agli altri a 90
        dimarco 90 io    -> l'ho preso io a 90
        dimarco          -> cercalo

    Il marcatore sta solo sul MIO acquisto perche' in una lega da 8 squadre
    nove vendite su dieci non sono mie: il caso frequente non deve costare
    neanche un carattere.
    """
    testo = (message.text or "").strip()
    df, session = load_data(), get_session(message.from_user.id)
    if df is None or len(testo) < 2:
        return

    # ------------------------------------------------------------------
    # ASTA LIVE: durante una chiamata si hanno dieci secondi, non trenta.
    # Una cifra da sola vuol dire "siamo arrivati a tanto": non serve
    # ripetere il nome, il giocatore in asta lo sa gia' il bot.
    # ------------------------------------------------------------------
    if session.get('fase_asta') and testo.isdigit() and session.get('in_asta'):
        session['in_asta']['offerta'] = int(testo)
        salva_sessioni()
        try:
            bot.delete_message(message.chat.id, message.message_id)
        except Exception:
            pass
        return mostra_plancia(message.chat.id, session.get('id_plancia'), df, session)

    # All'asta si scrive, non si cerca il pulsante giusto: "annulla" deve
    # funzionare digitato, che e' il modo in cui viene in mente di usarlo
    # quando hai sbagliato una cifra e stanno gia' chiamando il prossimo.
    if testo.lower() in ("annulla", "annullo", "indietro", "undo", "cancella"):
        registro_asta = get_registro(session)
        tolta = registro_asta.annulla_ultima()
        if not tolta:
            return bot.reply_to(message, "Non c'e' niente da annullare.")
        salva_registro(registro_asta, session, message.chat.id)
        return bot.reply_to(
            message,
            f"\u21a9\ufe0e Tolto <b>{html.escape(str(tolta['nome']))}</b> "
            f"({tolta['prezzo']} cr) \u00b7 cassa <b>{registro_asta.budget()}</b>",
            parse_mode="HTML")

    nome, prezzo, acquirente = reg.interpreta(testo)
    if nome and prezzo is not None:
        return segna_vendita(message, nome, prezzo, acquirente, df, session)

    matches = df[df['Nome'].astype(str).str.lower().str.contains(testo.lower(), na=False)]
    if matches.empty:
        return bot.reply_to(message, "❌ Nessun giocatore trovato.")
    if len(matches) == 1:
        # In asta live il nome non apre la figurina: mette il giocatore sotto
        # il semaforo. La figurina la si guarda prima, non mentre si rilancia.
        if session.get('fase_asta'):
            return metti_in_asta(message, matches.iloc[0], df, session)
        return send_player_card_view(message.chat.id, matches.iloc[0]['Nome'], None, df, session)

    markup = InlineKeyboardMarkup(row_width=1)
    for _, row in matches.head(10).iterrows():
        markup.add(InlineKeyboardButton(
            f"{ROLE_ICONS.get(str(row.get('R','C')),'')} {row['Nome']} ({row.get('Squadra','-')})",
            callback_data=f"sq_pl_{row['Nome']}"))
    bot.reply_to(message, f"🔍 Scegli il giocatore esatto per <b>{html.escape(testo)}</b>:",
                 parse_mode="HTML", reply_markup=markup)


def segna_vendita(message, nome, prezzo, acquirente, df, session):
    """
    Scrive nel taccuino e risponde con quello che serve SU QUEL GIOCATORE.

    Prima il pulsante portava al piano del primo reparto ancora scoperto:
    segnavi un centrocampista e ti usciva la lista dei portieri. Ma la domanda
    dopo una vendita non e' "come sto messo in generale", e' "quello li' chi me
    lo sostituisce": stesso ruolo, stessa fascia di prezzo, ancora libero.
    """
    riga = dati.cerca_giocatore(nome, df)
    if riga is None:
        return bot.reply_to(message, f"❌ <b>{html.escape(nome)}</b> non e' nel listone.",
                            parse_mode="HTML")

    nome_vero = str(riga['Nome'])
    ruolo = str(riga.get('R', 'C')).upper()[:1]
    registro_asta = get_registro(session)
    mio = acquirente == reg.IO

    if mio:
        stato_prima = dati.stato_rosa(session)
        if prezzo > stato_prima['max_bid']:
            return bot.reply_to(
                message,
                f"⚠️ <b>{prezzo} cr</b> supera la tua offerta massima "
                f"(<b>{stato_prima['max_bid']}</b>): con {stato_prima['slot_liberi']} slot "
                f"da riempire non ti resterebbe un credito a casella.",
                parse_mode="HTML")

    era_in_wishlist = nome_vero in session.get('wishlist', [])
    registro_asta.segna(nome_vero, prezzo, ruolo, str(riga.get('Squadra', '')),
                        reg.IO if mio else "altri")
    salva_registro(registro_asta, session, message.chat.id)

    destinazione = "🟢 <b>preso da te</b>" if mio else "⚪ agli altri"
    listino = int(_num(riga.get('Prezzo'), 1))
    confronto = ""
    if listino >= 5 and prezzo:
        scarto = round((prezzo / listino - 1) * 100)
        if abs(scarto) >= 15:
            confronto = f"  ·  {scarto:+d}% sul listino ({listino})"

    stato = dati.stato_rosa(session)
    righe = [f"✓ <b>{html.escape(nome_vero)}</b> {prezzo} cr → {destinazione}{confronto}",
             f"💰 cassa <b>{session['budget']}</b>  ·  {stato['slot_liberi']} slot da fare"]

    markup = InlineKeyboardMarkup(row_width=1)
    mancanti = SLOT_PER_RUOLO.get(ruolo, 0) - stato['counts'].get(ruolo, 0)

    # Se te l'hanno soffiato e quel ruolo ti serve ancora, i sostituti si
    # vedono adesso: e' il momento in cui la risposta conta, non tre menu dopo.
    if not mio and mancanti > 0:
        # Stesso identico calcolo del Panic: il tetto viene dal piano, non da
        # una formula locale. Prima qui usciva 30 e nel Panic 34, ed erano due
        # conti diversi sullo stesso momento dell'asta.
        _, disponibili, quadro, _, _ = _quadro_piano(df, session)
        conti = piano.disponibile(quadro, ruolo)
        fasce = piano.fasce_di_spesa(conti['disponibile'], conti['mancanti'],
                                     session.get('strategia', 'equilibrata'))
        tetto = fasce[0] if fasce else conti['disponibile']
        _, _, _, inflazione_ora, _ = _quadro_piano(df, session)
        scelte = consiglio.consiglia(disponibili, ruolo, contesto_valori(df, session),
                                     tetto, conti['mancanti'], inflazione_ora,
                                     session.get('lega_partecipanti', 8))
        if scelte:
            righe.append("⭐ <i>era in wishlist</i> — al suo posto:" if era_in_wishlist
                         else f"<i>chi prendere adesso, fino a {tetto} cr:</i>")
            for scelta in scelte[:2]:
                righe.append(f"<b>{html.escape(scelta['nome'])}</b> "
                             f"({html.escape(scelta['squadra'])}) · vale "
                             f"<b>{scelta['prezzo']}</b> · {scelta['valore']:+.2f} pt/partita\n"
                             f"<i>{scelta['motivo']}</i>")
                markup.add(InlineKeyboardButton(
                    f"🔍 {scelta['nome']}  ·  {scelta['prezzo']} cr",
                    callback_data=f"sq_pl_{scelta['nome']}"))
        else:
            righe.append(f"<i>nessun {ruolo} alla tua portata ancora libero</i>")

    coda = [InlineKeyboardButton("↩︎ Annulla", callback_data="reg_annulla")]
    if mancanti > 0:
        coda.append(InlineKeyboardButton(f"🔨 Piano {ruolo}",
                                         callback_data=f"panic_ru_{ruolo}"))
    markup.row(*coda)

    bot.reply_to(message, "\n".join(righe), parse_mode="HTML", reply_markup=markup)

@bot.message_handler(content_types=['document'])
def handle_document(message):
    fname = message.document.file_name.lower()
    if not fname.endswith(('.csv', '.xlsx', '.xls')):
        return bot.reply_to(message, "❌ Invia solo file <code>.csv</code> o <code>.xlsx</code>!", parse_mode="HTML")

    temporaneo = "upload_temp" + os.path.splitext(fname)[1]
    try:
        with open(temporaneo, 'wb') as f:
            f.write(bot.download_file(bot.get_file(message.document.file_id).file_path))

        # Un .xlsx va convertito, non rinominato: salvarlo come .csv rompeva il bot.
        # I file di Fantacalcio hanno una riga di titolo prima delle intestazioni:
        # si prova header=0 e, se le colonne non tornano, header=1.
        if fname.endswith(('.xlsx', '.xls')):
            nuovo = pd.read_excel(temporaneo)
            if 'Nome' not in nuovo.columns:
                nuovo = pd.read_excel(temporaneo, header=1)
        else:
            try:
                nuovo = pd.read_csv(temporaneo, sep=';', on_bad_lines='skip')
            except Exception:
                nuovo = pd.read_csv(temporaneo, sep=',', on_bad_lines='skip')

        # Il listone delle quotazioni NON e' il Master: non ha FVM, Prezzo,
        # infortuni e foto. Accettarlo qui significava buttare via meta' dei dati
        # fino al download successivo. Le quotazioni vanno nel repo del motore.
        if 'Prezzo' not in nuovo.columns and 'FVM' not in nuovo.columns:
            return bot.reply_to(
                message,
                "❌ <b>Questo sembra il listone quotazioni</b>, non il Master.\n"
                "Caricarlo qui cancellerebbe FVM, prezzi e infortuni.\n\n"
                "Mettilo invece nel repository <code>fanta-master-ai</code>: "
                "il motore lo userà al prossimo giro notturno e il bot scaricherà "
                "il Master aggiornato da solo.", parse_mode="HTML")

        ok, mancanti = dati.salva_da_dataframe(nuovo)
        if not ok:
            return bot.reply_to(
                message,
                f"❌ <b>File non valido</b>: mancano {', '.join(mancanti)}.\n"
                f"Il listone precedente NON è stato toccato.", parse_mode="HTML")

        avviso = "" if 'Prezzo' in nuovo.columns else "\n⚠️ <i>Manca la colonna Prezzo: i valori saranno stimati.</i>"
        bot.reply_to(message, f"✅ <b>LISTONE AGGIORNATO</b>: {len(nuovo)} giocatori.{avviso}", parse_mode="HTML")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Errore caricamento: {str(e)}")
    finally:
        if os.path.exists(temporaneo):
            try:
                os.remove(temporaneo)
            except Exception:
                pass


# ==========================================
# GESTIONE CALLBACKS (Bottoni Inline)
# ==========================================
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    safe_answer_callback(call.id)
    user_id, chat_id = call.from_user.id, call.message.chat.id
    session, df = get_session(user_id), load_data()

    # Le schermate-elenco diventano il punto di ritorno della card giocatore:
    # cosi' "Indietro" riporta alla lista giusta invece che alla Home.
    if (call.data.startswith(("sq_ru_", "rig_sq_", "menu_top_ru_",
                              "menu_modificatore"))
            or call.data in ("pro_griglia", "menu_wishlist", "menu_rosa",
                             "menu_rigoristi", "sq_start", "menu_power",
                             "menu_scommessa_start")):
        session['ritorno'] = call.data
    elif call.data == "go_home":
        session['ritorno'] = None

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
        attivo = session.get('modificatore_attivo', False)
        tabella = session.get('tabella_modificatore') or modificatore.TABELLA_STANDARD
        markup = InlineKeyboardMarkup(row_width=3)
        markup.row(InlineKeyboardButton("💰 300", callback_data="imposta_bud_300"),
                   InlineKeyboardButton("💰 500", callback_data="imposta_bud_500"),
                   InlineKeyboardButton("💰 1000", callback_data="imposta_bud_1000"))
        markup.row(InlineKeyboardButton("👥 8", callback_data="imposta_part_8"),
                   InlineKeyboardButton("👥 10", callback_data="imposta_part_10"),
                   InlineKeyboardButton("👥 12", callback_data="imposta_part_12"))
        markup.add(InlineKeyboardButton(
            f"🛡️ Modificatore difesa: {'ATTIVO' if attivo else 'spento'}",
            callback_data="imposta_modif"))
        if attivo:
            markup.add(InlineKeyboardButton("✏️ Cambia la tabella",
                                            callback_data="imposta_tabella"))
        markup.add(InlineKeyboardButton("🔄 Reset", callback_data="imposta_reset"),
                   InlineKeyboardButton("🏠 Home", callback_data="go_home"))

        righe = ["⚙️ <b>LA MIA LEGA</b>",
                 f"💰 Budget: <code>{session.get('lega_budget_iniziale', 500)} cr</code>",
                 f"👥 Partecipanti: <code>{session.get('lega_partecipanti', 8)}</code>",
                 f"🛡️ Modificatore: <code>{'attivo' if attivo else 'spento'}</code>"]
        if attivo:
            righe += [f"<i>{modificatore.descrivi_tabella(tabella)}</i>",
                      "",
                      "<i>Col modificatore il valore di portieri e difensori sta "
                      "nella media voto, non nei bonus: il bot ne tiene conto in "
                      "ogni consiglio.</i>"]
        bot.edit_message_text("\n".join(righe), chat_id, call.message.message_id,
                              parse_mode="HTML", reply_markup=markup)

    elif call.data == "imposta_modif":
        session['modificatore_attivo'] = not session.get('modificatore_attivo', False)
        salva_sessioni()
        safe_answer_callback(call.id, "🛡️ Modificatore " +
                             ("attivato" if session['modificatore_attivo'] else "spento"), False)
        call.data = "menu_impostazioni_lega"
        handle_callbacks(call)

    elif call.data == "imposta_tabella":
        tabella = session.get('tabella_modificatore') or modificatore.TABELLA_STANDARD
        esempio = "  ".join(f"{s:g}={p:g}" for s, p in modificatore.normalizza_tabella(tabella))
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(InlineKeyboardButton("↩︎ Torna allo standard",
                                        callback_data="tabella_standard"),
                   InlineKeyboardButton("🔙 Lega", callback_data="menu_impostazioni_lega"))
        avviso = bot.edit_message_text(
            "✏️ <b>TABELLA DEL MODIFICATORE</b>\n\n"
            f"Adesso: <code>{esempio}</code>\n\n"
            "Scrivimi la tua nella stessa forma, <b>media=punti</b> separati da "
            "spazio. Per esempio:\n<code>6=1  6.5=3  7=6  7.5=8</code>",
            chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)
        bot.register_next_step_handler(avviso, process_tabella_modificatore)

    elif call.data == "tabella_standard":
        session['tabella_modificatore'] = None
        salva_sessioni()
        safe_answer_callback(call.id, "✅ Tabella standard ripristinata", False)
        call.data = "menu_impostazioni_lega"
        handle_callbacks(call)

    elif call.data.startswith("imposta_bud_"):
        # Si sposta il tetto, non la cassa: se hai gia' comprato, quello che hai
        # speso resta speso. Prima cambiare budget a meta' asta te lo azzerava.
        nuovo_budget = int(call.data.replace("imposta_bud_", ""))
        speso = session.get('lega_budget_iniziale', 500) - session.get('budget', 500)
        session['lega_budget_iniziale'] = nuovo_budget
        session['budget'] = max(0, nuovo_budget - speso)
        safe_answer_callback(call.id, f"✅ Budget: {nuovo_budget} cr (cassa {session['budget']})!", True)
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

    elif call.data == "menu_top_start":
        # Gemme e' confluito nei Pronostici, ma Top liberi condivideva con lui
        # lo stesso blocco: toglierne uno faceva sparire anche l'altro.
        bot.edit_message_text(
            "👑 <b>TOP LIBERI</b> - Scegli ruolo:", chat_id, call.message.message_id,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(row_width=4).add(
                *[InlineKeyboardButton(f"{ROLE_ICONS[r]} {r}",
                                       callback_data=f"menu_top_ru_{r}")
                  for r in ['P', 'D', 'C', 'A']]).add(
                InlineKeyboardButton("🔙 Strumenti", callback_data="menu_scouting"),
                InlineKeyboardButton("🏠 Home", callback_data="go_home")))

    elif call.data == "menu_rigoristi":
        gerarchie = gerarchie_rigoristi(df)
        if not gerarchie:
            bot.edit_message_text("🎯 <b>RADAR RIGORISTI</b>\n\n⚠️ Il Master non contiene la colonna <code>Rc</code>: aggiorna il listone.",
                                  chat_id, call.message.message_id, parse_mode="HTML",
                                  reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🏠 Home", callback_data="go_home")))
        else:
            markup = InlineKeyboardMarkup(row_width=2)
            for sq in sorted(gerarchie):
                markup.add(InlineKeyboardButton(f"{get_team_icon(sq)} {sq}", callback_data=f"rig_sq_{sq}"))
            markup.add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
            bot.edit_message_text("🎯 <b>RADAR RIGORISTI</b>\n<i>Rigori calciati nella scorsa stagione. Scegli la squadra:</i>",
                                  chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif call.data.startswith("rig_sq_"):
        squadra = call.data.replace("rig_sq_", "")
        dati = gerarchie_rigoristi(df, squadra).get(squadra, {})
        markup = InlineKeyboardMarkup(row_width=1)
        for voce in dati.get('rigoristi', []):
            nome = voce.rsplit(" (", 1)[0]
            markup.add(InlineKeyboardButton(f"⚽ {voce}", callback_data=f"sq_pl_{nome}"))
        markup.add(InlineKeyboardButton("🔙 Squadre", callback_data="menu_rigoristi"),
                   InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text(f"🎯 <b>{get_team_icon(squadra)} {squadra}</b>\n<i>Fra parentesi i rigori calciati. Tocca per la card:</i>",
                              chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif call.data == "menu_power":
        baseline = analisi.baseline_ruoli(df)
        hot, freddi = [], []
        for p in session.get('rosa', []):
            row = get_player_stats(p['nome'], df)
            if row is None:
                continue
            prof = analisi.profilo(row, None, baseline)
            riferimento = baseline.get(prof['ruolo'], (6.0, 0.3))[0]
            scarto = prof['fantamedia_ponderata'] - riferimento
            voce = f"{ROLE_ICONS.get(prof['ruolo'], '')} {prof['nome']}: {prof['fantamedia']:.2f} ({scarto:+.2f} sul ruolo)"
            (hot if scarto >= 0.15 else freddi).append((scarto, voce))
        hot.sort(reverse=True); freddi.sort(reverse=True)
        testo = "⚡ <b>POWER RANKING ROSA</b>\n<i>Confronto con la media del proprio ruolo</i>\n━━━━━━━━━━━━━━━━━━━━\n"
        testo += ("<b>Sopra la media:</b>\n" + "\n".join(v for _, v in hot) + "\n\n") if hot else ""
        testo += ("<b>Sotto la media:</b>\n" + "\n".join(v for _, v in freddi)) if freddi else ""
        if not hot and not freddi:
            testo = "⚡ <b>POWER RANKING</b>\n\nRosa vuota: compra qualcuno e torna qui."
        bot.edit_message_text(testo, chat_id, call.message.message_id, parse_mode="HTML",
                              reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🏠 Home", callback_data="go_home")))

    elif call.data == "menu_sistema": bot.edit_message_text("⚙️ <b>SISTEMA</b>", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=system_menu_keyboard())
    elif call.data == "reload_excel": 
        load_data(force_reload=True)
        bot.send_message(chat_id, "⚡ <b>Dati dal Master sincronizzati!</b>", parse_mode="HTML")
    elif call.data == "reset_confirm":
        user_sessions[user_id] = {'budget': session.get('lega_budget_iniziale', 500), 'rosa': [], 'wishlist': session.get('wishlist', []), 'scartati': [], 'compare_p1': None, 'lega_budget_iniziale': session.get('lega_budget_iniziale', 500), 'lega_partecipanti': session.get('lega_partecipanti', 8), 'modificatore_attivo': session.get('modificatore_attivo', False), 'fase_asta': None}
        send_dashboard(chat_id, user_id, call.message.message_id)

    elif call.data == "menu_scouting":
        bot.edit_message_text(
            "🔎 <b>SCOUTING</b>\n<i>Trova i giocatori giusti per il tuo budget</i>",
            chat_id, call.message.message_id, parse_mode="HTML",
            reply_markup=scouting_menu_keyboard())

    elif call.data == "menu_pro": bot.edit_message_text("🛠️ <b>STRUMENTI PRO</b>", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=pro_menu_keyboard())
    elif call.data == "pro_griglia":
        avail = get_available_players(df, session)
        griglia = analisi.griglia_difensiva(avail)
        classifica = analisi.classifica_difensiva(avail)[:6]
        markup = InlineKeyboardMarkup(row_width=1)
        if griglia is not None and not griglia.empty:
            for _, r in griglia.head(10).iterrows():
                markup.add(InlineKeyboardButton(
                    f"🛡️ {r['Nome']} ({r['Squadra']}) · Fm {_num(r.get('Fm')):.2f} · {int(_num(r.get('Prezzo'), 1))} cr",
                    callback_data=f"sq_pl_{r['Nome']}"))
        markup.add(InlineKeyboardButton("🔙 Menu PRO", callback_data="menu_pro"))
        elenco = ", ".join(f"{sq} ({d['gol_subiti_partita']})" for sq, d in classifica)
        bot.edit_message_text(
            f"🛡️ <b>GRIGLIA DIFENSIVA</b>\n<i>Difensori piu' impiegati delle squadre meno battute</i>\n\n"
            f"<b>Gol subiti a partita:</b> {elenco}",
            chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif call.data.startswith("stats_"):
        p = call.data.replace("stats_", "")
        tastiera = InlineKeyboardMarkup(row_width=2).add(
            InlineKeyboardButton("🔙 Scheda", callback_data=f"sq_pl_{p}"),
            InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        if session.get('ritorno'):
            tastiera.add(InlineKeyboardButton("↩️ Torna alla lista", callback_data=session['ritorno']))
        bot.edit_message_text(get_storico(p, df), chat_id, call.message.message_id, parse_mode="HTML", reply_markup=tastiera)

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
        p = int(call.data.split("_page_")[1]) if "_page_" in call.data else 1
        mods = analisi.candidati_modificatore(get_available_players(df, session), limite=45)
        markup, nav = InlineKeyboardMarkup(row_width=1), []
        if mods is not None and not mods.empty:
            for _, r in mods.iloc[(p - 1) * 15:p * 15].iterrows():
                markup.add(InlineKeyboardButton(
                    f"🛡️ {r['Nome']} ({r['Squadra']}) · MV {_num(r.get('Mv')):.2f} · {int(_num(r.get('Pv')))} pres",
                    callback_data=f"sq_pl_{r['Nome']}"))
            if p > 1:
                nav.append(InlineKeyboardButton("◀️ Precedenti", callback_data=f"menu_modificatore_page_{p - 1}"))
            if len(mods) > p * 15:
                nav.append(InlineKeyboardButton("➕ Altri", callback_data=f"menu_modificatore_page_{p + 1}"))
        if nav: markup.row(*nav)
        markup.add(InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text(
            f"🛡️ <b>MODIFICATORE 6.5</b> (Pag. {p})\n"
            f"<i>Conta il voto puro, non la fantamedia: ordinati per MV ponderata e solidita' della difesa</i>",
            chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif call.data == "menu_rosa":
        r = "\n".join([f"<b>{ROLE_ICONS[ru]} {ru}:</b>\n" + "".join([f"• {html.escape(p['nome'])} (<code>{p['prezzo']} cr.</code>)\n" for p in session.get('rosa', []) if p.get('ruolo') == ru]) for ru in ['P', 'D', 'C', 'A'] if any(p.get('ruolo') == ru for p in session.get('rosa', []))])
        bot.edit_message_text(f"📋 <b>LA TUA ROSA:</b>\n───────────────────────────\n{r}" if r else "📋 <b>ROSA VUOTA!</b>", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🏠 Home", callback_data="go_home")))

    elif call.data == "sq_start":
        markup = InlineKeyboardMarkup(row_width=2).add(*[InlineKeyboardButton(f"{get_team_icon(s)} {s}", callback_data=f"sq_sq_{s}") for s in sorted(df['Squadra'].dropna().astype(str).unique())]).add(InlineKeyboardButton("🔙 Home", callback_data="go_home"))
        bot.edit_message_text("👕 <b>ESPLORA SQUADRE</b>", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif call.data.startswith("sq_sq_"): bot.edit_message_text("Scegli ruolo:", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(row_width=4).add(*[InlineKeyboardButton(f"{ROLE_ICONS[r]} {r}", callback_data=f"sq_ru_{call.data.replace('sq_sq_', '')}_{r}") for r in ['P', 'D', 'C', 'A']]).add(InlineKeyboardButton("🔙 Squadre", callback_data="sq_start")))
    elif call.data.startswith("sq_ru_"):
        sq, ru = call.data.split("_")[2], call.data.split("_")[3]
        markup = InlineKeyboardMarkup(row_width=1).add(*[InlineKeyboardButton(f"{'⭐ ' if r['Nome'] in session.get('wishlist', []) else ''}{ROLE_ICONS.get(ru,'')} {r['Nome']} ─ {fair_price(r, session)} cr", callback_data=f"sq_pl_{r['Nome']}") for _, r in df[(df['Squadra'] == sq) & (df['R'] == ru)].iterrows()]).add(InlineKeyboardButton("🔙 Cambia Ruolo", callback_data=f"sq_sq_{sq}"),
             InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text(f"Giocatori ({sq} - {ru}):", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif call.data == "menu_panic_start":
        mostra_panic(chat_id, call.message.message_id, df, session)

    elif call.data.startswith("panic_ru_"):
        mostra_panic(chat_id, call.message.message_id, df, session,
                     ruolo_forzato=call.data.split("_")[-1])

    elif call.data.startswith("menu_top_ru_") or call.data.startswith("menu_gemme_ru_"):
        pfx, raw = call.data.split("_")[1], call.data.split("_ru_")[1]
        r, p = (raw.split("_page_")[0], int(raw.split("_page_")[1])) if "_page_" in raw else (raw, 1)
        avail = get_available_players(df, session)
        # La fascia si calcola SEMPRE sul listone intero, altrimenti lo stesso
        # giocatore risulta TOP nella sua card e di un'altra fascia nell'elenco,
        # perche' i compagni gia' comprati sparivano dalla classifica di ruolo.
        # Chi e' gia' stato preso lo si toglie dopo, solo dalla visualizzazione.
        mappa_fasce = {'gemme': 'quarta', 'top': 'top'}
        lst = analisi.fascia(df, r, mappa_fasce.get(pfx, 'top'),
                             session.get('lega_partecipanti', 8))
        if lst is not None and not lst.empty:
            lst = lst[lst['Nome'].isin(avail['Nome'])]
        if lst is None or lst.empty:
            lst = avail[avail['R'] == r].sort_values(by='FVM', ascending=False)
        
        markup, nav = InlineKeyboardMarkup(row_width=1), []
        for _, row in lst.iloc[(p-1)*15:p*15].iterrows(): markup.add(InlineKeyboardButton(f"🔍 {row['Nome']} ({row.get('Squadra','-')}) · {int(_num(row.get('Prezzo'), 1))} cr", callback_data=f"sq_pl_{row['Nome']}"))
        if p > 1: nav.append(InlineKeyboardButton("◀️", callback_data=f"menu_{pfx}_ru_{r}_page_{p - 1}"))
        if len(lst) > p*15: nav.append(InlineKeyboardButton("➕", callback_data=f"menu_{pfx}_ru_{r}_page_{p + 1}"))
        if nav: markup.row(*nav)
        markup.add(InlineKeyboardButton("🔙 Cambia Ruolo", callback_data=f"menu_{pfx}_start"), InlineKeyboardButton("🏠 Home", callback_data="go_home"))
        bot.edit_message_text(f"{pfx.upper()} - {ROLE_ICONS[r]} {r} (Pag. {p}):", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif call.data == "menu_scommessa_start":
        mostra_pronostici(chat_id, call.message.message_id, df, session)

    elif call.data == "menu_studio_start":
        session['compare_p1'] = None
        bot.edit_message_text("📊 <b>STUDIO 3D</b>\nSquadra TUO giocatore:", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(row_width=2).add(*[InlineKeyboardButton(f"{get_team_icon(s)} {s}", callback_data=f"std1_sq_{s}") for s in sorted(df['Squadra'].dropna().astype(str).unique())]).add(InlineKeyboardButton("🔙 Home", callback_data="go_home")))

    elif call.data.startswith("std1_sq_"): bot.edit_message_text("Scegli ruolo:", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(row_width=4).add(*[InlineKeyboardButton(f"{ROLE_ICONS[r]} {r}", callback_data=f"std1_ru_{call.data.replace('std1_sq_', '')}_{r}") for r in ['P', 'D', 'C', 'A']]).add(InlineKeyboardButton("🔙 Indietro", callback_data="menu_studio_start"),
     InlineKeyboardButton("🏠 Home", callback_data="go_home")))
    elif call.data.startswith("std1_ru_"): bot.edit_message_text("Seleziona:", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(row_width=1).add(*[InlineKeyboardButton(f"{r['Nome']}", callback_data=f"std1_pl_{r['Nome']}") for _, r in df[(df['Squadra'] == call.data.split('_')[2]) & (df['R'] == call.data.split('_')[3])].iterrows()]).add(InlineKeyboardButton("🔙", callback_data=f"std1_sq_{call.data.split('_')[2]}")))
    elif call.data.startswith("std1_pl_"):
        session['compare_p1'] = df[df['Nome'] == call.data.replace("std1_pl_", "")].iloc[0].to_dict()
        bot.edit_message_text(f"📊 <b>Hai scelto {html.escape(session['compare_p1']['Nome'].upper())}</b>\nSquadra PROPOSTO:", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(row_width=2).add(*[InlineKeyboardButton(f"{get_team_icon(s)} {s}", callback_data=f"std2_sq_{s}") for s in sorted(df['Squadra'].dropna().astype(str).unique())]).add(InlineKeyboardButton("🔙 Ricomincia", callback_data="menu_studio_start"),
     InlineKeyboardButton("🏠 Home", callback_data="go_home")))
    elif call.data.startswith("std2_sq_"): bot.edit_message_text("Scegli:", chat_id, call.message.message_id, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(row_width=1).add(*[InlineKeyboardButton(f"🆚 {r['Nome']}", callback_data=f"std2_pl_{r['Nome']}") for _, r in df[(df['Squadra'] == call.data.replace("std2_sq_", "")) & (df['R'] == session['compare_p1']['R']) & (df['Nome'] != session['compare_p1']['Nome'])].iterrows()]).add(InlineKeyboardButton("🔙", callback_data=f"std1_pl_{session['compare_p1']['Nome']}")))
    elif call.data.startswith("std2_pl_"): bot.edit_message_text(advanced_trade_analyzer_3d(session['compare_p1'], df[df['Nome'] == call.data.replace("std2_pl_", "")].iloc[0].to_dict(), session, df), chat_id, call.message.message_id, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(row_width=2).add(InlineKeyboardButton(f"⚡ Compra {session['compare_p1']['Nome']}", callback_data=f"buy_{session['compare_p1']['Nome']}"), InlineKeyboardButton(f"⚡ Compra {call.data.replace('std2_pl_', '')}", callback_data=f"buy_{call.data.replace('std2_pl_', '')}")).add(InlineKeyboardButton("🔄 Nuovo", callback_data="menu_studio_start"), InlineKeyboardButton("🏠 Home", callback_data="go_home")))

    elif call.data.startswith("sq_pl_"): send_player_card_view(chat_id, call.data.replace("sq_pl_", ""), call.message.message_id, df, session)
    elif call.data.startswith("buy_"): bot.register_next_step_handler(bot.send_message(chat_id, f"💰 Crediti spesi per <b>{html.escape(call.data.replace('buy_', ''))}</b>?:", parse_mode="HTML"), process_buy_price, call.data.replace("buy_", ""), user_id)
    
    elif call.data.startswith("taken_"):
        # Passa dal registro: cosi' esiste una sola fonte di verita' e
        # l'annulla funziona anche su quello che segni coi pulsanti.
        nome_venduto = call.data.replace("taken_", "")
        riga_venduta = get_player_stats(nome_venduto, df)
        registro_asta = get_registro(session)
        registro_asta.segna(nome_venduto, 0,
                            str(riga_venduta.get('R', 'C')) if riga_venduta is not None else 'C',
                            str(riga_venduta.get('Squadra', '')) if riga_venduta is not None else '',
                            "altri")
        salva_registro(registro_asta, session, chat_id)
        safe_answer_callback(call.id, text="🚫 Segnato: preso dagli altri", show_alert=False)
        send_asta_dashboard(chat_id, user_id, call.message.message_id) if session.get('fase_asta') else send_dashboard(chat_id, user_id, call.message.message_id)

    elif call.data.startswith("wl_toggle_"):
        if call.data.replace("wl_toggle_", "") in session.get('wishlist', []): session['wishlist'].remove(call.data.replace("wl_toggle_", ""))
        else: session.setdefault('wishlist', []).append(call.data.replace("wl_toggle_", ""))
        send_player_card_view(chat_id, call.data.replace("wl_toggle_", ""), call.message.message_id, df, session)

    elif call.data in ("asta_preso_io", "asta_preso_altri"):
        # Chiusa la chiamata: si segna al prezzo dell'ultimo rilancio e la
        # plancia riparte pulita, gia' col turno avanzato di uno.
        in_asta = session.get('in_asta') or {}
        prezzo = in_asta.get('offerta')
        if not in_asta.get('nome') or prezzo is None:
            safe_answer_callback(call.id, "Scrivi prima a quanto e' arrivato.", True)
        else:
            registro_asta = get_registro(session)
            registro_asta.segna(in_asta['nome'], prezzo, in_asta.get('ruolo', 'C'),
                                in_asta.get('squadra', ''),
                                acquirente=reg.IO if call.data == "asta_preso_io"
                                else reg.ALTRI)
            salva_registro(registro_asta, session, chat_id)
            session['in_asta'] = None
            safe_answer_callback(call.id, f"✓ {in_asta['nome']} {prezzo} cr", False)
        mostra_plancia(chat_id, session.get('id_plancia') or call.message.message_id,
                       df, session)

    elif call.data == "asta_turno_mio":
        # Sincronizza il giro: da qui in avanti il bot sa contare da solo,
        # perche' ogni chiamata finisce con una vendita.
        session['turno_offset'] = len(get_registro(session).voci)
        salva_sessioni()
        safe_answer_callback(call.id, "🔔 Turno sincronizzato", False)
        mostra_plancia(chat_id, session.get('id_plancia') or call.message.message_id,
                       df, session)

    elif call.data == "menu_andamento":
        mostra_andamento(chat_id, call.message.message_id, df, session)

    elif call.data == "reg_annulla":
        registro_asta = get_registro(session)
        tolta = registro_asta.annulla_ultima()
        if tolta is None:
            safe_answer_callback(call.id, "Niente da annullare.", True)
        else:
            salva_registro(registro_asta, session, chat_id)
            safe_answer_callback(call.id, f"↩︎ Annullato: {tolta['nome']}", False)
            try:
                bot.edit_message_text(
                    f"↩︎ <b>Annullato</b>: {html.escape(tolta['nome'])} "
                    f"({tolta['prezzo']} cr)\n💰 cassa <b>{session['budget']}</b>",
                    chat_id, call.message.message_id, parse_mode="HTML")
            except Exception:
                pass

    elif call.data == "menu_wishlist":
        mostra_wishlist(chat_id, call.message.message_id, df, session)


def verifica_istanza_unica(tentativi=6, attesa=10):
    """
    Una chiamata a getUpdates prima di partire: se un'altra istanza sta gia'
    leggendo, Telegram risponde 409. Serve perche' infinity_polling intercetta
    gli errori e ritenta all'infinito, lasciando il bot muto senza spiegazioni.

    Si riprova per un minuto prima di arrendersi: durante un deploy il processo
    precedente puo' impiegare qualche secondo a mollare il token, e uscire
    subito farebbe ripartire Render in un ciclo di riavvii.
    """
    for numero in range(1, tentativi + 1):
        try:
            bot.get_updates(offset=-1, timeout=1)
            if numero > 1:
                print(f"✅ Token libero al tentativo {numero}.")
            return True
        except ApiTelegramException as e:
            if getattr(e, 'error_code', None) != 409:
                print(f"⚠️ Telegram ha risposto {getattr(e, 'error_code', '?')}: proseguo comunque.")
                return True
            if numero < tentativi:
                print(f"⏳ Token occupato (409), tentativo {numero}/{tentativi}: "
                      f"riprovo fra {attesa}s...")
                time.sleep(attesa)
        except Exception as e:
            print(f"⚠️ Controllo istanza non riuscito ({e}): proseguo comunque.")
            return True

    print("🛑 HTTP 409 dopo {} tentativi: un'altra istanza del bot è in ascolto.\n"
          "   Da controllare: un solo servizio su Render con questo BOT_TOKEN,\n"
          "   Instances = 1, nessun deploy vecchio ancora vivo, nessuna copia in locale.\n"
          "   Verifica dall'esterno: apri nel browser\n"
          "   https://api.telegram.org/bot<TOKEN>/getUpdates\n"
          "   con il servizio Render sospeso. Se risponde 409, il fantasma è altrove."
          .format(tentativi))
    return False


def avvia_pianificatore():
    """
    Download notturno del Master e salvataggio periodico delle sessioni.
    Prima lo scheduler era importato ma mai istanziato: il listone si aggiornava
    solo per caso, quando Render riavviava il servizio.
    """
    pianificatore = BackgroundScheduler(timezone="Europe/Rome")
    pianificatore.add_job(auto_download_listone, 'cron',
                          hour=config.ORA_DOWNLOAD, minute=0,
                          id='download_master', replace_existing=True)
    pianificatore.add_job(salva_sessioni, 'interval', seconds=30,
                          id='salva_sessioni', replace_existing=True)
    pianificatore.start()
    print(f"⏰ Download del Master pianificato ogni giorno alle "
          f"{config.ORA_DOWNLOAD:02d}:00 (Europe/Rome).")
    return pianificatore


if __name__ == '__main__':
    carica_sessioni()
    load_data()

    try:
        bot.remove_webhook()
    except Exception:
        pass

    if not verifica_istanza_unica():
        sys.exit(1)

    pianificatore = avvia_pianificatore()
    print("🚀 FANTABOT PRO ASTA LIVE In Ascolto!")

    try:
        bot.infinity_polling(timeout=10, long_polling_timeout=5, skip_pending=True)
    except ApiTelegramException as e:
        if getattr(e, 'error_code', None) == 409:
            print("🛑 HTTP 409 durante il polling: è comparsa una seconda istanza.")
            salva_sessioni()
            sys.exit(1)
        raise
    except KeyboardInterrupt:
        pass
    finally:
        salva_sessioni()
        try:
            pianificatore.shutdown(wait=False)
        except Exception:
            pass
