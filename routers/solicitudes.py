from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
import models

router = APIRouter(prefix="/solicitudes", tags=["solicitudes"])


def audit(db, usuario_id, accion, detalle):
    db.add(models.AuditLog(usuario_id=usuario_id, accion=accion, detalle=detalle))
    db.commit()


@router.post("/stock")
def solicitar_acceso_stock(datos: dict, db: Session = Depends(get_db)):
    usuario_id = datos["usuario_id"]
    usuario = db.query(models.Usuario).filter_by(id=usuario_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    # Verificar si ya tiene una solicitud pendiente
    existente = db.query(models.SolicitudStock).filter_by(
        usuario_id=usuario_id, estado="pendiente"
    ).first()
    if existente:
        return {"ok": True, "mensaje": "Ya tenés una solicitud pendiente"}

    s = models.SolicitudStock(
        usuario_id=usuario_id,
        estado="pendiente"
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    audit(db, usuario_id, "solicitar_stock",
          f"{usuario.nombre} solicitó acceso al stock")
    return {"ok": True, "solicitud_id": s.id}


@router.get("/stock/pendientes")
def listar_pendientes(db: Session = Depends(get_db)):
    solicitudes = db.query(models.SolicitudStock).filter_by(
        estado="pendiente"
    ).all()
    return [
        {
            "id": s.id,
            "usuario_id": s.usuario_id,
            "usuario": s.usuario.nombre if s.usuario else "—",
            "fecha": s.fecha,
            "estado": s.estado
        }
        for s in solicitudes
    ]


@router.post("/stock/{solicitud_id}/aprobar")
def aprobar(solicitud_id: int, datos: dict, db: Session = Depends(get_db)):
    s = db.query(models.SolicitudStock).filter_by(id=solicitud_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    s.estado = "aprobada"

    # Dar acceso temporal al stock
    u = db.query(models.Usuario).filter_by(id=s.usuario_id).first()
    if u:
        u.stock_habilitado = True

    db.commit()
    audit(db, datos.get("aprobado_por"), "aprobar_stock",
          f"Acceso al stock aprobado para {u.nombre if u else s.usuario_id}")
    return {"ok": True}


@router.post("/stock/{solicitud_id}/rechazar")
def rechazar(solicitud_id: int, datos: dict, db: Session = Depends(get_db)):
    s = db.query(models.SolicitudStock).filter_by(id=solicitud_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    s.estado = "rechazada"
    db.commit()
    return {"ok": True}


@router.post("/stock/revocar/{usuario_id}")
def revocar(usuario_id: int, datos: dict, db: Session = Depends(get_db)):
    u = db.query(models.Usuario).filter_by(id=usuario_id).first()
    if u:
        u.stock_habilitado = False
        db.commit()
    audit(db, datos.get("revocado_por"), "revocar_stock",
          f"Acceso al stock revocado para {u.nombre if u else usuario_id}")
    return {"ok": True}


@router.get("/stock/acceso/{usuario_id}")
def verificar_acceso(usuario_id: int, db: Session = Depends(get_db)):
    u = db.query(models.Usuario).filter_by(id=usuario_id).first()
    if not u:
        return {"acceso": False}
    # Dueño y admin siempre tienen acceso
    if u.rol in ["dueño", "admin"]:
        return {"acceso": True}
    return {"acceso": bool(u.stock_habilitado)}
