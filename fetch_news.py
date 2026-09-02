import os
import sys
import re
import time
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
import dateutil.parser
import feedparser
import requests
from bs4 import BeautifulSoup

from database import upsert_articles, init_db, get_stats

# Setup structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("fetch_news")

RSS_FEEDS = [
    # --- Indian Domestic Media ---
    {
        "source": "Economic Times",
        "feed_name": "ET Markets",
        "url": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"
    },
    {
        "source": "Economic Times",
        "feed_name": "ET Stocks",
        "url": "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms"
    },
    {
        "source": "Business Standard",
        "feed_name": "BS Top Stories",
        "url": "https://www.business-standard.com/rss/home_page_top_stories.rss"
    },
    {
        "source": "LiveMint",
        "feed_name": "LiveMint Markets",
        "url": "https://www.livemint.com/rss/markets"
    },
    {
        "source": "Financial Express",
        "feed_name": "FE Markets",
        "url": "https://www.financialexpress.com/market/feed/"
    },

    # --- International & Global Wire (High Frequency 24/7) ---
    {
        "source": "Reuters",
        "feed_name": "Reuters Global Economy",
        "url": "https://www.investing.com/rss/news_14.rss"
    },
    {
        "source": "Reuters",
        "feed_name": "Reuters Market Wire",
        "url": "https://www.investing.com/rss/news_25.rss"
    },
    {
        "source": "Reuters",
        "feed_name": "Reuters Currencies & FX",
        "url": "https://www.investing.com/rss/news_1.rss"
    },
    {
        "source": "Bloomberg",
        "feed_name": "Bloomberg Markets Wire",
        "url": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml"
    },
    {
        "source": "Bloomberg",
        "feed_name": "Bloomberg World Macro",
        "url": "https://feeds.bbci.co.uk/news/business/rss.xml"
    },
    {
        "source": "Yahoo Finance",
        "feed_name": "Yahoo Market Wire",
        "url": "https://finance.yahoo.com/news/rssindex"
    },
    {
        "source": "Yahoo Finance",
        "feed_name": "Yahoo Asia & Global",
        "url": "https://sg.finance.yahoo.com/news/rssindex"
    },
    {
        "source": "CNBC",
        "feed_name": "CNBC World Top",
        "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100727362"
    },
    {
        "source": "CNBC",
        "feed_name": "CNBC US Markets",
        "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839069"
    },
    {
        "source": "CNBC",
        "feed_name": "CNBC Economy",
        "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258"
    },
    {
        "source": "Investing.com",
        "feed_name": "Investing Stocks",
        "url": "https://www.investing.com/rss/stock.rss"
    },
    {
        "source": "Investing.com",
        "feed_name": "Investing Global News",
        "url": "https://www.investing.com/rss/news.rss"
    },
    {
        "source": "Financial Times",
        "feed_name": "FT MarketWatch",
        "url": "https://feeds.content.dowjones.io/public/rss/mw_topstories"
    },

    # --- Trump Truth & Tariff Wire ---
    {
        "source": "Trump Wire",
        "feed_name": "Trump Truth & Market Wire",
        "url": "https://news.google.com/rss/search?q=%22Donald+Trump%22+(%22Truth+Social%22+OR+tariffs+OR+markets+OR+economy+OR+trade+OR+Fed+OR+crypto)+when:1d&hl=en-US&gl=US&ceid=US:en"
    }
]

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

# Sentiment & Tagging dictionary for Indian Financial Markets
BULLISH_KEYWORDS = [
    r"\bsurge(s|d)?\b", r"\brall(y|ies|ied)\b", r"\bsoar(s|ed|ing)?\b", r"\bjump(s|ed|ing)?\b",
    r"\bgain(s|ed|ing)?\b", r"\bclimbs?\b", r"\badvance(s|d)?\b", r"\brecord high\b",
    r"\ball-time high\b", r"\b52-week high\b", r"\bprofit surges?\b", r"\bprofit jump(s|ed)?\b",
    r"\bprofit up\b", r"\bpat up\b", r"\bbull(ish|s)?\b", r"\bupgrade(s|d)?\b", r"\boutperform\b",
    r"\bgrowth\b", r"\bexpanded\b", r"\bpositive\b", r"\bgreen\b", r"\bbounce(s|d)?\b",
    r"\buptick\b", r"\bmultibagger\b", r"\bbreakout\b", r"\bhigher\b", r"\bdividend\b",
    r"\bbonus issue\b", r"\bbuyback\b", r"\border win\b", r"\bbagged order\b"
]

