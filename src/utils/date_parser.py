from datetime import datetime, date
from typing import Optional
from typing import Union, Optional

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


def format_datetime_for_display(dt: Union[datetime, date, str, None]) -> str:
    """
    Formatea un datetime/date a string DD/MM/YYYY para display.

    Args:
        dt: datetime, date, string o None

    Returns:
        str: Fecha en formato DD/MM/YYYY o "Sin fecha"

    Examples:
        >>> format_datetime_for_display(datetime(2025, 11, 1))
        '01/11/2025'
        >>> format_datetime_for_display(date(2025, 11, 1))
        '01/11/2025'
        >>> format_datetime_for_display(None)
        'Sin fecha'
    """
    if dt is None:
        return "Sin fecha"

    try:
        if isinstance(dt, str):
            # Si ya es string, intentar parsearlo
            # Soporta varios formatos de entrada
            for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"]:
                try:
                    dt = datetime.strptime(dt, fmt)
                    break
                except ValueError:
                    continue

            if isinstance(dt, str):
                # Si no se pudo parsear, retornar tal cual
                return dt

        if isinstance(dt, datetime):
            return dt.strftime("%d/%m/%Y")
        elif isinstance(dt, date):
            return dt.strftime("%d/%m/%Y")
        else:
            return str(dt)

    except Exception as e:
        logger.warning(f"Error formatting date {dt}: {e}")
        return "Fecha inválida"


def parse_date_string(dt: Union[datetime, date, str, None]) -> str:
    """
    Alias de format_datetime_for_display para compatibilidad.
    """
    return format_datetime_for_display(dt)

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
