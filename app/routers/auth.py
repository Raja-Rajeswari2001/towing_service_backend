from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session
from datetime import timedelta, datetime
from typing import Dict, Optional
import secrets
import traceback
import httpx

from app.database import get_db
from app.models import User, UserRole
from app.schemas import (
    UserCreate, UserLogin, TokenResponse, UserResponse,
    PhoneLogin, OTPVerify, EmailOTPRequest, EmailOTPVerify
)
from app.utils import (
    verify_password, get_password_hash, create_access_token,
    generate_otp
)
from app.auth import get_current_user
from app.config import settings

router = APIRouter(prefix="/auth", tags=["Authentication"])

# OTP stores
otp_store: Dict[str, dict] = {}
email_otp_store: Dict[str, dict] = {}
google_states = {}


# =====================================================
# Helper Functions
# =====================================================
def send_otp_dev(phone_number: str, otp_code: str):
    """Development OTP sender"""
    print(f"\n{'='*50}")
    print(f"🔐 OTP for {phone_number}: {otp_code}")
    print(f"Valid for: 5 minutes")
    print(f"{'='*50}\n")
    return True


def send_email_otp_dev(email: str, otp_code: str):
    """Development email OTP sender"""
    print(f"\n{'='*50}")
    print(f"📧 Email OTP for {email}: {otp_code}")
    print(f"Valid for: 5 minutes")
    print(f"{'='*50}\n")
    return True