BEARISH_KEYWORDS = [
    r"\bplunge(s|d)?\b", r"\bslump(s|ed)?\b", r"\bcrash(es|ed)?\b", r"\btumble(s|d)?\b",
    r"\bdrop(s|ped|ping)?\b", r"\bfall(s|en|ing)?\b", r"\bslide(s)?\b", r"\bdecline(s|d)?\b",
    r"\bsell-?off\b", r"\bloss(es)?\b", r"\bnet loss\b", r"\bprofit drop(s|ped)?\b",
    r"\bprofit falls?\b", r"\bbear(ish|s)?\b", r"\bdowngrade(s|d)?\b", r"\bunderperform\b",
    r"\bdip(s|ped)?\b", r"\bbleed(ing)?\b", r"\bred\b", r"\bdrag(ged|s)?\b",
    r"\bdownward\b", r"\bheadwinds?\b", r"\blower\b", r"\bweak(er|ness)?\b",
    r"\bresignation\b", r"\bpenalty\b", r"\bdefault\b"
]

EARNINGS_KEYWORDS = [
    r"\bq[1-4]\b", r"\bquarter(ly)?\b", r"\bfinancial results\b", r"\bearnings\b",
    r"\brevenue\b", r"\bnet profit\b", r"\bpat\b", r"\bebitda\b", r"\bdividend\b",
    r"\bguidance\b", r"\bmargins?\b", r"\bunaudited financial\b", r"\baudited financial\b"
]

POLICY_KEYWORDS = [
    r"\brbi\b", r"\bsebi\b", r"\brepo rate\b", r"\bmonetary policy\b", r"\binterest rate(s)?\b",
    r"\binflation\b", r"\bgdp\b", r"\bfed\b", r"\bfederal reserve\b", r"\bbudget\b",
    r"\btax(ation)?\b", r"\bfiscal\b", r"\bgovernment\b", r"\bgovernor\b", r"\bregulation\b"
]

IPO_KEYWORDS = [
    r"\bipo\b", r"\binitial public offer(ing)?\b", r"\blisting\b", r"\bsubscription\b",
    r"\bgrey market\b", r"\bgmp\b", r"\banchor investor\b"
]

# ==============================================================================
# Article Classification (Important vs Filing vs General)
# ==============================================================================

# News Outlets General Important Keywords
IMPORTANT_KEYWORDS = [
    "crash", "plunge", "surge", "record high", "record low",
    "circuit", "rbi", "repo rate", "interest rate", "recession", "war", "ban", "merger",
    "acquisition", "ipo", "results", "scam", "fraud", "resigns", "bankruptcy", "default",
    "sebi", "budget", "tariff"
]

FILING_KEYWORDS = [
    "regulation 30", "lodr", "agm", "annual general meeting",
    "newspaper publication", "disclosure under regulation", "clarification on price movement",
    "board meeting intimation", "postal ballot", "record date", "trading window", "annual report"
]

PERCENTAGE_DIRECTION_PATTERN = re.compile(
    r'(?:\d+(?:\.\d+)?%|%\s*\d+(?:\.\d+)?).*(?:up|down|fall|rise|jump|drop|surge|gain|loss|plunge)|(?:up|down|fall|rise|jump|drop|surge|gain|loss|plunge).*(?:\d+(?:\.\d+)?%|%\s*\d+(?:\.\d+)?)',
    re.IGNORECASE
)

# Strict Whitelist Pattern for NSE / BSE Corporate Filings: ONLY Genuine Financial Results
FILING_RESULTS_PATTERN = re.compile(
    r'\b(financial results?|quarterly results?|un-?audited (?:financial )?results?|audited (?:financial )?results?|results for the quarter)\b',
    re.IGNORECASE
)

FILING_ROUTINE_EXCLUSIONS = re.compile(
    r'\b(board meeting intimation|prior intimation|intimation of board meeting|newspaper publication|copy of newspaper|clarification\s*[-–]\s*financial results|clarification on price)\b',
    re.IGNORECASE
)

def is_exchange_filing_source(source_name: str, feed_name: str = "", link: str = "") -> bool:
    """Identifies whether an article originates from an official exchange filing stream."""
    s = (source_name or "").lower()
    f = (feed_name or "").lower()
    l = (link or "").lower()
    if "nse" in s or "bse" in s or "exchange" in s:
        return True
    if "filing" in f or "corporate" in f or "nse" in f or "bse" in f:
        return True
    if "bseindia.com" in l or "nseindia.com" in l:
        return True
    return False

def is_important_filing(title: str) -> bool:
    """Strict check: ONLY genuine Financial Results are marked as Important from BSE/NSE."""
    t = title.strip()
    if FILING_ROUTINE_EXCLUSIONS.search(t):
        return False
    if FILING_RESULTS_PATTERN.search(t):
        return True
    return False

