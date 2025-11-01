"""
Servicio de rutas (CORREGIDO FINAL).
"""
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, cast, Date
from datetime import datetime, date
from typing import List, Optional, Dict, Any
import logging
from reportlab.lib.pagesizes import letter

from src.models.route import Route
from src.models.route_detail import RouteDetail
from src.models.route_inventory import RouteInventory
from src.models.orders import Order
from src.models.customer import Customer
from src.modules.routes.type import RouteCreate, EstadoRuta
from src.utils.product_helpers import get_product_display_name_from_order

from src.modules.routes.inventory_service import (
    reserve_stock_for_route,
    return_remaining_stock_to_warehouse,
    InsufficientStockError
)

logger = logging.getLogger(__name__)


def create_route(db: Session, route_data: RouteCreate) -> Route:
    """
    Crea una ruta automáticamente con TODAS las órdenes de una fecha específica.
    🔥 NUEVO: Descuenta stock AL CREAR (no al iniciar).
    """
    from src.models.user import User

    # 1. Validar vendedor
    vendedor = db.query(User).filter(User.id == route_data.vendedor_id).first()
    if not vendedor:
        raise ValueError(f"Usuario {route_data.vendedor_id} no existe")

    if vendedor.rol != 'vendedor':
        raise ValueError(
            f"El usuario {vendedor.nombre} no tiene rol de vendedor. "
            f"Rol actual: {vendedor.rol}"
        )

    if not vendedor.activo:
        raise ValueError(f"El vendedor {vendedor.nombre} está inactivo")

    # 2. Buscar órdenes
    ordenes = (
        db.query(Order)
        .filter(
            cast(Order.fecha_solicitud, Date) == route_data.fecha,
            Order.asignada == False
        )
        .all()
    )

    if not ordenes:
        raise ValueError(
            f"No hay órdenes pendientes para la fecha {route_data.fecha}"
        )

    if route_data.fecha < date.today():
        raise ValueError(
            f"No se pueden crear rutas para fechas pasadas: {route_data.fecha}"
        )

    # 3. Agrupar por cliente
    ordenes_por_cliente = {}
    for orden in ordenes:
        if orden.cliente_id not in ordenes_por_cliente:
            ordenes_por_cliente[orden.cliente_id] = []
        ordenes_por_cliente[orden.cliente_id].append(orden)

    # 4. Crear ruta
    route = Route(
        nombre=route_data.nombre,
        vendedor_id=route_data.vendedor_id,
        almacen_id=route_data.almacen_id,
        fecha=route_data.fecha,
        estado=EstadoRuta.PENDIENTE
    )
    db.add(route)
    db.flush()

    # 5. Crear detalles
    orden_visita = 1
    for cliente_id, ordenes_cliente in ordenes_por_cliente.items():
        detalle = RouteDetail(
            ruta_id=route.id,
            cliente_id=cliente_id,
            orden=orden_visita,
            estado_entrega='no_entregado'
        )
        db.add(detalle)
        orden_visita += 1

        for orden in ordenes_cliente:
            orden.asignada = True
            orden.ruta_id = route.id

    # 6. Calcular inventario total
    inventario_dict = {}
    for orden in ordenes:
        producto_id = orden.producto_id
        cantidad = orden.cantidad
        inventario_dict[producto_id] = inventario_dict.get(producto_id, 0) + cantidad

    # 7. 🔥 RESERVAR STOCK INMEDIATAMENTE (descuenta y crea RouteInventory)
    try:
        reserve_stock_for_route(db, route.id, route.almacen_id, inventario_dict)
    except InsufficientStockError as e:
        db.rollback()
        raise ValueError(f"Stock insuficiente: {e.productos_faltantes}")

    db.commit()
    db.refresh(route)

    logger.info(
        f"Route created: {route.nombre} with "
        f"{len(ordenes_por_cliente)} clients and {len(ordenes)} orders. "
        f"Stock reserved."
    )
    return route


def start_route(db: Session, route_id: int) -> Route:
    """
    Inicia una ruta (PENDIENTE → EN_PROCESO).
    🔥 YA NO DESCUENTA STOCK (ya se hizo en create_route).
    """
    route = db.query(Route).filter(Route.id == route_id).first()

    if not route:
        raise ValueError(f"Ruta {route_id} no existe")

    if route.estado != 'pendiente':
        raise ValueError(
            f"Solo se pueden iniciar rutas en estado PENDIENTE. "
            f"Estado actual: {route.estado}"
        )

    # 🔥 Solo cambia el estado (el stock YA fue descontado)
    route.estado = 'en_proceso'
    route.inicio_timestamp = datetime.now()

    db.commit()
    db.refresh(route)

    logger.info(f"Route {route_id} started")
    return route


