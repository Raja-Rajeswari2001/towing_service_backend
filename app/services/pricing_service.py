from sqlalchemy.orm import Session
from sqlalchemy import func
from uuid import UUID
from datetime import datetime
from typing import Dict, Optional

from app.models import (
    ServiceRequest, Quotation, PricingConfig,
    VehicleTypePricing, ServiceTypePricing, Vehicle
)
from app.utils import calculate_distance, is_night_time, is_weekend


class PricingService:
    def __init__(self, db: Session):
        self.db = db
    
    async def calculate_quotation(self, request_id: UUID) -> Quotation:
        """Calculate quotation for a service request"""
        
        service_request = self.db.query(ServiceRequest).filter(
            ServiceRequest.id == request_id
        ).first()
        
        if not service_request:
            raise ValueError("Service request not found")
        
        # Get pricing configuration
        config = await self._get_pricing_config()
        
        # Calculate distance
        distance_km = 0
        if service_request.from_location_latitude and service_request.from_location_longitude:
            # Calculate distance to destination or to base
            distance_km = 10  # Default for demo
        
        # Base hookup fee
        base_hookup_fee = config.get("base_hookup_fee", 50.00)
        
        # Free miles calculation
        free_miles_included = config.get("free_miles_included", 5)
        distance_miles = distance_km * 0.621371
        
        distance_cost = 0
        extra_miles = 0
        extra_miles_cost = 0
        
        if distance_miles > free_miles_included:
            extra_miles = distance_miles - free_miles_included
            per_mile_rate = config.get("per_mile_rate_normal", 4.00)
            distance_cost = free_miles_included * per_mile_rate
            extra_miles_cost = extra_miles * per_mile_rate
        else:
            per_mile_rate = config.get("per_mile_rate_normal", 4.00)
            distance_cost = distance_miles * per_mile_rate
        
        # Service type charge
        service_charge = await self._get_service_charge(service_request.service_type)
        
        # Vehicle type charge
        vehicle_type_charge = await self._get_vehicle_charge(service_request)
        
        # Night charge
        night_charge = 0
        if is_night_time():
            night_percent = config.get("night_charge_percent", 25)
            night_charge = (base_hookup_fee + distance_cost) * night_percent / 100
        
        # Weekend charge
        weekend_charge = 0
        if is_weekend():
            weekend_percent = config.get("weekend_charge_percent", 15)
            weekend_charge = (base_hookup_fee + distance_cost) * weekend_percent / 100
        
        # Emergency/Priority charge
        emergency_charge = 0
        priority_charge = 0
        if service_request.urgency:
            if service_request.urgency.value == "emergency":
                emergency_charge = config.get("emergency_charge", 50.00)
            elif service_request.urgency.value == "priority":
                priority_charge = config.get("priority_charge", 30.00)
        
        # Tax calculation
        tax_percentage = config.get("tax_percentage", 8.00)
        
        # Create quotation
        quotation = Quotation(
            request_id=request_id,
            base_hookup_fee=base_hookup_fee,
            distance_km=distance_km,
            distance_miles=distance_miles,
            distance_cost=distance_cost,
            free_miles_included=free_miles_included,
            extra_miles=extra_miles if extra_miles > 0 else None,
            extra_miles_cost=extra_miles_cost,
            service_charge=service_charge,
            vehicle_type_charge=vehicle_type_charge,
            night_charge=night_charge,
            weekend_charge=weekend_charge,
            emergency_charge=emergency_charge,
            priority_charge=priority_charge,
            tax_percentage=tax_percentage,
            expires_at=datetime.utcnow()
        )
        
        # Check if quotation already exists
        existing = self.db.query(Quotation).filter(Quotation.request_id == request_id).first()
        
        if existing:
            # Update existing
            for key, value in quotation.__dict__.items():
                if not key.startswith('_') and key != 'id' and key != 'created_at':
                    setattr(existing, key, value)
            quotation = existing
        else:
            self.db.add(quotation)
        
        self.db.commit()
        self.db.refresh(quotation)
        
        return quotation
    
    async def _get_pricing_config(self) -> Dict:
        """Get pricing configuration as dictionary"""
        
        configs = self.db.query(PricingConfig).all()
        
        config_dict = {}
        for config in configs:
            if config.config_value is not None:
                config_dict[config.config_key] = float(config.config_value)
            elif config.config_text is not None:
                try:
                    config_dict[config.config_key] = float(config.config_text)
                except ValueError:
                    config_dict[config.config_key] = config.config_text
        
        return config_dict
    
    async def _get_service_charge(self, service_type) -> float:
        """Get charge for a service type"""
        
        pricing = self.db.query(ServiceTypePricing).filter(
            ServiceTypePricing.service_type == service_type
        ).first()
        
        return float(pricing.flat_charge) if pricing else 0
    
    async def _get_vehicle_charge(self, service_request: ServiceRequest) -> float:
        """Get charge based on vehicle type"""
        
        vehicle_type = None
        
        # Get vehicle type from linked vehicle
        if service_request.vehicle_id:
            vehicle = self.db.query(Vehicle).filter(
                Vehicle.id == service_request.vehicle_id
            ).first()
            if vehicle and vehicle.vehicle_type:
                vehicle_type = vehicle.vehicle_type
        
        # Or from direct fields
        if not vehicle_type and service_request.vehicle_brand:
            # Try to infer from brand
            vehicle_type = "sedan"  # Default
        
        if vehicle_type:
            pricing = self.db.query(VehicleTypePricing).filter(
                VehicleTypePricing.vehicle_type == vehicle_type
            ).first()
            if pricing:
                return float(pricing.base_charge)
        
        return 50.00  # Default charge