def is_multi_source_breaking(article: Dict[str, Any], batch_articles: List[Dict[str, Any]]) -> bool:
    """
    Checks if a story appears from 2+ different GENUINE news outlets in the batch.
    Excludes NSE/BSE corporate filings from this check entirely.
    """
    src_a = (article.get("source") or "").lower()
    feed_a = (article.get("feed_name") or "").lower()
    link_a = (article.get("link") or "").lower()
    if is_exchange_filing_source(src_a, feed_a, link_a):
        return False

    title_a = re.sub(r"[^\w\s]", "", (article.get("title") or "").lower())
    words_a = set(w for w in title_a.split() if len(w) > 3)
    if len(words_a) < 3:
        return False

    for other in batch_articles:
        if other.get("link") == article.get("link"):
            continue
        src_b = (other.get("source") or "").lower()
        feed_b = (other.get("feed_name") or "").lower()
        link_b = (other.get("link") or "").lower()
        if is_exchange_filing_source(src_b, feed_b, link_b):
            continue
        if src_a != src_b:
            title_b = re.sub(r"[^\w\s]", "", (other.get("title") or "").lower())
            words_b = set(w for w in title_b.split() if len(w) > 3)
            overlap = words_a.intersection(words_b)
            if len(overlap) >= 4 or (len(words_a) > 0 and (len(overlap) / len(words_a)) >= 0.6):
                return True
    return False

def classify_article(article: Dict[str, Any], batch_articles: Optional[List[Dict[str, Any]]] = None) -> str:
    """
    Classifies an article into exactly one type:
      - PATH 1: For NSE/BSE Corporate Filings:
          ONLY genuine Financial Results -> 'important'
          ALL other corporate filings -> 'filing'
      - PATH 2: For Genuine News Outlets (ET, BS, Mint, MC, Reuters, CNBC, Yahoo, Investing, FT, Trump Wire):
          STEP A: 'important' (keywords, % volatility, cross-source breaking)
          STEP B: 'filing'
          STEP C: 'general'
    """
    title = (article.get("title") or "").strip()
    src = (article.get("source") or "").strip()
    feed = (article.get("feed_name") or "").strip()
    link = (article.get("link") or "").strip()

    # --- PATH 1: NSE / BSE Corporate Filings (ONLY FINANCIAL RESULTS ARE IMPORTANT) ---
    if is_exchange_filing_source(src, feed, link):
        if is_important_filing(title):
            return "important"
        return "filing"

    # --- PATH 2: Genuine News Outlets & Trump Wire ---
    title_lower = title.lower()

    # STEP A: Check "Important" for news media
    for kw in IMPORTANT_KEYWORDS:
        if re.search(r"\b" + re.escape(kw) + r"\b", title_lower):
            return "important"

    if PERCENTAGE_DIRECTION_PATTERN.search(title_lower):
        return "important"

    if batch_articles and is_multi_source_breaking(article, batch_articles):
        return "important"

    # STEP B: Check "Filing"
    for fkw in FILING_KEYWORDS:
        if fkw in title_lower:
            return "filing"

    # STEP C: General
    return "general"

def clean_html(text: str) -> str:
    """Strips HTML tags, handles entities, and cleans whitespace."""
    if not text:
        return ""
    try:
        soup = BeautifulSoup(text, "html.parser")
        clean_text = soup.get_text(separator=" ", strip=True)
    except Exception:
        clean_text = re.sub(r"<[^>]+>", "", text)

    clean_text = clean_text.replace("\xa0", " ").replace("&amp;", "&").replace("&quot;", '"').replace("&apos;", "'")
    clean_text = re.sub(r"\s+", " ", clean_text).strip()
    return clean_text

def parse_date(date_str: Optional[str], entry: Any = None) -> Tuple[datetime, str]:
    """Parses various date representations into UTC datetime and readable IST string."""
    dt = None

    if entry and hasattr(entry, "published_parsed") and entry.published_parsed:
        try:
            dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        except Exception:
            pass

    if not dt and entry and hasattr(entry, "updated_parsed") and entry.updated_parsed:
        try:
            dt = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
        except Exception:
            pass

    if not dt and date_str:
        try:
            parsed = dateutil.parser.parse(date_str)
            if parsed.tzinfo is None:
                # If date is from Indian exchange (e.g. NSE/BSE without timezone offset), treat as IST (+05:30)
                from dateutil import tz
                ist_zone = tz.gettz("Asia/Kolkata")
                dt = parsed.replace(tzinfo=ist_zone).astimezone(timezone.utc)
            else:
                dt = parsed.astimezone(timezone.utc)
        except Exception:
            pass

    if not dt:
        dt = datetime.now(timezone.utc)

    # Format human-readable string in IST (+05:30)
    try:
        from dateutil import tz
        ist_zone = tz.gettz("Asia/Kolkata")
        ist_dt = dt.astimezone(ist_zone)
        formatted_str = ist_dt.strftime("%d %b %Y, %I:%M %p IST")
    except Exception:
        formatted_str = dt.strftime("%d %b %Y, %H:%M UTC")

    return dt, formatted_str

