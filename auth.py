import os
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

import models
from database import get_db

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "kiosco-dev-secret-cambiame-en-produccion")
ALGORITHM = "HS256"
# Los tokens son stateless: cada dispositivo (celular, PC) recibe el suyo al loguearse y
# ninguno invalida a los otros. Duran una semana para que nadie quede deslogueado en pleno turno.
ACCESS_TOKEN_EXPIRE_HOURS = int(os.getenv("ACCESS_TOKEN_EXPIRE_HOURS", str(24 * 7)))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_token(data: dict) -> str:
    to_encode = data.copy()
    # RFC 7519: "sub" debe ser string (python-jose reciente rechaza enteros)
    if "sub" in to_encode:
        to_encode["sub"] = str(to_encode["sub"])
    to_encode["exp"] = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    # verify_sub=False: siguen siendo válidos los tokens emitidos antes con "sub" numérico
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM], options={"verify_sub": False})


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        user_id = int(decode_token(token)["sub"])
    except (JWTError, KeyError, ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Token inválido")
    user = db.query(models.Usuario).filter_by(id=user_id).first()
    if not user or not user.activo:
        raise HTTPException(status_code=401, detail="Usuario no válido")
    return user


def puede_editar_stock(user) -> bool:
    return user.rol in ("dueño", "admin") or bool(user.stock_habilitado)


def require_stock_access(user=Depends(get_current_user)):
    """Dueño/admin, o empleado al que el dueño le aprobó el acceso al stock."""
    if not puede_editar_stock(user):
        raise HTTPException(status_code=403, detail="No tenés acceso al stock. Pedile autorización al dueño.")
    return user


def require_dueno(user=Depends(get_current_user)):
    if user.rol not in ("dueño", "admin"):
        raise HTTPException(status_code=403, detail="Solo el dueño puede ver esta información")
    return user
