#-------------------------------------------------
# Nomba API Client for PayCycle
# Handles:
# - OAuth2 token issuance + caching (refresh at 55-min mark)
#  - Checkout session creation
#  - Tokenized card charging
#  - Webhook signature verification
#All amounts passed INTO this client are in Naira (float).
#This client converts to kobo internally before sending to Nomba.
#All amounts coming OUT are in Naira.
#-------------------------------------------------

import hmac
import hashlib
import time
import logging
import uuid
from typing import Optional
import httpx
from core.config import settings
import utils

logger = logging.getLogger("paycycle.nomba")
#-------------------------------------------------
#Token cache - one token shared across all requests. 
# refreshed at 55-min mark. Nomba tokens expire after 60 minutes.
#-------------------------------------------------------

class _TokenCache:
    def __init__(self):
        self._token: Optional[str] = None
        self._expires_at: float = 0 #unix timestamp


    def is_valid(self) -> bool:
        #Treat token as expired 5 minutes early
        return self._token is not None and time.time() < self._expires_at

    def set(self, token: str, expires_in: int = 3600):
        self._token = token
        # Expire 5 minutes early to avoid edge cases
        self._expires_at = time.time() + expires_in - 300
 
    def get(self) -> Optional[str]:
        return self._token if self.is_valid() else None
 
 
