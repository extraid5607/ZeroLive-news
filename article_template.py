import re
import json
import html
import requests
import urllib.request
import urllib.parse
import concurrent.futures
from bs4 import BeautifulSoup
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from urllib.parse import quote

KNOWN_TICKERS = [
    (r'\b(reliance|jio)\b', '#RELIANCE'),
    (r'\b(tcs|tata consultancy)\b', '#TCS'),
    (r'\b(tata motors|jlr)\b', '#TATAMOTORS'),
    (r'\b(tata steel)\b', '#TATASTEEL'),
    (r'\b(hdfc|hdfc bank)\b', '#HDFCBANK'),
    (r'\b(icici|icici bank)\b', '#ICICIBANK'),
    (r'\b(infosys|infy)\b', '#INFY'),
    (r'\b(sbi|state bank of india)\b', '#SBIN'),
    (r'\b(airtel|bharti airtel)\b', '#BHARTIARTL'),
    (r'\b(itc)\b', '#ITC'),
    (r'\b(l&t|larsen)\b', '#LT'),
    (r'\b(adani|cemindia)\b', '#ADANIENT'),
    (r'\b(maruti|suzuki)\b', '#MARUTI'),
    (r'\b(wipro)\b', '#WIPRO'),
    (r'\b(zomato)\b', '#ZOMATO'),
    (r'\b(nvidia|nvda)\b', '#NVDA'),
    (r'\b(tesla|tsla)\b', '#TSLA'),
    (r'\b(apple|aapl)\b', '#AAPL'),
    (r'\b(microsoft|msft)\b', '#MSFT'),
    (r'\b(amazon|amzn)\b', '#AMZN'),
    (r'\b(google|alphabet)\b', '#GOOGL'),
    (r'\b(crude|oil|brent|opec)\b', '#CRUDE'),
    (r'\b(gold|bullion)\b', '#GOLD'),
    (r'\b(trump|truth social|tariff|tariffs)\b', '#TRUMP')
]

def slugify_title(title: str) -> str:
    """Converts a headline into a clean, URL-safe slug."""
    if not title:
        return "market-news"
    slug = re.sub(r'[^a-zA-Z0-9\s-]', '', title).strip().lower()
    slug = re.sub(r'[\s-]+', '-', slug).strip('-')
    slug = slug[:90].rstrip('-')
    return slug or "market-news"

def extract_tickers(title: str, desc: str) -> List[str]:
    """Extracts relevant stock ticker hashtags from title and description."""
    text = f"{title} {desc}".lower()
    matched = []
    for pattern, tag in KNOWN_TICKERS:
        if re.search(pattern, text, re.IGNORECASE):
            if tag not in matched:
                matched.append(tag)
        if len(matched) >= 4:
            break
    return matched

def get_source_color(source: str) -> str:
    s = (source or '').lower()
    if 'economic times' in s: return '#ff9800'
    if 'business standard' in s: return '#3b82f6'
    if 'livemint' in s or 'mint' in s: return '#10b981'
    if 'moneycontrol' in s: return '#06b6d4'
    if 'bse' in s or 'nse' in s: return '#ec4899'
    if 'reuters' in s or 'bloomberg' in s: return '#f59e0b'
    return '#38bdf8'

_STORY_CACHE: Dict[str, List[str]] = {}

def get_story_paragraphs(url: str, title: str, desc: str, source: str, sentiment: str, tickers: List[str]) -> List[str]:
    """
    Retrieves a rich 3 to 5 paragraph story (5-9 lines) for the article page.
    Attempts live extraction with a fast timeout (3.0s) and caches results.
    If unavailable or blocked, dynamically synthesizes an institutional-grade 4-paragraph story.
    """
    cache_key = url or title
    if cache_key in _STORY_CACHE:
        return _STORY_CACHE[cache_key]

    paras: List[str] = []

    # 1. Attempt live web scraping if URL is valid HTTP/HTTPS
    if url and (url.startswith('http://') or url.startswith('https://')):
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9'
            }
            resp = requests.get(url, headers=headers, timeout=3.0)
            if resp.status_code == 200 and 'text/html' in resp.headers.get('Content-Type', ''):
                soup = BeautifulSoup(resp.text, 'html.parser')
                container = soup.select_one('.content_wrapper, .arti-flow, article, .story_body, .story-details, .article-content, #content, .story-body')
                raw_paras = container.find_all('p') if container else soup.find_all('p')
                
                bad_keywords = [
                    'also read', 'click here', 'download the app', 'follow us', 'telegram', 
                    'whatsapp', 'disclaimer', 'advertisement', 'copyright', 'unlisted shares', 
                    'subscribe', 'newsletter', 'privacy policy', 'terms of use', 'all rights reserved',
                    'sign in', 'log in', 'sponsored content'
                ]
                
                for p in raw_paras:
                    txt = ' '.join(p.get_text().split())
                    low = txt.lower()
                    if len(txt) < 55 or len(txt) > 800:
                        continue
                    if any(bad in low for bad in bad_keywords):
                        continue
                    paras.append(txt)
                    if len(paras) >= 5:
                        break
        except Exception:
            pass

    # 2. Fallback / Synthesis if fewer than 3 paragraphs found
    if len(paras) < 3:
        clean_desc = (desc or '').strip()
        clean_title = (title or '').strip()
        sent_upper = (sentiment or 'NEUTRAL').upper()
        ticker_str = ", ".join(tickers) if tickers else "relevant market segments"
        
        # Paragraph 1: Headline narrative & initial announcement
        p1 = clean_desc if clean_desc else f"In a major development reported by {source}, market participants are closely assessing recent announcements surrounding {clean_title}."
        if len(p1) < 90:
            p1 += f" The announcement from {source} highlights rapid institutional movements and shifts in domestic investor positioning."

        # Paragraph 2: Corporate / Regulatory / Disclosure context
        p2 = (
            f"According to primary filings and dispatches highlighted by {source}, the latest move impacts key counters including {ticker_str}. "
            f"Market analysts note that volume activity and corporate disclosures indicate significant retail and domestic institutional engagement with the development."
        )

        # Paragraph 3: Market Sentiment & Technical perspective
        if sent_upper == 'BULLISH':
            p3 = (
                f"Trading sentiment across desk terminals remains firmly constructive, with price action and derivatives indicators reflecting strong dip-buying demand. "
                f"Market specialists point out that immediate support zones remain well-defended as upside momentum persists."
            )
        elif sent_upper == 'BEARISH':
            p3 = (
                f"Traders are proceeding with cautious positioning as downside risks and profit-booking pressures are closely monitored across market segments. "
                f"Risk management parameters suggest awaiting clear base-building signals before taking fresh directional exposure."
            )
        else:
            p3 = (
                f"Terminal indicators suggest a balanced risk-reward profile, with institutional participants waiting for confirmation from subsequent quarterly prints or macro cues. "
                f"Range-bound consolidation is expected in the near term as market participants digest the broader ramifications of the announcement."
            )

        # Paragraph 4: Outlook & Monitoring
        p4 = (
            f"Investors and intraday participants are advised to monitor official exchange disclosures on BSE and NSE, alongside subsequent management commentary. "
            f"ZeroLive will continue monitoring real-time order book developments, price action triggers, and regulatory updates as they unfold."
        )

        paras = [p1, p2, p3, p4]

    # Keep cache within bounds (up to 500 entries)
    if len(_STORY_CACHE) > 500:
        _STORY_CACHE.clear()
    _STORY_CACHE[cache_key] = paras
    return paras

_ARTICLE_TRANSLATION_CACHE: Dict[str, Dict[str, Any]] = {}

