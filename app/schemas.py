from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, Dict, Any, List
from datetime import datetime
from uuid import UUID
from enum import Enum
from app.models import UserRole 

# =====================================================
# Enums for Pydantic
# =====================================================

class UserCreate(BaseModel):
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = None
    password: Optional[str] = Field(None, min_length=6)
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    
    @field_validator('password')
    def validate_password_length(cls, v):
        if v:
            # Check byte length
            byte_length = len(v.encode('utf-8'))
            if byte_length > 72:
                raise ValueError(f'Password is too long ({byte_length} bytes). Maximum 72 bytes allowed.')
            if len(v) > 128:
                raise ValueError('Password cannot exceed 128 characters')
        return v
    
    @field_validator('email', 'phone_number')
    def validate_contact(cls, v, info):
        if not v and info.field_name == 'email' and not info.data.get('phone_number'):
            raise ValueError('Either email or phone number is required')
        return v



class UserRole(str, Enum):
    CUSTOMER = "customer"
    ADMIN = "admin"


class VehicleType(str, Enum):
    MOTORCYCLE = "motorcycle"
    SEDAN = "sedan"
    SUV = "suv"
    TRUCK = "truck"
    HEAVY_DUTY = "heavy_duty"


class VehicleCondition(str, Enum):
    RUNNING = "running"
    NOT_RUNNING = "not_running"
    ACCIDENT = "accident"
    FLAT_TIRE = "flat_tire"
    BATTERY_DEAD = "battery_dead"
    ENGINE_FAILURE = "engine_failure"
    DAMAGED = "damaged"


class TowingType(str, Enum):
    OPEN = "open"
    FLATBED = "flatbed"
    WHEEL_LIFT = "wheel_lift"
    INTEGRATED = "integrated"


class PriorityLevel(str, Enum):
    NORMAL = "normal"
    PRIORITY = "priority"
    EMERGENCY = "emergency"


class ServiceType(str, Enum):
    TOWING = "towing"
    JUMP_START = "jump_start"
    FLAT_TIRE = "flat_tire"
    LOCKOUT = "lockout"
    FUEL_DELIVERY = "fuel_delivery"
    WINCHING = "winching"


class ServiceRequestStatus(str, Enum):
    REQUEST_CREATED = "request_created"
    QUOTED = "quoted"
    CONFIRMED = "confirmed"
    PENDING = "pending"
    IN_QUEUE = "in_queue"
    DISPATCHED = "dispatched"
    ACCEPTED = "accepted"
    ON_THE_WAY = "on_the_way"
    PICKED = "picked"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class PaymentMethod(str, Enum):
    CASH = "cash"
    CARD = "card"
    WALLET = "wallet"
    BANK_TRANSFER = "bank_transfer"


class PaymentStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


class AdminStatus(str, Enum):
    AVAILABLE = "available"
    BUSY = "busy"
    SCHEDULED = "scheduled"
    OFF_DUTY = "off_duty"


# =====================================================
# User Schemas
# =====================================================
class UserBase(BaseModel):
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class UserCreate(UserBase):
    password: Optional[str] = Field(None, min_length=6)
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = None
    role: Optional[UserRole] = UserRole.CUSTOMER  # Add this line
    
    @field_validator('password')
    def validate_password(cls, v):
        if v:
            # Check byte length (not character length)
            byte_length = len(v.encode('utf-8'))
            if byte_length > 72:
                raise ValueError(f'Password is too long ({byte_length} bytes). Maximum 72 bytes allowed.')
            if len(v) > 128:
                raise ValueError('Password cannot exceed 128 characters')
        return v
    
    @field_validator('email', 'phone_number')
    def validate_contact(cls, v, info):
        if not v and info.field_name == 'email' and not info.data.get('phone_number'):
            raise ValueError('Either email or phone number is required')
        return v


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class PhoneLogin(BaseModel):
    phone_number: str


class OTPVerify(BaseModel):
    phone_number: str
    otp_code: str


class EmailOTPRequest(BaseModel):
    email: EmailStr
    purpose: str = "login"
    check_existing: bool = False


class EmailOTPVerify(BaseModel):
    email: EmailStr
    otp_code: str
    purpose: str = "login"
    full_name: Optional[str] = None


class UserResponse(BaseModel):
    id: UUID
    email: Optional[str] = None
    phone_number: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: str
    role: UserRole
    is_verified: bool
    profile_picture: Optional[str] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# =====================================================
