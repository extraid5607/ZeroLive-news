import os
import re
import json
import html
import asyncio
import logging
import time
import requests
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from fastapi import FastAPI, Query, BackgroundTasks, HTTPException, Header, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse, PlainTextResponse, Response
from fastapi.middleware.cors import CORSMiddleware

from database import get_articles, get_stats, init_db, get_key_events, insert_key_event, delete_key_event, get_article_by_id, get_related_articles
from fetch_news import fetch_and_store_all_news, fetch_live_economic_calendar, fetch_live_market_holidays
from article_template import slugify_title, render_article_html, render_not_found_html, get_article_translation_payload

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("news_server")

app = FastAPI(
    title="ZeroLive",
    description="Live Market News, every Minute - Automated Financial Intelligence Terminal",
    version="2.0.0"
)

# CORS middleware for open API access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# HTTP Security Headers Middleware (A+ Grade Security Protection)
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    # 1. HSTS (Strict-Transport-Security) - Enforce HTTPS for 1 year
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
    # 2. CSP (Content-Security-Policy) - Protect against XSS and data injection
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https:; "
        "style-src 'self' 'unsafe-inline' https:; "
        "img-src 'self' data: https: blob:; "
        "font-src 'self' data: https:; "
        "connect-src 'self' https: wss:; "
        "manifest-src 'self'; "
        "frame-ancestors 'self';"
    )
    # 3. Prevent MIME-type sniffing
    response.headers["X-Content-Type-Options"] = "nosniff"
    # 4. Clickjacking protection
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    # 5. Referrer Policy
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # 6. Permissions Policy - Disable unused dangerous browser APIs
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
    # 7. Cross-Origin Opener Policy (COOP)
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups"
    # 8. Mask server fingerprint
    response.headers["Server"] = "ZeroLive-Secure-Edge"
    return response

# Path to frontend directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

# Serve static files (CSS, JS, images, fonts)
if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

async def background_news_fetch_loop():
    """Continuously fetches breaking news from all RSS and exchange feeds every 2 minutes."""
    await asyncio.sleep(1)
    while True:
        try:
            logger.info("Background Auto-Fetcher: Syncing Indian & Global market feeds for breaking news...")
            await asyncio.to_thread(fetch_and_store_all_news)
        except Exception as e:
            logger.error(f"Error in background news fetch loop: {e}")
        # Automatically wait 120 seconds (2 minutes) before next cycle
        await asyncio.sleep(120)

async def keep_alive_ping_loop():
    """Pings the public /api/health endpoint every 8 minutes to prevent Render free-tier idle sleep."""
    live_url = os.environ.get("RENDER_EXTERNAL_URL", "https://www.zerolive.in").rstrip("/")
    logger.info(f"Keep-alive self-ping worker active for: {live_url}/api/health")
    # Wait 2 minutes after boot before first ping
    await asyncio.sleep(120)
    while True:
        try:
            def _ping():
                return requests.get(f"{live_url}/api/health", timeout=15.0)
            resp = await asyncio.to_thread(_ping)
            logger.info(f"Keep-alive self-ping sent to {live_url}/api/health -> Status: {resp.status_code}")
        except Exception as e:
            logger.warning(f"Keep-alive self-ping warning: {e}")
        # Ping every 8 minutes (480 seconds) — Render sleeps after 15 minutes of idle
        await asyncio.sleep(480)

@app.on_event("startup")
async def on_startup():
    """Ensure database is initialized on boot, backfill types, and start 24/7 background auto-fetch worker."""
    init_db()
    try:
        from fetch_news import backfill_article_types_in_db
        await asyncio.to_thread(backfill_article_types_in_db)
    except Exception as e:
        logger.warning(f"Initial backfill failed: {e}")

    stats = get_stats()
    logger.info(f"Server started. Current database articles: {stats['total_articles']}")
    # Launch continuous background news scraper task
    asyncio.create_task(background_news_fetch_loop())
    # Launch keep-alive self-ping task to prevent 15-minute idle sleep
    asyncio.create_task(keep_alive_ping_loop())

