import json
import logging
import os
from typing import Any, Dict

from src.autonomy_store import delete_push_subscription, list_push_subscriptions

logger = logging.getLogger(__name__)


def public_vapid_key() -> str | None:
    return os.getenv("VAPID_PUBLIC_KEY")


def send_push_notification(title: str, message: str, event_type: str) -> None:
    private_key = os.getenv("VAPID_PRIVATE_KEY")
    subject = os.getenv("VAPID_CLAIMS_EMAIL")
    if not private_key or not subject:
        logger.info("Push notification not sent: VAPID credentials are not configured")
        return

    try:
        subscriptions = list_push_subscriptions()
        if not subscriptions:
            return
        from pywebpush import WebPushException, webpush
    except Exception:
        logger.exception("Could not prepare push notification delivery")
        return

    payload: Dict[str, Any] = {
        "title": title,
        "body": message,
        "tag": event_type,
        "url": "/",
    }
    for subscription in subscriptions:
        try:
            webpush(
                subscription_info=subscription,
                data=json.dumps(payload),
                vapid_private_key=private_key,
                vapid_claims={"sub": subject},
            )
        except WebPushException as exc:
            response = getattr(exc, "response", None)
            status_code = getattr(response, "status_code", None)
            if status_code in (404, 410):
                try:
                    delete_push_subscription(subscription["endpoint"])
                except Exception:
                    logger.exception("Could not remove expired push subscription")
            else:
                logger.exception("Push notification delivery failed")
        except Exception:
            logger.exception("Push notification delivery failed")
