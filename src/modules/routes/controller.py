"""
Controlador de rutas - Endpoints principales del sistema de entregas.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from typing import Optional
import logging
from src.utils.http_response import HttpResponse
from fastapi.responses import Response

from src.modules.routes.type import (
    RouteCreate,
    RouteChangeStateRequest,
    EstadoRuta
)
from src.modules.routes import route_service
from src.modules.routes.inventory_service import (
    get_route_inventory_status,
    InsufficientStockError
)

from src.models.orders import Order
from sqlalchemy import or_, cast, Date
from db.deps import get_db
from src.modules.auth.dependencies import require_role
from src.common.constants.roles import ADMIN, OPERATOR, SELLER
from src.utils.http_response import HttpResponse
from src.utils.product_helpers import get_product_display_name_from_order
from src.utils.type_converters import safe_title


router = APIRouter(prefix="/routes", tags=["routes"], dependencies=[Depends(require_role(ADMIN, OPERATOR, SELLER))])
logger = logging.getLogger(__name__)


@router.post(
    "/",
    summary="Crear ruta automática por fecha",
    response_description="Ruta creada exitosamente"
)
def api_create_route(
    route_data: RouteCreate,
    db: Session = Depends(get_db)
):
    """
    Crea una ruta automáticamente con todas las órdenes ACTIVAS de una fecha específica.

    **Campos requeridos:**
    - nombre: Nombre descriptivo de la ruta
    - vendedor_id: ID del vendedor asignado
    - almacen_id: ID del almacén de origen
    - fecha: Fecha para buscar órdenes (YYYY-MM-DD)

    **Proceso automático:**
    - Busca todas las órdenes NO asignadas y NO canceladas de esa fecha
    - Agrupa clientes por orden de visita
    - Calcula inventario total necesario
    - Valida stock disponible en almacén
    """
    try:
        route = route_service.create_route(db, route_data)
        logger.info(f"Route created successfully: {route.id} - {route.nombre}")

        return HttpResponse.created(
            response={
                "id": route.id,
                "nombre": route.nombre,
                "vendedor_id": route.vendedor_id,
                "almacen_id": route.almacen_id,
                "fecha": route.fecha.isoformat(),
                "estado": route.estado,
                "total_clientes": len(route.detalles)
            }
        )

    except ValueError as e:
        logger.warning(f"Validation error creating route: {str(e)}")
        return HttpResponse.bad_request(error=str(e))

    except SQLAlchemyError as se:
        db.rollback()
        logger.error(f"Database error creating route: {str(se)}")
        return HttpResponse.internal_server_error(
            error="Error de base de datos al crear la ruta"
        )

    except Exception as e:
        db.rollback()
        logger.exception(f"Unexpected error creating route: {str(e)}")
        return HttpResponse.internal_server_error(
            error="Ocurrió un error inesperado al crear la ruta"
        )


@router.get(
    "/export/excel",
    summary="📊 Exportar rutas a Excel",
    response_description="Archivo Excel generado"
)
def api_export_routes_excel(db: Session = Depends(get_db)):
    """
    Exporta todas las rutas a formato Excel.

    **Columnas incluidas:**
    - ID
    - Nombre de ruta
    - Vendedor asignado
    - Fecha de ruta
    - Estado (pendiente/en_proceso/completada)
    - Total de clientes
    - Clientes entregados
    - Porcentaje de éxito

    **Uso:** Para análisis en hojas de cálculo y reportes.

    **Respuesta:** Descarga directa del archivo .xlsx
    """
    try:
        excel_bytes = route_service.export_routes_to_excel(db)

        logger.info("Routes exported to Excel successfully")

        return Response(
            content=excel_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": 'attachment; filename="rutas.xlsx"'
            }
        )

    except Exception as e:
        logger.exception(f"Error exporting routes to Excel: {str(e)}")
        return HttpResponse.internal_server_error(
            error="Ocurrió un error al exportar las rutas a Excel"
        )


@router.get(
    "/export/pdf",
    summary="📄 Exportar rutas a PDF",
    response_description="Archivo PDF generado"
)
def api_export_routes_pdf(db: Session = Depends(get_db)):
    """
    Exporta todas las rutas a formato PDF.

    **Información incluida:**
    - Listado completo de rutas
    - Datos del vendedor
    - Fecha y estado
    - Estadísticas de entregas
    - Porcentaje de éxito por ruta

    **Formato:** PDF profesional con tabla formateada

    **Uso:** Para impresión y archivos oficiales.

    **Respuesta:** Descarga directa del archivo .pdf
    """
    try:
        pdf_bytes = route_service.export_routes_to_pdf(db)

        logger.info("Routes exported to PDF successfully")

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": 'attachment; filename="rutas.pdf"'
            }
        )

    except Exception as e:
        logger.exception(f"Error exporting routes to PDF: {str(e)}")
        return HttpResponse.internal_server_error(
            error="Ocurrió un error al exportar las rutas a PDF"
        )


@router.post(
    "/{route_id}/start",
    summary="Iniciar ruta (PENDIENTE → EN_PROCESO)",
    response_description="Ruta iniciada exitosamente"
)
def api_start_route(
    route_id: int,
    db: Session = Depends(get_db)
):
    """
    **Vendedor presiona "Comenzar Ruta"**

    Cambia automáticamente de PENDIENTE → EN_PROCESO.

    **Efectos:**
    - ✅ Reserva stock del almacén
    - ✅ Inicializa inventario de ruta
    - ✅ Registra timestamp de inicio
    - ✅ Bloquea la edición de la ruta

    **Validaciones:**
    - La ruta debe estar en estado PENDIENTE
    - Debe haber stock suficiente en el almacén
    """
    try:
        route = route_service.start_route(db, route_id)

        logger.info(f"Route {route_id} started by vendor")

        return HttpResponse.updated(
            response={
                "id": route.id,
                "nombre": route.nombre,
                "estado": route.estado,
                "inicio_timestamp": route.inicio_timestamp.isoformat() if route.inicio_timestamp else None,
                "mensaje": "Ruta iniciada exitosamente. Stock reservado del almacén."
            }
        )

    except ValueError as e:
        logger.warning(f"Cannot start route {route_id}: {str(e)}")
        return HttpResponse.bad_request(error=str(e))

    except InsufficientStockError as e:
        logger.error(f"Insufficient stock to start route {route_id}")
        return HttpResponse.conflict(
            error=f"Stock insuficiente para iniciar la ruta, productos_faltantes: {e.productos_faltantes}",
        )

    except SQLAlchemyError as se:
        db.rollback()
        logger.error(f"Database error starting route {route_id}: {str(se)}")
        return HttpResponse.internal_server_error(
            error="Error de base de datos al iniciar la ruta"
        )

    except Exception as e:
        db.rollback()
        logger.exception(f"Unexpected error starting route {route_id}: {str(e)}")
        return HttpResponse.internal_server_error(
            error="Ocurrió un error inesperado al iniciar la ruta"
        )


@router.post(
    "/{route_id}/complete",
    summary="Finalizar ruta (EN_PROCESO → COMPLETADA)",
    response_description="Ruta finalizada exitosamente"
)
def api_complete_route(
    route_id: int,
    db: Session = Depends(get_db)
):
    """
    **Vendedor presiona "Finalizar Ruta"**

    Cambia automáticamente de EN_PROCESO → COMPLETADA.

    **Efectos:**
    - ✅ Devuelve stock no entregado al almacén
    - ✅ Libera órdenes de clientes no visitados
    - ✅ Registra timestamp de finalización
    - ✅ Genera reporte de entregas

    **Validaciones:**
    - La ruta debe estar en estado EN_PROCESO

    **Retorna:**
    - Estadísticas de la ruta completada
    - Productos devueltos al almacén
    - Órdenes liberadas
    """
    try:
        result = route_service.complete_route(db, route_id)

        logger.info(
            f"Route {route_id} completed. "
            f"Returned {result['stock_devuelto']['total_unidades']} units, "
            f"Released {result['ordenes_liberadas']} orders"
        )

        return HttpResponse.updated(
            response={
                "id": result['route'].id,
                "nombre": result['route'].nombre,
                "estado": result['route'].estado,
                "fin_timestamp": result['route'].fin_timestamp.isoformat() if result['route'].fin_timestamp else None,
                "resumen": {
                    "clientes_totales": result['estadisticas']['total_clientes'],
                    "clientes_entregados": result['estadisticas']['clientes_entregados'],
                    "clientes_no_entregados": result['estadisticas']['clientes_no_entregados'],
                    "porcentaje_exito": result['estadisticas']['porcentaje_exito']
                },
                "stock_devuelto": result['stock_devuelto'],
                "ordenes_liberadas": result['ordenes_liberadas'],
                "mensaje": "Ruta finalizada exitosamente"
            }
        )

    except ValueError as e:
        logger.warning(f"Cannot complete route {route_id}: {str(e)}")
        return HttpResponse.bad_request(error=str(e))

    except SQLAlchemyError as se:
        db.rollback()
        logger.error(f"Database error completing route {route_id}: {str(se)}")
        return HttpResponse.internal_server_error(
            error="Error de base de datos al finalizar la ruta"
        )

    except Exception as e:
        db.rollback()
        logger.exception(f"Unexpected error completing route {route_id}: {str(e)}")
        return HttpResponse.internal_server_error(
            error="Ocurrió un error inesperado al finalizar la ruta"
        )

@router.get(
    "/{route_id}",
    summary="Obtener ruta por ID",
    response_description="Información de ruta obtenida exitosamente"
)
def api_get_route(
    route_id: int,
    db: Session = Depends(get_db)
):
    """
    Obtiene información completa de una ruta.
    """
    try:
        route = route_service.get_route(db, route_id)

        if not route:
            logger.warning(f"Route not found with ID: {route_id}")
            return HttpResponse.not_found(
                error=f"Ruta con ID {route_id} no existe"
            )

        logger.info(f"Route {route_id} retrieved successfully")
        return HttpResponse.success(
            message="Ruta obtenida exitosamente",
            response={
                "id": route.id,
                "nombre": route.nombre,
                "vendedor_id": route.vendedor_id,
                "almacen_id": route.almacen_id,
                "fecha": route.fecha.isoformat(),
                "estado": route.estado,
                "inicio_timestamp": route.inicio_timestamp.isoformat() if route.inicio_timestamp else None,
                "fin_timestamp": route.fin_timestamp.isoformat() if route.fin_timestamp else None,
                "motivo_cancelacion": route.motivo_cancelacion if hasattr(route, 'motivo_cancelacion') else None,  # 🔥 AGREGAR
                "cancelada_en": route.cancelada_en.isoformat() if hasattr(route, 'cancelada_en') and route.cancelada_en else None,  # 🔥 AGREGAR
                "detalles": [
                    {
                        "id": d.id,
                        "cliente_id": d.cliente_id,
                        "orden": d.orden,
                        "estado_entrega": d.estado_entrega
                    }
                    for d in route.detalles
                ],
                "total_clientes": len(route.detalles)
            }
        )

    except Exception as e:
        logger.exception(f"Error retrieving route {route_id}: {str(e)}")
        return HttpResponse.internal_server_error(
            error="Ocurrió un error al obtener la ruta"
        )

@router.get(
    "/{route_id}/current-cliente",
    summary="Obtener próximo cliente a visitar",
    response_description="Información del siguiente cliente obtenida"
)
def api_get_route_with_current_cliente(
    route_id: int,
    db: Session = Depends(get_db)
):
    """
    Obtiene la ruta con indicador del siguiente cliente a visitar.

    **Útil para app móvil del vendedor:**
    - Identifica el siguiente cliente (puede_entregar=true)
    - Muestra órdenes pendientes por cliente
    - Calcula progreso de entregas
    """
    try:
        route_data = route_service.get_route_with_current_cliente(db, route_id)

        logger.info(f"Current cliente info retrieved for route {route_id}")
        return HttpResponse.success(
            message="Información del siguiente cliente obtenida",
            response=route_data
        )

    except ValueError as e:
        logger.warning(f"Route {route_id} not found")
        return HttpResponse.not_found(error=str(e))

    except Exception as e:
        logger.exception(f"Error getting current cliente for route {route_id}")
        return HttpResponse.internal_server_error(
            error="Ocurrió un error al obtener información del cliente"
        )


@router.get(
    "/{route_id}/inventory",
    summary="Obtener inventario de la ruta",
    response_description="Estado del inventario obtenido"
)
def api_get_route_inventory(
    route_id: int,
    db: Session = Depends(get_db)
):
    """
    Obtiene el estado actual del inventario de una ruta.

    **Incluye por producto:**
    - Cantidad inicial
    - Cantidad actual (después de entregas)
    - Cantidad entregada
    - Porcentaje de avance
    """
    try:
        inventory_status = get_route_inventory_status(db, route_id)

        logger.info(f"Inventory status retrieved for route {route_id}")
        return HttpResponse.success(
            message="Estado del inventario obtenido",
            response=inventory_status
        )

    except Exception as e:
        logger.exception(f"Error getting inventory for route {route_id}")
        return HttpResponse.internal_server_error(
            error="Ocurrió un error al obtener el inventario"
        )

@router.get(
    "/",
    summary="Listar rutas con filtros",
    response_description="Lista de rutas obtenida exitosamente"
)
def api_list_routes(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1, description="Número de página (inicia en 1)"),
    per_page: int = Query(10, ge=1, le=100, description="Elementos por página (max 100)"),
    vendedor_id: Optional[int] = Query(None, description="Filtrar por vendedor"),  # ✅ AGREGAR
    estado: Optional[str] = Query(None, description="Filtrar por estado")  # ✅ AGREGAR
):
    """
    Lista rutas con paginación y filtros opcionales.
    """
    try:
        skip = (page - 1) * per_page

        # ✅ Pasar filtros al servicio
        routes = route_service.list_routes(
            db,
            skip=skip,
            limit=per_page,
            vendedor_id=vendedor_id,  # ✅ CRÍTICO
            estado=estado
        )

        if not routes:
            logger.info("No routes found")
            return HttpResponse.success(
                message="No se encontraron rutas",
                response={
                    "routes": [],
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

        # ✅ Contar con los mismos filtros
        total_routes = route_service.count_routes(
            db,
            vendedor_id=vendedor_id,
            estado=estado
        )
        total_pages = (total_routes + per_page - 1) // per_page

        logger.info(f"Retrieved {len(routes)} routes for page {page}")
        return HttpResponse.success(
            message=f"Se obtuvieron {len(routes)} rutas exitosamente",
            response={
                "routes": [
                    {
                        "id": r.id,
                        "nombre": r.nombre,
                        "vendedor_id": r.vendedor_id,
                        "vendedor_nombre": safe_title(r.vendedor.nombre),
                        "almacen_id": r.almacen_id,
                        "almacen_nombre": safe_title(r.almacen.nombre) if r.almacen else "Sin almacén",
                        "fecha": r.fecha.isoformat(),
                        "estado": r.estado,
                        "total_clientes": len(r.detalles)
                    }
                    for r in routes
                ],
                "pagination": {
                    "page": page,
                    "per_page": per_page,
                    "total_items": total_routes,
                    "total_pages": total_pages,
                    "has_next": page < total_pages,
                    "has_prev": page > 1
                }
            }
        )

    except SQLAlchemyError as se:
        logger.error(f"Database error listing routes: {str(se)}")
        return HttpResponse.internal_server_error(
            error="Error de base de datos al listar rutas"
        )

    except Exception as e:
        logger.exception(f"Unexpected error listing routes: {str(e)}")
        return HttpResponse.internal_server_error(
            error="Ocurrió un error inesperado al listar rutas"
        )


@router.post(
    "/{route_id}/cancel",
    summary="🚫 Cancelar ruta",
    response_description="Ruta cancelada exitosamente"
)
def api_cancel_route(
    route_id: int,
    motivo: str = Query(..., min_length=5, description="Motivo de cancelación (mínimo 5 caracteres)"),
    db: Session = Depends(get_db)
):
    """
    Cancela una ruta en estado PENDIENTE.

    **Solo para rutas pendientes** (no iniciadas)

    **Acciones automáticas:**
    - ✅ Devuelve todo el stock al almacén
    - ✅ Libera las órdenes asignadas (quedan disponibles para otra ruta)
    - ✅ Marca la ruta como CANCELADA
    - ✅ Registra motivo y timestamp de cancelación

    **Parámetros:**
    - route_id: ID de la ruta a cancelar
    - motivo: Razón de la cancelación (obligatorio, mínimo 5 caracteres)

    **Ejemplos de motivos:**
    - "Vendedor enfermo"
    - "Condiciones climáticas adversas"
    - "Vehículo averiado"
    - "Ruta reprogramada para otra fecha"

    **Validaciones:**
    - La ruta debe existir
    - La ruta debe estar en estado PENDIENTE
    - El motivo es obligatorio y debe tener al menos 5 caracteres
    """
    try:
        result = route_service.cancel_route(db, route_id, motivo)

        logger.info(f"Route {route_id} cancelled successfully")

        return HttpResponse.success(
            message="Ruta cancelada exitosamente",
            response={
                "id": result['route'].id,
                "nombre": result['route'].nombre,
                "estado": result['route'].estado,
                "motivo_cancelacion": result['motivo'],
                "cancelada_en": result['cancelada_en'],
                "stock_devuelto": result['stock_devuelto'],
                "ordenes_liberadas": result['ordenes_liberadas']
            }
        )

    except ValueError as e:
        logger.warning(f"Cannot cancel route {route_id}: {str(e)}")
        return HttpResponse.bad_request(error=str(e))

    except SQLAlchemyError as se:
        db.rollback()
        logger.error(f"Database error cancelling route {route_id}: {str(se)}")
        return HttpResponse.internal_server_error(
            error="Error de base de datos al cancelar la ruta"
        )

    except Exception as e:
        db.rollback()
        logger.exception(f"Unexpected error cancelling route {route_id}: {str(e)}")
        return HttpResponse.internal_server_error(
            error="Ocurrió un error inesperado al cancelar la ruta"
        )


# ============================================
# ENDPOINTS PARA CREAR RUTAS (MODAL)
# ============================================

@router.get(
    "/search/sellers",
    summary="🔍 Buscar vendedores para crear ruta",
    response_description="Lista de vendedores encontrados",
    dependencies=[Depends(require_role(ADMIN, OPERATOR))]
)
def api_search_sellers(
    db: Session = Depends(get_db),
    query: str = Query("", description="Búsqueda por nombre o email"),
    limit: int = Query(10, ge=1, le=50, description="Máximo de resultados")
):
    """
    Busca vendedores activos por nombre o email.

    **Uso:** Autocomplete en modal de crear ruta

    **Parámetros:**
    - query: Término de búsqueda (vacío = todos los vendedores)
    - limit: Máximo de resultados (default: 10)

    **Retorna:**
    - Lista de vendedores con: id, nombre, email
    """
    from src.models.user import User
    from src.common.constants.roles import SELLER
    from sqlalchemy import or_

    try:
        # Construir query base (vendedores activos)
        db_query = db.query(User).filter(
            User.rol == SELLER.lower(),
            User.activo == True
        )

        # Si hay búsqueda, filtrar
        if query:
            search_pattern = f"%{query}%"
            db_query = db_query.filter(
                or_(
                    User.nombre.ilike(search_pattern),
                    User.email.ilike(search_pattern)
                )
            )

        # Ordenar y limitar
        sellers = db_query.order_by(User.nombre).limit(limit).all()

        logger.info(f"Found {len(sellers)} sellers for query: '{query}'")
        return HttpResponse.success(
            message=f"Se encontraron {len(sellers)} vendedores",
            response=[
                {
                    "id": s.id,
                    "nombre": safe_title(s.nombre),
                    "email": s.email
                }
                for s in sellers
            ]
        )

    except SQLAlchemyError as se:
        logger.error(f"Database error searching sellers: {str(se)}")
        return HttpResponse.internal_server_error(
            error="Error de base de datos al buscar vendedores"
        )

    except Exception as e:
        logger.exception(f"Unexpected error searching sellers: {str(e)}")
        return HttpResponse.internal_server_error(
            error="Ocurrió un error inesperado al buscar vendedores"
        )


@router.get(
    "/search/warehouses",
    summary="🔍 Buscar almacenes para crear ruta",
    response_description="Lista de almacenes encontrados",
    dependencies=[Depends(require_role(ADMIN, OPERATOR))]
)
def api_search_warehouses(
    db: Session = Depends(get_db),
    query: str = Query("", description="Búsqueda por nombre"),
    limit: int = Query(10, ge=1, le=50, description="Máximo de resultados")
):
    """
    Busca almacenes por nombre.

    **Uso:** Autocomplete en modal de crear ruta

    **Parámetros:**
    - query: Término de búsqueda (vacío = todos los almacenes)
    - limit: Máximo de resultados (default: 10)

    **Retorna:**
    - Lista de almacenes con: id, nombre, direccion
    """
    from src.models.warehouse import Warehouse

    try:
        # Construir query base
        db_query = db.query(Warehouse)

        # Si hay búsqueda, filtrar
        if query:
            search_pattern = f"%{query}%"
            db_query = db_query.filter(
                Warehouse.nombre.ilike(search_pattern)
            )

        # Ordenar y limitar
        warehouses = db_query.order_by(Warehouse.nombre).limit(limit).all()

        logger.info(f"Found {len(warehouses)} warehouses for query: '{query}'")
        return HttpResponse.success(
            message=f"Se encontraron {len(warehouses)} almacenes",
            response=[
                {
                    "id": w.id,
                    "nombre": safe_title(w.nombre),
                    "direccion": safe_title(w.direccion) if w.direccion else None
                }
                for w in warehouses
            ]
        )

    except SQLAlchemyError as se:
        logger.error(f"Database error searching warehouses: {str(se)}")
        return HttpResponse.internal_server_error(
            error="Error de base de datos al buscar almacenes"
        )

    except Exception as e:
        logger.exception(f"Unexpected error searching warehouses: {str(e)}")
        return HttpResponse.internal_server_error(
            error="Ocurrió un error inesperado al buscar almacenes"
        )


@router.get(
    "/orders/by-date",
    summary="📦 Obtener órdenes disponibles por fecha",
    response_description="Lista de órdenes no asignadas y activas",
    dependencies=[Depends(require_role(ADMIN, OPERATOR))]
)
def api_get_orders_by_date(
    db: Session = Depends(get_db),
    fecha: str = Query(..., description="Fecha en formato YYYY-MM-DD")
):
    """
    Obtiene todas las órdenes ACTIVAS y NO asignadas de una fecha específica.

    **Uso:** Preview de órdenes en modal de crear ruta

    **Parámetros:**
    - fecha: Fecha a consultar (YYYY-MM-DD)

    **Retorna:**
    - Lista de órdenes con: id, cliente_nombre, producto_nombre,
      cantidad, precio_unitario, subtotal
    - Agrupadas para vista previa antes de crear la ruta

    **Validaciones:**
    - Solo órdenes con asignada = False
    - Solo órdenes con cancelada = False (🔥 NO muestra canceladas)
    - Solo de la fecha especificada
    """
    from datetime import datetime
    from sqlalchemy import cast, Date

    try:
        # Validar formato de fecha
        try:
            fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date()
        except ValueError:
            return HttpResponse.bad_request(
                error="Formato de fecha inválido. Use YYYY-MM-DD"
            )

        # Buscar órdenes NO asignadas y NO canceladas de esa fecha
        ordenes = (
            db.query(Order)
            .filter(
                cast(Order.fecha_solicitud, Date) == fecha_obj,
                Order.asignada == False,
                Order.cancelada == False  # 🔥 Excluir canceladas
            )
            .all()
        )

        if not ordenes:
            logger.info(f"No unassigned active orders found for date: {fecha}")
            return HttpResponse.success(
                message=f"No hay órdenes activas pendientes para la fecha {fecha}",
                response=[]
            )

        # Formatear respuesta
        orders_response = []
        for orden in ordenes:
            orders_response.append({
                "id": orden.id,
                "cliente_nombre": safe_title(orden.cliente.nombre) if orden.cliente else "Desconocido",
                "producto_nombre": get_product_display_name_from_order(orden),
                "cantidad": orden.cantidad,
                "precio_unitario": float(orden.producto.precio),
                "subtotal": float(orden.cantidad * orden.producto.precio)
            })

        logger.info(f"Found {len(ordenes)} unassigned active orders for {fecha}")
        return HttpResponse.success(
            message=f"Se encontraron {len(ordenes)} órdenes activas para {fecha}",
            response=orders_response
        )

    except SQLAlchemyError as se:
        logger.error(f"Database error getting orders by date: {str(se)}")
        return HttpResponse.internal_server_error(
            error="Error de base de datos al obtener órdenes"
        )

    except Exception as e:
        logger.exception(f"Unexpected error getting orders by date: {str(e)}")
        return HttpResponse.internal_server_error(
            error="Ocurrió un error inesperado al obtener órdenes"
        )


# Agregar al final de route_controller.py

@router.post(
    "/{route_id}/optimize-order",
    summary="🗺️ Optimizar orden de visitas por cercanía",
    response_description="Orden optimizado generado"
)
def api_optimize_route_order(
    route_id: int,
    db: Session = Depends(get_db)
):
    """
    **Optimiza el orden de visitas usando el algoritmo del vecino más cercano**

    Calcula la ruta óptima comenzando desde el almacén y visitando
    siempre el cliente más cercano no visitado.

    **Requisitos:**
    - El almacén debe tener latitud y longitud configuradas
    - Todos los clientes deben tener latitud y longitud

    **Retorna:**
    - Nuevo orden de visitas
    - Distancia total de la ruta
    - Distancia entre cada segmento
    """
    from src.modules.routes import route_optimization_service

    try:
        result = route_optimization_service.optimize_route_order_by_proximity(
            db,
            route_id
        )

        logger.info(f"Route {route_id} order optimized: {result['distancia_total_km']} km")

        return HttpResponse.success(
            message="Orden de visitas optimizado exitosamente",
            response=result
        )

    except ValueError as e:
        logger.warning(f"Cannot optimize route {route_id}: {str(e)}")
        return HttpResponse.bad_request(error=str(e))

    except Exception as e:
        logger.exception(f"Error optimizing route {route_id}")
        return HttpResponse.internal_server_error(
            error="Error al optimizar el orden de visitas"
        )


@router.get(
    "/{route_id}/next-client",
    summary="Obtener siguiente cliente a visitar",
    response_description="Cliente obtenido exitosamente"
)
def api_get_next_client(
    route_id: int,
    db: Session = Depends(get_db)
):
    """
    **Obtiene el siguiente cliente pendiente de visita**

    Retorna el cliente con el orden más bajo que aún no ha sido visitado.

    **Incluye:**
    - Datos del cliente (nombre, dirección, teléfono, coordenadas)
    - Lista de productos a entregar
    - Orden de visita
    """
    from src.modules.routes import route_optimization_service

    try:
        next_client = route_optimization_service.get_next_client_to_visit(
            db,
            route_id
        )

        if not next_client:
            return HttpResponse.success(
                message="No hay más clientes pendientes",
                response={"completado": True}
            )

        logger.info(f"Next client for route {route_id}: {next_client['nombre']}")

        return HttpResponse.success(
            message="Cliente obtenido exitosamente",
            response=next_client
        )

    except Exception as e:
        logger.exception(f"Error getting next client for route {route_id}")
        return HttpResponse.internal_server_error(
            error="Error al obtener el siguiente cliente"
        )
