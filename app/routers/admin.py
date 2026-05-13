from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from uuid import UUID
from datetime import datetime

from app.database import get_db
from app.models import (
    User, ServiceRequest, Quotation, Payment, AdminAvailability,
    ServiceQueue, Earning, VehicleTypePricing, ServiceTypePricing,  
    PricingConfig, RefundRequest
)
from app.schemas import (
    ServiceRequestResponse, ServiceRequestAdminUpdate, QuotationResponse,
    AdminAvailabilityUpdate, AdminAvailabilityResponse, DashboardStats,
    EarningsResponse, PricingConfigResponse, PricingConfigUpdate
)
from app.auth import get_current_admin
from app.services.pricing_service import PricingService
from app.services.queue_service import QueueService
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/admin", tags=["Admin"])


# =====================================================
# Dashboard
# =====================================================
@router.get("/dashboard", response_model=DashboardStats)
async def get_dashboard_stats(
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Get admin dashboard statistics"""
    
    # Request counts by status
    status_counts = db.query(
        ServiceRequest.status,
        func.count(ServiceRequest.id)
    ).group_by(ServiceRequest.status).all()
    
    status_dict = dict(status_counts)
    
    # Revenue calculations
    total_revenue = db.query(func.sum(Payment.amount)).filter(
        Payment.payment_status == "completed"
    ).scalar() or 0
    
    today_revenue = db.query(func.sum(Payment.amount)).filter(
        Payment.payment_status == "completed",
        func.date(Payment.paid_at) == datetime.utcnow().date()
    ).scalar() or 0
    
    monthly_revenue = db.query(func.sum(Payment.amount)).filter(
        Payment.payment_status == "completed",
        func.extract('month', Payment.paid_at) == datetime.utcnow().month
    ).scalar() or 0
    
    return DashboardStats(
        pending_quotes=status_dict.get("request_created", 0) + status_dict.get("quoted", 0),
        confirmed_requests=status_dict.get("confirmed", 0),
        queued_requests=status_dict.get("in_queue", 0),
        dispatched_requests=status_dict.get("dispatched", 0),
        active_jobs=status_dict.get("accepted", 0) + status_dict.get("on_the_way", 0) + status_dict.get("picked", 0),
        completed_services=status_dict.get("completed", 0),
        cancelled_requests=status_dict.get("cancelled", 0),
        total_requests=sum(status_dict.values()),
        total_revenue=float(total_revenue),
        today_revenue=float(today_revenue),
        monthly_revenue=float(monthly_revenue)
    )


# =====================================================
# Service Request Management
# =====================================================
@router.get("/service-requests", response_model=List[ServiceRequestResponse])
async def get_all_service_requests(
    status: Optional[str] = None,
    limit: int = 100,
    skip: int = 0,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Get all service requests (admin view)"""
    
    query = db.query(ServiceRequest)
    
    if status:
        query = query.filter(ServiceRequest.status == status)
    
    requests = query.order_by(ServiceRequest.created_at.desc()).offset(skip).limit(limit).all()
    
    return [ServiceRequestResponse.model_validate(r) for r in requests]


@router.put("/service-requests/{request_id}/status")
async def update_service_request_status(
    request_id: UUID,
    update_data: ServiceRequestAdminUpdate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Update service request status"""
    
    service_request = db.query(ServiceRequest).filter(ServiceRequest.id == request_id).first()
    
    if not service_request:
        raise HTTPException(status_code=404, detail="Service request not found")
    
    old_status = service_request.status
    service_request.status = update_data.status
    
    # Update timestamps based on status
    if update_data.status == "accepted" and not service_request.accepted_at:
        service_request.accepted_at = datetime.utcnow()
    elif update_data.status == "picked" and not service_request.picked_at:
        service_request.picked_at = datetime.utcnow()
    elif update_data.status == "completed" and not service_request.completed_at:
        service_request.completed_at = datetime.utcnow()
    
    if update_data.estimated_eta_minutes is not None:
        service_request.estimated_eta_minutes = update_data.estimated_eta_minutes
    
    if update_data.cancellation_reason:
        service_request.cancellation_reason = update_data.cancellation_reason
    
    db.commit()
    
    # Send notification to customer
    notification_service = NotificationService(db, background_tasks)
    await notification_service.send_notification(
        user_id=service_request.customer_id,
        notification_type="status_update",
        title="Booking Status Updated",
        message=f"Your booking {service_request.request_number} status has been updated to {update_data.status}"
    )
    
    return {"message": f"Status updated from {old_status} to {update_data.status}"}


@router.post("/service-requests/{request_id}/dispatch")
async def dispatch_service_request(
    request_id: UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Dispatch a service request to the driver (admin)"""
    
    service_request = db.query(ServiceRequest).filter(ServiceRequest.id == request_id).first()
    
    if not service_request:
        raise HTTPException(status_code=404, detail="Service request not found")
    
    if service_request.status != "in_queue":
        raise HTTPException(status_code=400, detail="Request must be in queue to dispatch")
    
    # Update status
    service_request.status = "dispatched"
    db.commit()
    
    # Update admin availability (admin = driver)
    admin_availability = db.query(AdminAvailability).first()
    if admin_availability:
        admin_availability.status = "busy"
        admin_availability.current_job_id = request_id
        admin_availability.busy_until = datetime.utcnow()
        db.commit()
    
    # Send notification to customer
    notification_service = NotificationService(db, background_tasks)
    await notification_service.send_notification(
        user_id=service_request.customer_id,
        notification_type="admin_assigned",
        title="Driver Dispatched",
        message=f"A driver has been dispatched for your booking {service_request.request_number}"
    )
    
    return {"message": "Service request dispatched successfully"}


# =====================================================
# Admin Availability Management
# =====================================================
@router.get("/availability", response_model=AdminAvailabilityResponse)
async def get_admin_availability(
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Get current admin availability status"""
    
    availability = db.query(AdminAvailability).first()
    
    if not availability:
        # Create default availability
        availability = AdminAvailability(
            admin_id=current_user.id,
            status="available"
        )
        db.add(availability)
        db.commit()
        db.refresh(availability)
    
    return AdminAvailabilityResponse.model_validate(availability)


@router.put("/availability", response_model=AdminAvailabilityResponse)
async def update_admin_availability(
    update_data: AdminAvailabilityUpdate,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Update admin availability status"""
    
    availability = db.query(AdminAvailability).first()
    
    if not availability:
        availability = AdminAvailability(admin_id=current_user.id)
        db.add(availability)
    
    availability.status = update_data.status
    availability.busy_until = update_data.busy_until
    availability.scheduled_from = update_data.scheduled_from
    availability.scheduled_to = update_data.scheduled_to
    availability.notes = update_data.notes
    availability.last_status_change = datetime.utcnow()
    
    db.commit()
    db.refresh(availability)
    
    return AdminAvailabilityResponse.model_validate(availability)


# =====================================================
# Queue Management
# =====================================================
@router.get("/queue")
async def get_service_queue(
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Get current service queue"""
    
    queue_entries = db.query(ServiceQueue).filter(
        ServiceQueue.is_active == True
    ).order_by(ServiceQueue.queue_position).all()
    
    result = []
    for entry in queue_entries:
        service_request = db.query(ServiceRequest).filter(
            ServiceRequest.id == entry.request_id
        ).first()
        
        if service_request:
            result.append({
                "position": entry.queue_position,
                "priority_level": entry.priority_level,
                "request_number": service_request.request_number,
                "service_type": service_request.service_type,
                "urgency": service_request.urgency,
                "estimated_eta": entry.estimated_eta
            })
    
    return result


@router.post("/queue/reorder")
async def reorder_queue(
    new_order: List[UUID],
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Reorder the service queue"""
    
    for position, request_id in enumerate(new_order, start=1):
        queue_entry = db.query(ServiceQueue).filter(
            ServiceQueue.request_id == request_id
        ).first()
        
        if queue_entry:
            queue_entry.queue_position = position
    
    db.commit()
    
    return {"message": "Queue reordered successfully"}


# =====================================================
# Earnings & Reports
# =====================================================
@router.get("/earnings", response_model=List[EarningsResponse])
async def get_earnings(
    settlement_status: Optional[str] = None,
    limit: int = 100,
    skip: int = 0,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Get earnings records"""
    try:
        # Use Earning model (singular, not Earnings)
        query = db.query(Earning)
        
        if settlement_status:
            query = query.filter(Earning.settlement_status == settlement_status)
        
        earnings = query.order_by(Earning.created_at.desc()).offset(skip).limit(limit).all()
        
        return [EarningsResponse.model_validate(e) for e in earnings]
    
    except Exception as e:
        print(f"Error in get_earnings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/earnings/summary")
async def get_earnings_summary(
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Get earnings summary"""
    try:
        from sqlalchemy import func
        
        # Use the correct model name (check your models.py)
        # Option 1: If your model is named "Earning"
        total_earnings = db.query(func.sum(Earning.admin_earning)).filter(
            Earning.settlement_status == "settled"
        ).scalar() or 0
        
        pending_earnings = db.query(func.sum(Earning.admin_earning)).filter(
            Earning.settlement_status == "pending"
        ).scalar() or 0
        
        total_platform_fees = db.query(func.sum(Earning.platform_fee)).scalar() or 0
        
        # Get additional stats
        total_transactions = db.query(func.count(Earning.id)).scalar() or 0
        
        settled_transactions = db.query(func.count(Earning.id)).filter(
            Earning.settlement_status == "settled"
        ).scalar() or 0
        
        return {
            "total_earnings": float(total_earnings),
            "pending_earnings": float(pending_earnings),
            "total_platform_fees": float(total_platform_fees),
            "total_transactions": total_transactions,
            "settled_transactions": settled_transactions,
            "average_earning": float(total_earnings / settled_transactions) if settled_transactions > 0 else 0
        }
    
    except Exception as e:
        print(f"Error in get_earnings_summary: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================
# Refund Management
# =====================================================
@router.get("/refunds")
async def get_refund_requests(
    status: Optional[str] = None,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Get refund requests"""
    try:
        query = db.query(RefundRequest)
        
        if status:
            query = query.filter(RefundRequest.status == status)
        
        refunds = query.order_by(RefundRequest.created_at.desc()).all()
        
        result = []
        for refund in refunds:
            service_request = db.query(ServiceRequest).filter(
                ServiceRequest.id == refund.request_id
            ).first()
            
            result.append({
                "id": str(refund.id),  # Convert UUID to string
                "request_number": service_request.request_number if service_request else None,
                "amount": float(refund.amount),
                "reason": refund.reason,
                "status": refund.status,
                "created_at": refund.created_at
            })
        
        return result
    
    except Exception as e:
        print(f"Error in get_refund_requests: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/refunds/{refund_id}/process")
async def process_refund(
    refund_id: UUID,
    action: str,  # "approve" or "reject"
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Process a refund request"""
    
    refund = db.query(RefundRequest).filter(RefundRequest.id == refund_id).first()
    
    if not refund:
        raise HTTPException(status_code=404, detail="Refund request not found")
    
    if refund.status != "pending":
        raise HTTPException(status_code=400, detail=f"Refund already {refund.status}")
    
    if action == "approve":
        refund.status = "approved"
        refund.processed_by = current_user.id
        refund.processed_at = datetime.utcnow()
        
        # Update payment status
        payment = db.query(Payment).filter(Payment.id == refund.payment_id).first()
        if payment:
            payment.payment_status = "refunded"
            payment.refunded_at = datetime.utcnow()
            payment.refund_amount = refund.amount
            payment.refund_reason = refund.reason
        
        db.commit()
        
        return {"message": "Refund approved successfully"}
    
    elif action == "reject":
        refund.status = "rejected"
        refund.processed_by = current_user.id
        refund.processed_at = datetime.utcnow()
        db.commit()
        
        return {"message": "Refund rejected"}
    
    else:
        raise HTTPException(status_code=400, detail="Invalid action. Use 'approve' or 'reject'")


# =====================================================# Pricing Configuration
# =====================================================
@router.get("/pricing", response_model=List[PricingConfigResponse])
async def get_pricing_config(
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Get all pricing configuration"""
    
    configs = db.query(PricingConfig).all()
    return [PricingConfigResponse.model_validate(c) for c in configs]


@router.put("/pricing/{config_key}", response_model=PricingConfigResponse)
async def update_pricing_config(
    config_key: str,
    update_data: PricingConfigUpdate,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Update pricing configuration"""
    
    config = db.query(PricingConfig).filter(PricingConfig.config_key == config_key).first()
    
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")
    
    if update_data.config_value is not None:
        config.config_value = update_data.config_value
    if update_data.config_text is not None:
        config.config_text = update_data.config_text
    if update_data.config_json is not None:
        config.config_json = update_data.config_json
    if update_data.description is not None:
        config.description = update_data.description
    
    config.updated_by = current_user.id
    
    db.commit()
    db.refresh(config)
    
    return PricingConfigResponse.model_validate(config)


@router.get("/vehicle-pricing")
async def get_vehicle_pricing(
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Get vehicle type pricing"""
    
    pricing = db.query(VehicleTypePricing).all()
    
    return [
        {
            "vehicle_type": p.vehicle_type.value,
            "base_charge": float(p.base_charge),
            "per_mile_multiplier": float(p.per_mile_multiplier),
            "description": p.description
        }
        for p in pricing
    ]


@router.get("/service-pricing")
async def get_service_pricing(
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Get service type pricing"""
    
    pricing = db.query(ServiceTypePricing).all()
    
    return [
        {
            "service_type": p.service_type.value,
            "flat_charge": float(p.flat_charge),
            "travel_included": p.travel_included,
            "description": p.description
        }
        for p in pricing
    ]