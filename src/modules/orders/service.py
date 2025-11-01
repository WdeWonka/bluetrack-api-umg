from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from typing import List, Optional, Tuple
import logging
from src.models.orders import Order
from src.models.customer import Customer
from src.models.product import Product
from src.modules.orders.type import OrderCreate, OrderUpdate
from src.utils.pdf_exporter import PDFReportGenerator
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
    """Crea una nueva orden de cliente."""

    # ✅ Verificar que el producto existe y obtener su nombre
    producto = db.query(Product).filter(
        Product.id == order_data.producto_id,
        Product.activo == True  # Solo productos activos
    ).first()

    if not producto:
        raise ValueError(f"Producto con ID {order_data.producto_id} no existe o está inactivo")

    # ✅ Verificar que el cliente existe
    cliente = db.query(Customer).filter(Customer.id == order_data.cliente_id).first()
    if not cliente:
        raise ValueError(f"Cliente con ID {order_data.cliente_id} no existe")

    order = Order(
        cliente_id=order_data.cliente_id,
        producto_id=order_data.producto_id,
        producto_nombre_snapshot=producto.nombre,  # ✅ GUARDAR SNAPSHOT
        cantidad=order_data.cantidad,
        prioridad="normal",
        fecha_solicitud=order_data.fecha_solicitud
    )

    db.add(order)
    db.commit()
    db.refresh(order)
    return order

def get_order(db: Session, order_id: int) -> Order | None:
    """Obtiene una orden por su ID"""
    return db.query(Order).filter(Order.id == order_id).first()


def update_order(db: Session, order_id: int, order_data: OrderUpdate) -> Order | None:
    """Actualiza una orden existente."""
    order = get_order(db, order_id)
    if not order:
        return None

    if order_data.cliente_id is not None:
        order.cliente_id = order_data.cliente_id

    # ✅ Si se cambia el producto, actualizar snapshot
    if order_data.producto_id is not None:
        producto = db.query(Product).filter(
            Product.id == order_data.producto_id,
            Product.activo == True
        ).first()

        if not producto:
            raise ValueError(f"Producto con ID {order_data.producto_id} no existe o está inactivo")

        order.producto_id = order_data.producto_id
        order.producto_nombre_snapshot = producto.nombre  # ✅ ACTUALIZAR SNAPSHOT

    if order_data.cantidad is not None:
        order.cantidad = order_data.cantidad

    if order_data.fecha_solicitud is not None:
        if isinstance(order_data.fecha_solicitud, str):
            parsed_date = parse_date_flexible(order_data.fecha_solicitud)
            if parsed_date:
                order.fecha_solicitud = parsed_date  # type: ignore[attr-defined]
            else:
                raise ValueError(f"Formato de fecha inválido: {order_data.fecha_solicitud}")
        else:
            order.fecha_solicitud = order_data.fecha_solicitud  # type: ignore[attr-defined]

    db.commit()
    db.refresh(order)
    return order

