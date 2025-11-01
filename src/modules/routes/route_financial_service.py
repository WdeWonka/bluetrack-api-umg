"""
Servicio de análisis financiero de rutas.
"""
from sqlalchemy.orm import Session
from typing import Dict, Any, List
from decimal import Decimal
import logging

from src.models.route import Route
from src.models.route_detail import RouteDetail
from src.models.orders import Order
from src.models.delivery import Delivery
from src.models.route_inventory import RouteInventory
from src.utils.product_helpers import get_product_display_name_from_order


logger = logging.getLogger(__name__)


def calculate_client_financial_info(
    db: Session,
    ruta_detalle_id: int
) -> Dict[str, Any]:
    """
    Calcula información financiera de un cliente específico.

    Returns:
        Dict con subtotal esperado y subtotal entregado
    """
    detalle = db.query(RouteDetail).filter(
        RouteDetail.id == ruta_detalle_id
    ).first()

    if not detalle:
        return {
            "subtotal_esperado": 0.0,
            "subtotal_entregado": 0.0,
            "productos": []
        }

    # Obtener órdenes del cliente
    ordenes = (
        db.query(Order)
        .filter(
            Order.ruta_id == detalle.ruta_id,
            Order.cliente_id == detalle.cliente_id
        )
        .all()
    )

    subtotal_esperado = Decimal('0')
    subtotal_entregado = Decimal('0')
    productos_info = []

    for orden in ordenes:
        precio_unitario = Decimal(str(orden.producto.precio))
        cantidad_ordenada = orden.cantidad

        # Calcular esperado
        monto_esperado = precio_unitario * Decimal(str(cantidad_ordenada))
        subtotal_esperado += monto_esperado

        # Calcular entregado
        entregas = db.query(Delivery).filter(
            Delivery.orden_id == orden.id
        ).all()

        cantidad_entregada = sum(e.cantidad for e in entregas)
        monto_entregado = precio_unitario * Decimal(str(cantidad_entregada))
        subtotal_entregado += monto_entregado

        productos_info.append({
            "producto_id": orden.producto_id,
            "producto_nombre": get_product_display_name_from_order(orden),
            "precio_unitario": float(precio_unitario),
            "cantidad_ordenada": cantidad_ordenada,
            "cantidad_entregada": cantidad_entregada,
            "monto_esperado": float(monto_esperado),
            "monto_entregado": float(monto_entregado)
        })

    return {
        "subtotal_esperado": float(subtotal_esperado),
        "subtotal_entregado": float(subtotal_entregado),
        "productos": productos_info
    }


def get_route_financial_summary(
    db: Session,
    route_id: int
) -> Dict[str, Any]:
    """
    Genera resumen financiero completo de una ruta.

    **Incluye:**
    - Total esperado (todas las órdenes)
    - Total entregado (lo que realmente se vendió)
    - Pérdida por no entregas
    - Desglose por cliente
    - Análisis de inventario
    """
    route = db.query(Route).filter(Route.id == route_id).first()
    if not route:
        raise ValueError(f"Ruta {route_id} no encontrada")

    detalles = (
        db.query(RouteDetail)
        .filter(RouteDetail.ruta_id == route_id)
        .order_by(RouteDetail.orden)
        .all()
    )

    # === CÁLCULOS FINANCIEROS POR CLIENTE ===
    total_esperado = Decimal('0')
    total_entregado = Decimal('0')
    clientes_detalle = []

    for detalle in detalles:
        info_cliente = calculate_client_financial_info(db, detalle.id)

        total_esperado += Decimal(str(info_cliente['subtotal_esperado']))
        total_entregado += Decimal(str(info_cliente['subtotal_entregado']))

        clientes_detalle.append({
            "detalle_id": detalle.id,
            "cliente_id": detalle.cliente_id,
            "cliente_nombre": detalle.cliente.nombre if detalle.cliente else "Desconocido",
            "orden_visita": detalle.orden,
            "estado_entrega": detalle.estado_entrega,
            "subtotal_esperado": info_cliente['subtotal_esperado'],
            "subtotal_entregado": info_cliente['subtotal_entregado'],
            "productos": info_cliente['productos']
        })

    perdida_por_no_entregas = total_esperado - total_entregado

    # === ANÁLISIS DE INVENTARIO ===
    inventario_items = (
        db.query(RouteInventory)
        .filter(RouteInventory.ruta_id == route_id)
        .all()
    )

    inventario_resumen = []
    total_unidades_cargadas = 0
    total_unidades_entregadas = 0

    for item in inventario_items:
        cantidad_inicial = int(item.cantidad_inicial)
        cantidad_final = int(item.cantidad_final) if item.cantidad_final is not None else 0
        cantidad_entregada = cantidad_inicial - cantidad_final

        total_unidades_cargadas += cantidad_inicial
        total_unidades_entregadas += cantidad_entregada
        inventario_resumen.append({
            "producto_id": item.producto_id,
            "producto_nombre": item.producto.nombre if item.producto else "Desconocido",
            "cantidad_cargada": cantidad_inicial,
            "cantidad_entregada": cantidad_entregada,
            "cantidad_devuelta": cantidad_final,
            "porcentaje_vendido": round(
                (cantidad_entregada / cantidad_inicial * 100) if cantidad_inicial > 0 else 0,
                2
            )
        })

    # === ESTADÍSTICAS GENERALES ===
    total_clientes = len(detalles)
    clientes_entregados = sum(1 for d in detalles if d.estado_entrega == "entregado")
    clientes_no_entregados = sum(
        1 for d in detalles
        if d.estado_entrega == "no_entregado" and d.motivo is not None
    )

    tasa_conversion = (
        (clientes_entregados / total_clientes * 100) if total_clientes > 0 else 0
    )

    return {
        "ruta_id": route.id,
        "ruta_nombre": route.nombre,
        "estado": route.estado,
        "fecha": route.fecha.isoformat(),

        # 💰 RESUMEN FINANCIERO
        "resumen_financiero": {
            "total_esperado": float(total_esperado),
            "total_entregado": float(total_entregado),
            "perdida": float(perdida_por_no_entregas),
            "porcentaje_cobrado": round(
                (float(total_entregado) / float(total_esperado) * 100)
                if total_esperado > 0 else 0,
                2
            )
        },

        # 📦 RESUMEN DE INVENTARIO
        "resumen_inventario": {
            "total_unidades_cargadas": total_unidades_cargadas,
            "total_unidades_entregadas": total_unidades_entregadas,
            "total_unidades_devueltas": total_unidades_cargadas - total_unidades_entregadas,
            "porcentaje_vendido": round(
                (total_unidades_entregadas / total_unidades_cargadas * 100)
                if total_unidades_cargadas > 0 else 0,
                2
            ),
            "productos": inventario_resumen
        },

        # 👥 RESUMEN DE CLIENTES
        "resumen_clientes": {
            "total_clientes": total_clientes,
            "clientes_entregados": clientes_entregados,
            "clientes_no_entregados": clientes_no_entregados,
            "tasa_conversion": round(tasa_conversion, 2)
        },

        # 📋 DETALLE POR CLIENTE
        "clientes": clientes_detalle
    }


