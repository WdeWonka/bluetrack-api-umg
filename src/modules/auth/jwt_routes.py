"""
Rutas de autenticación.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from fastapi.security import OAuth2PasswordBearer
from src.utils.token_blacklist import add_to_blacklist
from db.session import get_db
from src.modules.auth.service import login
from src.modules.auth.dependencies import get_current_user
from src.models.user import User

router = APIRouter(prefix="/auth", tags=["Autenticación"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# === SCHEMAS ===

class LoginRequest(BaseModel):
    """Schema para login con email/password."""
    email: EmailStr
    password: str

    class Config:
        json_schema_extra = {
            "example": {
                "email": "admin@mail.com",
                "password": "Admin123"
            }
        }


class LoginResponse(BaseModel):
    """Schema de respuesta del login."""
    access_token: str
    token_type: str = "bearer"  # 👈 Valor por defecto
    user: dict


class UserResponse(BaseModel):
    """Schema para información del usuario."""
    id: int
    nombre: str
    email: str
    rol: str
    dpi: str
    activo: bool

    class Config:
        from_attributes = True  # 👈 Para Pydantic v2 (antes era orm_mode)


# === ENDPOINTS ===

@router.post("/login", response_model=LoginResponse)
async def login_endpoint(
    credentials: LoginRequest,
    db: Session = Depends(get_db)
):
    """
    **LOGIN** - Autentica un usuario y retorna un token JWT.
    """
    try:
        result = login(db, credentials.email, credentials.password)
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """
    **Obtiene información del usuario autenticado.**
    """
    return current_user


@router.post("/logout")
async def logout(
    token: str = Depends(oauth2_scheme),
    current_user: User = Depends(get_current_user)
):
    """
    **LOGOUT** - Cierra la sesión (lado cliente elimina el token).
    """
    add_to_blacklist(token)  # Agregar el token a la lista negra
    return {
        "message": "Logout exitoso",
        "user": current_user.email
    }
