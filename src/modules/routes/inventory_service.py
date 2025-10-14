"""
Servicio de gestión de inventario de rutas (CORREGIDO FINAL).
"""
from sqlalchemy.orm import Session
from typing import List, Dict, Any
import logging

from src.models.route import Route
from src.models.route_inventory import RouteInventory
from src.models.product import Product
from src.modules.routes.type import EstadoRuta

logger = logging.getLogger(__name__)


class InsufficientStockError(Exception):
    """Error cuando no hay suficiente stock en el almacén."""
    def __init__(self, message: str, productos_faltantes: List[Dict[str, Any]] = None):
        super().__init__(message)
        self.productos_faltantes = productos_faltantes or []


def reserve_stock_for_route(
    db: Session,
    ruta_id: int,
    almacen_id: int,
    inventario_dict: Dict[int, int]
) -> None:
    """
    🔥 NUEVA VERSIÓN: Descuenta stock AL CREAR LA RUTA (no al iniciarla).

    Args:
        db: Sesión de base de datos
        ruta_id: ID de la ruta
        almacen_id: ID del almacén
        inventario_dict: {producto_id: cantidad_total}

    Raises:
        InsufficientStockError: Si no hay stock suficiente
    """
    productos_faltantes: List[Dict[str, Any]] = []

    for producto_id, cantidad_necesaria in inventario_dict.items():
        producto = db.query(Product).filter(Product.id == producto_id).first()

        if not producto:
            raise ValueError(f"Producto {producto_id} no existe")

        stock_actual = int(producto.stock_total) if producto.stock_total is not None else 0

        # Validar stock
        if stock_actual < cantidad_necesaria:
            productos_faltantes.append({
                "producto_id": int(producto_id),
                "nombre": producto.nombre,
                "requerido": cantidad_necesaria,
                "disponible": stock_actual
            })
            continue

        # 🔥 DESCONTAR del stock total
        producto.stock_total = stock_actual - cantidad_necesaria

        # 🔥 CREAR registro en inventario_ruta con cantidad_final inicializada
        inventario = RouteInventory(
            ruta_id=ruta_id,
            producto_id=producto_id,
            cantidad_inicial=cantidad_necesaria,
            cantidad_final=cantidad_necesaria  # 🔥 INICIALIZAR AQUÍ
        )
        db.add(inventario)

    if productos_faltantes:
        raise InsufficientStockError(
            f"Stock insuficiente para {len(productos_faltantes)} productos",
            productos_faltantes
        )

    db.commit()
    logger.info(
        f"Stock reserved for route {ruta_id} from warehouse {almacen_id}. "
        f"Total products: {len(inventario_dict)}"
    )


def update_inventory_after_delivery(
    db: Session,
    ruta_id: int,
    entregas: List[Dict[str, int]]
) -> None:
    """
    Actualiza inventario_ruta.cantidad_final después de cada entrega.
    """
    for entrega in entregas:
        producto_id = int(entrega["producto_id"])
        cantidad_entregada = int(entrega["cantidad"])

        inv_item = (
            db.query(RouteInventory)
            .filter(
                RouteInventory.ruta_id == ruta_id,
                RouteInventory.producto_id == producto_id
            )
            .first()
        )

        if not inv_item:
            raise ValueError(
                f"Producto {producto_id} no está en el inventario de la ruta"
            )

        cantidad_disponible = int(inv_item.cantidad_final) if inv_item.cantidad_final is not None else 0

        if cantidad_disponible < cantidad_entregada:
            raise ValueError(
                f"No hay suficiente stock en ruta para producto {producto_id}. "
                f"Disponible: {cantidad_disponible}, "
                f"Solicitado: {cantidad_entregada}"
            )

        # 🔥 Descontar del inventario de la ruta
        inv_item.cantidad_final = cantidad_disponible - cantidad_entregada

    db.commit()
    logger.info(f"Inventory updated for route {ruta_id}")


def return_remaining_stock_to_warehouse(
    db: Session,
    ruta_id: int,
    almacen_id: int
) -> Dict[str, Any]:
    """
    Devuelve stock no entregado al almacén (al finalizar ruta).
    """
    route = db.query(Route).filter(Route.id == ruta_id).first()
    if not route:
        raise ValueError(f"Ruta {ruta_id} no existe")

    if route.estado != EstadoRuta.EN_PROCESO.value:
        raise ValueError("Solo se pueden finalizar rutas en proceso")

    inventario_items = (
        db.query(RouteInventory)
        .filter(RouteInventory.ruta_id == ruta_id)
        .all()
    )

    total_devuelto = 0
    productos_devueltos: List[Dict[str, Any]] = []

    for item in inventario_items:
        cantidad_devuelta = int(item.cantidad_final) if item.cantidad_final is not None else 0

        if cantidad_devuelta > 0:
            producto = (
                db.query(Product)
                .filter(Product.id == item.producto_id)
                .first()
            )

            if not producto:
                logger.warning(f"Producto {item.producto_id} no encontrado al devolver stock")
                continue

            # 🔥 Devolver al stock
            current_stock = int(producto.stock_total) if producto.stock_total is not None else 0
            producto.stock_total = current_stock + cantidad_devuelta

            total_devuelto += cantidad_devuelta
            productos_devueltos.append({
                "producto_id": int(item.producto_id),
                "nombre": producto.nombre,
                "cantidad_devuelta": cantidad_devuelta
            })

    db.commit()
    logger.info(
        f"Stock returned to warehouse {almacen_id} from route {ruta_id}: "
        f"{total_devuelto} units"
    )

    return {
        "total_productos_devueltos": len(productos_devueltos),
        "total_unidades_devueltas": total_devuelto,
        "detalle": productos_devueltos
    }


def get_route_inventory_status(
    db: Session,
    ruta_id: int
) -> Dict[str, Any]:
    """
    Obtiene el estado actual del inventario de una ruta.
    """
    inventario_items = (
        db.query(RouteInventory)
        .filter(RouteInventory.ruta_id == ruta_id)
        .all()
    )

    if not inventario_items:
        return {
            "productos": [],
            "total_inicial": 0,
            "total_actual": 0,
            "total_entregado": 0,
            "porcentaje_entregado": 0.0
        }

    productos: List[Dict[str, Any]] = []
    total_inicial = 0
    total_actual = 0

    for item in inventario_items:
        producto = (
            db.query(Product)
            .filter(Product.id == item.producto_id)
            .first()
        )

        cantidad_inicial_int = int(item.cantidad_inicial)
        cantidad_final_int = int(item.cantidad_final) if item.cantidad_final is not None else 0
        cantidad_entregada = cantidad_inicial_int - cantidad_final_int

        porcentaje = (
            float(cantidad_entregada) / float(cantidad_inicial_int) * 100.0
            if cantidad_inicial_int > 0 else 0.0
        )

        productos.append({
            "producto_id": int(item.producto_id),
            "nombre": producto.nombre if producto else "Desconocido",
            "cantidad_inicial": cantidad_inicial_int,
            "cantidad_actual": cantidad_final_int,
            "cantidad_entregada": cantidad_entregada,
            "porcentaje_entregado": round(porcentaje, 2)
        })

        total_inicial += cantidad_inicial_int
        total_actual += cantidad_final_int

    total_entregado = total_inicial - total_actual
    porcentaje_entregado = (
        float(total_entregado) / float(total_inicial) * 100.0
        if total_inicial > 0 else 0.0
    )

    return {
        "productos": productos,
        "total_inicial": total_inicial,
        "total_actual": total_actual,
        "total_entregado": total_entregado,
        "porcentaje_entregado": round(porcentaje_entregado, 2)
    }
