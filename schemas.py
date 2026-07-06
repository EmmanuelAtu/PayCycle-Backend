from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional
from model import SubscriptionStatus   # single source of truth for the enum


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
class UserCreate(BaseModel):
    name: str
    email: EmailStr
    phone_number: str
    password: str


class UserOut(BaseModel):
    id: int
    name: str
    email: EmailStr
    created_at: datetime

    class Config:                      # ← capital C
        from_attributes = True


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str


# ---------------------------------------------------------------------------
# Plans
# ---------------------------------------------------------------------------
class PlanCreate(BaseModel):
    name: str
    amount: int                        # in kobo
    billing_frequency: str             # "weekly" | "monthly" | "quarterly" | "yearly"
    billing_day: Optional[int] = None


class PlanOut(BaseModel):
    id: int
    name: str
    amount: int                        # in kobo
    billing_frequency: str
    billing_day: Optional[int] = None
    provider_id: int
    join_token: Optional[str] = None
    
    class Config:                      # ← capital C
        from_attributes = True


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------
class CustomerOut(BaseModel):
    id: int
    name: str
    phone: str
    email: Optional[str] = None

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Subscriptions
# ---------------------------------------------------------------------------
class SubscriptionCreate(BaseModel):
    plan_id: int
    customer_name: str
    customer_email: str
    customer_phone: str


class SubscriptionOut(BaseModel):
    id: int
    customer_id: int
    plan_id: int
    status: SubscriptionStatus
    checkout_reference: Optional[str] = None
    next_billing_date: datetime
    last_four: Optional[str] = None

    class Config:
        from_attributes = True


class SubscriptionCheckoutResponse(BaseModel):
    message: str
    checkout_url: str
    checkout_reference: str
    subscription_id: int               # ← matches what the route actually returns
    

# ---------------------------------------------------------------------------
# Schema — what the client fills in on the join page
# ---------------------------------------------------------------------------
class CustomerJoinSchema(BaseModel):
    name: str
    email: EmailStr
    phone: str


class JoinResponse(BaseModel):
    message: str
    checkout_url: str
    checkout_reference: str


class SubscriberOut(BaseModel):
    id: int
    customer: CustomerOut
    plan_id: int
    status: SubscriptionStatus
    next_billing_date: datetime

    class Config:
        from_attributes = True