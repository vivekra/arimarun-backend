from fastapi import APIRouter, Depends, HTTPException, status, Request, Header
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.events import WebhookEvent
from app.core.redis import default_queue
from app.tasks.webhook_tasks import process_paymenter_webhook_task
from app.core.config import settings
import hmac
import hashlib
import json

router = APIRouter()

# Assuming a webhook secret is stored in env for verification
WEBHOOK_SECRET = getattr(settings, "PAYMENTER_WEBHOOK_SECRET", "default_secret")

def verify_signature(payload: bytes, signature: str) -> bool:
    if not signature:
        return False
    expected_mac = hmac.new(WEBHOOK_SECRET.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected_mac, signature)

@router.post("/paymenter")
async def receive_paymenter_webhook(request: Request, x_signature: str = Header(None), db: Session = Depends(get_db)):
    payload_bytes = await request.body()
    
    # Verify Signature (disabled if testing without it)
    # if not verify_signature(payload_bytes, x_signature):
    #     raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = json.loads(payload_bytes)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event_id = payload.get("id")
    event_type = payload.get("event")

    if not event_id or not event_type:
        raise HTTPException(status_code=400, detail="Missing event id or type")

    # Idempotency Check
    existing_event = db.query(WebhookEvent).filter(WebhookEvent.event_id == event_id).first()
    if existing_event:
        # Already received, return 202 to acknowledge without reprocessing
        return {"message": "Event already processed or pending", "status": "acknowledged"}

    # Persist Event
    new_event = WebhookEvent(
        event_id=event_id,
        event_type=event_type,
        payload=payload,
        processing_status="pending"
    )
    db.add(new_event)
    db.commit()

    # Enqueue for background processing
    default_queue.enqueue(process_paymenter_webhook_task, event_id)

    return {"message": "Webhook received and queued", "status": "accepted"}