def analyze_sentiment_and_category(title: str, description: str) -> Tuple[str, str]:
    """Determines market sentiment and asset category from title and description."""
    full_text = f"{title} {description}".lower()

    # Determine Category
    category = "MARKETS"
    if any(re.search(pat, full_text) for pat in IPO_KEYWORDS):
        category = "IPO"
    elif any(re.search(pat, full_text) for pat in EARNINGS_KEYWORDS):
        category = "EARNINGS"
    elif any(re.search(pat, full_text) for pat in POLICY_KEYWORDS):
        category = "POLICY"
    elif any(word in full_text for word in ["stock", "share", "equity", "nifty", "sensex", "tcs", "reliance", "hdfc", "infy", "board meeting", "filing"]):
        category = "STOCKS"

    # Determine Sentiment
    bullish_matches = sum(1 for pat in BULLISH_KEYWORDS if re.search(pat, full_text))
    bearish_matches = sum(1 for pat in BEARISH_KEYWORDS if re.search(pat, full_text))

    if bullish_matches > bearish_matches and bullish_matches > 0:
        sentiment = "BULLISH"
    elif bearish_matches > bullish_matches and bearish_matches > 0:
        sentiment = "BEARISH"
    elif category == "EARNINGS":
        sentiment = "EARNINGS"
    elif category == "POLICY":
        sentiment = "POLICY"
    else:
        sentiment = "NEUTRAL"

    return sentiment, category

def fetch_feed_data(feed_info: Dict[str, str]) -> List[Dict[str, Any]]:
    """Fetches and parses a single RSS feed safely."""
    source = feed_info["source"]
    feed_name = feed_info["feed_name"]
    url = feed_info["url"]

    logger.info(f"Fetching [{source} - {feed_name}] from {url}...")
    articles = []

    try:
        headers = {"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml, text/xml, */*"}
        resp = requests.get(url, headers=headers, timeout=12)
        resp.raise_for_status()

        feed = feedparser.parse(resp.content)
        if feed.bozo and not feed.entries:
            feed = feedparser.parse(resp.text)

        logger.info(f"Retrieved {len(feed.entries)} entries from [{feed_name}]")

        for entry in feed.entries:
            title = clean_html(getattr(entry, "title", ""))
            link = getattr(entry, "link", "").strip()

            if not title or not link:
                continue

            description = ""
            if hasattr(entry, "summary") and entry.summary:
                description = clean_html(entry.summary)
            elif hasattr(entry, "description") and entry.description:
                description = clean_html(entry.description)

            if description == title:
                description = ""

            date_str = getattr(entry, "published", None) or getattr(entry, "updated", None)
            pub_dt, pub_str = parse_date(date_str, entry)
            sentiment, category = analyze_sentiment_and_category(title, description)

            articles.append({
                "title": title,
                "link": link,
                "source": source,
                "feed_name": feed_name,
                "description": description,
                "published_at": pub_dt,
                "published_str": pub_str,
                "sentiment": sentiment,
                "category": category
            })

    except Exception as e:
        logger.warning(f"Error fetching RSS feed {url}: {e}")

    return articles

def fetch_nse_corporate_announcements() -> List[Dict[str, Any]]:
    """Fetches real-time corporate announcements directly from NSE India."""
    logger.info("Fetching direct corporate announcements from NSE India API...")
    articles = []
    url = "https://www.nseindia.com/api/corporate-announcements?index=equities"

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-announcements"
    }

    try:
        session = requests.Session()
        session.headers.update(headers)
        resp = session.get(url, timeout=12)

        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                logger.info(f"Retrieved {len(data)} announcements from NSE India")
                for item in data:
                    symbol = item.get("symbol", "").strip()
                    company_name = item.get("sm_name", "").strip() or symbol
                    desc = item.get("desc", "").strip()
                    attch_text = item.get("attchmntText", "").strip()
                    pdf_file = item.get("attchmntFile", "").strip()
                    date_str = item.get("sort_date") or item.get("an_dt")

                    title = f"[{symbol}] {desc} - {company_name}"
                    description = attch_text if attch_text else desc

                    # If PDF attachment exists, link directly to PDF, else NSE company filing page
                    link = pdf_file if pdf_file.startswith("http") else f"https://www.nseindia.com/companies-listing/corporate-filings-announcements?symbol={symbol}"

                    pub_dt, pub_str = parse_date(date_str)
                    sentiment, category = analyze_sentiment_and_category(title, description)

                    articles.append({
                        "title": clean_html(title),
                        "link": link,
                        "source": "NSE India",
                        "feed_name": "NSE Corporate Filings",
                        "description": clean_html(description),
                        "published_at": pub_dt,
                        "published_str": pub_str,
                        "sentiment": sentiment,
                        "category": "STOCKS"
                    })
    except Exception as e:
        logger.warning(f"Failed to fetch NSE India announcements: {e}")

    return articles

