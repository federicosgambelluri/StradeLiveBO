import feedparser

import telegram

import asyncio

import aiohttp

import logging

import time

import smtplib

import unicodedata

from collections import OrderedDict

from email.mime.text import MIMEText

from telegram.constants import ParseMode

from telegram.helpers import escape_markdown

import logging.handlers  # Necessario per SMTPHandler



# Configura il bot con il Token API e il canale o chat di destinazione

TOKEN = "IL TUO TOKEN"

CHAT_ID = "@tangelivebo"  # Usa @nomecanale per canali pubblici o l'ID numerico per chat private



bot = telegram.Bot(token=TOKEN)

URL_RSS = "https://www.cciss.it/rss"



# Utilizza un OrderedDict per tracciare le notizie già inviate

notizie_inviate = OrderedDict()

MAX_NOTIZIE_MEMORIZZATE = 100



# Configura il logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')



# Configura SMTPHandler per inviare email in caso di errori

mailhost = ("smtp.gmail.com", 587)  # Esempio per Gmail

fromaddr = "EMAIL MITTENTE"  # Inserisci la tua email

toaddrs = ["EMAIL DESTINATARIO"]  # Inserisci l'indirizzo email di notifica

credentials = ("EMAIL MITTENTE", "PASSWORD MITTENTE")  # Inserisci le tue credenziali

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

    body = "Il canale TANGE_BOLOGNA è stato avviato e la connessione è attiva."

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



# Funzione per normalizzare il testo e sostituire eventuali dash speciali con il trattino ASCII

def normalizza_testo(testo: str) -> str:

    if testo:

        # Normalizza Unicode (NFKC) per unificare le varianti dei caratteri

        testo = unicodedata.normalize("NFKC", testo)

        # Converti in minuscolo

        testo = testo.lower()

        # Sostituisci en-dash, em-dash, ecc. con il trattino ASCII

        testo = testo.replace("–", "-").replace("—", "-").replace("―", "-")

    return testo



# Salva il timestamp di avvio del programma (in secondi dall'epoca)

program_start_timestamp = time.time()



async def send_start_message():

    try:

        messaggio = escape_markdown("✅ Canale operativo! In attesa di nuove notizie...", version=2)

        await bot.send_message(chat_id=CHAT_ID, text=messaggio, parse_mode=ParseMode.MARKDOWN_V2)

        logging.info("✅ Canale operativo!")

    except Exception as e:

        logging.error(f"❌ Errore nell'invio del messaggio di avvio: {e}")



# Funzione per effettuare il fetch con retry

async def fetch_with_retry(session, url, retries=3, delay=5):

    for attempt in range(retries):

        try:

            async with session.get(url, timeout=10) as response:

                if response.status == 200:

                    return await response.read()

                else:

                    logging.warning(f"Attempt {attempt+1}: Stato HTTP {response.status} per {url}")

        except asyncio.TimeoutError as e:

            logging.error(f"Attempt {attempt+1}: Timeout durante il recupero - TGBO: {e}")

        except Exception as e:

            logging.error(f"Attempt {attempt+1}: Errore durante il recupero - TGBO: {e}")

        await asyncio.sleep(delay)

    return None



async def fetch_and_send_news():

    logging.info("🔍 Controllo nuove notizie...")

    try:

        async with aiohttp.ClientSession() as session:

            content = await fetch_with_retry(session, URL_RSS)

            if not content:

                logging.error("❌ Impossibile recuperare il feed dopo i retry - TGBO.")

                return

    except Exception as e:

        logging.error(f"❌ Errore durante la creazione della sessione - TGBO: {e}")

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



        descrizione = getattr(entry, 'description', None)

        if descrizione:

            # Rimuove i tag <br/>, <br /> e <br>

            descrizione = descrizione.replace("<br/>", " ").replace("<br />", " ").replace("<br>", " ")



        # Normalizza titolo e descrizione per gestire varianti Unicode e dash speciali

        titolo_clean = normalizza_testo(titolo)

        descrizione_clean = normalizza_testo(descrizione) if descrizione else ""



        

        # Filtra le notizie che NON contengono "tg-bo" o "tangenziale di bologna" in titolo O descrizione

        if not (("tg-bo" in titolo_clean or "tangenziale di bologna" in titolo_clean) or 

                ("tg-bo" in descrizione_clean or "tangenziale di bologna" in descrizione_clean)):

            logging.info(f"Notizia '{titolo}' ignorata: non contiene 'TG-BO'.") 

            continue



        link = getattr(entry, 'link', None) or "https://www.cciss.it"

        data_pubblicazione = getattr(entry, 'published', "Data non disponibile")

        logging.info(f"📰 Notizia trovata: {titolo} (Pubblicata il: {data_pubblicazione})")



        # Usa l'id del feed se disponibile, altrimenti il titolo normalizzato come identificatore univoco

        unique_id = getattr(entry, 'description', None)



        # Se la notizia è già stata inviata, saltala

        if unique_id in notizie_inviate:

            continue



        titolo_escaped = escape_markdown(titolo, version=2)

        descrizione_escaped = escape_markdown(descrizione, version=2) if descrizione else ""

        messaggio = f"🚦 *{titolo_escaped}*\n📌 {descrizione_escaped}\n🔗 [Leggi di più]({link})"

        try:

            await bot.send_message(chat_id=CHAT_ID, text=messaggio, parse_mode=ParseMode.MARKDOWN_V2)

            notizie_inviate[unique_id] = time.time()

            if(time.localtime(time.time()).tm_hour == 1 and time.localtime(time.time()).tm_min == 0):

                #for myTime in notizie_inviate:

                    #logging.info("-->"+myTime)

                notizie_inviate.clear()

                #for myTime in notizie_inviate:

                    #logging.info("----->"+myTime)

            # Mantiene solo le ultime MAX_NOTIZIE_MEMORIZZATE notizie

            if len(notizie_inviate) > MAX_NOTIZIE_MEMORIZZATE:

                notizie_inviate.popitem(last=False)

        except Exception as e:

            logging.error(f"❌ Errore nell'invio della notizia '{titolo}': {e}")



async def periodic_fetch():

    while True:

        await fetch_and_send_news()

        # Attende 60 secondi prima del prossimo controllo

        await asyncio.sleep(300)



async def main():

    # Invia l'email di avvio

    send_start_email()

    await send_start_message()

    asyncio.create_task(periodic_fetch())

    while True:

        await asyncio.sleep(3600)



if __name__ == "__main__":

    asyncio.run(main())

