from typing import Annotated
from src.utils.type_converters import format_phone_gt
from pydantic import BaseModel, ConfigDict, StringConstraints, condecimal, Field, field_validator
from datetime import datetime
from decimal import Decimal
# Tipos con validaciones
NombreType = Annotated[str, StringConstraints(min_length=3, max_length=100)]
DireccionType = Annotated[str, StringConstraints(min_length=5, max_length=255)]
TelefonoType = Annotated[str, StringConstraints(min_length=7, max_length=20)]
LatitudType = Annotated[condecimal(max_digits=10, decimal_places=6), Field(ge=-90.0, le=90.0)]
LongitudType = Annotated[condecimal(max_digits=10, decimal_places=6), Field(ge=-180.0, le=180.0)]


class WarehouseBase(BaseModel):
    nombre: NombreType
    direccion: DireccionType
    telefono: TelefonoType
    latitud: LatitudType
    longitud: LongitudType


class WarehouseCreate(WarehouseBase):
    pass


class WarehouseUpdate(BaseModel):
    nombre: NombreType
    direccion: DireccionType
    telefono: TelefonoType
    latitud: LatitudType | None = None
    longitud: LongitudType | None = None


class WarehouseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre: str
    direccion: str
    telefono: str
    latitud: float
    longitud: float
    creado_en: datetime | None = None

class BulkWarehouseImport(BaseModel):
    nombre: str
    direccion: str
    telefono: str
    latitud: Decimal
    longitud: Decimal

    @field_validator('telefono')
    @classmethod
    def limpiar_y_validar_telefono(cls, v):
        """
        Limpia el teléfono y valida que sea válido para Guatemala.
        Acepta formatos: 23671234, 2367-1234, 44567890, 4456-7890
        """
        if not v:
            raise ValueError("El teléfono es requerido")

        # Limpiar el teléfono (remover guiones, espacios, etc)
        telefono_limpio = format_phone_gt(v, "storage")

        # Validar que sea un número válido de 8 dígitos
        if not telefono_limpio.isdigit():
            raise ValueError(f"El teléfono debe contener solo números. Recibido: {v}")

        if len(telefono_limpio) != 8:
            raise ValueError(
                f"El teléfono debe tener 8 dígitos. "
                f"Recibido: {v} (limpio: {telefono_limpio})"
            )

        # Validar que empiece con números válidos de Guatemala
        prefijos_validos = ['2', '3', '4', '5', '6', '7']
        if telefono_limpio[0] not in prefijos_validos:
            raise ValueError(
                f"El teléfono debe empezar con {', '.join(prefijos_validos)}. "
                f"Recibido: {telefono_limpio}"
            )

        return telefono_limpio  # Retornar limpio para la DB

    @field_validator('nombre')
    @classmethod
    def validar_nombre(cls, v):
        """Valida que el nombre no esté vacío."""
        if not v or not v.strip():
            raise ValueError("El nombre no puede estar vacío")
        return v.strip()

    @field_validator('direccion')
    @classmethod
    def validar_direccion(cls, v):
        """Valida que la dirección no esté vacía."""
        if not v or not v.strip():
            raise ValueError("La dirección no puede estar vacía")
        return v.strip()
    @field_validator('latitud')
    @classmethod
    def validar_latitud(cls, v):
        """Valida que la latitud esté en rango válido para Guatemala."""
        if not -90 <= v <= 90:
            raise ValueError(f"Latitud inválida: {v}. Debe estar entre -90 y 90")
        # Rango aproximado de Guatemala
        if not 13.5 <= v <= 18.0:
            raise ValueError(
                f"Latitud fuera del rango de Guatemala: {v}. "
                f"Debe estar entre 13.5 y 18.0"
            )
        return v
    @field_validator('longitud')
    @classmethod
    def validar_longitud(cls, v):
        """Valida que la longitud esté en rango válido para Guatemala."""
        if not -180 <= v <= 180:
            raise ValueError(f"Longitud inválida: {v}. Debe estar entre -180 y 180")
        # Rango aproximado de Guatemala
        if not -92.5 <= v <= -88.0:
            raise ValueError(
                f"Longitud fuera del rango de Guatemala: {v}. "
                f"Debe estar entre -92.5 y -88.0"
            )
        return v
