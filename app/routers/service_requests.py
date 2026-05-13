from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from uuid import UUID
from datetime import datetime, timedelta
import secrets 
from app.database import get_db
from app.models import (
    User, ServiceRequest, Vehicle, Quotation, Payment,
    AdminAvailability, ServiceQueue, Notification, CustomerProfile
)
from app.schemas import (
    ServiceRequestCreate, ServiceRequestResponse, ServiceRequestUpdate,
    QuotationResponse, QuotationAccept, CancelRequest,
    Location, PaymentResponse, PaymentIntentResponse
)
from app.auth import get_current_customer, get_current_user
from app.services.pricing_service import PricingService
from app.services.queue_service import QueueService
from app.services.notification_service import NotificationService
from app.config import settings

router = APIRouter(prefix="/service-requests", tags=["Service Requests"])


@router.post("/", response_model=ServiceRequestResponse)
async def create_service_request(
    request_data: ServiceRequestCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_customer),
    db: Session = Depends(get_db)
):
    """Create a new service request"""
    try:
        print(f"Creating service request for user: {current_user.id}")
        
        # Generate unique request number
        year_part = datetime.now().strftime('%Y')
        random_part = secrets.token_hex(4).upper()
        request_number = f"TRK-{year_part}-{random_part}"
        print(f"Generated request number: {request_number}")
        
        # Validate vehicle if provided
        if request_data.vehicle_id:
            vehicle = db.query(Vehicle).filter(
                Vehicle.id == request_data.vehicle_id,
                Vehicle.customer_id == current_user.id
            ).first()
            if not vehicle:
                raise HTTPException(status_code=404, detail="Vehicle not found")
            print(f"Vehicle found: {vehicle.brand} {vehicle.model}")
        
        # Create service request
        new_request = ServiceRequest(
            request_number=request_number,
            customer_id=current_user.id,
            vehicle_id=request_data.vehicle_id if request_data.vehicle_id else None,
            from_location_address=request_data.from_location.address,
            from_location_latitude=request_data.from_location.latitude,
            from_location_longitude=request_data.from_location.longitude,
            from_location_landmark=request_data.from_location.landmark,
            from_location_city=request_data.from_location.city,
            from_location_state=request_data.from_location.state,
            from_location_zipcode=request_data.from_location.zipcode,
            service_type=request_data.service_type,
            vehicle_condition=request_data.vehicle_condition,
            towing_type=request_data.towing_type,
            urgency=request_data.urgency,
            issue_description=request_data.issue_description,
            special_instructions=request_data.special_instructions,
            status="request_created",
            requested_at=datetime.utcnow(),
            created_at=datetime.utcnow()
        )
        
        # Add to location if provided
        if request_data.to_location:
            new_request.to_location_address = request_data.to_location.address
            new_request.to_location_latitude = request_data.to_location.latitude
            new_request.to_location_longitude = request_data.to_location.longitude
            new_request.to_location_landmark = request_data.to_location.landmark
            new_request.to_location_city = request_data.to_location.city
            new_request.to_location_state = request_data.to_location.state
            new_request.to_location_zipcode = request_data.to_location.zipcode
        
        # Add vehicle details if provided directly (without vehicle_id)
        if request_data.vehicle_brand:
            new_request.vehicle_brand = request_data.vehicle_brand
        if request_data.vehicle_model:
            new_request.vehicle_model = request_data.vehicle_model
        if request_data.vehicle_color:
            new_request.vehicle_color = request_data.vehicle_color
        if request_data.vehicle_model_year:
            new_request.vehicle_model_year = request_data.vehicle_model_year
        if request_data.vehicle_license_plate:
            new_request.vehicle_license_plate = request_data.vehicle_license_plate
        if request_data.vehicle_vin_number:
            new_request.vehicle_vin_number = request_data.vehicle_vin_number
        
        # If vehicle is selected, copy details from vehicle
        if request_data.vehicle_id:
            vehicle = db.query(Vehicle).filter(Vehicle.id == request_data.vehicle_id).first()
            if vehicle:
                new_request.vehicle_brand = vehicle.brand
                new_request.vehicle_model = vehicle.model
                new_request.vehicle_color = vehicle.color
                new_request.vehicle_model_year = vehicle.year
                new_request.vehicle_license_plate = vehicle.license_plate
                new_request.vehicle_vin_number = vehicle.vin_number
        
        db.add(new_request)
        db.commit()
        db.refresh(new_request)
        
        print(f"✅ Service request created: {new_request.id}")
        
        # Try to generate quotation (don't fail if this fails)
        try:
            pricing_service = PricingService(db)
            quotation = await pricing_service.calculate_quotation(new_request.id)
            
            # Update request status
            new_request.status = "quoted"
            new_request.quoted_at = datetime.utcnow()
            db.commit()
            
            print(f"✅ Quotation generated: {quotation.total_amount}")
        except Exception as e:
            print(f"⚠️ Quotation generation error (non-fatal): {e}")
        
        return ServiceRequestResponse.model_validate(new_request)
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Service request creation error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=List[ServiceRequestResponse])
async def get_my_requests(
    current_user: User = Depends(get_current_customer),
    status: Optional[str] = None,
    limit: int = 50,
    skip: int = 0,
    db: Session = Depends(get_db)
):
    """Get all service requests for current customer"""
    try:
        # Log for debugging
        print(f"Fetching requests for user: {current_user.id}")
        print(f"Filters - status: {status}, limit: {limit}, skip: {skip}")
        
        # Build query
        query = db.query(ServiceRequest).filter(ServiceRequest.customer_id == current_user.id)
        
        # Apply status filter if provided
        if status:
            # Convert to lowercase to handle case-insensitive queries
            status_lower = status.lower()
            query = query.filter(ServiceRequest.status == status_lower)
            print(f"Filtering by status: {status_lower}")
        
        # Apply pagination and ordering
        requests = query.order_by(ServiceRequest.created_at.desc()).offset(skip).limit(limit).all()
        
        print(f"Found {len(requests)} requests")
        
        # Convert to response model
        return [ServiceRequestResponse.model_validate(r) for r in requests]
        
    except Exception as e:
        print(f"Error in get_my_requests: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{request_id}", response_model=ServiceRequestResponse)
