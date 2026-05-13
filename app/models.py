from sqlalchemy import (
    Column, String, Boolean, DateTime, Float, Enum, Integer, 
    Text, ForeignKey, JSON, DECIMAL
)
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID, ARRAY, INET
from sqlalchemy.orm import relationship
from app.database import Base

import enum
import uuid


class UserRole(str, enum.Enum):
    CUSTOMER = "customer"
    ADMIN = "admin"


class VehicleType(str, enum.Enum):
    MOTORCYCLE = "motorcycle"
    SEDAN = "sedan"
    SUV = "suv"
    TRUCK = "truck"
    HEAVY_DUTY = "heavy_duty"


class VehicleCondition(str, enum.Enum):
    RUNNING = "running"
    NOT_RUNNING = "not_running"
    ACCIDENT = "accident"
    FLAT_TIRE = "flat_tire"
    BATTERY_DEAD = "battery_dead"
    ENGINE_FAILURE = "engine_failure"
    DAMAGED = "damaged"


class TowingType(str, enum.Enum):
    OPEN = "open"
    FLATBED = "flatbed"
    WHEEL_LIFT = "wheel_lift"
    INTEGRATED = "integrated"


class PriorityLevel(str, enum.Enum):
    NORMAL = "normal"
    PRIORITY = "priority"
    EMERGENCY = "emergency"


class ServiceType(str, enum.Enum):
    TOWING = "towing"
    JUMP_START = "jump_start"
    FLAT_TIRE = "flat_tire"
    LOCKOUT = "lockout"
    FUEL_DELIVERY = "fuel_delivery"
    WINCHING = "winching"


class ServiceRequestStatus(str, enum.Enum):
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


class PaymentMethod(str, enum.Enum):
    CASH = "cash"
    CARD = "card"
    WALLET = "wallet"
    BANK_TRANSFER = "bank_transfer"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


class AdminStatus(str, enum.Enum):
    AVAILABLE = "available"
    BUSY = "busy"
    SCHEDULED = "scheduled"
    OFF_DUTY = "off_duty"


class NotificationType(str, enum.Enum):
    NEW_REQUEST = "new_request"
    BOOKING_CONFIRMATION = "booking_confirmation"
    STATUS_UPDATE = "status_update"
    QUOTATION_READY = "quotation_ready"
    ADMIN_ASSIGNED = "admin_assigned"
    ETA_UPDATE = "eta_update"
    PAYMENT_SUCCESS = "payment_success"
    PAYMENT_FAILED = "payment_failed"
    CANCELLATION = "cancellation"
    REVIEW_REQUEST = "review_request"
    PROMOTION = "promotion"


