"""
registro.py - Il taccuino dell'asta.

Tiene traccia di ogni giocatore venduto: a chi, a quanto, quando. E' la fonte
da cui il resto del bot ricava tutto - quanto puoi spendere, chi puo' ancora
farti concorrenza, se in questa serata si sta pagando sopra o sotto il listino.

Due regole di progetto, imparate a spese di chi ha provato prima:

1. Scrivere deve costare pochissimo. Se segnare un acquisto richiede piu' di
   tre secondi, alla decima chiamata smetti, il registro resta indietro e il
   bot inizia a consigliarti giocatori gia' venduti: peggio che non averlo.
2. Sbagliare e' la norma. Un taccuino senza gomma non si usa: ogni operazione
   e' annullabile, sempre, senza conferme.
"""

import re
import time

IO = "io"                      # identificativo riservato alla propria squadra


def _pulisci(testo):
    return " ".join(str(testo or "").split()).strip()


class Registro:
    """
    Le voci sono la verita': tutto il resto (rosa, budget, conteggi) si
    ricalcola da qui. Cosi' annullare e' togliere una riga, non ricostruire
    a mano cinque contatori diversi che finirebbero per non tornare.
    """

    def __init__(self, dati=None):
        dati = dati or {}
        self.voci = list(dati.get('voci', []))
        self.avversari = list(dati.get('avversari', []))
        self.budget_iniziale = int(dati.get('budget_iniziale', 500))
        self.partecipanti = int(dati.get('partecipanti', 8))

    # ------------------------------------------------------------------
    def come_dizionario(self):
        return {'voci': self.voci, 'avversari': self.avversari,
                'budget_iniziale': self.budget_iniziale,
                'partecipanti': self.partecipanti}

    # ------------------------------------------------------------------
    # SCRITTURA
    # ------------------------------------------------------------------
    def segna(self, nome, prezzo, ruolo, squadra="", acquirente=IO):
        """Un giocatore e' stato venduto. Ritorna la voce creata."""
        nome = _pulisci(nome)
        if not nome:
            return None
        self.dimentica(nome)          # niente doppioni: l'ultima parola vince
        voce = {
            'nome': nome,
            'prezzo': max(0, int(prezzo or 0)),
            'ruolo': str(ruolo or 'C').upper()[:1],
            'squadra': _pulisci(squadra),
            'a': _pulisci(acquirente) or IO,
            'quando': int(time.time()),
        }
        self.voci.append(voce)
        if voce['a'] != IO and voce['a'] not in self.avversari:
            self.avversari.append(voce['a'])
        return voce

    def dimentica(self, nome):
        """Toglie un giocatore dal registro. True se c'era."""
        chiave = _pulisci(nome).lower()
        prima = len(self.voci)
        self.voci = [v for v in self.voci if v['nome'].lower() != chiave]
        return len(self.voci) < prima

    def annulla_ultima(self):
        """La gomma: toglie l'ultima riga scritta e la restituisce."""
        return self.voci.pop() if self.voci else None

    def azzera(self):
        self.voci, self.avversari = [], []

    # ------------------------------------------------------------------
    # LETTURA
    # ------------------------------------------------------------------
    def venduti(self):
        return {v['nome'] for v in self.voci}

    def rosa(self, di=IO):
        return [v for v in self.voci if v['a'] == di]

    def speso(self, di=IO):
        return sum(v['prezzo'] for v in self.rosa(di))

    def budget(self, di=IO):
        return self.budget_iniziale - self.speso(di)

    def conteggi(self, di=IO):
        conta = {'P': 0, 'D': 0, 'C': 0, 'A': 0}
        for v in self.rosa(di):
            if v['ruolo'] in conta:
                conta[v['ruolo']] += 1
        return conta

    def speso_per_ruolo(self, di=IO):
        speso = {'P': 0, 'D': 0, 'C': 0, 'A': 0}
        for v in self.rosa(di):
            if v['ruolo'] in speso:
                speso[v['ruolo']] += v['prezzo']
        return speso

    # ------------------------------------------------------------------
    # GLI ALTRI
    # ------------------------------------------------------------------
    def quadro_avversari(self, slot_per_ruolo, rosa_completa):
        """
        Chi puo' ancora farti concorrenza, e su cosa.

        E' l'informazione che nessun collegamento automatico all'asta
        darebbe: chi e' rimasto a corto di crediti non rilancera', e chi ha
        ancora un buco obbligatorio da riempire paghera' sopra prezzo.
        """
        quadro = []
        for nome in self.avversari:
            presi = len(self.rosa(nome))
            residuo = self.budget(nome)
            slot_liberi = max(0, rosa_completa - presi)
            conteggi = self.conteggi(nome)
            mancanti = {r: max(0, slot_per_ruolo.get(r, 0) - n)
                        for r, n in conteggi.items()}
            quadro.append({
                'nome': nome, 'presi': presi, 'residuo': residuo,
                'slot_liberi': slot_liberi, 'mancanti': mancanti,
                # Quanto puo' offrire al massimo tenendo 1 credito per casella.
                'offerta_max': max(0, residuo - (slot_liberi - 1)) if slot_liberi else 0,
            })
        return sorted(quadro, key=lambda x: -x['offerta_max'])

    def rivali_per_ruolo(self, ruolo, prezzo, slot_per_ruolo, rosa_completa):
        """Quanti avversari possono permettersi questo giocatore a questa cifra."""
        quadro = self.quadro_avversari(slot_per_ruolo, rosa_completa)
        return [a for a in quadro
                if a['offerta_max'] >= prezzo and a['mancanti'].get(ruolo, 0) > 0]

    # ------------------------------------------------------------------
    # IL MERCATO DI QUESTA SERATA
    # ------------------------------------------------------------------
    def inflazione(self, prezzi_listino, minimo_campione=8):
        """
        Quanto si sta pagando rispetto al listino, in questa asta.

        Restituisce (fattore, campione). 1.20 = si paga il 20% sopra. Sotto
        {minimo_campione} vendite il dato non e' affidabile e si torna 1.0:
        meglio nessuna correzione che una correzione basata su tre acquisti.

        Si contano solo i giocatori sopra i 5 crediti di listino: sui giocatori
        da 1 credito una differenza di 2 crediti e' rumore, non inflazione.
        """
        pagati, listino = 0, 0
        campione = 0
        for voce in self.voci:
            riferimento = prezzi_listino.get(voce['nome'])
            if not riferimento or riferimento < 5:
                continue
            pagati += voce['prezzo']
            listino += riferimento
            campione += 1

        if campione < minimo_campione or listino <= 0:
            return 1.0, campione
        return round(pagati / listino, 3), campione