def fetch_bse_corporate_announcements() -> List[Dict[str, Any]]:
    """Fetches real-time corporate announcements directly from BSE India."""
    logger.info("Fetching direct corporate announcements from BSE India API...")
    articles = []
    url = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w?pageno=1&strCat=-1&strPrevDate=&strScrip=&strSearch=P&strToDate=&strType=C"

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.bseindia.com/",
        "Origin": "https://www.bseindia.com"
    }

    try:
        resp = requests.get(url, headers=headers, timeout=12)
        if resp.status_code == 200:
            data = resp.json()
            table = data.get("Table", [])
            logger.info(f"Retrieved {len(table)} announcements from BSE India")
            for item in table:
                scrip_cd = str(item.get("SCRIP_CD", "")).strip()
                company_name = item.get("SLONGNAME", "").strip()
                news_sub = item.get("NEWSSUB", "").strip()
                more_text = item.get("MORE", "") or item.get("HEADLINE", "")
                attach_name = item.get("ATTACHMENTNAME", "").strip()
                date_str = item.get("DT_TM") or item.get("NEWS_DT")

                title = news_sub if news_sub else f"[{company_name}] Corporate Update"
                description = more_text if more_text else news_sub

                if attach_name:
                    link = f"https://www.bseindia.com/xml-data/corpfiling/AttachLive/{attach_name}"
                else:
                    link = f"https://www.bseindia.com/stock-share-price/scrip/{scrip_cd}/"

                pub_dt, pub_str = parse_date(date_str)
                sentiment, category = analyze_sentiment_and_category(title, description)

                articles.append({
                    "title": clean_html(title),
                    "link": link,
                    "source": "BSE India",
                    "feed_name": "BSE Corporate Filings",
                    "description": clean_html(description),
                    "published_at": pub_dt,
                    "published_str": pub_str,
                    "sentiment": sentiment,
                    "category": "STOCKS"
                })
    except Exception as e:
        logger.warning(f"Failed to fetch BSE India announcements: {e}")

    return articles

def fetch_moneycontrol_live() -> List[Dict[str, Any]]:
    """Scrapes live market articles directly from Moneycontrol Markets webpage."""
    url = "https://www.moneycontrol.com/news/business/markets/"
    logger.info("Fetching live articles directly from Moneycontrol...")
    articles = []
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9"
    }

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            now_dt = datetime.now(timezone.utc)
            now_str = now_dt.strftime("%d %b %Y, %I:%M %p IST")

            for li in soup.find_all("li", class_="clearfix"):
                h2 = li.find("h2") or li.find("h3")
                a = li.find("a")
                p = li.find("p")
                span = li.find("span")
                if h2 and a and a.get("href"):
                    title = clean_html(h2.get_text(strip=True))
                    link = a.get("href", "").strip()
                    desc = clean_html(p.get_text(strip=True)) if p else title
                    time_text = span.get_text(strip=True) if span else ""

                    if not title or not link or "javascript:" in link:
                        continue

                    # Parse published time or fallback to now
                    pub_dt = now_dt
                    pub_str = now_str
                    if time_text:
                        try:
                            clean_time = re.sub(r"\s+IST$", "", time_text.strip())
                            parsed = dateutil.parser.parse(clean_time)
                            pub_dt = parsed.replace(tzinfo=timezone.utc)
                            pub_str = time_text
                        except Exception:
                            pass

                    sentiment, category = analyze_sentiment_and_category(title, desc)
                    articles.append({
                        "title": title,
                        "link": link,
                        "source": "Moneycontrol",
                        "feed_name": "MC Live Markets",
                        "description": desc,
                        "published_at": pub_dt,
                        "published_str": pub_str,
                        "sentiment": sentiment,
                        "category": category
                    })
            logger.info(f"Retrieved {len(articles)} live articles directly from Moneycontrol")
    except Exception as e:
        logger.warning(f"Failed to fetch live Moneycontrol articles: {e}")

    return articles

