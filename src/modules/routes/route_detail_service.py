"""
Servicio de detalles de ruta (MEJORADO con entrega automática).
"""
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List, Dict, Any
import logging

from src.models.route_detail import RouteDetail
from src.models.delivery import Delivery
from src.models.orders import Order
from src.modules.routes.type import RouteDetailUpdateStatus, EstadoEntrega
from src.modules.routes.inventory_service import update_inventory_after_delivery

logger = logging.getLogger(__name__)


def update_delivery_status(
    db: Session,
    ruta_detalle_id: int,
    status_data: RouteDetailUpdateStatus
) -> RouteDetail:
    """
    Actualiza estado de entrega con validación de entregas previas.
    """
    detalle = db.query(RouteDetail).filter(
        RouteDetail.id == ruta_detalle_id
    ).first()

    if not detalle:
        raise ValueError(f"Route detail {ruta_detalle_id} not found")

    detalle.estado_entrega = status_data.estado_entrega
    detalle.motivo = status_data.motivo
    detalle.timestamp_entrega = datetime.now()

    if status_data.estado_entrega == EstadoEntrega.ENTREGADO:
        entregas_list = []

        for entrega_item in status_data.entregas:
            orden = db.query(Order).filter(Order.id == entrega_item.orden_id).first()
            if not orden:
                raise ValueError(f"Orden {entrega_item.orden_id} no existe")

            if orden.cliente_id != detalle.cliente_id:
                raise ValueError(
                    f"Orden {entrega_item.orden_id} no pertenece al "
                    f"cliente {detalle.cliente_id}"
                )

            if orden.ruta_id != detalle.ruta_id:
                raise ValueError(
                    f"Orden {entrega_item.orden_id} no está asignada a "
                    f"esta ruta {detalle.ruta_id}"
                )

            entregas_previas = db.query(Delivery).filter(
                Delivery.orden_id == entrega_item.orden_id
            ).all()

            total_entregado_previo = sum(e.cantidad for e in entregas_previas)
            total_con_nueva = total_entregado_previo + entrega_item.cantidad

            if total_con_nueva > orden.cantidad:
                raise ValueError(
                    f"Total a entregar ({total_con_nueva}) excede "
                    f"la orden ({orden.cantidad}). "
                    f"Ya entregado: {total_entregado_previo}"
                )

            entrega = Delivery(
                ruta_detalle_id=detalle.id,
                orden_id=entrega_item.orden_id,
                producto_id=entrega_item.producto_id,
                cantidad=entrega_item.cantidad
            )
            db.add(entrega)

            entregas_list.append({
                "producto_id": entrega_item.producto_id,
                "cantidad": entrega_item.cantidad
            })

            if total_con_nueva == orden.cantidad:
                logger.info(f"Order {entrega_item.orden_id} fully delivered")
            else:
                logger.warning(
                    f"Order {entrega_item.orden_id} partially delivered: "
                    f"{total_con_nueva}/{orden.cantidad}"
                )

        update_inventory_after_delivery(db, detalle.ruta_id, entregas_list)

    db.commit()
    db.refresh(detalle)
    logger.info(f"Delivery status updated for detail {ruta_detalle_id}")
    return detalle


def deliver_all_orders_automatically(
    db: Session,
    ruta_detalle_id: int
) -> Dict[str, Any]:
    """
    🔥 NUEVO: Entrega TODAS las órdenes del cliente automáticamente.

    Útil para el flujo móvil donde el vendedor solo marca "entregado".
    """
    detalle = db.query(RouteDetail).filter(
        RouteDetail.id == ruta_detalle_id
    ).first()

    if not detalle:
        raise ValueError(f"Route detail {ruta_detalle_id} not found")

    if detalle.estado_entrega == 'entregado':
        raise ValueError("Este cliente ya fue marcado como entregado")

    # Obtener órdenes pendientes
    ordenes = (
        db.query(Order)
        .filter(
            Order.ruta_id == detalle.ruta_id,
            Order.cliente_id == detalle.cliente_id
        )
        .all()
    )

    if not ordenes:
        raise ValueError("No hay órdenes para entregar a este cliente")

    entregas_list = []
    entregas_registradas = []

    for orden in ordenes:
        # Verificar cuánto falta entregar
        entregas_previas = db.query(Delivery).filter(
            Delivery.orden_id == orden.id
        ).all()

        total_entregado_previo = sum(e.cantidad for e in entregas_previas)
        cantidad_pendiente = orden.cantidad - total_entregado_previo

        if cantidad_pendiente <= 0:
            logger.info(f"Order {orden.id} already fully delivered")
            continue

        # Registrar entrega completa
        entrega = Delivery(
            ruta_detalle_id=detalle.id,
            orden_id=orden.id,
            producto_id=orden.producto_id,
            cantidad=cantidad_pendiente
        )
        db.add(entrega)

        entregas_list.append({
            "producto_id": orden.producto_id,
            "cantidad": cantidad_pendiente
        })

        entregas_registradas.append({
            "orden_id": orden.id,
            "producto_id": orden.producto_id,
            "producto_nombre": orden.producto.nombre,
            "cantidad_entregada": cantidad_pendiente
        })

    if not entregas_list:
        raise ValueError("No hay cantidades pendientes por entregar")

    # Actualizar inventario
    update_inventory_after_delivery(db, detalle.ruta_id, entregas_list)

    # Marcar como entregado
    detalle.estado_entrega = 'entregado'
    detalle.timestamp_entrega = datetime.now()

    db.commit()
    db.refresh(detalle)

    logger.info(
        f"All orders delivered automatically for detail {ruta_detalle_id}: "
        f"{len(entregas_registradas)} deliveries"
    )

    return {
        "detalle_id": detalle.id,
        "cliente_id": detalle.cliente_id,
        "estado_entrega": detalle.estado_entrega,
        "timestamp_entrega": (t.isoformat() if (t := detalle.timestamp_entrega) else None),
        "entregas_registradas": entregas_registradas,
        "total_productos": len(entregas_registradas)
    }


