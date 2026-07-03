from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

def hash(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password:str , hashed_password:str):
    return pwd_context.verify(plain_password,hashed_password)

def to_kobo(naira: float) -> int:
    """Convert Naira to kobo. ₦15,000 → 1500000"""
    return int(naira * 100)


def from_kobo(kobo: int) -> float:
    """Convert kobo to Naira. 1500000 → ₦15,000.0"""
    return kobo / 100

