"""
Dependencias de autenticación.
"""
from fastapi import Depends, HTTPException, status, Request, Response
import jwt
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from db.session import get_db
from src.models.user import User
from src.core.config import settings
from src.utils.security import create_access_token
import logging

logger = logging.getLogger(__name__)

def verify_token(token: str):
    """
    Verifica y decodifica el JWT.
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido",
            headers={"WWW-Authenticate": "Bearer"},
        )

async def get_current_user(
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
) -> User:
    """
    Dependency para obtener el usuario actual.
    Lee el token desde la cookie y lo renueva si está próximo a expirar (sliding session).
    """
    # 1. Intentar obtener token de la cookie primero
    token = request.cookies.get("auth_token")

    # 2. Si no hay cookie, intentar desde Authorization header (fallback)
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.replace("Bearer ", "")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No autenticado",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 3. Verificar token
    payload = verify_token(token)
    user_id = payload.get("userId") or payload.get("sub")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido"
        )

    # 4. Obtener usuario de la DB
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no encontrado"
        )

    if not user.activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario inactivo"
        )

    # 5. SLIDING SESSION: Renovar token si está próximo a expirar
    exp_timestamp = payload.get("exp")

    if exp_timestamp:
        exp_datetime = datetime.fromtimestamp(exp_timestamp)
        time_until_expiry = exp_datetime - datetime.utcnow()

        # Si el token expira en menos de 30 minutos, renovarlo
        if time_until_expiry < timedelta(minutes=30):
            logger.info(f"🔄 Token renovado para {user.email} (quedaban {time_until_expiry})")

            # Crear nuevo token con los mismos datos
            new_token_data = {
                "userId": user.id,
                "email": user.email,
                "rol": user.rol
            }
            new_token = create_access_token(new_token_data)

            # Setear nueva cookie
            response.set_cookie(
                key="auth_token",
                value=new_token,
                httponly=True,
                secure=False,
                samesite="lax",
                max_age=settings.JWT_EXPIRE_MINUTES * 60,
                path="/",
                domain=None
            )

    return user


def require_role(*allowed_roles: str):
    """
    Dependency para proteger rutas por rol.

    Uso:
    @router.get("/admin", dependencies=[Depends(require_role("admin"))])
    """
    async def role_checker(
        current_user: User = Depends(get_current_user)
    ):
        if current_user.rol not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acceso denegado. Se requiere rol: {', '.join(allowed_roles)}"
            )
        return current_user

    return role_checker
