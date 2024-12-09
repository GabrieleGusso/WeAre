import hashlib
import os
import feedparser
from datetime import datetime, timedelta
import requests
from difflib import SequenceMatcher
import pytz

# Fuso orario dell'Europa Centrale
CET = pytz.timezone("Europe/Rome")


# Funzione per inviare il messaggio su Telegram
def send_telegram_message(bot_token, chat_id, message):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
    response = requests.post(url, data=payload)
    return response


def is_similar(title1, title2, threshold=0.6):
    """
    Verifica se due stringhe sono simili oltre una certa soglia.
    """
    return SequenceMatcher(None, title1, title2).ratio() > threshold


def consolidate_relevance(articles, threshold=0.6):
    """
    Combina articoli simili aggiungendo il punteggio dell'articolo scartato
    a quello mantenuto.
    """
    consolidated_articles = []
    for article in articles:
        similar_article = next(
            (
                existing_article
                for existing_article in consolidated_articles
                if is_similar(article["title"], existing_article["title"], threshold)
            ),
            None,
        )
        if similar_article:
            # Aggiungi la rilevanza dell'articolo scartato a quello mantenuto
            similar_article["relevance"] += article["relevance"]
        else:
            consolidated_articles.append(article)
    return consolidated_articles


# Funzione per calcolare l'hash di un articolo
def calculate_article_hash(article):
    """
    Calcola un hash univoco per un articolo basandosi sul titolo e sul link.
    """
    hash_input = f"{article['title']}_{article['link']}".encode("utf-8")
    return hashlib.sha256(hash_input).hexdigest()


# Funzione per caricare il file di log
def load_log(log_file):
    """
    Carica gli articoli dal file di log con punteggi e timestamp.
    """
    if not os.path.exists(log_file):
        return {}
    with open(log_file, "r") as file:
        log_data = {}
        for line in file:
            parts = line.strip().split()
            if len(parts) == 3:
                h, t, relevance = parts
                log_data[h] = (
                    datetime.strptime(t, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=CET),
                    float(relevance),
                )
        return log_data


# Funzione per aggiornare il file di log
def update_log(log_file, articles):
    """
    Aggiorna il file di log con i nuovi articoli e punteggi, rimuovendo quelli
    più vecchi di 24 ore.
    """
    current_time = datetime.now(CET)
    existing_log = load_log(log_file)
    updated_log = {
        h: (t, r)
        for h, (t, r) in existing_log.items()
        if t > current_time - timedelta(hours=24)
    }

    for article in articles:
        updated_log[calculate_article_hash(article)] = (
            current_time,
            article["relevance"],
        )

    with open(log_file, "w") as file:
        for h, (t, r) in updated_log.items():
            file.write(f"{h} {t.strftime('%Y-%m-%dT%H:%M:%S')} {r}\n")


def calculate_relevance(text, keywords):
    """
    Calcola la rilevanza di un testo basandosi sul conteggio delle occorrenze di ogni parola chiave.
    """
    return sum(text.lower().count(keyword.lower()) for keyword in keywords)


def get_rss_news_trends(
    rss_urls,
    keywords,
    num_articles=10,
    hours=6,
    bot_token=None,
    chat_id=None,
    log_file="sent_articles.log",
):
    """
    Recupera i titoli e i link degli articoli più rilevanti dai feed RSS,
    ordinandoli per "trend" e limitando agli articoli pubblicati entro un numero di ore specificato.
    Evita di inviare articoli già inviati nelle ultime 24 ore.
    """
    articles_with_date = []
    current_time = datetime.now(CET)
    time_threshold = current_time - timedelta(hours=hours)

    # Carica il log degli articoli già inviati
    sent_hashes = load_log(log_file)
    max_relevance_logged = max((r for _, r in sent_hashes.values()), default=0)

    for rss_url in rss_urls:
        feed = feedparser.parse(rss_url)
        for entry in feed.entries:
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published_time = CET.localize(datetime(*entry.published_parsed[:6]))
                if published_time >= time_threshold:
                    title_relevance = calculate_relevance(entry.title, keywords)
                    summary_relevance = calculate_relevance(
                        entry.get("summary", ""), keywords
                    )
                    total_relevance = title_relevance + summary_relevance

                    if total_relevance > 0:
                        articles_with_date.append(
                            {
                                "title": entry.title,
                                "link": entry.link,
                                "published": published_time,
                                "relevance": total_relevance,
                            }
                        )

    # Consolidamento del punteggio per articoli simili
    articles_with_date = consolidate_relevance(articles_with_date)

    # Ordina gli articoli consolidati per punteggio di rilevanza
    articles_with_date = sorted(
        articles_with_date, key=lambda x: x["relevance"], reverse=True
    )

    # Genera una lista estesa di articoli per garantire almeno num_articles dopo il filtraggio
    extended_list = articles_with_date[: num_articles * 10]

    new_articles = [
        article
        for article in extended_list
        if calculate_article_hash(article) not in sent_hashes
    ]

    new_articles = new_articles[:num_articles]

    if new_articles:
        new_hashes = []
        max_relevance_current = max(article["relevance"] for article in new_articles)
        max_relevance_global = max(max_relevance_logged, max_relevance_current)

        for idx, article in enumerate(new_articles, start=1):
            relevance_percentage = article["relevance"] / max_relevance_global * 100
            message = (
                f"Rassegna ore {current_time.strftime('%H')}\n"
                f"Articolo {idx} - Rilevanza {relevance_percentage:.0f}%\n"
                f"<i>{article['published'].strftime('%Y-%m-%d %H:%M:%S')}</i>\n\n"
                f"<b>{article['title']}</b>\n"
                f"{article['link']}\n"
            )
            send_telegram_message(bot_token, chat_id, message)
            new_hashes.append(article)

        update_log(log_file, new_articles)
    else:
        message = f"Nessuna notizia trovata per la ricerca '{', '.join(keywords)}' nelle ultime {hours} ore."
        send_telegram_message(bot_token, chat_id, message)


# Configurazione RSS
rss_urls = [
    "https://roma.repubblica.it/rss/cronaca/rss2.0.xml",
    "https://www.corriere.it/dynamic-feed/rss/section/Roma.xml",
    "https://www.ilmessaggero.it/rss/roma.xml",
    "https://www.ilcorrieredellacitta.com/feed",
    "https://www.fanpage.it/roma/feed/",
    "https://www.ansa.it/lazio/notizie/lazio_rss.xml",
]

# Configurazione parole chiave
keywords = ["Roma", "video", "filmato", "incidente", "incendio", "fuoco", "morto", "morta"]

# Parametri del bot Telegram
bot_token = os.getenv("BOT_TOKEN") # dai secrets di GitHub
chat_id = os.getenv("CHAT_ID") # dai secrets di GitHub

# Chiamata alla funzione
get_rss_news_trends(
    rss_urls,
    keywords,
    num_articles=5,
    hours=16,
    bot_token=bot_token,
    chat_id=chat_id,
)
