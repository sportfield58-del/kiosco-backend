from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
import openpyxl
import models
from database import get_db

router = APIRouter(prefix="/productos", tags=["productos"])


def audit(db, usuario_id, accion, detalle):
    db.add(models.AuditLog(usuario_id=usuario_id, accion=accion, detalle=detalle))
    db.commit()


@router.get("")
def listar(db: Session = Depends(get_db)):
    prods = db.query(models.Producto).filter_by(activo=True).order_by(models.Producto.nombre).all()
    return [_serializar(p) for p in prods]


@router.get("/buscar")
def buscar_por_codigo(codigo: str, db: Session = Depends(get_db)):
    p = db.query(models.Producto).filter_by(codigo_barra=codigo.strip(), activo=True).first()
    if not p:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return _serializar(p)


@router.get("/alertas-stock")
def alertas_stock(db: Session = Depends(get_db)):
    prods = db.query(models.Producto).filter(
        models.Producto.activo == True,
        models.Producto.stock <= models.Producto.stock_minimo
    ).all()
    return [_serializar(p) for p in prods]


@router.post("")
def crear(datos: dict, db: Session = Depends(get_db)):
    if db.query(models.Producto).filter_by(codigo_barra=datos["codigo_barra"]).first():
        raise HTTPException(status_code=400, detail="Código de barra ya existe")
    p = models.Producto(
        codigo_barra=datos["codigo_barra"],
        nombre=datos["nombre"],
        precio_costo=datos.get("precio_costo", 0),
        precio_venta=datos["precio_venta"],
        stock=datos.get("stock", 0),
        stock_minimo=datos.get("stock_minimo", 5),
        categoria=datos.get("categoria", "general")
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    audit(db, datos.get("usuario_id"), "crear_producto",
          f"Producto '{p.nombre}' ({p.codigo_barra}) creado. Stock: {p.stock}, Precio: ${p.precio_venta}")
    return {"ok": True, "id": p.id}


@router.put("/{producto_id}")
def editar(producto_id: int, datos: dict, db: Session = Depends(get_db)):
    p = db.query(models.Producto).filter_by(id=producto_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="No encontrado")
    cambios = []
    campos = ["nombre", "precio_costo", "precio_venta", "stock", "stock_minimo", "categoria"]
    for campo in campos:
        if campo in datos:
            valor_anterior = getattr(p, campo)
            setattr(p, campo, datos[campo])
            if valor_anterior != datos[campo]:
                cambios.append(f"{campo}: {valor_anterior} → {datos[campo]}")
    db.commit()
    if cambios:
        audit(db, datos.get("usuario_id"), "editar_producto",
              f"Producto '{p.nombre}' modificado: {' | '.join(cambios)}")
    return {"ok": True}


@router.post("/ajuste-stock/{producto_id}")
def ajustar_stock(producto_id: int, datos: dict, db: Session = Depends(get_db)):
    p = db.query(models.Producto).filter_by(id=producto_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="No encontrado")
    stock_anterior = p.stock
    p.stock = datos["stock_nuevo"]
    db.commit()
    audit(db, datos.get("usuario_id"), "ajuste_stock",
          f"Stock de '{p.nombre}' ajustado: {stock_anterior} → {p.stock} "
          f"(motivo: {datos.get('motivo', 'sin especificar')})")
    return {"ok": True}


@router.post("/importar-excel")
async def importar_excel(
    file: UploadFile = File(...),
    usuario_id: int = 0,
    db: Session = Depends(get_db)
):
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos .xlsx o .xls")

    contenido = await file.read()
    import io
    wb = openpyxl.load_workbook(io.BytesIO(contenido))
    ws = wb.active

    creados = 0
    actualizados = 0
    errores = []

    for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        try:
            if not row[0]:
                continue
            codigo = str(row[0]).strip()
            nombre = str(row[1]).strip()
            precio_costo = float(row[2] or 0)
            precio_venta = float(row[3])
            stock = int(row[4] or 0)
            stock_minimo = int(row[5] or 5)
            categoria = str(row[6]).strip() if row[6] else "general"

            existente = db.query(models.Producto).filter_by(codigo_barra=codigo).first()
            if existente:
                existente.nombre = nombre
                existente.precio_costo = precio_costo
                existente.precio_venta = precio_venta
                existente.stock = stock
                existente.stock_minimo = stock_minimo
                existente.categoria = categoria
                existente.activo = True
                actualizados += 1
            else:
                p = models.Producto(
                    codigo_barra=codigo,
                    nombre=nombre,
                    precio_costo=precio_costo,
                    precio_venta=precio_venta,
                    stock=stock,
                    stock_minimo=stock_minimo,
                    categoria=categoria
                )
                db.add(p)
                creados += 1
        except Exception as e:
            errores.append(f"Fila {i}: {str(e)}")

    db.commit()
    audit(db, usuario_id, "importar_excel",
          f"Importación Excel: {creados} creados, {actualizados} actualizados, {len(errores)} errores")
    return {"creados": creados, "actualizados": actualizados, "errores": errores}


def _serializar(p):
    ganancia = ((p.precio_venta - p.precio_costo) / p.precio_costo * 100) if p.precio_costo else 0
    return {
        "id": p.id,
        "codigo_barra": p.codigo_barra,
        "nombre": p.nombre,
        "precio_costo": p.precio_costo,
        "precio_venta": p.precio_venta,
        "ganancia_pct": round(ganancia, 1),
        "stock": p.stock,
        "stock_minimo": p.stock_minimo,
        "categoria": p.categoria,
        "stock_bajo": p.stock <= p.stock_minimo
    }
