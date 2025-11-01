from sqlalchemy import Column, Integer, String, DateTime, Numeric, Boolean, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from db.base import Base
from datetime import datetime
from sqlalchemy.types import DECIMAL

# Modelo de Producto
class Product(Base):
    __tablename__ = "productos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    precio: Mapped[float] = mapped_column(DECIMAL(10,2), nullable=False)
    stock_total: Mapped[int] = mapped_column(Integer, default=0)
    stock_reservado: Mapped[int] = mapped_column(Integer, default=0)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    # 🆕 Constraint para validar stock_reservado
    __table_args__ = (
        CheckConstraint(
            'stock_reservado >= 0 AND stock_reservado <= stock_total',
            name='check_stock_reservado_valido'
        ),
    )

    inventario_ruta = relationship("RouteInventory", back_populates="producto")
    ordenes = relationship("Order", back_populates="producto")
