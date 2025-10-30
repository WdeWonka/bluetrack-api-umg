"""
Servicio para gestión de staff (operadores y vendedores).
"""
import re
from typing import List, Tuple, Optional
from sqlalchemy import or_, func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from src.models.user import User
from src.common.types.userType import StaffCreate, UserUpdate, BulkStaffImport, UserRead
from src.common.constants.roles import OPERATOR, SELLER
from src.utils.security import hash_password
from src.utils.excel_formatter import (
    read_excel,
    convert_to_model_list,
    validate_no_duplicates,
    export_to_excel,
    ExcelImportError
)
from src.utils.pdf_exporter import PDFReportGenerator
from reportlab.lib.pagesizes import letter
import logging

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


def create_user(db: Session, user_data: StaffCreate) -> User:
    """
    Crea un nuevo usuario de staff (operador o vendedor).
    El rol viene en user_data.rol

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
        rol=user_data.rol.lower(),  # ✅ Rol viene del input
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_user(db: Session, user_id: int) -> User | None:
    """Obtiene un usuario por su ID"""
    user = db.query(User).filter(User.id == user_id).first()

    # ✅ Validar que sea staff (operador o vendedor)
    if user and user.rol not in [OPERATOR.lower(), SELLER.lower()]:
        return None

    return user


def update_user(db: Session, user_id: int, user_data: UserUpdate) -> User | None:
    """
    Actualiza un usuario existente.

    ⚠️ NO permite cambiar el rol para mantener control.

    Raises:
        ValueError: Si la validación de contraseña falla
        SQLAlchemyError: Para errores de base de datos

    Returns:
        User | None: El usuario actualizado o None si no existe
    """
    user = get_user(db, user_id)
    if not user:
        return None

    # ✅ Actualizar solo campos permitidos (NO incluye 'rol')
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

def list_users(
    db: Session,
    skip: int = 0,
    limit: int = 10
) -> list[User]:
    """
    Lista TODOS los usuarios de staff (operadores y vendedores) con paginación.

    Esta función trae ambos roles sin necesidad de filtro.

    Args:
        db: Sesión de base de datos
        skip: Número de registros a saltar (offset)
        limit: Número máximo de registros a retornar

    Returns:
        Lista de usuarios del staff (operadores y vendedores)
    """
    query = db.query(User).filter(
        User.rol.in_([OPERATOR.lower(), SELLER.lower()])
    )

    return query.order_by(User.id.desc()).offset(skip).limit(limit).all()

def count_users(db: Session) -> int:
    """
    Cuenta el total de usuarios de staff (operadores y vendedores).
    """
    return db.query(func.count(User.id)).filter(
        User.rol.in_([OPERATOR.lower(), SELLER.lower()])
    ).scalar()

def search_users(
    db: Session,
    query: str,
    role: Optional[str] = None,
    skip: int = 0,
    limit: int = 5
) -> list[User]:
    """
    Busca usuarios de staff por nombre o DPI con paginación

    Args:
        db: Sesión de base de datos
        query: Término de búsqueda
        role: Rol de los usuarios a buscar (opcional)
        skip: Número de registros a saltar
        limit: Número máximo de registros a retornar
    """
    search_pattern = f"%{query}%"

    db_query = db.query(User).filter(
        or_(
            User.nombre.ilike(search_pattern),
            User.dpi.ilike(search_pattern)
        )
    )

    if role:
        db_query = db_query.filter(User.rol == role.lower())
    else:
        db_query = db_query.filter(User.rol.in_([OPERATOR.lower(), SELLER.lower()]))

    return db_query.order_by(User.id).offset(skip).limit(limit).all()


def count_search_results(db: Session, query: str, role: Optional[str] = None) -> int:
    """Cuenta el total de resultados de una búsqueda"""
    search_pattern = f"%{query}%"

    db_query = db.query(func.count(User.id)).filter(
        or_(
            User.nombre.ilike(search_pattern),
            User.dpi.ilike(search_pattern)
        )
    )

    if role:
        db_query = db_query.filter(User.rol == role.lower())
    else:
        db_query = db_query.filter(User.rol.in_([OPERATOR.lower(), SELLER.lower()]))

    return db_query.scalar()


def get_available_sellers_by_date(
    db: Session,
    fecha: str
) -> list[User]:
    """
    Obtiene vendedores disponibles (no asignados a ruta) en una fecha específica.

    Args:
        db: Sesión de base de datos
        fecha: Fecha en formato YYYY-MM-DD

    Returns:
        Lista de vendedores disponibles

    Raises:
        ValueError: Si el formato de fecha es inválido
    """
    from datetime import datetime
    from src.models.route import Route as Ruta

    # Parsear fecha
    try:
        fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("Formato de fecha inválido. Use YYYY-MM-DD")

    # Obtener IDs de vendedores ocupados ese día (subquery)
    vendedores_ocupados_subquery = (
        db.query(Ruta.vendedor_id)
        .filter(Ruta.fecha == fecha_obj)
        .distinct()
        .subquery()
    )

    # Obtener vendedores activos que NO están ocupados
    vendedores_disponibles = (
        db.query(User)
        .filter(
            User.rol == SELLER.lower(),
            User.activo == True,
            ~User.id.in_(vendedores_ocupados_subquery)  # NOT IN (subquery)
        )
        .order_by(User.nombre)
        .all()
    )

    logger.info(f"Found {len(vendedores_disponibles)} available sellers for {fecha_obj}")
    return vendedores_disponibles


def get_all_sellers(db: Session) -> list[User]:
    """
    Obtiene todos los vendedores activos (sin filtro de disponibilidad).

    Args:
        db: Sesión de base de datos

    Returns:
        Lista de todos los vendedores activos
    """
    vendedores = (
        db.query(User)
        .filter(
            User.rol == SELLER.lower(),
            User.activo == True
        )
        .order_by(User.nombre)
        .all()
    )

    logger.info(f"Retrieved {len(vendedores)} active sellers")
    return vendedores


def import_users_from_excel(
    file,
    db: Session
) -> Tuple[List[User], List[dict], List[dict]]:
    """
    Importa usuarios de staff desde un archivo Excel.
    El rol debe venir en el archivo Excel.

    Args:
        file: UploadFile de FastAPI
        db: Sesión de base de datos

    Returns:
        Tuple con:
        - Lista de usuarios creados exitosamente
        - Lista de errores de validación (formato/duplicados en Excel)
        - Lista de errores de base de datos (duplicados en DB)
    """
    required_columns = ['nombre', 'dpi', 'email', 'password', 'rol']

    try:
        # 1. Leer Excel
        df = read_excel(file, required_columns=required_columns)
        logger.info(f"Excel file read successfully. Found {len(df)} rows")

        # 2. Convertir a modelos Pydantic y validar
        items, validation_errors = convert_to_model_list(
            df,
            model=BulkStaffImport,
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

            assert isinstance(item, BulkStaffImport)

            try:
                user_data = StaffCreate(
                    nombre=item.nombre,
                    dpi=item.dpi,
                    email=item.email,
                    password=item.password,
                    rol=item.rol  # ✅ Rol desde el Excel
                )

                user = create_user(db, user_data)
                created_users.append(user)
                logger.info(f"User created: {user.email} with role {user.rol}")

            except IntegrityError as ie:
                db.rollback()
                error_msg = str(ie.orig) if hasattr(ie, 'orig') else str(ie)

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
                        "email": item.email,
                        "rol": item.rol
                    }
                })
                logger.warning(f"Duplicate user at row {row_number}: {item.email}")

            except ValueError as ve:
                db.rollback()
                db_errors.append({
                    "row": row_number,
                    "error": f"Error de validación: {str(ve)}",
                    "data": {
                        "nombre": item.nombre,
                        "dpi": item.dpi,
                        "email": item.email,
                        "rol": item.rol
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
                        "email": item.email,
                        "rol": item.rol
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


def export_users_to_excel(db: Session, role: Optional[str] = None) -> bytes:
    """
    Exporta usuarios de staff a Excel.

    Args:
        db: Sesión de base de datos
        role: Si es None, exporta ambos roles. Si especifica, solo ese rol.

    Returns:
        bytes: Contenido del archivo Excel
    """
    try:
        query = db.query(User)

        if role:
            query = query.filter(User.rol == role.lower())
        else:
            query = query.filter(User.rol.in_([OPERATOR.lower(), SELLER.lower()]))

        users = query.order_by(User.id).all()

        if not users:
            logger.warning(f"No staff users found with role: {role}")
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
            logger.info(f"Exporting {len(users)} staff users")

        # Generar Excel
        filename = f"staff_{role if role else 'todos'}.xlsx"
        excel_file = export_to_excel(
            data=data,
            filename=filename,
            sheet_name="Staff"
        )

        return excel_file.getvalue()

    except Exception as e:
        logger.exception(f"Error exporting staff to Excel: {str(e)}")
        raise Exception(f"Error al exportar staff: {str(e)}")


def export_users_to_pdf(db: Session, role: Optional[str] = None) -> bytes:
    """
    Exporta usuarios de staff a PDF.

    Args:
        db: Sesión de base de datos
        role: Si es None, exporta ambos roles. Si especifica, solo ese rol.

    Returns:
        bytes: Contenido del archivo PDF
    """
    try:
        query = db.query(User)

        if role:
            query = query.filter(User.rol == role.lower())
        else:
            query = query.filter(User.rol.in_([OPERATOR.lower(), SELLER.lower()]))

        users = query.order_by(User.nombre).all()

        if not users:
            logger.warning(f"No staff users found with role: {role}")
            data = []
        else:
            data = []
            for user in users:
                nombre_val = str(user.nombre) if user.nombre is not None else ""
                rol_val = str(user.rol) if user.rol is not None else ""

                data.append({
                    "dpi": user.dpi or "",
                    "nombre": nombre_val.title() if nombre_val else "",
                    "email": user.email or "",
                    "rol": rol_val.capitalize() if rol_val else ""
                })

            logger.info(f"Exporting {len(users)} staff users to PDF")

        # Anchos de columnas
        col_widths = [110.0, 140.0, 160.0, 80.0]

        # Generar PDF
        title = f"REPORTE DE {'STAFF' if not role else role.upper()}"
        generator = PDFReportGenerator(
            title=title,
            page_size=letter,
            author="Sistema",
            subject=f"reporte_staff.pdf"
        )

        pdf_bytes = generator.generate(
            headers=["DPI", "Nombre", "Email", "Rol"],
            data=data,
            col_widths=col_widths
        )

        return pdf_bytes

    except Exception as e:
        logger.exception(f"Error exporting staff to PDF: {str(e)}")
        raise Exception(f"Error al exportar staff a PDF: {str(e)}")
