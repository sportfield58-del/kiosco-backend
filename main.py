import os
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
import models, auth
from database import engine, get_db, Base
from routers import usuarios, turnos, productos, ventas, reportes, botones, solicitudes

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Kiosco POS API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(usuarios.router)
app.include_router(turnos.router)
app.include_router(productos.router)
app.include_router(ventas.router)
app.include_router(reportes.router)
app.include_router(botones.router)
app.include_router(solicitudes.router)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = auth.decode_token(token)
        user = db.query(models.Usuario).filter_by(id=payload["sub"]).first()
        if not user or not user.activo:
            raise HTTPException(status_code=401, detail="Usuario no válido")
        return user
    except Exception:
        raise HTTPException(status_code=401, detail="Token inválido")


@app.post("/login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.Usuario).filter_by(username=form.username).first()
    if not user or not auth.verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Credenciales incorrectas")
    token = auth.create_token({"sub": user.id, "rol": user.rol})
    return {
        "access_token": token,
        "token_type": "bearer",
        "usuario": {"id": user.id, "nombre": user.nombre, "rol": user.rol, "username": user.username}
    }


@app.get("/me")
def me(current=Depends(get_current_user)):
    return {"id": current.id, "nombre": current.nombre, "rol": current.rol, "username": current.username}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.on_event("startup")
def crear_admin_inicial():
    db = next(get_db())
    if not db.query(models.Usuario).first():
        admin = models.Usuario(
            nombre="Administrador",
            username="admin",
            password_hash=auth.hash_password("admin123"),
            rol="dueño"
        )
        db.add(admin)
        db.commit()
        print("✅ Usuario inicial: admin / admin123  ← CAMBIÁ LA CONTRASEÑA")