def complete_route(db: Session, route_id: int) -> Dict[str, Any]:
    """
    Finaliza una ruta (EN_PROCESO → COMPLETADA).
    """
    route = db.query(Route).filter(Route.id == route_id).first()

    if not route:
        raise ValueError(f"Ruta {route_id} no existe")

    if route.estado != 'en_proceso':
        raise ValueError(
            f"Solo se pueden finalizar rutas en estado EN_PROCESO. "
            f"Estado actual: {route.estado}"
        )

    # 1. Devolver stock sobrante
    devolucion_info = return_remaining_stock_to_warehouse(
        db, route.id, route.almacen_id
    )

    # 2. Liberar órdenes NO visitadas
    detalles_no_visitados = (
        db.query(RouteDetail)
        .filter(
            RouteDetail.ruta_id == route.id,
            RouteDetail.estado_entrega == 'no_entregado',
            RouteDetail.motivo.is_(None)
        )
        .all()
    )

    ordenes_liberadas = 0
    for detalle in detalles_no_visitados:
        ordenes = (
            db.query(Order)
            .filter(
                Order.ruta_id == route.id,
                Order.cliente_id == detalle.cliente_id
            )
            .all()
        )

        for orden in ordenes:
            orden.asignada = False
            orden.ruta_id = None
            ordenes_liberadas += 1

    # 3. Estadísticas
    total_detalles = len(route.detalles)
    detalles_entregados = sum(
        1 for d in route.detalles
        if d.estado_entrega == 'entregado'
    )
    detalles_no_entregados = sum(
        1 for d in route.detalles
        if d.estado_entrega == 'no_entregado' and d.motivo is not None
    )

    porcentaje_exito = (
        (detalles_entregados / total_detalles * 100)
        if total_detalles > 0 else 0
    )

    # 4. Actualizar estado
    route.estado = 'completada'
    route.fin_timestamp = datetime.now()

    db.commit()
    db.refresh(route)

    logger.info(
        f"Route {route_id} completed. "
        f"Delivered: {detalles_entregados}/{total_detalles} clients. "
        f"Returned: {devolucion_info['total_unidades_devueltas']} units. "
        f"Released: {ordenes_liberadas} orders."
    )

    return {
        "route": route,
        "estadisticas": {
            "total_clientes": total_detalles,
            "clientes_entregados": detalles_entregados,
            "clientes_no_entregados": detalles_no_entregados,
            "clientes_no_visitados": len(detalles_no_visitados),
            "porcentaje_exito": round(porcentaje_exito, 2)
        },
        "stock_devuelto": {
            "total_productos": devolucion_info['total_productos_devueltos'],
            "total_unidades": devolucion_info['total_unidades_devueltas'],
            "detalle": devolucion_info['detalle']
        },
        "ordenes_liberadas": ordenes_liberadas
    }


def change_route_state(db: Session, route_id: int, nuevo_estado: EstadoRuta) -> Route:
    """[LEGACY] Función original mantenida por compatibilidad."""
    if nuevo_estado == EstadoRuta.EN_PROCESO:
        return start_route(db, route_id)
    elif nuevo_estado == EstadoRuta.COMPLETADA:
        result = complete_route(db, route_id)
        return result['route']
    else:
        raise ValueError(f"Estado {nuevo_estado} no soportado")


def get_route(db: Session, route_id: int) -> Optional[Route]:
    """Obtiene una ruta con todas sus relaciones."""
    return (
        db.query(Route)
        .options(
            joinedload(Route.detalles).joinedload(RouteDetail.entregas),
            joinedload(Route.inventario)
        )
        .filter(Route.id == route_id)
        .first()
    )


def get_route_with_current_cliente(db: Session, route_id: int) -> dict:
    """Obtiene ruta con el cliente activo (siguiente a visitar)."""
    route = get_route(db, route_id)
    if not route:
        raise ValueError(f"Route {route_id} not found")

    cliente_actual = None
    siguiente_orden = None

    for detalle in sorted(route.detalles, key=lambda d: d.orden):
        if detalle.estado_entrega == "no_entregado" and detalle.motivo is None:
            siguiente_orden = detalle.orden
            cliente_actual = detalle
            break

    if not cliente_actual:
        return {
            "ruta_id": route.id,
            "ruta_nombre": route.nombre,
            "estado_ruta": route.estado,
            "completado": True,
            "mensaje": "Todos los clientes han sido visitados",
            "progreso": {
                "total_clientes": len(route.detalles),
                "visitados": len([d for d in route.detalles
                                 if d.estado_entrega == "entregado" or d.motivo is not None]),
                "pendientes": 0
            }
        }

    ordenes = (
        db.query(Order)
        .filter(
            Order.ruta_id == route_id,
            Order.cliente_id == cliente_actual.cliente_id
        )
        .all()
    )

    precio_total = sum(o.cantidad * o.producto.precio for o in ordenes)

    productos_detalle = []
    for orden in ordenes:
        productos_detalle.append({
            "orden_id": orden.id,
            "producto_id": orden.producto_id,
            "producto_nombre": get_product_display_name_from_order(orden),
            "cantidad": orden.cantidad,
            "precio_unitario": float(orden.producto.precio),
            "subtotal": float(orden.cantidad * orden.producto.precio),
            "prioridad": orden.prioridad
        })

    total_clientes = len(route.detalles)
    visitados = sum(1 for d in route.detalles
                   if d.estado_entrega == "entregado" or d.motivo is not None)

    return {
        "ruta_id": route.id,
        "ruta_nombre": route.nombre,
        "estado_ruta": route.estado,
        "completado": False,
        "cliente_actual": {
            "detalle_id": cliente_actual.id,
            "cliente_id": cliente_actual.cliente_id,
            "nombre": cliente_actual.cliente.nombre if cliente_actual.cliente else "Desconocido",
            "direccion": cliente_actual.cliente.direccion if cliente_actual.cliente else None,
            "telefono": cliente_actual.cliente.telefono if cliente_actual.cliente else None,
            "orden_visita": cliente_actual.orden,
            "precio_total": float(precio_total),
            "productos": productos_detalle
        },
        "progreso": {
            "total_clientes": total_clientes,
            "visitados": visitados,
            "pendientes": total_clientes - visitados,
            "porcentaje": round((visitados / total_clientes * 100), 2) if total_clientes > 0 else 0
        }
    }


