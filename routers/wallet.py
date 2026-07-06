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

router = APIRouter(prefix="/wallet", tags=["WALLET"])

@router.get("/wallet", response_model=schemas.WalletOut)
def get_wallet(
    db: Session = Depends(get_db),
    current_user: model.User = Depends(security.get_current_user)
):
    wallet = db.query(model.Wallet).filter(
        model.Wallet.provider_id == current_user.id
    ).first()

    if not wallet:
        wallet = model.Wallet(provider_id=current_user.id, balance=0)
        db.add(wallet)
        db.commit()
        db.refresh(wallet)

    return wallet


@router.get("/wallet/ledger", response_model=list[schemas.WalletLedgerOut])
def get_wallet_ledger(
    db: Session = Depends(get_db),
    current_user: model.User = Depends(security.get_current_user)
):
    wallet = db.query(model.Wallet).filter(
        model.Wallet.provider_id == current_user.id
    ).first()

    if not wallet:
        return []

    return db.query(model.WalletLedger).filter(
        model.WalletLedger.wallet_id == wallet.id
    ).order_by(model.WalletLedger.created_at.desc()).all()