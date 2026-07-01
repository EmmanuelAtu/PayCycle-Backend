from pydantic import BaseModel, EmailStr
from datetime import datetime

class UserCreate(BaseModel):
    name:str
    email:EmailStr
    phone_number:str
    password:str

class UserOut(BaseModel):
    id:int
    email:EmailStr
    created_at: datetime

    class config:
        from_attributes = True
        
class UserLogin(BaseModel):
    email:EmailStr
    password:str

    
