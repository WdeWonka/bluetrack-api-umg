from passlib.context import CryptContext
import jwt
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
import os
from dotenv import load_dotenv
from src.core.config import settings  # ✅ Importar settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(plain: str) -> str:
    """Hashea una contraseña usando bcrypt."""
    if not isinstance(plain, str):
        plain = str(plain)
    return pwd_context.hash(plain)

def verify_password(plain: str, hashed: str) -> bool:
    """Verifica que una contraseña coincida con su hash."""
    if not isinstance(plain, str):
        plain = str(plain)
    return pwd_context.verify(plain, hashed)


# Configuracion de JWT
load_dotenv()
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("JWT_SECRET_KEY no encontrada en .env")

ALGORITHM = "HS256"

def create_access_token(data: Dict[str, Any], expires_delta: Optional[int] = None) -> str:
    """
    Crea un token JWT usando PyJWT.

    Args:
        data: Datos a incluir en el token (userId, email, rol, etc.)
        expires_delta: Tiempo de expiración en MINUTOS (opcional)

    Returns:
        Token JWT como string

    Example:
        token = create_access_token({"userId": 1, "email": "user@mail.com", "rol": "admin"})
    """
    to_encode = data.copy()

    # ✅ Usar settings.JWT_EXPIRE_MINUTES en lugar de constante hardcodeada
    if expires_delta:
        expire = datetime.now(timezone.utc) + timedelta(minutes=expires_delta)
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})

    # Crear el token con PyJWT
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Verifica y decodifica un token JWT usando PyJWT.

    Args:
        token: Token JWT a verificar

    Returns:
        Payload del token si es válido, None si no lo es

    Example:
        payload = verify_token(token)
        if payload:
            user_id = payload["userId"]
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        print("Token ha expirado")
        return None
    except jwt.InvalidTokenError:
        print("Token inválido")
        return None
    except Exception:
        return None
