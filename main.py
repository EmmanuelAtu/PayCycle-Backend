from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import model
from database import engine
from routers import auth

model.Base.metadata.create_all(bind=engine)

app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok", "service": "paycycle"}

app.include_router(auth.router, prefix="/auth")    