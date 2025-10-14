from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import or_, func
import re
from src.models.user import User
from src.common.types.userType import UserCreate, UserUpdate
from src.common.constants.roles import ADMIN
from src.utils.security import hash_password


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


def create_user(db: Session, user_data: UserCreate, role: str = ADMIN) -> User:
    """
    Crea un nuevo usuario con validación de contraseña.
    
    Raises:
        ValueError: Si la validación de contraseña falla
        IntegrityError: Si el usuario ya existe (DPI o email duplicado)
        SQLAlchemyError: Para otros errores de base de datos
    
    Returns:
        User: El usuario creado
    """
    # Validar contraseña ANTES de intentar crear
    is_valid, error_message = validate_password(user_data.password)
    if not is_valid:
        raise ValueError(error_message)
    
    user = User(
        nombre=str(user_data.nombre).lower(),
        email=str(user_data.email).lower(),
        password=hash_password(user_data.password),
        dpi=str(user_data.dpi),
        rol=role.lower(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_user(db: Session, user_id: int) -> User | None:
    """Obtiene un usuario por su ID"""
    return db.query(User).filter(User.id == user_id).first()


def update_user(db: Session, user_id: int, user_data: UserUpdate) -> User | None:
    """
    Actualiza un usuario existente.
    
    Raises:
        ValueError: Si la validación de contraseña falla
        SQLAlchemyError: Para errores de base de datos
    
    Returns:
        User | None: El usuario actualizado o None si no existe
    """
    user = get_user(db, user_id)
    if not user:
        return None

    if user_data.nombre is not None:
        setattr(user, "nombre", user_data.nombre.lower())
    if user_data.dpi is not None:
        setattr(user, "dpi", user_data.dpi)
    if user_data.email is not None:
        setattr(user, "email", user_data.email.lower())
    if user_data.password is not None:
        is_valid, error_message = validate_password(user_data.password)
        if not is_valid:
            raise ValueError(error_message)
        setattr(user, "password", hash_password(user_data.password))

    db.commit()
    db.refresh(user)
    return user


def list_users(db: Session, role: str = ADMIN, skip: int = 0, limit: int = 10) -> list[User]:
    """
    Lista usuarios con paginación
    
    Args:
        db: Sesión de base de datos
        role: Rol de los usuarios a listar
        skip: Número de registros a saltar (offset)
        limit: Número máximo de registros a retornar
    """
    return (
        db.query(User)
        .filter(User.rol == role.lower())
        .order_by(User.id)  # SQL Server requiere ORDER BY con OFFSET
        .offset(skip)
        .limit(limit)
        .all()
    )


def count_users(db: Session, role: str = ADMIN) -> int:
    """Cuenta el total de usuarios con un rol específico"""
    return (
        db.query(func.count(User.id))
        .filter(User.rol == role.lower())
        .scalar()
    )


def search_users(db: Session, query: str, role: str = ADMIN, skip: int = 0, limit: int = 5) -> list[User]:
    """
    Busca usuarios por nombre o DPI con paginación
    
    Args:
        db: Sesión de base de datos
        query: Término de búsqueda
        role: Rol de los usuarios a buscar
        skip: Número de registros a saltar
        limit: Número máximo de registros a retornar
    """
    search_pattern = f"%{query}%"
    
    return (
        db.query(User)
        .filter(
            User.rol == role.lower(),
            or_(
                User.nombre.ilike(search_pattern),
                User.dpi.ilike(search_pattern)
            )
        )
        .order_by(User.id)  
        .offset(skip)
        .limit(limit)
        .all()
    )


def count_search_results(db: Session, query: str, role: str = ADMIN) -> int:
    """Cuenta el total de resultados de una búsqueda"""
    search_pattern = f"%{query}%"
    
    return (
        db.query(func.count(User.id))
        .filter(
            User.rol == role.lower(),
            or_(
                User.nombre.ilike(search_pattern),
                User.dpi.ilike(search_pattern)
            )
        )
        .scalar()
    )