def fetch_and_store_all_news() -> Tuple[int, int]:
    """
    Main ingestion coordinator:
    1. Fetches RSS feeds (ET, BS, LiveMint, Reuters, Bloomberg, Yahoo, CNBC, Investing).
    2. Fetches direct NSE & BSE Corporate Announcements.
    3. Fetches live Moneycontrol Market News.
    4. Deduplicates across all sources.
    5. Sorts newest first.
    6. Upserts into database (Postgres or SQLite).
    """
    start_time = time.time()
    init_db()

    all_articles: List[Dict[str, Any]] = []
    seen_links = set()

    # 1. Fetch RSS Feeds
    for feed_info in RSS_FEEDS:
        feed_articles = fetch_feed_data(feed_info)
        for art in feed_articles:
            if art["link"] not in seen_links:
                seen_links.add(art["link"])
                all_articles.append(art)

    # 2. Fetch Direct NSE Corporate Announcements
    nse_articles = fetch_nse_corporate_announcements()
    for art in nse_articles:
        if art["link"] not in seen_links:
            seen_links.add(art["link"])
            all_articles.append(art)

    # 3. Fetch Direct BSE Corporate Announcements
    bse_articles = fetch_bse_corporate_announcements()
    for art in bse_articles:
        if art["link"] not in seen_links:
            seen_links.add(art["link"])
            all_articles.append(art)

    # 4. Fetch Direct Moneycontrol Live News
    mc_articles = fetch_moneycontrol_live()
    for art in mc_articles:
        if art["link"] not in seen_links:
            seen_links.add(art["link"])
            all_articles.append(art)

    # 4. Classify each article into exactly one type: 'important', 'filing', or 'general'
    for art in all_articles:
        art["type"] = classify_article(art, all_articles)

    # Sort all articles by published_at DESC (newest first)
    all_articles.sort(key=lambda x: x["published_at"], reverse=True)

    logger.info(f"Total unique articles parsed across all sources: {len(all_articles)}")

    # Store into database
    inserted, skipped = upsert_articles(all_articles)
    elapsed = time.time() - start_time

    logger.info(f"Ingestion complete in {elapsed:.2f}s: {inserted} newly inserted, {skipped} existing skipped.")

    # Broadcast real-time Web Push alert ONLY if a brand new important story was inserted
    if inserted > 0:
        try:
            from push_service import broadcast_news_alerts
            pushed = broadcast_news_alerts()
            if pushed > 0:
                logger.info(f"Broadcasted breaking news push notification to {pushed} devices.")
        except Exception as push_err:
            logger.warning(f"Push notification broadcast issue: {push_err}")

    stats = get_stats()
    logger.info(f"Database status: {stats['total_articles']} total stored articles. Latest: {stats['latest_article_time']}")

    return inserted, skipped

def backfill_article_types_in_db() -> int:
    """Classifies and updates all existing articles in the database in a fast batch."""
    from database import get_db_connection, is_postgres
    conn = get_db_connection()
    updated = 0
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, title, link, source, description, type FROM articles")
        rows = cur.fetchall()
        if is_postgres():
            colnames = [desc[0] for desc in cur.description]
            articles = [dict(zip(colnames, r)) for r in rows]
        else:
            articles = [dict(r) for r in rows]

        updates = []
        for art in articles:
            new_type = classify_article(art)
            if art.get("type") != new_type:
                updates.append((new_type, art["id"]))

        if updates:
            if is_postgres():
                cur.executemany("UPDATE articles SET type = %s WHERE id = %s", updates)
            else:
                cur.executemany("UPDATE articles SET type = ? WHERE id = ?", updates)
            conn.commit()
            updated = len(updates)
        logger.info(f"Backfilled classification types for {updated} articles.")
    except Exception as e:
        logger.warning(f"Error backfilling article types: {e}")
    finally:
        conn.close()
    return updated

# ==============================================================================
# Economic Calendar & Market Holiday Data Services
# ==============================================================================

ECONOMIC_CALENDAR_CACHE = {
    "data": [],
    "last_updated": 0
}

HOLIDAY_CALENDAR_CACHE = {
    "data": [],
    "last_updated": 0
}

ALLOWED_CALENDAR_COUNTRIES = {"IND", "USA", "US", "JPN", "CHN"}

CALENDAR_COUNTRY_MAP = {
    "IND": ("India", "🇮🇳"),
    "USA": ("USA", "🇺🇸"),
    "US": ("USA", "🇺🇸"),
    "CHN": ("China", "🇨🇳"),
    "JPN": ("Japan", "🇯🇵")
}

