from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, func
from db.base import Base

class Order(Base):
    __tablename__ = "ordenes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"), nullable=False)
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id"), nullable=False)
    producto_nombre_snapshot: Mapped[str | None] = mapped_column(String(120), nullable=True)
    cantidad: Mapped[int] = mapped_column(Integer, nullable=False)
    prioridad: Mapped[str] = mapped_column(String(20), default='normal')  # alta, normal, baja
    fecha_solicitud: Mapped[DateTime] = mapped_column(DateTime, server_default=func.getdate())
    asignada: Mapped[bool] = mapped_column(Boolean, default=False)
    cancelada: Mapped[bool] = mapped_column(Boolean, default=False)
    ruta_id: Mapped[int | None] = mapped_column(ForeignKey("rutas.id"), nullable=True)
    creado_en: Mapped[DateTime] = mapped_column(DateTime, server_default=func.getdate())

    # Relaciones
    cliente = relationship("Customer", back_populates="ordenes")
    producto = relationship("Product", back_populates="ordenes")
    ruta = relationship("Route", back_populates="ordenes")
    entregas = relationship("Delivery", back_populates="orden")
