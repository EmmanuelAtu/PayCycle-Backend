from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import model
from database import engine
from routers import auth , plans, customer,suscription,webhook,dashboard, join
import httpx
from services.nomba_client import nomba
from core.config import settings
model.Base.metadata.create_all(bind=engine)

app = FastAPI()

@app.get("/")
def root():
    return {"message": "Welcome to the PayCycle API"}

@app.get("/health")
def health():
    return {"status": "ok", "service": "paycycle"}

@app.head("/health")
def health():
    return {"status": "ok", "service": "paycycle"}

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi import Request

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # This will read the exact JSON the Flutter app sent
    body = await request.body()
    print(f"\n--- 422 VALIDATION ERROR ---")
    print(f"Flutter sent this body: {body.decode()}")
    print(f"FastAPI rejected it because: {exc.errors()}")
    print(f"----------------------------\n")
    
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": body.decode()},
    )

@app.get("/debug/check-order/{order_ref}")
async def check_order(order_ref: str):
    try:
        token = await nomba._get_token()
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.nomba.com/v1/checkout/order/{order_ref}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "accountId": "f666ef9b-888e-4799-85ce-acb505b28023",
                },
                timeout=15.0
            )
        return response.json()
    except Exception as e:
        return {"error": str(e)}
    
@app.get("/debug/check-webhooks")
async def check_webhooks():
    try:
        token = await nomba._get_token()
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://api.nomba.com/v1/webhooks/event-logs",
                headers={
                    "Authorization": f"Bearer {token}",
                    "accountId": "f666ef9b-888e-4799-85ce-acb505b28023",
                    "Content-Type": "application/json",
                },
                json={
                    "coreUserId": settings.NOMBA_SUB_ACCOUNT_ID,
                    "eventType": "payment_success"
                },
                timeout=15.0
            )
        return response.json()
    except Exception as e:
        return {"error": str(e)}
    
app.include_router(auth.router)   
app.include_router(plans.router)
app.include_router(customer.router)
app.include_router(suscription.router)
app.include_router(webhook.router)
app.include_router(join.router)