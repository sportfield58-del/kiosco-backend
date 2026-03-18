from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
import models

router = APIRouter(prefix="/botones", tags=["botones"])

BOTONES_DEFAULT = [
    {"id": 1, "nombre": "Pancho",           "emoji": "🌭", "precio": 2000, "activo": True},
    {"id": 2, "nombre": "Cigarrillo suelto","emoji": "🚬", "precio": 1500, "activo": True},
    {"id": 3, "nombre": "Gomitas",          "emoji": "🍬", "precio": 500,  "activo": True},
]

def audit(db, usuario_id, accion, detalle):
    db.add(models.AuditLog(usuario_id=usuario_id, accion=accion, detalle=detalle))
    db.commit()


@router.get("")
def listar(db: Session = Depends(get_db)):
    botones = db.query(models.BotonRapido).order_by(models.BotonRapido.orden).all()
    if not botones:
        # Inicializar con defaults
        for b in BOTONES_DEFAULT:
            db.add(models.BotonRapido(**b))
        db.commit()
        botones = db.query(models.BotonRapido).order_by(models.BotonRapido.orden).all()
    return [{"id": b.id, "nombre": b.nombre, "emoji": b.emoji,
             "precio": b.precio, "activo": b.activo, "orden": b.orden} for b in botones]


@router.put("/{boton_id}")
def editar(boton_id: int, datos: dict, db: Session = Depends(get_db)):
    b = db.query(models.BotonRapido).filter_by(id=boton_id).first()
    if not b:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Botón no encontrado")
    cambios = []
    for campo in ["nombre", "emoji", "precio", "activo"]:
        if campo in datos:
            viejo = getattr(b, campo)
            setattr(b, campo, datos[campo])
            if viejo != datos[campo]:
                cambios.append(f"{campo}: {viejo}→{datos[campo]}")
    db.commit()
    if cambios:
        audit(db, datos.get("usuario_id"), "editar_boton_rapido",
              f"Botón '{b.nombre}' modificado: {' | '.join(cambios)}")
    return {"ok": True}


@router.post("")
def crear(datos: dict, db: Session = Depends(get_db)):
    ultimo = db.query(models.BotonRapido).count()
    b = models.BotonRapido(
        nombre=datos["nombre"],
        emoji=datos.get("emoji", "🛒"),
        precio=datos["precio"],
        activo=True,
        orden=ultimo + 1
    )
    db.add(b)
    db.commit()
    db.refresh(b)
    audit(db, datos.get("usuario_id"), "crear_boton_rapido",
          f"Botón rápido '{b.nombre}' creado a ${b.precio}")
    return {"ok": True, "id": b.id}


@router.delete("/{boton_id}")
def eliminar(boton_id: int, usuario_id: int = 0, db: Session = Depends(get_db)):
    b = db.query(models.BotonRapido).filter_by(id=boton_id).first()
    if b:
        nombre = b.nombre
        db.delete(b)
        db.commit()
        audit(db, usuario_id, "eliminar_boton_rapido", f"Botón '{nombre}' eliminado")
    return {"ok": True}