def translate_single_text(text: str, target_lang: str = 'pa') -> str:
    """Translates a single string into the target language using Google Translate API."""
    if not text or not text.strip():
        return text
    try:
        url = 'https://clients5.google.com/translate_a/t?client=dict-chrome-ex&sl=en&tl=' + target_lang + '&q=' + urllib.parse.quote(text)
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            if isinstance(data, list) and len(data) > 0:
                return data[0] if isinstance(data[0], str) else text
            elif isinstance(data, str):
                return data
            return text
    except Exception:
        return text

PUNGLISH_COMMON_REPLACEMENTS = [
    # Entities, Acronyms & Countries
    (r'ਜ਼ੀਰੋਲਾਈਵ|ਜ਼ੀਰੋ ਲਾਈਵ', 'ZeroLive'),
    (r'ਯੂਕੇ|ਯੂ\.ਕੇ\.', 'UK'),
    (r'ਯੂਐਸਏ|ਯੂਐਸ|ਯੂ\.ਐੱਸ\.', 'US'),
    (r'ਆਈਪੀਓ|ਆਈ\.ਪੀ\.ਓ\.', 'IPO'),
    (r'ਬੀਐਸਈ|ਬੀ\.ਐਸ\.ਈ\.', 'BSE'),
    (r'ਐਨਐਸਈ|ਐਨ\.ਐਸ\.ਈ\.', 'NSE'),
    (r'ਸੈਂਸੈਕਸ', 'Sensex'),
    (r'ਨਿਫਟੀ', 'Nifty'),
    (r'ਜੀਡੀਪੀ', 'GDP'),
    (r'ਈਵੀ', 'EV'),
    (r'ਆਰਬੀਆਈ', 'RBI'),
    (r'ਸੇਬੀ', 'SEBI'),

    # Market Participants (Plurals first!)
    (r'ਵਿਦੇਸ਼ੀ ਸੰਸਥਾਗਤ ਨਿਵੇਸ਼ਕਾਂ', 'Foreign Institutional Investors (FIIs)'),
    (r'ਵਿਦੇਸ਼ੀ ਨਿਵੇਸ਼ਕਾਂ', 'Foreign Investors'),
    (r'ਸੰਸਥਾਗਤ ਨਿਵੇਸ਼ਕਾਂ', 'Institutional Investors'),
    (r'ਨਿਵੇਸ਼ਕਾਂ', 'Investors'),
    (r'ਨਿਵੇਸ਼ਕ', 'Investor'),
    (r'ਵਪਾਰੀਆਂ|ਟ੍ਰੇਡਰਾਂ', 'Traders'),
    (r'ਵਪਾਰੀ|ਟ੍ਰੇਡਰ', 'Trader'),
    (r'ਵਿਸ਼ਲੇਸ਼ਕਾਂ', 'Analysts'),
    (r'ਵਿਸ਼ਲੇਸ਼ਕ', 'Analyst'),
    (r'ਦਲਾਲਾਂ|ਦਲਾਲ', 'Brokers'),
    (r'ਪ੍ਰਬੰਧਨ', 'Management'),

    # Financial & Market Terms (Plurals first!)
    (r'ਬਜ਼ਾਰਾਂ|ਮਾਰਕੀਟਾਂ', 'Markets'),
    (r'ਬਜ਼ਾਰ|ਮਾਰਕੀਟ', 'Market'),
    (r'ਸ਼ੇਅਰਾਂ|ਸ਼ੇਅਰ', 'Shares'),
    (r'ਸਟਾਕਾਂ|ਸਟਾਕ', 'Stocks'),
    (r'ਕੰਪਨੀਆਂ', 'Companies'),
    (r'ਕੰਪਨੀ', 'Company'),
    (r'ਬੈਂਕਾਂ|ਬੈਂਕ', 'Banks'),
    (r'ਮੁਨਾਫੇ|ਮੁਨਾਫਾ', 'Profit'),
    (r'ਨੁਕਸਾਨ', 'Loss'),
    (r'ਵਪਾਰਕ|ਵਪਾਰ', 'Trading'),
    (r'ਤਿਮਾਹੀਆਂ|ਤਿਮਾਹੀ', 'Quarter'),
    (r'ਵਾਲੀਅਮ', 'Volume'),
    (r'ਪਲੇਟਫਾਰਮ', 'Platform'),
    (r'ਸੂਚੀਕਰਨ|ਸੂਚੀ', 'Listing'),
    (r'ਪ੍ਰੀਮੀਅਮ', 'Premium'),
    (r'ਡਿਸਕਾਊਂਟ', 'Discount'),
    (r'ਰਿਪੋਰਟਾਂ|ਰਿਪੋਰਟ', 'Report'),
    (r'ਫਾਈਲਿੰਗਾਂ|ਫਾਈਲਿੰਗ', 'Filings'),
    (r'ਖੁਲਾਸੇ|ਖੁਲਾਸਾ', 'Disclosures'),
    (r'ਟਰਮੀਨਲਾਂ|ਟਰਮੀਨਲ', 'Terminals'),
    (r'ਡੈਸਕਾਂ|ਡੈਸਕ', 'Desk'),
    (r'ਅੰਕਾਂ|ਅੰਕ', 'points'),
    (r'ਸਹਾਇਤਾ ਪੱਧਰਾਂ|ਸਹਾਇਤਾ ਪੱਧਰ', 'Support levels'),
    (r'ਵਿਰੋਧ ਪੱਧਰਾਂ|ਵਿਰੋਧ ਪੱਧਰ', 'Resistance levels'),
    (r'ਖਰੀਦਦਾਰੀ', 'Buying'),
    (r'ਵਿਕਰੀ', 'Selling'),
    (r'ਰੈਲੀ', 'Rally'),
    (r'ਗਤੀਸ਼ੀਲਤਾ|ਗਤੀ', 'Momentum'),
    (r'ਡੈਰੀਵੇਟਿਵਜ਼|ਡੈਰੀਵੇਟਿਵ', 'Derivatives'),
    (r'ਬੋਨਸ', 'Bonus'),
    (r'ਲਾਭਅੰਸ਼', 'Dividend')
]

def to_conversational_punglish(text: str) -> str:
    """Converts formal Gurmukhi into natural Conversational Punjabi + English."""
    if not text:
        return text
    for pat, repl in PUNGLISH_COMMON_REPLACEMENTS:
        text = re.sub(pat, repl, text, flags=re.IGNORECASE)
    return text

