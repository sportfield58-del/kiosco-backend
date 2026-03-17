from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import models, auth
from database import get_db

router = APIRouter(prefix="/usuarios", tags=["usuarios"])


def get_current_user(token: str, db: Session):
    from jose import JWTError
    try:
        payload = auth.decode_token(token)
        user = db.query(models.Usuario).filter_by(id=payload["sub"]).first()
        if not user or not user.activo:
            raise HTTPException(status_code=401, detail="Usuario no válido")
        return user
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido")


def audit(db, usuario_id, accion, detalle):
    db.add(models.AuditLog(usuario_id=usuario_id, accion=accion, detalle=detalle))
    db.commit()


@router.get("")
def listar(db: Session = Depends(get_db), current=Depends(lambda: None)):
    usuarios = db.query(models.Usuario).filter_by(activo=True).all()
    return [
        {"id": u.id, "nombre": u.nombre, "username": u.username,
         "rol": u.rol, "activo": u.activo, "creado_en": u.creado_en}
        for u in usuarios
    ]


@router.post("")
def crear(datos: dict, db: Session = Depends(get_db)):
    if db.query(models.Usuario).filter_by(username=datos["username"]).first():
        raise HTTPException(status_code=400, detail="El username ya existe")
    u = models.Usuario(
        nombre=datos["nombre"],
        username=datos["username"],
        password_hash=auth.hash_password(datos["password"]),
        rol=datos.get("rol", "vendedor")
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    audit(db, u.id, "crear_usuario", f"Usuario '{u.username}' creado con rol '{u.rol}'")
    return {"ok": True, "id": u.id}


@router.put("/{usuario_id}")
def editar(usuario_id: int, datos: dict, db: Session = Depends(get_db)):
    u = db.query(models.Usuario).filter_by(id=usuario_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    campos_modificados = []
    if "nombre" in datos:
        u.nombre = datos["nombre"]
        campos_modificados.append("nombre")
    if "rol" in datos:
        u.rol = datos["rol"]
        campos_modificados.append("rol")
    if "password" in datos and datos["password"]:
        u.password_hash = auth.hash_password(datos["password"])
        campos_modificados.append("password")
    if "activo" in datos:
        u.activo = datos["activo"]
        campos_modificados.append("activo")
    db.commit()
    audit(db, usuario_id, "editar_usuario",
          f"Usuario '{u.username}' modificó: {', '.join(campos_modificados)}")
    return {"ok": True}


@router.delete("/{usuario_id}")
def eliminar(usuario_id: int, db: Session = Depends(get_db)):
    u = db.query(models.Usuario).filter_by(id=usuario_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="No encontrado")
    u.activo = False
    db.commit()
    audit(db, usuario_id, "desactivar_usuario", f"Usuario '{u.username}' desactivado")
    return {"ok": True}
