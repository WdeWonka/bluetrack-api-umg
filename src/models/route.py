from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Integer, String, Date, DateTime, ForeignKey
from datetime import datetime, date
from db.base import Base
from src.modules.routes.type import EstadoRuta

class Route(Base):
    __tablename__ = "rutas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    vendedor_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    almacen_id: Mapped[int] = mapped_column(ForeignKey("almacenes.id"), nullable=False)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)

    # 🔥 String en lugar de SQLEnum
    estado: Mapped[str] = mapped_column(
        String(20),
        default=EstadoRuta.PENDIENTE.value,
        nullable=False
    )

    inicio_timestamp: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fin_timestamp: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # 🆕 NUEVOS CAMPOS PARA CANCELACIÓN
    cancelada_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    motivo_cancelacion: Mapped[str | None] = mapped_column(String(255), nullable=True)

    creado_en: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    # Relaciones
    vendedor = relationship("User", back_populates="rutas")
    almacen = relationship("Warehouse", back_populates="rutas")
    detalles = relationship("RouteDetail", back_populates="ruta", cascade="all, delete-orphan")
    inventario = relationship("RouteInventory", back_populates="ruta", cascade="all, delete-orphan")
    ordenes = relationship("Order", back_populates="ruta", cascade="all, delete-orphan")
