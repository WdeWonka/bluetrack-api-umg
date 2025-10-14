from fastapi import APIRouter, Depends, File, UploadFile, Response, Query
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

from db.deps import get_db
from src.modules.sellers.service import (
    create_user, 
    get_user, 
    update_user, 
    list_users,
    search_users,
    count_users,
    count_search_results,
    import_users_from_excel,
    export_users_to_excel,
    export_users_to_pdf
)

from src.utils.excel_formatter import ExcelImportError, create_template_excel

from src.common.types.userType import UserCreate, UserUpdate, UserRead
from src.common.constants.roles import SELLER
from src.utils.http_response import HttpResponse
import logging

logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/sellers",
    tags=["sellers"]
)
@router.post(
    "/users",
    summary="Create a new seller user",
    response_description="User created successfully"
)
def api_create_user(
    user_data: UserCreate,
    db: Session = Depends(get_db)
):
    try:
        user = create_user(db, user_data, role=SELLER)
        logger.info(f"User created successfully: {user.email}")
        return HttpResponse.created(response=UserRead.model_validate(user).model_dump(mode='json'))
        
    except ValueError as ve:
        # Error de validación (contraseña)
        logger.error(f"Validation error creating user: {str(ve)}")
        return HttpResponse.unprocessable_entity(error=str(ve))
    
    except IntegrityError as ie:
        # Error de integridad (usuario duplicado)
        db.rollback()
        logger.error(f"Integrity error creating user: {str(ie)}")
        return HttpResponse.conflict(error="El usuario ya existe en la base de datos (email o DPI duplicado)")
    
    except SQLAlchemyError as se:
        # Otros errores de base de datos
        db.rollback()
        logger.error(f"Database error creating user: {str(se)}")
        return HttpResponse.internal_server_error(error="Error de base de datos al crear el usuario")
    
    except Exception as e:
        # Errores inesperados
        db.rollback()
        logger.exception(f"Unexpected error creating user: {str(e)}")
        return HttpResponse.internal_server_error(error="Ocurrió un error inesperado al crear el usuario")


# IMPORTANTE: Esta ruta debe estar ANTES de /users/{user_id}
@router.get(
    "/users/search",
    summary="Search users by name or DPI",
    response_description="Search results retrieved successfully"
)
def api_search_users(
    db: Session = Depends(get_db),
    q: str = Query(..., min_length=1, description="Search query (name or DPI)"),
    page: int = Query(1, ge=1, description="Page number (starts at 1)"),
    per_page: int = Query(5, ge=1, le=50, description="Items per page (max 50)")
):
   
    try:
        skip = (page - 1) * per_page

        results = search_users(db, query=q, role=SELLER, skip=skip, limit=per_page)

        if not results or len(results) == 0:
            logger.info(f"No users found for search query: {q}")
            return HttpResponse.success(
                message=f"No users found matching '{q}'",
                response={
                    "users": [],
                    "search_query": q,
                    "pagination": {
                        "page": page,
                        "per_page": per_page,
                        "total_items": 0,
                        "total_pages": 0,
                        "has_next": False,
                        "has_prev": False
                    }
                }
            )
        
        total_results = count_search_results(db, query=q, role=SELLER)
        total_pages = (total_results + per_page - 1) // per_page
        
        logger.info(f"Found {len(results)} users for search query: {q}")
        return HttpResponse.success(
            message=f"Found {total_results} users matching '{q}'",
            response={
                "users": [UserRead.model_validate(user).model_dump(mode='json') for user in results],
                "search_query": q,
                "pagination": {
                    "page": page,
                    "per_page": per_page,
                    "total_items": total_results,
                    "total_pages": total_pages,
                    "has_next": page < total_pages,
                    "has_prev": page > 1
                }
            }
        )
    
    except SQLAlchemyError as se:
        logger.error(f"Database error searching users with query '{q}': {str(se)}")
        return HttpResponse.internal_server_error(error="Error de base de datos al buscar usuarios")
        
    except Exception as e:
        logger.exception(f"Unexpected error searching users with query '{q}': {str(e)}")
        return HttpResponse.internal_server_error(error="An unexpected error occurred while searching users")


