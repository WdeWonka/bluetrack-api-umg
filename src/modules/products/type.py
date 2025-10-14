from typing import Annotated, Optional
from pydantic import BaseModel, ConfigDict, StringConstraints, Field, field_validator
from decimal import Decimal
from datetime import datetime

# Tipos con validaciones
NombreType = Annotated[str, StringConstraints(min_length=3, max_length=100)]
PrecioType = Annotated[Decimal, Field(gt=0, max_digits=10, decimal_places=2)]
StockType = Annotated[int, Field(ge=0, le=50000)]


class ProductBase(BaseModel):
    nombre: NombreType
    precio: PrecioType
    stock_total: StockType

class ProductCreate(ProductBase):

    @field_validator('nombre')
    @classmethod
    def validar_nombre(cls, v):
        """Valida y limpia el nombre del producto."""
        if not v or not v.strip():
            raise ValueError("El nombre no puede estar vacío")
        return v.strip().title()

    @field_validator('stock_total')
    @classmethod
    def validar_stock(cls, v):
        """Valida que el stock sea razonable."""
        if v < 0:
            raise ValueError("El stock no puede ser negativo")
        if v > 50000:
            raise ValueError(
                "El stock excede el límite máximo permitido (50,000 unidades). "
                "Si necesitas un límite mayor, contacta al administrador."
            )
        return v


class ProductUpdate(BaseModel):
    nombre: Optional[NombreType] = None
    precio: Optional[PrecioType] = None
    stock_total: Optional[StockType] = None

    @field_validator('stock_total')
    @classmethod
    def validar_stock(cls, v):
        """Valida que el stock sea razonable."""
        if v is not None:
            if v < 0:
                raise ValueError("El stock no puede ser negativo")
            if v > 50000:
                raise ValueError(
                    "El stock excede el límite máximo permitido (50,000 unidades)"
                )
        return v




class ProductRead(BaseModel):
    """Schema para leer un producto desde la API."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    precio: float
    stock_total: int
    activo: bool
    creado_en: datetime


class BulkProductImport(BaseModel):
    nombre: NombreType
    precio: PrecioType
    stock_total: StockType

    @field_validator('nombre')
    @classmethod
    def validar_nombre(cls, v):
        """Valida y limpia el nombre del producto."""
        if not v or not v.strip():
            raise ValueError("El nombre no puede estar vacío")
        return v.strip().title()

    @field_validator('precio')
    @classmethod
    def validar_precio(cls, v):
        """Valida que el precio sea positivo."""
        if v <= 0:
            raise ValueError("El precio debe ser mayor a 0")
        return v

    @field_validator('stock_total')
    @classmethod
    def validar_stock(cls, v):
        """Valida que el stock sea razonable."""
        if v < 0:
            raise ValueError("El stock no puede ser negativo")
        if v > 50000:
            raise ValueError(
                "El stock excede el límite máximo permitido (50,000 unidades)"
            )
        return v