def export_route_summary_to_pdf(db: Session, route_id: int) -> bytes:
    """
    Exporta el resumen financiero de una ruta a PDF.

    Args:
        db: Sesión de base de datos
        route_id: ID de la ruta

    Returns:
        bytes: Contenido del PDF

    Raises:
        ValueError: Si la ruta no existe
    """
    from src.utils.financial_pdf_exporter import export_route_summary_to_pdf as generate_pdf

    # Obtener datos completos de la ruta
    route_data = get_route_financial_summary(db, route_id)

    # Generar PDF
    pdf_bytes = generate_pdf(route_data)

    logger.info(f"PDF exported for route {route_id}")
    return pdf_bytes


def get_route_progress_with_prices(
    db: Session,
    route_id: int
) -> Dict[str, Any]:
    """
    Obtiene progreso de ruta CON información de precios (versión ligera).
    """
    route = db.query(Route).filter(Route.id == route_id).first()
    if not route:
        raise ValueError(f"Ruta {route_id} no encontrada")

    detalles = (
        db.query(RouteDetail)
        .filter(RouteDetail.ruta_id == route_id)
        .order_by(RouteDetail.orden)
        .all()
    )

    total_esperado = Decimal('0')
    total_entregado = Decimal('0')
    clientes_info = []

    for detalle in detalles:
        info_cliente = calculate_client_financial_info(db, detalle.id)

        total_esperado += Decimal(str(info_cliente['subtotal_esperado']))
        total_entregado += Decimal(str(info_cliente['subtotal_entregado']))

        clientes_info.append({
            "detalle_id": detalle.id,
            "cliente_id": detalle.cliente_id,
            "cliente_nombre": detalle.cliente.nombre if detalle.cliente else "Desconocido",
            "orden_visita": detalle.orden,
            "estado_entrega": detalle.estado_entrega,
            "motivo": detalle.motivo,
            "timestamp": detalle.timestamp_entrega.isoformat() if detalle.timestamp_entrega else None,
            "subtotal_esperado": info_cliente['subtotal_esperado'],
            "subtotal_entregado": info_cliente['subtotal_entregado']
        })

    # Estadísticas
    total_clientes = len(detalles)
    entregados = sum(1 for d in detalles if d.estado_entrega == "entregado")
    no_entregados = sum(
        1 for d in detalles
        if d.estado_entrega == "no_entregado" and d.motivo is not None
    )
    pendientes = sum(
        1 for d in detalles
        if d.estado_entrega == "no_entregado" and d.motivo is None
    )

    visitados = entregados + no_entregados
    porcentaje = (visitados / total_clientes * 100) if total_clientes > 0 else 0

    return {
        "ruta_id": route_id,
        "estado_ruta": route.estado,
        "total_clientes": total_clientes,
        "visitados": visitados,
        "pendientes": pendientes,
        "entregados": entregados,
        "no_entregados": no_entregados,
        "porcentaje_avance": round(porcentaje, 2),

        # 💰 TOTALES FINANCIEROS
        "total_esperado": float(total_esperado),
        "total_entregado": float(total_entregado),
        "perdida_estimada": float(total_esperado - total_entregado),

        # 📋 DETALLE POR CLIENTE
        "detalles": clientes_info
    }
