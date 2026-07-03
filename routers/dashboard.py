from database import get_db, sessionLocal
import model, schemas, utils
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, HTTPException,status
from core import security
router = APIRouter(tags=["Dashboard"])


@router.get("/dashboard")
def get_mock_dashboard():
    # Temporary mock data so the Flutter app doesn't crash
    return {
        "total_revenue": 0,
        "active_subscribers": 0,
        "failed_payments": 0,
        "next_billing": "—"
    }