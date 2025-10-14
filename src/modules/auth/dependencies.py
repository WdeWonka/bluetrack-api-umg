from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from typing import Optional
from src.utils.token_blacklist import is_blacklisted

from db.session import get_db
from src.models.user import User
from src.utils.security import verify_token

# 🔐 Configuración de OAuth2
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    """
    Obtiene el usuario actual desde el token JWT.
    """

    if is_blacklisted(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesión cerrada. Inicia sesión nuevamente",
            headers={"WWW-Authenticate": "Bearer"},
        )

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudo validar las credenciales",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Verificar el token
    payload = verify_token(token)
    if payload is None:
        raise credentials_exception

    # Extraer user_id del token
    user_id: Optional[int] = payload.get("user_id")
    if user_id is None:
        raise credentials_exception

    # Buscar usuario en la base de datos
    user = db.query(User).filter(
        User.id == user_id,
        User.activo == True  # 👈 Filtrar directamente en la query
    ).first()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,  # 👈 401 en vez de 403
            detail="Usuario no encontrado o inactivo"
        )

    return user


def require_role(*allowed_roles: str):  # 👈 Mejor sintaxis con *args
    """
    Factory para requerir roles específicos.

    Uso:
        @router.get("/admin", dependencies=[Depends(require_role("admin"))])
    """
    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.rol not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acceso denegado. Rol requerido: {' o '.join(allowed_roles)}"
            )
        return current_user
    return role_checker


# 🎯 Shortcuts para roles comunes
require_admin = require_role("admin")
require_operador = require_role("admin", "operador")
require_vendedor = require_role("vendedor")
