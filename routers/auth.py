from database import sessionLocal, get_db
from fastapi import APIRouter, Depends, HTTPException,status
from sqlalchemy.orm import Session
import model, schemas, utils
from core import security

router = APIRouter(tags=["USERS"])

@router.post("/signup",status_code = status.HTTP_201_CREATED, response_model=schemas.UserOut)
def sign_up(user: schemas.UserCreate, db:Session = Depends(get_db)):
    #check if the user already exist
    existing_user = db.query(model.User).filter(model.User.email == user.email).first()

    if existing_user:
        raise HTTPException(status_code= status.HTTP_400_BAD_REQUEST,detail="User already exists")
    
    #hash the password
    hashed_password = utils.hash(user.password)
    user.password = hashed_password

    #add to the database
    new_user = model.User(name = user.name, phone_number = user.phone_number ,email = user.email, hashed_password = user.password)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user

@router.post("/login", response_model=dict)
def login(user: schemas.UserLogin, db: Session = Depends(get_db)):
    #check if the user exists
    existing_user = db.query(model.User).filter(model.User.email == user.email).first()

    if not existing_user:
        raise HTTPException(status_code= status.HTTP_400_BAD_REQUEST,detail="Invalid email or password")
    
    #verify the password
    if not utils.verify_password(user.password, existing_user.hashed_password):
        raise HTTPException(status_code= status.HTTP_400_BAD_REQUEST,detail="Invalid email or password")
    
    #create access token
    access_token = security.create_access_token(data={"sub": str(existing_user.id)})

    return {"access_token": access_token, "token_type": "bearer"}

