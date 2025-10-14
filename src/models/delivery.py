from sqlalchemy import Column, Integer, DateTime, ForeignKey, CheckConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from db.base import Base

class Delivery(Base):
    __tablename__ = "entregas"

    id = Column(Integer, primary_key=True, index=True)
    ruta_detalle_id = Column(
        Integer,
        ForeignKey("ruta_detalle.id", ondelete="CASCADE"),
        nullable=False
    )
    orden_id = Column(  # 🔥 AGREGADA
        Integer,
        ForeignKey("ordenes.id", ondelete="SET NULL"),
        nullable=True  # Puede ser NULL si es una entrega sin orden específica
    )
    producto_id = Column(Integer, ForeignKey("productos.id"), nullable=False)
    cantidad = Column(Integer, nullable=False)
    creado_en = Column(DateTime, server_default=func.getdate(), nullable=False)

    __table_args__ = (
        CheckConstraint('cantidad >= 0', name='check_cantidad_positiva'),
    )

    # Relaciones
    ruta_detalle = relationship("RouteDetail", back_populates="entregas")
    orden = relationship("Order", back_populates="entregas")
    producto = relationship("Product")