@router.post(
    "/users/import",
    summary="Import sellers users from Excel file",
    response_description="Sellers imported successfully"
)
async def api_import_sellers(
    file: UploadFile = File(..., description="Excel file (.xlsx) with seller data"),
    db: Session = Depends(get_db)
):
    """
    Import multiple sellers from an Excel file.

    Same format as sellers import. See /sellers/users/import for details.
    """
    # Validar que el archivo tenga nombre
    if not file.filename:
        logger.warning("File uploaded without filename")
        return HttpResponse.bad_request(error="El archivo no tiene nombre")
    
    # Validar extensión del archivo
    if not file.filename.endswith(('.xlsx', '.xls')):
        logger.warning(f"Invalid file type uploaded: {file.filename}")
        return HttpResponse.bad_request(
            error="Tipo de archivo inválido. Por favor sube un archivo Excel (.xlsx o .xls)"
        )
    
    try:
        created_users, validation_errors, db_errors = import_users_from_excel(
            file=file,
            db=db,
            role=SELLER
        )
        
        if not validation_errors and not db_errors:
            logger.info(f"All {len(created_users)} sellers imported successfully")
            return HttpResponse.custom(
                message=f"Se crearon {len(created_users)} vendedores exitosamente",
                response={
                    "created_count": len(created_users),
                    "users": [
                        {
                            "nombre": user.nombre,
                            "email": user.email,
                            "dpi": user.dpi
                        }
                        for user in created_users
                    ]
                },
                status_code=201
            )
        
        elif validation_errors and not db_errors:
            logger.warning(f"Import failed with {len(validation_errors)} validation errors")
            return HttpResponse.custom(
                message="El archivo contiene errores de validación. No se creó ningún vendedor.",
                response={
                    "validation_errors": validation_errors,
                    "total_errors": len(validation_errors)
                },
                status_code=422
            )
        
        else:
            logger.info(f"Partial import: {len(created_users)} created, {len(db_errors)} failed")
            return HttpResponse.custom(
                message=f"Se crearon {len(created_users)} vendedores. {len(db_errors)} vendedores no se pudieron crear.",
                response={
                    "created_count": len(created_users),
                    "error_count": len(db_errors),
                    "created_users": [
                        {
                            
                            "nombre": user.nombre,
                            "email": user.email,
                            "dpi": user.dpi
                        }
                        for user in created_users
                    ],
                    "db_errors": db_errors
                },
                status_code=200
            )
    
    except ExcelImportError as e:
        logger.error(f"Excel import error: {str(e)}")
        return HttpResponse.bad_request(error=str(e))
    
    except Exception as e:
        logger.exception(f"Unexpected error during import: {str(e)}")
        return HttpResponse.internal_server_error(
            error="Ocurrió un error inesperado al procesar el archivo"
        )
    
    
@router.get(
    "/users/export/excel",
    summary="Export all users to Excel",
    response_description="Excel file with all users"
)
def api_export_users(db: Session = Depends(get_db)):
    """
    Export all seller users to an Excel file.
    
    **Returns:**
    - Excel file (.xlsx) with all user information
    - Columns: id, nombre, dpi, email, rol, fecha_creacion
    - Password is NOT included for security reasons
    """
    try:
        excel_content = export_users_to_excel(db, role=SELLER)
        
        logger.info("Users exported to Excel successfully")
        return Response(
            content=excel_content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": "attachment; filename=usuarios_sellers.xlsx"
            }
        )
    
    except Exception as e:
        logger.exception(f"Error exporting users: {str(e)}")
        return HttpResponse.internal_server_error(
            error="Ocurrió un error al exportar los usuarios"
        )

@router.get(
    "/users/export/pdf",
    summary="Export all sellers to PDF",
    response_description="PDF file with all sellers"
)
def api_export_sellers_pdf(db: Session = Depends(get_db)):
    """
    Export all seller users to a PDF report.
    
    **Returns:**
    - PDF file with formatted table
    - Columns: ID, Nombre, DPI, Email, Rol, Fecha Creación
    """
    try:
        pdf_content = export_users_to_pdf(db, role=SELLER)
        
        logger.info("Sellers exported to PDF successfully")
        return Response(
            content=pdf_content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": "attachment; filename=reporte_sellers.pdf"
            }
        )
    
    except Exception as e:
        logger.exception(f"Error exporting sellers to PDF: {str(e)}")
        return HttpResponse.internal_server_error(
            error="Ocurrió un error al exportar los vendedores a PDF"
        )


@router.get(
    "/users/template",
    summary="Download Excel template for bulk import",
    response_description="Excel template file"
)
def api_download_template():
    """
    Download an Excel template for bulk user import.
    
    **Returns:**
    - Excel template with required columns and example data
    - Use this template to prepare your bulk import file
    """
    try:
        template = create_template_excel(
            columns=["nombre", "dpi", "email", "password"],
            example_data=[
                {
                    "nombre": "Juan Pérez López",
                    "dpi": "1234567890123",
                    "email": "juan.perez@example.com",
                    "password": "Admin123"
                },
                {
                    "nombre": "María García Hernández",
                    "dpi": "9876543210987",
                    "email": "maria.garcia@example.com",
                    "password": "Secure456"
                }
            ],
            filename="template_usuarios.xlsx"
        )
        
        logger.info("Template downloaded successfully")
        return Response(
            content=template.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": "attachment; filename=template_usuarios.xlsx"
            }
        )
    
    except Exception as e:
        logger.exception(f"Error creating template: {str(e)}")
        return HttpResponse.internal_server_error(
            error="Ocurrió un error al generar el template"
        )



