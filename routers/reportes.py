from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, date, timedelta
import models
from database import get_db

router = APIRouter(prefix="/reportes", tags=["reportes"])


@router.get("/dia")
def reporte_dia(fecha: str = None, db: Session = Depends(get_db)):
    fecha_dt = datetime.strptime(fecha, "%Y-%m-%d").date() if fecha else date.today()

    ventas = db.query(models.Venta).filter(
        func.date(models.Venta.fecha) == fecha_dt,
        models.Venta.anulada == False
    ).all()

    total = sum(v.total for v in ventas)
    por_medio = {}
    for v in ventas:
        por_medio[v.medio_pago] = por_medio.get(v.medio_pago, 0) + v.total

    # Top productos del día
    items_dia = []
    for v in ventas:
        for item in v.items:
            nombre = item.producto.nombre if item.producto else "—"
            encontrado = next((i for i in items_dia if i["nombre"] == nombre), None)
            if encontrado:
                encontrado["cantidad"] += item.cantidad
                encontrado["total"] += item.subtotal
            else:
                items_dia.append({"nombre": nombre, "cantidad": item.cantidad, "total": item.subtotal})
    top_productos = sorted(items_dia, key=lambda x: x["total"], reverse=True)[:10]

    # Costo del día (para calcular ganancia)
    costo_total = 0
    for v in ventas:
        for item in v.items:
            if item.producto:
                costo_total += item.producto.precio_costo * item.cantidad

    # Ventas por usuario
    por_usuario = {}
    for v in ventas:
        nombre = v.usuario.nombre if v.usuario else "—"
        if nombre not in por_usuario:
            por_usuario[nombre] = {"total": 0, "cantidad": 0}
        por_usuario[nombre]["total"] += v.total
        por_usuario[nombre]["cantidad"] += 1

    return {
        "fecha": str(fecha_dt),
        "total_vendido": round(total, 2),
        "total_costo": round(costo_total, 2),
        "ganancia_neta": round(total - costo_total, 2),
        "cantidad_ventas": len(ventas),
        "por_medio_pago": por_medio,
        "top_productos": top_productos,
        "por_usuario": por_usuario
    }


@router.get("/semana")
def reporte_semana(db: Session = Depends(get_db)):
    hoy = date.today()
    resultados = []
    for i in range(7):
        dia = hoy - timedelta(days=i)
        ventas = db.query(models.Venta).filter(
            func.date(models.Venta.fecha) == dia,
            models.Venta.anulada == False
        ).all()
        total = sum(v.total for v in ventas)
        costo = sum(
            item.producto.precio_costo * item.cantidad
            for v in ventas for item in v.items if item.producto
        )
        resultados.append({
            "fecha": str(dia),
            "dia": dia.strftime("%A"),
            "total": round(total, 2),
            "ganancia": round(total - costo, 2),
            "cantidad": len(ventas)
        })
    return list(reversed(resultados))


@router.get("/alertas")
def alertas(db: Session = Depends(get_db)):
    logs = db.query(models.AuditLog).order_by(
        models.AuditLog.fecha.desc()
    ).limit(100).all()
    return [
        {
            "id": l.id,
            "usuario": l.usuario.nombre if l.usuario else "Sistema",
            "accion": l.accion,
            "detalle": l.detalle,
            "fecha": l.fecha
        }
        for l in logs
    ]


@router.get("/stock-bajo")
def stock_bajo(db: Session = Depends(get_db)):
    prods = db.query(models.Producto).filter(
        models.Producto.activo == True,
        models.Producto.stock <= models.Producto.stock_minimo
    ).all()
    return [
        {
            "id": p.id,
            "nombre": p.nombre,
            "stock": p.stock,
            "stock_minimo": p.stock_minimo,
            "faltante": p.stock_minimo - p.stock
        }
        for p in prods
    ]