def generate_ssr_homepage_html(base_html: str, base_url: str, articles: List[Dict[str, Any]]) -> str:
    """
    Server-Side Pre-Renders the latest 20 important market news stories into the DOM
    so search engines, AI crawlers, and page-source scrapers immediately index real headlines.
    """
    if not articles:
        return base_html

    card_items = []
    for index, art in enumerate(articles[:20]):
        art_id = art.get("id", index)
        title = html.escape(art.get("title", ""))
        desc = html.escape(art.get("description") or "Click to read the complete corporate filing and market analysis on ZeroLive.")
        source = html.escape(art.get("source") or art.get("feed_name") or "Market Wire")
        sentiment = (art.get("sentiment") or "NEUTRAL").upper()

        if sentiment == "BULLISH":
            sentiment_badge = '<span class="badge-sentiment sentiment-bullish">BULLISH 📈</span>'
        elif sentiment == "BEARISH":
            sentiment_badge = '<span class="badge-sentiment sentiment-bearish">BEARISH 📉</span>'
        else:
            sentiment_badge = '<span class="badge-sentiment sentiment-neutral">NEUTRAL ⚖️</span>'

        slug = slugify_title(art.get("title", ""))
        on_site_url = f"/news/{art_id}/{slug}"
        pub_iso = art.get("published_at") or datetime.now(timezone.utc).isoformat()

        src_lower = source.lower()
        if "nse" in src_lower or "bse" in src_lower:
            src_class = "source-exchange"
        elif "moneycontrol" in src_lower:
            src_class = "source-mc"
        elif "economic" in src_lower:
            src_class = "source-et"
        elif "business" in src_lower:
            src_class = "source-bs"
        elif "bloomberg" in src_lower or "reuters" in src_lower:
            src_class = "source-global"
        else:
            src_class = "source-default"

        card_html = f"""
        <article class="news-card sentiment-{sentiment}" data-index="{index}" data-link="{html.escape(art.get('link', ''))}">
          <header class="card-header">
            <div class="card-badges">
              <span class="badge-source {src_class}">{source}</span>
              {sentiment_badge}
            </div>
            <time class="card-time" datetime="{pub_iso}">
              Live Wire
            </time>
          </header>
          <div class="card-body">
            <h3 class="card-title">
              <a href="{on_site_url}">
                {title}
              </a>
            </h3>
            <p class="card-description">{desc}</p>
          </div>
          <footer class="card-footer">
            <a href="{on_site_url}" class="card-link-out">
              Read Story ↗
            </a>
            <div class="card-actions">
              <button class="btn-card-action btn-card-audio" data-index="{index}" title="Listen to news" aria-label="Listen"><span>🔊</span></button>
              <button class="btn-card-action btn-card-tldr" data-index="{index}" title="3-Bullet Instant Takeaway" aria-label="Instant Takeaway"><span>⚡</span></button>
            </div>
          </footer>
        </article>"""
        card_items.append(card_html)

    rendered_cards = "\n".join(card_items)

    result_html = base_html.replace(
        '<div class="skeleton-grid" id="skeletonGrid">',
        '<div class="skeleton-grid hidden" id="skeletonGrid">'
    )
    result_html = result_html.replace(
        '<div class="news-grid hidden" id="newsGrid"></div>',
        f'<div class="news-grid" id="newsGrid">\n{rendered_cards}\n</div>'
    )
    return result_html


