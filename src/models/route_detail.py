from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Integer, String, DateTime, ForeignKey
from datetime import datetime
from db.base import Base

class RouteDetail(Base):
    __tablename__ = "ruta_detalle"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    ruta_id: Mapped[int] = mapped_column(ForeignKey("rutas.id"), nullable=False)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"), nullable=False)
    orden: Mapped[int] = mapped_column(Integer, nullable=False)

    # ✅ Default a 'no_entregado' (coincide con DB)
    estado_entrega: Mapped[str] = mapped_column(
        String(20),
        default='no_entregado',
        nullable=False
    )

    motivo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    timestamp_entrega: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relaciones
    ruta = relationship("Route", back_populates="detalles")
    cliente = relationship("Customer", back_populates="detalles")
    entregas = relationship("Delivery", back_populates="ruta_detalle")
