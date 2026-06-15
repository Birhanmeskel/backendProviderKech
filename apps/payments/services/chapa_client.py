"""Low-level Chapa HTTP client — no business rules."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from django.conf import settings

logger = logging.getLogger("kech.payments.chapa")

CHAPA_API_BASE = "https://api.chapa.co/v1"
DEFAULT_TIMEOUT_SECONDS = 30


class ChapaClientError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None, payload: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.payload = payload


@dataclass(frozen=True)
class ChapaInitializeResult:
    checkout_url: str
    raw: dict[str, Any]


@dataclass(frozen=True)
class ChapaVerifyResult:
    status: str
    amount: str | None
    currency: str | None
    chapa_reference: str | None
    payment_method: str | None
    raw: dict[str, Any]


def _secret_key() -> str:
    key = getattr(settings, "CHAPA_SECRET_KEY", "") or ""
    if not key and not getattr(settings, "CHAPA_MOCK_MODE", False):
        raise ChapaClientError("CHAPA_SECRET_KEY is not configured.")
    return key


def _request(
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if getattr(settings, "CHAPA_MOCK_MODE", False):
        return _mock_response(method, path, body)

    url = f"{CHAPA_API_BASE}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {_secret_key()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT_SECONDS) as resp:
            parsed = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            parsed = json.loads(exc.read().decode("utf-8"))
        except (json.JSONDecodeError, ValueError):
            parsed = {}
        message = parsed.get("message") if isinstance(parsed, dict) else str(exc)
        if isinstance(message, dict):
            parts = [
                f"{field}: {', '.join(str(item) for item in errs) if isinstance(errs, list) else errs}"
                for field, errs in message.items()
            ]
            message = "; ".join(parts) if parts else str(exc.reason)
        logger.warning("Chapa HTTP error %s %s: %s", method, path, message)
        raise ChapaClientError(str(message or exc.reason), status_code=exc.code, payload=parsed) from exc
    except urllib.error.URLError as exc:
        logger.exception("Chapa network error %s %s", method, path)
        raise ChapaClientError(f"Chapa request failed: {exc.reason}") from exc

    if not isinstance(parsed, dict):
        raise ChapaClientError("Unexpected Chapa response shape.")
    return parsed


def initialize_transaction(
    *,
    amount: str,
    currency: str,
    email: str,
    first_name: str,
    last_name: str,
    phone_number: str,
    tx_ref: str,
    callback_url: str,
    return_url: str,
    customization: dict[str, str] | None = None,
    meta: dict[str, Any] | None = None,
) -> ChapaInitializeResult:
    payload: dict[str, Any] = {
        "amount": amount,
        "currency": currency,
        "email": email,
        "first_name": first_name,
        "last_name": last_name,
        "phone_number": phone_number,
        "tx_ref": tx_ref,
        "callback_url": callback_url,
        "return_url": return_url,
    }
    if customization:
        payload["customization"] = customization
    if meta:
        payload["meta"] = meta

    response = _request("POST", "/transaction/initialize", body=payload)
    if response.get("status") != "success":
        raise ChapaClientError(
            str(response.get("message") or "Chapa initialize failed."),
            payload=response,
        )
    data = response.get("data") or {}
    checkout_url = data.get("checkout_url")
    if not checkout_url:
        raise ChapaClientError("Chapa did not return checkout_url.", payload=response)
    return ChapaInitializeResult(checkout_url=str(checkout_url), raw=response)


def verify_transaction(tx_ref: str) -> ChapaVerifyResult:
    response = _request("GET", f"/transaction/verify/{tx_ref}")
    if response.get("status") != "success":
        raise ChapaClientError(
            str(response.get("message") or "Chapa verify failed."),
            payload=response,
        )
    data = response.get("data") or {}
    return ChapaVerifyResult(
        status=str(data.get("status") or "").lower(),
        amount=str(data.get("amount")) if data.get("amount") is not None else None,
        currency=str(data.get("currency") or "") or None,
        chapa_reference=str(data.get("reference") or data.get("chapa_reference") or "") or None,
        payment_method=str(data.get("payment_method") or "") or None,
        raw=response,
    )


def _mock_checkout_page_url(tx_ref: str) -> str:
    """Hosted mock checkout page (real URL loads in WebView; fake chapa.co/mock/* does not)."""
    from urllib.parse import quote

    base = getattr(settings, "CHAPA_PUBLIC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    return f"{base}/api/v1/payments/mock-checkout/?tx_ref={quote(str(tx_ref))}"


def _mock_response(method: str, path: str, body: dict[str, Any] | None) -> dict[str, Any]:
    if method == "POST" and path == "/transaction/initialize":
        tx_ref = (body or {}).get("tx_ref", "mock-tx")
        return {
            "status": "success",
            "message": "mock",
            "data": {"checkout_url": _mock_checkout_page_url(tx_ref)},
        }
    if method == "GET" and path.startswith("/transaction/verify/"):
        tx_ref = path.rsplit("/", 1)[-1]
        return {
            "status": "success",
            "data": {
                "status": "success",
                "amount": "100.00",
                "currency": "ETB",
                "reference": f"MOCK-{tx_ref}",
                "payment_method": "test",
                "tx_ref": tx_ref,
            },
        }
    raise ChapaClientError(f"Unhandled mock Chapa path {method} {path}")