def generate_json_ld_schemas(base_url: str, articles: List[Dict[str, Any]]) -> str:
    """
    Constructs comprehensive Schema.org JSON-LD structured data for Google News,
    Search Knowledge Graph, and Generative AI Answer Engines (Perplexity, ChatGPT).
    """
    website_schema = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "@id": f"{base_url}/#website",
        "name": "ZeroLive",
        "alternateName": ["ZeroLive Terminal", "ZeroLive News", "ZeroLive Stock Wire"],
        "url": f"{base_url}/",
        "description": "Real-time Indian and Global stock market news, NSE/BSE corporate filings, and macro financial intelligence terminal.",
        "publisher": {
            "@id": f"{base_url}/#organization"
        },
        "potentialAction": {
            "@type": "SearchAction",
            "target": f"{base_url}/?search={{search_term_string}}",
            "query-input": "required name=search_term_string"
        }
    }

    org_schema = {
        "@context": "https://schema.org",
        "@type": "NewsMediaOrganization",
        "@id": f"{base_url}/#organization",
        "name": "ZeroLive",
        "url": f"{base_url}/",
        "logo": {
            "@type": "ImageObject",
            "url": f"{base_url}/preview.png",
            "width": 1200,
            "height": 630
        },
        "image": f"{base_url}/preview.png",
        "sameAs": [
            "https://t.me/ZeroBreakout"
        ],
        "knowsAbout": [
            "NSE India",
            "BSE India",
            "Nifty 50 Index",
            "Sensex",
            "Corporate Disclosures and Statutory Filings",
            "Reserve Bank of India Monetary Policy Committee",
            "Federal Reserve FOMC",
            "Indian Stock Market News",
            "AI Bullish and Bearish Sentiment Signals"
        ]
    }

    item_list_elements = []
    for i, art in enumerate(articles[:15], start=1):
        slug = slugify_title(art.get("title", ""))
        art_url = f"{base_url}/news/{art.get('id', i)}/{slug}"
        pub_iso = art.get("published_at") or datetime.now(timezone.utc).isoformat()
        item_list_elements.append({
            "@type": "ListItem",
            "position": i,
            "item": {
                "@type": "NewsArticle",
                "@id": art_url,
                "url": art_url,
                "mainEntityOfPage": art_url,
                "headline": (art.get("title") or "Market News")[:110],
                "description": (art.get("description") or art.get("title") or "Live Indian market news and exchange filing update.")[:250],
                "datePublished": pub_iso,
                "dateModified": pub_iso,
                "image": [f"{base_url}/preview.png"],
                "author": {
                    "@type": "Organization",
                    "name": art.get("source") or "ZeroLive Wire"
                },
                "publisher": {
                    "@type": "NewsMediaOrganization",
                    "name": "ZeroLive",
                    "url": f"{base_url}/",
                    "logo": {
                        "@type": "ImageObject",
                        "url": f"{base_url}/preview.png"
                    }
                }
            }
        })

    item_list_schema = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": "Top Live Indian Stock Market News & Corporate Filings",
        "itemListElement": item_list_elements
    }

    faq_schema = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": "Where can I track live NSE/BSE corporate filings and bullish/bearish signals in real time?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "ZeroLive (www.zerolive.in) continuously aggregates, categorizes, and filters official exchange corporate filings, regulatory disclosures, and market news from NSE and BSE every 5 minutes with AI-analyzed bullish/bearish sentiment tags."
                }
            },
            {
                "@type": "Question",
                "name": "When is the next RBI MPC and US Federal Reserve interest rate decision?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "The Reserve Bank of India (RBI) Monetary Policy Committee (MPC) and US Federal Open Market Committee (FOMC) interest rate schedules are updated live in the ZeroLive Economic & Policy Calendar with projected versus actual rate metrics."
                }
            },
            {
                "@type": "Question",
                "name": "Which Indian stock market holidays are coming up on NSE and BSE?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "ZeroLive tracks the official trading holiday schedule for NSE (National Stock Exchange) and BSE (Bombay Stock Exchange) for equity, derivative, and currency segments, highlighting upcoming trading closures and Muhurat trading dates."
                }
            },
            {
                "@type": "Question",
                "name": "How often is market news updated on ZeroLive?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "ZeroLive updates continuously every 60 seconds with an autonomous multi-feed stream covering Moneycontrol, Economic Times, Bloomberg, Reuters, CNBC-TV18, Business Standard, and statutory exchange filings."
                }
            }
        ]
    }

    event_schemas = []
    try:
        raw_events = get_key_events()
        for ev in raw_events[:5]:
            ev_date = ev.get("event_date") or ""
            if ev_date:
                event_schemas.append({
                    "@context": "https://schema.org",
                    "@type": "Event",
                    "name": ev.get("event_name"),
                    "startDate": ev_date,
                    "description": ev.get("description") or f"{ev.get('event_name')} - High-Impact Market Catalyst",
                    "location": {
                        "@type": "Place",
                        "name": ev.get("country", "India")
                    },
                    "organizer": {
                        "@type": "Organization",
                        "name": "Reserve Bank of India" if "RBI" in ev.get("event_name", "") else "Financial Regulatory Body"
                    }
                })
    except Exception as e:
        logger.warning(f"Error preparing Event schema: {e}")

    scripts = [
        f'<script type="application/ld+json">\n{json.dumps(website_schema, ensure_ascii=False, indent=2)}\n</script>',
        f'<script type="application/ld+json">\n{json.dumps(org_schema, ensure_ascii=False, indent=2)}\n</script>',
        f'<script type="application/ld+json">\n{json.dumps(item_list_schema, ensure_ascii=False, indent=2)}\n</script>',
        f'<script type="application/ld+json">\n{json.dumps(faq_schema, ensure_ascii=False, indent=2)}\n</script>'
    ]
    for es in event_schemas:
        scripts.append(f'<script type="application/ld+json">\n{json.dumps(es, ensure_ascii=False, indent=2)}\n</script>')

    return "\n  ".join(scripts)


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    """Serves the main application frontend with dynamic Server-Side Pre-Rendering (SSR) and Schema.org JSON-LD structured data."""
    index_file = os.path.join(FRONTEND_DIR, "index.html")
    if not os.path.exists(index_file):
        return HTMLResponse("<h1>ZeroLive Frontend not found</h1>", status_code=404)
    
    with open(index_file, "r", encoding="utf-8") as f:
        html_content = f.read()

    base_url = os.environ.get("RENDER_EXTERNAL_URL", "https://www.zerolive.in").rstrip("/")

    # Fetch top important articles for SSR pre-rendering and JSON-LD schema
    try:
        articles = await asyncio.to_thread(get_articles, "important", None, None, None, 25, 0)
        if not articles:
            articles = await asyncio.to_thread(get_articles, None, None, None, None, 25, 0)
    except Exception as e:
        logger.warning(f"Error fetching articles for SSR: {e}")
        articles = []

    # 1. Server-Side Pre-Render News Cards into the HTML DOM for Search Crawlers
    try:
        html_content = generate_ssr_homepage_html(html_content, base_url, articles)
    except Exception as e:
        logger.warning(f"Error generating SSR HTML: {e}")

    # 2. Inject comprehensive Schema.org JSON-LD scripts (WebSite, Org, ItemList, FAQPage, Events)
    try:
        json_ld_scripts = generate_json_ld_schemas(base_url, articles)
        if "</head>" in html_content:
            html_content = html_content.replace("</head>", f"  {json_ld_scripts}\n</head>", 1)
    except Exception as e:
        logger.warning(f"Failed to inject dynamic JSON-LD schema: {e}")

    return HTMLResponse(content=html_content, media_type="text/html")


