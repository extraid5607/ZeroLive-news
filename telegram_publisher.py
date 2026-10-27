import os
import re
import time
import json
import html
import logging
import threading
from typing import Dict, Any, List, Optional, Tuple, Set
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

# Concurrency & Deduplication Guards
_PUBLISH_LOCK = threading.Lock()
_SENT_IDS: Set[str] = set()
_SENT_TITLES: Set[str] = set()

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

# Comprehensive Pattern for Financial Results / Earnings
EARNINGS_RESULTS_PATTERN = re.compile(
    r'\b('
    r'financial\s+results?|quarterly\s+results?|un-?audited\s+(?:financial\s+)?results?|'
    r'audited\s+(?:financial\s+)?results?|results\s+for\s+the\s+quarter|'
    r'outcome\s+of\s+board\s+meeting.*(?:financial\s+results|results)|'
    r'statement\s+of\s+(?:un-?audited|audited)\s+financial\s+results?|'
    r'standalone\s+and\s+consolidated\s+financial\s+results?|'
    r'q[1-4]\s*(?:fy\d{2,4})?\s*(?:financial\s+)?(?:results?|earnings?|net\s*profit|profit|loss|pat|numbers?|revenue|ebitda)|'
    r'(?:net\s*profit|net\s*loss|pat)\s*(?:surges?|jumps?|rises?|falls?|drops?|slips?|up|down|declines?|grows?|soars?|dips?)|'
    r'(?:reports?|posts?|clocks?|records?)\s*(?:net\s*profit|net\s*loss|q[1-4]|earnings?)|'
    r'quarterly\s+(?:net\s*)?(?:profit|loss|earnings?)|'
    r'earnings\s+(?:season|preview|review|report|release|beat|miss|call)|'
    r'(?:q[1-4]|quarterly)\s+performance|'
    r'dividend\s+(?:declaration|declared|recommendation)|interim\s+dividend|final\s+dividend'
    r')\b',
    re.IGNORECASE
)

# Routine Corporate Filings Exclusions (to filter out compliance spam from Telegram)
ROUTINE_FILING_EXCLUSIONS = re.compile(
    r'\b('
    r'analysts?[/\s]*institutional\s+investor\s+meet|'
    r'newspaper\s+publication|copy\s+of\s+newspaper|'
    r'shareholders?\s+meeting|postal\s+ballot|'
    r'loss\s+of\s+share\s+certificates?|duplicate\s+share\s+certificate|'
    r'trading\s+window|closure\s+of\s+trading\s+window|'
    r'clarification\s+on\s+price|regulation\s+30|'
    r'prior\s+intimation\s+of\s+board\s+meeting|'
    r'board\s+meeting\s+intimation(?!.*results)|'
    r'intimation\s+of\s+schedule|'
    r'updates\s+-\s+|'
    r'structural\s+digital\s+database'
    r')\b',
    re.IGNORECASE
)

def is_earnings_news(title: str, description: str = "") -> bool:
    """Checks if a story is a financial results or quarterly earnings report."""
    text = f"{title} {description}".strip()
    return bool(EARNINGS_RESULTS_PATTERN.search(text))

def is_routine_filing(title: str) -> bool:
    """Checks if a corporate filing is routine non-result paperwork."""
    return bool(ROUTINE_FILING_EXCLUSIONS.search(title))

def should_publish_to_telegram(story: Dict[str, Any]) -> bool:
    """
    OPTION 2 FILTER + EVERY EARNINGS NEWS:
    1. Important News (crashes, surges, RBI/Fed policies, IPOs, macro).
    2. Every Earnings News (quarterly results, Q1-Q4 net profit/loss, revenue, dividend announcements).
    3. From NSE/BSE: STRICTLY Financial Results / Earnings ONLY (routine filings excluded).
    """
    title = (story.get("title") or "").strip()
    desc = (story.get("description") or "").strip()
    src = (story.get("source") or "").lower()
    feed = (story.get("feed_name") or "").lower()
    link = (story.get("link") or "").lower()
    art_type = (story.get("type") or "general").lower()

    is_exchange = ("nse" in src or "bse" in src or "exchange" in src or "bseindia" in link or "nseindia" in link)
    is_routine = is_routine_filing(title)
    is_earn = is_earnings_news(title, desc)

    # 1. Exchange filings: strictly ONLY Financial Results / Earnings allowed
    if is_exchange:
        return is_earn and not is_routine

    # 2. Media news: Allow if it's an Earnings / Results story
    if is_earn and not is_routine:
        return True

    # 3. Media news: Allow if classified as 'important'
    if art_type == "important" and not is_routine:
        return True

    return False

# Default built-in credentials for ZeroLive Telegram Channel
DEFAULT_BOT_TOKEN = "8846942797:AAHsRl9jPAYoRaVGhTt5RG6EODVqunJW-NE"
DEFAULT_CHANNEL_ID = "@Zerolive_news"

