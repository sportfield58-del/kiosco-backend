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


def aplicar_recargo_nocturno(total: float) -> tuple[float, bool]:
    """Devuelve (total_final, es_nocturno). De 22:00 a 06:00 aplica +10% hora Argentina."""
    from datetime import timezone, timedelta
    AR = timezone(timedelta(hours=-3))
    hora = datetime.now(AR).hour
    if hora >= 22 or hora < 6:
        return round(total * 1.10, 2), True
    return total, False


@router.get("/recargo-nocturno")
def estado_recargo_nocturno():
    from datetime import timezone, timedelta
    AR = timezone(timedelta(hours=-3))
    hora = datetime.now(AR).hour
    activo = hora >= 22 or hora < 6
    return {"activo": activo, "hora": hora}


@router.post("")
def registrar_venta(datos: dict, db: Session = Depends(get_db)):
    usuario_id = datos["usuario_id"]
    turno = db.query(models.Turno).filter_by(usuario_id=usuario_id, cerrado=False).first()
    if not turno:
        raise HTTPException(status_code=400, detail="Abri un turno primero")

    total_original = datos["total"]
    total_final, es_nocturno = aplicar_recargo_nocturno(total_original)

    # Pago mixto
    medio = datos.get("medio_pago", "efectivo")
    monto_efectivo = datos.get("monto_efectivo", None)
    monto_mp = datos.get("monto_mp", None)

    # Si viene pago mixto, validar que sumen el total
    if monto_efectivo is not None and monto_mp is not None:
        medio = "mixto"
        suma = round(float(monto_efectivo) + float(monto_mp), 2)
        if abs(suma - total_final) > 1:
            raise HTTPException(status_code=400, detail=f"Los montos no suman el total: ${suma:.2f} ≠ ${total_final:.2f}")

    venta = models.Venta(
        turno_id=turno.id,
        usuario_id=usuario_id,
        total=total_final,
        medio_pago=medio,
        monto_efectivo=float(monto_efectivo) if monto_efectivo is not None else None,
        monto_mp=float(monto_mp) if monto_mp is not None else None,
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

    recargo_txt = f" | ⚠ Recargo nocturno +10% (original: ${total_original:.2f})" if es_nocturno else ""
    mixto_txt = f" | Mixto: efectivo ${monto_efectivo} + MP ${monto_mp}" if medio == "mixto" else ""
    audit(db, usuario_id, "venta",
          f"Venta #{venta.id} | Total: ${venta.total:.2f} | "
          f"Pago: {medio} | Items: {', '.join(nombres_items)}{recargo_txt}{mixto_txt}")

    return {
        "venta_id": venta.id,
        "total": venta.total,
        "recargo_nocturno": es_nocturno,
        "total_original": total_original if es_nocturno else None,
        "medio_pago": medio,
    }


# ── CONSUMO EMPLEADO ──────────────────────────────────────
@router.post("/consumo-empleado")
def consumo_empleado(datos: dict, db: Session = Depends(get_db)):
    """Empleado se lleva productos con 20% off. Se descuenta del stock, queda como deuda."""
    usuario_id = datos["usuario_id"]
    turno = db.query(models.Turno).filter_by(usuario_id=usuario_id, cerrado=False).first()

    total_original = 0
    items_procesados = []

    for item in datos["items"]:
        producto = db.query(models.Producto).filter_by(id=item["producto_id"]).first()
        if not producto:
            raise HTTPException(status_code=404, detail=f"Producto {item['producto_id']} no encontrado")
        if producto.stock < item["cantidad"]:
            raise HTTPException(status_code=400,
                detail=f"Stock insuficiente: '{producto.nombre}' tiene {producto.stock} unidades")
        subtotal = producto.precio_venta * item["cantidad"]
        total_original += subtotal
        items_procesados.append((producto, item["cantidad"], producto.precio_venta, subtotal))

    descuento = round(total_original * 0.20, 2)
    total_a_cobrar = round(total_original - descuento, 2)

    consumo = models.ConsumoEmpleado(
        usuario_id=usuario_id,
        turno_id=turno.id if turno else None,
        total_original=total_original,
        descuento=descuento,
        total_a_cobrar=total_a_cobrar,
    )
    db.add(consumo)
    db.flush()

    for producto, cantidad, precio_u, subtotal in items_procesados:
        producto.stock -= cantidad
        db.add(models.ItemConsumoEmpleado(
            consumo_id=consumo.id,
            producto_id=producto.id,
            cantidad=cantidad,
            precio_unitario=precio_u,
            subtotal=subtotal,
        ))

    db.commit()
    audit(db, usuario_id, "consumo_empleado",
          f"Consumo empleado #{consumo.id} | Original: ${total_original:.2f} | "
          f"Descuento 20%: -${descuento:.2f} | A cobrar: ${total_a_cobrar:.2f}")

    return {
        "consumo_id": consumo.id,
        "total_original": total_original,
        "descuento": descuento,
        "total_a_cobrar": total_a_cobrar,
        "cobrado": False
    }


@router.get("/consumo-empleado/{usuario_id}")
def consumos_empleado(usuario_id: int, db: Session = Depends(get_db)):
    """Lista de consumos pendientes de cobro del empleado."""
    consumos = db.query(models.ConsumoEmpleado).filter_by(
        usuario_id=usuario_id, cobrado=False
    ).all()
    return [{
        "id": c.id,
        "fecha": c.fecha,
        "total_original": c.total_original,
        "descuento": c.descuento,
        "total_a_cobrar": c.total_a_cobrar,
        "cobrado": c.cobrado,
        "items": [{"nombre": i.producto.nombre if i.producto else "?",
                   "cantidad": i.cantidad, "subtotal": i.subtotal} for i in c.items]
    } for c in consumos]


@router.post("/consumo-empleado/{consumo_id}/cobrar")
def cobrar_consumo_empleado(consumo_id: int, datos: dict, db: Session = Depends(get_db)):
    """Marcar consumo de empleado como cobrado."""
    consumo = db.query(models.ConsumoEmpleado).filter_by(id=consumo_id).first()
    if not consumo:
        raise HTTPException(status_code=404, detail="Consumo no encontrado")
    consumo.cobrado = True
    db.commit()
    audit(db, datos.get("usuario_id"), "cobrar_consumo_empleado",
          f"Consumo #{consumo_id} cobrado. Total: ${consumo.total_a_cobrar:.2f}")
    return {"ok": True}


# ── CONSUMO DUEÑO ──────────────────────────────────────────
@router.post("/consumo-dueno")
def consumo_dueno(datos: dict, db: Session = Depends(get_db)):
    """Dueño consume productos — sale del stock, no se cobra."""
    usuario_id = datos["usuario_id"]
    turno = db.query(models.Turno).filter_by(usuario_id=usuario_id, cerrado=False).first()

    total_costo = 0
    items_procesados = []

    for item in datos["items"]:
        producto = db.query(models.Producto).filter_by(id=item["producto_id"]).first()
        if not producto:
            raise HTTPException(status_code=404, detail=f"Producto {item['producto_id']} no encontrado")
        if producto.stock < item["cantidad"]:
            raise HTTPException(status_code=400,
                detail=f"Stock insuficiente: '{producto.nombre}' tiene {producto.stock} unidades")
        subtotal = producto.precio_costo * item["cantidad"]
        total_costo += subtotal
        items_procesados.append((producto, item["cantidad"], producto.precio_costo, subtotal))

    consumo = models.ConsumoDueno(
        usuario_id=usuario_id,
        turno_id=turno.id if turno else None,
        total_costo=total_costo,
        motivo=datos.get("motivo", "consumo propio"),
    )
    db.add(consumo)
    db.flush()

    for producto, cantidad, precio_u, subtotal in items_procesados:
        producto.stock -= cantidad
        db.add(models.ItemConsumoDueno(
            consumo_id=consumo.id,
            producto_id=producto.id,
            cantidad=cantidad,
            precio_unitario=precio_u,
            subtotal=subtotal,
        ))

    db.commit()
    audit(db, usuario_id, "consumo_dueno",
          f"Consumo dueño #{consumo.id} | Costo: ${total_costo:.2f} | Motivo: {datos.get('motivo','consumo propio')}")

    return {
        "consumo_id": consumo.id,
        "total_costo": total_costo,
        "mensaje": "Stock descontado. Sin cobro."
    }


@router.get("/turno/{turno_id}")
def ventas_del_turno(turno_id: int, db: Session = Depends(get_db)):
    ventas = db.query(models.Venta).filter_by(turno_id=turno_id, anulada=False).all()
    total = sum(v.total for v in ventas)
    por_medio = {}
    for v in ventas:
        key = v.medio_pago
        por_medio[key] = por_medio.get(key, 0) + v.total
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
        "monto_efectivo": v.monto_efectivo,
        "monto_mp": v.monto_mp,
        "fecha": v.fecha,
        "anulada": v.anulada,
        "items": [
            {
                "nombre": i.producto.nombre if i.producto else "Producto rápido",
                "cantidad": i.cantidad,
                "precio_unitario": i.precio_unitario,
                "subtotal": i.subtotal
            }
            for i in v.items
        ]
    }
