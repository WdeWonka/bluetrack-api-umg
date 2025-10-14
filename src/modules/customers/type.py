from typing import Annotated
from pydantic import BaseModel, ConfigDict, StringConstraints, condecimal, Field
from datetime import datetime

# Tipos con validaciones
NombreType = Annotated[str, StringConstraints(min_length=3, max_length=100)]
DireccionType = Annotated[str, StringConstraints(min_length=5, max_length=255)]
TelefonoType = Annotated[str, StringConstraints(min_length=7, max_length=20)]
LatitudType = Annotated[condecimal(max_digits=10, decimal_places=6), Field(ge=-90.0, le=90.0)]
LongitudType = Annotated[condecimal(max_digits=10, decimal_places=6), Field(ge=-180.0, le=180.0)]


class CustomerBase(BaseModel):
    nombre: NombreType
    direccion: DireccionType
    telefono: TelefonoType
    latitud: LatitudType
    longitud: LongitudType


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    nombre: NombreType 
    direccion: DireccionType 
    telefono: TelefonoType 
    latitud: LatitudType | None = None
    longitud: LongitudType | None = None


class CustomerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre: str
    direccion: str
    telefono: str
    latitud: float
    longitud: float
    creado_en: datetime | None = None