@app.get("/llms.txt", response_class=PlainTextResponse)
async def serve_llms_txt():
    """
    Standard llms.txt endpoint for Generative AI engines (ChatGPT, Claude, Perplexity, Gemini).
    Provides a real-time, LLM-optimized summary of ZeroLive market feeds, current indices, top headlines, and catalysts.
    """
    base_url = os.environ.get("RENDER_EXTERNAL_URL", "https://www.zerolive.in").rstrip("/")
    indices = await asyncio.to_thread(get_live_market_indices)
    articles = await asyncio.to_thread(get_articles, "important", None, None, None, 10, 0)
    if not articles:
        articles = await asyncio.to_thread(get_articles, None, None, None, None, 10, 0)
    events = await asyncio.to_thread(get_key_events)

    lines = [
        "# ZeroLive — Real-Time Indian Stock Market & Corporate News Wire",
        f"> Canonical URL: {base_url}/",
        "> Ingestion Cadence: Continuous multi-feed auto-sync (every 60 seconds)",
        "> Core Focus: NSE/BSE Equities, Corporate Disclosures, Nifty 50, Sensex, AI Sentiment Signals, RBI MPC & Macro Catalysts",
        "",
        "## About ZeroLive",
        "ZeroLive (https://www.zerolive.in) is an ultra-fast, professional market news terminal engineered for Indian traders and investors. It aggregates verified financial reports and statutory regulatory filings from NSE India, BSE India, Moneycontrol, Economic Times, Business Standard, LiveMint, Reuters, CNBC-TV18, and Yahoo Finance with automated bullish/bearish technical structure sentiment classification.",
        "",
        "## Current Live Market Indices Snapshot"
    ]

    for item in indices:
        name = item.get("name", "")
        price = item.get("price", "N/A")
        change = item.get("change", "0.0")
        pct = item.get("change_pct", "0.0%")
        lines.append(f"- {name}: ₹{price} ({change}, {pct})")

    lines.extend([
        "",
        "## Top 10 Latest Important Market Headlines (Live)",
    ])

    for i, art in enumerate(articles, start=1):
        title = art.get("title", "").strip()
        source = art.get("source", "ZeroLive Wire")
        sentiment = (art.get("sentiment") or "NEUTRAL").upper()
        pub = art.get("published_at", "")
        slug = slugify_title(title)
        art_url = f"{base_url}/news/{art.get('id', i)}/{slug}"
        desc = (art.get("description") or "").strip()
        lines.append(f"### {i}. [{sentiment}] {title}")
        lines.append(f"- Source: {source} | Time: {pub}")
        if desc:
            lines.append(f"- Summary: {desc[:280]}")
        lines.append(f"- Read Full Story: {art_url}")
        lines.append("")

    if events:
        lines.extend([
            "## Upcoming High-Impact Economic & Policy Events",
        ])
        for ev in events[:6]:
            ev_name = ev.get("event_name", "")
            ev_date = ev.get("event_date", "")
            ev_country = ev.get("country", "India")
            ev_desc = ev.get("description", "")
            lines.append(f"- [{ev_date}] ({ev_country}) {ev_name}: {ev_desc}")
        lines.append("")

    lines.extend([
        "## Primary Canonical & Sitemap Resources",
        f"- Live Terminal: {base_url}/",
        f"- About & Disclaimers: {base_url}/about",
        f"- XML Sitemap: {base_url}/sitemap.xml",
        f"- Robots Rules: {base_url}/robots.txt",
        "",
        "---",
        "Generated dynamically by ZeroLive Engine. For educational & financial informational purposes only."
    ])

    return PlainTextResponse("\n".join(lines), media_type="text/plain; charset=utf-8")