def list_routes(db: Session, skip: int = 0, limit: int = 10) -> list[Route]:
    """Lista rutas con paginación."""
    return (
        db.query(Route)
        .order_by(Route.fecha.desc(), Route.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def count_routes(
    db: Session,
    vendedor_id: Optional[int] = None,
    estado: Optional[EstadoRuta] = None
) -> int:
    """Cuenta rutas con filtros."""
    query = db.query(func.count(Route.id))

    if vendedor_id:
        query = query.filter(Route.vendedor_id == vendedor_id)

    if estado:
        query = query.filter(Route.estado == estado)

    return query.scalar()


def export_routes_to_excel(db: Session) -> bytes:
    """
    Exporta todas las rutas a Excel.

    Returns:
        bytes: Contenido del archivo Excel
    """
    from src.utils.excel_formatter import export_to_excel
    from src.utils.type_converters import safe_title
    from src.utils.date_parser import parse_date_string

    try:
        routes = (
            db.query(Route)
            .join(Route.vendedor)
            .order_by(Route.fecha.desc(), Route.id.desc())
            .all()
        )

        if not routes:
            logger.warning("No routes found to export")
            data = []
        else:
            data = []
            for route in routes:
                # Calcular totales
                total_clientes = len(route.detalles)
                clientes_entregados = sum(
                    1 for d in route.detalles
                    if d.estado_entrega == 'entregado'
                )

                data.append({
                    "id": route.id,
                    "nombre": safe_title(route.nombre),
                    "vendedor": safe_title(route.vendedor.nombre),
                    "estado": route.estado.capitalize(),
                    "total_clientes": total_clientes,
                    "clientes_entregados": clientes_entregados,

                })

            logger.info(f"Exporting {len(routes)} routes to Excel")

        excel_file = export_to_excel(
            data=data,
            filename="rutas.xlsx",
            sheet_name="Rutas"
        )

        return excel_file.getvalue()

    except Exception as e:
        logger.exception(f"Error exporting routes to Excel: {str(e)}")
        raise Exception(f"Error al exportar rutas a Excel: {str(e)}")


def export_routes_to_pdf(db: Session) -> bytes:
    """
    Exporta todas las rutas a PDF.

    Returns:
        bytes: Contenido del archivo PDF
    """
    from src.utils.pdf_exporter import PDFReportGenerator
    from src.utils.type_converters import safe_title
    from src.utils.date_parser import parse_date_string

    try:
        routes = (
            db.query(Route)
            .join(Route.vendedor)
            .order_by(Route.fecha.desc(), Route.id.desc())
            .all()
        )

        if not routes:
            logger.warning("No routes found to export")
            data = []
        else:
            data = []
            for route in routes:
                # Calcular totales
                total_clientes = len(route.detalles)
                clientes_entregados = sum(
                    1 for d in route.detalles
                    if d.estado_entrega == 'entregado'
                )

                data.append({
                    "nombre": safe_title(route.nombre),
                    "vendedor": safe_title(route.vendedor.nombre),
                    "estado": "En Proceso" if route.estado == "en_proceso" else route.estado.capitalize(),
                    "Clientes totales": total_clientes,
                    "Entregados": clientes_entregados,
                })

            logger.info(f"Exporting {len(routes)} routes to PDF")

        # Anchos personalizados para las columnas
        col_widths = [ 120.0, 120.0, 80.0, 100.0, 70.0]

        generator = PDFReportGenerator(
            title="REPORTE DE RUTAS",
            page_size=letter,
            author="Sistema",
            subject="reporte_rutas.pdf"
        )

        pdf_bytes = generator.generate(
            headers=[

                "Nombre",
                "Vendedor",
                "Estado",
                "Clientes totales",
                "Entregados",

            ],
            data=data,
            col_widths=col_widths
        )

        return pdf_bytes

    except Exception as e:
        logger.exception(f"Error exporting routes to PDF: {str(e)}")
        raise Exception(f"Error al exportar rutas a PDF: {str(e)}")