_CREDENTIALS_WARNED = False

def get_telegram_credentials() -> Tuple[Optional[str], Optional[str]]:
    """
    Retrieves TELEGRAM_BOT_TOKEN and normalized TELEGRAM_CHANNEL_ID.
    Checks environment variables -> .env -> Telegram.txt -> built-in defaults.
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

    # 3. Built-in defaults guarantee delivery even on fresh Render deployments
    if not token:
        token = DEFAULT_BOT_TOKEN
    if not channel_id:
        channel_id = DEFAULT_CHANNEL_ID

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


def clean_raw_text(text: str) -> str:
    """Removes HTML tags, decodes HTML entities (&nbsp;, &amp;, etc.), and normalizes whitespace."""
    if not text:
        return ""
    clean = html.unescape(text)
    clean = re.sub(r'<[^>]+>', ' ', clean)
    clean = clean.replace('\xa0', ' ').replace('&nbsp;', ' ')
    clean = re.sub(r'[\r\n\t]+', ' ', clean)
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean


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
    art_type = (story.get("type") or "general").lower()
    source_lower = (story.get("source") or "").lower()
    is_earn = is_earnings_news(story.get("title", ""), story.get("description", ""))

    if is_earn:
        if sentiment == "BULLISH":
            badge_bg = (11, 61, 32)      # #0b3d20
            badge_border = (34, 197, 94)  # #22c55e
            badge_text = "Q-RESULTS ↑"
            dot_color = (34, 197, 94)
        elif sentiment == "BEARISH":
            badge_bg = (69, 18, 21)      # #451215
            badge_border = (239, 68, 68)  # #ef4444
            badge_text = "Q-RESULTS ↓"
            dot_color = (239, 68, 68)
        else:
            badge_bg = (14, 42, 71)      # deep corporate blue
            badge_border = (56, 189, 248) # #38bdf8 cyan
            badge_text = "Q-RESULTS"
            dot_color = (56, 189, 248)
    elif sentiment == "BULLISH":
        badge_bg = (11, 61, 32)      # #0b3d20
        badge_border = (34, 197, 94)  # #22c55e
        badge_text = "BULLISH ↑"
        dot_color = (34, 197, 94)
    elif sentiment == "BEARISH":
        badge_bg = (69, 18, 21)      # #451215
        badge_border = (239, 68, 68)  # #ef4444
        badge_text = "BEARISH ↓"
        dot_color = (239, 68, 68)
    elif art_type == "filing" or "nse" in source_lower or "bse" in source_lower:
        badge_bg = (20, 35, 60)      # #14233c
        badge_border = (56, 189, 248) # #38bdf8 cyan/blue
        badge_text = "CORP FILING"
        dot_color = (56, 189, 248)
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
    if is_earn:
        wire_tag = "📊 FINANCIAL RESULTS WIRE"
    else:
        wire_tag = "⚡ BREAKING MARKET WIRE"
    tag_text = f"{wire_tag}  •  #{ticker}" if ticker else wire_tag
    font_tag = get_font(19, bold=True)
    draw.text((50, 120), tag_text, font=font_tag, fill=(245, 158, 11))

    # 5b. Headline with Dynamic Font Scaling (44px down to 34px, max 3 lines)
    clean_title = clean_raw_text(story.get("title") or "Market Breaking Update")

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
    clean_desc = clean_raw_text(story.get("description") or "")

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
            draw.text((50, curr_y), s_line, font=font_summary, fill=(226, 232, 240))
            curr_y += sum_line_height

    # 6. Bottom Footer Bar
    # Thin Horizontal Divider at y = 600
    draw.line([(50, 600), (width - 50, 600)], fill=(0, 240, 255), width=2)

    # 6a. Bottom-Left Source
    source = clean_raw_text(story.get("source") or story.get("feed_name") or "ZeroLive Wire")
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


def build_telegram_message(story: Dict[str, Any], base_url: str = "https://www.zerolive.in") -> str:
    """
    Constructs an ultra-clean, minimal, clutter-free Telegram text message.
    Highlights the primary headline and context without image bloat.
    """
    raw_title = clean_raw_text(story.get("title") or "Market Update")
    escaped_title = html.escape(raw_title)

    raw_source = clean_raw_text(story.get("source") or story.get("feed_name") or "ZeroLive Wire")
    source = html.escape(raw_source)

    sentiment = (story.get("sentiment") or "NEUTRAL").upper()
    ticker = extract_ticker(raw_title, story.get("description", ""))
    ticker_tags = f"#{ticker}" if ticker else ""
    art_type = (story.get("type") or "general").lower()
    source_lower = raw_source.lower()
    is_earn = is_earnings_news(raw_title, story.get("description", ""))

    if is_earn:
        if sentiment == "BULLISH":
            badge_header = f"📊 <b>FINANCIAL RESULTS (BULLISH ↑)</b> | <b>{source}</b>"
        elif sentiment == "BEARISH":
            badge_header = f"📊 <b>FINANCIAL RESULTS (BEARISH ↓)</b> | <b>{source}</b>"
        else:
            badge_header = f"📊 <b>FINANCIAL RESULTS</b> | <b>{source}</b>"
    elif sentiment == "BULLISH":
        badge_header = f"🟢 <b>BULLISH</b> | <b>{source}</b>"
    elif sentiment == "BEARISH":
        badge_header = f"🔴 <b>BEARISH</b> | <b>{source}</b>"
    elif art_type == "filing" or "nse" in source_lower or "bse" in source_lower:
        badge_header = f"🏛️ <b>CORPORATE FILING</b> | <b>{source}</b>"
    else:
        badge_header = f"⚡ <b>BREAKING NEWS</b> | <b>{source}</b>"

    if ticker_tags:
        badge_header += f" {ticker_tags}"

    # Summary/Context - extracted cleanly
    raw_desc = clean_raw_text(story.get("description") or "")
    desc_section = ""
    # Avoid duplicate text if summary is the same as title
    if raw_desc and raw_desc.strip().lower() != raw_title.strip().lower():
        # Keep it concise (up to 300 chars)
        if len(raw_desc) > 300:
            raw_desc = raw_desc[:297].rstrip() + "..."
        desc_section = f"\n\n{html.escape(raw_desc)}"

    # Generate canonical story URL
    slug = re.sub(r'[^a-z0-9]+', '-', raw_title.lower()).strip('-')[:80]
    story_id = story.get("id")
    if story_id:
        story_url = f"{base_url}/news/{story_id}/{slug}"
    else:
        story_url = story.get("link") or base_url

    # Clean, uncluttered, professional text message:
    # Headline & News context on TOP, Category Badge & Terminal link at the BOTTOM
    message = (
        f"📰 <b>{escaped_title}</b>"
        f"{desc_section}\n\n"
        f"{badge_header}\n"
        f'⚡ <a href="{story_url}"><b>Read Full Story on ZeroLive Terminal ↗</b></a>'
    )
    return message


# Alias for backward compatibility
build_telegram_caption = build_telegram_message


def send_telegram_message(text: str, disable_web_page_preview: bool = True) -> bool:
    """Sends a clean text message to the Telegram channel using sendMessage without image."""
    token, channel_id = get_telegram_credentials()
    if not token or not channel_id:
        logger.warning("Telegram Bot Token or Channel ID is missing. Skipping Telegram broadcast.")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": channel_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": disable_web_page_preview,
        "link_preview_options": {"is_disabled": disable_web_page_preview}
    }
    try:
        resp = requests.post(url, json=payload, timeout=20)
        if resp.status_code == 200:
            logger.info(f"Telegram text alert successfully broadcasted to {channel_id}")
            return True
        else:
            logger.error(f"Telegram sendMessage API error ({resp.status_code}): {resp.text}")
            return False
    except Exception as e:
        logger.error(f"Exception sending text message to Telegram: {e}")
        return False


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
    Seeds persistent storage (DB + telegram_sent.json) with existing stories if empty,
    so older backlog stories are never spammed.
    """
    global _SENT_IDS, _SENT_TITLES
    from database import load_sent_telegram_records_from_db, mark_story_sent_to_telegram, normalize_title_hash
    db_ids, db_titles = load_sent_telegram_records_from_db()
    file_records = load_sent_records()

    if not db_ids and not file_records:
        logger.info("Initializing Telegram First-Boot Guard (preventing backlog spam)...")
        try:
            from database import get_articles
            all_existing = get_articles(limit=2000)
            # Seed older stories (leave newest 2 unsent so channel gets live cards right away)
            to_seed = all_existing[2:] if len(all_existing) > 2 else []
            for art in to_seed:
                rec_id = str(art.get("id") or art.get("link"))
                title = art.get("title") or ""
                if rec_id:
                    _SENT_IDS.add(rec_id)
                    mark_story_sent_to_telegram(rec_id, title)
                t_hash = normalize_title_hash(title)
                if t_hash:
                    _SENT_TITLES.add(t_hash)
            save_sent_records(_SENT_IDS)
            logger.info(f"Telegram First-Boot Guard active: {len(_SENT_IDS)} existing stories marked as sent.")
        except Exception as e:
            logger.warning(f"Could not initialize first-boot guard from database: {e}")
    else:
        _SENT_IDS.update(db_ids)
        _SENT_IDS.update(file_records)
        _SENT_TITLES.update(db_titles)


