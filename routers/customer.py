from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from core.security import get_current_user
import schemas, model

router = APIRouter(prefix="/customers", tags=["CUSTOMERS"])


@router.get("/", response_model=list[schemas.CustomerOut])
def get_customers(
    db: Session = Depends(get_db),
    current_user: model.User = Depends(get_current_user),
):
    """
    Returns all customers who have subscribed to any of the
    logged-in provider's plans.
    """
    customers = (
        db.query(model.Customer)
        .join(model.Subscription, model.Subscription.customer_id == model.Customer.id)
        .join(model.Plan, model.Plan.id == model.Subscription.plan_id)
        .filter(
            model.Plan.provider_id == current_user.id,
            model.Customer.is_active == True,
        )
        .distinct()
        .all()
    )
    return customers


@router.get("/{customer_id}", response_model=schemas.CustomerOut)
def get_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: model.User = Depends(get_current_user),
):
    """Get a single customer by ID — must belong to the logged-in provider."""
    customer = (
        db.query(model.Customer)
        .join(model.Subscription, model.Subscription.customer_id == model.Customer.id)
        .join(model.Plan, model.Plan.id == model.Subscription.plan_id)
        .filter(
            model.Customer.id == customer_id,
            model.Plan.provider_id == current_user.id,
            model.Customer.is_active == True,
        )
        .first()
    )
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer


@router.get("/{customer_id}/subscriptions", response_model=list[schemas.SubscriptionOut])
def get_customer_subscriptions(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: model.User = Depends(get_current_user),
):
    """All subscriptions for a specific customer under this provider."""
    subscriptions = (
        db.query(model.Subscription)
        .join(model.Plan, model.Plan.id == model.Subscription.plan_id)
        .filter(
            model.Subscription.customer_id == customer_id,
            model.Plan.provider_id == current_user.id,
            model.Subscription.is_active == True,
        )
        .all()
    )
    return subscriptions


@router.delete("/{customer_id}", status_code=204)
def deactivate_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: model.User = Depends(get_current_user),
):
    """Soft delete a customer — sets is_active to False."""
    customer = (
        db.query(model.Customer)
        .join(model.Subscription, model.Subscription.customer_id == model.Customer.id)
        .join(model.Plan, model.Plan.id == model.Subscription.plan_id)
        .filter(
            model.Customer.id == customer_id,
            model.Plan.provider_id == current_user.id,
        )
        .first()
    )
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    customer.is_active = False
    db.commit()

@router.get("/customers/{phone}/subscriptions", response_model=list[schemas.SubscriberOut])
def get_customer_subscriptions(
    phone: str,
    db: Session = Depends(get_db)
):
    customer = db.query(model.Customer).filter(
        model.Customer.phone == phone
    ).first()

    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    subscriptions = db.query(model.Subscription).filter(
        model.Subscription.customer_id == customer.id
    ).order_by(model.Subscription.created_at.desc()).all()

    return subscriptions