FALLBACK_ECONOMIC_EVENTS = [
    {"date": "31 Aug, Mon", "time": "07:00 AM", "country": "China", "flag": "🇨🇳", "country_code": "CHN", "event_name": "NBS Manufacturing PMI AUG", "impact": "Low", "expected": "49.7", "actual": "49.8", "previous": "49.2"},
    {"date": "31 Aug, Mon", "time": "04:00 PM", "country": "India", "flag": "🇮🇳", "country_code": "IND", "event_name": "GDP Growth Rate YoY Q1", "impact": "High", "expected": "7.1%", "actual": "7.8%", "previous": "7.8%"},
    {"date": "03 Sep, Thu", "time": "06:00 PM", "country": "USA", "flag": "🇺🇸", "country_code": "USA", "event_name": "Initial Jobless Claims AUG/29", "impact": "Medium", "expected": "205K", "actual": "-", "previous": "203K"},
    {"date": "04 Sep, Fri", "time": "06:00 PM", "country": "USA", "flag": "🇺🇸", "country_code": "USA", "event_name": "Non Farm Payrolls AUG", "impact": "High", "expected": "58K", "actual": "-", "previous": "-23K"},
    {"date": "08 Sep, Tue", "time": "05:20 AM", "country": "Japan", "flag": "🇯🇵", "country_code": "JPN", "event_name": "GDP Growth Rate QoQ Final", "impact": "High", "expected": "0.7%", "actual": "-", "previous": "0.8%"},
    {"date": "10 Sep, Thu", "time": "06:00 PM", "country": "USA", "flag": "🇺🇸", "country_code": "USA", "event_name": "Initial Jobless Claims SEP/05", "impact": "Medium", "expected": "-", "actual": "-", "previous": "-"},
    {"date": "10 Sep, Thu", "time": "07:30 PM", "country": "USA", "flag": "🇺🇸", "country_code": "USA", "event_name": "Existing Home Sales AUG", "impact": "Medium", "expected": "-", "actual": "-", "previous": "4.06M"},
    {"date": "11 Sep, Fri", "time": "06:00 PM", "country": "USA", "flag": "🇺🇸", "country_code": "USA", "event_name": "Inflation Rate YoY AUG", "impact": "High", "expected": "-", "actual": "-", "previous": "3.4%"},
    {"date": "12 Sep, Sat", "time": "04:00 PM", "country": "India", "flag": "🇮🇳", "country_code": "IND", "event_name": "Inflation Rate YoY AUG", "impact": "High", "expected": "-", "actual": "-", "previous": "4.45%"},
    {"date": "14 Sep, Mon", "time": "12:00 PM", "country": "India", "flag": "🇮🇳", "country_code": "IND", "event_name": "WPI Inflation YoY AUG", "impact": "Medium", "expected": "-", "actual": "-", "previous": "9.78%"},
    {"date": "15 Sep, Tue", "time": "07:30 AM", "country": "China", "flag": "🇨🇳", "country_code": "CHN", "event_name": "Industrial Production YoY AUG", "impact": "Medium", "expected": "-", "actual": "-", "previous": "4.5%"},
    {"date": "16 Sep, Wed", "time": "06:00 PM", "country": "USA", "flag": "🇺🇸", "country_code": "USA", "event_name": "Retail Sales YoY AUG", "impact": "Medium", "expected": "-", "actual": "-", "previous": "5%"},
    {"date": "16 Sep, Wed", "time": "11:30 PM", "country": "USA", "flag": "🇺🇸", "country_code": "USA", "event_name": "Fed Interest Rate Decision", "impact": "High", "expected": "-", "actual": "-", "previous": "3.75%"},
    {"date": "17 Sep, Thu", "time": "06:00 PM", "country": "USA", "flag": "🇺🇸", "country_code": "USA", "event_name": "Housing Starts AUG", "impact": "Medium", "expected": "-", "actual": "-", "previous": "1.239M"},
    {"date": "19 Sep, Fri", "time": "08:30 AM", "country": "Japan", "flag": "🇯🇵", "country_code": "JPN", "event_name": "BoJ Interest Rate Decision", "impact": "High", "expected": "0.25%", "actual": "-", "previous": "0.25%"}
]

FALLBACK_NSE_HOLIDAYS = [
    {"date": "15-Jan-2026", "weekday": "Thursday", "description": "Municipal Corporation Election", "exchange": "NSE / BSE"},
    {"date": "26-Jan-2026", "weekday": "Monday", "description": "Republic Day", "exchange": "NSE / BSE"},
    {"date": "18-Feb-2026", "weekday": "Wednesday", "description": "Mahashivratri", "exchange": "NSE / BSE"},
    {"date": "04-Mar-2026", "weekday": "Wednesday", "description": "Holi", "exchange": "NSE / BSE"},
    {"date": "20-Mar-2026", "weekday": "Friday", "description": "Id-Ul-Fitr (Ramzan Id)", "exchange": "NSE / BSE"},
    {"date": "30-Mar-2026", "weekday": "Monday", "description": "Shri Ram Navami", "exchange": "NSE / BSE"},
    {"date": "03-Apr-2026", "weekday": "Friday", "description": "Good Friday", "exchange": "NSE / BSE"},
    {"date": "14-Apr-2026", "weekday": "Tuesday", "description": "Dr. Baba Saheb Ambedkar Jayanti", "exchange": "NSE / BSE"},
    {"date": "01-May-2026", "weekday": "Friday", "description": "Maharashtra Day", "exchange": "NSE / BSE"},
    {"date": "15-Aug-2026", "weekday": "Saturday", "description": "Independence Day", "exchange": "NSE / BSE"},
    {"date": "02-Oct-2026", "weekday": "Friday", "description": "Mahatma Gandhi Jayanti", "exchange": "NSE / BSE"},
    {"date": "20-Oct-2026", "weekday": "Tuesday", "description": "Dussehra", "exchange": "NSE / BSE"},
    {"date": "09-Nov-2026", "weekday": "Monday", "description": "Diwali Laxmi Pujan (Muhurat Trading)", "exchange": "NSE / BSE"},
    {"date": "10-Nov-2026", "weekday": "Tuesday", "description": "Diwali Balipratipada", "exchange": "NSE / BSE"},
    {"date": "24-Nov-2026", "weekday": "Tuesday", "description": "Gurunanak Jayanti", "exchange": "NSE / BSE"},
    {"date": "25-Dec-2026", "weekday": "Friday", "description": "Christmas", "exchange": "NSE / BSE"}
]