def send_email_otp_production(email: str, otp_code: str):
    """Production email OTP sender with beautiful HTML design"""
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    from datetime import datetime
    
    try:
        smtp_server = settings.SMTP_SERVER
        smtp_port = settings.SMTP_PORT
        smtp_username = settings.SMTP_USERNAME
        smtp_password = settings.SMTP_PASSWORD
        
        # Calculate expiry time
        current_time = datetime.now().strftime("%I:%M %p")
        expiry_time = (datetime.now() + timedelta(minutes=5)).strftime("%I:%M %p")
        
        msg = MIMEMultipart('alternative')
        msg['From'] = f"Towing Service <{smtp_username}>"
        msg['To'] = email
        msg['Subject'] = '🔐 Your OTP Verification Code - Towing Service'
        
        # Beautiful HTML email template
        html_content = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>OTP Verification</title>
            <style>
                @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
                
                * {{
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }}
                
                body {{
                    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    margin: 0;
                    padding: 20px;
                    -webkit-font-smoothing: antialiased;
                }}
                
                .container {{
                    max-width: 560px;
                    margin: 0 auto;
                    background: #ffffff;
                    border-radius: 24px;
                    overflow: hidden;
                    box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
                    animation: slideIn 0.5s ease-out;
                }}
                
                @keyframes slideIn {{
                    from {{
                        opacity: 0;
                        transform: translateY(-30px);
                    }}
                    to {{
                        opacity: 1;
                        transform: translateY(0);
                    }}
                }}
                
                .header {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    padding: 40px 30px;
                    text-align: center;
                    position: relative;
                    overflow: hidden;
                }}
                
                .header::before {{
                    content: '';
                    position: absolute;
                    top: -50%;
                    right: -50%;
                    width: 200%;
                    height: 200%;
                    background: radial-gradient(circle, rgba(255,255,255,0.1) 0%, transparent 70%);
                    animation: pulse 4s ease-in-out infinite;
                }}
                
                @keyframes pulse {{
                    0%, 100% {{ transform: scale(1); opacity: 0.5; }}
                    50% {{ transform: scale(1.1); opacity: 0.3; }}
                }}
                
                .logo-icon {{
                    font-size: 56px;
                    margin-bottom: 16px;
                    position: relative;
                    z-index: 1;
                }}
                
                .header h1 {{
                    color: white;
                    font-size: 28px;
                    font-weight: 700;
                    margin: 0;
                    letter-spacing: -0.5px;
                    position: relative;
                    z-index: 1;
                }}
                
                .header p {{
                    color: rgba(255, 255, 255, 0.9);
                    margin-top: 8px;
                    font-size: 14px;
                    position: relative;
                    z-index: 1;
                }}
                
                .content {{
                    padding: 40px 35px;
                    background: white;
                }}
                
                .greeting {{
                    font-size: 18px;
                    color: #1a1a2e;
                    margin-bottom: 20px;
                    font-weight: 600;
                }}
                
                .greeting span {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    -webkit-background-clip: text;
                    -webkit-text-fill-color: transparent;
                    background-clip: text;
                }}
                
                .message {{
                    color: #4a5568;
                    line-height: 1.6;
                    margin-bottom: 25px;
                    font-size: 15px;
                }}
                
                .otp-container {{
                    background: linear-gradient(135deg, #f6f9fc 0%, #eef2f7 100%);
                    border-radius: 20px;
                    padding: 35px;
                    text-align: center;
                    margin: 25px 0;
                    position: relative;
                    border: 2px solid rgba(102, 126, 234, 0.1);
                }}
                
                .otp-label {{
                    font-size: 12px;
                    text-transform: uppercase;
                    letter-spacing: 3px;
                    color: #667eea;
                    margin-bottom: 15px;
                    font-weight: 600;
                }}
                
                .otp-code {{
                    font-size: 48px;
                    font-weight: 800;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    -webkit-background-clip: text;
                    -webkit-text-fill-color: transparent;
                    background-clip: text;
                    letter-spacing: 8px;
                    font-family: 'Courier New', monospace;
                    margin: 10px 0;
                }}
                
                .otp-expiry {{
                    display: inline-block;
                    background: rgba(102, 126, 234, 0.1);
                    padding: 6px 12px;
                    border-radius: 20px;
                    font-size: 12px;
                    color: #667eea;
                    margin-top: 10px;
                }}
                
                .info-grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                    gap: 15px;
                    margin: 25px 0;
                }}
                
                .info-card {{
                    background: #f8fafc;
                    padding: 15px;
                    border-radius: 12px;
                    text-align: center;
                    transition: transform 0.2s;
                }}
                
                .info-card:hover {{
                    transform: translateY(-2px);
                }}
                
                .info-emoji {{
                    font-size: 24px;
                    margin-bottom: 8px;
                }}
                
                .info-title {{
                    font-size: 13px;
                    font-weight: 600;
                    color: #1a1a2e;
                    margin-bottom: 4px;
                }}
                
                .info-desc {{
                    font-size: 11px;
                    color: #64748b;
                }}
                
                .warning-box {{
                    background: #fef3c7;
                    border-left: 4px solid #f59e0b;
                    padding: 15px 20px;
                    margin: 25px 0;
                    border-radius: 8px;
                }}
                
                .warning-title {{
                    font-size: 13px;
                    font-weight: 600;
                    color: #92400e;
                    margin-bottom: 5px;
                }}
                
                .warning-text {{
                    font-size: 12px;
                    color: #78350f;
                    line-height: 1.5;
                }}
                
                .button {{
                    display: inline-block;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    text-decoration: none;
                    padding: 14px 35px;
                    border-radius: 12px;
                    font-weight: 600;
                    font-size: 14px;
                    margin: 15px 0;
                    transition: transform 0.2s, box-shadow 0.2s;
                    box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);
                }}
                
                .button:hover {{
                    transform: translateY(-2px);
                    box-shadow: 0 6px 20px rgba(102, 126, 234, 0.4);
                }}
                
                .footer {{
                    background: #f8fafc;
                    padding: 30px;
                    text-align: center;
                    border-top: 1px solid #e2e8f0;
                }}
                
                .footer p {{
                    color: #64748b;
                    font-size: 12px;
                    margin: 5px 0;
                    line-height: 1.5;
                }}
                
                .footer a {{
                    color: #667eea;
                    text-decoration: none;
                }}
                
                .social-icons {{
                    margin: 15px 0;
                }}
                
                .social-icons span {{
                    display: inline-block;
                    margin: 0 8px;
                    font-size: 20px;
                    cursor: default;
                }}
                
                @media (max-width: 600px) {{
                    .content {{
                        padding: 25px 20px;
                    }}
                    .otp-code {{
                        font-size: 36px;
                        letter-spacing: 5px;
                    }}
                    .info-grid {{
                        grid-template-columns: 1fr;
                    }}
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <div class="logo-icon">🔐</div>
                    <h1>Email Verification</h1>
                    <p>Secure access to your account</p>
                </div>
                
                <div class="content">
                    <div class="greeting">
                        Hello <span>{email.split('@')[0]}</span>! 👋
                    </div>
                    
                    <div class="message">
                        We received a request to verify your email address for your Towing Service account. 
                        Please use the verification code below to complete your authentication.
                    </div>
                    
                    <div class="otp-container">
                        <div class="otp-label">YOUR VERIFICATION CODE</div>
                        <div class="otp-code">{otp_code}</div>
                        <div class="otp-expiry">
                            ⏰ Expires at {expiry_time}
                        </div>
                    </div>
                    
                    <div class="info-grid">
                        <div class="info-card">
                            <div class="info-emoji">⏱️</div>
                            <div class="info-title">5 Minutes Valid</div>
                            <div class="info-desc">Code expires after 5 minutes</div>
                        </div>
                        <div class="info-card">
                            <div class="info-emoji">🔄</div>
                            <div class="info-title">One Time Use</div>
                            <div class="info-desc">Valid for single use only</div>
                        </div>
                        <div class="info-card">
                            <div class="info-emoji">🔒</div>
                            <div class="info-title">Secure</div>
                            <div class="info-desc">End-to-end encrypted</div>
                        </div>
                    </div>
                    
                    <div class="warning-box">
                        <div class="warning-title">⚠️ Security Alert</div>
                        <div class="warning-text">
                            Never share this OTP with anyone, including our support team. 
                            We will never ask you for your verification code.
                        </div>
                    </div>
                    
                    <div style="text-align: center;">
                        <div class="button" style="cursor: default;">🔐 Verify Your Account</div>
                    </div>
                </div>
                
                <div class="footer">
                    <p>Need help? Contact our support team</p>
                    <p><a href="mailto:support@towingservice.com">support@towingservice.com</a> | +1 (555) 123-4567</p>
                    <div class="social-icons">
                        <span>📱</span>
                        <span>🐦</span>
                        <span>📘</span>
                        <span>📷</span>
                    </div>
                    <p style="margin-top: 20px;">&copy; 2024 Towing Service. All rights reserved.</p>
                    <p style="font-size: 11px;">This is an automated message, please do not reply to this email.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Plain text version as fallback
        text_content = f"""
🔐 YOUR OTP VERIFICATION CODE

Hello {email.split('@')[0]}!

Your verification code is: {otp_code}

⏰ This code expires at {expiry_time}

Important Security Information:
• Never share this OTP with anyone
• This code is valid for one use only
• Valid for 5 minutes only

If you didn't request this code, please ignore this email or contact our support team.

Need help? Contact us at support@towingservice.com

© 2024 Towing Service. All rights reserved.
        """
        
        # Attach both versions
        msg.attach(MIMEText(text_content, 'plain'))
        msg.attach(MIMEText(html_content, 'html'))
        
        # Send email
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(smtp_username, smtp_password)
            server.send_message(msg)
        
        print(f"✅ Beautiful email OTP sent successfully to {email}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to send email OTP: {e}")
        print(f"Error type: {type(e).__name__}")
        print(f"Error details: {str(e)}")
        return False


def send_email_otp(email: str, otp_code: str):
    """Wrapper function to send email OTP with fallback"""
    from app.utils import send_email_otp as send_email_otp_util
    
    # Try using the production/development function first
    try:
        if settings.ENVIRONMENT == "production":
            result = send_email_otp_production(email, otp_code)
        else:
            # In development, still try to send but also print to console
            print(f"\n{'='*60}")
            print(f"📧 DEVELOPMENT MODE - Email OTP")
            print(f"To: {email}")
            print(f"OTP Code: {otp_code}")
            print(f"Valid for: 5 minutes")
            print(f"{'='*60}\n")
            
            # Try to send real email even in development
            result = send_email_otp_production(email, otp_code)
            
            if not result:
                print("⚠️ Could not send real email, OTP printed above for testing")
        
        return result
    except Exception as e:
        print(f"❌ Email sending failed: {e}")
        print(f"📧 OTP for {email}: {otp_code}")
        return False


# =====================================================
# Email/Password Auth Endpoints
# =====================================================
@router.post("/register", response_model=TokenResponse)
async def register(user_data: UserCreate, db: Session = Depends(get_db)):
    try:
        print(f"Registration attempt for: {user_data.email or user_data.phone_number}")
        
        # Validate contact info
        if not user_data.email and not user_data.phone_number:
            raise HTTPException(status_code=400, detail="Either email or phone number is required")
        
        if user_data.email:
            existing_user = db.query(User).filter(User.email == user_data.email).first()
            if existing_user:
                raise HTTPException(status_code=400, detail="Email already registered")
        
        if user_data.phone_number:
            existing_user = db.query(User).filter(User.phone_number == user_data.phone_number).first()
            if existing_user:
                raise HTTPException(status_code=400, detail="Phone number already registered")
        
        # Validate role - only allow admin if specific conditions (optional security)
        role = user_data.role if user_data.role else UserRole.CUSTOMER
        
        # Optional: Add security check for admin registration
        # Only allow admin registration if a secret key is provided or if no admin exists
        if role == UserRole.ADMIN:
            # Check if any admin already exists
            existing_admin = db.query(User).filter(User.role == UserRole.ADMIN).first()
            if existing_admin:
                # You can either prevent or allow based on your business logic
                print(f"⚠️ Warning: Admin already exists. New admin user not allowed.")
                # Option 1: Prevent creating another admin
                raise HTTPException(status_code=403, detail="Admin already exists. Cannot create another admin.")
                # Option 2: Still allow but log it (comment the above line)
        
        # Hash password with automatic truncation
        hashed_password = None
        if user_data.password:
            print(f"Original password length: {len(user_data.password)} chars, {len(user_data.password.encode('utf-8'))} bytes")
            hashed_password = get_password_hash(user_data.password)
        
        new_user = User(
            email=user_data.email,
            phone_number=user_data.phone_number,
            password_hash=hashed_password,
            first_name=user_data.first_name,
            last_name=user_data.last_name,
            role=role,  # Use the role from request instead of hardcoding CUSTOMER
            is_verified=True
        )
        
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        # Create access token
        access_token = create_access_token(data={"sub": str(new_user.id)})
        
        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            user=UserResponse.model_validate(new_user)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Registration error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/login", response_model=TokenResponse)
async def login(login_data: UserLogin, db: Session = Depends(get_db)):
    try:
        print(f"Login attempt for: {login_data.email}")
        
        user = db.query(User).filter(User.email == login_data.email).first()
        
        if not user or not verify_password(login_data.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        access_token = create_access_token(data={"sub": str(user.id)})
        
        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            user=UserResponse.model_validate(user)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Login error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================
# Phone OTP Endpoints
# =====================================================
@router.post("/send-otp")
async def send_otp(phone_data: PhoneLogin, background_tasks: BackgroundTasks):
    try:
        phone_number = phone_data.phone_number
        print(f"Sending OTP to: {phone_number}")
        
        if not phone_number or len(phone_number) < 10:
            raise HTTPException(status_code=400, detail="Invalid phone number")
        
        otp_code = generate_otp()
        
        otp_store[phone_number] = {
            "otp": otp_code,
            "expires_at": datetime.utcnow() + timedelta(minutes=5),
            "attempts": 0
        }
        
        background_tasks.add_task(send_otp_dev, phone_number, otp_code)
        
        response = {"message": "OTP sent successfully"}
        if settings.ENVIRONMENT != "production":
            response["debug_otp"] = otp_code
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Send OTP error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/verify-otp", response_model=TokenResponse)
async def verify_otp(verify_data: OTPVerify, db: Session = Depends(get_db)):
    try:
        phone_number = verify_data.phone_number
        otp_code = verify_data.otp_code
        
        stored_otp = otp_store.get(phone_number)
        
        if not stored_otp:
            raise HTTPException(status_code=400, detail="No OTP found. Please request a new OTP.")
        
        if stored_otp.get("attempts", 0) >= 3:
            del otp_store[phone_number]
            raise HTTPException(status_code=400, detail="Too many failed attempts. Please request a new OTP.")
        
        if stored_otp["expires_at"] < datetime.utcnow():
            del otp_store[phone_number]
            raise HTTPException(status_code=400, detail="OTP expired. Please request a new OTP.")
        
        if stored_otp["otp"] != otp_code:
            stored_otp["attempts"] = stored_otp.get("attempts", 0) + 1
            remaining = 3 - stored_otp["attempts"]
            raise HTTPException(status_code=400, detail=f"Invalid OTP. {remaining} attempts remaining.")
        
        user = db.query(User).filter(User.phone_number == phone_number).first()
        
        if not user:
            user = User(
                phone_number=phone_number,
                first_name=f"User{phone_number[-4:]}",
                role=UserRole.CUSTOMER,
                is_verified=True
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        
        del otp_store[phone_number]
        
        access_token = create_access_token(data={"sub": str(user.id)})
        
        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            user=UserResponse.model_validate(user)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Verify OTP error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================
# Email OTP Endpoints
# =====================================================
@router.post("/send-email-otp")
async def send_email_otp_endpoint(
    email_data: EmailOTPRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    try:
        email = email_data.email
        print(f"Sending email OTP to: {email}")
        
        if email_data.check_existing:
            existing_user = db.query(User).filter(User.email == email).first()
            if not existing_user:
                raise HTTPException(status_code=404, detail="Email not registered")
        
        otp_code = generate_otp()
        
        email_otp_store[email] = {
            "otp": otp_code,
            "expires_at": datetime.utcnow() + timedelta(minutes=5),
            "attempts": 0,
            "created_at": datetime.utcnow(),
            "purpose": email_data.purpose
        }
        
        background_tasks.add_task(send_email_otp, email, otp_code)
        
        response = {"message": "Email OTP sent successfully"}
        if settings.ENVIRONMENT != "production":
            response["debug_otp"] = otp_code
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Send email OTP error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/verify-email-otp", response_model=TokenResponse)
async def verify_email_otp(
    verify_data: EmailOTPVerify,
    db: Session = Depends(get_db)
):
    try:
        email = verify_data.email
        otp_code = verify_data.otp_code
        purpose = verify_data.purpose
        
        stored_data = email_otp_store.get(email)
        
        if not stored_data:
            raise HTTPException(status_code=400, detail="No OTP found. Please request a new OTP.")
        
        if stored_data.get("attempts", 0) >= 3:
            del email_otp_store[email]
            raise HTTPException(status_code=400, detail="Too many failed attempts. Please request a new OTP.")
        
        if stored_data["expires_at"] < datetime.utcnow():
            del email_otp_store[email]
            raise HTTPException(status_code=400, detail="OTP expired. Please request a new OTP.")
        
        if stored_data["otp"] != otp_code:
            stored_data["attempts"] = stored_data.get("attempts", 0) + 1
            remaining = 3 - stored_data["attempts"]
            raise HTTPException(status_code=400, detail=f"Invalid OTP. {remaining} attempts remaining.")
        
        user = db.query(User).filter(User.email == email).first()
        
        if not user and purpose == "login":
            user = User(
                email=email,
                first_name=verify_data.full_name or email.split('@')[0],
                role=UserRole.CUSTOMER,
                is_verified=True
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        del email_otp_store[email]
        
        access_token = create_access_token(data={"sub": str(user.id)})
        
        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            user=UserResponse.model_validate(user)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Verify email OTP error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/resend-email-otp")
async def resend_email_otp(
    email_data: EmailOTPRequest,
    background_tasks: BackgroundTasks
):
    try:
        email = email_data.email
        
        existing_data = email_otp_store.get(email)
        if existing_data:
            time_elapsed = (datetime.utcnow() - existing_data.get("created_at", datetime.utcnow())).total_seconds()
            if time_elapsed < 60:
                wait_time = 60 - int(time_elapsed)
                raise HTTPException(status_code=429, detail=f"Please wait {wait_time} seconds before requesting another OTP")
        
        otp_code = generate_otp()
        
        email_otp_store[email] = {
            "otp": otp_code,
            "expires_at": datetime.utcnow() + timedelta(minutes=5),
            "attempts": 0,
            "created_at": datetime.utcnow(),
            "purpose": email_data.purpose
        }
        
        background_tasks.add_task(send_email_otp, email, otp_code)
        
        response = {"message": "Email OTP resent successfully"}
        if settings.ENVIRONMENT != "production":
            response["debug_otp"] = otp_code
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Resend email OTP error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================
# Google OAuth Endpoints
# =====================================================
@router.get("/google/login")
async def google_login():
    """Initiate Google OAuth login"""
    try:
        if not settings.GOOGLE_CLIENT_ID or settings.GOOGLE_CLIENT_ID == "":
            return JSONResponse(
                status_code=400,
                content={"detail": "Google OAuth not configured. Please check your .env file."}
            )
        
        state = secrets.token_urlsafe(32)
        google_states[state] = {"created_at": datetime.utcnow()}
        
        auth_url = (
            "https://accounts.google.com/o/oauth2/v2/auth?"
            f"client_id={settings.GOOGLE_CLIENT_ID}&"
            "response_type=code&"
            f"redirect_uri={settings.GOOGLE_REDIRECT_URI}&"
            "scope=openid email profile&"
            f"state={state}&"
            "access_type=online"
        )
        
        return RedirectResponse(url=auth_url)
        
    except Exception as e:
        print(f"Google login error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/google/callback", response_model=TokenResponse)
async def google_callback(
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    db: Session = Depends(get_db)
):
    try:
        if error:
            raise HTTPException(status_code=400, detail=f"Google OAuth error: {error}")
        
        if not code:
            raise HTTPException(status_code=400, detail="Authorization code missing")
        
        if not state or state not in google_states:
            raise HTTPException(status_code=400, detail="Invalid state parameter")
        
        del google_states[state]
        
        # Exchange code for tokens
        token_url = "https://oauth2.googleapis.com/token"
        token_data = {
            "code": code,
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code"
        }
        
        async with httpx.AsyncClient() as client:
            token_response = await client.post(token_url, data=token_data)
            tokens = token_response.json()
            
            if "error" in tokens:
                raise HTTPException(status_code=400, detail=f"Token error: {tokens.get('error_description')}")
            
            access_token = tokens.get("access_token")
            
            userinfo_response = await client.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            user_info = userinfo_response.json()
        
        email = user_info.get("email")
        if not email:
            raise HTTPException(status_code=400, detail="Email not provided by Google")
        
        full_name = user_info.get("name", email.split('@')[0])
        profile_picture = user_info.get("picture")
        
        user = db.query(User).filter(User.email == email).first()
        
        if not user:
            user = User(
                email=email,
                first_name=full_name.split()[0] if ' ' in full_name else full_name,
                last_name=full_name.split()[1] if ' ' in full_name and len(full_name.split()) > 1 else None,
                profile_picture=profile_picture,
                role=UserRole.CUSTOMER,
                is_verified=True
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        
        access_token_jwt = create_access_token(data={"sub": str(user.id)})
        
        return TokenResponse(
            access_token=access_token_jwt,
            token_type="bearer",
            user=UserResponse.model_validate(user)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Google callback error: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================
# User Info Endpoint
# =====================================================
@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return UserResponse.model_validate(current_user)