from sqlalchemy.orm import Session
from sqlalchemy import func, or_, cast, Date
from typing import List, Optional, Tuple, cast
import logging
from datetime import datetime, date
from src.models.orders import Order
from src.models.customer import Customer
from src.models.product import Product
from src.modules.orders.type import OrderCreate, OrderUpdate
from src.utils.pdf_generator import PDFReportOrder
from reportlab.lib.pagesizes import letter
from src.utils.product_helpers import get_product_display_name_from_order
from src.utils.type_converters import safe_title
from src.utils.date_parser import parse_date_flexible, parse_date_string
from src.utils.excel_formatter import (
    read_excel,
    convert_to_model_list,
    export_to_excel,
    ExcelImportError
)

logger = logging.getLogger(__name__)

def create_order(db: Session, order_data: OrderCreate) -> Order:
    """
    Crea una nueva orden y RESERVA el stock (sin descontarlo del stock_total).
    El stock_total solo se descuenta cuando se crea la ruta.
    """

    # ✅ Verificar producto
    producto = db.query(Product).filter(
        Product.id == order_data.producto_id,
        Product.activo == True
    ).first()

    if not producto:
        raise ValueError(f"Producto con ID {order_data.producto_id} no existe o está inactivo")

    # ✅ Verificar cliente
    cliente = db.query(Customer).filter(Customer.id == order_data.cliente_id).first()
    if not cliente:
        raise ValueError(f"Cliente con ID {order_data.cliente_id} no existe")

    # 🔥 VALIDAR STOCK DISPONIBLE (stock_total - stock_reservado)
    stock_total = producto.stock_total or 0
    stock_reservado = producto.stock_reservado or 0
    stock_disponible = stock_total - stock_reservado

    if stock_disponible < order_data.cantidad:
        raise ValueError(
            f"Stock insuficiente para {producto.nombre}. "
            f"Disponible: {stock_disponible} (Total: {stock_total}, "
            f"Reservado: {stock_reservado}), Solicitado: {order_data.cantidad}"
        )

    # 🔥 RESERVAR STOCK (NO descontar de stock_total todavía)
    producto.stock_reservado = stock_reservado + order_data.cantidad

    # 🔧 El validador de Pydantic ya convirtió fecha_solicitud a datetime
    # Si no se proporcionó, ya tiene datetime.now()
    fecha_orden = order_data.fecha_solicitud

    # Crear orden
    order = Order(
        cliente_id=order_data.cliente_id,
        producto_id=order_data.producto_id,
        producto_nombre_snapshot=producto.nombre,
        cantidad=order_data.cantidad,
        prioridad="normal",
        fecha_solicitud=fecha_orden,  # type: ignore[arg-type]
        asignada=False,
        cancelada=False
    )

    db.add(order)
    db.commit()
    db.refresh(order)

    logger.info(
        f"✅ Order #{order.id} created: {order_data.cantidad}x {producto.nombre}. "
        f"Stock: Total={stock_total}, Reservado={producto.stock_reservado}, "
        f"Disponible={stock_total - producto.stock_reservado}"
    )

    return order


def cancel_order(db: Session, order_id: int) -> Order:
    """
    Cancela una orden y LIBERA el stock reservado.

    ⚠️ Solo se pueden cancelar órdenes que NO estén asignadas a una ruta.
    """
    order = db.query(Order).filter(Order.id == order_id).first()

    if not order:
        raise ValueError(f"Orden #{order_id} no existe")

    if order.cancelada:
        raise ValueError("La orden ya está cancelada")

    if order.asignada:
        raise ValueError(
            "No se puede cancelar una orden asignada a una ruta. "
            "Debes marcarla como 'no entregada' desde la ruta."
        )

    # 🔥 LIBERAR STOCK RESERVADO
    producto = db.query(Product).filter(Product.id == order.producto_id).first()

    if producto:
        stock_reservado = producto.stock_reservado or 0
        producto.stock_reservado = max(0, stock_reservado - order.cantidad)

        logger.info(
            f"📦 Stock liberado: {order.cantidad}x {producto.nombre}. "
            f"Nuevo stock reservado: {producto.stock_reservado}"
        )
    else:
        logger.warning(f"⚠️ Producto #{order.producto_id} no encontrado al cancelar orden")

    # Marcar como cancelada
    order.cancelada = True

    db.commit()
    db.refresh(order)

    logger.info(f"❌ Orden #{order_id} cancelada exitosamente")
    return order


def get_order(db: Session, order_id: int) -> Order | None:
    """Obtiene una orden por su ID"""
    return db.query(Order).filter(Order.id == order_id).first()