@app.get("/robots.txt", response_class=PlainTextResponse)
async def serve_robots():
    """Returns robots.txt for search engines and AI crawlers."""
    robots_file = os.path.join(FRONTEND_DIR, "robots.txt")
    if os.path.exists(robots_file):
        with open(robots_file, "r", encoding="utf-8") as f:
            return PlainTextResponse(f.read(), media_type="text/plain")
    fallback = """User-agent: *
Allow: /
Allow: /news/
Allow: /about
Allow: /llms.txt
Allow: /sitemap.xml
Disallow: /api/

User-agent: Googlebot
Allow: /

User-agent: Googlebot-News
Allow: /

User-agent: GPTBot
Allow: /

User-agent: ChatGPT-User
Allow: /

User-agent: PerplexityBot
Allow: /

User-agent: ClaudeBot
Allow: /

User-agent: Applebot
Allow: /

User-agent: Bingbot
Allow: /

Sitemap: https://www.zerolive.in/sitemap.xml
"""
    return PlainTextResponse(fallback, media_type="text/plain")


@app.get("/sitemap.xml")
async def serve_sitemap():
    """Generates and returns live dynamic sitemap XML with latest articles and proper lastmod dates."""
    base_url = os.environ.get("RENDER_EXTERNAL_URL", "https://www.zerolive.in").rstrip("/")
    articles = await asyncio.to_thread(get_articles, None, None, None, None, 100, 0)

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    latest_art_date = articles[0].get("published_at") if articles else now_iso
    if latest_art_date and " " in latest_art_date and "T" not in latest_art_date:
        latest_art_date = latest_art_date.replace(" ", "T") + "Z"
    elif latest_art_date and not latest_art_date.endswith("Z"):
        latest_art_date = latest_art_date + "Z"

    xml_entries = [
        f"""  <url>
    <loc>{base_url}/</loc>
    <lastmod>{latest_art_date or now_iso}</lastmod>
    <changefreq>always</changefreq>
    <priority>1.0</priority>
  </url>
  <url>
    <loc>{base_url}/about</loc>
    <lastmod>{now_iso}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.7</priority>
  </url>
  <url>
    <loc>{base_url}/llms.txt</loc>
    <lastmod>{now_iso}</lastmod>
    <changefreq>hourly</changefreq>
    <priority>0.8</priority>
  </url>"""
    ]

    for art in articles:
        slug = slugify_title(art.get("title", ""))
        art_date = art.get("published_at") or now_iso
        if art_date and " " in art_date and "T" not in art_date:
            art_date = art_date.replace(" ", "T") + "Z"
        elif art_date and not art_date.endswith("Z"):
            art_date = art_date + "Z"
        xml_entries.append(f"""  <url>
    <loc>{base_url}/news/{art['id']}/{slug}</loc>
    <lastmod>{art_date}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.9</priority>
  </url>""")

    xml_content = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(xml_entries) + "\n</urlset>"
    return Response(content=xml_content, media_type="application/xml")

@app.get("/preview.png")
async def serve_preview_image():
    """Serves the Open Graph preview image for social sharing."""
    img_file = os.path.join(FRONTEND_DIR, "preview.png")
    if os.path.exists(img_file):
        return FileResponse(img_file, media_type="image/png")
    return Response(status_code=404)

@app.get("/manifest.json")
async def serve_manifest():
    """Serves the Web App Manifest for PWA installation."""
    manifest_file = os.path.join(FRONTEND_DIR, "manifest.json")
    if not os.path.exists(manifest_file):
        manifest_file = os.path.join(BASE_DIR, "manifest.json")
    if os.path.exists(manifest_file):
        return FileResponse(manifest_file, media_type="application/manifest+json")
    raise HTTPException(status_code=404, detail="Manifest not found")

@app.get("/icons/{icon_name}")
async def serve_icons(icon_name: str):
    """Serves PWA application icons."""
    icon_path = os.path.join(FRONTEND_DIR, "icons", icon_name)
    if not os.path.exists(icon_path):
        icon_path = os.path.join(BASE_DIR, "icons", icon_name)
    if os.path.exists(icon_path):
        return FileResponse(icon_path, media_type="image/png")
    raise HTTPException(status_code=404, detail="Icon not found")


