import feedparser
import telegram
import asyncio
import aiohttp
import logging
import time
import calendar
import smtplib
from email.mime.text import MIMEText
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown
import logging.handlers  # Necessario per SMTPHandler

# Configura il bot con il Token API e il canale o chat di destinazione
TOKEN = "IL MIO TOKEN"
CHAT_ID = "@stradelivebo"  # Usa @nomecanale per canali pubblici o l'ID numerico per chat private

bot = telegram.Bot(token=TOKEN)
URL_RSS = "https://www.cciss.it/rss"

# Set per tenere traccia delle notizie già inviate (per evitare duplicati)
notizie_inviate = set()

# Configura il logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Aggiungi SMTPHandler per inviare email in caso di errori
mailhost = ("smtp.gmail.com", 587)  # Esempio per Gmail
fromaddr = "MIA_EMAIL@gmail.com"  # Inserisci la tua email
toaddrs = ["MIA_EMAIL@gmail.com"]  # Inserisci l'indirizzo email di notifica
credentials = ("MIA_EMAIL@gmail.com", "MIA_PASSWORD")  # Inserisci le tue credenziali
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

async def fetch_and_send_news():
    logging.info("🔍 Controllo nuove notizie...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(URL_RSS, timeout=10) as response:
                if response.status != 200:
                    logging.warning(f"⚠️ Errore nel caricamento del feed RSS. Stato HTTP: {response.status}")
                    return
                content = await response.read()
    except asyncio.TimeoutError as e:
        logging.error(f"❌ Timeout durante il recupero delle notizie: {e}")
        return
    except Exception as e:
        logging.error(f"❌ Errore durante il recupero del feed: {e}")
        return

    feed = feedparser.parse(content)
    logging.info(f"🔍 {len(feed.entries)} notizie trovate nel feed.")

    if not feed.entries:
        logging.info("⚠️ Nessuna notizia trovata nel feed.")
        return

    for entry in feed.entries:
        titolo = getattr(entry, 'title', None)
        if not titolo:
            logging.warning("Notizia saltata per mancanza di titolo.")
            continue

        if hasattr(entry, 'published_parsed'):
            entry_timestamp = calendar.timegm(entry.published_parsed)
            if entry_timestamp < program_start_timestamp:
                logging.info(f"Notizia '{titolo}' ignorata: pubblicata prima dell'avvio del programma.")
                continue

        descrizione = getattr(entry, 'description', None)
        if descrizione:
            # Rimuove i tag <br/> e <br>
            descrizione = descrizione.replace("<br/>", " ").replace("<br>", " ")
        if not ("bologna" in titolo.lower() or (descrizione and "bologna" in descrizione.lower())):
            logging.info(f"Notizia '{titolo}' ignorata: non contiene 'Bologna'.")
            continue

        link = getattr(entry, 'link', None) or "https://www.cciss.it"
        data_pubblicazione = getattr(entry, 'published', "Data non disponibile")
        logging.info(f"📰 Notizia trovata: {titolo} (Pubblicata il: {data_pubblicazione})")

        if titolo in notizie_inviate:
            continue

        titolo_escaped = escape_markdown(titolo, version=2)
        descrizione_escaped = escape_markdown(descrizione, version=2) if descrizione else ""
        messaggio = f"🚦 *{titolo_escaped}*\n📌 {descrizione_escaped}\n🔗 [Leggi di più]({link})"
        try:
            await bot.send_message(chat_id=CHAT_ID, text=messaggio, parse_mode=ParseMode.MARKDOWN_V2)
            notizie_inviate.add(titolo)
            if len(notizie_inviate) > 100:
                notizie_inviate.pop()
        except Exception as e:
            logging.error(f"❌ Errore nell'invio della notizia '{titolo}': {e}")

async def periodic_fetch():
    while True:
        await fetch_and_send_news()
        # Attende 60 secondi (1 minuto) prima del prossimo controllo
        await asyncio.sleep(60)

async def main():
    # Invia l'email di avvio
    send_start_email()
    await send_start_message()
    asyncio.create_task(periodic_fetch())
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())