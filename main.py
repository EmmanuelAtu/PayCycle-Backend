from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import model
from database import engine
from routers import auth , plans, customer,suscription,webhook,dashboard, join , wallet
import httpx
from services.nomba_client import nomba
from core.config import settings
model.Base.metadata.create_all(bind=engine)


app = FastAPI()

origins = [
    "https://paycycle.princefrank269.workers.dev", #  Cloudflare production URL
    "http://localhost",
    "http://localhost:8080", 
    "https://paycycle-backend-1.onrender.com", # Render production URL
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"], # Allows all methods (GET, POST, PUT, DELETE, etc.)
    allow_headers=["*"], # Allows all headers
)

@app.get("/")
def root():
    return {"message": "Welcome to the PayCycle API"}

@app.get("/health")
def health():
    return {"status": "ok", "service": "paycycle"}

@app.head("/health")
def health():
    return {"status": "ok", "service": "paycycle"}


    
app.include_router(auth.router)   
app.include_router(plans.router)
app.include_router(customer.router)
app.include_router(suscription.router)
app.include_router(webhook.router)
app.include_router(join.router)
app.include_router(wallet.router)