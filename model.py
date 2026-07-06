import enum

from sqlalchemy import Integer, Column, String, Boolean,ForeignKey,Enum
from database import Base
from sqlalchemy.sql.sqltypes import TIMESTAMP
from sqlalchemy.sql.expression import text
from sqlalchemy.orm import Relationship, relationship
from sqlalchemy import DateTime
from sqlalchemy.sql import func


#Enums
class BillingFrequency(str, enum.Enum):
    weekly = "weekly"
    quarterly = "quarterly"
    monthly = "monthly"
    yearly = "yearly"

class SubscriptionStatus(str, enum.Enum):
    pending = "pending"
    active = "active"
    paused = "paused"
    cancelled = "cancelled"
    past_due = "past_due"

class TransactionStatus(str, enum.Enum):
    pending = "pending"
    success = "success"
    failed = "failed"   

# Shared Mixin: Automatically adds audit trails & soft delete to every table
class CommonMixin:
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)     

class User(Base, CommonMixin):

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, nullable=False)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True)
    phone_number = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    #created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text('now()'))
    #for hackathon using sqlite
    #created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    plans = relationship("Plan",back_populates="provider", cascade="all, delete-orphan")
    wallet = relationship("Wallet", back_populates="provider", uselist=False, cascade="all, delete-orphan")

class Plan(Base, CommonMixin):
    """Billing Plans offered by Providers"""
    __tablename__ = "plans"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    amount = Column(Integer, nullable=False)  # Stored in Kobo/Cents
    billing_frequency = Column(Enum(BillingFrequency), nullable=False)
    billing_day = Column(Integer, nullable=True)  # e.g., 15 for the 15th of each month
    provider_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    # When plan is created, generate a unique join token
    join_token = Column(String, unique=True, index=True, nullable=True)
    provider = relationship("User", back_populates="plans")
    subscriptions = relationship("Subscription", back_populates="plan", cascade="all, delete-orphan")


class Customer(Base, CommonMixin):
    """Normalized End-User table (People paying for plans)"""
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    phone = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, nullable=True)

    subscriptions = relationship("Subscription", back_populates="customer", cascade="all, delete-orphan")


class Subscription(Base, CommonMixin):
    """Join Table linking Customers to Plans with payment tokens"""
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)
    plan_id = Column(Integer, ForeignKey("plans.id", ondelete="CASCADE"), nullable=False)
    
    token_key = Column(String, nullable=True)  # populated post-checkout webhook
    last_four = Column(String, nullable=True)
    status = Column(Enum(SubscriptionStatus), default=SubscriptionStatus.active, nullable=False)
    next_billing_date = Column(DateTime(timezone=True), nullable=False)

    customer = relationship("Customer", back_populates="subscriptions")
    plan = relationship("Plan", back_populates="subscriptions")
    transactions = relationship("Transaction", back_populates="subscription", cascade="all, delete-orphan")

    nomba_customer_id = Column(String, nullable=True)  # needed for token charge API
    checkout_reference = Column(String, nullable=True, index=True)  # match webhook to subscription
    last_charged_at = Column(DateTime(timezone=True), nullable=True)


class Transaction(Base, CommonMixin):
    """Audit trail of billing attempts via Nomba"""
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    subscription_id = Column(Integer, ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False)
    amount = Column(Integer, nullable=False)
    status = Column(Enum(TransactionStatus), default=TransactionStatus.pending, nullable=False)
    reference = Column(String, unique=True, index=True, nullable=False)  # Nomba transaction reference
    failure_reason = Column(String, nullable=True)
    subscription = relationship("Subscription", back_populates="transactions")

class ProcessedEvent(Base):
    __tablename__ = "processed_events"

    event_id = Column(String, primary_key=True)
    processed_at = Column(DateTime(timezone=True), server_default=func.now())    

class WalletTransactionType(str, enum.Enum):
    credit = "credit"
    debit = "debit"

class Wallet(Base, CommonMixin):
    __tablename__ = "wallets"

    id = Column(Integer, primary_key=True, index=True)
    provider_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    balance = Column(Integer, nullable=False, default=0)  # kobo

    provider = relationship("User", back_populates="wallet")
    ledger = relationship("WalletLedger", back_populates="wallet", cascade="all, delete-orphan")


class WalletLedger(Base, CommonMixin):
    """Audit trail of wallet credits/debits"""
    __tablename__ = "wallet_ledger"

    id = Column(Integer, primary_key=True, index=True)
    wallet_id = Column(Integer, ForeignKey("wallets.id", ondelete="CASCADE"), nullable=False)
    amount = Column(Integer, nullable=False)  # kobo, always positive
    type = Column(Enum(WalletTransactionType), nullable=False)
    reference = Column(String, nullable=True)  # e.g. transaction.reference that triggered this
    description = Column(String, nullable=True)

    wallet = relationship("Wallet", back_populates="ledger")
