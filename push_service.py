import os
import json
import logging
from typing import List, Dict, Any, Optional
from pywebpush import webpush, WebPushException

from database import get_all_subscriptions, delete_subscription

logger = logging.getLogger("push_service")

DEFAULT_VAPID_PUBLIC = "BGi9y17K6RN_A_3km5pV092KDHR9OG0Y1-B0afuj_05zG3anaa9mtuwi2uwy8TU8JVVixowcMOIOdknguPiYvJI"
DEFAULT_VAPID_PRIVATE = "M3CIIH4Fy8mc3h44mCLQ_ky2b23bxfX7nT54PGdjBGQ"

def get_vapid_keys() -> Dict[str, str]:
    """Retrieves VAPID keys from environment, vapid_keys.json, or built-in defaults."""
    pub = os.environ.get("VAPID_PUBLIC_KEY")
    priv = os.environ.get("VAPID_PRIVATE_KEY")
    if pub and priv:
        return {"publicKey": pub, "privateKey": priv}

    key_path = os.path.join(os.path.dirname(__file__), "vapid_keys.json")
    if os.path.exists(key_path):
        try:
            with open(key_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data.get("publicKey") and data.get("privateKey"):
                    return data
        except Exception as e:
            logger.error(f"Error reading vapid_keys.json: {e}")

    return {
        "publicKey": DEFAULT_VAPID_PUBLIC,
        "privateKey": DEFAULT_VAPID_PRIVATE
    }

def send_web_push(subscription: Dict[str, Any], payload: Dict[str, Any]) -> bool:
    """Sends a Web Push notification to a single subscriber."""
    keys = get_vapid_keys()
    if not keys.get("privateKey"):
        logger.warning("Cannot send Web Push: VAPID private key is missing.")
        return False

    vapid_claims = {
        "sub": os.environ.get("VAPID_SUBJECT", "mailto:Harjinder1070@gmail.com")
    }

    try:
        webpush(
            subscription_info=subscription,
            data=json.dumps(payload),
            vapid_private_key=keys["privateKey"],
            vapid_claims=vapid_claims
        )
        return True
    except WebPushException as ex:
        logger.warning(f"WebPushException: {ex}")
        status_code = getattr(ex.response, 'status_code', None) if hasattr(ex, 'response') else None
        if status_code in [404, 410]:
            endpoint = subscription.get("endpoint")
            if endpoint:
                logger.info(f"Removing expired subscription (HTTP {status_code}): {endpoint[:40]}...")
                delete_subscription(endpoint)
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending push: {e}")
        return False

def broadcast_news_alerts(articles: List[Dict[str, Any]]) -> int:
    """Broadcasts push notification to all subscribers ONLY for articles where type == 'important'."""
    if not articles:
        return 0

    important_articles = [art for art in articles if art.get("type") == "important"]
    if not important_articles:
        return 0

    subscriptions = get_all_subscriptions()
    if not subscriptions:
        return 0

    if len(important_articles) == 1:
        art = important_articles[0]
        payload = {
            "title": "ZeroLive – Breaking Market Alert",
            "body": art.get("title", ""),
            "url": art.get("link", "https://zerolive.in/"),
            "tag": f"news-{abs(hash(art.get('title', '')))}"
        }
    else:
        top_titles = [f"• {a.get('title', '')}" for a in important_articles[:3]]
        payload = {
            "title": f"ZeroLive – {len(important_articles)} Breaking Updates",
            "body": "\n".join(top_titles),
            "url": "https://zerolive.in/",
            "tag": f"news-batch-{len(important_articles)}"
        }

    sent_count = 0
    for sub in subscriptions:
        if send_web_push(sub, payload):
            sent_count += 1

    logger.info(f"Pushed alert to {sent_count}/{len(subscriptions)} subscribers for {len(important_articles)} important stories.")
    return sent_count