def update_order(db: Session, order_id: int, order_data: OrderUpdate) -> Order | None:
    """
    Actualiza una orden y ajusta reservas si cambia la cantidad.
    """
    order = get_order(db, order_id)
    if not order:
        return None

    # 🛡️ No permitir editar órdenes asignadas o canceladas
    if order.asignada:
        raise ValueError("No se puede editar una orden asignada a una ruta")

    if order.cancelada:
        raise ValueError("No se puede editar una orden cancelada")

    # Si se cambia la cantidad, ajustar reserva
    if order_data.cantidad is not None and order_data.cantidad != order.cantidad:
        producto = db.query(Product).filter(Product.id == order.producto_id).first()

        if not producto:
            raise ValueError(f"Producto con ID {order.producto_id} no existe")

        diferencia = order_data.cantidad - order.cantidad
        stock_reservado = producto.stock_reservado or 0
        stock_total = producto.stock_total or 0
        stock_disponible = stock_total - stock_reservado

        # Si aumenta la cantidad, validar stock
        if diferencia > 0:
            if stock_disponible < diferencia:
                raise ValueError(
                    f"Stock insuficiente. Disponible: {stock_disponible}, "
                    f"Adicional requerido: {diferencia}"
                )
            producto.stock_reservado = stock_reservado + diferencia
        else:
            # Si disminuye, liberar stock
            producto.stock_reservado = max(0, stock_reservado + diferencia)

        order.cantidad = order_data.cantidad

    # Actualizar cliente
    if order_data.cliente_id is not None:
        order.cliente_id = order_data.cliente_id

    # Si cambia el producto
    if order_data.producto_id is not None:
        producto_viejo = db.query(Product).filter(Product.id == order.producto_id).first()
        producto_nuevo = db.query(Product).filter(
            Product.id == order_data.producto_id,
            Product.activo == True
        ).first()

        if not producto_nuevo:
            raise ValueError(f"Producto con ID {order_data.producto_id} no existe o está inactivo")

        if not producto_viejo:
            raise ValueError(f"Producto viejo con ID {order.producto_id} no existe")

        # Liberar reserva del producto viejo
        producto_viejo.stock_reservado = max(0, (producto_viejo.stock_reservado or 0) - order.cantidad)

        # Reservar en producto nuevo
        stock_disponible_nuevo = (producto_nuevo.stock_total or 0) - (producto_nuevo.stock_reservado or 0)
        if stock_disponible_nuevo < order.cantidad:
            raise ValueError(
                f"Stock insuficiente en el nuevo producto. "
                f"Disponible: {stock_disponible_nuevo}, Requerido: {order.cantidad}"
            )

        producto_nuevo.stock_reservado = (producto_nuevo.stock_reservado or 0) + order.cantidad

        order.producto_id = order_data.producto_id
        order.producto_nombre_snapshot = producto_nuevo.nombre

    # Actualizar fecha (el validador ya convirtió a datetime si es necesario)
    if order_data.fecha_solicitud is not None:
        order.fecha_solicitud = order_data.fecha_solicitud  # type: ignore[assignment]

    db.commit()
    db.refresh(order)

    logger.info(
        f"✅ Order #{order_id} updated. "
        f"Producto: {order.producto_id}, Cantidad: {order.cantidad}"
    )

    return order


