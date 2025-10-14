from datetime import datetime
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def parse_date_flexible(date_str: str, allow_slashes: bool = True) -> Optional[datetime]:
    """
    Parsea fecha en múltiples formatos comunes.

    Formatos soportados:
    - DD-MM-YYYY (08-10-2025)
    - YYYY-MM-DD (2025-10-08) - ISO format
    - DD/MM/YYYY (08/10/2025) - Solo si allow_slashes=True
    - DD/MM/YY (08/10/25) - Solo si allow_slashes=True

    Args:
        date_str: String con la fecha
        allow_slashes: Si False, no acepta formatos con /

    Returns:
        datetime object o None si no se pudo parsear
    """
    if isinstance(date_str, datetime):
        return date_str

    if not isinstance(date_str, str):
        return None

    # Formatos sin slashes (siempre permitidos)
    formats_no_slash = [
        "%d-%m-%Y",  # 08-10-2025
        "%Y-%m-%d",  # 2025-10-08 (ISO)
        "%d-%m-%y",  # 08-10-25
    ]

    # Formatos con slashes (opcionales)
    formats_with_slash = [
        "%d/%m/%Y",  # 08/10/2025
        "%d/%m/%y",  # 08/10/25
    ]

    # Intentar formatos sin slash primero
    for fmt in formats_no_slash:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue

    # Intentar formatos con slash solo si están permitidos
    if allow_slashes:
        for fmt in formats_with_slash:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue

    logger.warning(f"Could not parse date: {date_str}")
    return None


def format_date_for_display(date_obj: datetime) -> str:
    """
    Formatea fecha para mostrar en formato DD/MM/YYYY

    Args:
        date_obj: objeto datetime

    Returns:
        String en formato DD/MM/YYYY
    """
    if date_obj is None:
        return ""
    return date_obj.strftime("%d/%m/%Y")

def parse_date_string(date_str: str, allow_slashes: bool = True) -> Optional[str]:
    """
    Parsea una fecha en múltiples formatos y la devuelve como string 'dd/mm/yyyy'
    sin incluir hora.
    """
    if isinstance(date_str, datetime):
        return date_str.strftime("%d/%m/%Y")

    if not isinstance(date_str, str):
        return None

    formats_no_slash = [
        "%d-%m-%Y",
        "%Y-%m-%d",
        "%d-%m-%y",
    ]

    formats_with_slash = [
        "%d/%m/%Y",
        "%d/%m/%y",
    ]

    # Intentar formatos sin slash
    for fmt in formats_no_slash:
        try:
            return datetime.strptime(date_str, fmt).strftime("%d/%m/%Y")
        except ValueError:
            continue

    # Intentar formatos con slash (si están permitidos)
    if allow_slashes:
        for fmt in formats_with_slash:
            try:
                return datetime.strptime(date_str, fmt).strftime("%d/%m/%Y")
            except ValueError:
                continue

    logger.warning(f"Could not parse date: {date_str}")
    return None

def format_datetime_for_display(datetime_obj: datetime) -> str:
    """
    Formatea fecha y hora para mostrar en formato DD/MM/YYYY HH:MM

    Args:
        datetime_obj: objeto datetime

    Returns:
        String en formato DD/MM/YYYY HH:MM
    """
    if datetime_obj is None:
        return ""
    return datetime_obj.strftime("%d/%m/%Y %H:%M")


def format_date_for_url(date_str: str) -> str:
    """
    Convierte una fecha con slashes a formato con guiones para URLs.

    Args:
        date_str: Fecha en formato DD/MM/YYYY

    Returns:
        Fecha en formato DD-MM-YYYY

    Example:
        >>> format_date_for_url("10/11/2025")
        "10-11-2025"
    """
    return date_str.replace('/', '-')
