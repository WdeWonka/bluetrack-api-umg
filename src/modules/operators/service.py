import re
from typing import List, Tuple
from sqlalchemy import or_, func
from src.models.user import User
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from src.utils.security import hash_password
from src.common.constants.roles import OPERATOR
from src.common.types.userType import UserCreate, UserUpdate,BulkUserImport
import logging
from src.utils.pdf_exporter import PDFReportGenerator
from reportlab.lib.pagesizes import letter
from src.utils.excel_formatter import (
    read_excel,
    convert_to_model_list,
    validate_no_duplicates,
    export_to_excel,
    ExcelImportError
)
logger = logging.getLogger(__name__)

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


def create_user(db: Session, user_data: UserCreate, role: str = OPERATOR) -> User:
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


def list_users(db: Session, role: str = OPERATOR, skip: int = 0, limit: int = 10) -> list[User]:
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


def count_users(db: Session, role: str = OPERATOR) -> int:
    """Cuenta el total de usuarios con un rol específico"""
    return (
        db.query(func.count(User.id))
        .filter(User.rol == role.lower())
        .scalar()
    )


def search_users(db: Session, query: str, role: str = OPERATOR, skip: int = 0, limit: int = 5) -> list[User]:
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


def count_search_results(db: Session, query: str, role: str = OPERATOR) -> int:
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

def import_users_from_excel(
    file,
    db: Session,
    role: str
) -> Tuple[List[User], List[dict], List[dict]]:
    """
    Importa usuarios desde un archivo Excel.

    Args:
        file: UploadFile de FastAPI
        db: Sesión de base de datos
        role: Rol a asignar a los usuarios

    Returns:
        Tuple con:
        - Lista de usuarios creados exitosamente
        - Lista de errores de validación (formato/duplicados en Excel)
        - Lista de errores de base de datos (duplicados en DB)
    """
    required_columns = ['nombre', 'dpi', 'email', 'password']

    try:
        # 1. Leer Excel
        df = read_excel(file, required_columns=required_columns)
        logger.info(f"Excel file read successfully. Found {len(df)} rows")

        # 2. Convertir a modelos Pydantic y validar
        items, validation_errors = convert_to_model_list(
            df,
            model=BulkUserImport,
            clean_data=True
        )

        if validation_errors:
            logger.warning(f"Found {len(validation_errors)} validation errors in Excel")

        # 3. Validar duplicados DENTRO del Excel
        duplicate_errors = validate_no_duplicates(
            items,
            unique_fields=['dpi', 'email']
        )

        if duplicate_errors:
            logger.warning(f"Found {len(duplicate_errors)} duplicate entries in Excel")
            validation_errors.extend(duplicate_errors)

        # 4. Si hay errores de validación, retornar sin crear usuarios
        if validation_errors:
            return [], validation_errors, []

        # 5. Intentar crear usuarios en la base de datos
        created_users = []
        db_errors = []

        for idx, item in enumerate(items):
            row_number = idx + 2  # +2 por header y índice base 0

            # Type assertion para ayudar al type checker
            assert isinstance(item, BulkUserImport)

            try:
                user_data = UserCreate(
                    nombre=item.nombre,
                    dpi=item.dpi,
                    email=item.email,
                    password=item.password
                )

                user = create_user(db, user_data, role=role)
                created_users.append(user)
                logger.info(f"User created: {user.email}")

            except IntegrityError as ie:
                db.rollback()
                error_msg = str(ie.orig) if hasattr(ie, 'orig') else str(ie)

                # Determinar qué campo causó el error
                if 'email' in error_msg.lower():
                    field = 'email'
                elif 'dpi' in error_msg.lower():
                    field = 'dpi'
                else:
                    field = 'email/dpi'

                db_errors.append({
                    "row": row_number,
                    "error": f"Ya existe un usuario con este {field} en la base de datos",
                    "data": {
                        "nombre": item.nombre,
                        "dpi": item.dpi,
                        "email": item.email
                    }
                })
                logger.warning(f"Duplicate user at row {row_number}: {item.email}")

            except ValueError as ve:
                # Errores de validación de contraseña que puedan escapar
                db.rollback()
                db_errors.append({
                    "row": row_number,
                    "error": f"Error de validación: {str(ve)}",
                    "data": {
                        "nombre": item.nombre,
                        "dpi": item.dpi,
                        "email": item.email
                    }
                })
                logger.warning(f"Validation error at row {row_number}: {str(ve)}")

            except Exception as e:
                db.rollback()
                db_errors.append({
                    "row": row_number,
                    "error": f"Error inesperado: {str(e)}",
                    "data": {
                        "nombre": item.nombre,
                        "dpi": item.dpi,
                        "email": item.email
                    }
                })
                logger.error(f"Unexpected error creating user at row {row_number}: {str(e)}")

        logger.info(f"Import completed. Created: {len(created_users)}, DB Errors: {len(db_errors)}")
        return created_users, [], db_errors

    except ExcelImportError as e:
        logger.error(f"Excel import error: {str(e)}")
        raise
    except Exception as e:
        logger.exception(f"Unexpected error during Excel import: {str(e)}")
        raise Exception(f"Error procesando el archivo Excel: {str(e)}")