# Vehicle Schemas
# =====================================================
class VehicleBase(BaseModel):
    vin_number: Optional[str] = Field(None, max_length=17)
    brand: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = Field(None, ge=1900, le=datetime.now().year + 1)
    color: Optional[str] = None
    license_plate: Optional[str] = None
    vehicle_type: Optional[VehicleType] = None
    body_class: Optional[str] = None
    vehicle_condition: Optional[VehicleCondition] = None
    towing_type: Optional[TowingType] = None
    priority_level: PriorityLevel = PriorityLevel.NORMAL
    is_default: bool = False


class VehicleCreate(VehicleBase):
    pass


class VehicleUpdate(VehicleBase):
    pass


class VehicleResponse(VehicleBase):
    id: UUID
    customer_id: UUID
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


# =====================================================
# Location Schemas
# =====================================================
class Location(BaseModel):
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    address: str
    landmark: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zipcode: Optional[str] = None


# =====================================================
# Service Request Schemas
# =====================================================
class ServiceRequestBase(BaseModel):
    from_location: Location
    to_location: Optional[Location] = None
    service_type: ServiceType
    vehicle_condition: Optional[VehicleCondition] = None
    towing_type: Optional[TowingType] = None
    urgency: PriorityLevel = PriorityLevel.NORMAL
    issue_description: Optional[str] = None
    special_instructions: Optional[str] = None
    
    # Optional vehicle details (if not using saved vehicle)
    vehicle_brand: Optional[str] = None
    vehicle_model: Optional[str] = None
    vehicle_color: Optional[str] = None
    vehicle_model_year: Optional[int] = None
    vehicle_license_plate: Optional[str] = None
    vehicle_vin_number: Optional[str] = None


class ServiceRequestCreate(ServiceRequestBase):
    vehicle_id: Optional[UUID] = None


class ServiceRequestUpdate(BaseModel):
    from_location: Optional[Location] = None
    to_location: Optional[Location] = None
    special_instructions: Optional[str] = None


class ServiceRequestResponse(BaseModel):
    id: UUID
    request_number: str
    customer_id: UUID
    vehicle_id: Optional[UUID] = None
    
    from_location_address: str
    from_location_latitude: Optional[float] = None
    from_location_longitude: Optional[float] = None
    from_location_landmark: Optional[str] = None
    from_location_city: Optional[str] = None
    from_location_state: Optional[str] = None
    from_location_zipcode: Optional[str] = None
    
    to_location_address: Optional[str] = None
    to_location_latitude: Optional[float] = None
    to_location_longitude: Optional[float] = None
    to_location_landmark: Optional[str] = None
    to_location_city: Optional[str] = None
    to_location_state: Optional[str] = None
    to_location_zipcode: Optional[str] = None
    
    vehicle_brand: Optional[str] = None
    vehicle_model: Optional[str] = None
    vehicle_color: Optional[str] = None
    vehicle_model_year: Optional[int] = None
    vehicle_license_plate: Optional[str] = None
    
    service_type: ServiceType
    vehicle_condition: Optional[VehicleCondition] = None
    towing_type: Optional[TowingType] = None
    urgency: PriorityLevel
    status: ServiceRequestStatus
    
    requested_at: datetime
    quoted_at: Optional[datetime] = None
    confirmed_at: Optional[datetime] = None
    accepted_at: Optional[datetime] = None
    picked_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    cancellation_reason: Optional[str] = None
    
    queue_position: Optional[int] = None
    estimated_eta_minutes: Optional[int] = None
    issue_description: Optional[str] = None
    special_instructions: Optional[str] = None
    
    vehicle: Optional[VehicleResponse] = None
    
    class Config:
        from_attributes = True


# =====================================================
# Quotation Schemas
# =====================================================
class QuotationBase(BaseModel):
    base_hookup_fee: float = 0
    distance_km: Optional[float] = None
    distance_miles: Optional[float] = None
    distance_cost: float = 0
    free_miles_included: int = 0
    extra_miles: Optional[float] = None
    extra_miles_cost: float = 0
    service_charge: float = 0
    vehicle_type_charge: float = 0
    night_charge: float = 0
    weekend_charge: float = 0
    emergency_charge: float = 0
    priority_charge: float = 0
    highway_charge: float = 0
    remote_charge: float = 0
    waiting_time_minutes: int = 0
    waiting_charge: float = 0
    toll_charges: float = 0
    permit_charges: float = 0
    tax_percentage: float = 0