def list_orders(db: Session, skip: int = 0, limit: int = 10) -> list[Order]:
    """
    Lista órdenes con paginación

    Args:
        db: Sesión de base de datos
        skip: Número de registros a saltar (offset)
        limit: Número máximo de registros a retornar
    """
    return (
        db.query(Order)
        .order_by(Order.fecha_solicitud.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def count_orders(db: Session) -> int:
    """Cuenta el total de ordenes"""
    return db.query(func.count(Order.id)).scalar()


def search_customers_for_order(
    db: Session,
    query: str,
    limit: int = 10
) -> List[dict]:
    """
    Busca clientes por nombre o teléfono para usar en el selector de órdenes.
    Si query está vacío, retorna los primeros N clientes.
    """
    # 🆕 Si no hay query, retornar los primeros clientes
    if not query or len(query.strip()) == 0:
        customers = (
            db.query(Customer)
            .order_by(Customer.nombre)  # Ordenar alfabéticamente
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
    Si query está vacío, retorna los primeros N productos.
    """
    # 🆕 Si no hay query, retornar los primeros productos
    if not query or len(query.strip()) == 0:
        products = (
            db.query(Product)
            .filter(Product.activo == True)  # Solo productos activos
            .order_by(Product.nombre)  # Ordenar alfabéticamente
            .limit(limit)
            .all()
        )
    else:
        search_pattern = f"%{query}%"
        products = (
            db.query(Product)
            .filter(
                Product.nombre.ilike(search_pattern),
                Product.activo == True  # Solo productos activos
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
            "stock_disponible": p.stock_total if hasattr(p, 'stock_total') else None
        }
        for p in products
    ]

def search_orders_by_client_or_phone(
    db: Session,
    query: str,
    skip: int = 0,
    limit: int = 10
) -> List[Order]:
    """
    Busca órdenes por nombre de cliente o número de teléfono.

    Args:
        db: Sesión de base de datos
        query: Término de búsqueda (nombre o teléfono del cliente)
        skip: Número de registros a saltar
        limit: Número máximo de resultados

    Returns:
        Lista de órdenes que coinciden con la búsqueda
    """
    search_pattern = f"%{query}%"

    orders = (
        db.query(Order)
        .join(Customer, Order.cliente_id == Customer.id)
        .filter(
            or_(
                Customer.nombre.ilike(search_pattern),
                Customer.telefono.ilike(search_pattern)
            )
        )
        .order_by(Order.fecha_solicitud.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    logger.info(f"Found {len(orders)} orders matching query: {query}")
    return orders


def get_orders_by_date(
    db: Session,
    fecha: str
) -> List[Order]:
    """
    Obtiene órdenes NO asignadas de una fecha específica.
    Usado para el modal de crear ruta.

    Args:
        db: Sesión de base de datos
        fecha: Fecha en formato DD-MM-YYYY o YYYY-MM-DD (NO acepta slashes)

    Returns:
        Lista de órdenes NO asignadas de la fecha especificada

    Raises:
        ValueError: Si el formato de fecha es inválido o contiene slashes
    """
    from sqlalchemy import cast, Date
    from src.utils.date_parser import parse_date_flexible

    # No permitir slashes en este contexto (para URLs)
    fecha_obj = parse_date_flexible(fecha, allow_slashes=False)

    if fecha_obj is None:
        raise ValueError(
            "Formato de fecha inválido. Use DD-MM-YYYY o YYYY-MM-DD (sin slashes)"
        )

    fecha_date = fecha_obj.date()

    # Usar CAST para SQL Server (compatible con todos los DBs)
    orders = (
        db.query(Order)
        .join(Customer, Order.cliente_id == Customer.id)
        .join(Product, Order.producto_id == Product.id)
        .filter(
            cast(Order.fecha_solicitud, Date) == fecha_date,
            Order.asignada == False
        )
        .order_by(Order.prioridad.desc(), Order.fecha_solicitud)
        .all()
    )

    logger.info(f"Found {len(orders)} unassigned orders for date {fecha_date}")
    return orders


def count_orders_by_date(db: Session, fecha: str) -> int:
    """
    Cuenta órdenes de una fecha específica.

    Args:
        db: Sesión de base de datos
        fecha: Fecha en formato DD/MM/YYYY, DD-MM-YYYY, o YYYY-MM-DD

    Returns:
        Número de órdenes en la fecha
    """
    from src.utils.date_parser import parse_date_flexible

    fecha_obj = parse_date_flexible(fecha)
    if fecha_obj is None:
        return 0

    fecha_date = fecha_obj.date()

    return (
        db.query(func.count(Order.id))
        .filter(func.date(Order.fecha_solicitud) == fecha_date)
        .scalar()
    )


def count_search_results(db: Session, query: str) -> int:
    """Cuenta el total de resultados de búsqueda"""
    search_pattern = f"%{query}%"
    return (
        db.query(func.count(Order.id))
        .join(Customer, Order.cliente_id == Customer.id)
        .filter(
            or_(
                Customer.nombre.ilike(search_pattern),
                Customer.telefono.ilike(search_pattern)
            )
        )
        .scalar()
    )


def get_unassigned_orders_by_cliente(
    db: Session,
    cliente_ids: List[int]
) -> dict:
    """
    Obtiene órdenes pendientes agrupadas por cliente.
    Útil para el modal de crear ruta.
    """
    orders = (
        db.query(Order)
        .filter(
            Order.cliente_id.in_(cliente_ids),
            Order.asignada == False
        )
        .all()
    )

    # Agrupar por cliente
    orders_by_cliente = {}
    for order in orders:
        if order.cliente_id not in orders_by_cliente:
            orders_by_cliente[order.cliente_id] = []

        orders_by_cliente[order.cliente_id].append({
            "orden_id": order.id,
            "producto_id": order.producto_id,
            "producto_nombre": order.producto.nombre,
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


def import_orders_from_excel(
    file,
    db: Session,
) -> Tuple[List[Order], List[dict], List[dict]]:
    """
    Importa órdenes desde un archivo Excel.

    Returns:
        Tupla con (órdenes_creadas, errores_validación, errores_db)
    """
    required_columns = ['cliente_id', 'producto_id', 'cantidad']

    try:
        # 1. Leer Excel
        df = read_excel(file, required_columns=required_columns)
        logger.info(f"Excel file read successfully. Found {len(df)} rows")

        # 2. Convertir a modelos Pydantic y validar
        items, validation_errors = convert_to_model_list(
            df,
            model=OrderCreate,
            clean_data=True
        )

        if validation_errors:
            logger.warning(f"Found {len(validation_errors)} validation errors in Excel")

        # 3. Si hay errores de validación, retornar sin crear órdenes
        if validation_errors:
            return [], validation_errors, []

        # 4. Intentar crear órdenes en la base de datos
        created_orders = []
        db_errors = []

        for idx, item in enumerate(items):
            row_number = idx + 2  # +2 por header y índice base 0

            assert isinstance(item, OrderCreate)

            try:
                # Verificar que el cliente existe
                customer = db.query(Customer).filter(Customer.id == item.cliente_id).first()
                if not customer:
                    db_errors.append({
                        "row": row_number,
                        "error": f"Cliente con ID {item.cliente_id} no existe",
                        "data": {
                            "cliente_id": item.cliente_id,
                            "producto_id": item.producto_id,
                            "cantidad": item.cantidad
                        }
                    })
                    continue

                # Verificar que el producto existe
                product = db.query(Product).filter(Product.id == item.producto_id).first()
                if not product:
                    db_errors.append({
                        "row": row_number,
                        "error": f"Producto con ID {item.producto_id} no existe",
                        "data": {
                            "cliente_id": item.cliente_id,
                            "producto_id": item.producto_id,
                            "cantidad": item.cantidad
                        }
                    })
                    continue

                order = create_order(db, item)
                created_orders.append(order)
                logger.info(f"Order created: ID {order.id} for customer {item.cliente_id}")

            except ValueError as ve:
                db.rollback()
                db_errors.append({
                    "row": row_number,
                    "error": f"Error de validación: {str(ve)}",
                    "data": {
                        "cliente_id": item.cliente_id,
                        "producto_id": item.producto_id,
                        "cantidad": item.cantidad
                    }
                })
                logger.warning(f"Validation error at row {row_number}: {str(ve)}")

            except Exception as e:
                db.rollback()
                db_errors.append({
                    "row": row_number,
                    "error": f"Error inesperado: {str(e)}",
                    "data": {
                        "cliente_id": item.cliente_id,
                        "producto_id": item.producto_id,
                        "cantidad": item.cantidad
                    }
                })
                logger.error(f"Unexpected error creating order at row {row_number}: {str(e)}")

        logger.info(f"Import completed. Created: {len(created_orders)}, DB Errors: {len(db_errors)}")
        return created_orders, [], db_errors

    except ExcelImportError as e:
        logger.error(f"Excel import error: {str(e)}")
        raise
    except Exception as e:
        logger.exception(f"Unexpected error during Excel import: {str(e)}")
        raise Exception(f"Error procesando el archivo Excel: {str(e)}")


def export_orders_to_excel(db: Session) -> bytes:
    """Exporta todas las órdenes a Excel."""
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
                data.append({
                    "id": order.id,
                    "cliente_nombre": safe_title(order.cliente.nombre),
                    "cliente_direccion": safe_title(order.cliente.direccion),
                    "producto_nombre": safe_title(get_product_display_name_from_order(order)),
                    "cantidad": order.cantidad,
                    "fecha_solicitud": parse_date_string(order.fecha_solicitud)
                })

            logger.info(f"Exporting {len(orders)} orders to Excel")

        excel_file = export_to_excel(
            data=data,
            filename="ordenes.xlsx",
            sheet_name="Ordenes"
        )

        return excel_file.getvalue()

    except Exception as e:
        logger.exception(f"Error exporting orders to Excel: {str(e)}")
        raise Exception(f"Error al exportar órdenes a Excel: {str(e)}")


def export_orders_to_pdf(db: Session) -> bytes:
    """Exporta todas las órdenes a PDF."""
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
                data.append({
                    "id": order.id,
                    "Cliente": safe_title(order.cliente.nombre),
                    "Direccion": safe_title(order.cliente.direccion),
                    "Producto": safe_title(get_product_display_name_from_order(order)),
                    "Cantidad": order.cantidad,
                    "Fecha Solicitud": parse_date_string(order.fecha_solicitud)
                })

            logger.info(f"Exporting {len(orders)} orders to PDF")

        col_widths = [40.0, 100.0, 120.0, 100.0, 60.0, 90.0]

        generator = PDFReportGenerator(
            title="REPORTE DE ÓRDENES",
            page_size=letter,
            author="Sistema",
            subject="reporte_ordenes.pdf"
        )

        pdf_bytes = generator.generate(
            headers=["ID", "Cliente", "Direccion", "Producto", "Cantidad", "Fecha Solicitud"],
            data=data,
            col_widths=col_widths
        )

        return pdf_bytes

    except Exception as e:
        logger.exception(f"Error exporting orders to PDF: {str(e)}")
        raise Exception(f"Error al exportar órdenes a PDF: {str(e)}")
