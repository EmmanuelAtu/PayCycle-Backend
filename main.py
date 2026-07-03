from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import model
from database import engine
from routers import auth , plans, customer,suscription,webhook,dashboard, join

model.Base.metadata.create_all(bind=engine)

app = FastAPI()

@app.get("/")
def root():
    return {"message": "Welcome to the PayCycle API"}

@app.get("/health")
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

app.include_router(auth.router)   
app.include_router(plans.router)
app.include_router(customer.router)
app.include_router(suscription.router)
app.include_router(webhook.router)
app.include_router(join.router)