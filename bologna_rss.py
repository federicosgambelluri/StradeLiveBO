import feedparser
import telegram
import asyncio
import aiohttp
import logging
import time
import smtplib
import os
from email.mime.text import MIMEText
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown
from collections import OrderedDict
import logging.handlers  # Necessario per SMTPHandler

# Carica le variabili d'ambiente per sicurezza - INSERISCI I TUOI DATI
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "IL TUO TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "@stradelivebo")
SMTP_USER = os.environ.get("SMTP_USER", "EMAIL MITTENTE")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "LA PASSWORD DELLA TUA EMAIL")
ALERT_EMAIL = os.environ.get("ALERT_EMAIL", "EMAIL DESTINATARIO")

bot = telegram.Bot(token=TOKEN)
URL_RSS = "https://www.cciss.it/rss"

# Utilizza un OrderedDict per tracciare le notizie già inviate
notizie_inviate = OrderedDict()
MAX_NOTIZIE_MEMORIZZATE = 100

# Configura il logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Configura SMTPHandler per notifiche via email in caso di errori
mailhost = ("smtp.gmail.com", 587)
fromaddr = SMTP_USER
toaddrs = [ALERT_EMAIL]
credentials = (SMTP_USER, SMTP_PASSWORD)
secure = ()

smtp_handler = logging.handlers.SMTPHandler(
    mailhost=mailhost,
    fromaddr=fromaddr,
    toaddrs=toaddrs,
    subject="Telegram Bot Error Notification",
    credentials=credentials,
    secure=secure
)
smtp_handler.setLevel(logging.ERROR)
logging.getLogger().addHandler(smtp_handler)

# Funzione per inviare un'email al momento dell'avvio
def send_start_email():
    subject = "Telegram Bot Avviato"
    body = "Il canale STRADE_BOLOGNA è stato avviato e la connessione è attiva."
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = fromaddr
    msg['To'] = ", ".join(toaddrs)
    try:
        smtp_server = smtplib.SMTP(mailhost[0], mailhost[1])
        smtp_server.starttls()
        smtp_server.login(credentials[0], credentials[1])
        smtp_server.sendmail(fromaddr, toaddrs, msg.as_string())
        smtp_server.quit()
        logging.info("Email di avvio inviata correttamente.")
    except Exception as e:
        logging.error(f"Errore nell'invio dell'email di avvio: {e}")

# Salva il timestamp di avvio del programma (in secondi dall'epoca)
program_start_timestamp = time.time()

async def send_start_message():
    try:
        messaggio = escape_markdown("✅ Canale operativo! In attesa di nuove notizie...", version=2)
        await bot.send_message(chat_id=CHAT_ID, text=messaggio, parse_mode=ParseMode.MARKDOWN_V2)
        logging.info("✅ Canale operativo!")
    except Exception as e:
        logging.error(f"❌ Errore nell'invio del messaggio di avvio: {e}")

# Funzione di fetch con retry per migliorare l'affidabilità
async def fetch_with_retry(session, url, retries=3, delay=5):
    for attempt in range(retries):
        try:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    return await response.read()
                else:
                    logging.warning(f"Attempt {attempt+1}: Stato HTTP {response.status} per {url}")
        except asyncio.TimeoutError as e:
            logging.error(f"Attempt {attempt+1}: Timeout durante il recupero - BO: {e}")
        except Exception as e:
            logging.error(f"Attempt {attempt+1}: Errore durante il recupero - BO: {e}")
        await asyncio.sleep(delay)
    return None

async def fetch_and_send_news():
    logging.info("🔍 Controllo nuove notizie...")
    try:
        async with aiohttp.ClientSession() as session:
            content = await fetch_with_retry(session, URL_RSS)
            if not content:
                logging.error("❌ Impossibile recuperare il feed dopo i retry - BO.")
                return
    except Exception as e:
        logging.error(f"❌ Errore durante la creazione della sessione - BO: {e}")
        return

    feed = feedparser.parse(content)
    num_entries = len(feed.entries) if feed.entries else 0
    logging.info(f"🔍 {num_entries} notizie trovate nel feed.")

    if not feed.entries:
        logging.info("⚠️ Nessuna notizia trovata nel feed.")
        return

    for entry in feed.entries:
        titolo = getattr(entry, 'title', None)
        if not titolo:
            logging.warning("Notizia saltata per mancanza di titolo.")
            continue

        descrizione = getattr(entry, 'description', None)
        if descrizione:
            # Rimuove i tag <br /> e <br>
            descrizione = descrizione.replace("<br />", " ").replace("<br>", " ")

        # Definisco le versioni "pulite" (minuscole) per il confronto
        titolo_clean = titolo.lower()
        descrizione_clean = descrizione.lower() if descrizione else ""

        # Filtra le notizie che NON contengono "bologna" in titolo o descrizione
        if not (("bologna" in titolo_clean) or ("bologna" in descrizione_clean)):
            logging.info(f"Notizia '{titolo}' ignorata: non contiene 'Bologna'.")
            continue

        link = getattr(entry, 'link', None) or "https://www.cciss.it"
        data_pubblicazione = getattr(entry, 'published', "Data non disponibile")
        logging.info(f"📰 Notizia trovata: {titolo} (Pubblicata il: {data_pubblicazione})")

        # Usa un identificatore unico se presente (es. guid/id), altrimenti usa il titolo
        unique_id = getattr(entry, 'description', None)

        # Se la notizia è già stata inviata, saltala
        if unique_id in notizie_inviate:
            continue

        titolo_escaped = escape_markdown(titolo, version=2)
        descrizione_escaped = escape_markdown(descrizione, version=2) if descrizione else ""
        messaggio = f"🚦 *{titolo_escaped}*\n📌 {descrizione_escaped}\n🔗 [Leggi di più]({link})"
        try:
            await bot.send_message(chat_id=CHAT_ID, text=messaggio, parse_mode=ParseMode.MARKDOWN_V2)
            # Aggiunge l'ID univoco alla lista delle notizie inviate
            notizie_inviate[unique_id] = time.time()
            # Mantiene solo le ultime MAX_NOTIZIE_MEMORIZZATE notizie
            if(time.localtime(time.time()).tm_hour == 1 and time.localtime(time.time()).tm_min == 0):
                #for myTime in notizie_inviate:
                    #logging.info("-->"+myTime)
                notizie_inviate.clear()
                #for myTime in notizie_inviate:
                    #logging.info("----->"+myTime)
            if len(notizie_inviate) > MAX_NOTIZIE_MEMORIZZATE:
                notizie_inviate.popitem(last=False)
        except Exception as e:
            logging.error(f"❌ Errore nell'invio della notizia '{titolo}': {e}")

async def periodic_fetch():
    while True:
        await fetch_and_send_news()
        # Attende 60 secondi prima del prossimo controllo
        await asyncio.sleep(60)

async def main():
    # Invia l'email di avvio
    send_start_email()
    await send_start_message()
    # Avvia il task periodico per il polling del feed RSS
    asyncio.create_task(periodic_fetch())
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