def get_article_translation_payload(article: Dict[str, Any], lang: str = 'pa') -> Dict[str, Any]:
    """Translates article title, takeaways, and story paragraphs concurrently and caches the result."""
    art_id = article.get("id", 0)
    cache_key = f"{art_id}_{lang}"
    if cache_key in _ARTICLE_TRANSLATION_CACHE:
        return _ARTICLE_TRANSLATION_CACHE[cache_key]

    title = article.get("title", "").strip()
    desc = (article.get("description") or "").strip()
    source = article.get("source", "Market Wire").strip()
    sentiment = article.get("sentiment", "NEUTRAL").upper()
    link = article.get("link", "").strip()
    tickers = extract_tickers(title, desc)

    paras = get_story_paragraphs(link, title, desc, source, sentiment, tickers)

    event_bullet = title
    impact_bullet = desc if len(desc) > 25 else f"Direct corporate announcement and filing via {source}. Expected to influence stock sentiment."
    action_bullet = "Monitor price volume action at market open; check key technical support/resistance levels."
    if sentiment == "BULLISH":
        action_bullet = "🟢 Bullish Trigger: Positive business expansion or earnings beat may attract institutional and retail buying."
    elif sentiment == "BEARISH":
        action_bullet = "🔴 Bearish Risk: Regulatory scrutiny, profit decline, or sell-off risk may create near-term volatility."
    elif sentiment == "EARNINGS":
        action_bullet = "📊 Earnings Focus: Assess quarterly EBITDA margins, year-over-year revenue, and management guidance."
    elif sentiment == "POLICY":
        action_bullet = "🏛️ Policy & Macro: Interest rate, inflation, or regulatory changes affecting broad market valuations."

    to_translate = [title, event_bullet, impact_bullet, action_bullet] + paras

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        translated = list(executor.map(lambda t: translate_single_text(t, lang), to_translate))

    if lang == 'pa':
        title_tr = to_conversational_punglish(translated[0])
        event_tr = to_conversational_punglish(translated[1])
        impact_tr = to_conversational_punglish(translated[2])
        action_tr = to_conversational_punglish(translated[3])
        paras_tr = [to_conversational_punglish(p) for p in translated[4:]]
    else:
        title_tr = translated[0]
        event_tr = translated[1]
        impact_tr = translated[2]
        action_tr = translated[3]
        paras_tr = translated[4:]

    labels = {
        "tldr_header": "⚡ Key Takeaways (ਮੁੱਖ ਨੁਕਤੇ)" if lang == 'pa' else "⚡ Instant Key Takeaways (TL;DR)",
        "core_label": "Main Update (ਮੁੱਖ ਅਪਡੇਟ):" if lang == 'pa' else "Core Development:",
        "impact_label": "Market Impact (ਵਿੱਤੀ ਪ੍ਰਭਾਵ):" if lang == 'pa' else "Market & Financial Impact:",
        "action_label": "Actionable Insight (ਸੂਝ):" if lang == 'pa' else "Actionable Insight:",
        "read_original": f"Read Full Coverage on {source} ↗" if lang == 'pa' else f"Read Original Full Coverage on {source} ↗",
        "lang_toggle_text": "English (ਅੰਗਰੇਜ਼ੀ)" if lang == 'pa' else "ਪੰਜਾਬੀ + Eng"
    }

    result = {
        "status": "success",
        "lang": lang,
        "title": title_tr,
        "labels": labels,
        "bullets": {
            "core": event_tr,
            "impact": impact_tr,
            "action": action_tr
        },
        "paragraphs": paras_tr,
        "speech_text": f"{title_tr}. " + " ".join(paras_tr[:3])
    }

    if len(_ARTICLE_TRANSLATION_CACHE) > 500:
        _ARTICLE_TRANSLATION_CACHE.clear()
    _ARTICLE_TRANSLATION_CACHE[cache_key] = result
    return result

