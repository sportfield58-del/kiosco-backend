from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import models, auth
from database import get_db

router = APIRouter(prefix="/usuarios", tags=["usuarios"])


def audit(db, usuario_id, accion, detalle):
    db.add(models.AuditLog(usuario_id=usuario_id, accion=accion, detalle=detalle))
    db.commit()


@router.get("")
def listar(db: Session = Depends(get_db)):
    usuarios = db.query(models.Usuario).filter_by(activo=True).all()
    return [
        {"id": u.id, "nombre": u.nombre, "username": u.username,
         "rol": u.rol, "activo": u.activo,
         "stock_habilitado": getattr(u, "stock_habilitado", False),
         "creado_en": u.creado_en}
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
    cambios = []
    for campo in ["nombre", "rol", "activo", "stock_habilitado"]:
        if campo in datos:
            valor_anterior = getattr(u, campo)
            setattr(u, campo, datos[campo])
            if valor_anterior != datos[campo]:
                cambios.append(f"{campo}: {valor_anterior} -> {datos[campo]}")
    if "password" in datos and datos["password"]:
        u.password_hash = auth.hash_password(datos["password"])
        cambios.append("password")
    db.commit()
    audit(db, usuario_id, "editar_usuario",
          f"Usuario '{u.username}' modifico: {', '.join(cambios)}")
    return {"ok": True}


@router.delete("/{usuario_id}")
def eliminar(usuario_id: int, db: Session = Depends(get_db)):
    u = db.query(models.Usuario).filter_by(id=usuario_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="No encontrado")
    if not u.activo:
        raise HTTPException(status_code=400, detail="El usuario ya estaba desactivado")

    username_original = u.username
    u.activo = False
    # `username` es UNIQUE en la base y "eliminar" solo desactiva (para no perder el historial de
    # ventas/turnos del usuario). Sin liberar el nombre acá, quedaba tomado para siempre: no se
    # podía volver a dar de alta a alguien con el mismo username nunca más.
    u.username = f"{username_original}__baja{u.id}"
    db.add(models.AuditLog(usuario_id=usuario_id, accion="desactivar_usuario",
                           detalle=f"Usuario '{username_original}' desactivado"))
    db.commit()
    return {"ok": True}