# =====================================================
# USERS TABLE
# =====================================================
class User(Base):
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=True)
    phone_number = Column(String(20), unique=True, nullable=True)
    password_hash = Column(String(255), nullable=True)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    role = Column(Enum(UserRole), default=UserRole.CUSTOMER)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    profile_picture = Column(Text, nullable=True)
    firebase_uid = Column(String(255), unique=True, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_login = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    customer_profile = relationship("CustomerProfile", back_populates="user", uselist=False)
    vehicles = relationship("Vehicle", back_populates="customer", cascade="all, delete-orphan")
    service_requests = relationship("ServiceRequest", back_populates="customer")
    payments = relationship("Payment", back_populates="customer")
    reviews = relationship("Review", back_populates="customer")
    notifications = relationship("Notification", back_populates="user")
    audit_logs = relationship("AuditLog", back_populates="user")
    
    @property
    def full_name(self):
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.first_name or self.email or self.phone_number or "User"
    
    @property
    def full_name_or_email(self):
        return self.full_name or self.email or str(self.id)


# =====================================================
# CUSTOMER PROFILES
# =====================================================
class CustomerProfile(Base):
    __tablename__ = "customer_profiles"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    loyalty_points = Column(Integer, default=0)
    total_bookings = Column(Integer, default=0)
    total_spent = Column(DECIMAL(10, 2), default=0)
    preferred_payment_method = Column(String(50), nullable=True)
    is_premium = Column(Boolean, default=False)
    notes = Column(Text, nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="customer_profile")


# =====================================================
# VEHICLES TABLE
# =====================================================
class Vehicle(Base):
    __tablename__ = "vehicles"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    
    vin_number = Column(String(17), nullable=True)
    brand = Column(String(50), nullable=True)
    model = Column(String(50), nullable=True)
    year = Column(Integer, nullable=True)
    color = Column(String(30), nullable=True)
    license_plate = Column(String(20), nullable=True)
    
    vehicle_type = Column(Enum(VehicleType), nullable=True)
    body_class = Column(String(100), nullable=True)
    
    vehicle_condition = Column(Enum(VehicleCondition), nullable=True)
    towing_type = Column(Enum(TowingType), nullable=True)
    priority_level = Column(Enum(PriorityLevel), default=PriorityLevel.NORMAL)
    
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    customer = relationship("User", back_populates="vehicles")
    service_requests = relationship("ServiceRequest", back_populates="vehicle")


# =====================================================
# ADMIN AVAILABILITY
# =====================================================
class AdminAvailability(Base):
    __tablename__ = "admin_availability"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    admin_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    status = Column(Enum(AdminStatus), default=AdminStatus.AVAILABLE)
    next_available_time = Column(DateTime(timezone=True), nullable=True)
    current_job_id = Column(UUID(as_uuid=True), nullable=True)
    busy_until = Column(DateTime(timezone=True), nullable=True)
    scheduled_from = Column(DateTime(timezone=True), nullable=True)
    scheduled_to = Column(DateTime(timezone=True), nullable=True)
    last_status_change = Column(DateTime(timezone=True), server_default=func.now())
    notes = Column(Text, nullable=True)
    
    # Relationships
    admin = relationship("User")


# =====================================================
# SERVICE REQUESTS TABLE
# =====================================================
class ServiceRequest(Base):
    __tablename__ = "service_requests"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_number = Column(String(50), unique=True, nullable=False)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    vehicle_id = Column(UUID(as_uuid=True), ForeignKey("vehicles.id"), nullable=True)
    
    # From Location (Pickup)
    from_location_latitude = Column(DECIMAL(10, 8), nullable=True)
    from_location_longitude = Column(DECIMAL(11, 8), nullable=True)
    from_location_address = Column(Text, nullable=False)
    from_location_landmark = Column(Text, nullable=True)
    from_location_city = Column(String(100), nullable=True)
    from_location_state = Column(String(50), nullable=True)
    from_location_zipcode = Column(String(20), nullable=True)
    
    # To Location (Drop)
    to_location_latitude = Column(DECIMAL(10, 8), nullable=True)
    to_location_longitude = Column(DECIMAL(11, 8), nullable=True)
    to_location_address = Column(Text, nullable=True)
    to_location_landmark = Column(Text, nullable=True)
    to_location_city = Column(String(100), nullable=True)
    to_location_state = Column(String(50), nullable=True)
    to_location_zipcode = Column(String(20), nullable=True)
    
    # Vehicle Details (Direct fields)
    vehicle_brand = Column(String(50), nullable=True)
    vehicle_model = Column(String(50), nullable=True)
    vehicle_color = Column(String(30), nullable=True)
    vehicle_model_year = Column(Integer, nullable=True)
    vehicle_license_plate = Column(String(20), nullable=True)
    vehicle_vin_number = Column(String(17), nullable=True)
    
    # Service Details
    service_type = Column(Enum(ServiceType))
    vehicle_condition = Column(Enum(VehicleCondition), nullable=True)
    towing_type = Column(Enum(TowingType), nullable=True)
    urgency = Column(Enum(PriorityLevel), default=PriorityLevel.NORMAL)
    
    # Status Flow
    status = Column(Enum(ServiceRequestStatus), default=ServiceRequestStatus.REQUEST_CREATED)
    
    # Timestamps
    requested_at = Column(DateTime(timezone=True), server_default=func.now())
    quoted_at = Column(DateTime(timezone=True), nullable=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    picked_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_by = Column(String(20), nullable=True)
    cancellation_reason = Column(Text, nullable=True)
    
    # Queue & Priority
    queue_position = Column(Integer, nullable=True)
    priority_score = Column(Integer, default=0)
    estimated_eta_minutes = Column(Integer, nullable=True)
    
    # Additional Info
    issue_description = Column(Text, nullable=True)
    special_instructions = Column(Text, nullable=True)
    is_covered_area = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    customer = relationship("User", back_populates="service_requests")
    vehicle = relationship("Vehicle", back_populates="service_requests")
    quotation = relationship("Quotation", back_populates="service_request", uselist=False)
    payment = relationship("Payment", back_populates="service_request", uselist=False)
    review = relationship("Review", back_populates="service_request", uselist=False)
    earnings = relationship("Earning", back_populates="service_request", uselist=False)
    notifications = relationship("Notification", back_populates="service_request")
    queue_entry = relationship("ServiceQueue", back_populates="service_request", uselist=False)


# =====================================================
# QUOTATIONS TABLE
# =====================================================
class Quotation(Base):
    __tablename__ = "quotations"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id = Column(UUID(as_uuid=True), ForeignKey("service_requests.id", ondelete="CASCADE"))
    
    # Base Pricing Components
    base_hookup_fee = Column(DECIMAL(10, 2), default=0)
    distance_km = Column(DECIMAL(10, 2), nullable=True)
    distance_miles = Column(DECIMAL(10, 2), nullable=True)
    distance_cost = Column(DECIMAL(10, 2), default=0)
    
    free_miles_included = Column(Integer, default=0)
    extra_miles = Column(DECIMAL(10, 2), nullable=True)
    extra_miles_cost = Column(DECIMAL(10, 2), default=0)
    
    service_charge = Column(DECIMAL(10, 2), default=0)
    vehicle_type_charge = Column(DECIMAL(10, 2), default=0)
    
    # Time-based charges
    night_charge = Column(DECIMAL(10, 2), default=0)
    weekend_charge = Column(DECIMAL(10, 2), default=0)
    emergency_charge = Column(DECIMAL(10, 2), default=0)
    priority_charge = Column(DECIMAL(10, 2), default=0)
    
    # Location-based charges
    highway_charge = Column(DECIMAL(10, 2), default=0)
    remote_charge = Column(DECIMAL(10, 2), default=0)
    
    # Waiting charges
    waiting_time_minutes = Column(Integer, default=0)
    waiting_charge = Column(DECIMAL(10, 2), default=0)
    
    # Additional
    toll_charges = Column(DECIMAL(10, 2), default=0)
    permit_charges = Column(DECIMAL(10, 2), default=0)
    tax_percentage = Column(DECIMAL(5, 2), default=0)
    tax_amount = Column(DECIMAL(10, 2), default=0)
    
    # Total calculations
    subtotal = Column(DECIMAL(10, 2), default=0)
    total_amount = Column(DECIMAL(10, 2), default=0)
    
    # Status
    is_accepted = Column(Boolean, default=False)
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    service_request = relationship("ServiceRequest", back_populates="quotation")
    payment = relationship("Payment", back_populates="quotation", uselist=False)


# =====================================================
# PAYMENTS TABLE
# =====================================================
class Payment(Base):
    __tablename__ = "payments"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id = Column(UUID(as_uuid=True), ForeignKey("service_requests.id"))
    quotation_id = Column(UUID(as_uuid=True), ForeignKey("quotations.id"), nullable=True)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    
    payment_method = Column(Enum(PaymentMethod), nullable=True)
    payment_status = Column(Enum(PaymentStatus), default=PaymentStatus.PENDING)
    
    amount = Column(DECIMAL(10, 2), nullable=False)
    stripe_payment_intent_id = Column(String(255), nullable=True)
    stripe_charge_id = Column(String(255), nullable=True)
    
    payment_gateway_response = Column(JSON, nullable=True)
    
    paid_at = Column(DateTime(timezone=True), nullable=True)
    refunded_at = Column(DateTime(timezone=True), nullable=True)
    refund_amount = Column(DECIMAL(10, 2), nullable=True)
    refund_reason = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    service_request = relationship("ServiceRequest", back_populates="payment")
    quotation = relationship("Quotation", back_populates="payment")
    customer = relationship("User", back_populates="payments")
    refund_request = relationship("RefundRequest", back_populates="payment", uselist=False)


# =====================================================
# PRICING CONFIGURATION
# =====================================================
class PricingConfig(Base):
    __tablename__ = "pricing_config"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    config_key = Column(String(100), unique=True, nullable=False)
    config_value = Column(DECIMAL(10, 2), nullable=True)
    config_text = Column(Text, nullable=True)
    config_json = Column(JSON, nullable=True)
    description = Column(Text, nullable=True)
    updated_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class VehicleTypePricing(Base):
    __tablename__ = "vehicle_type_pricing"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vehicle_type = Column(Enum(VehicleType), unique=True, nullable=False)
    base_charge = Column(DECIMAL(10, 2), nullable=False)
    per_mile_multiplier = Column(DECIMAL(3, 2), default=1.00)
    description = Column(Text, nullable=True)


class ServiceTypePricing(Base):
    __tablename__ = "service_type_pricing"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_type = Column(Enum(ServiceType), unique=True, nullable=False)
    flat_charge = Column(DECIMAL(10, 2), nullable=False)
    travel_included = Column(Boolean, default=False)
    description = Column(Text, nullable=True)


# =====================================================
# QUEUE MANAGEMENT
# =====================================================
class ServiceQueue(Base):
    __tablename__ = "service_queue"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id = Column(UUID(as_uuid=True), ForeignKey("service_requests.id"), unique=True)
    queue_position = Column(Integer, nullable=False)
    priority_level = Column(Integer, default=0)  # 0:normal, 1:priority, 2:emergency
    estimated_duration_minutes = Column(Integer, nullable=True)
    estimated_eta = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True)
    added_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    service_request = relationship("ServiceRequest", back_populates="queue_entry")


# =====================================================
# NOTIFICATIONS TABLE
# =====================================================
class Notification(Base):
    __tablename__ = "notifications"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    request_id = Column(UUID(as_uuid=True), ForeignKey("service_requests.id"), nullable=True)
    type = Column(Enum(NotificationType))
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    data = Column(JSON, nullable=True)
    is_read = Column(Boolean, default=False)
    is_sent = Column(Boolean, default=False)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    user = relationship("User", back_populates="notifications")
    service_request = relationship("ServiceRequest", back_populates="notifications")


# =====================================================
# REVIEWS & RATINGS
# =====================================================
class Review(Base):
    __tablename__ = "reviews"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id = Column(UUID(as_uuid=True), ForeignKey("service_requests.id"), unique=True)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    rating = Column(Integer)  # 1-5
    review_text = Column(Text, nullable=True)
    response_text = Column(Text, nullable=True)
    is_approved = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    service_request = relationship("ServiceRequest", back_populates="review")
    customer = relationship("User", back_populates="reviews")


# =====================================================
# SERVICE AREAS
# =====================================================
class ServiceArea(Base):
    __tablename__ = "service_areas"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    area_name = Column(String(100), nullable=False)
    zip_codes = Column(ARRAY(String), nullable=True)
    city = Column(String(100), nullable=True)
    state = Column(String(50), nullable=True)
    country = Column(String(50), default="USA")
    is_active = Column(Boolean, default=True)
    coordinates = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# =====================================================
# EARNINGS & TRANSACTIONS
# =====================================================
class Earning(Base):
    __tablename__ = "earnings"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id = Column(UUID(as_uuid=True), ForeignKey("service_requests.id"))
    total_amount = Column(DECIMAL(10, 2), nullable=True)
    platform_fee = Column(DECIMAL(10, 2), nullable=True)
    admin_earning = Column(DECIMAL(10, 2), nullable=True)
    tax_amount = Column(DECIMAL(10, 2), nullable=True)
    settlement_status = Column(String(20), default="pending")
    settled_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    service_request = relationship("ServiceRequest", back_populates="earnings")


# =====================================================
# AUDIT LOGS
# =====================================================
class AuditLog(Base):
    __tablename__ = "audit_logs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    action = Column(String(100), nullable=False)
    entity_type = Column(String(50), nullable=True)
    entity_id = Column(UUID(as_uuid=True), nullable=True)
    old_values = Column(JSON, nullable=True)
    new_values = Column(JSON, nullable=True)
    ip_address = Column(INET, nullable=True)
    user_agent = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    user = relationship("User", back_populates="audit_logs")


# =====================================================
# REFUND REQUESTS
# =====================================================
class RefundRequest(Base):
    __tablename__ = "refund_requests"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id = Column(UUID(as_uuid=True), ForeignKey("service_requests.id"))
    payment_id = Column(UUID(as_uuid=True), ForeignKey("payments.id"))
    customer_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    amount = Column(DECIMAL(10, 2), nullable=False)
    reason = Column(Text, nullable=True)
    status = Column(String(20), default="pending")
    processed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    payment = relationship("Payment", back_populates="refund_request")