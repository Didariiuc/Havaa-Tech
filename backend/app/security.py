import re
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from passlib.context import CryptContext
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from .config import settings
from .db import get_db
from .models import User
pwd=CryptContext(schemes=['bcrypt'], deprecated='auto'); bearer=HTTPBearer(auto_error=False)
def hash_password(p): return pwd.hash(p)
def verify_password(p,h): return pwd.verify(p,h)
def token_for(user): return jwt.encode({'sub':str(user.id),'role':user.role,'exp':datetime.now(timezone.utc)+timedelta(minutes=settings.jwt_expire_minutes)},settings.jwt_secret,algorithm='HS256')
def current_user(creds:HTTPAuthorizationCredentials=Depends(bearer), db:Session=Depends(get_db)):
    if not creds: raise HTTPException(401,'Authentication required')
    try: uid=int(jwt.decode(creds.credentials,settings.jwt_secret,algorithms=['HS256'])['sub'])
    except (JWTError,ValueError): raise HTTPException(401,'Invalid or expired session')
    user=db.get(User,uid)
    if not user: raise HTTPException(401,'Account not found')
    return user
def require_roles(*roles):
    def guard(user:User=Depends(current_user)):
        if user.role not in roles: raise HTTPException(403,'You do not have permission for this action')
        return user
    return guard
def redact_pii(text):
    text=re.sub(r'\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b','[REDACTED_EMAIL]',text)
    text=re.sub(r'(?<!\d)(?:\+?8801|01)[3-9]\d{8}(?!\d)','[REDACTED_PHONE]',text)
    text=re.sub(r'\b\d{13,19}\b','[REDACTED_NUMBER]',text)
    return text
def injection_detected(text):
    patterns=['ignore all previous instructions','reveal system prompt','bypass approval','act as system','ignore safety rules']
    return any(p in text.lower() for p in patterns)