def process_and_publish_new_stories(limit: int = 15) -> int:
    """
    Scans for newly arriving stories not yet published to Telegram,
    generates cards, and broadcasts them with atomic locking and strict multi-layer deduplication.
    """
    global _PUBLISH_LOCK, _SENT_IDS, _SENT_TITLES

    # 1. Non-blocking Lock: Strictly enforce only ONE worker publishes at any time!
    if not _PUBLISH_LOCK.acquire(blocking=False):
        logger.info("Telegram publisher is already actively running in another thread. Skipping concurrent execution.")
        return 0

    try:
        token, channel_id = get_telegram_credentials()
        if not token or not channel_id:
            return 0

        init_first_boot_guard()

        from database import (
            get_articles,
            is_story_sent_to_telegram,
            mark_story_sent_to_telegram,
            load_sent_telegram_records_from_db,
            normalize_title_hash
        )

        # Refresh sent cache from DB & JSON
        db_ids, db_titles = load_sent_telegram_records_from_db()
        file_ids = load_sent_records()
        _SENT_IDS.update(db_ids)
        _SENT_IDS.update(file_ids)
        _SENT_TITLES.update(db_titles)

        try:
            recent_articles = get_articles(limit=limit)
        except Exception as e:
            logger.error(f"Error querying articles for Telegram publish: {e}")
            return 0

        pending = []
        for art in recent_articles:
            rec_id = str(art.get("id") or art.get("link"))
            rec_link = str(art.get("link") or "").strip()
            title = (art.get("title") or "").strip()
            t_hash = normalize_title_hash(title)

            # Strict Multi-Layer Deduplication:
            # Check ID, URL, or Title Hash in memory cache
            if rec_id in _SENT_IDS or (rec_link and rec_link in _SENT_IDS) or (t_hash and t_hash in _SENT_TITLES):
                continue

            # Check persistent database log
            if is_story_sent_to_telegram(rec_id, title) or (rec_link and is_story_sent_to_telegram(rec_link, title)):
                _SENT_IDS.add(rec_id)
                if rec_link:
                    _SENT_IDS.add(rec_link)
                if t_hash:
                    _SENT_TITLES.add(t_hash)
                continue

            # Check Option 2 Filter (Important + Financial Results)
            if should_publish_to_telegram(art):
                pending.append(art)
                # Immediately pre-mark in in-memory cache to prevent any race condition
                _SENT_IDS.add(rec_id)
                if rec_link:
                    _SENT_IDS.add(rec_link)
                if t_hash:
                    _SENT_TITLES.add(t_hash)
            else:
                # Mark routine filings and unimpactful news so we don't re-check repeatedly
                _SENT_IDS.add(rec_id)
                if rec_link:
                    _SENT_IDS.add(rec_link)
                if t_hash:
                    _SENT_TITLES.add(t_hash)
                mark_story_sent_to_telegram(rec_id, title)

        if not pending:
            save_sent_records(_SENT_IDS)
            return 0

        # Publish oldest pending first so chronological order is preserved
        pending.reverse()
        published_count = 0

        for story in pending:
            rec_id = str(story.get("id") or story.get("link"))
            rec_link = str(story.get("link") or "").strip()
            title = (story.get("title") or "").strip()
            t_hash = normalize_title_hash(title)
            try:
                logger.info(f"Publishing Telegram text alert for story #{story.get('id')}: {title[:60]}...")
                message_text = build_telegram_message(story)
                success = send_telegram_message(message_text, disable_web_page_preview=True)
                if success:
                    published_count += 1
                    # Persist to both database AND json file
                    mark_story_sent_to_telegram(rec_id, title)
                    if rec_link and rec_link != rec_id:
                        mark_story_sent_to_telegram(rec_link, title)
                    _SENT_IDS.add(rec_id)
                    if rec_link:
                        _SENT_IDS.add(rec_link)
                    if t_hash:
                        _SENT_TITLES.add(t_hash)
                    save_sent_records(_SENT_IDS)
                    logger.info(f"Successfully posted text alert to Telegram for #{story.get('id')}")
                    time.sleep(2)
                else:
                    logger.warning(f"Failed to post text alert for story #{story.get('id')} to Telegram.")
            except Exception as err:
                logger.error(f"Error processing story for Telegram: {err}")

        return published_count
    finally:
        _PUBLISH_LOCK.release()


def test_telegram_alert() -> Dict[str, Any]:
    """
    Sends 1 sample text alert using the latest important story
    (or a mock story if empty) to verify the Telegram integration immediately without images.
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

    try:
        message_text = build_telegram_message(sample_story)
        success = send_telegram_message(message_text, disable_web_page_preview=True)
        if success:
            return {
                "status": "success",
                "message": f"Test text alert successfully delivered to {channel_id}!",
                "story_title": sample_story.get("title")
            }
        else:
            return {
                "status": "error",
                "message": "Telegram API rejected the sendMessage request. Check server logs."
            }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Exception during test Telegram send: {e}"
        }
