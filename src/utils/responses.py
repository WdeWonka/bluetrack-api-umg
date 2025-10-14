# src/utils/responses.py
"""
Utilidades para respuestas estandarizadas.
"""
from typing import Any, Optional
from fastapi.responses import JSONResponse

def success_response(
    data: Any,
    message: str = "Operación exitosa",
    status_code: int = 200
) -> JSONResponse:
    """Respuesta exitosa estandarizada."""
    return JSONResponse(
        status_code=status_code,
        content={
            "success": True,
            "message": message,
            "data": data
        }
    )


def error_response(
    message: str,
    errors: Optional[Any] = None,
    status_code: int = 400
) -> JSONResponse:
    """Respuesta de error estandarizada."""
    content = {
        "success": False,
        "message": message
    }

    if errors:
        content["errors"] = errors

    return JSONResponse(
        status_code=status_code,
        content=content
    )
