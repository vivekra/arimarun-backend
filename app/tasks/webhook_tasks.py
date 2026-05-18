"""
webhook_tasks.py — Background task to process Paymenter billing webhooks.

Key design:
- subscription.created / upgraded → UPDATE the existing trial sub IN-PLACE
  (never INSERT a new row — prevents UniqueViolation on paymenter_subscription_id)
- subscription.cancelled / suspended → transition status + stop containers
- subscription.reactivated → restore to active
"""
import logging
from datetime import datetime, timezone, timedelta
from calendar import monthrange

from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.events import WebhookEvent
from app.models.product import Product
from app.models.subscription import Subscription
from app.models.resource import Resource
from app.models.deployment import Deployment
from app.tasks.deployment_tasks import stop_deployment_task, provision_deployment_task
from app.core.redis import default_queue

logger = logging.getLogger(__name__)


def _compute_renews_at() -> datetime:
    """First day of next month at midnight UTC."""
    now = datetime.now(timezone.utc)
    days_in_month = monthrange(now.year, now.month)[1]
    return now.replace(day=days_in_month, hour=23, minute=59, second=59) + timedelta(seconds=1)


def process_paymenter_webhook_task(event_id: str):
    db: Session = SessionLocal()
    event = db.query(WebhookEvent).filter(WebhookEvent.event_id == event_id).first()

    if not event or event.processing_status != "pending":
        db.close()
        return

    try:
        payload    = event.payload
        event_type = event.event_type
        data       = payload.get("data", {})
        tenant_id  = data.get("tenant_id")

        if not tenant_id:
            raise ValueError("tenant_id missing in webhook payload")

        logger.info(f"Processing webhook — event_type={event_type} tenant_id={tenant_id}")

        # ── subscription.created / subscription.upgraded ─────────────────────
        if event_type in ("subscription.created", "subscription.upgraded"):
            # Resolve product from the catalog using slug from Paymenter payload
            product_slug  = data.get("product_slug")
            paymenter_id  = data.get("id")
            plan_name     = data.get("plan_name", "basic").lower()

            product = None
            if product_slug:
                product = (
                    db.query(Product)
                    .filter(Product.extra["slug"].astext == product_slug)
                    .first()
                )

            # Derive limits from product; fall back to payload limits
            if product:
                plan_limits = {
                    "cpu":          product.cpu,
                    "memory":       product.memory,
                    "deployments":  product.max_instances,
                    "storage_gb":   product.storage_gb,
                }
                plan_name = product.name.lower().replace(" ", "-")
                logger.info(f"Resolved product={product.name} (slug={product_slug})")
            else:
                plan_limits = data.get("limits", {"cpu": "1.0", "memory": "1g", "deployments": 2})
                logger.warning(f"Product slug='{product_slug}' not found — using payload limits")

            # ── Upgrade: update existing subscription IN-PLACE ────────────────
            sub = (
                db.query(Subscription)
                .filter(Subscription.tenant_id == tenant_id)
                .order_by(Subscription.created_at.desc())
                .first()
            )

            if sub:
                logger.info(
                    f"Upgrading subscription sub_id={sub.id} "
                    f"{sub.plan_name}/{sub.status} → {plan_name}/active"
                )
                sub.paymenter_subscription_id = paymenter_id
                sub.product_id    = product.id if product else sub.product_id
                sub.plan_name     = plan_name
                sub.status        = "active"
                sub.trial_ends_at = None
                sub.started_at    = datetime.now(timezone.utc)
                sub.renews_at     = _compute_renews_at()
                sub.limits        = plan_limits
            else:
                logger.warning(f"No existing subscription for tenant_id={tenant_id} — creating.")
                sub = Subscription(
                    tenant_id=tenant_id,
                    product_id=product.id if product else None,
                    paymenter_subscription_id=paymenter_id,
                    plan_name=plan_name,
                    status="active",
                    trial_ends_at=None,
                    started_at=datetime.now(timezone.utc),
                    renews_at=_compute_renews_at(),
                    limits=plan_limits,
                )
                db.add(sub)

            db.flush()

            # ── Create Resource record linked to this subscription ─────────────
            existing_resource = db.query(Resource).filter(
                Resource.tenant_id == tenant_id,
                Resource.subscription_id == sub.id,
            ).first()

            if not existing_resource:
                resource_type = product.resource_type if product else "desktop"
                new_resource = Resource(
                    tenant_id=tenant_id,
                    subscription_id=sub.id,
                    resource_type=resource_type,
                    status="provisioning",
                )
                db.add(new_resource)
                db.flush()
                logger.info(f"Resource record created — resource_id={new_resource.id}")

            # ── Provision desktop workspace if none exists ────────────────────
            if not product or product.resource_type == "desktop":
                existing_dep = db.query(Deployment).filter(
                    Deployment.tenant_id == tenant_id
                ).first()

                if not existing_dep:
                    logger.info(f"Provisioning desktop workspace for tenant_id={tenant_id}")
                    new_dep = Deployment(
                        tenant_id=tenant_id,
                        name="Primary Workspace",
                        image="kasmweb/ubuntu-focal-desktop:1.14.0",
                        subdomain=f"ws-{str(tenant_id)[:8]}",
                        status="pending",
                        specs=plan_limits,
                    )
                    db.add(new_dep)
                    db.flush()
                    default_queue.enqueue(
                        provision_deployment_task,
                        str(new_dep.id),
                        job_timeout=1800,
                    )

        # ── subscription.cancelled / subscription.suspended ───────────────────
        elif event_type in ("subscription.cancelled", "subscription.suspended"):
            sub = (
                db.query(Subscription)
                .filter(
                    Subscription.tenant_id == tenant_id,
                    Subscription.status.in_(["active", "trialing"]),
                )
                .first()
            )
            if sub:
                new_status = "cancelled" if "cancelled" in event_type else "suspended"
                logger.info(f"Transitioning sub_id={sub.id} → {new_status}")
                sub.status = new_status

                running = db.query(Deployment).filter(
                    Deployment.tenant_id == tenant_id,
                    Deployment.status == "running",
                ).all()
                for dep in running:
                    logger.info(f"Queuing stop for deployment_id={dep.id}")
                    default_queue.enqueue(stop_deployment_task, str(dep.id))

                # Suspend associated Resource records
                resources = db.query(Resource).filter(
                    Resource.tenant_id == tenant_id,
                    Resource.status == "running",
                ).all()
                for res in resources:
                    res.status = "suspended"

        # ── subscription.reactivated ──────────────────────────────────────────
        elif event_type == "subscription.reactivated":
            sub = (
                db.query(Subscription)
                .filter(Subscription.tenant_id == tenant_id)
                .order_by(Subscription.created_at.desc())
                .first()
            )
            if sub:
                logger.info(f"Reactivating sub_id={sub.id}")
                sub.status    = "active"
                sub.renews_at = _compute_renews_at()

        # ── subscription.renewed ──────────────────────────────────────────────
        elif event_type == "subscription.renewed":
            sub = (
                db.query(Subscription)
                .filter(Subscription.tenant_id == tenant_id, Subscription.status == "active")
                .first()
            )
            if sub:
                sub.renews_at = _compute_renews_at()
                logger.info(f"Renewal recorded — sub_id={sub.id} next_renew={sub.renews_at.date()}")

        else:
            logger.warning(f"Unhandled event_type={event_type} for tenant_id={tenant_id}")

        event.processing_status = "processed"
        db.commit()
        logger.info(f"Webhook event_id={event_id} processed successfully")

    except Exception as e:
        logger.exception(f"Failed to process webhook event_id={event_id}: {e}")
        try:
            event.processing_status = "failed"
            event.error_message = str(e)
            db.commit()
        except Exception as inner:
            logger.error(f"Failed to mark event as failed: {inner}")
    finally:
        db.close()
