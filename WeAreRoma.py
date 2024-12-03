import feedparser
from datetime import datetime, timedelta
import requests
from difflib import SequenceMatcher


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


def remove_duplicates(articles, threshold=0.6):
    """
    Rimuove articoli con titoli simili, mantenendo quello con la maggiore rilevanza.
    """
    unique_articles = []
    for article in articles:
        # Cerca un articolo simile già nella lista dei risultati unici
        similar_article = next(
            (
                unique_article
                for unique_article in unique_articles
                if is_similar(article["title"], unique_article["title"], threshold)
            ),
            None,
        )
        if similar_article:
            # Se esiste un articolo simile, mantieni quello con maggiore rilevanza
            if article["relevance"] > similar_article["relevance"]:
                unique_articles.remove(similar_article)
                unique_articles.append(article)
        else:
            # Se non ci sono articoli simili, aggiungilo alla lista
            unique_articles.append(article)
    return unique_articles


def get_rss_news_trends(
    rss_urls, query, num_articles=10, hours=6, bot_token=None, chat_id=None
):
    """
    Recupera i titoli e i link degli articoli più rilevanti dai feed RSS,
    ordinandoli per "trend" e limitando agli articoli pubblicati entro un numero di ore specificato.
    Gli articoli senza data di pubblicazione aumentano la rilevanza.
    """
    articles_with_date = []
    articles_without_date = []
    current_time = datetime.now()
    time_threshold = current_time - timedelta(hours=hours)

    for rss_url in rss_urls:
        feed = feedparser.parse(rss_url)
        for entry in feed.entries:
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                # Gestione articoli con data di pubblicazione
                published_time = datetime(*entry.published_parsed[:6])
                if published_time >= time_threshold:
                    # Calcola la rilevanza del termine di ricerca
                    title_relevance = entry.title.lower().count(query.lower())
                    summary_relevance = (
                        entry.get("summary", "").lower().count(query.lower())
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
            else:
                # Articolo senza data di pubblicazione
                title_relevance = entry.title.lower().count(query.lower())
                summary_relevance = (
                    entry.get("summary", "").lower().count(query.lower())
                )
                total_relevance = title_relevance + summary_relevance

                if total_relevance > 0:
                    articles_without_date.append(
                        {
                            "title": entry.title,
                            "link": entry.link,
                            "relevance": total_relevance,
                        }
                    )

    # Calcola il bonus totale dagli articoli senza data
    bonus_relevance = sum(
        article["relevance"] * 0.13 for article in articles_without_date
    )

    # Applica il bonus agli articoli con data
    for article in articles_with_date:
        article["relevance"] += bonus_relevance

    # Ordina gli articoli con data per rilevanza (dal più alto al più basso)
    articles_with_date = sorted(
        articles_with_date, key=lambda x: x["relevance"], reverse=True
    )

    # Rimuovi articoli con titoli duplicati o molto simili
    articles_with_date = remove_duplicates(articles_with_date)

    # Limita al numero massimo di articoli richiesti
    articles_with_date = articles_with_date[:num_articles]

    # Trova la rilevanza massima
    max_relevance = (
        max(article["relevance"] for article in articles_with_date)
        if articles_with_date
        else 1
    )

    # Ottieni l'ora corrente
    current_time_str = datetime.now().strftime("%H")

    # Invia ogni articolo separatamente con la rilevanza in percentuale
    if articles_with_date:
        for idx, article in enumerate(articles_with_date, start=1):
            relevance_percentage = (article["relevance"] / max_relevance) * 100
            message = (
                f"Rassegna ore {current_time_str}\n"
                f"Articolo {idx} - Rilevanza {relevance_percentage:.0f}%\n"
                f"<i>{article['published'].strftime('%Y-%m-%d %H:%M:%S')}</i>\n\n"
                f"<b>{article['title']}</b>\n"
                f"{article['link']}\n"
            )
            send_telegram_message(bot_token, chat_id, message)
    else:
        message = f"Nessuna notizia trovata per la ricerca '{query}' nelle ultime {hours} ore."
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

# Parametri del bot Telegram
bot_token = "7801463866:AAGZwnKjlyiCp1dTyOvRY2bBKeoqubTqYcQ"  # Sostituisci con il token del tuo bot
chat_id = "-1002411361533"  # Sostituisci con l'ID della chat del destinatario

# Chiamata alla funzione
get_rss_news_trends(
    rss_urls, "Roma", num_articles=10, hours=6, bot_token=bot_token, chat_id=chat_id
)