def render_article_html(article: Dict[str, Any], related: List[Dict[str, Any]], base_url: str) -> str:
    """Renders the complete dedicated story page with full SEO and WhatsApp Open Graph tags."""
    title = article.get("title", "Market Update").strip()
    source = article.get("source", "Market Wire").strip()
    feed_name = article.get("feed_name", source).strip()
    desc = (article.get("description") or "Live financial intelligence and market filing report on ZeroLive.").strip()
    link = article.get("link", "").strip()
    sentiment = article.get("sentiment", "NEUTRAL").upper()
    category = article.get("category", "GENERAL").upper()
    published_str = article.get("published_str") or article.get("published_at", "")
    art_id = article.get("id", 0)

    slug = slugify_title(title)
    canonical_url = f"{base_url}/news/{art_id}/{slug}"
    preview_img = f"{base_url}/preview.png"
    tickers = extract_tickers(title, desc)
    source_color = get_source_color(source)

    # Fetch rich multi-paragraph story (5-9 lines)
    story_paras = get_story_paragraphs(link, title, desc, source, sentiment, tickers)
    story_paragraphs_html = "\n        ".join([f'<p class="story-p">{html.escape(p)}</p>' for p in story_paras])
    story_speech_text = re.sub(r'[\r\n\t]+', ' ', f"{title}. " + " ".join(story_paras[:3]))

    sent_class = "NEUTRAL"
    sent_label = "NEUTRAL"
    sent_icon = "⚪"
    if sentiment == "BULLISH":
        sent_class = "BULLISH"
        sent_label = "BULLISH"
        sent_icon = "🟢"
    elif sentiment == "BEARISH":
        sent_class = "BEARISH"
        sent_label = "BEARISH"
        sent_icon = "🔴"
    elif sentiment == "EARNINGS":
        sent_class = "EARNINGS"
        sent_label = "EARNINGS"
        sent_icon = "📊"
    elif sentiment == "POLICY":
        sent_class = "POLICY"
        sent_label = "RBI/POLICY"
        sent_icon = "🏛️"

    share_text = f"⚡ [{sent_label}] {title}\n\n📰 Source: {source}\n📊 Full Story: {canonical_url}\n\nZeroLive – Live Market News, Every Minute"
    whatsapp_share_url = f"https://api.whatsapp.com/send?text={quote(share_text)}"
    telegram_share_url = f"https://t.me/share/url?url={quote(canonical_url)}&text={quote(f'⚡ [{sent_label}] {title} | Source: {source}')}"

    event_bullet = title
    impact_bullet = desc if len(desc) > 25 else f"Direct corporate announcement and filing via {source}. Expected to influence stock sentiment."
    action_bullet = "Monitor price volume action at market open; check key technical support/resistance levels."
    if sentiment == "BULLISH":
        action_bullet = "🟢 Bullish Trigger: Positive business expansion or earnings beat may attract institutional and retail buying."
    elif sentiment == "BEARISH":
        action_bullet = "🔴 Bearish Risk: Regulatory scrutiny, profit decline, or sell-off risk may create near-term volatility."
    elif sentiment == "EARNINGS":
        action_bullet = "📊 Earnings Focus: Assess quarterly EBITDA margins, year-over-year revenue, and management guidance."
    elif sentiment == "POLICY":
        action_bullet = "🏛️ Policy & Macro: Interest rate, inflation, or regulatory changes affecting broad market valuations."

    json_ld = {
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": title,
        "image": [preview_img],
        "datePublished": str(article.get("published_at", "")),
        "dateModified": str(article.get("published_at", "")),
        "description": desc[:250],
        "author": [{
            "@type": "Organization",
            "name": source,
            "url": link or canonical_url
        }],
        "publisher": {
            "@type": "Organization",
            "name": "ZeroLive",
            "logo": {
                "@type": "ImageObject",
                "url": f"{base_url}/icons/icon-512.png"
            }
        },
        "mainEntityOfPage": {
            "@type": "WebPage",
            "@id": canonical_url
        }
    }

    related_html_parts = []
    for r in related:
        r_slug = slugify_title(r.get("title", ""))
        r_url = f"/news/{r['id']}/{r_slug}"
        r_sent = r.get("sentiment", "NEUTRAL")
        r_sent_icon = "🟢" if r_sent == "BULLISH" else "🔴" if r_sent == "BEARISH" else "⚪"
        related_html_parts.append(f"""
            <a href="{r_url}" class="related-story-card">
                <div class="related-story-meta">
                    <span class="related-source">{html.escape(r.get('source', 'News'))}</span>
                    <span class="related-time">{html.escape(r.get('published_str', 'Recently'))}</span>
                </div>
                <h4 class="related-title">{html.escape(r.get('title', ''))}</h4>
                <div class="related-sentiment">{r_sent_icon} {r_sent}</div>
            </a>
        """)
    related_html = "".join(related_html_parts)

    ticker_badges = "".join([f'<a href="/?search={t.replace("#", "")}" class="article-ticker-tag">{t}</a>' for t in tickers])

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>{html.escape(title)} | ZeroLive – Source: {html.escape(source)}</title>
  <meta name="description" content="{html.escape(desc[:160])}">
  <link rel="canonical" href="{canonical_url}">

  <!-- Open Graph / WhatsApp / Social Sharing -->
  <meta property="og:site_name" content="ZeroLive – Live Market News">
  <meta property="og:title" content="⚡ {html.escape(title)} | ZeroLive (Source: {html.escape(source)})">
  <meta property="og:description" content="{html.escape(desc[:200])}">
  <meta property="og:image" content="{preview_img}">
  <meta property="og:image:secure_url" content="{preview_img}">
  <meta property="og:image:type" content="image/png">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:url" content="{canonical_url}">
  <meta property="og:type" content="article">
  <meta property="article:published_time" content="{article.get('published_at', '')}">
  <meta property="article:author" content="{html.escape(source)}">
  <meta property="article:section" content="Finance">

  <!-- Twitter Card -->
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:site" content="@ZeroLiveNews">
  <meta name="twitter:title" content="⚡ {html.escape(title)} | ZeroLive">
  <meta name="twitter:description" content="{html.escape(desc[:200])}">
  <meta name="twitter:image" content="{preview_img}">

  <!-- PWA & Theme -->
  <link rel="manifest" href="/manifest.json">
  <meta name="theme-color" content="#0a0a0c">
  <link rel="apple-touch-icon" href="/icons/icon-192.png">
  <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>⚡</text></svg>">

  <!-- Fonts & Core Styles -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;600;700&family=Syne:wght@700;800&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="/static/style.css?v=4.7">

  <script>
    (function() {{
      try {{
        if (localStorage.getItem('dalal_theme') === 'light') {{
          document.documentElement.setAttribute('data-theme', 'light');
        }}
      }} catch(e) {{}}
    }})();
  </script>

  <!-- Google News Structured Data -->
  <script type="application/ld+json">
  {json.dumps(json_ld, indent=2)}
  </script>

  <style>
    body {{
      background: var(--bg-core);
      color: var(--text-primary);
      font-family: var(--font-body);
      margin: 0;
      padding: 0;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }}
    .article-nav {{
      position: sticky;
      top: 0;
      z-index: 100;
      background: var(--bg-glass);
      backdrop-filter: blur(14px);
      -webkit-backdrop-filter: blur(14px);
      border-bottom: 1px solid var(--border-subtle);
      padding: 0.75rem 1.25rem;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }}
    .article-nav-left {{
      display: flex;
      align-items: center;
      gap: 1.25rem;
    }}
    .btn-nav-back {{
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      color: var(--text-secondary);
      text-decoration: none;
      font-size: 0.88rem;
      font-weight: 600;
      padding: 0.45rem 0.85rem;
      border-radius: 8px;
      background: var(--bg-surface-1);
      border: 1px solid var(--border-subtle);
      transition: all 0.2s ease;
    }}
    .btn-nav-back:hover {{
      background: var(--bg-surface-hover);
      color: var(--gain-color);
      border-color: var(--border-active);
    }}
    .article-main-wrapper {{
      max-width: 860px;
      width: 100%;
      margin: 2rem auto;
      padding: 0 1.25rem 4rem;
      box-sizing: border-box;
      flex: 1;
    }}
    .article-card-full {{
      background: var(--bg-surface-1);
      border: 1px solid var(--border-subtle);
      border-radius: 16px;
      padding: 2.25rem;
      box-shadow: var(--shadow-card);
      position: relative;
      overflow: hidden;
    }}
    .article-meta-row {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 0.75rem;
      margin-bottom: 1.25rem;
    }}
    .badge-source-lg {{
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      padding: 0.35rem 0.85rem;
      border-radius: 6px;
      font-family: var(--font-mono);
      font-size: 0.78rem;
      font-weight: 700;
      background: rgba(56, 189, 248, 0.14);
      color: {source_color};
      border: 1px solid {source_color}44;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }}
    .article-time {{
      color: var(--text-dim);
      font-size: 0.82rem;
      font-family: var(--font-mono);
    }}
    .article-tickers-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
      margin-bottom: 1rem;
    }}
    .article-ticker-tag {{
      display: inline-block;
      padding: 0.25rem 0.6rem;
      background: var(--bg-surface-2);
      border: 1px solid var(--border-subtle);
      border-radius: 4px;
      color: var(--gain-color);
      font-family: var(--font-mono);
      font-size: 0.8rem;
      font-weight: 700;
      text-decoration: none;
      transition: all 0.15s;
    }}
    .article-ticker-tag:hover {{
      border-color: var(--gain-color);
      background: var(--gain-bg);
    }}
    .article-title-h1 {{
      font-family: var(--font-display);
      font-size: 1.85rem;
      line-height: 1.35;
      margin: 0 0 1.5rem 0;
      color: var(--text-primary);
      letter-spacing: -0.02em;
    }}
    .article-action-bar {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 0.65rem;
      padding: 1rem 0;
      margin-bottom: 1.75rem;
      border-top: 1px solid var(--border-subtle);
      border-bottom: 1px solid var(--border-subtle);
    }}
    .btn-action-pill {{
      display: inline-flex;
      align-items: center;
      gap: 0.45rem;
      padding: 0.55rem 1rem;
      border-radius: 8px;
      font-size: 0.84rem;
      font-weight: 600;
      cursor: pointer;
      text-decoration: none;
      border: 1px solid var(--border-subtle);
      background: var(--bg-surface-2);
      color: var(--text-secondary);
      transition: all 0.2s ease;
    }}
    .btn-action-pill:hover {{
      background: var(--bg-surface-hover);
      color: var(--text-primary);
      border-color: var(--border-active);
    }}
    .btn-action-pill.btn-whatsapp {{
      background: rgba(37, 211, 102, 0.12);
      border-color: rgba(37, 211, 102, 0.35);
      color: #25d366;
    }}
    .btn-action-pill.btn-whatsapp:hover {{
      background: rgba(37, 211, 102, 0.22);
      color: #ffffff;
    }}
    .btn-action-pill.btn-audio.playing {{
      background: var(--gain-bg);
      border-color: var(--gain-color);
      color: var(--gain-color);
    }}
    .btn-action-pill.btn-translate {{
      background: rgba(14, 165, 233, 0.12);
      border-color: rgba(14, 165, 233, 0.35);
      color: #38bdf8;
    }}
    .btn-action-pill.btn-translate:hover {{
      background: rgba(14, 165, 233, 0.25);
      color: #ffffff;
      border-color: #38bdf8;
    }}
    .btn-action-pill.btn-translate.active {{
      background: #0284c7;
      border-color: #38bdf8;
      color: #ffffff;
    }}
    .tldr-card-box {{
      background: rgba(16, 23, 38, 0.65);
      border: 1px solid rgba(56, 189, 248, 0.28);
      border-radius: 12px;
      padding: 1.35rem 1.5rem;
      margin-bottom: 2rem;
    }}
    .tldr-box-header {{
      display: flex;
      align-items: center;
      gap: 0.5rem;
      font-family: var(--font-mono);
      font-size: 0.85rem;
      font-weight: 800;
      color: #38bdf8;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      margin-bottom: 1rem;
    }}
    .tldr-item {{
      display: flex;
      align-items: flex-start;
      gap: 0.75rem;
      margin-bottom: 0.85rem;
      font-size: 0.94rem;
      line-height: 1.5;
    }}
    .tldr-item:last-child {{
      margin-bottom: 0;
    }}
    .tldr-icon {{
      font-size: 1.1rem;
      line-height: 1.3;
    }}
    .article-body-text {{
      font-size: 1.08rem;
      line-height: 1.75;
      color: var(--text-secondary);
      margin-bottom: 2.5rem;
    }}
    .article-body-text p, .story-p {{
      margin-bottom: 1.25rem;
      line-height: 1.75;
    }}
    .source-credit-box {{
      background: rgba(24, 34, 54, 0.8);
      border: 1px solid var(--border-active);
      border-radius: 12px;
      padding: 1.5rem;
      display: flex;
      flex-direction: column;
      gap: 1rem;
      margin-bottom: 2.5rem;
    }}
    .source-credit-info {{
      display: flex;
      align-items: flex-start;
      gap: 0.85rem;
    }}
    .source-credit-text {{
      font-size: 0.9rem;
      line-height: 1.55;
      color: var(--text-muted);
    }}
    .source-credit-text strong {{
      color: var(--text-primary);
    }}
    .btn-read-original {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 0.6rem;
      background: var(--gain-color);
      color: #000000;
      font-weight: 700;
      font-size: 0.96rem;
      padding: 0.85rem 1.75rem;
      border-radius: 10px;
      text-decoration: none;
      transition: all 0.2s ease;
      box-shadow: 0 4px 14px rgba(0, 230, 118, 0.25);
    }}
    .btn-read-original:hover {{
      background: #00ff84;
      transform: translateY(-2px);
      box-shadow: 0 6px 20px rgba(0, 230, 118, 0.4);
    }}
    .related-section {{
      margin-top: 3rem;
      border-top: 1px solid var(--border-subtle);
      padding-top: 2rem;
    }}
    .related-heading {{
      font-family: var(--font-display);
      font-size: 1.35rem;
      margin-bottom: 1.25rem;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }}
    .related-stories-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
      gap: 1rem;
    }}
    .related-story-card {{
      background: var(--bg-surface-2);
      border: 1px solid var(--border-subtle);
      border-radius: 10px;
      padding: 1.15rem;
      text-decoration: none;
      color: var(--text-primary);
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      gap: 0.65rem;
      transition: all 0.2s;
    }}
    .related-story-card:hover {{
      border-color: var(--border-active);
      transform: translateY(-2px);
      background: var(--bg-surface-hover);
    }}
    .related-story-meta {{
      display: flex;
      justify-content: space-between;
      font-size: 0.72rem;
      color: var(--text-dim);
      font-family: var(--font-mono);
    }}
    .related-title {{
      font-size: 0.9rem;
      line-height: 1.4;
      margin: 0;
      font-weight: 600;
      color: var(--text-primary);
      display: -webkit-box;
      -webkit-line-clamp: 3;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }}
    .related-sentiment {{
      font-size: 0.74rem;
      font-family: var(--font-mono);
      font-weight: 700;
    }}
    .toast {{
      position: fixed;
      bottom: 2rem;
      right: 2rem;
      background: var(--bg-surface-1);
      color: var(--text-primary);
      border: 1px solid var(--border-active);
      padding: 0.75rem 1.25rem;
      border-radius: 10px;
      box-shadow: 0 10px 25px rgba(0,0,0,0.5);
      z-index: 1000;
      display: none;
      align-items: center;
      gap: 0.5rem;
      font-weight: 600;
      font-size: 0.88rem;
    }}
    @media (max-width: 768px) {{
      .article-card-full {{
        padding: 1.35rem;
        border-radius: 12px;
      }}
      .article-title-h1 {{
        font-size: 1.45rem;
      }}
      .article-action-bar {{
        gap: 0.5rem;
      }}
      .btn-action-pill {{
        padding: 0.45rem 0.75rem;
        font-size: 0.78rem;
      }}
      .btn-read-original {{
        width: 100%;
        box-sizing: border-box;
      }}
      .related-stories-grid {{
        grid-template-columns: 1fr;
      }}
    }}

    /* Titanium Pro Light Theme Overrides */
    [data-theme="light"] body {{
      background: #eef2f6 !important;
      color: #0f172a !important;
    }}
    [data-theme="light"] .article-nav {{
      background: rgba(255, 255, 255, 0.94) !important;
      border-bottom-color: #d3dce6 !important;
    }}
    [data-theme="light"] .btn-nav-back {{
      color: #334155 !important;
    }}
    [data-theme="light"] .btn-nav-back:hover {{
      color: #0f172a !important;
    }}
    [data-theme="light"] .btn-theme-toggle {{
      background: #f1f5f9 !important;
      border-color: #cbd5e1 !important;
      color: #334155 !important;
    }}
    [data-theme="light"] .article-card-full {{
      background: #ffffff !important;
      border-color: #d3dce6 !important;
      box-shadow: 0 4px 20px -2px rgba(0, 0, 0, 0.06) !important;
    }}
    [data-theme="light"] .article-title-h1 {{
      color: #0f172a !important;
    }}
    [data-theme="light"] .article-time {{
      color: #64748b !important;
    }}
    [data-theme="light"] .article-ticker-tag {{
      background: #ecfdf5 !important;
      border-color: #6ee7b7 !important;
      color: #059669 !important;
    }}
    [data-theme="light"] .btn-action-pill {{
      background: #f1f5f9 !important;
      color: #334155 !important;
      border-color: #cbd5e1 !important;
    }}
    [data-theme="light"] .btn-action-pill:hover {{
      background: #e2e8f0 !important;
      color: #0f172a !important;
    }}
    [data-theme="light"] .btn-action-pill.btn-whatsapp {{
      background: rgba(37, 211, 102, 0.12) !important;
      border-color: rgba(37, 211, 102, 0.4) !important;
      color: #15803d !important;
    }}
    [data-theme="light"] .btn-action-pill.btn-translate {{
      background: rgba(2, 132, 199, 0.08) !important;
      border-color: rgba(2, 132, 199, 0.3) !important;
      color: #0284c7 !important;
    }}
    [data-theme="light"] .btn-action-pill.btn-translate:hover {{
      background: #0284c7 !important;
      color: #ffffff !important;
    }}
    [data-theme="light"] .btn-action-pill.btn-translate.active {{
      background: #0284c7 !important;
      color: #ffffff !important;
    }}
    [data-theme="light"] .tldr-card-box {{
      background: #f0fdf4 !important;
      border: 1px solid #86efac !important;
      box-shadow: 0 4px 12px rgba(16, 185, 129, 0.08) !important;
    }}
    [data-theme="light"] .tldr-box-header {{
      color: #047857 !important;
      font-weight: 800 !important;
    }}
    [data-theme="light"] .tldr-item {{
      color: #0f172a !important;
      font-size: 0.95rem !important;
    }}
    [data-theme="light"] .tldr-item strong {{
      color: #064e3b !important;
      font-weight: 700 !important;
    }}
    [data-theme="light"] .article-body-text {{
      color: #1e293b !important;
    }}
    [data-theme="light"] .story-p {{
      color: #1e293b !important;
    }}
    [data-theme="light"] .source-credit-box {{
      background: #f8fafc !important;
      border-color: #cbd5e1 !important;
    }}
    [data-theme="light"] .source-credit-text {{
      color: #475569 !important;
    }}
    [data-theme="light"] .source-credit-text strong {{
      color: #0f172a !important;
    }}
    [data-theme="light"] .btn-read-original {{
      background: #f1f5f9 !important;
      border-color: #cbd5e1 !important;
      color: #2563eb !important;
    }}
    [data-theme="light"] .btn-read-original:hover {{
      background: #2563eb !important;
      color: #ffffff !important;
      border-color: #2563eb !important;
    }}
    [data-theme="light"] .related-heading {{
      color: #0f172a !important;
    }}
    [data-theme="light"] .related-story-card {{
      background: #ffffff !important;
      border-color: #e2e8f0 !important;
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04) !important;
    }}
    [data-theme="light"] .related-title {{
      color: #0f172a !important;
    }}
    [data-theme="light"] .related-source {{
      color: #64748b !important;
    }}
    [data-theme="light"] .related-time {{
      color: #94a3b8 !important;
    }}
    [data-theme="light"] .article-footer {{
      border-top-color: #e2e8f0 !important;
      color: #64748b !important;
    }}
    [data-theme="light"] .article-footer a {{
      color: #475569 !important;
    }}
  </style>