def determine_calendar_impact(event_name: str) -> str:
    name_lower = event_name.lower()
    if any(k in name_lower for k in [
        "rate decision", "interest rate", "gdp", "fed", "rbi",
        "non farm payroll", "cpi", "inflation rate", "fomc", "repo rate"
    ]):
        return "High"
    elif any(k in name_lower for k in [
        "pmi", "jobless claims", "retail sales", "trade balance",
        "ppi", "industrial production", "housing", "monetary", "unemployment", "crude oil"
    ]):
        return "Medium"
    return "Low"

def fetch_live_economic_calendar() -> List[Dict[str, Any]]:
    global ECONOMIC_CALENDAR_CACHE
    now = time.time()

    if ECONOMIC_CALENDAR_CACHE["data"] and (now - ECONOMIC_CALENDAR_CACHE["last_updated"] < 600):
        return ECONOMIC_CALENDAR_CACHE["data"]

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }

    events = []
    try:
        r = requests.get("https://www.moneycontrol.com/economic-calendar/", headers=headers, timeout=6)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            tables = soup.find_all("table")
            if len(tables) >= 3:
                table = tables[2]
                for tr in table.find_all("tr"):
                    tds = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                    if len(tds) >= 8 and tds[1] and tds[2] and tds[3]:
                        code = tds[2].upper()
                        if code not in ALLOWED_CALENDAR_COUNTRIES:
                            continue
                        time_str = tds[1]
                        title = tds[3]
                        actual = tds[5] if len(tds) > 5 and tds[5] != "" else "-"
                        previous = tds[6] if len(tds) > 6 and tds[6] != "" else "-"
                        expected = tds[7] if len(tds) > 7 and tds[7] != "" else "-"
                        country_name, flag = CALENDAR_COUNTRY_MAP.get(code, (code, "🌐"))

                        today_str = datetime.now().strftime("%d %b, %a")

                        events.append({
                            "date": today_str,
                            "time": time_str,
                            "country_code": code,
                            "country": country_name,
                            "flag": flag,
                            "event_name": title,
                            "impact": determine_calendar_impact(title),
                            "actual": actual,
                            "previous": previous,
                            "expected": expected
                        })
    except Exception as e:
        logger.warning(f"Error fetching live economic calendar: {e}")

    if events:
        combined = list(events)
        existing_names = {e["event_name"].lower() for e in events}
        for fb in FALLBACK_ECONOMIC_EVENTS:
            if fb["event_name"].lower() not in existing_names:
                combined.append(fb)

        ECONOMIC_CALENDAR_CACHE["data"] = combined
        ECONOMIC_CALENDAR_CACHE["last_updated"] = now
        return combined

    return FALLBACK_ECONOMIC_EVENTS

def fetch_live_market_holidays() -> List[Dict[str, Any]]:
    global HOLIDAY_CALENDAR_CACHE
    now = time.time()

    if HOLIDAY_CALENDAR_CACHE["data"] and (now - HOLIDAY_CALENDAR_CACHE["last_updated"] < 86400):
        return HOLIDAY_CALENDAR_CACHE["data"]

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }

    holidays = []
    try:
        s = requests.Session()
        s.get("https://www.nseindia.com", headers=headers, timeout=5)
        r = s.get("https://www.nseindia.com/api/holiday-master?type=trading", headers=headers, timeout=5)
        if r.status_code == 200:
            data = r.json()
            cbm_list = data.get("CBM", []) or data.get("CM", [])
            for h in cbm_list:
                holidays.append({
                    "date": h.get("tradingDate", ""),
                    "weekday": h.get("weekDay", ""),
                    "description": h.get("description", ""),
                    "exchange": "NSE / BSE"
                })
    except Exception as e:
        logger.warning(f"Error fetching NSE holidays: {e}")

    if holidays:
        HOLIDAY_CALENDAR_CACHE["data"] = holidays
        HOLIDAY_CALENDAR_CACHE["last_updated"] = now
        return holidays

    return FALLBACK_NSE_HOLIDAYS

def main():
    logger.info("=== Starting Automated Stock Market News Scraper ===")
    try:
        backfill_article_types_in_db()
        inserted, skipped = fetch_and_store_all_news()
        logger.info(f"=== Execution Succeeded. Exiting (inserted: {inserted}, skipped: {skipped}) ===")
        sys.exit(0)
    except Exception as e:
        logger.critical(f"Fatal error during news fetch: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
