from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import auth
import models
from database import get_db
from models import now_ar

router = APIRouter(prefix="/turnos", tags=["turnos"])

TIPOS_TURNO = ("mañana", "tarde", "noche")
HORARIOS = {"mañana": "06-14", "tarde": "14-22", "noche": "22-06"}


def _desglose_pagos(ventas):
    """Totales por medio de pago. El pago mixto se reparte entre efectivo y Mercado Pago
    según los montos declarados, para que Efectivo + MP + Tarjeta == total del turno."""
    efectivo = mp = tarjeta = 0.0
    for v in ventas:
        if v.medio_pago == "mixto":
            parte_ef = v.monto_efectivo or 0
            efectivo += parte_ef
            mp += v.monto_mp if v.monto_mp is not None else v.total - parte_ef
        elif v.medio_pago == "efectivo":
            efectivo += v.total
        elif v.medio_pago == "tarjeta":
            tarjeta += v.total
        else:  # mercadopago / transferencia
            mp += v.total
    return {
        "efectivo": round(efectivo, 2),
        "mercadopago": round(mp, 2),
        "tarjeta": round(tarjeta, 2),
        "total": round(efectivo + mp + tarjeta, 2),
    }


def audit(db, usuario_id, accion, detalle):
    db.add(models.AuditLog(usuario_id=usuario_id, accion=accion, detalle=detalle))
    db.commit()


def _serializar_ventas_turno(ventas):
    """Lista completa de ventas con detalle de cada producto vendido."""
    resultado = []
    for v in ventas:
        resultado.append({
            "id": v.id,
            "total": v.total,
            "medio_pago": v.medio_pago,
            "fecha": v.fecha,
            "items": [
                {
                    "nombre": i.producto.nombre if i.producto else "Producto rápido",
                    "cantidad": i.cantidad,
                    "precio_unitario": i.precio_unitario,
                    "subtotal": i.subtotal
                }
                for i in v.items
            ]
        })
    return resultado


def _resumen_productos(ventas):
    """Agrupa todos los items vendidos por producto con totales."""
    productos = {}
    for v in ventas:
        for i in v.items:
            nombre = i.producto.nombre if i.producto else "Producto rápido"
            if nombre not in productos:
                productos[nombre] = {"nombre": nombre, "cantidad": 0, "subtotal": 0}
            productos[nombre]["cantidad"] += i.cantidad
            productos[nombre]["subtotal"] += i.subtotal
    return sorted(productos.values(), key=lambda x: x["subtotal"], reverse=True)


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
    return {"turno_id": t.id, "tipo": t.tipo, "inicio": t.inicio, "horario": HORARIOS.get(t.tipo)}


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
    t.cierre = now_ar()  # misma zona que `inicio`; datetime.now() usaba la hora del servidor (UTC)
    t.monto_cierre = datos.get("monto_cierre", 0)
    db.commit()

    audit(db, usuario_id, "cerrar_turno",
          f"Turno '{t.tipo}' cerrado | Ventas: ${total_ventas:.2f} | "
          f"Efectivo: ${por_medio.get('efectivo', 0):.2f} | "
          f"Tarjeta: ${por_medio.get('tarjeta', 0):.2f} | "
          f"Mercado Pago: ${por_medio.get('mercadopago', 0):.2f}")

    return {
        "ok": True,
        "turno_id": t.id,
        "resumen": {
            "tipo": t.tipo,
            "horario": HORARIOS.get(t.tipo),
            "inicio": t.inicio,
            "cierre": t.cierre,
            "total_ventas": total_ventas,
            "cantidad_ventas": len(ventas),
            "por_medio_pago": por_medio,
            "desglose": _desglose_pagos(ventas),
            "monto_apertura": t.monto_apertura,
            "monto_cierre": t.monto_cierre,
            "detalle_ventas": _serializar_ventas_turno(ventas),
            "resumen_productos": _resumen_productos(ventas)
        }
    }


@router.get("/activo/{usuario_id}")
def turno_activo(usuario_id: int, db: Session = Depends(get_db)):
    t = db.query(models.Turno).filter_by(usuario_id=usuario_id, cerrado=False).first()
    if not t:
        return {"turno": None}
    return {"turno": {"id": t.id, "tipo": t.tipo, "horario": HORARIOS.get(t.tipo),
                      "inicio": t.inicio, "monto_apertura": t.monto_apertura}}


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
            "cantidad_ventas": len(ventas),
            "detalle_ventas": _serializar_ventas_turno(ventas),
            "resumen_productos": _resumen_productos(ventas)
        })
    return resultado


