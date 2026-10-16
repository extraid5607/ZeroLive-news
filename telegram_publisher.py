import os
import re
import time
import json
import html
import logging
from typing import Dict, Any, List, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont
import requests

logger = logging.getLogger("telegram_publisher")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
FONTS_DIR = os.path.join(ASSETS_DIR, "fonts")
TEMP_BANNER_DIR = os.path.join(BASE_DIR, "temp_banners")
SENT_FILE = os.path.join(BASE_DIR, "telegram_sent.json")

# Ensure necessary directories exist
os.makedirs(TEMP_BANNER_DIR, exist_ok=True)
os.makedirs(FONTS_DIR, exist_ok=True)

# Common Indian ticker list for smart hashtag tagging
COMMON_TICKERS = [
    "RELIANCE", "TCS", "HDFCBANK", "INFOSYS", "ICICIBANK", "SBIN", "BHARTIARTL",
    "ITC", "LT", "HINDUNILVR", "TATAMOTORS", "ADANIENT", "ADANIPORTS", "BAJFINANCE",
    "MARUTI", "TITAN", "KOTAKBANK", "AXISBANK", "SUNPHARMA", "NTPC", "ONGC",
    "COALINDIA", "TATASTEEL", "POWERGRID", "M&M", "JSWSTEEL", "WIPRO", "HCLTECH",
    "ULTRACEMCO", "TECHM", "NESTLEIND", "GRASIM", "BAJAJFINSV", "CIPLA", "DRREDDY",
    "EICHERMOT", "DIVISLAB", "APOLLOHOSP", "BPCL", "HEROMOTOCO", "INDUSINDBK",
    "NIFTY", "SENSEX", "BANKNIFTY", "RBI", "FED", "SEBI"
]

_CREDENTIALS_WARNED = False

