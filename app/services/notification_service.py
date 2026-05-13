from sqlalchemy.orm import Session
from fastapi import BackgroundTasks
from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime

from app.models import Notification, User, ServiceRequest
from app.config import settings


class NotificationService:
    def __init__(self, db: Session, background_tasks: BackgroundTasks = None):
        self.db = db
        self.background_tasks = background_tasks
    
    async def send_notification(
        self,
        user_id: UUID,
        notification_type: str,
        title: str,
        message: str,
        request_id: Optional[UUID] = None,
        data: Optional[Dict[str, Any]] = None
    ) -> Notification:
        """Create a notification for a user"""
        
        notification = Notification(
            user_id=user_id,
            type=notification_type,
            title=title,
            message=message,
            data=data,
            request_id=request_id,
            is_read=False,
            is_sent=True,
            sent_at=datetime.utcnow()
        )
        
        self.db.add(notification)
        self.db.commit()
        self.db.refresh(notification)
        
        # In production, also send push notification/email here
        if self.background_tasks:
            self.background_tasks.add_task(self._send_push_notification, user_id, title, message, data)
        
        return notification
    
    async def send_bulk_notifications(
        self,
        user_ids: list,
        notification_type: str,
        title: str,
        message: str,
        data: Optional[Dict[str, Any]] = None
    ) -> list:
        """Send notifications to multiple users"""
        
        notifications = []
        
        for user_id in user_ids:
            notification = Notification(
                user_id=user_id,
                type=notification_type,
                title=title,
                message=message,
                data=data,
                is_read=False,
                is_sent=True,
                sent_at=datetime.utcnow()
            )
            self.db.add(notification)
            notifications.append(notification)
        
        self.db.commit()
        
        return notifications
    
    async def _send_push_notification(
        self,
        user_id: UUID,
        title: str,
        message: str,
        data: Optional[Dict[str, Any]] = None
    ):
        """Send push notification (FCM or similar)"""
        
        # Implementation for FCM/APNS would go here
        # This is a placeholder for production push notification service
        
        user = self.db.query(User).filter(User.id == user_id).first()
        
        if user and user.firebase_uid:
            print(f"Sending push notification to {user.firebase_uid}: {title} - {message}")
            # Add FCM send logic here
    
    async def send_status_update(self, request_id: UUID, status: str) -> None:
        """Send status update notification for a service request"""
        
        service_request = self.db.query(ServiceRequest).filter(
            ServiceRequest.id == request_id
        ).first()
        
        if service_request:
            await self.send_notification(
                user_id=service_request.customer_id,
                notification_type="status_update",
                title="Booking Status Updated",
                message=f"Your booking {service_request.request_number} status has been updated to {status}",
                request_id=request_id
            )
    
    async def send_eta_update(self, request_id: UUID, eta_minutes: int) -> None:
        """Send ETA update notification"""
        
        service_request = self.db.query(ServiceRequest).filter(
            ServiceRequest.id == request_id
        ).first()
        
        if service_request:
            await self.send_notification(
                user_id=service_request.customer_id,
                notification_type="eta_update",
                title="ETA Update",
                message=f"Your driver will arrive in approximately {eta_minutes} minutes",
                request_id=request_id,
                data={"eta_minutes": eta_minutes}
            )