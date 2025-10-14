import re
from typing import Annotated
from pydantic import BaseModel, EmailStr, ConfigDict, StringConstraints, field_validator
from datetime import datetime

DPIType = Annotated[str, StringConstraints(min_length=13, max_length=13)]

def validate_password(password: str) -> tuple[bool, str]:
    """
    Valida que la contraseña cumpla con los requisitos de seguridad

    Requisitos:
    - Mínimo 8 caracteres
    - Al menos una letra mayúscula
    - Al menos un número

    Returns:
        tuple: (es_valida, mensaje_error)
    """
    if len(password) < 8:
        return False, "La contraseña debe tener al menos 8 caracteres"

    if not re.search(r"[A-Z]", password):
        return False, "La contraseña debe contener al menos una letra mayúscula"

    if not re.search(r"\d", password):
        return False, "La contraseña debe contener al menos un número"

    return True, ""



class UserBase(BaseModel):
    nombre: str
    dpi: DPIType
    email: EmailStr


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    nombre: str | None = None
    dpi: DPIType | None = None
    email: EmailStr | None = None
    password: str | None = None


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    dpi: str
    email: str
    rol: str
    activo: bool | None = None
    creado_en: datetime | None = None


class BulkUserImport(BaseModel):
    nombre: str
    dpi: str
    email: str
    password: str

    @field_validator('nombre', 'email', 'password', 'dpi')
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('El campo no puede estar vacío')
        return v.strip()

    @field_validator('dpi')
    @classmethod
    def validate_dpi_length(cls, v: str) -> str:
        if len(v) != 13:
            raise ValueError('El DPI debe tener exactamente 13 dígitos')
        if not v.isdigit():
            raise ValueError('El DPI solo debe contener números')
        return v

    @field_validator('email')
    @classmethod
    def validate_email_format(cls, v: str) -> str:
        if '@' not in v or '.' not in v.split('@')[-1]:
            raise ValueError('Formato de email inválido')
        return v.lower()

    @field_validator('password')
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        is_valid, error_msg = validate_password(v)
        if not is_valid:
            raise ValueError(error_msg)
        return v