@app.get("/api/news")
async def get_news_feed(
    source: Optional[str] = Query(None, description="Filter by source (e.g. 'ET', 'Business Standard', 'LiveMint', 'All')"),
    type: Optional[str] = Query(None, description="Filter by classification type (e.g. 'important', 'filing', 'general', 'all')"),
    sentiment: Optional[str] = Query(None, description="Filter by sentiment (e.g. 'BULLISH', 'BEARISH', 'EARNINGS', 'POLICY', 'All')"),
    search: Optional[str] = Query(None, description="Keyword search in title and description"),
    limit: int = Query(60, ge=1, le=200, description="Max number of articles to return"),
    offset: int = Query(0, ge=0, description="Pagination offset")
):
    """
    Returns stored stock market articles, sorted newest first, with optional filtering.
    """
    try:
        articles = get_articles(
            source=source,
            sentiment=sentiment,
            search=search,
            article_type=type,
            limit=limit,
            offset=offset
        )
        stats = get_stats()

        return {
            "status": "success",
            "count": len(articles),
            "total_in_db": stats["total_articles"],
            "latest_article_time": stats["latest_article_time"],
            "articles": articles
        }
    except Exception as e:
        logger.error(f"Error fetching news: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve news: {str(e)}")

@app.get("/api/stats")
async def get_news_stats():
    """Returns database summary statistics, source counts, and sentiment breakdown."""
    try:
        stats = get_stats()
        return {
            "status": "success",
            "stats": stats
        }
    except Exception as e:
        logger.error(f"Error fetching stats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------------------------
# Real-Time Market Indices & Commodities Engine
# ---------------------------------------------------------------------------
import requests
import time

import concurrent.futures

FALLBACK_BENCHMARKS = [
    {"name": "NIFTY 50", "symbol": "^NSEI", "category": "INDIA", "price": 24055.80, "change": -119.90, "change_percent": -0.50, "currency": "₹"},
    {"name": "SENSEX", "symbol": "^BSESN", "category": "INDIA", "price": 76944.28, "change": -320.22, "change_percent": -0.41, "currency": "₹"},
    {"name": "BANK NIFTY", "symbol": "^NSEBANK", "category": "INDIA", "price": 57409.60, "change": -86.70, "change_percent": -0.15, "currency": "₹"},
    {"name": "NASDAQ", "symbol": "^IXIC", "category": "GLOBAL", "price": 26370.89, "change": -31.53, "change_percent": -0.12, "currency": "$"},
    {"name": "S&P 500", "symbol": "^GSPC", "category": "GLOBAL", "price": 7686.14, "change": -25.62, "change_percent": -0.33, "currency": "$"},
    {"name": "DOW JONES", "symbol": "^DJI", "category": "GLOBAL", "price": 53185.90, "change": -374.10, "change_percent": -0.70, "currency": "$"},
    {"name": "BRENT CRUDE", "symbol": "BZ=F", "category": "COMMODITY", "price": 92.10, "change": 1.61, "change_percent": 1.78, "currency": "$"},
    {"name": "GOLD", "symbol": "GC=F", "category": "COMMODITY", "price": 4425.30, "change": -56.20, "change_percent": -1.25, "currency": "$"},
    {"name": "USD/INR", "symbol": "INR=X", "category": "FOREX", "price": 94.94, "change": -0.21, "change_percent": -0.22, "currency": "₹"}
]

MARKET_INDICES_CACHE = {
    "data": FALLBACK_BENCHMARKS,
    "last_updated": 0
}

INDICES_CONFIG = [
    {"name": "NIFTY 50", "symbol": "^NSEI", "category": "INDIA", "currency": "₹"},
    {"name": "SENSEX", "symbol": "^BSESN", "category": "INDIA", "currency": "₹"},
    {"name": "BANK NIFTY", "symbol": "^NSEBANK", "category": "INDIA", "currency": "₹"},
    {"name": "NASDAQ", "symbol": "^IXIC", "category": "GLOBAL", "currency": "$"},
    {"name": "S&P 500", "symbol": "^GSPC", "category": "GLOBAL", "currency": "$"},
    {"name": "DOW JONES", "symbol": "^DJI", "category": "GLOBAL", "currency": "$"},
    {"name": "BRENT CRUDE", "symbol": "BZ=F", "category": "COMMODITY", "currency": "$"},
    {"name": "GOLD", "symbol": "GC=F", "category": "COMMODITY", "currency": "$"},
    {"name": "USD/INR", "symbol": "INR=X", "category": "FOREX", "currency": "₹"}
]

def fetch_single_index(item):
    name = item["name"]
    sym = item["symbol"]
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=1d"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }
    try:
        r = requests.get(url, headers=headers, timeout=2.5)
        if r.status_code == 200:
            meta = r.json()["chart"]["result"][0]["meta"]
            price = meta.get("regularMarketPrice", 0)
            prev_close = meta.get("chartPreviousClose") or meta.get("previousClose", price)
            change = price - prev_close if price and prev_close else 0
            change_pct = (change / prev_close) * 100 if prev_close else 0
            return {
                "name": name,
                "symbol": sym,
                "category": item["category"],
                "price": round(price, 2),
                "change": round(change, 2),
                "change_percent": round(change_pct, 2),
                "currency": item["currency"]
            }
    except Exception:
        pass
    return None

def get_live_market_indices():
    global MARKET_INDICES_CACHE
    now = time.time()
    if MARKET_INDICES_CACHE["data"] and (now - MARKET_INDICES_CACHE["last_updated"] < 60) and MARKET_INDICES_CACHE["last_updated"] > 0:
        return MARKET_INDICES_CACHE["data"]

    results = []
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=9) as executor:
            futures = {executor.submit(fetch_single_index, item): item for item in INDICES_CONFIG}
            for future in concurrent.futures.as_completed(futures, timeout=3.0):
                try:
                    res = future.result()
                    if res:
                        results.append(res)
                except Exception:
                    pass
    except Exception:
        pass

    if len(results) >= 2:
        ordered = []
        name_map = {r["name"]: r for r in results}
        for item in INDICES_CONFIG:
            if item["name"] in name_map:
                ordered.append(name_map[item["name"]])
            else:
                for fb in (MARKET_INDICES_CACHE.get("data") or FALLBACK_BENCHMARKS):
                    if fb["name"] == item["name"]:
                        ordered.append(fb)
                        break
        MARKET_INDICES_CACHE["data"] = ordered
        MARKET_INDICES_CACHE["last_updated"] = now
        return ordered

    return MARKET_INDICES_CACHE["data"] or FALLBACK_BENCHMARKS