def mark_as_not_delivered(
    db: Session,
    ruta_detalle_id: int,
    motivo: str
) -> RouteDetail:
    """
    🔥 NUEVO: Marca cliente como NO entregado con motivo.
    """
    if not motivo or len(motivo.strip()) == 0:
        raise ValueError("Debe proporcionar un motivo para no entregar")

    detalle = db.query(RouteDetail).filter(
        RouteDetail.id == ruta_detalle_id
    ).first()

    if not detalle:
        raise ValueError(f"Route detail {ruta_detalle_id} not found")

    if detalle.estado_entrega == 'entregado':
        raise ValueError("No se puede marcar como no entregado un cliente ya entregado")

    detalle.estado_entrega = 'no_entregado'
    detalle.motivo = motivo.strip()
    detalle.timestamp_entrega = datetime.now()

    db.commit()
    db.refresh(detalle)

    logger.info(f"Detail {ruta_detalle_id} marked as not delivered: {motivo}")
    return detalle


def get_route_detail_with_orders(
    db: Session,
    ruta_detalle_id: int
) -> dict:
    """
    Obtiene un detalle de ruta con sus órdenes asignadas.
    """
    detalle = db.query(RouteDetail).filter(
        RouteDetail.id == ruta_detalle_id
    ).first()

    if not detalle:
        raise ValueError(f"Route detail {ruta_detalle_id} not found")

    ordenes = (
        db.query(Order)
        .filter(
            Order.ruta_id == detalle.ruta_id,
            Order.cliente_id == detalle.cliente_id
        )
        .all()
    )

    entregas = db.query(Delivery).filter(
        Delivery.ruta_detalle_id == detalle.id
    ).all()

    fue_visitado = (
        detalle.estado_entrega == 'entregado' or
        (detalle.estado_entrega == 'no_entregado' and detalle.motivo is not None)
    )

    return {
        "detalle_id": detalle.id,
        "cliente_id": detalle.cliente_id,
        "cliente_nombre": detalle.cliente.nombre if detalle.cliente else "Desconocido",
        "orden_visita": detalle.orden,
        "estado_entrega": detalle.estado_entrega,
        "timestamp_entrega": detalle.timestamp_entrega.isoformat() if detalle.timestamp_entrega else None,
        "motivo": detalle.motivo,
        "fue_visitado": fue_visitado,
        "ordenes": [
            {
                "orden_id": o.id,
                "producto_id": o.producto_id,
                "producto_nombre": o.producto.nombre,
                "cantidad_ordenada": o.cantidad,
                "cantidad_entregada": _get_cantidad_entregada(db, o.id),
                "cantidad_pendiente": o.cantidad - _get_cantidad_entregada(db, o.id),
                "prioridad": o.prioridad
            }
            for o in ordenes
        ],
        "entregas": [
            {
                "orden_id": e.orden_id,
                "producto_id": e.producto_id,
                "cantidad_entregada": e.cantidad
            }
            for e in entregas
        ]
    }


def _get_cantidad_entregada(db: Session, orden_id: int) -> int:
    """Calcula cantidad total entregada de una orden."""
    from sqlalchemy import func

    resultado = (
        db.query(func.sum(Delivery.cantidad))
        .filter(Delivery.orden_id == orden_id)
        .scalar()
    )

    return int(resultado) if resultado is not None else 0
