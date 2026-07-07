from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from core import security
from database import get_db
from core.config import settings
from services.nomba_client import nomba
from pydantic import BaseModel, EmailStr
import model, schemas
import secrets
import os
import httpx
import time

router = APIRouter(tags=["JOIN"])


# ---------------------------------------------------------------------------
# Helper — generate a unique join token when a plan is created
# Call this from your plans router when creating a plan
# ---------------------------------------------------------------------------
def generate_join_token() -> str:
    return secrets.token_urlsafe(12)  # e.g. "aB3xK9mNqR2p"


# ---------------------------------------------------------------------------
# GET /join/{join_token}
# Serves the HTML page — browser opens this when student taps the link
# ---------------------------------------------------------------------------
@router.get("/join/{join_token}", response_class=HTMLResponse)
def serve_join_page(join_token: str):
    html_path = os.path.join(os.path.dirname(__file__), "..", "static", "pay.html")
    with open(html_path, "r") as f:
        return HTMLResponse(content=f.read())
 
 
# ---------------------------------------------------------------------------
# GET /api/join/{join_token}
# JSON endpoint — pay.html calls this to get plan details
# ---------------------------------------------------------------------------
@router.get("/api/join/{join_token}")
def get_plan_by_token(join_token: str, db: Session = Depends(get_db)):
    plan = db.query(model.Plan).filter(
        model.Plan.join_token == join_token,
        model.Plan.is_active == True,
    ).first()
 
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found or no longer active")
 
    return {
        "plan_id": plan.id,
        "plan_name": plan.name,
        "amount": plan.amount / 100,
        "billing_frequency": plan.billing_frequency,
        "provider_name": plan.provider.name,
    }
 
 
# ---------------------------------------------------------------------------
# POST /api/join/{join_token}
# Student submits details → create subscription → return checkout URL
# ---------------------------------------------------------------------------
@router.post("/api/join/{join_token}", response_model=schemas.JoinResponse)
async def join_plan(
    join_token: str,
    data: schemas.CustomerJoinSchema,
    db: Session = Depends(get_db),
):
    # 1. Find plan
    plan = db.query(model.Plan).filter(
        model.Plan.join_token == join_token,
        model.Plan.is_active == True,
    ).first()
 
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found or no longer active")
 
    # 2. Find or create customer
    customer = db.query(model.Customer).filter(
        model.Customer.phone == data.phone
    ).first()
 
    if not customer:
        customer = model.Customer(
            name=data.name,
            email=data.email,
            phone=data.phone,
        )
        db.add(customer)
        db.commit()
        db.refresh(customer)
 
    # 3. Prevent duplicate active subscriptions
    # CORRECT — only block if already active
    existing = db.query(model.Subscription).filter(
        model.Subscription.customer_id == customer.id,
        model.Subscription.plan_id == plan.id,
        model.Subscription.status == model.SubscriptionStatus.active,
        model.Subscription.is_active == True,
    ).first()
 
    if existing:
        raise HTTPException(status_code=400, detail="You are already subscribed to this plan")
 
    # 4. Create pending subscription
    new_sub = model.Subscription(
        customer_id=customer.id,
        plan_id=plan.id,
        status=model.SubscriptionStatus.pending,
        next_billing_date=datetime.utcnow() + timedelta(days=30),
    )
    db.add(new_sub)
    db.commit()
    db.refresh(new_sub)
 
    # 5. Generate ref AFTER we have the ID, store it before calling Nomba
    nomba_ref = checkout_data["orderReference"]
    new_sub.checkout_reference = nomba_ref
    db.commit()
 
    # 6. Call Nomba
    try:
        checkout_data = await nomba.create_checkout(
            amount=plan.amount / 100,
            customer_email=customer.email,
            subscription_id=str(new_sub.id),
            callback_url=f"{settings.APP_URL}/payment/return?orderReference={nomba_ref}",
            customer_name=customer.name,
            order_ref=nomba_ref,
        )
        # After getting checkout_data, store Nomba's actual reference
        new_sub.checkout_reference = checkout_data["orderReference"]  # ← use Nomba's ref
        db.commit()
    except Exception as e:
        new_sub.status = model.SubscriptionStatus.cancelled
        db.commit()
        raise HTTPException(status_code=502, detail=f"Payment provider error: {str(e)}")
 
    return {
        "message": "Redirecting to payment",
        "checkout_url": checkout_data["checkoutLink"],
        "checkout_reference": nomba_ref,
    }
 
 
# ---------------------------------------------------------------------------
# GET /payment/return  — Nomba redirects here after checkout
# ---------------------------------------------------------------------------
@router.get("/payment/return", response_class=HTMLResponse)
async def payment_return(orderReference: str = None, db: Session = Depends(get_db)):
    """
    Nomba redirects here after checkout with orderReference as query param.
    We poll Nomba to confirm payment and activate the subscription.
    """
    if orderReference:
        try:
            # Check order status directly from Nomba
            token = await nomba._get_token()
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"https://api.nomba.com/v1/checkout/order/{orderReference}",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "accountId": "f666ef9b-888e-4799-85ce-acb505b28023",
                    },
                    timeout=15.0
                )
            data = response.json()
            order_data = data.get("data", {})
            status = order_data.get("status", "")

            if status == "COMPLETED" or status == "SUCCESS":
                # Find subscription by checkout_reference
                subscription = db.query(model.Subscription).filter(
                    model.Subscription.checkout_reference == orderReference
                ).first()

                if subscription and subscription.status == model.SubscriptionStatus.pending:
                    subscription.status = model.SubscriptionStatus.active
                    subscription.next_billing_date = datetime.utcnow() + timedelta(days=30)

                    # Record transaction
                    transaction = model.Transaction(
                        subscription_id=subscription.id,
                        amount=order_data.get("amount", 0),
                        status=model.TransactionStatus.success,
                        reference=orderReference,
                    )
                    db.add(transaction)
                    db.commit()

        except Exception as e:
            print(f"Payment return polling error: {e}")

    return HTMLResponse(content="""
    <html>
      <head>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
          body { font-family: sans-serif; text-align: center; 
                 padding: 60px 20px; background: #F6F8FA; }
          .card { background: white; border-radius: 16px; 
                  padding: 48px 32px; max-width: 380px; 
                  margin: 0 auto; box-shadow: 0 4px 24px rgba(0,0,0,.08); }
          h2 { color: #0A6E4A; margin-bottom: 12px; }
          p { color: #6B7280; font-size: 15px; line-height: 1.6; }
        </style>
      </head>
      <body>
        <div class="card">
          <div style="font-size:48px;margin-bottom:16px">✅</div>
          <h2>Payment received!</h2>
          <p>Your subscription is now active. You can close this page.</p>
        </div>
      </body>
    </html>
    """)