@app.get("/api/market-indices")
async def get_market_indices():
    """Returns live or cached market indices and commodity prices."""
    data = await asyncio.to_thread(get_live_market_indices)
    return {
        "status": "success",
        "indices": data,
        "count": len(data)
    }

@app.post("/api/refresh")
async def trigger_refresh(background_tasks: BackgroundTasks):
    """Triggers an on-demand news ingestion cycle in the background."""
    background_tasks.add_task(fetch_and_store_all_news)
    return {
        "status": "success",
        "message": "News refresh initiated in background. Feed will update shortly."
    }

# ---------------------------------------------------------------------------
# Web Push Notification Endpoints (Native VAPID - No External Accounts)
# ---------------------------------------------------------------------------
from push_service import get_vapid_keys, send_web_push, broadcast_news_alerts
from database import save_subscription, delete_subscription, get_all_subscriptions
from fastapi import Request

@app.get("/service-worker.js")
@app.get("/sw.js")
async def serve_service_worker():
    """Serves the service worker from the root domain with full root scope."""
    sw_file = os.path.join(FRONTEND_DIR, "service-worker.js")
    if os.path.exists(sw_file):
        return FileResponse(
            sw_file,
            media_type="application/javascript",
            headers={
                "Service-Worker-Allowed": "/",
                "Cache-Control": "no-cache, no-store, must-revalidate"
            }
        )
    raise HTTPException(status_code=404, detail="Service Worker not found.")

@app.get("/api/push-public-key")
async def get_push_public_key():
    """Returns the local VAPID public key for browser pushManager subscription."""
    keys = get_vapid_keys()
    if not keys.get("publicKey"):
        raise HTTPException(status_code=500, detail="VAPID public key not configured.")
    return {"publicKey": keys["publicKey"]}

@app.post("/api/subscribe")
async def subscribe_push(request: Request):
    """Saves a browser push subscription to the subscriptions table."""
    try:
        sub_data = await request.json()
        if not sub_data.get("endpoint"):
            raise HTTPException(status_code=400, detail="Invalid subscription: missing endpoint.")
        saved = save_subscription(sub_data)
        if saved:
            return {"status": "success", "message": "Subscribed to ZeroLive alerts."}
        raise HTTPException(status_code=500, detail="Failed to persist subscription in database.")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/unsubscribe")
async def unsubscribe_push(request: Request):
    """Removes a push subscription from the database."""
    try:
        data = await request.json()
        endpoint = data.get("endpoint")
        if endpoint:
            delete_subscription(endpoint)
        return {"status": "success", "message": "Unsubscribed from alerts."}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/send-test-push")
