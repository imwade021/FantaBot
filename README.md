# FantaBot

Interfaccia Telegram per l'asta del Fantacalcio. **Non calcola niente**: legge
`Lista_Finale_Master.csv` prodotto da
[`fanta-master-ai`](https://github.com/imwade021/fanta-master-ai) e lo presenta.

Se un numero e' sbagliato, il posto da correggere e' il motore, non questa repo.

## Moduli

| File | Responsabilita' |
|---|---|
| `config.py` | costanti: URL, slot, budget, icone. Nessuna logica |
| `dati.py` | download, caricamento, ricerca, prezzo riscalato sulla lega |
| `analisi.py` | profilo, confronto, fasce, rischio. Nessuna dipendenza da Telegram |
| `interfaccia.py` | card e dashboard grafiche (Pillow) |
| `bot.py` | comandi, bottoni, sessioni |

`analisi.py` e `dati.py` si provano da riga di comando:
`python3 dati.py`, `python3 -c "import analisi"`.

## Variabili d'ambiente

| Variabile | Default | Note |
|---|---|---|
| `BOT_TOKEN` | — | obbligatoria |
| `LISTONE_URL` | raw di `fanta-master-ai` | da dove scarica il Master |
| `ORA_DOWNLOAD` | `5` | ora (Europe/Rome) del download notturno |
| `FILE_SESSIONI` | `sessioni.json` | dove sopravvivono rosa e cassa a un riavvio |

## Deploy su Render

Deve essere un **Background Worker** con **una sola istanza**.

Telegram consente un solo lettore per token: due processi in ascolto danno
HTTP 409 e il bot smette di rispondere. All'avvio il bot fa una chiamata di
prova e, se trova un'altra istanza, si ferma con un messaggio esplicito invece
di riprovare in silenzio.

Da controllare quando compare il 409:
- il servizio e' un Worker e non un Web Service;
- non ci sono due servizi con lo stesso `BOT_TOKEN`;
- il deploy precedente e' terminato davvero;
- non gira una copia in locale.

## Cosa NON caricare nel bot

Il file quotazioni di Fantacalcio va messo in `fanta-master-ai`, non inviato in
chat: non contiene FVM, prezzi ne' infortuni, e il bot lo rifiuta apposta.