# ----------------------------------------------------------------------
# INSERIMENTO RAPIDO
# ----------------------------------------------------------------------
#   "dimarco 90"     -> venduto a un altro per 90 crediti
#   "dimarco 90 io"  -> l'ho preso io
#   "io dimarco 90"  -> uguale, se viene piu' comodo dirlo prima
#   "dimarco"        -> venduto a un altro, prezzo non registrato
PAROLE_MIE = {'io', 'mio', 'mia', 'me', 'preso', 'mine'}
ALTRI = "altri"


def interpreta(testo):
    """
    Scompone una riga battuta al volo durante l'asta.

    Torna (nome, prezzo, acquirente). prezzo None se non indicato,
    acquirente None se non indicato: decide chi chiama cosa farne.

    Nessun formato rigido e nessuna conferma: durante un'asta si scrive di
    fretta e con una mano sola.
    """
    testo = _pulisci(testo)
    if not testo:
        return None, None, None

    # "io" puo' stare in testa o in coda: "io dimarco 90", "dimarco 90 io".
    pezzi = testo.split()
    mio = False
    if pezzi and pezzi[0].lower() in PAROLE_MIE:
        mio, pezzi = True, pezzi[1:]
    if pezzi and pezzi[-1].lower() in PAROLE_MIE:
        mio, pezzi = True, pezzi[:-1]
    testo = " ".join(pezzi)

    # Il prezzo e' il primo numero isolato: "dimarco 90" oppure "90 dimarco".
    numeri = re.findall(r'(?<![\w])(\d{1,3})(?![\w])', testo)
    prezzo = int(numeri[0]) if numeri else None
    if prezzo is not None:
        prima, _, dopo = testo.partition(str(prezzo))
        nome = _pulisci(prima) or _pulisci(dopo)
    else:
        nome = testo

    # Senza marcatore l'acquisto e' degli altri: in una lega da 8 squadre
    # nove acquisti su dieci non sono tuoi, quindi il caso frequente non deve
    # costare neanche un carattere. Il valore torna sempre esplicito: lasciare
    # None significava far decidere a chi chiama, e sbagliare il default li'
    # avrebbe accreditato a te la rosa di tutta la lega.
    return (nome or None), prezzo, (IO if mio else ALTRI)


