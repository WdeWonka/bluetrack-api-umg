"""
Utilidades para manejo de productos.
"""

def get_product_display_name_from_order(order) -> str:
    """
    Obtiene el nombre del producto para mostrar desde una orden.
    Prioriza el snapshot histórico sobre la relación.

    Args:
        order: Instancia de Order con producto_nombre_snapshot

    Returns:
        str: Nombre del producto para mostrar
    """
    # 1. Prioridad: snapshot (nombre cuando se creó la orden)
    if hasattr(order, 'producto_nombre_snapshot') and order.producto_nombre_snapshot:
        return order.producto_nombre_snapshot

    # 2. Fallback: relación con producto (puede estar eliminado)
    if hasattr(order, 'producto') and order.producto:
        nombre = order.producto.nombre
        # Si tiene prefijo de eliminado, limpiarlo
        if nombre.startswith("del_"):
            parts = nombre.split("_", 2)
            return parts[2] if len(parts) > 2 else "Producto eliminado"
        return nombre

    # 3. Último recurso
    return "Producto no disponible"


def get_product_display_name(product) -> str:
    """
    Obtiene el nombre del producto para mostrar desde un producto directo.
    Limpia nombres de productos soft-deleted.

    Args:
        product: Instancia de Product

    Returns:
        str: Nombre del producto para mostrar
    """
    if not product or not product.nombre:
        return "Producto no disponible"

    # Si tiene el prefijo de deleted, extraerlo
    if product.nombre.startswith("del_"):
        parts = product.nombre.split("_", 2)
        return parts[2] if len(parts) > 2 else "Producto eliminado"

    return product.nombre
