from app.core.database import SessionLocal
from app.models.user import User
from app.models.tenant import Tenant
from app.models.subscription import Subscription

db = SessionLocal()
try:
    user = db.query(User).filter(User.email == "vivekra@talentegra.com").first()
    if user:
        print(f"USER found: ID={user.id}, email={user.email}")
        tenant = db.query(Tenant).filter(Tenant.owner_id == user.id).first()
        if tenant:
            print(f"TENANT found: ID={tenant.id}, owner_id={tenant.owner_id}")
            subscriptions = db.query(Subscription).filter(Subscription.tenant_id == tenant.id).all()
            if subscriptions:
                for sub in subscriptions:
                    print(f"SUBSCRIPTION found: ID={sub.id}, plan_name={sub.plan_name}, status={sub.status}, paymenter_id={sub.paymenter_subscription_id}")
            else:
                print("NO SUBSCRIPTIONS found for this tenant!")
        else:
            print("NO TENANT found for this user!")
    else:
        print("USER not found!")
finally:
    db.close()
