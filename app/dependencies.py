from typing import Optional
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import AdminAvailability, User


def get_admin_availability(db: Session) -> Optional[User]:
    """Get admin with availability status"""
    admin = db.query(User).filter(User.role == "admin", User.is_active == True).first()
    return admin


def is_admin_available(db: Session) -> bool:
    """Check if admin is available for service"""
    availability = db.query(AdminAvailability).first()
    if not availability:
        return False
    return availability.status.value == "available"