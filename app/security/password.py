import logging
import time
from passlib.context import CryptContext

logger = logging.getLogger(__name__)

# Explicitly set rounds=12 to prevent passlib from hanging on bcrypt auto-detection
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    logger.debug("Starting password verification...")
    t0 = time.time()
    result = pwd_context.verify(plain_password, hashed_password)
    logger.debug(f"Password verification completed in {time.time() - t0:.3f}s, result={result}")
    return result

def get_password_hash(password: str) -> str:
    logger.debug("Starting password hashing...")
    t0 = time.time()
    result = pwd_context.hash(password)
    logger.debug(f"Password hashing completed in {time.time() - t0:.3f}s")
    return result
