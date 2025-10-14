# utils/type_converters.py
from decimal import Decimal
from typing import Any, Optional, Union


def decimal_to_float(value: Any) -> Optional[float]:
    """
    Convierte un valor Decimal a float de forma segura.

    Args:
        value: Valor Decimal, Column[Decimal], o None

    Returns:
        float si el valor existe, None si es None

    Example:
        >>> decimal_to_float(Decimal("14.634915"))
        14.634915
        >>> decimal_to_float(None)
        None
    """
    if value is None:
        return None
    return float(value)


def decimal_to_str(value: Any) -> str:
    """
    Convierte un valor Decimal a string de forma segura.

    Args:
        value: Valor Decimal, Column[Decimal], o None

    Returns:
        string representando el número, o "" si es None

    Example:
        >>> decimal_to_str(Decimal("14.634915"))
        "14.634915"
        >>> decimal_to_str(None)
        ""
    """
    if value is None:
        return ""
    return str(value)


def safe_str(value: Any, default: str = "") -> str:
    """
    Convierte cualquier valor a string de forma segura.

    Args:
        value: Cualquier valor
        default: Valor por defecto si es None

    Returns:
        string del valor o default

    Example:
        >>> safe_str("hello")
        "hello"
        >>> safe_str(None)
        ""
        >>> safe_str(None, "N/A")
        "N/A"
    """
    if value is None:
        return default
    return str(value)


def safe_title(value: Any) -> str:
    """
    Capitaliza un string de forma segura.

    Args:
        value: String, Column[str], o None

    Returns:
        String capitalizado o ""

    Example:
        >>> safe_title("juan pérez")
        "Juan Pérez"
        >>> safe_title(None)
        ""
    """
    if not value:
        return ""
    return str(value).title()


def safe_capitalize(value: Any) -> str:
    """
    Capitaliza solo la primera letra de forma segura.

    Args:
        value: String, Column[str], o None

    Returns:
        String con primera letra mayúscula o ""

    Example:
        >>> safe_capitalize("vendedor")
        "Vendedor"
        >>> safe_capitalize(None)
        ""
    """
    if not value:
        return ""
    return str(value).capitalize()


def format_phone_gt(phone: Any, format_type: str = "display") -> str:
    """
    Formatea un número de teléfono de Guatemala.

    Args:
        phone: Número de teléfono (string o int)
        format_type: Tipo de formato
            - "display": Para mostrar en PDF/UI (ej: "2367-1234" o "4456-7890")
            - "storage": Para almacenar en DB (sin guiones, ej: "23671234")

    Returns:
        String del teléfono formateado

    Example:
        >>> format_phone_gt("23671234", "display")
        "2367-1234"
        >>> format_phone_gt("44567890", "display")
        "4456-7890"
        >>> format_phone_gt("2367-1234", "storage")
        "23671234"
        >>> format_phone_gt(None)
        ""
    """
    if not phone:
        return ""

    # Limpiar el teléfono (remover espacios, guiones, paréntesis)
    clean_phone = str(phone).replace("-", "").replace(" ", "").replace("(", "").replace(")", "")

    # Validar que solo contenga números
    if not clean_phone.isdigit():
        return str(phone)  # Retornar original si no es válido

    # Si es para almacenamiento, retornar sin formato
    if format_type == "storage":
        return clean_phone

    # Para display, formatear con guión
    if len(clean_phone) == 8:
        # Formato: XXXX-XXXX
        return f"{clean_phone[:4]}-{clean_phone[4:]}"
    elif len(clean_phone) == 11 and clean_phone.startswith("502"):
        # Formato internacional: +502 XXXX-XXXX
        return f"+502 {clean_phone[3:7]}-{clean_phone[7:]}"
    else:
        # Si no coincide con formato conocido, retornar limpio
        return clean_phone


def model_to_json_dict(obj: Any, decimal_fields: Optional[list[str]] = None) -> dict:
    """
    Convierte un modelo SQLAlchemy a dict serializable a JSON.
    Maneja automáticamente campos Decimal.

    Args:
        obj: Objeto del modelo SQLAlchemy
        decimal_fields: Lista de nombres de campos que son Decimal (opcional)

    Returns:
        Diccionario serializable a JSON

    Example:
        >>> warehouse = Warehouse(nombre="Central", latitud=Decimal("14.5"))
        >>> model_to_json_dict(warehouse, decimal_fields=["latitud", "longitud"])
        {"nombre": "Central", "latitud": 14.5, ...}
    """
    result = {}
    decimal_fields = decimal_fields or []

    # Obtener todos los atributos del modelo
    for column in obj.__table__.columns:
        field_name = column.name
        value = getattr(obj, field_name, None)

        # Convertir Decimals a float
        if field_name in decimal_fields and isinstance(value, Decimal):
            result[field_name] = decimal_to_float(value)
        else:
            result[field_name] = value

    return result