def list_orders(
    db: Session,
    skip: int = 0,
    limit: int = 10,
    include_cancelled: bool = False  # 🆕 Parámetro opcional
) -> list[Order]:
    """
    Lista órdenes con paginación.

    Args:
        skip: Número de registros a saltar
        limit: Número máximo de registros
        include_cancelled: Si True, incluye órdenes canceladas
    """
    query = db.query(Order)

    if not include_cancelled:
        query = query.filter(Order.cancelada == False)

    return (
        query
        .order_by(Order.fecha_solicitud.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def count_orders(db: Session, include_cancelled: bool = False) -> int:
    """
    Cuenta el total de ordenes.

    Args:
        include_cancelled: Si True, incluye órdenes canceladas
    """
    query = db.query(func.count(Order.id))

    if not include_cancelled:
        query = query.filter(Order.cancelada == False)

    return query.scalar()


def search_customers_for_order(
    db: Session,
    query: str,
    limit: int = 10
) -> List[dict]:
    """
    Busca clientes por nombre o teléfono para usar en el selector de órdenes.
    Si query está vacío, retorna los primeros N clientes.
    """
    if not query or len(query.strip()) == 0:
        customers = (
            db.query(Customer)
            .order_by(Customer.nombre)
            .limit(limit)
            .all()
        )
    else:
        search_pattern = f"%{query}%"
        customers = (
            db.query(Customer)
            .filter(
                or_(
                    Customer.nombre.ilike(search_pattern),
                    Customer.telefono.ilike(search_pattern)
                )
            )
            .order_by(Customer.nombre)
            .limit(limit)
            .all()
        )

    return [
        {
            "id": c.id,
            "nombre": c.nombre,
            "telefono": c.telefono,
            "direccion": c.direccion
        }
        for c in customers
    ]


def search_products_for_order(
    db: Session,
    query: str,
    limit: int = 10
) -> List[dict]:
    """
    Busca productos por nombre para usar en el selector de órdenes.
    Muestra stock disponible (stock_total - stock_reservado).
    """
    if not query or len(query.strip()) == 0:
        products = (
            db.query(Product)
            .filter(Product.activo == True)
            .order_by(Product.nombre)
            .limit(limit)
            .all()
        )
    else:
        search_pattern = f"%{query}%"
        products = (
            db.query(Product)
            .filter(
                Product.nombre.ilike(search_pattern),
                Product.activo == True
            )
            .order_by(Product.nombre)
            .limit(limit)
            .all()
        )

    return [
        {
            "id": p.id,
            "nombre": p.nombre,
            "precio": float(p.precio) if p.precio else 0.0,
            "stock_total": p.stock_total or 0,
            "stock_reservado": p.stock_reservado or 0,
            "stock_disponible": max(0, (p.stock_total or 0) - (p.stock_reservado or 0))  # 🔥 No negativos
        }
        for p in products
    ]

def search_orders_by_client_or_phone(
    db: Session,
    query: str,
    skip: int = 0,
    limit: int = 10,
    include_cancelled: bool = False  # 🆕 Agregar parámetro
) -> List[Order]:
    """Busca órdenes por nombre de cliente o teléfono."""
    search_pattern = f"%{query}%"

    query_builder = (
        db.query(Order)
        .join(Customer, Order.cliente_id == Customer.id)
        .filter(
            or_(
                Customer.nombre.ilike(search_pattern),
                Customer.telefono.ilike(search_pattern)
            )
        )
    )

    # 🆕 Solo filtrar canceladas si no se pide incluirlas
    if not include_cancelled:
        query_builder = query_builder.filter(Order.cancelada == False)

    orders = (
        query_builder
        .order_by(Order.fecha_solicitud.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    logger.info(f"Found {len(orders)} orders matching query: {query}")
    return orders


def get_orders_by_date(db: Session, fecha: str) -> List[Order]:
    """
    Obtiene órdenes NO asignadas y NO canceladas de una fecha específica.
    Usado para el modal de crear ruta.
    """
    fecha_obj = parse_date_flexible(fecha, allow_slashes=False)

    if fecha_obj is None:
        raise ValueError(
            "Formato de fecha inválido. Use DD-MM-YYYY o YYYY-MM-DD (sin slashes)"
        )

    fecha_date = fecha_obj.date()

    orders = (
        db.query(Order)
        .join(Customer, Order.cliente_id == Customer.id)
        .join(Product, Order.producto_id == Product.id)
        .filter(
            cast(Order.fecha_solicitud, Date) == fecha_date, # type: ignore[arg-type]
            Order.asignada == False,
            Order.cancelada == False
        )
        .order_by(Order.prioridad.desc(), Order.fecha_solicitud)
        .all()
    )

    logger.info(f"Found {len(orders)} unassigned active orders for date {fecha_date}")
    return orders


def count_orders_by_date(db: Session, fecha: str) -> int:
    """Cuenta órdenes activas de una fecha específica."""
    fecha_obj = parse_date_flexible(fecha)
    if fecha_obj is None:
        return 0

    fecha_date = fecha_obj.date()

    return (
        db.query(func.count(Order.id))
        .filter(
            func.date(Order.fecha_solicitud) == fecha_date,
            Order.cancelada == False  # 🔥 Solo activas
        )
        .scalar()
    )


def count_search_results(db: Session, query: str) -> int:
    """Cuenta el total de resultados de búsqueda (solo órdenes activas)"""
    search_pattern = f"%{query}%"
    return (
        db.query(func.count(Order.id))
        .join(Customer, Order.cliente_id == Customer.id)
        .filter(
            or_(
                Customer.nombre.ilike(search_pattern),
                Customer.telefono.ilike(search_pattern)
            ),
            Order.cancelada == False  # 🔥 Solo activas
        )
        .scalar()
    )


def get_unassigned_orders_by_cliente(
    db: Session,
    cliente_ids: List[int]
) -> dict:
    """Obtiene órdenes pendientes (activas) agrupadas por cliente."""
    orders = (
        db.query(Order)
        .filter(
            Order.cliente_id.in_(cliente_ids),
            Order.asignada == False,
            Order.cancelada == False  # 🔥 Solo activas
        )
        .all()
    )

    orders_by_cliente = {}
    for order in orders:
        if order.cliente_id not in orders_by_cliente:
            orders_by_cliente[order.cliente_id] = []

        orders_by_cliente[order.cliente_id].append({
            "orden_id": order.id,
            "producto_id": order.producto_id,
            "producto_nombre": (
                order.producto_nombre_snapshot  # 🔥 Prioridad al snapshot
                or (order.producto.nombre if order.producto else "Producto eliminado")
            ),
            "cantidad": order.cantidad,
            "prioridad": order.prioridad
        })

    return orders_by_cliente


def mark_orders_as_assigned(
    db: Session,
    orden_ids: List[int],
    ruta_id: int
) -> None:
    """Marca órdenes como asignadas a una ruta."""
    db.query(Order).filter(Order.id.in_(orden_ids)).update(
        {"asignada": True, "ruta_id": ruta_id},
        synchronize_session=False
    )
    db.commit()


def export_orders_to_excel(db: Session) -> bytes:
    """Exporta TODAS las órdenes (activas Y canceladas) a Excel."""
    try:
        orders = (
            db.query(Order)
            .join(Customer, Order.cliente_id == Customer.id)
            .join(Product, Order.producto_id == Product.id)
            .order_by(Order.fecha_solicitud.desc())
            .all()
        )

        if not orders:
            logger.warning("No orders found to export")
            data = []
        else:
            data = []
            for order in orders:
                # 🔥 Formatear fecha a DD/MM/YYYY
                if order.fecha_solicitud:
                    # Cast to python datetime to satisfy static type checkers
                    fecha_dt = cast(datetime, order.fecha_solicitud)
                    fecha_str = fecha_dt.strftime("%d/%m/%Y")
                else:
                    fecha_str = "Sin fecha"

                data.append({
                    "Cliente": safe_title(order.cliente.nombre),
                    "Producto": safe_title(get_product_display_name_from_order(order)),
                    "Cantidad": order.cantidad,
                    "Fecha Solicitud": fecha_str,
                    "Vigencia": "Cancelada" if order.cancelada else "Activa"
                })

        excel_file = export_to_excel(
            data=data,
            filename="ordenes_completas.xlsx",
            sheet_name="Ordenes"
        )

        return excel_file.getvalue()

    except Exception as e:
        logger.exception(f"Error exporting orders to Excel: {str(e)}")
        raise Exception(f"Error al exportar órdenes a Excel: {str(e)}")


def export_orders_to_pdf(db: Session) -> bytes:
    """
    Exporta TODAS las órdenes (activas Y canceladas) a PDF con estadísticas.
    """
    try:
        orders = (
            db.query(Order)
            .join(Customer, Order.cliente_id == Customer.id)
            .join(Product, Order.producto_id == Product.id)
            .order_by(Order.fecha_solicitud.desc())
            .all()
        )

        if not orders:
            logger.warning("No orders found to export")
            data = []
            stats = {
                "total": 0,
                "activas": 0,
                "canceladas": 0,
                "porcentaje_activas": 0,
                "porcentaje_canceladas": 0
            }
        else:
            # 📊 Calcular estadísticas
            total = len(orders)
            canceladas = sum(1 for o in orders if o.cancelada)
            activas = total - canceladas

            stats = {
                "total": total,
                "activas": activas,
                "canceladas": canceladas,
                "porcentaje_activas": round((activas / total) * 100, 1) if total > 0 else 0,
                "porcentaje_canceladas": round((canceladas / total) * 100, 1) if total > 0 else 0
            }

            data = []
            for order in orders:
                # 🔥 Formatear fecha a DD/MM/YYYY
                # 🔥 Formatear fecha a DD/MM/YYYY
                if order.fecha_solicitud:
                    # Cast to python datetime to satisfy static type checkers
                    fecha_dt = cast(datetime, order.fecha_solicitud)
                    fecha_str = fecha_dt.strftime("%d/%m/%Y")
                else:
                    fecha_str = "Sin fecha"

                data.append({
                    "Cliente": safe_title(order.cliente.nombre),
                    "Producto": safe_title(get_product_display_name_from_order(order)),
                    "Cantidad": order.cantidad,
                    "Fecha Solicitud": fecha_str,
                    "Vigencia": "CANCELADA" if order.cancelada else "Activa"
                })
        # 🔥 Anchos de columna ajustados para 5 columnas
        col_widths = [150.0, 150.0, 70.0, 100.0, 80.0]

        generator = PDFReportOrder(
            title="REPORTE DE ÓRDENES",
            page_size=letter,
            author="Sistema",
            subject="reporte_ordenes.pdf"
        )

        pdf_bytes = generator.generate(
            headers=["Cliente", "Producto", "Cantidad", "Fecha Solicitud", "Vigencia"],
            data=data,
            col_widths=col_widths,
            stats=stats
        )

        return pdf_bytes

    except Exception as e:
        logger.exception(f"Error exporting orders to PDF: {str(e)}")
        raise Exception(f"Error al exportar órdenes a PDF: {str(e)}")
