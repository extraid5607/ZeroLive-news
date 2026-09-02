import os
import json
import sqlite3
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple

DATABASE_URL = os.environ.get("DATABASE_URL")
SQLITE_DB_PATH = os.environ.get("SQLITE_DB_PATH", os.path.join(os.path.dirname(__file__), "data", "news.db"))

def is_postgres() -> bool:
    return bool(DATABASE_URL and (DATABASE_URL.startswith("postgres://") or DATABASE_URL.startswith("postgresql://")))

def get_normalized_postgres_url() -> str:
    url = DATABASE_URL or ""
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url

def get_db_connection():
    if is_postgres():
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(get_normalized_postgres_url())
        return conn
    else:
        db_dir = os.path.dirname(SQLITE_DB_PATH)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        conn = sqlite3.connect(SQLITE_DB_PATH, timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
        except Exception:
            pass
        return conn

def init_db():
    """Initializes the database schema if not already present."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        if is_postgres():
            cur.execute("""
                CREATE TABLE IF NOT EXISTS articles (
                    id SERIAL PRIMARY KEY,
                    title TEXT NOT NULL,
                    link TEXT NOT NULL UNIQUE,
                    source TEXT NOT NULL,
                    feed_name TEXT,
                    description TEXT,
                    published_at TIMESTAMP WITH TIME ZONE NOT NULL,
                    published_str TEXT,
                    sentiment TEXT DEFAULT 'NEUTRAL',
                    category TEXT DEFAULT 'GENERAL',
                    type TEXT DEFAULT 'general',
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_articles_published_at ON articles (published_at DESC);
                CREATE INDEX IF NOT EXISTS idx_articles_source ON articles (source);
                CREATE INDEX IF NOT EXISTS idx_articles_sentiment ON articles (sentiment);

                CREATE TABLE IF NOT EXISTS subscriptions (
                    id SERIAL PRIMARY KEY,
                    endpoint TEXT NOT NULL UNIQUE,
                    p256dh TEXT,
                    auth TEXT,
                    subscription_json TEXT NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS key_events (
                    id SERIAL PRIMARY KEY,
                    event_name TEXT NOT NULL,
                    country TEXT NOT NULL,
                    category TEXT NOT NULL,
                    event_date TEXT NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_key_events_date ON key_events (event_date ASC);
            """)
            try:
                cur.execute("ALTER TABLE articles ADD COLUMN IF NOT EXISTS type TEXT DEFAULT 'general';")
            except Exception:
                pass
            try:
                cur.execute("CREATE INDEX IF NOT EXISTS idx_articles_type ON articles (type);")
            except Exception:
                pass
        else:
            cur.executescript("""
                CREATE TABLE IF NOT EXISTS articles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    link TEXT NOT NULL UNIQUE,
                    source TEXT NOT NULL,
                    feed_name TEXT,
                    description TEXT,
                    published_at TEXT NOT NULL,
                    published_str TEXT,
                    sentiment TEXT DEFAULT 'NEUTRAL',
                    category TEXT DEFAULT 'GENERAL',
                    type TEXT DEFAULT 'general',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_articles_published_at ON articles (published_at DESC);
                CREATE INDEX IF NOT EXISTS idx_articles_source ON articles (source);
                CREATE INDEX IF NOT EXISTS idx_articles_sentiment ON articles (sentiment);

                CREATE TABLE IF NOT EXISTS subscriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    endpoint TEXT NOT NULL UNIQUE,
                    p256dh TEXT,
                    auth TEXT,
                    subscription_json TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS key_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_name TEXT NOT NULL,
                    country TEXT NOT NULL,
                    category TEXT NOT NULL,
                    event_date TEXT NOT NULL,
                    description TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_key_events_date ON key_events (event_date ASC);
            """)
            try:
                cur.execute("ALTER TABLE articles ADD COLUMN type TEXT DEFAULT 'general';")
            except Exception:
                pass
            try:
                cur.execute("CREATE INDEX IF NOT EXISTS idx_articles_type ON articles (type);")
            except Exception:
                pass
        conn.commit()
    finally:
        conn.close()

    # Seed initial key events if table is empty
    seed_key_events_if_empty()

def upsert_articles(articles: List[Dict[str, Any]]) -> Tuple[int, int]:
    """
    Inserts a list of articles. Ignores duplicates based on the unique 'link'.
    Returns (inserted_count, skipped_count).
    """
    if not articles:
        return 0, 0

    init_db()
    conn = get_db_connection()
    inserted_count = 0
    skipped_count = 0

    try:
        cur = conn.cursor()
        if is_postgres():
            for art in articles:
                pub_at = art.get("published_at")
                if isinstance(pub_at, str):
                    try:
                        pub_at = datetime.fromisoformat(pub_at)
                    except Exception:
                        pub_at = datetime.now(timezone.utc)

                cur.execute("""
                    INSERT INTO articles (title, link, source, feed_name, description, published_at, published_str, sentiment, category, type)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (link) DO NOTHING
                    RETURNING id;
                """, (
                    art.get("title", ""),
                    art.get("link", ""),
                    art.get("source", ""),
                    art.get("feed_name", ""),
                    art.get("description", ""),
                    pub_at,
                    art.get("published_str", ""),
                    art.get("sentiment", "NEUTRAL"),
                    art.get("category", "GENERAL"),
                    art.get("type", "general")
                ))
                res = cur.fetchone()
                if res:
                    inserted_count += 1
                else:
                    skipped_count += 1
        else:
            for art in articles:
                pub_at = art.get("published_at")
                if isinstance(pub_at, datetime):
                    pub_at = pub_at.isoformat()
                elif not pub_at:
                    pub_at = datetime.now(timezone.utc).isoformat()

                cur.execute("""
                    INSERT OR IGNORE INTO articles (title, link, source, feed_name, description, published_at, published_str, sentiment, category, type)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, (
                    art.get("title", ""),
                    art.get("link", ""),
                    art.get("source", ""),
                    art.get("feed_name", ""),
                    art.get("description", ""),
                    pub_at,
                    art.get("published_str", ""),
                    art.get("sentiment", "NEUTRAL"),
                    art.get("category", "GENERAL"),
                    art.get("type", "general")
                ))
                if cur.rowcount > 0:
                    inserted_count += 1
                else:
                    skipped_count += 1
        conn.commit()
    finally:
        conn.close()

    return inserted_count, skipped_count

def get_articles(
    source: Optional[str] = None,
    sentiment: Optional[str] = None,
    search: Optional[str] = None,
    article_type: Optional[str] = None,
    limit: int = 60,
    offset: int = 0
) -> List[Dict[str, Any]]:
    """Retrieves articles sorted by publish date (newest first) with optional filtering."""
    init_db()
    conn = get_db_connection()
    articles = []

    try:
        cur = conn.cursor()
        conditions = []
        params = []

        # 1. Classification Type Filtering (e.g. 'important', 'filing', 'general')
        if article_type and article_type.strip().lower() != "all":
            t_val = article_type.strip().lower()
            conditions.append("LOWER(type) = %s" if is_postgres() else "LOWER(type) = ?")
            params.append(t_val)

        # 2. Source / Category Hub Filtering
        if source and source.strip().lower() != "all":
            src_val = source.strip().lower()
            if src_val in ["exchange", "exchanges", "nse/bse", "filings", "filing"]:
                # Match official exchanges OR classified filings
                conditions.append("(LOWER(source) LIKE %s OR LOWER(source) LIKE %s OR LOWER(type) = %s)" if is_postgres() else "(LOWER(source) LIKE ? OR LOWER(source) LIKE ? OR LOWER(type) = ?)")
                params.extend(["%nse%", "%bse%", "filing"])
            elif src_val in ["indian", "india", "domestic"]:
                conditions.append("(LOWER(source) LIKE %s OR LOWER(source) LIKE %s OR LOWER(source) LIKE %s OR LOWER(source) LIKE %s)" if is_postgres() else "(LOWER(source) LIKE ? OR LOWER(source) LIKE ? OR LOWER(source) LIKE ? OR LOWER(source) LIKE ?)")
                params.extend(["%economic times%", "%business standard%", "%livemint%", "%moneycontrol%"])
            elif src_val in ["international", "global", "world"]:
                conditions.append("(LOWER(source) LIKE %s OR LOWER(source) LIKE %s OR LOWER(source) LIKE %s OR LOWER(source) LIKE %s OR LOWER(source) LIKE %s OR LOWER(source) LIKE %s)" if is_postgres() else "(LOWER(source) LIKE ? OR LOWER(source) LIKE ? OR LOWER(source) LIKE ? OR LOWER(source) LIKE ? OR LOWER(source) LIKE ? OR LOWER(source) LIKE ?)")
                params.extend(["%reuters%", "%yahoo%", "%cnbc%", "%bloomberg%", "%investing%", "%financial times%"])
            elif src_val in ["trump", "trump wire", "truth social"]:
                conditions.append("LOWER(source) LIKE %s" if is_postgres() else "LOWER(source) LIKE ?")
                params.append("%trump%")
            elif src_val in ["moneycontrol", "mc"]:
                conditions.append("LOWER(source) LIKE %s" if is_postgres() else "LOWER(source) LIKE ?")
                params.append("%moneycontrol%")
            elif src_val in ["reuters"]:
                conditions.append("LOWER(source) LIKE %s" if is_postgres() else "LOWER(source) LIKE ?")
                params.append("%reuters%")
            elif src_val in ["bloomberg"]:
                conditions.append("LOWER(source) LIKE %s" if is_postgres() else "LOWER(source) LIKE ?")
                params.append("%bloomberg%")
            elif src_val in ["investing", "investing.com"]:
                conditions.append("LOWER(source) LIKE %s" if is_postgres() else "LOWER(source) LIKE ?")
                params.append("%investing%")
            elif src_val in ["financial times", "ft"]:
                conditions.append("LOWER(source) LIKE %s" if is_postgres() else "LOWER(source) LIKE ?")
                params.append("%financial times%")
            elif src_val in ["yahoo", "yahoo finance"]:
                conditions.append("LOWER(source) LIKE %s" if is_postgres() else "LOWER(source) LIKE ?")
                params.append("%yahoo%")
            elif src_val in ["cnbc"]:
                conditions.append("LOWER(source) LIKE %s" if is_postgres() else "LOWER(source) LIKE ?")
                params.append("%cnbc%")
            elif src_val in ["et", "economictimes", "economic times"]:
                conditions.append("LOWER(source) LIKE %s" if is_postgres() else "LOWER(source) LIKE ?")
                params.append("%economic times%")
            elif src_val in ["bs", "business standard", "business-standard"]:
                conditions.append("LOWER(source) LIKE %s" if is_postgres() else "LOWER(source) LIKE ?")
                params.append("%business standard%")
            elif src_val in ["livemint", "mint"]:
                conditions.append("LOWER(source) LIKE %s" if is_postgres() else "LOWER(source) LIKE ?")
                params.append("%livemint%")
            elif src_val in ["nse", "nse india", "nse official"]:
                conditions.append("LOWER(source) LIKE %s" if is_postgres() else "LOWER(source) LIKE ?")
                params.append("%nse%")
            elif src_val in ["bse", "bse india", "bse official"]:
                conditions.append("LOWER(source) LIKE %s" if is_postgres() else "LOWER(source) LIKE ?")
                params.append("%bse%")
            else:
                conditions.append("LOWER(source) LIKE %s" if is_postgres() else "LOWER(source) LIKE ?")
                params.append(f"%{src_val}%")

        if sentiment and sentiment.strip().lower() != "all":
            sent_val = sentiment.strip().lower()
            if sent_val in ["macro_events", "macro", "events", "rbi_fed", "policy_macro"]:
                macro_patterns = [
                    "%rbi%", "%repo rate%", "%monetary policy%", "%interest rate%",
                    "%federal reserve%", "%fed %", "% fed%", "%fomc%", "%rate cut%", "%rate hike%", "%rate decision%",
                    "%inflation%", "%cpi%", "%wpi%", "%gdp%", "%tariff%", "%central bank%", "%ecb%", "%boj%", "%powell%"
                ]
                clauses = []
                for _ in macro_patterns:
                    if is_postgres():
                        clauses.append("(LOWER(title) LIKE %s OR (LOWER(source) NOT LIKE '%bse%' AND LOWER(source) NOT LIKE '%nse%' AND LOWER(description) LIKE %s))")
                    else:
                        clauses.append("(LOWER(title) LIKE ? OR (LOWER(source) NOT LIKE '%bse%' AND LOWER(source) NOT LIKE '%nse%' AND LOWER(description) LIKE ?))")
                conditions.append(f"({' OR '.join(clauses)})")
                for w in macro_patterns:
                    params.extend([w, w])
            else:
                conditions.append("UPPER(sentiment) = %s" if is_postgres() else "UPPER(sentiment) = ?")
                params.append(sentiment.strip().upper())

        if search and search.strip():
            query_str = f"%{search.strip().lower()}%"
            if is_postgres():
                conditions.append("(LOWER(title) LIKE %s OR LOWER(description) LIKE %s)")
                params.extend([query_str, query_str])
            else:
                conditions.append("(LOWER(title) LIKE ? OR LOWER(description) LIKE ?)")
                params.extend([query_str, query_str])

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"""
            SELECT id, title, link, source, feed_name, description, published_at, published_str, sentiment, category, type, created_at
            FROM articles
            {where_clause}
            ORDER BY published_at DESC
            LIMIT {'%s OFFSET %s' if is_postgres() else '? OFFSET ?'}
        """
        params.extend([limit, offset])

        cur.execute(query, tuple(params))
        rows = cur.fetchall()

        if is_postgres():
            colnames = [desc[0] for desc in cur.description]
            for row in rows:
                item = dict(zip(colnames, row))
                if isinstance(item.get("published_at"), datetime):
                    item["published_at"] = item["published_at"].isoformat()
                if isinstance(item.get("created_at"), datetime):
                    item["created_at"] = item["created_at"].isoformat()
                articles.append(item)
        else:
            for row in rows:
                articles.append(dict(row))

    finally:
        conn.close()

    return articles

def get_stats() -> Dict[str, Any]:
    """Returns article counts, sentiment breakdowns, source counts, types counts, and latest update time."""
    init_db()
    conn = get_db_connection()
    stats = {
        "total_articles": 0,
        "latest_article_time": None,
        "types": {
            "important": 0,
            "filing": 0,
            "general": 0
        },
        "sources": {},
        "sentiments": {
            "BULLISH": 0,
            "BEARISH": 0,
            "EARNINGS": 0,
            "POLICY": 0,
            "NEUTRAL": 0
        }
    }

    try:
        cur = conn.cursor()
        # Total count & latest article
        cur.execute("SELECT COUNT(*), MAX(published_at) FROM articles")
        row = cur.fetchone()
        if row:
            stats["total_articles"] = row[0] or 0
            latest = row[1]
            if isinstance(latest, datetime):
                stats["latest_article_time"] = latest.isoformat()
            else:
                stats["latest_article_time"] = latest

        # Type classification breakdown
        try:
            cur.execute("SELECT type, COUNT(*) FROM articles GROUP BY type")
            for t_val, count in cur.fetchall():
                if t_val:
                    stats["types"][t_val.lower()] = count
        except Exception:
            pass

        # Source breakdown
        cur.execute("SELECT source, COUNT(*) FROM articles GROUP BY source")
        for src, count in cur.fetchall():
            stats["sources"][src] = count

        # Sentiment breakdown
        cur.execute("SELECT sentiment, COUNT(*) FROM articles GROUP BY sentiment")
        for sent, count in cur.fetchall():
            if sent:
                stats["sentiments"][sent.upper()] = count

    finally:
        conn.close()

    return stats

def save_subscription(sub_data: Dict[str, Any]) -> bool:
    """Saves or updates a Web Push subscription."""
    endpoint = sub_data.get("endpoint")
    if not endpoint:
        return False

    keys = sub_data.get("keys", {})
    p256dh = keys.get("p256dh", "")
    auth = keys.get("auth", "")
    sub_json = json.dumps(sub_data) if isinstance(sub_data, dict) else str(sub_data)

    init_db()
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        if is_postgres():
            cur.execute("""
                INSERT INTO subscriptions (endpoint, p256dh, auth, subscription_json, created_at)
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (endpoint) DO UPDATE SET
                    p256dh = EXCLUDED.p256dh,
                    auth = EXCLUDED.auth,
                    subscription_json = EXCLUDED.subscription_json
            """, (endpoint, p256dh, auth, sub_json))
        else:
            cur.execute("""
                INSERT INTO subscriptions (endpoint, p256dh, auth, subscription_json, created_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(endpoint) DO UPDATE SET
                    p256dh=excluded.p256dh,
                    auth=excluded.auth,
                    subscription_json=excluded.subscription_json
            """, (endpoint, p256dh, auth, sub_json))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error saving subscription: {e}")
        return False
    finally:
        conn.close()

def get_all_subscriptions() -> List[Dict[str, Any]]:
    """Retrieves all active push subscriptions."""
    init_db()
    conn = get_db_connection()
    subs = []
    try:
        cur = conn.cursor()
        cur.execute("SELECT endpoint, p256dh, auth, subscription_json FROM subscriptions")
        for row in cur.fetchall():
            try:
                sub_dict = json.loads(row[3])
                subs.append(sub_dict)
            except Exception:
                subs.append({
                    "endpoint": row[0],
                    "keys": {
                        "p256dh": row[1],
                        "auth": row[2]
                    }
                })
    except Exception as e:
        print(f"Error fetching subscriptions: {e}")
    finally:
        conn.close()
    return subs

def delete_subscription(endpoint: str) -> bool:
    """Deletes a 410 Gone / expired subscription from the database."""
    if not endpoint:
        return False
    init_db()
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        if is_postgres():
            cur.execute("DELETE FROM subscriptions WHERE endpoint = %s", (endpoint,))
        else:
            cur.execute("DELETE FROM subscriptions WHERE endpoint = ?", (endpoint,))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error deleting subscription: {e}")
        return False
    finally:
        conn.close()

# ==============================================================================
# KEY EVENTS MANAGEMENT
# ==============================================================================
# MAINTENANCE NOTE (important):
# This table is NOT auto-scraped (no reliable free API covers RBI + Fed + Budget + market holidays together accurately).
# Add a simple admin route (e.g. POST /api/admin/events, protected by a basic password env variable)
# so new events can be added manually every couple months by checking:
# - RBI's official MPC calendar (rbi.org.in)
# - federalreserve.gov/monetarypolicy/fomccalendars.htm
# - NSE's published holiday list (nseindia.com)

SEED_KEY_EVENTS = [
    {
        "event_name": "Fed FOMC Rate Decision",
        "country": "World",
        "category": "Fed Policy",
        "event_date": "2026-09-16",
        "description": "US Federal Reserve interest rate decision"
    },
    {
        "event_name": "RBI MPC Policy Decision",
        "country": "India",
        "category": "RBI Policy",
        "event_date": "2026-10-07",
        "description": "RBI announces repo rate decision"
    },
    {
        "event_name": "RBI MPC Policy Decision",
        "country": "India",
        "category": "RBI Policy",
        "event_date": "2026-12-04",
        "description": "RBI announces repo rate decision"
    },
    {
        "event_name": "Union Budget 2027",
        "country": "India",
        "category": "Budget",
        "event_date": "2027-02-01",
        "description": "Government of India annual budget"
    }
]

def seed_key_events_if_empty():
    """Seeds the key_events table with confirmed real dates if empty."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM key_events")
        count = cur.fetchone()[0]
        if count == 0:
            for ev in SEED_KEY_EVENTS:
                if is_postgres():
                    cur.execute("""
                        INSERT INTO key_events (event_name, country, category, event_date, description)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (ev["event_name"], ev["country"], ev["category"], ev["event_date"], ev["description"]))
                else:
                    cur.execute("""
                        INSERT INTO key_events (event_name, country, category, event_date, description)
                        VALUES (?, ?, ?, ?, ?)
                    """, (ev["event_name"], ev["country"], ev["category"], ev["event_date"], ev["description"]))
            conn.commit()
    except Exception as e:
        print(f"Error seeding key events: {e}")
    finally:
        conn.close()

def get_key_events(country: Optional[str] = None) -> List[Dict[str, Any]]:
    """Fetches all key events sorted by event_date ASC."""
    init_db()
    conn = get_db_connection()
    events = []
    try:
        cur = conn.cursor()
        query = "SELECT id, event_name, country, category, event_date, description, created_at FROM key_events"
        params = []
        if country and country.lower() != "all":
            query += " WHERE LOWER(country) = " + ("%s" if is_postgres() else "?")
            params.append(country.lower())
        query += " ORDER BY event_date ASC"

        cur.execute(query, tuple(params))
        rows = cur.fetchall()
        for r in rows:
            events.append({
                "id": r[0],
                "event_name": r[1],
                "country": r[2],
                "category": r[3],
                "event_date": r[4],
                "description": r[5] or "",
                "created_at": r[6].isoformat() if hasattr(r[6], "isoformat") else str(r[6])
            })
    except Exception as e:
        print(f"Error fetching key events: {e}")
    finally:
        conn.close()
    return events

def insert_key_event(event_name: str, country: str, category: str, event_date: str, description: str = "") -> int:
    """Inserts a new key event into the database."""
    init_db()
    conn = get_db_connection()
    new_id = 0
    try:
        cur = conn.cursor()
        if is_postgres():
            cur.execute("""
                INSERT INTO key_events (event_name, country, category, event_date, description)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id;
            """, (event_name, country, category, event_date, description))
            res = cur.fetchone()
            if res:
                new_id = res[0]
        else:
            cur.execute("""
                INSERT INTO key_events (event_name, country, category, event_date, description)
                VALUES (?, ?, ?, ?, ?);
            """, (event_name, country, category, event_date, description))
            new_id = cur.lastrowid
        conn.commit()
    except Exception as e:
        print(f"Error inserting key event: {e}")
    finally:
        conn.close()
    return new_id

def delete_key_event(event_id: int) -> bool:
    """Deletes a key event by ID."""
    init_db()
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        if is_postgres():
            cur.execute("DELETE FROM key_events WHERE id = %s", (event_id,))
        else:
            cur.execute("DELETE FROM key_events WHERE id = ?", (event_id,))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error deleting key event {event_id}: {e}")
        return False
    finally:
        conn.close()