@router.get("/cierres")
def cierres_de_caja(
    fecha: str = None,
    tipo: str = None,
    db: Session = Depends(get_db),
    _dueno=Depends(auth.require_dueno),
):
    """Cierres de caja de un día, opcionalmente de un solo turno (mañana/tarde/noche).

    Cada turno se asigna al día en que se abrió (el turno noche 22-06 cuenta en el día en que empieza).
    Devuelve el desglose Efectivo / Mercado Pago / Tarjeta por turno y el acumulado del filtro.
    """
    try:
        dia = datetime.strptime(fecha, "%Y-%m-%d").date() if fecha else now_ar().date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Fecha inválida, usar AAAA-MM-DD")
    if tipo and tipo not in TIPOS_TURNO:
        raise HTTPException(status_code=400, detail=f"Turno inválido. Opciones: {', '.join(TIPOS_TURNO)}")

    desde = datetime.combine(dia, datetime.min.time())
    query = db.query(models.Turno).filter(
        models.Turno.inicio >= desde,
        models.Turno.inicio < desde + timedelta(days=1),
    )
    if tipo:
        query = query.filter(models.Turno.tipo == tipo)
    turnos = query.order_by(models.Turno.inicio).all()

    resultado = []
    acumulado_ventas = []
    for t in turnos:
        ventas = db.query(models.Venta).filter_by(turno_id=t.id, anulada=False).all()
        acumulado_ventas.extend(ventas)
        desglose = _desglose_pagos(ventas)
        esperado = round((t.monto_apertura or 0) + desglose["efectivo"], 2)
        resultado.append({
            "id": t.id,
            "usuario": t.usuario.nombre if t.usuario else "—",
            "tipo": t.tipo,
            "horario": HORARIOS.get(t.tipo),
            "inicio": t.inicio,
            "cierre": t.cierre,
            "cerrado": t.cerrado,
            "cantidad_ventas": len(ventas),
            "desglose": desglose,
            "monto_apertura": t.monto_apertura,
            "monto_cierre": t.monto_cierre,
            # Efectivo que debería haber en caja vs. lo que el empleado contó al cerrar
            "efectivo_esperado": esperado,
            "diferencia": round(t.monto_cierre - esperado, 2) if t.cerrado and t.monto_cierre is not None else None,
            "resumen_productos": _resumen_productos(ventas),
        })

    return {
        "fecha": str(dia),
        "tipo": tipo,
        "turnos": resultado,
        "acumulado": {**_desglose_pagos(acumulado_ventas), "cantidad_ventas": len(acumulado_ventas)},
    }


@router.get("/todos", dependencies=[Depends(auth.require_dueno)])
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
            "monto_cierre": t.monto_cierre,
            "detalle_ventas": _serializar_ventas_turno(ventas),
            "resumen_productos": _resumen_productos(ventas)
        })
    return resultado


@router.get("/detalle/{turno_id}", dependencies=[Depends(auth.require_dueno)])
def detalle_turno(turno_id: int, db: Session = Depends(get_db)):
    """Endpoint para que el dueño vea el detalle completo de cualquier turno."""
    t = db.query(models.Turno).filter_by(id=turno_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Turno no encontrado")
    ventas = db.query(models.Venta).filter_by(turno_id=t.id, anulada=False).all()
    total_ventas = sum(v.total for v in ventas)
    por_medio = {}
    for v in ventas:
        por_medio[v.medio_pago] = por_medio.get(v.medio_pago, 0) + v.total
    return {
        "id": t.id,
        "usuario": t.usuario.nombre if t.usuario else "—",
        "tipo": t.tipo,
        "inicio": t.inicio,
        "cierre": t.cierre,
        "cerrado": t.cerrado,
        "total_ventas": total_ventas,
        "cantidad_ventas": len(ventas),
        "por_medio_pago": por_medio,
        "monto_apertura": t.monto_apertura,
        "monto_cierre": t.monto_cierre,
        "detalle_ventas": _serializar_ventas_turno(ventas),
        "resumen_productos": _resumen_productos(ventas)
    }
