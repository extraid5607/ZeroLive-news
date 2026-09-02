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

def broadcast_news_alerts(articles: Optional[List[Dict[str, Any]]] = None) -> int:
    """
    Broadcasts a push notification to all subscribers ONLY when a BRAND NEW article
    arrives in the 'important' news section.

    Guarantees:
    - Never sends repeat notifications on the same news.
    - Sends exactly one alert per newly arrived important news item.
    - Directs the user to the installed PWA app (/?tab=important) instead of an external browser.
    """
    from database import get_unpushed_important_article, mark_article_as_pushed

    # 1. Check if there is a newly arrived important article that has not been pushed yet
    art = get_unpushed_important_article()
    if not art:
        # No new important news -> send NOTHING
        return 0

    subscriptions = get_all_subscriptions()
    if not subscriptions:
        # Mark as pushed so we don't accumulate backlog when no users are subscribed
        mark_article_as_pushed(art["id"])
        return 0

    art_title = art.get("title", "").strip()
    art_source = art.get("source", "").strip()
    art_id = art.get("id")

    # The URL MUST stay within the PWA scope so the OS opens the installed app
    pwa_url = f"/?tab=important&story={art_id}"

    payload = {
        "title": f"⚡ {art_source or 'ZeroLive'} Breaking Alert",
        "body": art_title,
        "url": pwa_url,
        "tag": f"zerolive-important-{art_id}",
        "icon": "/icons/icon-192.png",
        "badge": "/icons/icon-192.png"
    }

    sent_count = 0
    for sub in subscriptions:
        if send_web_push(sub, payload):
            sent_count += 1

    # Mark as pushed immediately so this article will NEVER be sent again
    mark_article_as_pushed(art_id)

    logger.info(f"Pushed breaking alert for [{art_title[:50]}] to {sent_count}/{len(subscriptions)} devices.")
    return sent_count