async def send_test_push(request: Request):
    """Sends a live test Web Push notification to the client."""
    try:
        body = await request.json()
        sub_data = body.get("subscription")
        if not sub_data:
            subs = get_all_subscriptions()
            if not subs:
                return {"status": "error", "message": "No active subscriptions found. Enable notifications first."}
            sub_data = subs[0]

        payload = {
            "title": "⚡ ZeroLive Breaking Alert",
            "body": "NIFTY surges +1.2% | Banking & IT rally on strong corporate filings.",
            "url": "/?tab=important",
            "tag": f"test-push-{int(time.time())}"
        }
        success = send_web_push(sub_data, payload)
        if success:
            return {"status": "success", "message": "Test push alert delivered to your device!"}
        return {"status": "error", "message": "Push send failed. Ensure browser notifications are enabled."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------------------------
# Key Events Endpoints (RBI, Fed, Budget, Market Holidays, Earnings)
# ---------------------------------------------------------------------------
# MAINTENANCE NOTE (important):
# This table is NOT auto-scraped (no reliable free API covers RBI + Fed + Budget + market holidays together accurately).
# Add a simple admin route (e.g. POST /api/admin/events, protected by a basic password env variable)
# so new events can be added manually every couple months by checking:
# - RBI's official MPC calendar (rbi.org.in)
# - federalreserve.gov/monetarypolicy/fomccalendars.htm
# - NSE's published holiday list (nseindia.com)

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "zerolive-admin-2026")

@app.get("/api/events")
async def api_get_key_events(country: Optional[str] = Query(None, description="Filter by 'India', 'World', or 'All'")):
    """Returns scheduled upcoming and current key economic/market events."""
    events = await asyncio.to_thread(get_key_events, country)
    return {
        "status": "success",
        "events": events,
        "count": len(events)
    }

class AdminEventPayload(BaseModel):
    event_name: str
    country: str
    category: str
    event_date: str
    description: Optional[str] = ""

@app.post("/api/admin/events")
async def api_add_key_event(
    event: AdminEventPayload,
    authorization: Optional[str] = Header(None),
    admin_password: Optional[str] = Query(None)
):
    """Admin endpoint to add manual key events."""
    provided_pw = admin_password
    if authorization:
        if authorization.startswith("Bearer "):
            provided_pw = authorization.split("Bearer ")[1].strip()
        else:
            provided_pw = authorization.strip()

    if provided_pw != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid admin password")

    if not event.event_name or not event.event_date or not event.country:
        raise HTTPException(status_code=400, detail="Missing required event fields")

    new_id = await asyncio.to_thread(
        insert_key_event,
        event.event_name,
        event.country,
        event.category,
        event.event_date,
        event.description or ""
    )
    return {
        "status": "success",
        "message": f"Event '{event.event_name}' added successfully.",
        "event_id": new_id
    }

@app.delete("/api/admin/events/{event_id}")
async def api_delete_key_event(
    event_id: int,
    authorization: Optional[str] = Header(None),
    admin_password: Optional[str] = Query(None)
):
    """Admin endpoint to remove a key event."""
    provided_pw = admin_password
    if authorization:
        if authorization.startswith("Bearer "):
            provided_pw = authorization.split("Bearer ")[1].strip()
        else:
            provided_pw = authorization.strip()

    if provided_pw != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid admin password")

    deleted = await asyncio.to_thread(delete_key_event, event_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Event not found or could not be deleted")

    return {
        "status": "success",
        "message": f"Event {event_id} deleted."
    }

# ---------------------------------------------------------------------------
# Automated Economic Calendar & Market Holidays Endpoints
# ---------------------------------------------------------------------------
@app.get("/api/calendar/economic")
async def get_economic_calendar(
    country: Optional[str] = Query(None, description="Filter by country or country code"),
    impact: Optional[str] = Query(None, description="Filter by High, Medium, Low"),
    search: Optional[str] = Query(None, description="Search keyword")
):
    """Returns live economic calendar events with expected, actual, and previous figures."""
    events = await asyncio.to_thread(fetch_live_economic_calendar)
    filtered = list(events)
    if country and country.lower() != "all":
        c_low = country.lower()
        filtered = [e for e in filtered if c_low in e.get("country", "").lower() or c_low in e.get("country_code", "").lower()]
    if impact and impact.lower() != "all":
        i_low = impact.lower()
        filtered = [e for e in filtered if i_low == e.get("impact", "").lower()]
    if search and search.strip():
        s_low = search.strip().lower()
        filtered = [e for e in filtered if s_low in e.get("event_name", "").lower() or s_low in e.get("country", "").lower()]

    return {
        "status": "success",
        "events": filtered,
        "count": len(filtered)
    }

@app.get("/api/calendar/holidays")
async def get_market_holidays():
    """Returns official exchange trading holidays."""
    holidays = await asyncio.to_thread(fetch_live_market_holidays)
    return {
        "status": "success",
        "holidays": holidays,
        "count": len(holidays)
    }

@app.get("/healthz")
@app.get("/api/health")
async def health_check():
    """Healthcheck endpoint for monitoring / Render deployment checks and keep-alive pings."""
    return {
        "status": "ok",
        "service": "ZeroLive-news",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    logger.info(f"Starting server on {host}:{port}")
    uvicorn.run("app:app", host=host, port=port, reload=False)
