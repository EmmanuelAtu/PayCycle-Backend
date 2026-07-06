from database import get_db
import model, schemas
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, HTTPException, status
from core import security
from routers.join import generate_join_token

router = APIRouter(tags=["PLANS"])


@router.post("/plans", status_code=status.HTTP_201_CREATED, response_model=schemas.PlanOut)
def create_plan(
    plan: schemas.PlanCreate,
    db: Session = Depends(get_db),
    current_user: model.User = Depends(security.get_current_user)
):
    new_plan = model.Plan(
        name=plan.name,
        amount=plan.amount,
        billing_frequency=plan.billing_frequency,
        billing_day=plan.billing_day,
        provider_id=current_user.id,
        join_token=generate_join_token()
    )
    db.add(new_plan)
    db.commit()
    db.refresh(new_plan)
    return new_plan


@router.get("/plans", response_model=list[schemas.PlanOut])
def get_plans(
    db: Session = Depends(get_db),
    current_user: model.User = Depends(security.get_current_user)
):
    return db.query(model.Plan).filter(
        model.Plan.provider_id == current_user.id,
        model.Plan.is_active == True
    ).all()


@router.get("/plans/{plan_id}", response_model=schemas.PlanOut)
def get_plan(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: model.User = Depends(security.get_current_user)
):
    plan = db.query(model.Plan).filter(
        model.Plan.id == plan_id,
        model.Plan.provider_id == current_user.id,  # ownership check
        model.Plan.is_active == True
    ).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan


@router.delete("/plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_plan(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: model.User = Depends(security.get_current_user)  # auth added
):
    plan = db.query(model.Plan).filter(
        model.Plan.id == plan_id,
        model.Plan.provider_id == current_user.id
    ).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    plan.is_active = False  # soft delete — preserves audit trail
    db.commit()


@router.put("/plans/{plan_id}", response_model=schemas.PlanOut)
def update_plan(
    plan_id: int,
    plan: schemas.PlanCreate,
    db: Session = Depends(get_db),
    current_user: model.User = Depends(security.get_current_user)
):
    existing_plan = db.query(model.Plan).filter(
        model.Plan.id == plan_id,
        model.Plan.provider_id == current_user.id  # ownership check
    ).first()
    if not existing_plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    existing_plan.name = plan.name
    existing_plan.amount = plan.amount
    existing_plan.billing_frequency = plan.billing_frequency
    existing_plan.billing_day = plan.billing_day
    # provider_id never updated — provider can't reassign their own plan

    db.commit()
    db.refresh(existing_plan)
    return existing_plan

@router.get("/plans/{plan_id}/subscriptions", response_model=list[schemas.SubscriberOut])
def all_subscriptions(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: model.User = Depends(security.get_current_user)
):
    plan = db.query(model.Plan).filter(
        model.Plan.id == plan_id,
        model.Plan.provider_id == current_user.id,
    ).first()

    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    subscribers = db.query(model.Subscription).join(
        model.Plan, model.Subscription.plan_id == model.Plan.id
    ).filter(
        model.Plan.id == plan_id,
        model.Plan.provider_id == current_user.id,
    ).all()

    return subscribers