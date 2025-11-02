from pydantic import BaseModel, ConfigDict, Field, field_validator
from datetime import datetime
from typing import Optional
from src.common.constants.priorities import PRIORITY_CHOICES
from src.utils.date_parser import parse_date_flexible


class OrderCreate(BaseModel):
    """Crear nueva orden."""
    cliente_id: int = Field(gt=0)
    producto_id: int = Field(gt=0)
    cantidad: int = Field(gt=0, le=1000)

    fecha_solicitud: Optional[datetime] = Field(
        default=None,
        description="Fecha de solicitud en formato DD/MM/YYYY, DD-MM-YYYY o YYYY-MM-DD. Si no se proporciona, se usa la fecha actual."
    )

    @field_validator('fecha_solicitud', mode='before')
    @classmethod
    def validate_fecha(cls, v):
        """Valida y convierte la fecha a datetime."""
        # Si no se proporciona, usar fecha actual
        if v is None:
            return datetime.now()

        # Si ya es datetime, retornarlo
        if isinstance(v, datetime):
            return v

        # Si es string, parsear
        if isinstance(v, str):
            fecha_obj = parse_date_flexible(v)
            if fecha_obj is None:
                raise ValueError(
                    "Formato de fecha inválido. Use DD/MM/YYYY, DD-MM-YYYY o YYYY-MM-DD"
                )
            return fecha_obj

        return v


class OrderUpdate(BaseModel):
    """Actualizar orden existente. Todos los campos son opcionales."""
    model_config = ConfigDict(from_attributes=True)

    cliente_id: Optional[int] = None
    producto_id: Optional[int] = None
    cantidad: Optional[int] = None
    fecha_solicitud: Optional[datetime] = None

    @field_validator('cliente_id', 'producto_id', mode='before')
    @classmethod
    def validar_ids_positivos(cls, v):
        """Valida que los IDs sean positivos si se proporcionan."""
        if v is not None and v <= 0:
            raise ValueError(f"El ID debe ser mayor a 0. Recibido: {v}")
        return v

    @field_validator('cantidad', mode='before')
    @classmethod
    def validar_cantidad(cls, v):
        """Valida que la cantidad esté en rango válido si se proporciona."""
        if v is not None:
            if v <= 0:
                raise ValueError(f"La cantidad debe ser mayor a 0. Recibido: {v}")
            if v > 1000:
                raise ValueError(f"La cantidad no puede exceder 1000. Recibido: {v}")
        return v

    @field_validator('fecha_solicitud', mode='before')
    @classmethod
    def validate_fecha(cls, v):
        """
        Valida y convierte la fecha a datetime.
        Si es None o no se proporciona, retorna None (no actualizar).
        """
        # Si es None, mantenerlo como None
        if v is None:
            return None

        # Si ya es datetime, retornarlo
        if isinstance(v, datetime):
            return v

        # Si es string, parsear
        if isinstance(v, str):
            fecha_obj = parse_date_flexible(v)
            if fecha_obj is None:
                raise ValueError(
                    "Formato de fecha inválido. Use DD/MM/YYYY, DD-MM-YYYY o YYYY-MM-DD"
                )
            return fecha_obj

        return v


class OrderRead(BaseModel):
    """Leer orden con información del cliente y producto."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    cliente_id: int
    cliente_nombre: str
    cliente_direccion: str
    producto_id: int
    producto_nombre: str
    cantidad: int
    prioridad: str
    asignada: bool
    cancelada: bool
    ruta_id: Optional[int] = None
    fecha_solicitud: datetime


class OrderListItem(BaseModel):
    """Item de orden para listados."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    cliente_nombre: str
    producto_nombre: str
    cantidad: int
    prioridad: str
    asignada: bool
    cancelada: bool
    ruta_nombre: Optional[str] = None
    fecha_solicitud: datetime


class BulkOrderImport(BaseModel):
    """Importación masiva de órdenes desde Excel."""
    cliente_id: int = Field(gt=0)
    producto_id: int = Field(gt=0)
    cantidad: int = Field(gt=0, le=1000)
    prioridad: Optional[str] = "normal"

    @field_validator('prioridad')
    @classmethod
    def validar_prioridad(cls, v):
        """Valida que la prioridad sea válida."""
        if v and v.lower() not in PRIORITY_CHOICES:
            raise ValueError(
                f"Prioridad inválida: {v}. "
                f"Debe ser una de: {', '.join(PRIORITY_CHOICES)}"
            )
        return v.lower() if v else "normal"

    @field_validator('cliente_id', 'producto_id')
    @classmethod
    def validar_ids_positivos(cls, v):
        """Valida que los IDs sean positivos."""
        if v <= 0:
            raise ValueError(f"El ID debe ser mayor a 0. Recibido: {v}")
        return v

    @field_validator('cantidad')
    @classmethod
    def validar_cantidad(cls, v):
        """Valida que la cantidad esté en rango válido."""
        if v <= 0:
            raise ValueError(f"La cantidad debe ser mayor a 0. Recibido: {v}")
        if v > 1000:
            raise ValueError(f"La cantidad no puede exceder 1000. Recibido: {v}")
        return v
