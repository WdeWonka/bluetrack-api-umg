"""
Servicio de autenticación.
"""
from sqlalchemy.orm import Session
from typing import Optional
import logging

from src.models.user import User
from src.utils.security import verify_password, create_access_token

logger = logging.getLogger(__name__)


def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
    """
    Autentica un usuario por email y contraseña.

    Args:
        db: Sesión de base de datos
        email: Email del usuario
        password: Contraseña en texto plano

    Returns:
        Usuario si las credenciales son válidas, None en caso contrario
    """
    # Buscar usuario por email
    user = db.query(User).filter(User.email == email.lower()).first()

    if not user:
        logger.warning(f"Login attempt for non-existent user: {email}")
        return None

    # Verificar contraseña
    if not verify_password(password, user.password):
        logger.warning(f"Invalid password for user: {email}")
        return None

    # Verificar que el usuario esté activo
    if not user.activo:
        logger.warning(f"Login attempt for inactive user: {email}")
        return None

    logger.info(f"User authenticated successfully: {email}")
    return user


def login(db: Session, email: str, password: str) -> dict:
    """
    Realiza el login completo: autentica y genera token.

    Args:
        db: Sesión de base de datos
        email: Email del usuario
        password: Contraseña

    Returns:
        Dict con access_token, token_type y datos del usuario

    Raises:
        ValueError: Si las credenciales son inválidas
    """
    # Autenticar usuario
    user = authenticate_user(db, email, password)

    if not user:
        raise ValueError("Email o contraseña incorrectos")

    # Crear token con datos del usuario
    token_data = {
        "user_id": user.id,
        "email": user.email,
        "rol": user.rol
    }

    access_token = create_access_token(token_data)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "nombre": user.nombre,
            "email": user.email,
            "rol": user.rol,
            "dpi": user.dpi
        }
    }
