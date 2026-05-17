from app.core.database import SessionLocal
from app.models.deployment import Deployment

db = SessionLocal()
try:
    deployments = db.query(Deployment).all()
    print("All deployments in DB:")
    for d in deployments:
        print(f"ID={d.id}, tenant={d.tenant_id}, subdomain={d.subdomain}, status={d.status}")
finally:
    db.close()
