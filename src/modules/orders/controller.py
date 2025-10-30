from fastapi import APIRouter, Depends, Query, UploadFile, File, Response
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
import logging
from src.modules.orders.type import OrderCreate, OrderUpdate
from src.modules.orders.service import (
    create_order,
    get_order,
    update_order,
    list_orders,
    count_orders,
    search_customers_for_order,
    search_products_for_order,
    search_orders_by_client_or_phone,
    get_orders_by_date,
    import_orders_from_excel,
    export_orders_to_excel,
    export_orders_to_pdf
)
from src.utils.date_parser import format_datetime_for_display
from src.utils.excel_formatter import ExcelImportError
from db.deps import get_db
from src.utils.http_response import HttpResponse
from src.modules.auth.dependencies import require_role
from src.common.constants.roles import ADMIN, OPERATOR

router = APIRouter(prefix="/orders", tags=["orders"], dependencies=[Depends(require_role([ADMIN, OPERATOR]))])
logger = logging.getLogger(__name__)


@router.post(
    "/",
    summary="Crear orden individual",
    response_description="Orden creada exitosamente"
)
def api_create_order(
    order_data: OrderCreate,
    db: Session = Depends(get_db)
):
    """
    Crea una orden individual de cliente.

    **Campos requeridos:**
    - cliente_id: ID del cliente que hace el pedido
    - producto_id: ID del producto solicitado
    - cantidad: Cantidad solicitada (> 0)

    **Campos opcionales:**
    - fecha_solicitud: Fecha en formato DD/MM/YYYY, DD-MM-YYYY o YYYY-MM-DD (default: hoy)
    - prioridad: 1-5 (default: 1)

    **La orden se crea con:**
    - asignada=False (sin ruta asignada)
    - fecha_solicitud automática si no se proporciona
    """
    try:
        order = create_order(db, order_data)
        logger.info(f"Order created: {order.id} for client {order.cliente_id}")

        return HttpResponse.created(
            response={
                "id": order.id,
                "cliente_id": order.cliente_id,
                "producto_id": order.producto_id,
                "cantidad": order.cantidad,
                "prioridad": order.prioridad,
                "asignada": order.asignada,
                "fecha_solicitud": format_datetime_for_display(order.fecha_solicitud)
            }
        )

    except ValueError as e:
        logger.warning(f"Validation error creating order: {str(e)}")
        return HttpResponse.bad_request(error=str(e))

    except IntegrityError as ie:
        db.rollback()
        logger.error(f"Integrity error creating order: {str(ie)}")
        return HttpResponse.conflict(
            error="El cliente o producto no existe en la base de datos"
        )

    except SQLAlchemyError as se:
        db.rollback()
        logger.error(f"Database error creating order: {str(se)}")
        return HttpResponse.internal_server_error(
            error="Error de base de datos al crear la orden"
        )

    except Exception as e:
        db.rollback()
        logger.exception(f"Unexpected error creating order: {str(e)}")
        return HttpResponse.internal_server_error(
            error="Ocurrió un error inesperado al crear la orden"
        )



@router.get(
    "/search/customers",
    summary="Buscar clientes para crear orden"
)
def api_search_customers_for_order(
    q: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db)
):
    """Busca clientes por nombre o teléfono."""
    try:
        customers = search_customers_for_order(db, q, limit)
        return HttpResponse.success(
            message=f"Se encontraron {len(customers)} clientes",
            response={"total": len(customers), "clientes": customers}
        )
    except Exception as e:
        logger.exception(f"Error searching customers: {str(e)}")
        return HttpResponse.internal_server_error(error="Error al buscar clientes")


@router.get(
    "/search/products",
    summary="Buscar productos para crear orden"
)
def api_search_products_for_order(
    q: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db)
):
    """Busca productos por nombre."""
    try:
        products = search_products_for_order(db, q, limit)
        return HttpResponse.success(
            message=f"Se encontraron {len(products)} productos",
            response={"total": len(products), "productos": products}
        )
    except Exception as e:
        logger.exception(f"Error searching products: {str(e)}")
        return HttpResponse.internal_server_error(error="Error al buscar productos")