async def get_service_request(
    request_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get service request details"""
    request = db.query(ServiceRequest).filter(ServiceRequest.id == request_id).first()
    
    if not request:
        raise HTTPException(status_code=404, detail="Service request not found")
    
    # Check authorization
    if current_user.role.value != "admin" and request.customer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return ServiceRequestResponse.model_validate(request)


@router.get("/{request_id}/quotation", response_model=QuotationResponse)
async def get_quotation(
    request_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get quotation for service request"""
    request = db.query(ServiceRequest).filter(ServiceRequest.id == request_id).first()
    
    if not request:
        raise HTTPException(status_code=404, detail="Service request not found")
    
    if current_user.role.value != "admin" and request.customer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    quotation = db.query(Quotation).filter(Quotation.request_id == request_id).first()
    
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")
    
    return QuotationResponse.model_validate(quotation)
@router.post("/{request_id}/accept-quote")
async def accept_quotation(
    request_id: UUID,
    accept_data: QuotationAccept,
    current_user: User = Depends(get_current_customer),
    db: Session = Depends(get_db)
):
    """Accept quotation and confirm booking"""
    try:
        from datetime import datetime, timezone
        
        now = datetime.now(timezone.utc)
        
        # Find the service request
        service_request = db.query(ServiceRequest).filter(
            ServiceRequest.id == request_id,
            ServiceRequest.customer_id == current_user.id
        ).first()
        
        if not service_request:
            raise HTTPException(status_code=404, detail="Service request not found")
        
        if service_request.status != "quoted":
            raise HTTPException(status_code=400, detail=f"Cannot accept. Status is {service_request.status}")
        
        # Find the quotation
        quotation = db.query(Quotation).filter(Quotation.request_id == request_id).first()
        
        if not quotation:
            raise HTTPException(status_code=404, detail="Quotation not found")
        
        # Update records
        quotation.is_accepted = True
        quotation.accepted_at = now
        
        service_request.status = "confirmed"
        service_request.confirmed_at = now
        
        # Update customer profile - FIXED: Handle None values
        customer_profile = db.query(CustomerProfile).filter(
            CustomerProfile.user_id == current_user.id
        ).first()
        
        if not customer_profile:
            customer_profile = CustomerProfile(
                user_id=current_user.id,
                total_bookings=0,
                total_spent=0,
                loyalty_points=0
            )
            db.add(customer_profile)
        else:
            # Initialize to 0 if None
            if customer_profile.total_bookings is None:
                customer_profile.total_bookings = 0
            if customer_profile.total_spent is None:
                customer_profile.total_spent = 0
        
        # Now safely increment
        customer_profile.total_bookings += 1
        customer_profile.total_spent += float(quotation.total_amount)
        
        db.commit()
        
        return {
            "message": "Quotation accepted successfully",
            "request_number": service_request.request_number,
            "total_amount": float(quotation.total_amount),
            "status": service_request.status,
            "confirmed_at": service_request.confirmed_at
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{request_id}/cancel")
async def cancel_service_request(
    request_id: UUID,
    cancel_data: CancelRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Cancel a service request"""
    
    service_request = db.query(ServiceRequest).filter(ServiceRequest.id == request_id).first()
    
    if not service_request:
        raise HTTPException(status_code=404, detail="Service request not found")
    
    # Check authorization
    if current_user.role.value != "admin" and service_request.customer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Check if cancellation is allowed
    allowed_statuses = ["request_created", "quoted", "confirmed", "pending", "in_queue"]
    if service_request.status not in allowed_statuses:
        raise HTTPException(status_code=400, detail=f"Cannot cancel request in {service_request.status} status")
    
    # Cancel the request
    service_request.status = "cancelled"
    service_request.cancelled_at = datetime.utcnow()
    service_request.cancelled_by = "customer" if current_user.role.value == "customer" else "admin"
    service_request.cancellation_reason = cancel_data.reason
    
    # Remove from queue if present
    queue_entry = db.query(ServiceQueue).filter(ServiceQueue.request_id == request_id).first()
    if queue_entry:
        queue_entry.is_active = False
        db.delete(queue_entry)
    
    db.commit()
    
    # Send notification
    notification_service = NotificationService(db, background_tasks)
    await notification_service.send_notification(
        user_id=service_request.customer_id,
        notification_type="cancellation",
        title="Booking Cancelled",
        message=f"Your booking {service_request.request_number} has been cancelled. Reason: {cancel_data.reason}"
    )
    
    return {"message": "Service request cancelled successfully"}


@router.get("/{request_id}/track")
async def track_service_request(
    request_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Track service request status and location"""
    
    service_request = db.query(ServiceRequest).filter(ServiceRequest.id == request_id).first()
    
    if not service_request:
        raise HTTPException(status_code=404, detail="Service request not found")
    
    if current_user.role.value != "admin" and service_request.customer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return {
        "request_number": service_request.request_number,
        "status": service_request.status,
        "estimated_eta_minutes": service_request.estimated_eta_minutes,
        "requested_at": service_request.requested_at,
        "accepted_at": service_request.accepted_at,
        "picked_at": service_request.picked_at,
        "completed_at": service_request.completed_at
    }