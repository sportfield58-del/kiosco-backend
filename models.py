from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base


class Usuario(Base):
    __tablename__ = "usuarios"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False)
    username = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    rol = Column(String, default="vendedor")  # "dueño", "admin", "vendedor"
    activo = Column(Boolean, default=True)
    creado_en = Column(DateTime, default=datetime.utcnow)


class Turno(Base):
    __tablename__ = "turnos"
    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    tipo = Column(String)  # "mañana", "tarde", "noche"
    inicio = Column(DateTime, default=datetime.utcnow)
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
    creado_en = Column(DateTime, default=datetime.utcnow)


class Venta(Base):
    __tablename__ = "ventas"
    id = Column(Integer, primary_key=True, index=True)
    turno_id = Column(Integer, ForeignKey("turnos.id"))
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    total = Column(Float, nullable=False)
    medio_pago = Column(String, default="efectivo")  # "efectivo", "tarjeta", "transferencia"
    fecha = Column(DateTime, default=datetime.utcnow)
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


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    accion = Column(String)
    detalle = Column(Text)
    fecha = Column(DateTime, default=datetime.utcnow)
    usuario = relationship("Usuario")
