from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import logging

from database import get_db
from services.nomba_client import nomba
import model

logger = logging.getLogger("paycycle.webhook")

router = APIRouter(tags=["WEBHOOKS"])

@router.get("/webhooks/nomba", status_code=200)
def webhook_verification():
    """Nomba GET ping to verify endpoint is alive"""
    return {"status": "ok"}


@router.post("/webhooks/nomba", status_code=200)
async def nomba_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Receives all Nomba payment events.

    Order of operations — DO NOT change this order:
      1. Read raw body (must be before any parsing)
      2. Verify HMAC signature — reject if invalid
      3. Parse JSON
      4. Check idempotency — return 200 if already processed
      5. Route by event type
      6. Mark event as processed
    """

    # ------------------------------------------------------------------
    # STEP 1 — Read raw bytes BEFORE parsing
    # Signature verification requires the raw body exactly as received
    # ------------------------------------------------------------------
    raw_body = await request.body()

    # ------------------------------------------------------------------
    # STEP 2 — Verify HMAC-SHA256 signature
    # Reject anything that doesn't come from Nomba
    # ------------------------------------------------------------------
    signature = request.headers.get("nomba-signature", "")

    if not nomba.verify_webhook(raw_body, signature):
        logger.warning("webhook | invalid signature rejected")
        raise HTTPException(status_code=401, detail="Invalid signature")

    # ------------------------------------------------------------------
    # STEP 3 — Parse the JSON payload
    # ------------------------------------------------------------------
    payload = await request.json()

    event_type = payload.get("event")
    request_id = payload.get("requestId")    # Nomba's unique event ID
    data = payload.get("data", {})

    logger.info(
        f"webhook | received event",
        extra={"event": event_type, "request_id": request_id},
    )

    # ------------------------------------------------------------------
    # STEP 4 — Idempotency check
    # If we've seen this requestId before, return 200 immediately.
    # Nomba may deliver the same event more than once.
    # ------------------------------------------------------------------
    if not request_id:
        logger.warning("webhook | missing requestId, rejecting")
        raise HTTPException(status_code=400, detail="Missing requestId")

    already_processed = db.query(model.ProcessedEvent).filter(
        model.ProcessedEvent.event_id == request_id
    ).first()

    if already_processed:
        logger.info(f"webhook | duplicate event ignored: {request_id}")
        return {"status": "already processed"}

    # ------------------------------------------------------------------
    # STEP 5 — Route by event type
    # ------------------------------------------------------------------
    if event_type == "payment_success":
        await _handle_payment_success(data, db)
    elif event_type == "charge.failed":
        await _handle_charge_failed(data, db)
    else:
        # Log unknown events but still return 200 so Nomba stops retrying
        logger.info(f"webhook | unhandled event type: {event_type}")

    # ------------------------------------------------------------------
    # STEP 6 — Mark event as processed AFTER successful handling
    # ------------------------------------------------------------------
    processed = model.ProcessedEvent(event_id=request_id)
    db.add(processed)
    db.commit()

    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Handler: payment_success
# Fires after BOTH:
#   - First-time checkout (gives us the card token)
#   - Recurring token charge (confirms billing succeeded)
# ---------------------------------------------------------------------------
async def _handle_payment_success(data: dict, db: Session):
    order_reference = data.get("orderReference") or data.get("merchantTxRef")
    amount_kobo = data.get("amount", 0)

    # Extract card token if present (only on first-time checkout)
    card = data.get("card", {})
    token_key = card.get("token") or card.get("cardToken")
    last_four = card.get("last4") or card.get("lastFour")
    nomba_customer_id = data.get("customerId")

    logger.info(
        f"webhook | payment_success",
        extra={"order_reference": order_reference, "amount_kobo": amount_kobo},
    )

    if not order_reference:
        logger.error("webhook | payment_success missing orderReference")
        return

    # ------------------------------------------------------------------
    # Case A: First-time checkout — reference starts with "ord_"
    # Find subscription by checkout_reference, store token, activate
    # ------------------------------------------------------------------
    if order_reference.startswith("ord_"):
        subscription = db.query(model.Subscription).filter(
            model.Subscription.checkout_reference == order_reference
        ).first()

        if not subscription:
            logger.error(f"webhook | no subscription found for ref: {order_reference}")
            return

        # Store the tokenized card — this is what enables recurring billing
        subscription.token_key = token_key
        subscription.last_four = last_four
        subscription.nomba_customer_id = nomba_customer_id
        subscription.status = model.SubscriptionStatus.active

        # Set next billing date based on plan frequency
        subscription.next_billing_date = _next_billing_date(
            subscription.plan.billing_frequency
        )

        # Record transaction
        transaction = model.Transaction(
            subscription_id=subscription.id,
            amount=amount_kobo,
            status=model.TransactionStatus.success,
            reference=order_reference,
        )
        db.add(transaction)
        db.commit()

        logger.info(
            f"webhook | subscription activated",
            extra={"subscription_id": subscription.id, "last_four": last_four},
        )

    # ------------------------------------------------------------------
    # Case B: Recurring charge success — reference starts with "sub_"
    # Find transaction by reference, mark it success
    # ------------------------------------------------------------------
    elif order_reference.startswith("sub_"):
        transaction = db.query(model.Transaction).filter(
            model.Transaction.reference == order_reference
        ).first()

        if not transaction:
            logger.error(f"webhook | no transaction found for ref: {order_reference}")
            return

        transaction.status = model.TransactionStatus.success
        transaction.subscription.status = model.SubscriptionStatus.active
        transaction.subscription.last_charged_at = datetime.utcnow()
        transaction.subscription.next_billing_date = _next_billing_date(
            transaction.subscription.plan.billing_frequency
        )

        db.commit()

        logger.info(
            f"webhook | recurring charge confirmed",
            extra={"reference": order_reference},
        )


# ---------------------------------------------------------------------------
# Handler: charge.failed
# Fires when a recurring token charge fails (insufficient funds, expired card)
# ---------------------------------------------------------------------------
async def _handle_charge_failed(data: dict, db: Session):
    merchant_tx_ref = data.get("merchantTxRef")
    failure_reason = data.get("message") or data.get("reason", "Unknown failure")

    logger.warning(
        f"webhook | charge.failed",
        extra={"merchant_tx_ref": merchant_tx_ref, "reason": failure_reason},
    )

    if not merchant_tx_ref:
        return

    # Find the transaction and mark it failed
    transaction = db.query(model.Transaction).filter(
        model.Transaction.reference == merchant_tx_ref
    ).first()

    if not transaction:
        logger.error(f"webhook | no transaction found for failed ref: {merchant_tx_ref}")
        return

    transaction.status = model.TransactionStatus.failed
    transaction.failure_reason = failure_reason
    transaction.subscription.status = model.SubscriptionStatus.past_due

    db.commit()

    logger.warning(
        f"webhook | subscription marked past_due",
        extra={"subscription_id": transaction.subscription_id},
    )

    # TODO: Trigger Termii WhatsApp alert here (Teammate B's task)
    # await send_failure_alert(transaction.subscription.customer, transaction)


# ---------------------------------------------------------------------------
# Helper: calculate next billing date from frequency
# ---------------------------------------------------------------------------
def _next_billing_date(frequency: model.BillingFrequency) -> datetime:
    now = datetime.utcnow()
    if frequency == model.BillingFrequency.weekly:
        return now + timedelta(weeks=1)
    elif frequency == model.BillingFrequency.monthly:
        return now + timedelta(days=30)
    elif frequency == model.BillingFrequency.quarterly:
        return now + timedelta(days=90)
    elif frequency == model.BillingFrequency.yearly:
        return now + timedelta(days=365)
    return now + timedelta(days=30)   # safe default