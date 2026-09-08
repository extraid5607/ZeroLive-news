import os
import json
import asyncio
import logging
import time
import requests
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from fastapi import FastAPI, Query, BackgroundTasks, HTTPException, Header, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse, PlainTextResponse, Response
from fastapi.middleware.cors import CORSMiddleware

from database import get_articles, get_stats, init_db, get_key_events, insert_key_event, delete_key_event, get_article_by_id, get_related_articles
from fetch_news import fetch_and_store_all_news, fetch_live_economic_calendar, fetch_live_market_holidays
from article_template import slugify_title, render_article_html, render_not_found_html

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
    live_url = os.environ.get("RENDER_EXTERNAL_URL", "https://zerolivenews.onrender.com").rstrip("/")
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

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    """Serves the main application frontend with dynamic JSON-LD structured data."""
    index_file = os.path.join(FRONTEND_DIR, "index.html")
    if not os.path.exists(index_file):
        return HTMLResponse("<h1>ZeroLive Frontend not found</h1>", status_code=404)
    
    with open(index_file, "r", encoding="utf-8") as f:
        html = f.read()

    # Dynamically inject JSON-LD ItemList populated with current real articles
    try:
        articles = get_articles(article_type="important", limit=25)
        if not articles:
            articles = get_articles(limit=25)
        item_list_elements = []
        for i, art in enumerate(articles, start=1):
            item_list_elements.append({
                "@type": "ListItem",
                "position": i,
                "url": art.get("link") or "https://zerolive.in/",
                "name": art.get("title") or "Market News"
            })

        json_ld_data = {
            "@context": "https://schema.org",
            "@type": "ItemList",
            "itemListElement": item_list_elements
        }
        json_ld_script = (
            '<script type="application/ld+json">\n'
            + json.dumps(json_ld_data, ensure_ascii=False, indent=2)
            + '\n</script>'
        )

        if "</head>" in html:
            html = html.replace("</head>", f"  {json_ld_script}\n</head>", 1)
    except Exception as e:
        logger.warning(f"Failed to inject dynamic JSON-LD schema: {e}")

    return HTMLResponse(content=html, media_type="text/html")

@app.get("/about", response_class=HTMLResponse)
async def serve_about():
    """Serves the ZeroLive About & Regulatory Disclaimer page."""
    about_file = os.path.join(FRONTEND_DIR, "about.html")
    if os.path.exists(about_file):
        with open(about_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), media_type="text/html")
    return HTMLResponse("<h1>ZeroLive About Page Not Found</h1>", status_code=404)

@app.get("/news/{article_id}", response_class=HTMLResponse)
@app.get("/news/{article_id}/{slug}", response_class=HTMLResponse)
async def serve_article_page(article_id: int, slug: Optional[str] = None):
    """
    Dedicated SEO & Social Sharing Article Page.
    Serves full on-site clean reader with source attribution, WhatsApp Open Graph cards, and JSON-LD schema.
    """
    article = await asyncio.to_thread(get_article_by_id, article_id)
    base_url = os.environ.get("RENDER_EXTERNAL_URL", "https://zerolivenews.onrender.com").rstrip("/")

    if not article:
        not_found_html = render_not_found_html(base_url)
        return HTMLResponse(content=not_found_html, status_code=404)

    related = await asyncio.to_thread(get_related_articles, article_id, 6)
    html_content = render_article_html(article, related, base_url)
    return HTMLResponse(content=html_content, media_type="text/html")

@app.get("/robots.txt", response_class=PlainTextResponse)
async def serve_robots():
    """Returns robots.txt for search engine crawlers."""
    robots_file = os.path.join(FRONTEND_DIR, "robots.txt")
    if os.path.exists(robots_file):
        with open(robots_file, "r", encoding="utf-8") as f:
            return PlainTextResponse(f.read(), media_type="text/plain")
    return PlainTextResponse("User-agent: *\nAllow: /\nSitemap: https://zerolivenews.onrender.com/sitemap.xml\n", media_type="text/plain")

@app.get("/sitemap.xml")
async def serve_sitemap():
    """Generates and returns live dynamic sitemap XML with latest articles."""
    base_url = os.environ.get("RENDER_EXTERNAL_URL", "https://zerolivenews.onrender.com").rstrip("/")
    articles = await asyncio.to_thread(get_articles, None, None, None, None, 100, 0)

    xml_entries = [
        f"""  <url>
    <loc>{base_url}/</loc>
    <changefreq>always</changefreq>
    <priority>1.0</priority>
  </url>
  <url>
    <loc>{base_url}/about</loc>
    <changefreq>monthly</changefreq>
    <priority>0.8</priority>
  </url>"""
    ]

    for art in articles:
        slug = slugify_title(art.get("title", ""))
        xml_entries.append(f"""  <url>
    <loc>{base_url}/news/{art['id']}/{slug}</loc>
    <changefreq>daily</changefreq>
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
