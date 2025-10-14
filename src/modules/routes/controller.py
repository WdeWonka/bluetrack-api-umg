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
from db.deps import get_db
from src.utils.http_response import HttpResponse

router = APIRouter(prefix="/routes", tags=["routes"])
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
    Crea una ruta automáticamente con todas las órdenes de una fecha específica.

    **Campos requeridos:**
    - nombre: Nombre descriptivo de la ruta
    - vendedor_id: ID del vendedor asignado
    - almacen_id: ID del almacén de origen
    - fecha: Fecha para buscar órdenes (YYYY-MM-DD)

    **Proceso automático:**
    - Busca todas las órdenes no asignadas de esa fecha
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

    **Incluye:**
    - Datos básicos (nombre, vendedor, almacén, fechas)
    - Lista de clientes a visitar
    - Estado de cada visita
    - Inventario asignado
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
):
    """
    Lista rutas con paginación y filtros opcionales.

    **Filtros disponibles:**
    - vendedor_id: Rutas de un vendedor específico
    - estado: pendiente, en_proceso, completada

    **Ordenamiento:** Por fecha descendente (más recientes primero)
    """
    try:
        skip = (page - 1) * per_page
        routes = route_service.list_routes(
            db,
            skip=skip,
            limit=per_page,

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

        total_routes = route_service.count_routes(
            db
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
                        "almacen_id": r.almacen_id,
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