</head>
<body>

  <!-- Top Navigation Header -->
  <header class="article-nav">
    <div class="article-nav-left">
      <a href="/" class="brand-logo" title="Return to Live Terminal">
        <span class="pulse-dot"></span>
        Zero<span class="brand-accent">Live</span>
      </a>
      <a href="/" class="btn-nav-back">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <line x1="19" y1="12" x2="5" y2="12"></line>
          <polyline points="12 19 5 12 12 5"></polyline>
        </svg>
        Live Terminal
      </a>
    </div>

    <div style="display: flex; align-items: center; gap: 0.75rem;">
      <a href="https://t.me/Zerolive_news" target="_blank" rel="noopener noreferrer" class="btn-action-pill" style="color: #229ED9; border-color: rgba(34, 158, 217, 0.4); text-decoration: none;" title="Join ZeroLive Telegram Wire (@Zerolive_news)">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm4.64 6.8c-.15 1.58-.8 5.42-1.13 7.19-.14.75-.42 1-.68 1.03-.58.05-1.02-.38-1.58-.75-.88-.58-1.38-.94-2.23-1.5-.99-.65-.35-1.01.22-1.59.15-.15 2.71-2.48 2.76-2.69a.2.2 0 00-.05-.18c-.06-.05-.14-.03-.21-.02-.09.02-1.49.95-4.22 2.79-.4.27-.76.41-1.08.4-.36-.01-1.04-.2-1.55-.37-.63-.2-1.12-.31-1.08-.66.02-.18.27-.36.74-.55 2.92-1.27 4.86-2.11 5.83-2.51 2.78-1.16 3.35-1.36 3.73-1.36.08 0 .27.02.39.12.1.08.13.19.14.27-.01.06.01.24 0 .38z"/>
        </svg>
        Telegram
      </a>
      <button id="themeToggleBtn" class="btn-action-pill" style="padding: 0.4rem 0.7rem;" title="Toggle Light/Dark Theme">
        <span id="themeIcon">🌓</span>
      </button>
    </div>
  </header>

  <!-- Article View Container -->
  <main class="article-main-wrapper">
    <article class="article-card-full">
      
      <!-- Meta Badges -->
      <div class="article-meta-row">
        <span class="badge-source-lg">📰 {html.escape(feed_name)}</span>
        <span class="badge-sentiment {sent_class}">{sent_icon} {sent_label}</span>
        <span class="article-time">🕒 {html.escape(published_str)}</span>
      </div>

      <!-- Ticker Hashtags -->
      {f'<div class="article-tickers-row">{ticker_badges}</div>' if ticker_badges else ''}

      <!-- Headline -->
      <h1 id="articleTitleH1" class="article-title-h1">{html.escape(title)}</h1>

      <!-- Action & Sharing Bar -->
      <div class="article-action-bar">
        <button id="listenAudioBtn" class="btn-action-pill btn-audio" title="Listen to story aloud">
          <span id="audioIcon">🔊</span>
          <span id="audioText">Listen to Story</span>
        </button>

        <button id="translateLangBtn" class="btn-action-pill btn-translate" title="Read in Conversational Punjabi + English / ਪੰਜਾਬੀ + Eng ਵਿੱਚ ਪੜ੍ਹੋ">
          <span id="transIcon">🌐</span>
          <span id="transText">ਪੰਜਾਬੀ + Eng</span>
        </button>

        <a href="{whatsapp_share_url}" target="_blank" rel="noopener noreferrer" class="btn-action-pill btn-whatsapp" title="Share on WhatsApp">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor">
            <path d="M.057 24l1.687-6.163c-1.041-1.804-1.588-3.849-1.587-5.946.003-6.556 5.338-11.891 11.893-11.891 3.181.001 6.167 1.24 8.413 3.488 2.245 2.248 3.481 5.236 3.48 8.414-.003 6.557-5.338 11.892-11.893 11.892-1.99-.001-3.951-.5-5.688-1.448l-6.305 1.654zm6.597-3.807c1.676.995 3.276 1.591 5.392 1.592 5.448 0 9.886-4.434 9.889-9.885.002-5.462-4.415-9.89-9.881-9.892-5.452 0-9.887 4.434-9.889 9.884-.001 2.225.651 3.891 1.746 5.634l-.999 3.648 3.742-.981z"/>
          </svg>
          Share on WhatsApp
        </a>

        <a href="{telegram_share_url}" target="_blank" rel="noopener noreferrer" class="btn-action-pill" title="Share on Telegram">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 0C5.37 0 0 5.37 0 12s5.37 12 12 12 12-5.37 12-12S18.63 0 12 0zm5.56 8.16l-1.97 9.29c-.15.65-.53.81-1.08.51l-3-2.21-1.45 1.39c-.16.16-.3.3-.61.3l.22-3.05 5.56-5.02c.24-.22-.05-.34-.38-.13l-6.87 4.33-2.96-.92c-.64-.2-.66-.64.13-.95l11.58-4.46c.54-.2 1.01.12.81.92z"/>
          </svg>
          Telegram
        </a>

        <button id="copyLinkBtn" class="btn-action-pill" title="Copy link to clipboard">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
          </svg>
          <span id="copyText">Copy Link</span>
        </button>

        <button id="bookmarkBtn" class="btn-action-pill" title="Save to Bookmarks">
          <span id="starIcon">⭐</span>
          <span id="starText">Bookmark</span>
        </button>
      </div>

      <!-- TL;DR Key Takeaways -->
      <div class="tldr-card-box">
        <div id="tldrHeader" class="tldr-box-header">⚡ Instant Key Takeaways (TL;DR)</div>
        <div class="tldr-item">
          <span class="tldr-icon">🎯</span>
          <div id="tldrCoreText"><strong>Core Development:</strong> {html.escape(event_bullet)}</div>
        </div>
        <div class="tldr-item">
          <span class="tldr-icon">📊</span>
          <div id="tldrImpactText"><strong>Market & Financial Impact:</strong> {html.escape(impact_bullet)}</div>
        </div>
        <div class="tldr-item">
          <span class="tldr-icon">💡</span>
          <div id="tldrActionText"><strong>Actionable Insight:</strong> {html.escape(action_bullet)}</div>
        </div>
      </div>

      <!-- Story Narrative Body -->
      <div id="articleBodyText" class="article-body-text">
        {story_paragraphs_html}
      </div>

      <!-- Full Publisher Attribution Box with Direct Link -->
      <div class="source-credit-box">
        <div class="source-credit-info">
          <span style="font-size: 1.5rem;">📰</span>
          <div class="source-credit-text">
            <strong>Official Publisher Attribution:</strong> This report is aggregated from <strong>{html.escape(source)}</strong>. ZeroLive provides live aggregation, automated sentiment synthesis, and exchange disclosure monitoring for retail market participants.
          </div>
        </div>

        {f'<a href="{html.escape(link)}" target="_blank" rel="noopener noreferrer" class="btn-read-original">Read Original Full Coverage on {html.escape(source)} ↗</a>' if link else ''}
      </div>

      <!-- Telegram Channel Wire Callout Card -->
      <div style="margin-top: 1.5rem; padding: 1.15rem 1.4rem; background: linear-gradient(135deg, rgba(14, 34, 61, 0.6) 0%, rgba(10, 14, 23, 0.9) 100%); border: 1px solid rgba(56, 189, 248, 0.3); border-left: 4px solid #229ED9; border-radius: 12px; display: flex; align-items: center; justify-content: space-between; gap: 1rem; flex-wrap: wrap;">
        <div style="display: flex; align-items: center; gap: 0.85rem;">
          <span style="font-size: 1.5rem;">⚡</span>
          <div>
            <div style="font-weight: 700; color: #ffffff; font-size: 0.95rem;">Get Breaking Stock Alerts & Q-Results on Telegram</div>
            <div style="color: #94a3b8; font-size: 0.82rem;">Real-time 1200x675 image cards and financial filings delivered instantly.</div>
          </div>
        </div>
        <a href="https://t.me/Zerolive_news" target="_blank" rel="noopener noreferrer" style="display: inline-flex; align-items: center; gap: 0.45rem; padding: 0.55rem 1.15rem; background: #229ED9; color: #ffffff; border-radius: 8px; font-weight: 700; font-size: 0.84rem; text-decoration: none; box-shadow: 0 4px 14px rgba(34, 158, 217, 0.35);">
          Join @Zerolive_news ↗
        </a>
      </div>

    </article>

    <!-- More Market Stories Feed -->
    {f'''
    <section class="related-section">
      <h3 class="related-heading">🔥 More Live Market Stories</h3>
      <div class="related-stories-grid">
        {related_html}
      </div>
    </section>
    ''' if related else ''}

  </main>

  <footer class="article-footer" style="max-width: 860px; margin: 0 auto; padding: 2rem 1.25rem 3rem; border-top: 1px solid var(--border-subtle); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1rem; font-size: 0.85rem; color: var(--text-dim);">
    <div>
      <strong>ZEROLIVE</strong> — Live Indian Stock Market News Wire & Regulatory Terminal.
    </div>
    <div style="display: flex; align-items: center; gap: 1rem; flex-wrap: wrap;">
      <a href="/" style="color: var(--text-secondary); text-decoration: none; font-weight: 600;">⚡ Live Terminal</a>
      <a href="/about" style="color: var(--text-secondary); text-decoration: none; font-weight: 600;">ℹ️ About</a>
      <a href="https://t.me/Zerolive_news" target="_blank" rel="noopener noreferrer" style="color: #229ED9; text-decoration: none; font-weight: 700;">✈️ Telegram (@Zerolive_news)</a>
    </div>
  </footer>

  <div id="toast" class="toast">Link copied to clipboard! ✅</div>

  <script>
    (function() {{
      const savedTheme = localStorage.getItem('dalal_theme');
      if (savedTheme === 'light') {{
        document.documentElement.setAttribute('data-theme', 'light');
      }}
      const themeBtn = document.getElementById('themeToggleBtn');
      if (themeBtn) {{
        themeBtn.addEventListener('click', function() {{
          const isLight = document.documentElement.getAttribute('data-theme') === 'light';
          if (isLight) {{
            document.documentElement.removeAttribute('data-theme');
            localStorage.setItem('dalal_theme', 'dark');
          }} else {{
            document.documentElement.setAttribute('data-theme', 'light');
            localStorage.setItem('dalal_theme', 'light');
          }}
        }});
      }}
    }})();

    const copyBtn = document.getElementById('copyLinkBtn');
    const toast = document.getElementById('toast');
    if (copyBtn) {{
      copyBtn.addEventListener('click', function() {{
        navigator.clipboard.writeText(window.location.href).then(function() {{
          toast.style.display = 'flex';
          document.getElementById('copyText').textContent = 'Copied!';
          setTimeout(function() {{
            toast.style.display = 'none';
            document.getElementById('copyText').textContent = 'Copy Link';
          }}, 2500);
        }}).catch(function() {{
          prompt('Copy this link:', window.location.href);
        }});
      }});
    }}

    const listenBtn = document.getElementById('listenAudioBtn');
    const audioIcon = document.getElementById('audioIcon');
    const audioText = document.getElementById('audioText');
    let isPlaying = false;
    let currentSpeechText = {json.dumps(story_speech_text)};
    let currentSpeechLang = 'en-IN';

    function getBestVoiceForSpeech(langCode) {{
      if (!('speechSynthesis' in window)) return null;
      const voices = window.speechSynthesis.getVoices();
      if (!voices || voices.length === 0) return null;

      if (langCode === 'pa') {{
        // 1. Check for Punjabi voice
        let v = voices.find(function(item) {{
          return item.lang && (item.lang.startsWith('pa') || (item.name && item.name.toLowerCase().includes('punjabi')));
        }});
        if (v) return v;

        // 2. Check for Indian Hindi/English voice that speaks Punglish with natural cadence
        v = voices.find(function(item) {{
          return item.lang && (item.lang === 'hi-IN' || item.lang.startsWith('hi') || item.lang === 'en-IN');
        }});
        if (v) return v;
      }}
      return voices.find(function(item) {{ return item.lang && item.lang.startsWith('en'); }}) || voices[0];
    }}

    if (listenBtn && ('speechSynthesis' in window)) {{
      listenBtn.addEventListener('click', function() {{
        if (isPlaying) {{
          window.speechSynthesis.cancel();
          isPlaying = false;
          listenBtn.classList.remove('playing');
          audioIcon.textContent = '🔊';
          audioText.textContent = (currentLang === 'pa') ? 'ਸੁਣੋ (Listen)' : 'Listen to Story';
          return;
        }}

        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(currentSpeechText);
        utterance.rate = 0.94;
        utterance.pitch = 1.0;
        utterance.lang = currentSpeechLang;

        const bestVoice = getBestVoiceForSpeech(currentLang);
        if (bestVoice) {{
          utterance.voice = bestVoice;
        }}

        utterance.onstart = function() {{
          isPlaying = true;
          listenBtn.classList.add('playing');
          audioIcon.textContent = '⏹️';
          audioText.textContent = 'Stop Audio';
        }};

        utterance.onend = function() {{
          isPlaying = false;
          listenBtn.classList.remove('playing');
          audioIcon.textContent = '🔊';
          audioText.textContent = (currentLang === 'pa') ? 'ਸੁਣੋ (Listen)' : 'Listen to Story';
        }};

        utterance.onerror = function() {{
          isPlaying = false;
          listenBtn.classList.remove('playing');
          audioIcon.textContent = '🔊';
          audioText.textContent = (currentLang === 'pa') ? 'ਸੁਣੋ (Listen)' : 'Listen to Story';
        }};

        window.speechSynthesis.speak(utterance);
      }});
    }}

    // Punjabi / Bilingual Translation Logic
    const articleId = {json.dumps(art_id)};
    const transBtn = document.getElementById('translateLangBtn');
    const transIcon = document.getElementById('transIcon');
    const transText = document.getElementById('transText');
    let currentLang = 'en';
    let cachedTranslation = null;
    let isTranslating = false;

    const enData = {{
      title: {json.dumps(title)},
      tldrHeader: '⚡ Instant Key Takeaways (TL;DR)',
      coreHtml: '<strong>Core Development:</strong> ' + {json.dumps(html.escape(event_bullet))},
      impactHtml: '<strong>Market & Financial Impact:</strong> ' + {json.dumps(html.escape(impact_bullet))},
      actionHtml: '<strong>Actionable Insight:</strong> ' + {json.dumps(html.escape(action_bullet))},
      bodyHtml: {json.dumps(story_paragraphs_html)},
      speechText: {json.dumps(story_speech_text)}
    }};

    function escapeHtml(str) {{
      if (!str) return '';
      return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }}

    function applyTranslation(data) {{
      const titleEl = document.getElementById('articleTitleH1');
      const headerEl = document.getElementById('tldrHeader');
      const coreEl = document.getElementById('tldrCoreText');
      const impactEl = document.getElementById('tldrImpactText');
      const actionEl = document.getElementById('tldrActionText');
      const bodyEl = document.getElementById('articleBodyText');

      if (titleEl) titleEl.textContent = data.title;
      if (headerEl) headerEl.textContent = data.labels.tldr_header;
      if (coreEl) coreEl.innerHTML = '<strong>' + data.labels.core_label + '</strong> ' + escapeHtml(data.bullets.core);
      if (impactEl) impactEl.innerHTML = '<strong>' + data.labels.impact_label + '</strong> ' + escapeHtml(data.bullets.impact);
      if (actionEl) actionEl.innerHTML = '<strong>' + data.labels.action_label + '</strong> ' + escapeHtml(data.bullets.action);

      if (bodyEl && data.paragraphs) {{
        bodyEl.innerHTML = data.paragraphs.map(function(p) {{
          return '<p class="story-p">' + escapeHtml(p) + '</p>';
        }}).join('\\n');
      }}

      if (data.speech_text) {{
        currentSpeechText = data.speech_text;
        currentSpeechLang = 'pa-IN';
      }}

      currentLang = 'pa';
      if (transBtn) {{
        transBtn.classList.add('active');
        transIcon.textContent = '🇬🇧';
        transText.textContent = 'English (ਅੰਗਰੇਜ਼ੀ)';
        transBtn.title = 'ਅੰਗਰੇਜ਼ੀ ਵਿੱਚ ਪੜ੍ਹੋ / Switch to English';
      }}
      if (!isPlaying) {{
        audioText.textContent = 'ਸੁਣੋ (Listen)';
      }}
    }}

    if (transBtn) {{
      transBtn.addEventListener('click', async function() {{
        if (isTranslating) return;

        if (currentLang === 'pa') {{
          // Switch back to English
          const titleEl = document.getElementById('articleTitleH1');
          const headerEl = document.getElementById('tldrHeader');
          const coreEl = document.getElementById('tldrCoreText');
          const impactEl = document.getElementById('tldrImpactText');
          const actionEl = document.getElementById('tldrActionText');
          const bodyEl = document.getElementById('articleBodyText');

          if (titleEl) titleEl.textContent = enData.title;
          if (headerEl) headerEl.textContent = enData.tldrHeader;
          if (coreEl) coreEl.innerHTML = enData.coreHtml;
          if (impactEl) impactEl.innerHTML = enData.impactHtml;
          if (actionEl) actionEl.innerHTML = enData.actionHtml;
          if (bodyEl) bodyEl.innerHTML = enData.bodyHtml;

          currentSpeechText = enData.speechText;
          currentSpeechLang = 'en-IN';
          currentLang = 'en';

          transBtn.classList.remove('active');
          transIcon.textContent = '🌐';
          transText.textContent = 'ਪੰਜਾਬੀ + Eng';
          transBtn.title = 'Read in Conversational Punjabi + English / ਪੰਜਾਬੀ + Eng ਵਿੱਚ ਪੜ੍ਹੋ';
          if (!isPlaying) {{
            audioText.textContent = 'Listen to Story';
          }}
          return;
        }}

        // Switch to Punjabi
        if (cachedTranslation) {{
          applyTranslation(cachedTranslation);
          return;
        }}

        isTranslating = true;
        transBtn.disabled = true;
        transIcon.textContent = '⏳';
        transText.textContent = 'ਅਨੁਵਾਦ ਹੋ ਰਿਹਾ ਹੈ...';

        try {{
          const res = await fetch('/api/article/' + articleId + '/translate?lang=pa');
          if (!res.ok) throw new Error('Translation failed');
          const data = await res.json();
          cachedTranslation = data;
          applyTranslation(data);
        }} catch(err) {{
          alert('ਅਨੁਵਾਦ ਲੋਡ ਕਰਨ ਵਿੱਚ ਅਸਮਰੱਥ (Translation could not be loaded). Please try again.');
          transIcon.textContent = '🌐';
          transText.textContent = 'ਪੰਜਾਬੀ + Eng';
        }} finally {{
          isTranslating = false;
          transBtn.disabled = false;
        }}
      }});
    }}

    const bookmarkBtn = document.getElementById('bookmarkBtn');
    const starIcon = document.getElementById('starIcon');
    const starText = document.getElementById('starText');
    const currentLink = {json.dumps(link)};

    function checkBookmark() {{
      try {{
        const bookmarks = JSON.parse(localStorage.getItem('dalal_bookmarks') || '[]');
        const exists = bookmarks.some(b => b.link === currentLink);
        if (exists) {{
          starIcon.textContent = '★';
          starText.textContent = 'Saved';
          bookmarkBtn.style.color = '#f59e0b';
        }} else {{
          starIcon.textContent = '⭐';
          starText.textContent = 'Bookmark';
          bookmarkBtn.style.color = '';
        }}
      }} catch(e) {{}}
    }}
    checkBookmark();

    if (bookmarkBtn) {{
      bookmarkBtn.addEventListener('click', function() {{
        try {{
          let bookmarks = JSON.parse(localStorage.getItem('dalal_bookmarks') || '[]');
          const idx = bookmarks.findIndex(b => b.link === currentLink);
          if (idx >= 0) {{
            bookmarks.splice(idx, 1);
          }} else {{
            bookmarks.unshift({{
              title: {json.dumps(title)},
              link: currentLink,
              source: {json.dumps(source)},
              description: {json.dumps(desc)},
              published_at: {json.dumps(article.get('published_at', ''))},
              sentiment: {json.dumps(sentiment)}
            }});
          }}
          localStorage.setItem('dalal_bookmarks', JSON.stringify(bookmarks));
          checkBookmark();
        }} catch(e) {{}}
      }});
    }}
  </script>
