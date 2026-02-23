"""
Order cancellation API client.

POST {ORDER_API_BASE_URL}/cancel  with JSON body {"order_id": "<id>"}
Authorization header: Bearer {ORDER_API_KEY}

When ORDER_API_BASE_URL is not configured (localhost default) or
ORDER_API_KEY is empty the client runs in STUB mode and returns a
successful mock response without making a real HTTP call.
"""

import requests

from config.settings import settings
from models.incident import CancelResult
from utils.logger import get_logger

log = get_logger(__name__)

_STUB_BASE = "http://localhost:9999"


class OrderAPIClient:
    def __init__(self) -> None:
        self._base = settings.order_api_base_url.rstrip("/")
        self._key = settings.order_api_key
        self._stub = (self._base == _STUB_BASE) or (not self._key)

        if self._stub:
            log.warning(
                "OrderAPIClient running in STUB mode — no real cancellation calls will be made. "
                "Set ORDER_API_BASE_URL and ORDER_API_KEY in .env to enable live mode."
            )

    def cancel_order(self, order_id: str) -> CancelResult:
        """
        Cancel an order.  Returns CancelResult with success flag and message.
        In stub mode returns a simulated success without HTTP call.
        """
        if self._stub:
            log.info("[STUB] Simulating cancellation of order '%s'", order_id)
            return CancelResult(
                success=True,
                message=f"Order {order_id} cancelled successfully (stub mode).",
            )

        url = f"{self._base}/cancel"
        headers = {
            "Authorization": f"Bearer {self._key}",
            "Content-Type": "application/json",
        }
        payload = {"order_id": order_id}

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            message = data.get("message") or f"Order {order_id} cancelled."
            log.info("Order '%s' cancelled via API. Response: %s", order_id, message)
            return CancelResult(success=True, message=message)

        except requests.HTTPError as exc:
            msg = f"HTTP error cancelling order {order_id}: {exc.response.status_code} {exc.response.text}"
            log.error(msg)
            return CancelResult(success=False, message=msg)

        except requests.RequestException as exc:
            msg = f"Network error cancelling order {order_id}: {exc}"
            log.error(msg)
            return CancelResult(success=False, message=msg)
