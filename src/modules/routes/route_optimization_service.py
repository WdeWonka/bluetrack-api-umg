"""
Servicio de optimización de rutas por cercanía geográfica.
Implementa algoritmo greedy del vecino más cercano.
"""
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional, Tuple
import logging
import math

from src.models.route import Route
from src.models.route_detail import RouteDetail
from src.models.customer import Customer
from src.models.warehouse import Warehouse

logger = logging.getLogger(__name__)


def calculate_distance(
    lat1: float, lon1: float,
    lat2: float, lon2: float
) -> float:
    """
    Calcula la distancia entre dos puntos geográficos usando la fórmula de Haversine.

    Args:
        lat1, lon1: Coordenadas del punto 1
        lat2, lon2: Coordenadas del punto 2

    Returns:
        Distancia en kilómetros
    """
    # Radio de la Tierra en kilómetros
    R = 6371.0

    # Convertir grados a radianes
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    # Diferencias
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    # Fórmula de Haversine
    a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    distance = R * c
    return distance


def optimize_route_order_by_proximity(
    db: Session,
    route_id: int
) -> Dict[str, Any]:
    """
    Reordena los clientes de una ruta usando el algoritmo del vecino más cercano.

    Algoritmo:
    1. Comienza en el almacén
    2. Encuentra el cliente más cercano no visitado
    3. Se mueve a ese cliente
    4. Repite hasta visitar todos los clientes

    Args:
        db: Sesión de base de datos
        route_id: ID de la ruta

    Returns:
        Dict con el nuevo orden y distancias calculadas

    Raises:
        ValueError: Si la ruta no existe o faltan coordenadas
    """
    # Obtener ruta
    route = db.query(Route).filter(Route.id == route_id).first()
    if not route:
        raise ValueError(f"Ruta {route_id} no existe")

    # Obtener almacén
    warehouse = db.query(Warehouse).filter(
        Warehouse.id == route.almacen_id
    ).first()

    if not warehouse:
        raise ValueError(f"Almacén {route.almacen_id} no existe")

    # Validar coordenadas del almacén
    if warehouse.latitud is None or warehouse.longitud is None:
        raise ValueError(
            f"El almacén '{warehouse.nombre}' no tiene coordenadas configuradas"
        )

    # Obtener detalles de la ruta con clientes
    detalles = (
        db.query(RouteDetail)
        .join(Customer, RouteDetail.cliente_id == Customer.id)
        .filter(RouteDetail.ruta_id == route_id)
        .all()
    )

    if not detalles:
        raise ValueError("La ruta no tiene clientes asignados")

    # Validar que todos los clientes tengan coordenadas
    clientes_sin_coordenadas = []
    for detalle in detalles:
        cliente = detalle.cliente
        if cliente.latitud is None or cliente.longitud is None:
            clientes_sin_coordenadas.append(cliente.nombre)

    if clientes_sin_coordenadas:
        raise ValueError(
            f"Los siguientes clientes no tienen coordenadas: "
            f"{', '.join(clientes_sin_coordenadas)}"
        )

    # === ALGORITMO DEL VECINO MÁS CERCANO ===

    # Punto de inicio (almacén)
    current_lat = float(warehouse.latitud)
    current_lon = float(warehouse.longitud)

    # Clientes pendientes de visitar
    pending_details = list(detalles)
    ordered_details = []
    total_distance = 0.0
    distances = []

    while pending_details:
        # Encontrar el cliente más cercano
        closest_detail = None
        closest_distance = float('inf')

        for detail in pending_details:
            cliente = detail.cliente
            if cliente is None:
                continue  # Skip si el cliente no existe

            distance = calculate_distance(
                current_lat, current_lon,
                float(cliente.latitud), float(cliente.longitud)
            )

            if distance < closest_distance:
                closest_distance = distance
                closest_detail = detail

        # Validar que se encontró un cliente
        if closest_detail is None or closest_detail.cliente is None:
            logger.warning(f"No se pudo encontrar cliente válido en ruta {route_id}")
            break

        # Mover al cliente más cercano
        cliente_actual = closest_detail.cliente
        ordered_details.append(closest_detail)

        # Determinar origen para el segmento
        origen = "Almacén" if len(ordered_details) == 1 else ordered_details[-2].cliente.nombre if ordered_details[-2].cliente else "Desconocido"

        distances.append({
            "desde": origen,
            "hacia": cliente_actual.nombre,
            "distancia_km": round(closest_distance, 2)
        })

        total_distance += closest_distance
        current_lat = float(cliente_actual.latitud)
        current_lon = float(cliente_actual.longitud)

        pending_details.remove(closest_detail)

    # === ACTUALIZAR ORDEN EN BASE DE DATOS ===

    for new_order, detail in enumerate(ordered_details, start=1):
        detail.orden = new_order

    db.commit()

    logger.info(
        f"Route {route_id} optimized. "
        f"Total distance: {round(total_distance, 2)} km, "
        f"Clients: {len(ordered_details)}"
    )

    return {
        "route_id": route_id,
        "total_clientes": len(ordered_details),
        "distancia_total_km": round(total_distance, 2),
        "distancia_promedio_km": round(total_distance / len(ordered_details), 2) if ordered_details else 0,
        "orden_optimizado": [
            {
                "detalle_id": detail.id,
                "cliente_id": detail.cliente_id,
                "cliente_nombre": detail.cliente.nombre,
                "nuevo_orden": detail.orden,
                "latitud": float(detail.cliente.latitud),
                "longitud": float(detail.cliente.longitud)
            }
            for detail in ordered_details
        ],
        "segmentos": distances
    }


def get_next_client_to_visit(
    db: Session,
    route_id: int
) -> Optional[Dict[str, Any]]:
    """
    Obtiene el siguiente cliente a visitar en una ruta ordenada.

    Args:
        db: Sesión de base de datos
        route_id: ID de la ruta

    Returns:
        Dict con información del cliente o None si no hay más clientes
    """
    from src.models.orders import Order

    # Buscar el siguiente cliente no visitado
    next_detail = (
        db.query(RouteDetail)
        .filter(
            RouteDetail.ruta_id == route_id,
            RouteDetail.estado_entrega == 'no_entregado',
            RouteDetail.motivo.is_(None)  # No ha sido marcado como "no entregado con motivo"
        )
        .order_by(RouteDetail.orden)
        .first()
    )

    if not next_detail:
        return None

    # Obtener órdenes del cliente
    ordenes = (
        db.query(Order)
        .filter(
            Order.ruta_id == route_id,
            Order.cliente_id == next_detail.cliente_id
        )
        .all()
    )

    cliente = next_detail.cliente

    return {
        "detalle_id": next_detail.id,
        "cliente_id": cliente.id,
        "nombre": cliente.nombre,
        "direccion": cliente.direccion,
        "telefono": cliente.telefono,
        "latitud": float(cliente.latitud) if cliente.latitud else None,
        "longitud": float(cliente.longitud) if cliente.longitud else None,
        "orden_visita": next_detail.orden,
        "productos": [
            {
                "orden_id": orden.id,
                "producto_id": orden.producto_id,
                "producto_nombre": orden.producto.nombre,
                "cantidad": orden.cantidad,
                "precio_unitario": float(orden.producto.precio)
            }
            for orden in ordenes
        ]
    }
