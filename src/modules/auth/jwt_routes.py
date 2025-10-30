# src/modules/auth/jwt_routes.py
"""
Rutas de autenticación.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from fastapi.security import OAuth2PasswordBearer
from src.utils.token_blacklist import add_to_blacklist
from db.session import get_db
from src.modules.auth.service import login
from src.modules.auth.dependencies import get_current_user, verify_token
from src.models.user import User
from src.core.config import settings

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
    token_type: str = "bearer"
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
        from_attributes = True


# === ENDPOINTS ===

@router.post("/login")
async def login_endpoint(
    credentials: LoginRequest,
    response: Response,
    db: Session = Depends(get_db)
):
    try:
        result = login(db, credentials.email, credentials.password)

        # 🍪 Configuración correcta de cookie para desarrollo local
        response.set_cookie(
            key="auth_token",
            value=result["access_token"],
            httponly=True,           # ✅ Cookie solo accesible por HTTP
            secure=False,            # 🔑 False para localhost (sin HTTPS)
            samesite="lax",          # 🔑 "lax" permite cookies cross-origin en localhost
            max_age=settings.JWT_EXPIRE_MINUTES * 60,
            path="/",
            domain=None              # 🔑 None para que funcione en localhost
        )

        return {
            "statusCode": 200,
            "message": "Login exitoso",
            "user": result["user"]  # 🔑 No devolver el token en el body (está en cookie)
        }

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

    ✅ Lee el token desde la cookie automáticamente
    """
    return current_user


@router.post("/logout")
async def logout(
    response: Response,
    request: Request
):
    token = request.cookies.get("auth_token")

    if token:
        add_to_blacklist(token)

    # 🗑️ Limpiar cookie correctamente
    response.delete_cookie(
        key="auth_token",
        path="/",
        domain=None,           # 🔑 Debe coincidir con el set_cookie
        samesite="lax"         # 🔑 Debe coincidir con el set_cookie
    )

    return {
        "statusCode": 200,
        "message": "Logout exitoso"
    }
