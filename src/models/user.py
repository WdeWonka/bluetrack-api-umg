from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from db.base import Base

# Modelo de Usuario
class User(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    dpi = Column(String(13), unique=True, nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    password = Column(String(255), nullable=False)
    rol = Column(String(20), nullable=False)
    activo = Column(Boolean, default=True)
    creado_en = Column(DateTime, server_default=func.getdate())

    # Relaciones
    rutas = relationship("Route", back_populates="vendedor")
