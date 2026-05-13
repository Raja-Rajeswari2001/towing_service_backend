from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from uuid import UUID

from app.database import get_db
from app.models import ServiceRequest, User
from app.schemas import QuotationResponse
from app.auth import get_current_user
from app.services.pricing_service import PricingService

router = APIRouter(prefix="/pricing", tags=["Pricing"])


@router.get("/estimate")
async def get_estimate(
    service_type: str,
    vehicle_type: str,
    distance_km: float,
    urgency: str = "normal",
    db: Session = Depends(get_db)
):
    """Get a price estimate without creating a request"""
    
    # Mock location data for estimate
    is_night = False
    is_weekend = False
    
    # Calculate base price
    base_fee = 50.00
    per_km_rate = 4.00
    distance_cost = distance_km * per_km_rate
    
    # Service type charges
    service_charges = {
        "towing": 0,
        "jump_start": 25.00,
        "flat_tire": 35.00,
        "lockout": 45.00,
        "fuel_delivery": 30.00,
        "winching": 75.00
    }
    service_charge = service_charges.get(service_type, 0)
    
    # Vehicle type charges
    vehicle_charges = {
        "motorcycle": 40.00,
        "sedan": 50.00,
        "suv": 65.00,
        "truck": 85.00,
        "heavy_duty": 120.00
    }
    vehicle_charge = vehicle_charges.get(vehicle_type, 50.00)
    
    # Urgency charges
    urgency_charge = 0
    if urgency == "priority":
        urgency_charge = 30.00
    elif urgency == "emergency":
        urgency_charge = 50.00
    
    # Calculate subtotal
    subtotal = base_fee + distance_cost + service_charge + vehicle_charge + urgency_charge
    
    # Add tax
    tax_percentage = 8.00
    tax_amount = subtotal * tax_percentage / 100
    total = subtotal + tax_amount
    
    return {
        "base_hookup_fee": base_fee,
        "distance_km": distance_km,
        "distance_cost": distance_cost,
        "service_charge": service_charge,
        "vehicle_type_charge": vehicle_charge,
        "urgency_charge": urgency_charge,
        "subtotal": round(subtotal, 2),
        "tax_amount": round(tax_amount, 2),
        "total_amount": round(total, 2)
    }


@router.get("/service-request/{request_id}/quotation", response_model=QuotationResponse)
async def get_request_quotation(
    request_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get quotation for a specific service request"""
    
    service_request = db.query(ServiceRequest).filter(ServiceRequest.id == request_id).first()
    
    if not service_request:
        raise HTTPException(status_code=404, detail="Service request not found")
    
    # Check authorization
    if current_user.role.value != "admin" and service_request.customer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    pricing_service = PricingService(db)
    quotation = await pricing_service.calculate_quotation(request_id)
    
    return QuotationResponse.model_validate(quotation)