</body>
</html>"""

def render_not_found_html(base_url: str) -> str:
    """Renders a friendly 404 page for missing or expired news articles."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Story Not Found | ZeroLive</title>
  <link rel="stylesheet" href="/static/style.css?v=4.7">
  <style>
    body {{
      background: #080c14;
      color: #ffffff;
      font-family: 'Inter', sans-serif;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      margin: 0;
      text-align: center;
      padding: 1.5rem;
    }}
    .box {{
      background: #101726;
      border: 1px solid #293750;
      border-radius: 16px;
      padding: 3rem 2rem;
      max-width: 500px;
      width: 100%;
    }}
    .icon {{ font-size: 3rem; margin-bottom: 1rem; }}
    h1 {{ font-family: 'Syne', sans-serif; font-size: 1.8rem; margin: 0 0 0.75rem; }}
    p {{ color: #94a3b8; line-height: 1.6; margin-bottom: 1.75rem; }}
    .btn {{
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      background: #00e676;
      color: #000000;
      font-weight: 700;
      padding: 0.75rem 1.5rem;
      border-radius: 8px;
      text-decoration: none;
    }}
  </style>
</head>
<body>
  <div class="box">
    <div class="icon">📡</div>
    <h1>Story Not Found or Archived</h1>
    <p>This market news item may have expired (older than 90 days) or the URL might be mistyped.</p>
    <a href="/" class="btn">← Return to Live Terminal</a>
  </div>
</body>
</html>"""

