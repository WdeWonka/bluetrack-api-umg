from sqlalchemy import Column, Integer, String, DateTime, Numeric
from db.base import Base
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
# Modelo de Cliente
class Customer(Base):
    __tablename__ = "clientes"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(120), nullable=False)
    direccion = Column(String(255), nullable=False)
    telefono = Column(String(20), nullable=False)
    latitud = Column(Numeric(10, 6), nullable=True)
    longitud = Column(Numeric(10, 6), nullable=True)
    creado_en = Column(DateTime, server_default=func.getdate())

    detalles = relationship("RouteDetail", back_populates="cliente")
    ordenes = relationship("Order", back_populates="cliente")