@router.get(
    "/users/{user_id}",
    summary="Get user by ID",
    response_description="User details retrieved successfully"
)
def api_get_user(
    user_id: int,
    db: Session = Depends(get_db)
):
    """
    Retrieve a specific user by their ID.
    
    - **user_id**: The ID of the user to retrieve
    """
    try:
        user = get_user(db, user_id)
        
        if not user:
            logger.warning(f"User not found with ID: {user_id}")
            return HttpResponse.not_found(error=f"User with ID {user_id} does not exist")
        
        logger.info(f"User retrieved successfully with ID: {user_id}")
        return HttpResponse.success(
            message="User retrieved successfully", 
            response=UserRead.model_validate(user).model_dump(mode='json')
        )
        
    except ValueError as ve:
        logger.error(f"Invalid user ID: {str(ve)}")
        return HttpResponse.bad_request(error="Invalid user ID format")
    
    except Exception as e:
        logger.exception(f"Unexpected error retrieving user {user_id}: {str(e)}")
        return HttpResponse.internal_server_error(error="An unexpected error occurred while retrieving the user")


@router.put(
    "/users/{user_id}",
    summary="Update user information",
    response_description="User updated successfully"
)
def api_update_user(
    user_id: int,
    user_data: UserUpdate,
    db: Session = Depends(get_db)
):
    """
    Update an existing user's information.
    
    - **user_id**: The ID of the user to update
    - **user_data**: Updated user information
    """
    try:
        user = update_user(db, user_id, user_data)
        
        if not user:
            logger.warning(f"User not found for update with ID: {user_id}")
            return HttpResponse.not_found(error=f"User with ID {user_id} does not exist")
        
        logger.info(f"User updated successfully with ID: {user_id}")
        return HttpResponse.updated(response=UserRead.model_validate(user).model_dump(mode='json'))
        
    except ValueError as ve:
        db.rollback()
        logger.error(f"Validation error updating user {user_id}: {str(ve)}")
        return HttpResponse.unprocessable_entity(error=str(ve))
    
    except IntegrityError as ie:
        db.rollback()
        logger.error(f"Integrity error updating user {user_id}: {str(ie)}")
        return HttpResponse.conflict(error="Email o DPI duplicado")
    
    except SQLAlchemyError as se:
        db.rollback()
        logger.error(f"Database error updating user {user_id}: {str(se)}")
        return HttpResponse.internal_server_error(error="Error de base de datos al actualizar el usuario")
    
    except Exception as e:
        db.rollback()
        logger.exception(f"Unexpected error updating user {user_id}: {str(e)}")
        return HttpResponse.internal_server_error(error="An unexpected error occurred while updating the user")


@router.get(
    "/users",
    summary="List all users with pagination",
    response_description="Paginated list of users retrieved successfully"
)
def api_list_users(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1, description="Page number (starts at 1)"),
    per_page: int = Query(10, ge=1, le=100, description="Items per page (max 100)")
):
    
    try:
        skip = (page - 1) * per_page
        
        users = list_users(db, role=SELLER, skip=skip, limit=per_page)
        
        if not users or len(users) == 0:
            logger.info("No users found in the database")
            return HttpResponse.success(
                message="No users found",
                response={
                    "users": [],
                    "pagination": {
                        "page": page,
                        "per_page": per_page,
                        "total_items": 0,
                        "total_pages": 0,
                        "has_next": False,
                        "has_prev": False
                    }
                }
            )
        
        total_users = count_users(db, role=SELLER)
        total_pages = (total_users + per_page - 1) // per_page
        
        logger.info(f"Retrieved {len(users)} users for page {page}")
        return HttpResponse.success(
            message=f"Retrieved {len(users)} users successfully",
            response={
                "users": [UserRead.model_validate(user).model_dump(mode='json') for user in users],
                "pagination": {
                    "page": page,
                    "per_page": per_page,
                    "total_items": total_users,
                    "total_pages": total_pages,
                    "has_next": page < total_pages,
                    "has_prev": page > 1
                }
            }
        )
    
    except SQLAlchemyError as se:
        logger.error(f"Database error listing users: {str(se)}")
        return HttpResponse.internal_server_error(error="Error de base de datos al listar usuarios")
        
    except Exception as e:
        logger.exception(f"Unexpected error listing users: {str(e)}")
        return HttpResponse.internal_server_error(error="An unexpected error occurred while retrieving users")


