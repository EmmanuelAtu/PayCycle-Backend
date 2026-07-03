from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from database import get_db
import schemas, model
from core.security import get_current_user
from core.config import settings          # ← was missing
from services.nomba_client import nomba
import time

router = APIRouter(tags=["SUBSCRIPTIONS"])


@router.post("/subscribe", response_model=schemas.SubscriptionCheckoutResponse)
async def create_subscription(
    sub_data: schemas.SubscriptionCreate,
    db: Session = Depends(get_db),
    current_user: model.User = Depends(get_current_user),
):
    # 1. Verify the plan exists and belongs to a real provider
    plan = db.query(model.Plan).filter(
        model.Plan.id == sub_data.plan_id,
        model.Plan.is_active == True
    ).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    # 2. Find or create the customer record
    customer = db.query(model.Customer).filter(
        model.Customer.phone == sub_data.customer_phone
    ).first()

    if not customer:
        customer = model.Customer(
            name=sub_data.customer_name,
            email=sub_data.customer_email,
            phone=sub_data.customer_phone,
        )
        db.add(customer)
        db.commit()
        db.refresh(customer)

    # 3. Create the PENDING subscription FIRST — we need its ID to build the ref
    new_sub = model.Subscription(
        customer_id=customer.id,
        plan_id=plan.id,
        status=model.SubscriptionStatus.pending,
        next_billing_date=datetime.utcnow() + timedelta(days=30),
    )
    db.add(new_sub)
    db.commit()
    db.refresh(new_sub)   # ← now new_sub.id exists

    # 4. Generate ref AFTER we have the subscription ID, store it immediately
    tx_ref = f"ord_{new_sub.id}_{int(time.time())}"
    new_sub.checkout_reference = tx_ref
    db.commit()           # ← ref is persisted before we call Nomba

    # 5. Call Nomba to get the checkout URL
    try:
        checkout_data = await nomba.create_checkout(
            amount=plan.amount / 100,           # kobo → Naira
            customer_email=customer.email,
            subscription_id=str(new_sub.id),
            callback_url=f"{settings.APP_URL}/payment/return",
            customer_name=customer.name,
            order_ref=tx_ref,
        )
    except Exception as e:
        # If Nomba call fails, mark subscription as cancelled so it doesn't hang
        new_sub.status = model.SubscriptionStatus.cancelled
        db.commit()
        raise HTTPException(status_code=502, detail=f"Payment provider error: {str(e)}")

    checkout_url = checkout_data["checkoutUrl"]

    return {
        "message": "Checkout initiated",
        "checkout_url": checkout_url,
        "checkout_reference": tx_ref,
        "subscription_id": new_sub.id,
    }