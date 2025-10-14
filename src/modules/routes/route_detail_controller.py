"""
Controlador de detalles de ruta - ENDPOINTS SIMPLIFICADOS.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from pydantic import BaseModel
import logging

from src.modules.routes.type import RouteDetailUpdateStatus
from src.modules.routes import route_detail_service
from db.deps import get_db
from src.utils.http_response import HttpResponse

router = APIRouter(prefix="/routes", tags=["route-details"])
logger = logging.getLogger(__name__)


# 🔥 NUEVO: Schema para no entrega
class NotDeliveredRequest(BaseModel):
    motivo: str

    class Config:
        json_schema_extra = {
            "example": {
                "motivo": "Cliente cerrado"
            }
        }


# 🔥 NUEVO: Endpoint simplificado para entrega completa
@router.post(
    "/{route_id}/details/{detail_id}/deliver-all",
    summary="✅ Entregar todas las órdenes (simplificado)",
    response_description="Entrega completa registrada"
)
def api_deliver_all_orders(
    route_id: int,
    detail_id: int,
    db: Session = Depends(get_db)
):
    """
    🚀 **ENDPOINT SIMPLIFICADO PARA APP MÓVIL**

    Entrega automáticamente TODAS las órdenes del cliente.

    **El vendedor solo necesita:**
    1. Presionar botón "Entregar"
    2. El sistema registra todo automáticamente

    **Qué hace:**
    - Busca todas las órdenes del cliente
    - Calcula cantidades pendientes
    - Registra entregas completas
    - Actualiza inventario de ruta
    - Marca cliente como "entregado"

    **No requiere body en la petición** ✨
    """
    from src.models.route_detail import RouteDetail

    try:
        # Validar que el detalle pertenece a la ruta
        detalle = db.query(RouteDetail).filter(
            RouteDetail.id == detail_id,
            RouteDetail.ruta_id == route_id
        ).first()

        if not detalle:
            return HttpResponse.not_found(
                error=f"Detalle {detail_id} no encontrado en ruta {route_id}"
            )

        # Entregar automáticamente
        result = route_detail_service.deliver_all_orders_automatically(
            db,
            detail_id
        )

        logger.info(
            f"All orders delivered for route {route_id}, detail {detail_id}"
        )

        return HttpResponse.success(
            message="Entrega completa registrada exitosamente",
            response=result
        )

    except ValueError as e:
        logger.warning(f"Validation error in auto-delivery: {str(e)}")
        return HttpResponse.bad_request(error=str(e))

    except SQLAlchemyError as se:
        db.rollback()
        logger.error(f"Database error in auto-delivery: {str(se)}")
        return HttpResponse.internal_server_error(
            error="Error de base de datos al registrar entrega"
        )

    except Exception as e:
        db.rollback()
        logger.exception(f"Error in auto-delivery: {str(e)}")
        return HttpResponse.internal_server_error(
            error="Ocurrió un error inesperado al registrar la entrega"
        )


# 🔥 NUEVO: Endpoint simplificado para no entrega
@router.post(
    "/{route_id}/details/{detail_id}/mark-not-delivered",
    summary="❌ Marcar como NO entregado (simplificado)",
    response_description="Cliente marcado como no entregado"
)
def api_mark_not_delivered(
    route_id: int,
    detail_id: int,
    request: NotDeliveredRequest,
    db: Session = Depends(get_db)
):
    """
    🚀 **ENDPOINT SIMPLIFICADO PARA APP MÓVIL**

    Marca cliente como NO entregado con un motivo.

    **Casos de uso:**
    - Cliente cerrado
    - Dirección incorrecta
    - Cliente no disponible
    - Rechazó el pedido

    **Requiere solo el motivo:**
    ```json
    {
      "motivo": "Cliente cerrado"
    }
    ```
    """
    from src.models.route_detail import RouteDetail

    try:
        # Validar que el detalle pertenece a la ruta
        detalle = db.query(RouteDetail).filter(
            RouteDetail.id == detail_id,
            RouteDetail.ruta_id == route_id
        ).first()

        if not detalle:
            return HttpResponse.not_found(
                error=f"Detalle {detail_id} no encontrado en ruta {route_id}"
            )

        # Marcar como no entregado
        updated_detail = route_detail_service.mark_as_not_delivered(
            db,
            detail_id,
            request.motivo
        )

        logger.info(
            f"Detail {detail_id} marked as not delivered: {request.motivo}"
        )

        return HttpResponse.success(
            message="Cliente marcado como no entregado",
            response={
                "detalle_id": updated_detail.id,
                "cliente_id": updated_detail.cliente_id,
                "estado_entrega": updated_detail.estado_entrega,
                "motivo": updated_detail.motivo,
                "timestamp_entrega": (t.isoformat() if (t := detalle.timestamp_entrega) else None),
            }
        )

    except ValueError as e:
        logger.warning(f"Validation error: {str(e)}")
        return HttpResponse.bad_request(error=str(e))

    except SQLAlchemyError as se:
        db.rollback()
        logger.error(f"Database error: {str(se)}")
        return HttpResponse.internal_server_error(
            error="Error de base de datos"
        )

    except Exception as e:
        db.rollback()
        logger.exception(f"Error marking not delivered: {str(e)}")
        return HttpResponse.internal_server_error(
            error="Ocurrió un error inesperado"
        )


# ========== ENDPOINTS ORIGINALES (mantener para flexibilidad) ==========

@router.post(
    "/{route_id}/details/{detail_id}/deliver",
    summary="Registrar entrega (avanzado)",
    response_description="Entrega registrada exitosamente"
)
def api_update_delivery_status(
    route_id: int,
    detail_id: int,
    status_data: RouteDetailUpdateStatus,
    db: Session = Depends(get_db)
):
    """
    ⚙️ **ENDPOINT AVANZADO** (para entregas parciales o personalizadas)

    Usa este endpoint cuando necesites:
    - Entregar solo algunos productos
    - Entregas parciales
    - Control granular sobre cantidades

    Para entregas completas simples, usa `/deliver-all` en su lugar.
    """
    from src.models.route_detail import RouteDetail

    try:
        detalle = db.query(RouteDetail).filter(
            RouteDetail.id == detail_id,
            RouteDetail.ruta_id == route_id
        ).first()

        if not detalle:
            return HttpResponse.not_found(
                error=f"Detalle {detail_id} no encontrado en ruta {route_id}"
            )

        updated_detail = route_detail_service.update_delivery_status(
            db,
            detail_id,
            status_data
        )

        logger.info(
            f"Delivery updated for route {route_id}, detail {detail_id}"
        )

        return HttpResponse.updated(
            response={
                "detalle_id": updated_detail.id,
                "ruta_id": updated_detail.ruta_id,
                "cliente_id": updated_detail.cliente_id,
                "estado_entrega": updated_detail.estado_entrega,
                "motivo": updated_detail.motivo,
                "timestamp_entrega": updated_detail.timestamp_entrega.isoformat() if updated_detail.timestamp_entrega else None,
                "entregas_registradas": len(status_data.entregas) if status_data.entregas else 0
            }
        )

    except ValueError as e:
        logger.warning(f"Validation error: {str(e)}")
        return HttpResponse.bad_request(error=str(e))

    except SQLAlchemyError as se:
        db.rollback()
        logger.error(f"Database error: {str(se)}")
        return HttpResponse.internal_server_error(
            error="Error de base de datos"
        )

    except Exception as e:
        db.rollback()
        logger.exception(f"Error updating delivery: {str(e)}")
        return HttpResponse.internal_server_error(
            error="Ocurrió un error inesperado"
        )


@router.get(
    "/{route_id}/details/{detail_id}",
    summary="Obtener detalle de visita con órdenes",
    response_description="Detalle de visita obtenido exitosamente"
)
def api_get_route_detail_with_orders(
    route_id: int,
    detail_id: int,
    db: Session = Depends(get_db)
):
    """
    Obtiene información completa de una visita a cliente.

    **Incluye:**
    - Datos del cliente
    - Estado de entrega
    - Órdenes (con cantidades ordenadas, entregadas y pendientes)
    - Entregas realizadas
    """
    from src.models.route_detail import RouteDetail

    try:
        detalle = db.query(RouteDetail).filter(
            RouteDetail.id == detail_id,
            RouteDetail.ruta_id == route_id
        ).first()

        if not detalle:
            return HttpResponse.not_found(
                error=f"Detalle {detail_id} no encontrado en ruta {route_id}"
            )

        detail_data = route_detail_service.get_route_detail_with_orders(
            db,
            detail_id
        )

        logger.info(f"Route detail {detail_id} retrieved successfully")
        return HttpResponse.success(
            message="Detalle de visita obtenido exitosamente",
            response=detail_data
        )

    except ValueError as e:
        logger.warning(f"Detail not found: {str(e)}")
        return HttpResponse.not_found(error=str(e))

    except Exception as e:
        logger.exception(f"Error getting route detail {detail_id}")
        return HttpResponse.internal_server_error(
            error="Ocurrió un error al obtener el detalle de ruta"
        )


@router.get(
    "/{route_id}/progress",
    summary="Obtener progreso de entregas CON PRECIOS",
    response_description="Progreso de ruta obtenido exitosamente"
)
def api_get_route_progress(
    route_id: int,
    db: Session = Depends(get_db)
):
    """
    🔥 MEJORADO: Obtiene progreso de ruta con información financiera.

    **Incluye:**
    - Progreso de visitas (visitados, pendientes)
    - **Subtotal esperado por cliente**
    - **Subtotal entregado por cliente**
    - **Total esperado de la ruta**
    - **Total entregado de la ruta**
    - **Pérdida estimada**

    **Uso:** Para monitoreo en tiempo real durante la ruta.
    """
    from src.modules.routes import route_financial_service

    try:
        progress_data = route_financial_service.get_route_progress_with_prices(
            db,
            route_id
        )

        logger.info(f"Route {route_id} progress retrieved with financial data")
        return HttpResponse.success(
            message="Progreso de ruta obtenido exitosamente",
            response=progress_data
        )

    except ValueError as e:
        logger.warning(f"Route not found: {str(e)}")
        return HttpResponse.not_found(error=str(e))

    except Exception as e:
        logger.exception(f"Error getting route {route_id} progress")
        return HttpResponse.internal_server_error(
            error="Ocurrió un error al obtener el progreso de la ruta"
        )


@router.get(
    "/{route_id}/summary",
    summary="📊 Resumen financiero completo de ruta",
    response_description="Resumen financiero obtenido exitosamente"
)
def api_get_route_financial_summary(
    route_id: int,
    db: Session = Depends(get_db)
):
    """
    🔥 NUEVO: Resumen financiero completo para rutas COMPLETADAS.

    **Incluye:**

    📊 **Resumen Financiero:**
    - Total esperado (todas las órdenes)
    - Total entregado (lo que realmente se cobró)
    - Pérdida por no entregas
    - Porcentaje de efectividad en cobros

    📦 **Resumen de Inventario:**
    - Unidades cargadas vs entregadas
    - Productos devueltos
    - Porcentaje de venta por producto

    👥 **Resumen de Clientes:**
    - Total de clientes
    - Tasa de conversión (entregados/total)
    - Detalle por cliente con subtotales

    **Ejemplo de respuesta:**
    ```json
    {
      "resumen_financiero": {
        "total_esperado": 1000.00,
        "total_entregado": 900.00,
        "perdida": 100.00,
        "porcentaje_cobrado": 90.0
      },
      "resumen_inventario": {
        "total_unidades_cargadas": 10,
        "total_unidades_entregadas": 9,
        "total_unidades_devueltas": 1,
        "porcentaje_vendido": 90.0
      }
    }
    ```

    **Uso:** Para reportes de admin después de completar la ruta.
    """
    from src.modules.routes import route_financial_service

    try:
        summary_data = route_financial_service.get_route_financial_summary(
            db,
            route_id
        )

        logger.info(f"Financial summary generated for route {route_id}")
        return HttpResponse.success(
            message="Resumen financiero obtenido exitosamente",
            response=summary_data
        )

    except ValueError as e:
        logger.warning(f"Route not found: {str(e)}")
        return HttpResponse.not_found(error=str(e))

    except Exception as e:
        logger.exception(f"Error generating summary for route {route_id}")
        return HttpResponse.internal_server_error(
            error="Ocurrió un error al generar el resumen financiero"
        )


@router.get(
    "/{route_id}/summary/pdf",
    summary="📄 Exportar resumen financiero a PDF",
    response_description="PDF generado exitosamente"
)
def api_export_route_summary_pdf(
    route_id: int,
    db: Session = Depends(get_db)
):
    """
    🔥 NUEVO: Exporta el resumen financiero completo a PDF.

    **Incluye en el PDF:**
    - Cajas de resumen con métricas clave
    - Resumen financiero (esperado vs entregado)
    - Resumen de inventario (cargado vs entregado)
    - Resumen de clientes (conversión)
    - Tabla detallada por cliente
    - Tabla de inventario de productos

    **Formato:** PDF profesional con múltiples secciones

    **Uso:** Para reportes de administración y archivos.

    **Respuesta:** Descarga directa del archivo PDF
    """
    from fastapi.responses import Response
    from src.modules.routes import route_financial_service

    try:
        # Generar PDF
        pdf_bytes = route_financial_service.export_route_summary_to_pdf(
            db,
            route_id
        )

        # Obtener nombre de ruta para el archivo
        from src.models.route import Route
        route = db.query(Route).filter(Route.id == route_id).first()

        filename = f"resumen_ruta_{route.nombre.replace(' ', '_')}_{route.fecha}.pdf" if route else f"resumen_ruta_{route_id}.pdf"

        logger.info(f"PDF exported for route {route_id}")

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )

    except ValueError as e:
        logger.warning(f"Route not found: {str(e)}")
        return HttpResponse.not_found(error=str(e))

    except Exception as e:
        logger.exception(f"Error exporting PDF for route {route_id}")
        return HttpResponse.internal_server_error(
            error="Ocurrió un error al exportar el PDF"
        )