def sincronizza(registro, session):
    """
    Riscrive nella sessione le chiavi storiche a partire dal registro.

    Il registro e' la fonte di verita', ma mezzo bot legge session['rosa'],
    session['budget'] e session['scartati']: invece di inseguire ogni punto in
    cui vengono usati, si tiene uno specchio sempre allineato.
    """
    session['registro'] = registro.come_dizionario()
    session['rosa'] = [{'nome': v['nome'], 'prezzo': v['prezzo'],
                        'ruolo': v['ruolo'], 'squadra': v['squadra']}
                       for v in registro.rosa()]
    session['budget'] = registro.budget()
    session['lega_budget_iniziale'] = registro.budget_iniziale
    session['lega_partecipanti'] = registro.partecipanti
    # "scartati" per il resto del bot significa "non piu' disponibile":
    # ci finisce tutto il venduto, mio compreso.
    session['scartati'] = sorted(registro.venduti())
    return session


# ----------------------------------------------------------------------
# IL TACCUINO DENTRO TELEGRAM
#
# sessioni.json vive sul disco di Render, che si azzera a ogni deploy: perdere
# il registro a meta' asta e' l'unico errore davvero irreparabile di tutto il
# progetto. Qui il registro si scrive anche in un messaggio fissato in cima
# alla chat. Telegram quel messaggio non lo perde, e come effetto secondario
# il taccuino diventa leggibile a colpo d'occhio senza premere niente.
#
# Si salvano solo nome, prezzo e chi ha comprato: ruolo e squadra si
# ritrovano dal listone, e ogni carattere risparmiato e' spazio guadagnato
# sotto il tetto dei 4096 caratteri di un messaggio.
# ----------------------------------------------------------------------
INTESTAZIONE = "📓 TACCUINO ASTA"
LIMITE_MESSAGGIO = 3800


def serializza(registro):
    """Il registro come testo compatto, leggibile anche da un umano."""
    righe = [INTESTAZIONE,
             f"budget {registro.budget_iniziale} · squadre {registro.partecipanti}",
             f"cassa {registro.budget()} · presi {len(registro.rosa())}",
             "———"]
    for voce in registro.voci:
        # La chiave e' 'a', non 'acquirente': sbagliandola ogni acquisto
        # tornava indietro come venduto agli altri, e la rosa si svuotava.
        segno = "io" if voce.get('a') == IO else "-"
        righe.append(f"{voce['nome']}|{voce['prezzo']}|{segno}")

    testo = "\n".join(righe)
    if len(testo) > LIMITE_MESSAGGIO:
        # Meglio un taccuino tagliato in coda che un salvataggio fallito: le
        # voci piu' vecchie sono anche le meno utili da recuperare.
        testo = testo[:LIMITE_MESSAGGIO].rsplit("\n", 1)[0] + "\n… (troppo lungo)"
    return testo


def deserializza(testo, cerca_giocatore=None, budget=500, partecipanti=8):
    """
    Ricostruisce il registro dal messaggio fissato.

    cerca_giocatore(nome) deve restituire (ruolo, squadra): ruolo e squadra
    non si salvano, si ritrovano dal listone. Se un nome non si trova piu'
    (listone aggiornato nel frattempo) la voce si tiene lo stesso, perche'
    perdere un acquisto e' peggio che tenerlo senza ruolo.
    """
    if not testo or INTESTAZIONE not in testo:
        return None

    registro = Registro({'budget_iniziale': budget, 'partecipanti': partecipanti})
    for riga in testo.splitlines():
        if riga.startswith("budget "):
            pezzi = riga.replace("·", " ").split()
            try:
                registro.budget_iniziale = int(pezzi[1])
                registro.partecipanti = int(pezzi[3])
            except (IndexError, ValueError):
                pass
            continue
        if "|" not in riga:
            continue
        parti = riga.split("|")
        if len(parti) < 3:
            continue
        nome, prezzo, segno = parti[0].strip(), parti[1].strip(), parti[2].strip()
        try:
            prezzo = int(prezzo)
        except ValueError:
            continue
        ruolo, squadra = ("", "")
        if cerca_giocatore:
            trovato = cerca_giocatore(nome)
            if trovato:
                ruolo, squadra = trovato
        registro.segna(nome, prezzo, ruolo, squadra,
                       acquirente=IO if segno == "io" else ALTRI)
    return registro if registro.voci else None
