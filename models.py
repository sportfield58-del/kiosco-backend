from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime, timezone, timedelta
from database import Base

AR = timezone(timedelta(hours=-3))

def now_ar():
    return datetime.now(AR).replace(tzinfo=None)


class Usuario(Base):
    __tablename__ = "usuarios"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False)
    username = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    rol = Column(String, default="vendedor")
    activo = Column(Boolean, default=True)
    stock_habilitado = Column(Boolean, default=False)
    creado_en = Column(DateTime, default=now_ar)


class Turno(Base):
    __tablename__ = "turnos"
    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    tipo = Column(String)
    inicio = Column(DateTime, default=now_ar)
    cierre = Column(DateTime, nullable=True)
    monto_apertura = Column(Float, default=0)
    monto_cierre = Column(Float, nullable=True)
    cerrado = Column(Boolean, default=False)
    usuario = relationship("Usuario")
    ventas = relationship("Venta", back_populates="turno")


class Producto(Base):
    __tablename__ = "productos"
    id = Column(Integer, primary_key=True, index=True)
    codigo_barra = Column(String, unique=True, nullable=False, index=True)
    nombre = Column(String, nullable=False)
    precio_costo = Column(Float, default=0)
    precio_venta = Column(Float, nullable=False)
    stock = Column(Integer, default=0)
    stock_minimo = Column(Integer, default=5)
    categoria = Column(String, default="general")
    activo = Column(Boolean, default=True)
    creado_en = Column(DateTime, default=now_ar)


class Venta(Base):
    __tablename__ = "ventas"
    id = Column(Integer, primary_key=True, index=True)
    turno_id = Column(Integer, ForeignKey("turnos.id"))
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    total = Column(Float, nullable=False)
    medio_pago = Column(String, default="efectivo")
    # Pago mixto
    monto_efectivo = Column(Float, nullable=True)
    monto_mp = Column(Float, nullable=True)
    fecha = Column(DateTime, default=now_ar)
    anulada = Column(Boolean, default=False)
    turno = relationship("Turno", back_populates="ventas")
    usuario = relationship("Usuario")
    items = relationship("ItemVenta", back_populates="venta")


class ItemVenta(Base):
    __tablename__ = "items_venta"
    id = Column(Integer, primary_key=True, index=True)
    venta_id = Column(Integer, ForeignKey("ventas.id"))
    producto_id = Column(Integer, ForeignKey("productos.id"))
    cantidad = Column(Integer)
    precio_unitario = Column(Float)
    subtotal = Column(Float)
    venta = relationship("Venta", back_populates="items")
    producto = relationship("Producto")


class ConsumoEmpleado(Base):
    """Consumo del empleado con 20% off — se cobra después (deuda)."""
    __tablename__ = "consumos_empleado"
    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    turno_id = Column(Integer, ForeignKey("turnos.id"), nullable=True)
    total_original = Column(Float, nullable=False)
    descuento = Column(Float, nullable=False)  # 20%
    total_a_cobrar = Column(Float, nullable=False)
    cobrado = Column(Boolean, default=False)
    fecha = Column(DateTime, default=now_ar)
    usuario = relationship("Usuario")
    items = relationship("ItemConsumoEmpleado", back_populates="consumo")


class ItemConsumoEmpleado(Base):
    __tablename__ = "items_consumo_empleado"
    id = Column(Integer, primary_key=True, index=True)
    consumo_id = Column(Integer, ForeignKey("consumos_empleado.id"))
    producto_id = Column(Integer, ForeignKey("productos.id"))
    cantidad = Column(Integer)
    precio_unitario = Column(Float)
    subtotal = Column(Float)
    consumo = relationship("ConsumoEmpleado", back_populates="items")
    producto = relationship("Producto")


class ConsumoDueno(Base):
    """Consumo del dueño — sale del stock, no se cobra."""
    __tablename__ = "consumos_dueno"
    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    turno_id = Column(Integer, ForeignKey("turnos.id"), nullable=True)
    total_costo = Column(Float, nullable=False)
    motivo = Column(String, default="consumo propio")
    fecha = Column(DateTime, default=now_ar)
    usuario = relationship("Usuario")
    items = relationship("ItemConsumoDueno", back_populates="consumo")


class ItemConsumoDueno(Base):
    __tablename__ = "items_consumo_dueno"
    id = Column(Integer, primary_key=True, index=True)
    consumo_id = Column(Integer, ForeignKey("consumos_dueno.id"))
    producto_id = Column(Integer, ForeignKey("productos.id"))
    cantidad = Column(Integer)
    precio_unitario = Column(Float)
    subtotal = Column(Float)
    consumo = relationship("ConsumoDueno", back_populates="items")
    producto = relationship("Producto")


class BotonRapido(Base):
    __tablename__ = "botones_rapidos"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False)
    emoji = Column(String, default="??")
    precio = Column(Float, nullable=False)
    activo = Column(Boolean, default=True)
    orden = Column(Integer, default=0)


class SolicitudStock(Base):
    __tablename__ = "solicitudes_stock"
    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    estado = Column(String, default="pendiente")
    fecha = Column(DateTime, default=now_ar)
    usuario = relationship("Usuario")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    accion = Column(String)
    detalle = Column(Text)
    fecha = Column(DateTime, default=now_ar)
    usuario = relationship("Usuario")
