from fastapi import APIRouter, Depends, Query, UploadFile, File, Response
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from src.utils.product_helpers import get_product_display_name_from_order
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
    export_orders_to_excel,
    export_orders_to_pdf,
    cancel_order
)
from src.utils.date_parser import format_datetime_for_display
from db.deps import get_db
from src.utils.http_response import HttpResponse
from src.modules.auth.dependencies import require_role
from src.common.constants.roles import ADMIN, OPERATOR

router = APIRouter(
    prefix="/orders",
    tags=["orders"],
    dependencies=[Depends(require_role(ADMIN, OPERATOR))]
)

logger = logging.getLogger(__name__)



@router.post("/", summary="Crear orden individual")
def api_create_order(
    order_data: OrderCreate,
    db: Session = Depends(get_db)
):
    """
    Crea una orden individual de cliente y RESERVA el stock.
    **Formato de fecha:** DD/MM/YYYY
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
                "cancelada": order.cancelada,
                "fecha_solicitud": format_datetime_for_display(order.fecha_solicitud)  # 🔥 DD/MM/YYYY
            }
        )

    except ValueError as e:
        logger.warning(f"Validation error creating order: {str(e)}")
        return HttpResponse.bad_request(error=str(e))
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
    q: str = Query("", min_length=0),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db)
):
    """
    Busca clientes por nombre o teléfono.
    Si no se proporciona query, retorna los primeros clientes ordenados alfabéticamente.
    """
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
    q: str = Query("", min_length=0),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db)
):
    """
    Busca productos por nombre.
    Si no se proporciona query, retorna los primeros productos ordenados alfabéticamente.

    **Retorna:**
    - stock_total: Inventario físico total
    - stock_reservado: Stock comprometido en órdenes pendientes
    - stock_disponible: stock_total - stock_reservado
    """
    try:
        products = search_products_for_order(db, q, limit)
        return HttpResponse.success(
            message=f"Se encontraron {len(products)} productos",
            response={"total": len(products), "productos": products}
        )
    except Exception as e:
        logger.exception(f"Error searching products: {str(e)}")
        return HttpResponse.internal_server_error(error="Error al buscar productos")



@router.get("/search", summary="Buscar órdenes por cliente")
def api_search_orders(
    q: str = Query(..., min_length=1),
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    include_cancelled: bool = Query(False, description="Incluir órdenes canceladas"),
    db: Session = Depends(get_db)
):
    """
    Busca órdenes por nombre de cliente o teléfono.
    **Formato de fecha:** DD/MM/YYYY
    """
    try:
        orders = search_orders_by_client_or_phone(
            db, q, skip, limit, include_cancelled
        )
        return HttpResponse.success(
            message=f"Se encontraron {len(orders)} órdenes",
            response={
                "total": len(orders),
                "ordenes": [
                    {
                        "id": o.id,
                        "cliente_id": o.cliente_id,
                        "cliente_nombre": o.cliente.nombre,
                        "producto_nombre": get_product_display_name_from_order(o),
                        "cantidad": o.cantidad,
                        "prioridad": o.prioridad,
                        "asignada": o.asignada,
                        "cancelada": o.cancelada,
                        "fecha_solicitud": format_datetime_for_display(o.fecha_solicitud)  # 🔥 DD/MM/YYYY
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
    Obtiene SOLO órdenes NO asignadas y NO canceladas de una fecha específica.

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
    if '/' in fecha:
        logger.warning(f"Date format with slashes rejected: {fecha}")
        return HttpResponse.bad_request(
            error="Formato de fecha inválido. No use '/' en la fecha. Use guiones '-' en su lugar. Ejemplo: 10-11-2025"
        )

    try:
        orders = get_orders_by_date(db, fecha)
        total_ordenes = len(orders)

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
                        "producto_nombre": get_product_display_name_from_order(o),
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

# router.py - Actualizar descripciones de endpoints

@router.get(
    "/export/excel",
    summary="Exportar todas las órdenes a Excel"
)
def api_export_orders_excel(db: Session = Depends(get_db)):
    """
    Exporta TODAS las órdenes (activas Y canceladas) a Excel.

    **Columnas incluidas:**
    - ID
    - Cliente
    - Dirección
    - Producto
    - Cantidad
    - Fecha Solicitud
    - Asignada (Sí/No)
    - Vigencia (Activa/Cancelada) ← Nueva columna

    **Nota:** Este endpoint exporta todas las órdenes sin filtros.
    """
    try:
        excel_content = export_orders_to_excel(db)
        logger.info("All orders (active + cancelled) exported to Excel successfully")
        return Response(
            content=excel_content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=ordenes_completas.xlsx"}
        )
    except Exception as e:
        logger.exception("Error exporting to Excel")
        return HttpResponse.internal_server_error(error="Error al exportar a Excel")


@router.get(
    "/export/pdf",
    summary="Exportar todas las órdenes a PDF con estadísticas"
)
def api_export_orders_pdf(db: Session = Depends(get_db)):
    """
    Exporta TODAS las órdenes (activas Y canceladas) a PDF con resumen estadístico.

    **Incluye:**
    - 📊 Resumen estadístico visual:
      - Total de órdenes
      - Órdenes activas (cantidad y porcentaje)
      - Órdenes canceladas (cantidad y porcentaje)

    - 📋 Tabla completa con todas las órdenes:
      - ID
      - Cliente
      - Dirección
      - Producto
      - Cantidad
      - Fecha Solicitud
      - Vigencia (resaltada en rojo si está cancelada)

    **Diseño:** Las órdenes canceladas se muestran en rojo para fácil identificación.
    """
    try:
        pdf_content = export_orders_to_pdf(db)
        logger.info("All orders (active + cancelled) exported to PDF with stats successfully")
        return Response(
            content=pdf_content,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=ordenes_completas.pdf"}
        )
    except Exception as e:
        logger.exception("Error exporting to PDF")
        return HttpResponse.internal_server_error(error="Error al exportar a PDF")



@router.get("/", summary="Listar todas las órdenes")
def api_list_orders(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100),
    include_cancelled: bool = Query(False, description="Incluir órdenes canceladas")
):
    """
    Lista órdenes con paginación.
    **Formato de fecha:** DD/MM/YYYY
    """
    try:
        skip = (page - 1) * per_page
        orders = list_orders(db, skip=skip, limit=per_page, include_cancelled=include_cancelled)

        if not orders:
            return HttpResponse.success(
                message="No se encontraron órdenes",
                response={
                    "orders": [],
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

        total_orders = count_orders(db, include_cancelled=include_cancelled)
        total_pages = (total_orders + per_page - 1) // per_page

        return HttpResponse.success(
            message=f"Se obtuvieron {len(orders)} órdenes",
            response={
                "orders": [
                    {
                        "id": order.id,
                        "cliente_id": order.cliente_id,
                        "cliente_nombre": order.cliente.nombre if order.cliente else None,
                        "producto_nombre": (
                            order.producto_nombre_snapshot
                            or (order.producto.nombre if order.producto else "Producto no disponible")
                        ),
                        "cantidad": order.cantidad,
                        "prioridad": order.prioridad,
                        "asignada": order.asignada,
                        "cancelada": order.cancelada,
                        "fecha_solicitud": format_datetime_for_display(order.fecha_solicitud)  # 🔥 DD/MM/YYYY
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



@router.get("/{order_id}", summary="Obtener orden por ID")
def api_get_order(
    order_id: int,
    db: Session = Depends(get_db)
):
    """
    Obtiene una orden específica por ID.
    **Formato de fecha:** DD/MM/YYYY
    """
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
                "producto_id": order.producto_id,
                "producto_nombre": get_product_display_name_from_order(order),
                "cantidad": order.cantidad,
                "prioridad": order.prioridad,
                "asignada": order.asignada,
                "cancelada": order.cancelada,
                "ruta_id": order.ruta_id,
                "fecha_solicitud": format_datetime_for_display(order.fecha_solicitud)  # 🔥 DD/MM/YYYY
            }
        )
    except Exception as e:
        logger.exception(f"Error retrieving order {order_id}")
        return HttpResponse.internal_server_error(error="Error al obtener la orden")


@router.patch("/{order_id}", summary="Actualizar orden")
def api_update_order(
    order_id: int,
    order_data: OrderUpdate,
    db: Session = Depends(get_db)
):
    """
    Actualiza una orden existente.
    **Formato de fecha:** DD/MM/YYYY
    """
    try:
        existing_order = get_order(db, order_id)
        if not existing_order:
            return HttpResponse.not_found(error=f"Orden con ID {order_id} no existe")

        updated_order = update_order(db, order_id, order_data)
        if not updated_order:
            return HttpResponse.internal_server_error(error="Error al actualizar")

        return HttpResponse.updated(
            response={
                "id": updated_order.id,
                "cliente_id": updated_order.cliente_id,
                "producto_id": updated_order.producto_id,
                "producto_nombre": get_product_display_name_from_order(updated_order),
                "cantidad": updated_order.cantidad,
                "prioridad": updated_order.prioridad,
                "asignada": updated_order.asignada,
                "cancelada": updated_order.cancelada,
                "fecha_solicitud": format_datetime_for_display(updated_order.fecha_solicitud)  # 🔥 DD/MM/YYYY
            }
        )

    except ValueError as e:
        logger.warning(f"Validation error updating order {order_id}: {str(e)}")
        return HttpResponse.bad_request(error=str(e))
    except Exception as e:
        db.rollback()
        logger.exception(f"Error updating order {order_id}")
        return HttpResponse.internal_server_error(error="Error al actualizar la orden")

@router.delete(
    "/{order_id}/cancel",
    summary="Cancelar orden"
)
def api_cancel_order(
    order_id: int,
    db: Session = Depends(get_db)
):
    """
    Cancela una orden y LIBERA el stock reservado.

    **Solo se pueden cancelar órdenes:**
    - ✅ NO asignadas a rutas
    - ✅ NO canceladas previamente

    **¿Qué pasa con el stock?**
    - El stock_reservado se LIBERA automáticamente
    - El stock vuelve a estar disponible para nuevas órdenes
    - El stock_total NO se modifica (nunca se descontó)

    **Ejemplo de flujo:**
    ```
    ANTES DE CANCELAR:
    stock_total = 500
    stock_reservado = 100 (de esta orden)
    stock_disponible = 400

    DESPUÉS DE CANCELAR:
    stock_total = 500 (sin cambios)
    stock_reservado = 0 (liberado)
    stock_disponible = 500 (disponible de nuevo)
    ```

    **Si la orden está en una ruta:**
    - No se puede cancelar desde aquí
    - Debe marcarse como "no entregada" desde la ruta
    - El stock se devolverá al finalizar la ruta
    """
    try:
        # Obtener orden para mostrar info en respuesta
        order_before = get_order(db, order_id)
        if not order_before:
            return HttpResponse.not_found(error=f"Orden con ID {order_id} no existe")

        # Guardar info del producto para la respuesta
        producto_nombre = get_product_display_name_from_order(order_before)
        cantidad_liberada = order_before.cantidad

        # Cancelar orden
        order = cancel_order(db, order_id)

        logger.info(
            f"✅ Order #{order_id} cancelled successfully. "
            f"Released {cantidad_liberada} units of {producto_nombre}"
        )

        return HttpResponse.success(
            message=f"Orden #{order_id} cancelada exitosamente. "
                   f"Se liberaron {cantidad_liberada} unidades de {producto_nombre}.",
            response={
                "id": order.id,
                "cancelada": order.cancelada,
                "cliente_id": order.cliente_id,
                "producto_nombre": producto_nombre,
                "cantidad_liberada": cantidad_liberada
            }
        )

    except ValueError as e:
        logger.warning(f"Cannot cancel order {order_id}: {str(e)}")
        return HttpResponse.bad_request(error=str(e))

    except Exception as e:
        db.rollback()
        logger.exception(f"Error cancelling order {order_id}")
        return HttpResponse.internal_server_error(error="Error al cancelar la orden")