_cache = _TokenCache()
 
 
# ---------------------------------------------------------------------------
# Nomba Client
# ---------------------------------------------------------------------------
class NombaClient:
    """
    Singleton-style Nomba API wrapper.
    Import and call directly — token management is handled internally.
 
    Usage:
        from services.nomba_client import nomba
 
        checkout = await nomba.create_checkout(
            amount=15000.0,
            customer_email="student@example.com",
            subscription_id="sub_abc123",
            callback_url="https://yourapp.com/payment/return"
        )
        print(checkout["checkoutUrl"])
    """
 
    def __init__(self):
        self.base_url = settings.NOMBA_BASE_URL.rstrip("/")
        self.account_id = settings.NOMBA_ACCOUNT_ID
        self.client_id = settings.NOMBA_CLIENT_ID
        self.client_secret = settings.NOMBA_CLIENT_SECRET
        self.webhook_secret = settings.NOMBA_WEBHOOK_SECRET
 
    # ------------------------------------------------------------------
    # Internal: get a valid token, fetching a new one if needed
    # ------------------------------------------------------------------
    async def _get_token(self) -> str:
        cached = _cache.get()
        if cached:
            return cached
 
        logger.info("nomba_auth | requesting new access token")
 
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/v1/auth/token/issue",
                headers={
                    "Content-Type": "application/json",
                    "accountId": self.account_id,
                },
                json={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
                timeout=10.0,
            )
 
        if response.status_code != 200:
            logger.error(f"nomba_auth | failed: {response.text}")
            raise Exception(f"Nomba auth failed: {response.status_code} {response.text}")
 
        data = response.json()
        token = data["data"]["access_token"]
        expires_in = data["data"].get("expires_in", 3600)
 
        _cache.set(token, expires_in)
        logger.info("nomba_auth | token cached successfully")
        return token
 
    # ------------------------------------------------------------------
    # Internal: make an authenticated request
    # ------------------------------------------------------------------
    async def _request(self, method: str, path: str, **kwargs) -> dict:
        token = await self._get_token()
 
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "accountId": self.account_id,
        }
 
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method,
                f"{self.base_url}/v1{path}",
                headers=headers,
                timeout=15.0,
                **kwargs,
            )
 
        logger.info(
            f"nomba_request | {method} {path} → {response.status_code}",
            extra={"path": path, "status": response.status_code},
        )
 
        if response.status_code not in (200, 201):
            logger.error(f"nomba_request | error: {response.text}")
            raise Exception(f"Nomba API error: {response.status_code} {response.text}")
 
        return response.json()
 
    # ------------------------------------------------------------------
    # Create a checkout session (first-time subscriber enrollment)
    # ------------------------------------------------------------------
    async def create_checkout(
        self,
        amount: float,           # in Naira
        customer_email: str,
        subscription_id: str,    # used as orderReference — ties checkout to your DB row
        callback_url: str,
        order_ref:str,
        customer_name: Optional[str] = None,
    ) -> dict:
        """
        Creates a Nomba hosted checkout session.
 
        Returns dict with keys:
          - checkoutUrl: str  → send this to Flutter to open in WebView
          - orderReference: str
          - status: str
 
        Flow:
          1. Call this → get checkoutUrl
          2. Flutter opens checkoutUrl in WebView
          3. Customer pays, Nomba sends payment_success webhook
          4. Webhook handler extracts token_key and stores it on the Subscription
        """
        
 
        logger.info(
            f"nomba_checkout | creating session",
            extra={"subscription_id": subscription_id, "amount_naira": amount, "ref": order_ref},
        )
 
        payload = {
            "order": {
                "orderReference": order_ref,
                "amount": utils.to_kobo(amount),   # ← kobo conversion here
                "currency": "NGN",
                "callbackUrl": callback_url,
                "customerEmail": customer_email,
            }
        }
 
        if customer_name:
            payload["order"]["customerName"] = customer_name
 
        data = await self._request("POST", "/checkout/order", json=payload)
        print("NOMBA CHECKOUT RESPONSE:", data)
        return data["data"]
 
    # ------------------------------------------------------------------
    # Charge a stored tokenized card (recurring billing)
    # ------------------------------------------------------------------
    async def charge_token(
        self,
        amount: float,           # in Naira
        token_key: str,          # stored from webhook after first checkout
        nomba_customer_id: str,  # stored from webhook after first checkout
        subscription_id: str,    # used to build unique merchantTxRef
        billing_period: str,     # e.g. "2026-07" — makes ref unique per billing cycle
    ) -> dict:
        """
        Charges a previously tokenized card without customer interaction.
 
        merchantTxRef = "sub_{subscription_id}_{billing_period}"
        This is idempotent — retrying with the same ref won't double-charge.
 
        Returns dict with charge result.
        Raises Exception on failure — caller should catch and update
        subscription status to 'failed'.
        """
        # Unique per subscription + billing period = idempotent retries
        merchant_tx_ref = f"sub_{subscription_id}_{billing_period}"
 
        logger.info(
            f"nomba_charge | charging token",
            extra={
                "subscription_id": subscription_id,
                "amount_naira": amount,
                "merchant_tx_ref": merchant_tx_ref,
            },
        )
 
        data = await self._request(
            "POST",
            "/tokenized-card/charge",
            json={
                "amount": utils.to_kobo(amount),   # ← kobo conversion here
                "currency": "NGN",
                "cardId": token_key,
                "customerId": nomba_customer_id,
                "merchantTxRef": merchant_tx_ref,
            },
        )
        return data["data"]
 
    # ------------------------------------------------------------------
    # Verify a webhook signature (call this FIRST in your webhook handler)
    # ------------------------------------------------------------------
    def verify_webhook(self, raw_body: bytes, signature_header: str) -> bool:
        """
        Verifies the nomba-signature HMAC-SHA256 signature.
 
        IMPORTANT: Pass raw request bytes, NOT parsed JSON.
        FastAPI usage:
            raw_body = await request.body()
            sig = request.headers.get("nomba-signature", "")
            if not nomba.verify_webhook(raw_body, sig):
                raise HTTPException(status_code=401)
 
        Returns True if valid, False if signature doesn't match.
        """
        expected = hmac.new(
            self.webhook_secret.encode(),
            raw_body,
            hashlib.sha256,
        ).hexdigest()
 
        is_valid = hmac.compare_digest(expected, signature_header)
 
        if not is_valid:
            logger.warning("nomba_webhook | signature verification FAILED")
 
        return is_valid
 
 
# ---------------------------------------------------------------------------
# Singleton instance — import this everywhere
# ---------------------------------------------------------------------------
nomba = NombaClient()
 