class QuotationResponse(BaseModel):
    id: UUID
    request_id: UUID
    subtotal: float
    tax_amount: float
    total_amount: float
    is_accepted: bool
    created_at: datetime
    expires_at: Optional[datetime] = None
    
    # Include all pricing components for transparency
    base_hookup_fee: float
    distance_km: Optional[float]
    distance_cost: float
    service_charge: float
    vehicle_type_charge: float
    night_charge: float
    weekend_charge: float
    emergency_charge: float
    priority_charge: float
    waiting_charge: float
    toll_charges: float
    
    class Config:
        from_attributes = True


class QuotationAccept(BaseModel):
    payment_method: PaymentMethod


# =====================================================
# Payment Schemas
# =====================================================
class PaymentCreate(BaseModel):
    payment_method: PaymentMethod
    payment_intent_id: Optional[str] = None


class PaymentResponse(BaseModel):
    id: UUID
    request_id: UUID
    amount: float
    payment_method: Optional[PaymentMethod]
    payment_status: PaymentStatus
    paid_at: Optional[datetime] = None
    stripe_payment_intent_id: Optional[str] = None
    
    class Config:
        from_attributes = True


class PaymentIntentResponse(BaseModel):
    client_secret: str
    amount: float
    payment_intent_id: str


# =====================================================
# Review Schemas
# =====================================================
class ReviewCreate(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    review_text: Optional[str] = None


class ReviewResponse(BaseModel):
    id: UUID
    request_id: UUID
    rating: int
    review_text: Optional[str]
    response_text: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True


# =====================================================
# Admin Schemas
# =====================================================
class AdminAvailabilityUpdate(BaseModel):
    status: AdminStatus
    busy_until: Optional[datetime] = None
    scheduled_from: Optional[datetime] = None
    scheduled_to: Optional[datetime] = None
    notes: Optional[str] = None


class AdminAvailabilityResponse(BaseModel):
    id: UUID
    status: AdminStatus
    next_available_time: Optional[datetime] = None
    busy_until: Optional[datetime] = None
    current_job_id: Optional[UUID] = None
    last_status_change: datetime
    
    class Config:
        from_attributes = True


class ServiceRequestAdminUpdate(BaseModel):
    status: ServiceRequestStatus
    estimated_eta_minutes: Optional[int] = None
    cancellation_reason: Optional[str] = None


class DashboardStats(BaseModel):
    pending_quotes: int
    confirmed_requests: int
    queued_requests: int
    dispatched_requests: int
    active_jobs: int
    completed_services: int
    cancelled_requests: int
    total_requests: int
    total_revenue: float
    today_revenue: float
    monthly_revenue: float


# =====================================================
# Notification Schemas
# =====================================================
class NotificationResponse(BaseModel):
    id: UUID
    type: str
    title: str
    message: str
    data: Optional[Dict[str, Any]] = None
    is_read: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


class NotificationMarkRead(BaseModel):
    notification_ids: List[UUID]


# =====================================================
# Pricing Config Schemas
# =====================================================
class PricingConfigUpdate(BaseModel):
    config_value: Optional[float] = None
    config_text: Optional[str] = None
    config_json: Optional[Dict] = None
    description: Optional[str] = None


class PricingConfigResponse(BaseModel):
    id: UUID
    config_key: str
    config_value: Optional[float] = None
    config_text: Optional[str] = None
    config_json: Optional[Dict] = None
    description: Optional[str] = None
    updated_at: datetime
    
    class Config:
        from_attributes = True


# =====================================================
# Geo and Distance Schemas
# =====================================================
class GeoPoint(BaseModel):
    lat: float
    lng: float


class DistanceResponse(BaseModel):
    distance_km: float
    distance_miles: float
    duration_minutes: int


# =====================================================
# Cancel Request Schema
# =====================================================
class CancelRequest(BaseModel):
    reason: str


# =====================================================
# Earnings Response
# =====================================================
class EarningsResponse(BaseModel):
    id: UUID
    request_id: UUID
    total_amount: float
    platform_fee: float
    admin_earning: float
    settlement_status: str
    created_at: datetime
    
    class Config:
        from_attributes = True