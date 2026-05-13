import random
import secrets
import smtplib
from datetime import datetime, timedelta,timezone

from typing import Optional, Dict, Any
from passlib.context import CryptContext
from jose import JWTError, jwt
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.config import settings

# Configure bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def generate_otp(length: int = 6) -> str:
    """Generate a numeric OTP"""
    return ''.join([str(random.randint(0, 9)) for _ in range(length)])

def utc_now():
    """Return timezone-aware current UTC datetime"""
    return datetime.now(timezone.utc)


def truncate_password_for_bcrypt(password: str, max_bytes: int = 72) -> str:
    """
    Truncate password to max_bytes for bcrypt compatibility.
    Bcrypt has a 72-byte limit, so we truncate if necessary.
    """
    if not password:
        return password
    
    # Encode to bytes
    password_bytes = password.encode('utf-8')
    
    # Check if exceeds limit
    if len(password_bytes) > max_bytes:
        # Truncate to max_bytes
        truncated_bytes = password_bytes[:max_bytes]
        # Decode back to string, ignoring any incomplete characters
        truncated = truncated_bytes.decode('utf-8', errors='ignore')
        print(f"⚠️ Password truncated from {len(password_bytes)} to {len(truncated_bytes)} bytes")
        return truncated
    
    return password


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash with automatic truncation"""
    if not hashed_password or not plain_password:
        return False
    
    try:
        # Truncate password if needed for bcrypt
        truncated_password = truncate_password_for_bcrypt(plain_password)
        return pwd_context.verify(truncated_password, hashed_password)
    except Exception as e:
        print(f"Password verification error: {e}")
        return False


def get_password_hash(password: str) -> str:
    """Hash password with automatic truncation for bcrypt"""
    if not password:
        return None
    
    try:
        # Truncate password if needed for bcrypt
        truncated_password = truncate_password_for_bcrypt(password)
        return pwd_context.hash(truncated_password)
    except Exception as e:
        print(f"Password hashing error: {e}")
        # Ultimate fallback - aggressive truncation
        truncated = password.encode('utf-8')[:72].decode('utf-8', errors='ignore')
        return pwd_context.hash(truncated)


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Dict[str, Any]:
    """Decode JWT token"""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return {}


def generate_request_number() -> str:
    """Generate unique request number"""
    year_part = datetime.now().strftime('%Y')
    random_part = secrets.token_hex(4).upper()
    return f"TRK-{year_part}-{random_part}"


def calculate_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate distance between two points using Haversine formula"""
    from math import radians, sin, cos, sqrt, atan2
    
    R = 6371  # Earth's radius in km
    
    lat1, lng1, lat2, lng2 = map(radians, [lat1, lng1, lat2, lng2])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlng/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    
    return R * c


def is_night_time() -> bool:
    """Check if current time is night time (10 PM - 6 AM)"""
    current_hour = datetime.now().hour
    return current_hour >= 22 or current_hour < 6


def is_weekend() -> bool:
    """Check if current day is weekend"""
    return datetime.now().weekday() >= 5


def send_email_otp(email: str, otp_code: str) -> bool:
    """Send OTP email using SMTP"""
    if not settings.SMTP_USERNAME or not settings.SMTP_PASSWORD:
        print(f"📧 Email OTP for {email}: {otp_code}")
        return True
    
    try:
        print(f"📧 Attempting to send OTP to: {email}")
        
        # Create message
        msg = MIMEMultipart('alternative')
        from_email = getattr(settings, 'SMTP_FROM_EMAIL', settings.SMTP_USERNAME)
        from_name = getattr(settings, 'SMTP_FROM_NAME', 'Towing Service')
        msg['From'] = f"{from_name} <{from_email}>"
        msg['To'] = email
        msg['Subject'] = '🔐 Your OTP Verification Code'
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>OTP Verification</title>
        </head>
        <body>
            <div style="font-family: Arial, sans-serif; max-width: 500px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #333;">Your OTP Code</h2>
                <div style="font-size: 32px; font-weight: bold; color: #4CAF50; padding: 20px; background: #f4f4f4; text-align: center;">
                    {otp_code}
                </div>
                <p>This OTP is valid for <strong>5 minutes</strong>.</p>
                <p>If you didn't request this, please ignore this email.</p>
                <hr>
                <small style="color: #888;">This is an automated message, please do not reply.</small>
            </div>
        </body>
        </html>
        """
        
        # Plain text version
        text_content = f"""
Your OTP Code: {otp_code}

This code is valid for 5 minutes.

If you didn't request this, please ignore this email.
        """
        
        msg.attach(MIMEText(text_content, 'plain'))
        msg.attach(MIMEText(html_content, 'html'))
        
        with smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT) as server:
            server.starttls()
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.send_message(msg)
        
        print(f"✅ Email OTP sent successfully to {email}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to send email: {e}")
        print(f"📧 OTP for {email}: {otp_code}")
        return False