from sqlalchemy.orm import Session
from uuid import UUID
from datetime import datetime, timedelta
from typing import List, Optional

from app.models import ServiceRequest, ServiceQueue, ServiceRequestStatus


class QueueService:
    def __init__(self, db: Session):
        self.db = db
    
    async def add_to_queue(self, request_id: UUID) -> ServiceQueue:
        """Add a service request to the queue"""
        
        service_request = self.db.query(ServiceRequest).filter(
            ServiceRequest.id == request_id
        ).first()
        
        if not service_request:
            raise ValueError("Service request not found")
        
        if service_request.status != "confirmed":
            raise ValueError(f"Cannot add request with status {service_request.status} to queue")
        
        # Calculate priority level
        priority_level = 0  # Normal
        if service_request.urgency:
            if service_request.urgency.value == "priority":
                priority_level = 1
            elif service_request.urgency.value == "emergency":
                priority_level = 2
        
        # Get current max position
        max_position = self.db.query(ServiceQueue).filter(
            ServiceQueue.is_active == True
        ).count()
        
        # Create queue entry
        queue_entry = ServiceQueue(
            request_id=request_id,
            queue_position=max_position + 1,
            priority_level=priority_level,
            estimated_duration_minutes=30,  # Default
            estimated_eta=datetime.utcnow() + timedelta(minutes=30 * (max_position + 1)),
            is_active=True
        )
        
        self.db.add(queue_entry)
        
        # Update service request status
        service_request.status = "in_queue"
        service_request.queue_position = max_position + 1
        
        self.db.commit()
        self.db.refresh(queue_entry)
        
        return queue_entry
    
    async def remove_from_queue(self, request_id: UUID) -> None:
        """Remove a service request from the queue"""
        
        queue_entry = self.db.query(ServiceQueue).filter(
            ServiceQueue.request_id == request_id
        ).first()
        
        if queue_entry:
            queue_entry.is_active = False
            self.db.delete(queue_entry)
            self.db.commit()
            
            # Reorder remaining queue positions
            await self._reorder_queue()
    
    async def get_queue_order(self) -> List[dict]:
        """Get current queue order"""
        
        queue_entries = self.db.query(ServiceQueue).filter(
            ServiceQueue.is_active == True
        ).order_by(
            ServiceQueue.priority_level.desc(),
            ServiceQueue.queue_position
        ).all()
        
        result = []
        for entry in queue_entries:
            service_request = self.db.query(ServiceRequest).filter(
                ServiceRequest.id == entry.request_id
            ).first()
            
            if service_request:
                result.append({
                    "position": entry.queue_position,
                    "priority_level": entry.priority_level,
                    "request_number": service_request.request_number,
                    "service_type": service_request.service_type.value if service_request.service_type else None,
                    "urgency": service_request.urgency.value if service_request.urgency else None,
                    "estimated_eta": entry.estimated_eta
                })
        
        return result
    
    async def get_next_request(self) -> Optional[UUID]:
        """Get the next request from the queue"""
        
        next_entry = self.db.query(ServiceQueue).filter(
            ServiceQueue.is_active == True
        ).order_by(
            ServiceQueue.priority_level.desc(),
            ServiceQueue.queue_position
        ).first()
        
        if next_entry:
            return next_entry.request_id
        
        return None
    
    async def _reorder_queue(self) -> None:
        """Reorder queue positions after removal"""
        
        queue_entries = self.db.query(ServiceQueue).filter(
            ServiceQueue.is_active == True
        ).order_by(
            ServiceQueue.priority_level.desc(),
            ServiceQueue.queue_position
        ).all()
        
        for position, entry in enumerate(queue_entries, start=1):
            entry.queue_position = position
            
            # Update ETA
            minutes_offset = position * 30  # 30 minutes per job
            entry.estimated_eta = datetime.utcnow() + timedelta(minutes=minutes_offset)
        
        self.db.commit()