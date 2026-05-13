from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from sqlalchemy.orm import Session
from uuid import UUID
from datetime import datetime
import json

from app.database import get_db
from app.models import User, ServiceRequest, Quotation, Payment, CustomerProfile
from app.schemas import PaymentCreate, PaymentResponse, PaymentIntentResponse
from app.auth import get_current_customer, get_current_user
from app.config import settings

import stripe

# Initialize Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY

router = APIRouter(prefix="/payments", tags=["Payments"])


@router.post("/create-payment-intent/{request_id}", response_model=PaymentIntentResponse)
async def create_payment_intent(
    request_id: UUID,
    current_user: User = Depends(get_current_customer),
    db: Session = Depends(get_db)
):
    """Create a Stripe payment intent for a service request"""
    
    service_request = db.query(ServiceRequest).filter(
        ServiceRequest.id == request_id,
        ServiceRequest.customer_id == current_user.id
    ).first()
    
    if not service_request:
        raise HTTPException(status_code=404, detail="Service request not found")
    
    quotation = db.query(Quotation).filter(Quotation.request_id == request_id).first()
    
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")
    
    if not quotation.is_accepted:
        raise HTTPException(status_code=400, detail="Quotation must be accepted before payment")
    
    # Check if payment already exists
    existing_payment = db.query(Payment).filter(Payment.request_id == request_id).first()
    if existing_payment and existing_payment.payment_status == "completed":
        raise HTTPException(status_code=400, detail="Payment already completed")
    
    # Create Stripe payment intent
    try:
        payment_intent = stripe.PaymentIntent.create(
            amount=int(quotation.total_amount * 100),  # Convert to cents
            currency="usd",
            metadata={
                "request_id": str(request_id),
                "request_number": service_request.request_number,
                "customer_id": str(current_user.id)
            }
        )
        
        # Save payment record
        payment = Payment(
            request_id=request_id,
            quotation_id=quotation.id,
            customer_id=current_user.id,
            amount=quotation.total_amount,
            payment_status="pending",
            stripe_payment_intent_id=payment_intent.id
        )
        
        db.add(payment)
        db.commit()
        
        return PaymentIntentResponse(
            client_secret=payment_intent.client_secret,
            amount=float(quotation.total_amount),
            payment_intent_id=payment_intent.id
        )
        
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Handle Stripe webhook events"""
    
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    # You'll need to set this in your .env file
    webhook_secret = getattr(settings, 'STRIPE_WEBHOOK_SECRET', '')
    
    try:
        if webhook_secret:
            event = stripe.Webhook.construct_event(
                payload, sig_header, webhook_secret
            )
        else:
            # For development without webhook secret
            event_data = json.loads(payload)
            event = stripe.Event.construct_from(event_data, stripe.api_key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid payload: {str(e)}")
    except stripe.error.SignatureVerificationError as e:
        raise HTTPException(status_code=400, detail=f"Invalid signature: {str(e)}")
    
    # Handle the event
    if event["type"] == "payment_intent.succeeded":
        payment_intent = event["data"]["object"]
        
        # Update payment record
        payment = db.query(Payment).filter(
            Payment.stripe_payment_intent_id == payment_intent["id"]
        ).first()
        
        if payment:
            payment.payment_status = "completed"
            payment.paid_at = datetime.utcnow()
            payment.stripe_charge_id = payment_intent.get("latest_charge")
            
            # Update service request status
            service_request = db.query(ServiceRequest).filter(
                ServiceRequest.id == payment.request_id
            ).first()
            
            if service_request and service_request.status == "confirmed":
                service_request.status = "in_queue"
            
            # Update customer profile
            customer_profile = db.query(CustomerProfile).filter(
                CustomerProfile.user_id == payment.customer_id
            ).first()
            
            if customer_profile:
                customer_profile.total_spent = (customer_profile.total_spent or 0) + payment.amount
            
            db.commit()
    
    elif event["type"] == "payment_intent.payment_failed":
        payment_intent = event["data"]["object"]
        
        payment = db.query(Payment).filter(
            Payment.stripe_payment_intent_id == payment_intent["id"]
        ).first()
        
        if payment:
            payment.payment_status = "failed"
            db.commit()
    
    return {"status": "success"}


@router.get("/{request_id}/status", response_model=PaymentResponse)
async def get_payment_status(
    request_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get payment status for a service request"""
    
    service_request = db.query(ServiceRequest).filter(ServiceRequest.id == request_id).first()
    
    if not service_request:
        raise HTTPException(status_code=404, detail="Service request not found")
    
    # Check authorization
    if current_user.role.value != "admin" and service_request.customer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    payment = db.query(Payment).filter(Payment.request_id == request_id).first()
    
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    
    return PaymentResponse.model_validate(payment)