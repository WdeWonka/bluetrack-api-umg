"""
Schemas de validación para rutas (SIN estado 'pendiente').
"""
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator
from datetime import date, datetime
from enum import Enum


# ========== ENUMS ==========
class EstadoRuta(str, Enum):
    PENDIENTE = "pendiente"
    EN_PROCESO = "en_proceso"
    COMPLETADA = "completada"
    CANCELADA = "cancelada"


class EstadoEntrega(str, Enum):
    """
    Estados de entrega por cliente:
    - no_entregado: Cliente no visitado aún (o visitado sin entrega)
    - entregado: Productos entregados exitosamente
    """
    ENTREGADO = "entregado"
    NO_ENTREGADO = "no_entregado"


# ========== CREAR RUTA ==========
class RouteCreate(BaseModel):
    """Crear ruta automáticamente con órdenes de una fecha específica."""
    nombre: str = Field(min_length=3, max_length=120)
    vendedor_id: int = Field(gt=0)
    almacen_id: int = Field(gt=0)
    fecha: date = Field(description="Fecha para filtrar órdenes")


# ========== CAMBIAR ESTADO DE RUTA ==========
class RouteChangeStateRequest(BaseModel):
    """Cambiar estado de ruta (pendiente → en_proceso → completada)."""
    nuevo_estado: EstadoRuta

    @field_validator('nuevo_estado')
    @classmethod
    def validar_estado(cls, v):
        if v not in [EstadoRuta.EN_PROCESO, EstadoRuta.COMPLETADA]:
            raise ValueError(
                "Solo se puede cambiar a 'en_proceso' o 'completada'"
            )
        return v


# ========== ENTREGAS ==========
class DeliveryItemCreate(BaseModel):
    """Producto entregado a un cliente."""
    orden_id: int = Field(..., gt=0, description="ID de la orden")
    producto_id: int = Field(gt=0)
    cantidad: int = Field(gt=0)


class DeliveryItemRead(BaseModel):
    id: int
    producto_id: int
    cantidad: int
    orden_id: Optional[int] = None


# ========== ACTUALIZAR ENTREGA ==========
class RouteDetailUpdateStatus(BaseModel):
    """
    Registrar entrega de un cliente.

    Lógica:
    - Al crear ruta: estado_entrega = 'no_entregado' (sin motivo)
    - Si se entrega: estado_entrega = 'entregado' + productos
    - Si NO se entrega: se mantiene 'no_entregado' + motivo
    """
    estado_entrega: EstadoEntrega
    motivo: Optional[str] = Field(
        None,
        description="Obligatorio si estado_entrega='no_entregado' Y ya se visitó"
    )
    entregas: List[DeliveryItemCreate] = Field(
        default=[],
        description="Productos entregados (vacío si no_entregado)"
    )

    @field_validator('motivo')
    @classmethod
    def validar_motivo(cls, v, info):
        """
        Si estado es no_entregado Y hay entregas vacías,
        el motivo es obligatorio (significa que se visitó pero no se entregó).
        """
        estado = info.data.get('estado_entrega')
        entregas = info.data.get('entregas', [])

        if estado == EstadoEntrega.NO_ENTREGADO and len(entregas) == 0 and not v:
            raise ValueError(
                "El motivo es obligatorio cuando no se entrega después de visitar"
            )
        return v

    @field_validator('entregas')
    @classmethod
    def validar_entregas(cls, v, info):
        """Si entregado, debe haber al menos un producto."""
        estado = info.data.get('estado_entrega')
        if estado == EstadoEntrega.ENTREGADO and len(v) == 0:
            raise ValueError(
                "Debe especificar al menos un producto entregado"
            )
        if estado == EstadoEntrega.NO_ENTREGADO and len(v) > 0:
            raise ValueError(
                "No debe especificar productos si no se entregó"
            )
        return v


# ========== DETALLE DE RUTA ==========
class RouteDetailRead(BaseModel):
    id: int
    cliente_id: int
    orden: int
    estado_entrega: EstadoEntrega
    motivo: Optional[str] = None
    timestamp_entrega: Optional[datetime] = None
    entregas: List[DeliveryItemRead] = []
    puede_entregar: bool = False
    fue_visitado: bool = False  # 🔥 NUEVO: indica si tiene motivo


# ========== INVENTARIO ==========
class InventoryItemRead(BaseModel):
    id: int
    producto_id: int
    cantidad_inicial: int
    cantidad_final: Optional[int] = None


# ========== RUTA BASE ==========
class RouteBase(BaseModel):
    nombre: str = Field(min_length=3, max_length=120)
    vendedor_id: int = Field(gt=0)
    almacen_id: int = Field(gt=0)
    fecha: date


class RouteRead(RouteBase):
    """Lectura completa de ruta."""
    id: int
    estado: EstadoRuta
    inicio_timestamp: Optional[datetime] = None
    fin_timestamp: Optional[datetime] = None
    creado_en: datetime
    detalles: List[RouteDetailRead] = []
    inventario: List[InventoryItemRead] = []
    proximo_cliente_orden: Optional[int] = None


class RouteListRead(RouteBase):
    """Lectura simplificada para listados."""
    id: int
    estado: EstadoRuta
    creado_en: datetime
    total_clientes: int = 0
    clientes_entregados: int = 0
    progreso_porcentaje: float = 0.0
