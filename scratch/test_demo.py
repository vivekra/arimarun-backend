import sys
import os
import uuid
import json

# Add current dir to path
sys.path.append(os.getcwd())

from app.core.database import SessionLocal
from app.models.user import User
from app.models.tenant import Tenant
from app.models.subscription import Subscription
from app.models.deployment import Deployment
from app.tasks.webhook_tasks import process_paymenter_webhook_task
from app.models.events import WebhookEvent

def test_demo():
    db = SessionLocal()
    try:
        # 1. Create a test user
        email = f"test_{uuid.uuid4().hex[:6]}@example.com"
        new_user = User(
            email=email,
            hashed_password="fakehash",
            full_name="Demo User"
        )
        db.add(new_user)
        db.flush()
        
        # 2. Create a tenant
        new_tenant = Tenant(
            name="Demo Workspace",
            owner_id=new_user.id
        )
        db.add(new_tenant)
        db.commit()
        db.refresh(new_tenant)
        
        tenant_id = str(new_tenant.id)
        print(f"Created Tenant ID: {tenant_id}")
        
        # 3. Simulate Paymenter Webhook Event
        event_id = f"pay_{uuid.uuid4().hex[:8]}"
        payload = {
            "id": event_id,
            "event": "subscription.created",
            "data": {
                "id": f"sub_{uuid.uuid4().hex[:8]}",
                "tenant_id": tenant_id,
                "plan_name": "Growth",
                "limits": {"mem_limit": "2g", "cpu_quota": 200000}
            }
        }
        
        new_event = WebhookEvent(
            event_id=event_id,
            event_type="subscription.created",
            payload=payload,
            processing_status="pending"
        )
        db.add(new_event)
        db.commit()
        print(f"Simulated Webhook Event Created: {event_id}")
        
        # 4. Process the task (manually call the task function)
        print("Processing Paymenter Webhook Task...")
        process_paymenter_webhook_task(event_id)
        
        # 5. Verify Results
        db.refresh(new_tenant)
        sub = db.query(Subscription).filter(Subscription.tenant_id == new_tenant.id).first()
        dep = db.query(Deployment).filter(Deployment.tenant_id == new_tenant.id).first()
        
        if sub:
            print(f"SUCCESS: Subscription created for {sub.plan_name}")
        else:
            print("FAILED: Subscription not found")
            
        if dep:
            print(f"SUCCESS: Deployment created: {dep.name} (Status: {dep.status})")
            print(f"Image: {dep.image}")
        else:
            print("FAILED: Deployment not found")
            
    finally:
        db.close()

if __name__ == "__main__":
    test_demo()
