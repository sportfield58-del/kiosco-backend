from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
import models
from database import get_db

router = APIRouter(prefix="/turnos", tags=["turnos"])


def audit(db, usuario_id, accion, detalle):
    db.add(models.AuditLog(usuario_id=usuario_id, accion=accion, detalle=detalle))
    db.commit()


@router.post("/abrir")
def abrir_turno(datos: dict, db: Session = Depends(get_db)):
    usuario_id = datos["usuario_id"]
    turno_abierto = db.query(models.Turno).filter_by(
        usuario_id=usuario_id, cerrado=False
    ).first()
    if turno_abierto:
        raise HTTPException(status_code=400, detail="Ya tenés un turno abierto")
    t = models.Turno(
        usuario_id=usuario_id,
        tipo=datos.get("tipo", "mañana"),
        monto_apertura=datos.get("monto_apertura", 0)
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    audit(db, usuario_id, "abrir_turno",
          f"Turno '{t.tipo}' abierto con ${t.monto_apertura} en caja")
    return {"turno_id": t.id, "tipo": t.tipo, "inicio": t.inicio}


@router.post("/cerrar")
def cerrar_turno(datos: dict, db: Session = Depends(get_db)):
    usuario_id = datos["usuario_id"]
    t = db.query(models.Turno).filter_by(usuario_id=usuario_id, cerrado=False).first()
    if not t:
        raise HTTPException(status_code=404, detail="No hay turno abierto")

    ventas = db.query(models.Venta).filter_by(turno_id=t.id, anulada=False).all()
    total_ventas = sum(v.total for v in ventas)
    por_medio = {}
    for v in ventas:
        por_medio[v.medio_pago] = por_medio.get(v.medio_pago, 0) + v.total

    t.cerrado = True
    t.cierre = datetime.utcnow()
    t.monto_cierre = datos.get("monto_cierre", 0)
    db.commit()

    audit(db, usuario_id, "cerrar_turno",
          f"Turno '{t.tipo}' cerrado | Ventas: ${total_ventas:.2f} | "
          f"Efectivo: ${por_medio.get('efectivo', 0):.2f} | "
          f"Tarjeta: ${por_medio.get('tarjeta', 0):.2f} | "
          f"Transferencia: ${por_medio.get('transferencia', 0):.2f}")

    return {
        "ok": True,
        "turno_id": t.id,
        "resumen": {
            "tipo": t.tipo,
            "inicio": t.inicio,
            "cierre": t.cierre,
            "total_ventas": total_ventas,
            "cantidad_ventas": len(ventas),
            "por_medio_pago": por_medio,
            "monto_apertura": t.monto_apertura,
            "monto_cierre": t.monto_cierre
        }
    }


@router.get("/activo/{usuario_id}")
def turno_activo(usuario_id: int, db: Session = Depends(get_db)):
    t = db.query(models.Turno).filter_by(usuario_id=usuario_id, cerrado=False).first()
    if not t:
        return {"turno": None}
    return {"turno": {"id": t.id, "tipo": t.tipo, "inicio": t.inicio,
                      "monto_apertura": t.monto_apertura}}


@router.get("/historial/{usuario_id}")
def historial_turnos(usuario_id: int, db: Session = Depends(get_db)):
    turnos = db.query(models.Turno).filter_by(
        usuario_id=usuario_id, cerrado=True
    ).order_by(models.Turno.cierre.desc()).limit(30).all()
    resultado = []
    for t in turnos:
        ventas = db.query(models.Venta).filter_by(turno_id=t.id, anulada=False).all()
        resultado.append({
            "id": t.id,
            "tipo": t.tipo,
            "inicio": t.inicio,
            "cierre": t.cierre,
            "total_ventas": sum(v.total for v in ventas),
            "cantidad_ventas": len(ventas)
        })
    return resultado


@router.get("/todos")
def todos_los_turnos(db: Session = Depends(get_db)):
    turnos = db.query(models.Turno).order_by(models.Turno.inicio.desc()).limit(100).all()
    resultado = []
    for t in turnos:
        ventas = db.query(models.Venta).filter_by(turno_id=t.id, anulada=False).all()
        resultado.append({
            "id": t.id,
            "usuario": t.usuario.nombre if t.usuario else "—",
            "tipo": t.tipo,
            "inicio": t.inicio,
            "cierre": t.cierre,
            "cerrado": t.cerrado,
            "total_ventas": sum(v.total for v in ventas),
            "cantidad_ventas": len(ventas),
            "monto_apertura": t.monto_apertura,
            "monto_cierre": t.monto_cierre
        })
    return resultado
