from sqlalchemy import Column, Integer, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from db.base import Base
from datetime import datetime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Integer, ForeignKey, DateTime, func

# Modelo para el inventario asociado a una ruta
class RouteInventory(Base):
    __tablename__ = "inventario_ruta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ruta_id: Mapped[int] = mapped_column(ForeignKey("rutas.id"))
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id"))
    cantidad_inicial: Mapped[int] = mapped_column(Integer, default=0)
    cantidad_final: Mapped[int] = mapped_column(Integer, default=0)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    ruta = relationship("Route", back_populates="inventario")
    producto = relationship("Product", back_populates="inventario_ruta")
