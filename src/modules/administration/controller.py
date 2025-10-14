from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from db.deps import get_db
from src.modules.administration.service import (
    create_user, 
    get_user, 
    update_user, 
    list_users,
    search_users,
    count_users,
    count_search_results,
)
from src.common.types.userType import UserCreate, UserUpdate, UserRead
from src.common.constants.roles import ADMIN
from src.utils.http_response import HttpResponse
import logging

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin",
    tags=["admin"]
)


@router.post(
    "/users",
    summary="Create a new admin user",
    response_description="User created successfully"
)
def api_create_user(
    user_data: UserCreate,
    db: Session = Depends(get_db)
):
    try:
        user = create_user(db, user_data, role=ADMIN)
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
    """
    Search users by name or DPI with pagination.
    
    - **q**: Search query (name or DPI)
    - **page**: Page number (starts at 1)
    - **per_page**: Number of items per page (default: 5, max: 50)
    
    Example: /admin/users/search?q=Juan&page=1&per_page=5
    """
    try:
        skip = (page - 1) * per_page
        
        results = search_users(db, query=q, role=ADMIN, skip=skip, limit=per_page)
        
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
        
        total_results = count_search_results(db, query=q, role=ADMIN)
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
    """
    Retrieve a paginated list of all users.
    
    - **page**: Page number (starts at 1)
    - **per_page**: Number of items per page (default: 10, max: 100)
    
    Example: /admin/users?page=1&per_page=10
    """
    try:
        skip = (page - 1) * per_page
        
        users = list_users(db, role=ADMIN, skip=skip, limit=per_page)
        
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
        
        total_users = count_users(db, role=ADMIN)
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