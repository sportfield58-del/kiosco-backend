from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
import models
from database import get_db

router = APIRouter(prefix="/ventas", tags=["ventas"])


def audit(db, usuario_id, accion, detalle):
    try:
        log = models.AuditLog(
            usuario_id=int(usuario_id) if usuario_id else None,
            accion=accion,
            detalle=detalle
        )
        db.add(log)
        db.commit()
    except Exception as e:
        print(f"ERROR audit: {e}")
        db.rollback()


@router.post("")
def registrar_venta(datos: dict, db: Session = Depends(get_db)):
    usuario_id = datos["usuario_id"]
    turno = db.query(models.Turno).filter_by(usuario_id=usuario_id, cerrado=False).first()
    if not turno:
        raise HTTPException(status_code=400, detail="Abri un turno primero")
    venta = models.Venta(
        turno_id=turno.id,
        usuario_id=usuario_id,
        total=datos["total"],
        medio_pago=datos.get("medio_pago", "efectivo")
    )
    db.add(venta)
    db.flush()
    nombres_items = []
    for item in datos["items"]:
        prod_id = item["producto_id"]
        if str(prod_id).startswith("rapido-"):
            nombres_items.append(f"{item.get('nombre', 'Producto rapido')} x{item['cantidad']}")
            iv = models.ItemVenta(
                venta_id=venta.id,
                producto_id=None,
                cantidad=item["cantidad"],
                precio_unitario=item["precio_unitario"],
                subtotal=item["cantidad"] * item["precio_unitario"]
            )
            db.add(iv)
            continue
        producto = db.query(models.Producto).filter_by(id=prod_id).first()
        if not producto:
            db.rollback()
            raise HTTPException(status_code=404, detail=f"Producto {prod_id} no encontrado")
        if producto.stock < item["cantidad"]:
            db.rollback()
            raise HTTPException(status_code=400,
                                detail=f"Stock insuficiente: '{producto.nombre}' tiene {producto.stock} unidades")
        producto.stock -= item["cantidad"]
        iv = models.ItemVenta(
            venta_id=venta.id,
            producto_id=prod_id,
            cantidad=item["cantidad"],
            precio_unitario=item["precio_unitario"],
            subtotal=item["cantidad"] * item["precio_unitario"]
        )
        db.add(iv)
        nombres_items.append(f"{producto.nombre} x{item['cantidad']}")
    db.commit()
    audit(db, usuario_id, "venta",
          f"Venta #{venta.id} | Total: ${venta.total:.2f} | "
          f"Pago: {venta.medio_pago} | Items: {', '.join(nombres_items)}")
    return {"venta_id": venta.id, "total": venta.total}


@router.get("/turno/{turno_id}")
def ventas_del_turno(turno_id: int, db: Session = Depends(get_db)):
    ventas = db.query(models.Venta).filter_by(turno_id=turno_id, anulada=False).all()
    total = sum(v.total for v in ventas)
    por_medio = {}
    for v in ventas:
        por_medio[v.medio_pago] = por_medio.get(v.medio_pago, 0) + v.total
    return {
        "ventas": [_serializar_venta(v) for v in ventas],
        "total": total,
        "cantidad": len(ventas),
        "por_medio_pago": por_medio
    }


@router.post("/anular/{venta_id}")
def anular_venta(venta_id: int, datos: dict, db: Session = Depends(get_db)):
    venta = db.query(models.Venta).filter_by(id=venta_id).first()
    if not venta:
        raise HTTPException(status_code=404, detail="Venta no encontrada")
    if venta.anulada:
        raise HTTPException(status_code=400, detail="La venta ya fue anulada")
    for item in venta.items:
        if item.producto:
            item.producto.stock += item.cantidad
    venta.anulada = True
    db.commit()
    audit(db, datos.get("usuario_id"), "anular_venta",
          f"Venta #{venta_id} anulada. Total devuelto: ${venta.total:.2f}. "
          f"Motivo: {datos.get('motivo', 'sin especificar')}")
    return {"ok": True}


def _serializar_venta(v):
    return {
        "id": v.id,
        "total": v.total,
        "medio_pago": v.medio_pago,
        "fecha": v.fecha,
        "anulada": v.anulada,
        "items": [
            {
                "nombre": i.producto.nombre if i.producto else i.precio_unitario,
                "cantidad": i.cantidad,
                "precio_unitario": i.precio_unitario,
                "subtotal": i.subtotal
            }
            for i in v.items
        ]
    }
