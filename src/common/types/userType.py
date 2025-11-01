# src/common/types/userType.py
import re
from typing import Annotated, Optional
from pydantic import BaseModel, EmailStr, ConfigDict, StringConstraints, field_validator
from datetime import datetime
from src.common.constants.roles import ADMIN, OPERATOR, SELLER

DPIType = Annotated[str, StringConstraints(min_length=13, max_length=50)]

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


# ============================================
# SCHEMAS BASE (Compartidos por todos)
# ============================================

class UserBase(BaseModel):
    """Schema base para todos los usuarios"""
    nombre: str
    dpi: DPIType
    email: EmailStr


class UserUpdate(BaseModel):
    """Schema para actualizar usuarios (cualquier rol)"""
    nombre: str | None = None
    dpi: DPIType | None = None
    email: EmailStr | None = None
    password: str | None = None

    @field_validator('dpi')
    @classmethod
    def validate_dpi(cls, v: str | None) -> str | None:
        """Valida DPI solo si no tiene prefijo DELETED_"""
        if v is not None and not v.startswith('DELETED_'):
            clean_dpi = v.replace(' ', '').replace('-', '')
            if not re.match(r'^\d{13}$', clean_dpi):
                raise ValueError('El DPI debe tener exactamente 13 dígitos numéricos')
            return clean_dpi
        return v


class UserRead(BaseModel):
    """Schema de lectura para todos los usuarios"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    dpi: str
    email: str
    rol: str
    activo: bool | None = None
    creado_en: datetime | None = None


# ============================================
# SCHEMAS ESPECÍFICOS - STAFF
# ============================================

class StaffCreate(UserBase):
    """
    Schema para crear usuarios de staff (operador o vendedor).
    El rol se especifica explícitamente.
    """
    password: str
    rol: str  # 'operador' o 'vendedor'

    @field_validator('dpi')
    @classmethod
    def validate_dpi(cls, v: str) -> str:
        """Valida que el DPI tenga 13 dígitos numéricos (no permite DELETED_)"""
        if v.startswith('DELETED_'):
            raise ValueError('No se puede crear un usuario con DPI marcado como eliminado')

        clean_dpi = v.replace(' ', '').replace('-', '')
        if not re.match(r'^\d{13}$', clean_dpi):
            raise ValueError('El DPI debe tener exactamente 13 dígitos numéricos')
        return clean_dpi

    @field_validator('rol')
    @classmethod
    def validate_rol(cls, v: str) -> str:
        v = v.lower()
        if v not in [OPERATOR.lower(), SELLER.lower()]:
            raise ValueError(f"Rol debe ser '{OPERATOR}' o '{SELLER}'")
        return v

    @field_validator('password')
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        is_valid, error_msg = validate_password(v)
        if not is_valid:
            raise ValueError(error_msg)
        return v


class BulkStaffImport(BaseModel):
    """Schema para importación masiva de staff desde Excel"""
    nombre: str
    dpi: str
    email: str
    password: str
    rol: str

    @field_validator('nombre', 'email', 'password', 'dpi', 'rol')
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

    @field_validator('rol')
    @classmethod
    def validate_rol(cls, v: str) -> str:
        v = v.lower()
        if v not in [OPERATOR.lower(), SELLER.lower()]:
            raise ValueError(f"Rol debe ser '{OPERATOR}' o '{SELLER}'")
        return v



# ============================================
# SCHEMAS ESPECÍFICOS - ADMIN
# ============================================

class AdminCreate(UserBase):
    """
    Schema para crear usuarios admin.
    El rol se establece automáticamente en 'admin'.
    """
    password: str

    @field_validator('password')
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        is_valid, error_msg = validate_password(v)
        if not is_valid:
            raise ValueError(error_msg)
        return v


class BulkAdminImport(BaseModel):
    """Schema para importación masiva de admins desde Excel"""
    nombre: str
    dpi: str
    email: str
    password: str
    # ✅ NO incluye 'rol' porque siempre es 'admin'

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


# ============================================
# SCHEMAS DEPRECADOS (mantener por compatibilidad)
# ============================================

class UserCreate(UserBase):
    """
    ⚠️ DEPRECADO: Usar StaffCreate o AdminCreate en su lugar.
    Se mantiene por compatibilidad con código existente.
    """
    password: str

    @field_validator('password')
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        is_valid, error_msg = validate_password(v)
        if not is_valid:
            raise ValueError(error_msg)
        return v


class BulkUserImport(BaseModel):
    """
    ⚠️ DEPRECADO: Usar BulkStaffImport en su lugar.
    Se mantiene por compatibilidad.
    """
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
