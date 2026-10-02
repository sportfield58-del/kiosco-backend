import os
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import text, func
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

# Todos los endpoints exigen sesión (Bearer token). Usuarios y reportes son solo del dueño/admin;
# las operaciones sensibles de los demás routers se restringen endpoint por endpoint.
login_requerido = [Depends(auth.get_current_user)]
solo_dueno = [Depends(auth.require_dueno)]

app.include_router(usuarios.router, dependencies=solo_dueno)
app.include_router(turnos.router, dependencies=login_requerido)
app.include_router(productos.router, dependencies=login_requerido)
app.include_router(ventas.router, dependencies=login_requerido)
app.include_router(reportes.router, dependencies=solo_dueno)
app.include_router(botones.router, dependencies=login_requerido)
app.include_router(solicitudes.router, dependencies=login_requerido)

@app.middleware("http")
async def no_cachear_api(request, call_next):
    """Los datos de stock/turnos/ventas nunca deben servirse desde una caché intermedia o del navegador."""
    response = await call_next(request)
    if request.method == "GET":
        response.headers["Cache-Control"] = "no-store"
    return response


@app.post("/login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # Case-insensitive y sin espacios: "Juan", "juan " y "JUAN" tienen que ser el mismo usuario.
    # El teclado de un celular auto-capitaliza el primer caracter de un campo de texto si no se le
    # dice lo contrario (ver Login.jsx), así que esto no es un caso raro — es lo esperable.
    username = (form.username or "").strip().lower()
    user = db.query(models.Usuario).filter(func.lower(models.Usuario.username) == username).first()
    if not user or not auth.verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Credenciales incorrectas")
    if not user.activo:
        # Recién acá, con la contraseña ya validada, se revela que la cuenta está desactivada
        # (antes de validar la contraseña no se distingue de "credenciales incorrectas").
        raise HTTPException(status_code=403, detail="Tu usuario está desactivado. Pedile al dueño que te reactive.")
    rol = models.normalizar_rol(user.rol)
    token = auth.create_token({"sub": user.id, "rol": rol})
    return {
        "access_token": token,
        "token_type": "bearer",
        "usuario": {
            "id": user.id,
            "nombre": user.nombre,
            "rol": rol,
            "username": user.username,
            "stock_habilitado": user.stock_habilitado
        }
    }


@app.get("/me")
def me(current=Depends(auth.get_current_user)):
    return {
        "id": current.id,
        "nombre": current.nombre,
        "rol": models.normalizar_rol(current.rol),
        "username": current.username,
        "stock_habilitado": current.stock_habilitado
    }


@app.get("/ping")
def ping():
    return {"pong": True, "timestamp": datetime.utcnow().isoformat()}


@app.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "error"
    return {
        "status": "ok" if db_status == "ok" else "error",
        "db": db_status,
        "timestamp": datetime.utcnow().isoformat()
    }


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