def get_telegram_credentials() -> Tuple[Optional[str], Optional[str]]:
    """
    Retrieves TELEGRAM_BOT_TOKEN and normalized TELEGRAM_CHANNEL_ID.
    Checks environment variables -> .env -> Telegram.txt.
    """
    global _CREDENTIALS_WARNED
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    channel_id = os.environ.get("TELEGRAM_CHANNEL_ID")

    # 1. Fallback to .env file
    env_file = os.path.join(BASE_DIR, ".env")
    if (not token or not channel_id) and os.path.exists(env_file):
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    if k == "TELEGRAM_BOT_TOKEN" and not token:
                        token = v
                    elif k == "TELEGRAM_CHANNEL_ID" and not channel_id:
                        channel_id = v
        except Exception as e:
            logger.debug(f"Error parsing .env for Telegram: {e}")

    # 2. Fallback to Telegram.txt or Telegram folder
    tg_txt = os.path.join(BASE_DIR, "Telegram.txt")
    if (not token or not channel_id) and os.path.exists(tg_txt):
        try:
            with open(tg_txt, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if ":" in line:
                        k, v = line.split(":", 1)
                        k = k.strip()
                        v = v.strip()
                        if "TELEGRAM_BOT_TOKEN" in k and not token:
                            token = v
                        elif "TELEGRAM_CHANNEL_ID" in k and not channel_id:
                            channel_id = v
        except Exception as e:
            logger.debug(f"Error reading Telegram.txt: {e}")

    # Clean and normalize channel identifier
    if channel_id:
        channel_id = channel_id.strip()
        if channel_id.startswith("https://t.me/"):
            channel_name = channel_id.replace("https://t.me/", "").strip("/").split("/")[0]
            channel_id = f"@{channel_name}" if not channel_name.startswith("@") else channel_name
        elif channel_id.startswith("t.me/"):
            channel_name = channel_id.replace("t.me/", "").strip("/").split("/")[0]
            channel_id = f"@{channel_name}" if not channel_name.startswith("@") else channel_name
        elif not channel_id.startswith("@") and not channel_id.startswith("-"):
            channel_id = f"@{channel_id}"

    if not token or not channel_id:
        if not _CREDENTIALS_WARNED:
            logger.warning(
                "Telegram Publisher: TELEGRAM_BOT_TOKEN or TELEGRAM_CHANNEL_ID is not configured. "
                "Telegram alerts are currently paused."
            )
            _CREDENTIALS_WARNED = True
        return None, None

    return token, channel_id


def get_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    """
    Returns a TrueType font cross-platform (bundled Roboto -> system Arial/DejaVu -> default).
    """
    candidates = []
    if bold:
        candidates.extend([
            os.path.join(FONTS_DIR, "Roboto-Bold.ttf"),
            "arialbd.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/calibrib.ttf",
            "C:/Windows/Fonts/segoeuib.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        ])
    else:
        candidates.extend([
            os.path.join(FONTS_DIR, "Roboto-Regular.ttf"),
            "arial.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/calibri.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        ])

    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue

    try:
        return ImageFont.load_default()
    except Exception:
        return None


def extract_ticker(title: str, description: str = "") -> str:
    """Extracts high-confidence stock ticker tag from headline or description."""
    full_text = f"{title} {description}".upper()

    # Match bracketed codes e.g. [RELIANCE] or [TCS]
    bracket_match = re.search(r'\[([A-Z0-9_\.]{2,15})\]', title)
    if bracket_match:
        code = bracket_match.group(1).strip()
        if not code.isdigit() and len(code) >= 3:
            return code

    # Match known Indian ticker names
    for ticker in COMMON_TICKERS:
        pattern = r'\b' + re.escape(ticker) + r'\b'
        if re.search(pattern, full_text):
            return ticker

    return ""


def wrap_text_lines(text: str, font: ImageFont.ImageFont, max_width: int) -> List[str]:
    """Wraps text into clean lines fitting within max_width pixels."""
    if not text:
        return []
    words = text.split()
    lines = []
    curr = []

    for word in words:
        test_line = " ".join(curr + [word])
        bbox = font.getbbox(test_line)
        w = bbox[2] - bbox[0]
        if w <= max_width:
            curr.append(word)
        else:
            if curr:
                lines.append(" ".join(curr))
                curr = [word]
            else:
                lines.append(word)
                curr = []
    if curr:
        lines.append(" ".join(curr))
    return lines


def generate_telegram_card(story: Dict[str, Any]) -> str:
    """
    Generates a 1200x675px dark-mode breaking news image card.
    Saves to temp_banners/<story_id>.png and returns the file path.
    """
    width, height = 1200, 675
    img = Image.new("RGB", (width, height), color=(10, 14, 23))
    draw = ImageDraw.Draw(img)

    # 1. Background: Vertical Gradient (#0a0e17 -> #141b2d)
    for y in range(height):
        ratio = y / float(height)
        r = int(10 + (20 - 10) * ratio)
        g = int(14 + (27 - 14) * ratio)
        b = int(23 + (45 - 23) * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    # 2. Subtle Dark Grid Overlay (every 60px)
    grid_color = (18, 25, 42)
    for x in range(0, width, 60):
        draw.line([(x, 0), (x, height)], fill=grid_color, width=1)
    for y in range(0, height, 60):
        draw.line([(0, y), (width, y)], fill=grid_color, width=1)

    # 3. Faint Watermark "Z" in Center
    font_z = get_font(360, bold=True)
    if font_z:
        draw.text((490, 135), "Z", font=font_z, fill=(22, 30, 52))

    # 4. Top Header Bar
    # 4a. Top-Left: Electric Cyan Lightning Bolt + ZEROLIVE Brand
    # Draw geometric lightning bolt
    bolt_x, bolt_y, bolt_h = 50, 48, 26
    bolt_w = int(bolt_h * 0.65)
    bolt_pts = [
        (bolt_x + int(bolt_w * 0.6), bolt_y),
        (bolt_x, bolt_y + int(bolt_h * 0.55)),
        (bolt_x + int(bolt_w * 0.45), bolt_y + int(bolt_h * 0.55)),
        (bolt_x + int(bolt_w * 0.35), bolt_y + bolt_h),
        (bolt_x + bolt_w, bolt_y + int(bolt_h * 0.4)),
        (bolt_x + int(bolt_w * 0.55), bolt_y + int(bolt_h * 0.4)),
    ]
    draw.polygon(bolt_pts, fill=(0, 240, 255))

    font_brand = get_font(28, bold=True)
    draw.text((bolt_x + bolt_w + 12, 45), "ZEROLIVE", font=font_brand, fill=(255, 255, 255))

    # Sub-badge next to brand
    font_sub = get_font(13, bold=True)
    draw.text((bolt_x + bolt_w + 168, 55), "• LIVE TERMINAL", font=font_sub, fill=(56, 189, 248))

    # 4b. Top-Right: Sentiment / Alert Pill Badge
    sentiment = (story.get("sentiment") or "NEUTRAL").upper()
    if sentiment == "BULLISH":
        badge_bg = (11, 61, 32)      # #0b3d20
        badge_border = (34, 197, 94)  # #22c55e
        badge_text = "BULLISH ↑"
        dot_color = (34, 197, 94)
    elif sentiment == "BEARISH":
        badge_bg = (69, 18, 21)      # #451215
        badge_border = (239, 68, 68)  # #ef4444
        badge_text = "BEARISH ↓"
        dot_color = (239, 68, 68)
    else:
        badge_bg = (61, 43, 11)      # #3d2b0b
        badge_border = (245, 158, 11) # #f59e0b
        badge_text = "BREAKING"
        dot_color = (245, 158, 11)

    font_badge = get_font(18, bold=True)
    text_bbox = font_badge.getbbox(badge_text)
    badge_text_w = text_bbox[2] - text_bbox[0]

    pill_w = badge_text_w + 64
    pill_h = 40
    pill_x2 = width - 50
    pill_x1 = pill_x2 - pill_w
    pill_y1 = 42
    pill_y2 = pill_y1 + pill_h

    draw.rounded_rectangle(
        [(pill_x1, pill_y1), (pill_x2, pill_y2)],
        radius=20,
        fill=badge_bg,
        outline=badge_border,
        width=2
    )

    # Indicator Dot inside Pill
    dot_radius = 5
    dot_cx = pill_x1 + 22
    dot_cy = pill_y1 + (pill_h // 2)
    draw.ellipse(
        [(dot_cx - dot_radius, dot_cy - dot_radius), (dot_cx + dot_radius, dot_cy + dot_radius)],
        fill=dot_color
    )

    draw.text((pill_x1 + 36, pill_y1 + 9), badge_text, font=font_badge, fill=badge_border)

    # 5. Main Content Area
    # 5a. Wire Category Header with Ticker Tag
    ticker = extract_ticker(story.get("title", ""), story.get("description", ""))
    tag_text = f"⚡ BREAKING MARKET WIRE  •  #{ticker}" if ticker else "⚡ BREAKING MARKET WIRE"
    font_tag = get_font(19, bold=True)
    draw.text((50, 120), tag_text, font=font_tag, fill=(245, 158, 11))

    # 5b. Headline with Dynamic Font Scaling (44px down to 34px, max 3 lines)
    raw_title = (story.get("title") or "Market Breaking Update").strip()
    clean_title = re.sub(r'[\r\n\t]+', ' ', raw_title)
    clean_title = re.sub(r'\s+', ' ', clean_title)

    font_headline = None
    headline_lines = []
    for fs in [44, 40, 38, 36, 34]:
        f_cand = get_font(fs, bold=True)
        lines_cand = wrap_text_lines(clean_title, f_cand, max_width=1100)
        if len(lines_cand) <= 3:
            font_headline = f_cand
            headline_lines = lines_cand
            break

    if not font_headline:
        font_headline = get_font(34, bold=True)
        headline_lines = wrap_text_lines(clean_title, font_headline, max_width=1100)[:3]
        if len(headline_lines) == 3 and not headline_lines[2].endswith("..."):
            headline_lines[2] = headline_lines[2][:max(10, len(headline_lines[2]) - 4)] + "..."

    curr_y = 165
    line_height = int(font_headline.size * 1.32)
    for line in headline_lines:
        draw.text((50, curr_y), line, font=font_headline, fill=(255, 255, 255))
        curr_y += line_height

    # 5c. Summary (max 3 lines cleanly truncated with ..., 24px)
    raw_desc = (story.get("description") or "").strip()
    clean_desc = re.sub(r'<[^>]+>', '', raw_desc)
    clean_desc = re.sub(r'[\r\n\t]+', ' ', clean_desc)
    clean_desc = re.sub(r'\s+', ' ', clean_desc).strip()

    if clean_desc:
        curr_y += 32
        font_summary = get_font(24, bold=False)
        summary_lines = wrap_text_lines(clean_desc, font_summary, max_width=1100)
        if len(summary_lines) > 3:
            summary_lines = summary_lines[:3]
            if not summary_lines[2].endswith("..."):
                summary_lines[2] = summary_lines[2][:max(10, len(summary_lines[2]) - 4)] + "..."

        sum_line_height = 34
        for s_line in summary_lines:
            draw.text((50, curr_y), s_line, font=font_summary, fill=(148, 163, 184))
            curr_y += sum_line_height

    # 6. Bottom Footer Bar
    # Thin Horizontal Divider at y = 600
    draw.line([(50, 600), (width - 50, 600)], fill=(0, 240, 255), width=2)

    # 6a. Bottom-Left Source
    source = (story.get("source") or story.get("feed_name") or "ZeroLive Wire").strip()
    font_footer = get_font(19, bold=False)
    draw.text((50, 622), f"📰 Source: {source}", font=font_footer, fill=(203, 213, 225))

    # 6b. Bottom-Right Terminal Branding
    font_footer_bold = get_font(19, bold=True)
    term_text = "⚡ Live Terminal: www.zerolive.in"
    term_bbox = font_footer_bold.getbbox(term_text)
    term_w = term_bbox[2] - term_bbox[0]
    draw.text((width - 50 - term_w, 622), term_text, font=font_footer_bold, fill=(245, 158, 11))

    # 7. Save to temp_banners
    story_id = str(story.get("id") or int(time.time()))
    safe_name = re.sub(r'[^a-zA-Z0-9_\-]', '', story_id)
    output_path = os.path.join(TEMP_BANNER_DIR, f"{safe_name}.png")
    img.save(output_path, "PNG", optimize=True)
    return output_path


def build_telegram_caption(story: Dict[str, Any], base_url: str = "https://www.zerolive.in") -> str:
    """
    Constructs an HTML-escaped Telegram photo caption strictly under 950 characters.
    """
    sentiment = (story.get("sentiment") or "NEUTRAL").upper()
    source = html.escape((story.get("source") or story.get("feed_name") or "ZeroLive Wire").strip())
    raw_title = (story.get("title") or "Market Update").strip()
    escaped_title = html.escape(raw_title)

    ticker = extract_ticker(raw_title, story.get("description", ""))
    ticker_tags = f"#{ticker}" if ticker else ""

    if sentiment == "BULLISH":
        badge_header = f"🟢 <b>BULLISH</b> | <b>{source}</b>"
    elif sentiment == "BEARISH":
        badge_header = f"🔴 <b>BEARISH</b> | <b>{source}</b>"
    else:
        badge_header = f"⚡ <b>IMPORTANT</b> | <b>{source}</b>"

    if ticker_tags:
        badge_header += f" {ticker_tags}"

    # Generate canonical story URL
    slug = re.sub(r'[^a-z0-9]+', '-', raw_title.lower()).strip('-')[:80]
    story_id = story.get("id")
    if story_id:
        story_url = f"{base_url}/news/{story_id}/{slug}"
    else:
        story_url = story.get("link") or base_url

    footer = f'⚡ <a href="{base_url}">Live Market Terminal</a> | 🔗 <a href="{story_url}">Read Full Story</a>'

    # Clean description and calculate budget for max 950 total caption chars
    raw_desc = (story.get("description") or "").strip()
    clean_desc = re.sub(r'<[^>]+>', '', raw_desc)
    clean_desc = re.sub(r'[\r\n\t]+', ' ', clean_desc)
    clean_desc = re.sub(r'\s+', ' ', clean_desc).strip()

    fixed_len = len(badge_header) + 4 + len(escaped_title) + 11 + 4 + len(footer)
    max_desc_len = max(100, 930 - fixed_len)

    if len(clean_desc) > max_desc_len:
        clean_desc = clean_desc[:max_desc_len - 3] + "..."

    escaped_summary = html.escape(clean_desc)

    caption = f"{badge_header}\n\n📰 <b>{escaped_title}</b>\n\n{escaped_summary}\n\n{footer}"
    return caption


def send_telegram_photo(image_path: str, caption: str) -> bool:
    """Sends the generated photo with HTML caption to Telegram channel."""
    token, channel_id = get_telegram_credentials()
    if not token or not channel_id:
        logger.warning("Telegram Bot Token or Channel ID is missing. Skipping Telegram broadcast.")
        return False

    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    try:
        with open(image_path, "rb") as photo_file:
            data = {
                "chat_id": channel_id,
                "caption": caption,
                "parse_mode": "HTML"
            }
            files = {
                "photo": photo_file
            }
            resp = requests.post(url, data=data, files=files, timeout=25)
            if resp.status_code == 200:
                logger.info(f"Telegram photo alert successfully broadcasted to {channel_id}")
                return True
            else:
                logger.error(f"Telegram API response ({resp.status_code}): {resp.text}")
                return False
    except Exception as e:
        logger.error(f"Exception sending photo to Telegram: {e}")
        return False


def load_sent_records() -> set:
    """Loads previously sent story IDs/links from persistent JSON file."""
    if not os.path.exists(SENT_FILE):
        return set()
    try:
        with open(SENT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return set(str(x) for x in data)
    except Exception as e:
        logger.warning(f"Error loading telegram_sent.json: {e}")
    return set()


def save_sent_records(records: set):
    """Saves up to the latest 2,000 sent records atomically."""
    try:
        as_list = list(records)[-2000:]
        temp_file = SENT_FILE + ".tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(as_list, f)
        if os.path.exists(temp_file):
            os.replace(temp_file, SENT_FILE)
    except Exception as e:
        logger.error(f"Error saving telegram_sent.json: {e}")


def init_first_boot_guard():
    """
    CRITICAL FIRST-BOOT GUARD:
    If telegram_sent.json does not exist yet (or is empty), seed it with all existing
    important stories in the database WITHOUT sending any messages to Telegram.
    """
    if not os.path.exists(SENT_FILE) or os.path.getsize(SENT_FILE) == 0:
        logger.info("Initializing Telegram First-Boot Guard (preventing backlog spam)...")
        try:
            from database import get_articles
            existing = get_articles(article_type="important", limit=2000)
            records = set()
            for art in existing:
                rec_id = str(art.get("id") or art.get("link"))
                if rec_id:
                    records.add(rec_id)
            save_sent_records(records)
            logger.info(f"Telegram First-Boot Guard active: {len(records)} existing stories marked as sent.")
        except Exception as e:
            logger.warning(f"Could not initialize first-boot guard from database: {e}")


def process_and_publish_new_stories(limit: int = 15) -> int:
    """
    Scans for newly arriving 'important' stories not yet published to Telegram,
    generates cards, and broadcasts them with a 3-second delay between posts.
    """
    token, channel_id = get_telegram_credentials()
    if not token or not channel_id:
        return 0

    init_first_boot_guard()
    sent_records = load_sent_records()

    try:
        from database import get_articles
        recent_important = get_articles(article_type="important", limit=limit)
    except Exception as e:
        logger.error(f"Error querying articles for Telegram publish: {e}")
        return 0

    # Filter to articles not yet sent
    pending = []
    for art in recent_important:
        rec_id = str(art.get("id") or art.get("link"))
        if rec_id and rec_id not in sent_records:
            pending.append(art)

    if not pending:
        return 0

    # Publish oldest pending first so chronology is preserved
    pending.reverse()
    published_count = 0

    for story in pending:
        rec_id = str(story.get("id") or story.get("link"))
        image_path = None
        try:
            logger.info(f"Generating Telegram breaking card for story #{story.get('id')}: {story.get('title')[:60]}...")
            image_path = generate_telegram_card(story)
            caption = build_telegram_caption(story)

            success = send_telegram_photo(image_path, caption)
            if success:
                sent_records.add(rec_id)
                save_sent_records(sent_records)
                published_count += 1
                logger.info(f"Successfully posted breaking card to Telegram for #{story.get('id')}")
                # 3-second rate limit between posts
                time.sleep(3)
            else:
                logger.warning(f"Failed to post story #{story.get('id')} to Telegram.")
        except Exception as err:
            logger.error(f"Error processing story for Telegram: {err}")
        finally:
            if image_path and os.path.exists(image_path):
                try:
                    os.remove(image_path)
                except Exception:
                    pass

    return published_count


def test_telegram_alert() -> Dict[str, Any]:
    """
    Generates and sends 1 sample card using the latest important story
    (or a mock story if empty) to verify the Telegram integration immediately.
    """
    token, channel_id = get_telegram_credentials()
    if not token or not channel_id:
        return {
            "status": "error",
            "message": "TELEGRAM_BOT_TOKEN or TELEGRAM_CHANNEL_ID is not configured."
        }

    sample_story = None
    try:
        from database import get_articles
        important = get_articles(article_type="important", limit=1)
        if important:
            sample_story = important[0]
    except Exception:
        pass

    if not sample_story:
        sample_story = {
            "id": 999999,
            "title": "Nifty 50 Hits Record High as Foreign Institutional Investors Inflow Surges",
            "source": "ZeroLive Terminal Wire",
            "description": "Benchmark indices registered historic highs today with strong buying in banking, auto, and technology heavyweights amid favorable global economic tailwinds.",
            "sentiment": "BULLISH",
            "link": "https://www.zerolive.in/"
        }

    image_path = None
    try:
        image_path = generate_telegram_card(sample_story)
        caption = build_telegram_caption(sample_story)
        success = send_telegram_photo(image_path, caption)
        if success:
            return {
                "status": "success",
                "message": f"Test alert successfully delivered to {channel_id}!",
                "story_title": sample_story.get("title")
            }
        else:
            return {
                "status": "error",
                "message": "Telegram API rejected the sendPhoto request. Check server logs."
            }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Exception during test Telegram send: {e}"
        }
    finally:
        if image_path and os.path.exists(image_path):
            try:
                os.remove(image_path)
            except Exception:
                pass
