import logging
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.events import WebhookEvent
from app.models.subscription import Subscription
from app.models.deployment import Deployment
from app.tasks.deployment_tasks import stop_deployment_task, provision_deployment_task
from app.core.redis import default_queue

logger = logging.getLogger(__name__)

def process_paymenter_webhook_task(event_id: str):
    db: Session = SessionLocal()
    event = db.query(WebhookEvent).filter(WebhookEvent.event_id == event_id).first()
    
    if not event or event.processing_status != "pending":
        db.close()
        return

    try:
        payload = event.payload
        event_type = event.event_type
        
        # Paymenter payload structure assumed (adjust based on actual docs)
        # e.g., payload["data"]["tenant_id"], payload["data"]["status"]
        
        data = payload.get("data", {})
        tenant_id = data.get("tenant_id")
        
        if not tenant_id:
            raise ValueError("tenant_id missing in webhook payload")

        if event_type == "subscription.created":
            sub = Subscription(
                tenant_id=tenant_id,
                paymenter_subscription_id=data.get("id"),
                plan_name=data.get("plan_name", "Unknown"),
                status="active",
                limits=data.get("limits", {})
            )
            db.add(sub)
            db.flush() # Ensure sub is in session if needed

            # Auto-provision default desktop environment for new subscribers
            new_deployment = Deployment(
                tenant_id=tenant_id,
                name="Primary Workspace",
                image="kasmweb/ubuntu-focal-desktop:1.14.0", # Default high-performance desktop image
                subdomain=f"ws-{str(tenant_id)[:8]}",
                status="pending",
                specs=data.get("limits", {"mem_limit": "2g", "cpu_quota": 200000})
            )
            db.add(new_deployment)
            db.commit()
            
            # Enqueue the actual container spinning task
            default_queue.enqueue(provision_deployment_task, str(new_deployment.id), job_timeout=1800)
            
        elif event_type == "subscription.cancelled" or event_type == "subscription.suspended":
            sub = db.query(Subscription).filter(Subscription.tenant_id == tenant_id, Subscription.status == "active").first()
            if sub:
                sub.status = "suspended"
                # Auto-suspend all deployments for this tenant
                deployments = db.query(Deployment).filter(Deployment.tenant_id == tenant_id, Deployment.status == "running").all()
                for dep in deployments:
                    # Enqueue tasks to stop containers safely
                    default_queue.enqueue(stop_deployment_task, str(dep.id))
                    
        event.processing_status = "processed"
        db.commit()

    except Exception as e:
        logger.error(f"Failed to process webhook {event_id}: {str(e)}")
        event.processing_status = "failed"
        event.error_message = str(e)
        db.commit()
    finally:
        db.close()
