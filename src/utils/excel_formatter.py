# utils/excel_formatter.py
import pandas as pd
from io import BytesIO
from pydantic import BaseModel, ValidationError
from typing import List, Type, Tuple, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class ExcelImportError(Exception):
    """Error personalizado para reportar problemas en la importación de Excel."""
    pass


def read_excel(
    file, 
    required_columns: List[str],
    sheet_name: str | int = 0,
    skip_empty_rows: bool = True
) -> pd.DataFrame:
    """
    Lee un archivo Excel y devuelve solo las columnas necesarias.
    
    Args:
        file: UploadFile de FastAPI
        required_columns: lista de columnas obligatorias
        sheet_name: nombre o índice de la hoja a leer (default: primera hoja)
        skip_empty_rows: si True, elimina filas completamente vacías
    
    Returns:
        DataFrame con solo las columnas requeridas y limpio
    
    Raises:
        ExcelImportError: si faltan columnas obligatorias o el archivo es inválido
    """
    try:
        contents = file.file.read()
        
        # Leer Excel
        df = pd.read_excel(
            BytesIO(contents),
            sheet_name=sheet_name,
            dtype=str  # ← Leer todo como string primero (evita problemas de tipos)
        )
        
        # Limpiar nombres de columnas (quitar espacios)
        df.columns = df.columns.str.strip()
        
        # Eliminar filas completamente vacías
        if skip_empty_rows:
            df = df.dropna(how='all')
        
        # Verificar columnas requeridas
        missing = set(required_columns) - set(df.columns)
        if missing:
            raise ExcelImportError(
                f"Faltan columnas obligatorias: {', '.join(sorted(missing))}. "
                f"Columnas encontradas: {', '.join(sorted(df.columns))}"
            )
        
        # Resetear índice después de eliminar filas
        df = df.reset_index(drop=True)
        
        # Retornar solo las columnas necesarias
        return df[required_columns]
        
    except pd.errors.EmptyDataError:
        raise ExcelImportError("El archivo Excel está vacío")
    except Exception as e:
        if isinstance(e, ExcelImportError):
            raise
        raise ExcelImportError(f"Error al leer el archivo Excel: {str(e)}")


def convert_to_model_list(
    df: pd.DataFrame, 
    model: Type[BaseModel],
    clean_data: bool = True
) -> Tuple[List[BaseModel], List[dict]]:
    """
    Convierte un DataFrame a una lista de instancias Pydantic.
    
    Args:
        df: DataFrame con los datos
        model: Clase Pydantic a instanciar
        clean_data: si True, limpia espacios en strings
    
    Returns:
        Tuple[List[BaseModel], List[dict]]: 
            - lista de objetos válidos
            - lista de errores por fila (con detalles)
    """
    items: List[BaseModel] = []
    errors: List[dict] = []

    for idx, row in df.iterrows():
        # Convert idx to int early to avoid type issues
        row_number = int(idx) + 2 if isinstance(idx, (int, float)) else 0  # +2 por header y índice base 0
        row_dict = {}
        
        try:
            # Convertir fila a dict
            row_dict = row.to_dict()
            
            # Limpiar datos si es necesario
            if clean_data:
                row_dict = _clean_row_data(row_dict)
            
            # Instanciar modelo Pydantic (aquí se valida)
            item = model(**row_dict)
            items.append(item)
            
        except ValidationError as e:
            # Pydantic devuelve errores detallados
            error_details = []
            
            for error in e.errors():
                field = error['loc'][0] if error['loc'] else 'unknown'
                msg = error['msg']
                error_details.append(f"{field}: {msg}")
            
            errors.append({
                "row": row_number,
                "errors": error_details,
                "data": {k: str(v) for k, v in row_dict.items()}  # Para debug
            })
            
        except Exception as e:
            errors.append({
                "row": row_number,
                "errors": [f"Error inesperado: {str(e)}"],
                "data": {k: str(v) for k, v in (row_dict if row_dict else row.to_dict()).items()}
            })

    return items, errors