@router.get(
    "/search",
    summary="Buscar órdenes por cliente"
)
def api_search_orders(
    q: str = Query(..., min_length=1),
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Busca órdenes por nombre de cliente o teléfono."""
    try:
        orders = search_orders_by_client_or_phone(db, q, skip, limit)
        return HttpResponse.success(
            message=f"Se encontraron {len(orders)} órdenes",
            response={
                "total": len(orders),
                "ordenes": [
                    {
                        "id": o.id,
                        "cliente_id": o.cliente_id,
                        "cliente_nombre": o.cliente.nombre,
                        "producto_nombre": o.producto.nombre,
                        "cantidad": o.cantidad,
                        "prioridad": o.prioridad,
                        "asignada": o.asignada,
                        "fecha_solicitud": format_datetime_for_display(o.fecha_solicitud)
                    }
                    for o in orders
                ]
            }
        )
    except Exception as e:
        logger.exception(f"Error searching orders: {str(e)}")
        return HttpResponse.internal_server_error(error="Error al buscar órdenes")


@router.get(
    "/date/{fecha}",
    summary="Obtener órdenes pendientes por fecha para crear ruta"
)
def api_get_orders_by_date(
    fecha: str,
    db: Session = Depends(get_db)
):
    """
    Obtiene SOLO órdenes NO asignadas de una fecha específica.

    **Uso:** Modal de crear ruta
    - Operador selecciona fecha de salida
    - Sistema muestra órdenes pendientes de ese día
    - Operador selecciona cuáles agregar a la ruta

    **Formatos aceptados (SOLO con guiones o ISO):**
    - DD-MM-YYYY → 10-11-2025 ✅
    - YYYY-MM-DD → 2025-11-10 ✅

    **NO aceptado:**
    - DD/MM/YYYY → 10/11/2025 ❌ (use guiones en su lugar)

    **Ejemplo:** GET /orders/date/10-11-2025
    """
    # Validar que no contenga slashes
    if '/' in fecha:
        logger.warning(f"Date format with slashes rejected: {fecha}")
        return HttpResponse.bad_request(
            error="Formato de fecha inválido. No use '/' en la fecha. Use guiones '-' en su lugar. Ejemplo: 10-11-2025"
        )

    try:
        orders = get_orders_by_date(db, fecha)
        total_ordenes = len(orders)

        # Estadísticas por prioridad
        por_prioridad = {}
        for orden in orders:
            prioridad = orden.prioridad or "normal"
            por_prioridad[prioridad] = por_prioridad.get(prioridad, 0) + 1

        logger.info(f"Found {total_ordenes} unassigned orders for date {fecha}")

        return HttpResponse.success(
            message=f"Se encontraron {total_ordenes} órdenes pendientes para {fecha}",
            response={
                "fecha": fecha,
                "total": total_ordenes,
                "por_prioridad": por_prioridad,
                "ordenes": [
                    {
                        "id": o.id,
                        "cliente_id": o.cliente_id,
                        "cliente_nombre": o.cliente.nombre,
                        "cliente_telefono": o.cliente.telefono or "",
                        "cliente_direccion": o.cliente.direccion,
                        "producto_id": o.producto_id,
                        "producto_nombre": o.producto.nombre,
                        "cantidad": o.cantidad,
                        "prioridad": o.prioridad or "normal",
                        "fecha_solicitud": format_datetime_for_display(o.fecha_solicitud)
                    }
                    for o in orders
                ]
            }
        )
    except ValueError as ve:
        logger.warning(f"Invalid date format: {fecha}")
        return HttpResponse.bad_request(error=str(ve))
    except SQLAlchemyError as se:
        logger.error(f"Database error: {str(se)}")
        return HttpResponse.internal_server_error(error="Error de base de datos")
    except Exception as e:
        logger.exception(f"Error getting orders for date {fecha}")
        return HttpResponse.internal_server_error(error="Error al obtener órdenes")

@router.get(
    "/export/excel",
    summary="Exportar órdenes a Excel"
)
def api_export_orders_excel(db: Session = Depends(get_db)):
    """Exporta todas las órdenes a Excel."""
    try:
        excel_content = export_orders_to_excel(db)
        logger.info("Orders exported to Excel successfully")
        return Response(
            content=excel_content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=ordenes.xlsx"}
        )
    except Exception as e:
        logger.exception("Error exporting to Excel")
        return HttpResponse.internal_server_error(error="Error al exportar a Excel")


@router.get(
    "/export/pdf",
    summary="Exportar órdenes a PDF"
)
def api_export_orders_pdf(db: Session = Depends(get_db)):
    """Exporta todas las órdenes a PDF."""
    try:
        pdf_content = export_orders_to_pdf(db)
        logger.info("Orders exported to PDF successfully")
        return Response(
            content=pdf_content,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=ordenes.pdf"}
        )
    except Exception as e:
        logger.exception("Error exporting to PDF")
        return HttpResponse.internal_server_error(error="Error al exportar a PDF")


@router.post(
    "/import",
    summary="Importar órdenes desde Excel"
)
async def api_import_orders(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Importa órdenes desde Excel."""
    if not file.filename or not file.filename.endswith(('.xlsx', '.xls')):
        return HttpResponse.bad_request(error="Archivo inválido. Use .xlsx o .xls")

    try:
        created_orders, validation_errors, db_errors = import_orders_from_excel(file.file, db)

        if not validation_errors and not db_errors:
            return HttpResponse.custom(
                message=f"Se crearon {len(created_orders)} órdenes exitosamente",
                response={"created_count": len(created_orders)},
                status_code=201
            )
        elif validation_errors:
            return HttpResponse.custom(
                message="Errores de validación",
                response={"validation_errors": validation_errors},
                status_code=422
            )
        else:
            return HttpResponse.custom(
                message=f"Creadas: {len(created_orders)}, Errores: {len(db_errors)}",
                response={"created_count": len(created_orders), "db_errors": db_errors},
                status_code=200
            )
    except ExcelImportError as e:
        return HttpResponse.bad_request(error=str(e))
    except Exception as e:
        logger.exception("Error importing orders")
        return HttpResponse.internal_server_error(error="Error al importar")


@router.get(
    "/",
    summary="Listar todas las órdenes"
)
def api_list_orders(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100)
):
    """Lista órdenes con paginación."""
    try:
        skip = (page - 1) * per_page
        orders = list_orders(db, skip=skip, limit=per_page)

        if not orders:
            return HttpResponse.success(
                message="No se encontraron órdenes",
                response={"orders": [], "pagination": {"page": page, "total_items": 0}}
            )

        total_orders = count_orders(db)
        total_pages = (total_orders + per_page - 1) // per_page

        return HttpResponse.success(
            message=f"Se obtuvieron {len(orders)} órdenes",
            response={
                "orders": [
                    {
                        "id": order.id,
                        "cliente_id": order.cliente_id,
                        "cliente_nombre": order.cliente.nombre if order.cliente else None,
                        "producto_nombre": order.producto.nombre if order.producto else None,
                        "cantidad": order.cantidad,
                        "prioridad": order.prioridad,
                        "asignada": order.asignada,
                        "fecha_solicitud": format_datetime_for_display(order.fecha_solicitud)
                    }
                    for order in orders
                ],
                "pagination": {
                    "page": page,
                    "per_page": per_page,
                    "total_items": total_orders,
                    "total_pages": total_pages,
                    "has_next": page < total_pages,
                    "has_prev": page > 1
                }
            }
        )
    except Exception as e:
        logger.exception("Error listing orders")
        return HttpResponse.internal_server_error(error="Error al listar órdenes")


