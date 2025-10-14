from sqlalchemy import Column, Integer, String,  DateTime, Numeric
from db.base import Base
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

# Modelo de Almacén
class Warehouse(Base):
    __tablename__ = "almacenes"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    direccion = Column(String(255), unique=True, nullable=False)
    telefono = Column(String(20), unique=True, nullable=False)
    latitud = Column(Numeric(10, 6), nullable=True)
    longitud = Column(Numeric(10, 6), nullable=True)
    creado_en = Column(DateTime, server_default=func.getdate())  # SQL Server

    rutas = relationship("Route", back_populates="almacen")