def export_users_to_excel(db: Session, role: str) -> bytes:
    """
    Exporta todos los usuarios de un rol específico a Excel.

    Args:
        db: Sesión de base de datos
        role: Rol de los usuarios a exportar

    Returns:
        bytes: Contenido del archivo Excel
    """
    try:
        # Obtener todos los usuarios del rol (sin paginación)
        users = db.query(User).filter(User.rol == role.lower()).order_by(User.id).all()

        if not users:
            logger.warning(f"No users found with role: {role}")
            # Retornar Excel vacío con headers
            data = []
        else:
            data = [
                {
                    "nombre": user.nombre,
                    "dpi": user.dpi,
                    "email": user.email,
                    "rol": user.rol,
                }
                for user in users
            ]
            logger.info(f"Exporting {len(users)} users with role: {role}")

        # Generar Excel
        excel_file = export_to_excel(
            data=data,
            filename=f"usuarios_{role}.xlsx",
            sheet_name="Usuarios"
        )

        return excel_file.getvalue()

    except Exception as e:
        logger.exception(f"Error exporting users to Excel: {str(e)}")
        raise Exception(f"Error al exportar usuarios: {str(e)}")

def export_users_to_pdf(db: Session, role: str) -> bytes:
    """
    Exporta todos los usuarios de un rol específico a PDF.

    Args:
        db: Sesión de base de datos
        role: Rol de los usuarios a exportar

    Returns:
        bytes: Contenido del archivo PDF
    """
    try:
        # Obtener todos los usuarios del rol
        users = db.query(User).filter(User.rol == role.lower()).order_by(User.nombre).all()

        if not users:
            logger.warning(f"No users found with role: {role}")
            data = []
        else:
            # Convertir a diccionarios con el orden correcto y nombre capitalizado
            data = []
            for user in users:
                # Extraer valores de forma segura para evitar warnings de SQLAlchemy
                nombre_val = str(user.nombre) if user.nombre is not None else ""
                rol_val = str(user.rol) if user.rol is not None else ""

                data.append({
                    "dpi": user.dpi or "",
                    "nombre": nombre_val.title() if nombre_val else "",
                    "email": user.email or "",
                    "rol": rol_val.capitalize() if rol_val else ""
                })

            logger.info(f"Exporting {len(users)} users to PDF with role: {role}")

        # Anchos personalizados para las columnas (en puntos)
        # DPI: 110, Nombre: 140, Email: 160, Rol: 80
        col_widths = [110.0, 140.0, 160.0, 80.0]

        # Generar PDF con anchos personalizados
        generator = PDFReportGenerator(
            title=f"REPORTE DE {role.upper()}ES",
            page_size=letter,
            author="Sistema",
            subject=f"reporte_{role}s.pdf"
        )

        pdf_bytes = generator.generate(
            headers=["DPI", "Nombre", "Email", "Rol"],
            data=data,
            col_widths=col_widths
        )

        return pdf_bytes

    except Exception as e:
        logger.exception(f"Error exporting users to PDF: {str(e)}")
        raise Exception(f"Error al exportar usuarios a PDF: {str(e)}")