# IMPORTANTE: Este endpoint DEBE ir DESPUÉS de todas las rutas específicas
@router.get(
    "/{order_id}",
    summary="Obtener orden por ID"
)
def api_get_order(
    order_id: int,
    db: Session = Depends(get_db)
):
    """Obtiene una orden específica por ID."""
    try:
        order = get_order(db, order_id)
        if not order:
            return HttpResponse.not_found(error=f"Orden con ID {order_id} no existe")

        return HttpResponse.success(
            message="Orden obtenida exitosamente",
            response={
                "id": order.id,
                "cliente_id": order.cliente_id,
                "cliente_nombre": order.cliente.nombre if order.cliente else None,
                "producto_nombre": order.producto.nombre if order.producto else None,
                "cantidad": order.cantidad,
                "prioridad": order.prioridad,
                "asignada": order.asignada,
                "ruta_id": order.ruta_id,
                "fecha_solicitud": format_datetime_for_display(order.fecha_solicitud)
            }
        )
    except Exception as e:
        logger.exception(f"Error retrieving order {order_id}")
        return HttpResponse.internal_server_error(error="Error al obtener la orden")


@router.patch(
    "/{order_id}",
    summary="Actualizar orden"
)
def api_update_order(
    order_id: int,
    order_data: OrderUpdate,
    db: Session = Depends(get_db)
):
    """Actualiza una orden existente."""
    try:
        existing_order = get_order(db, order_id)
        if not existing_order:
            return HttpResponse.not_found(error=f"Orden con ID {order_id} no existe")

        if existing_order.asignada:
            return HttpResponse.bad_request(
                error="No se puede editar una orden asignada a una ruta"
            )

        updated_order = update_order(db, order_id, order_data)
        if not updated_order:
            return HttpResponse.internal_server_error(error="Error al actualizar")

        return HttpResponse.updated(
            response={
                "id": updated_order.id,
                "cliente_id": updated_order.cliente_id,
                "producto_id": updated_order.producto_id,
                "cantidad": updated_order.cantidad,
                "prioridad": updated_order.prioridad,
                "fecha_solicitud": format_datetime_for_display(updated_order.fecha_solicitud)
            }
        )
    except IntegrityError:
        db.rollback()
        return HttpResponse.conflict(error="El cliente o producto no existe")
    except Exception as e:
        db.rollback()
        logger.exception(f"Error updating order {order_id}")
        return HttpResponse.internal_server_error(error="Error al actualizar")


@router.delete(
    "/{order_id}",
    summary="Eliminar orden"
)
def api_delete_order(
    order_id: int,
    db: Session = Depends(get_db)
):
    """Elimina una orden."""
    from src.models.orders import Order

    try:
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return HttpResponse.not_found(error=f"Orden con ID {order_id} no existe")

        if order.asignada:
            return HttpResponse.bad_request(
                error="No se puede eliminar una orden asignada"
            )

        db.delete(order)
        db.commit()

        return HttpResponse.success(
            message=f"Orden {order_id} eliminada exitosamente",
            response={"deleted_order_id": order_id}
        )
    except Exception as e:
        db.rollback()
        logger.exception(f"Error deleting order {order_id}")
        return HttpResponse.internal_server_error(error="Error al eliminar")