def _clean_row_data(row_dict: dict) -> dict:
    """
    Limpia datos de una fila (espacios, NaN, etc.)
    """
    cleaned = {}
    for key, value in row_dict.items():
        # Manejar NaN/None
        if pd.isna(value):
            cleaned[key] = None
        # Limpiar strings
        elif isinstance(value, str):
            cleaned[key] = value.strip()
        else:
            cleaned[key] = value
    
    return cleaned


def validate_no_duplicates(
    items: List[BaseModel], 
    unique_fields: List[str]
) -> List[dict]:
    """
    Valida que no haya duplicados dentro del archivo en los campos indicados.
    
    Args:
        items: lista de objetos Pydantic
        unique_fields: lista de campos que deben ser únicos
    
    Returns:
        Lista de errores si hay duplicados internos
    """
    errors = []
    seen = {field: {} for field in unique_fields}  # dict en vez de set para trackear filas
    
    for idx, item in enumerate(items):
        row_number = idx + 2
        
        for field in unique_fields:
            value = getattr(item, field, None)
            
            # Skip valores None/vacíos
            if value is None or (isinstance(value, str) and not value.strip()):
                continue
            
            # Normalizar para comparación
            normalized_value = value.lower() if isinstance(value, str) else value
            
            if normalized_value in seen[field]:
                first_occurrence = seen[field][normalized_value]
                errors.append({
                    "row": row_number,
                    "error": (
                        f"Duplicado en '{field}': '{value}' "
                        f"(ya apareció en fila {first_occurrence})"
                    )
                })
            else:
                seen[field][normalized_value] = row_number
    
    return errors


def export_to_excel(
    data: List[dict],
    filename: str = "export.xlsx",
    sheet_name: str = "Datos"
) -> BytesIO:
    """
    Exporta una lista de diccionarios a un archivo Excel en memoria.
    
    Args:
        data: lista de diccionarios con los datos
        filename: nombre sugerido para el archivo
        sheet_name: nombre de la hoja de Excel
    
    Returns:
        BytesIO con el contenido del Excel
    
    Example:
        excel_file = export_to_excel(
            data=[{"nombre": "Juan", "email": "juan@example.com"}],
            filename="usuarios.xlsx"
        )
        
        # En FastAPI:
        return Response(
            content=excel_file.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    """
    df = pd.DataFrame(data)
    
    output = BytesIO()
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name=sheet_name, index=False)
        
        # Auto-ajustar ancho de columnas (opcional pero útil)
        worksheet = writer.sheets[sheet_name]
        for idx, col in enumerate(df.columns):
            max_length = max(
                df[col].astype(str).map(len).max(),
                len(str(col))
            )
            worksheet.column_dimensions[chr(65 + idx)].width = min(max_length + 2, 50)
    
    output.seek(0)
    return output


def create_template_excel(
    columns: List[str],
    example_data: List[dict] | None = None,
    filename: str = "template.xlsx"
) -> BytesIO:
    """
    Crea un template de Excel con columnas específicas y opcionalmente datos de ejemplo.
    
    Args:
        columns: lista de nombres de columnas
        example_data: datos de ejemplo (opcional)
        filename: nombre sugerido del archivo
    
    Returns:
        BytesIO con el template
    
    Example:
        template = create_template_excel(
            columns=["nombre", "dpi", "email", "password"],
            example_data=[
                {"nombre": "Juan Pérez", "dpi": "1234567890123", 
                 "email": "juan@example.com", "password": "Admin123"}
            ]
        )
    """
    if example_data:
        df = pd.DataFrame(example_data)
    else:
        # Crear DataFrame vacío con las columnas
        df = pd.DataFrame(columns=columns)
    
    return export_to_excel(df.to_dict('records'), filename=filename)


