from reportlab.lib import colors

from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from io import BytesIO
from datetime import datetime
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class PDFReportGenerator:
    """
    Generador genérico de reportes PDF con tabla de datos.

    Características:
    - Título del reporte
    - Fecha de generación
    - Tabla con datos
    - Estilos personalizables
    - Soporte para paginación automática
    """

    def __init__(
        self,
        title: str,
        page_size=letter,
        author: str = "Sistema",
        subject: str = "Reporte"
    ):
        """
        Inicializa el generador de PDFs.

        Args:
            title: Título principal del reporte
            page_size: Tamaño de página (letter, A4, etc.)
            author: Autor del documento
            subject: Asunto del documento
        """
        self.title = title
        self.page_size = page_size
        self.author = author
        self.subject = subject
        self.buffer = BytesIO()

    def _create_styles(self):
        """Crea los estilos para el documento"""
        styles = getSampleStyleSheet()

        # Estilo para el título principal
        styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#1a1a1a'),
            spaceAfter=30,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        ))

        # Estilo para subtítulos
        styles.add(ParagraphStyle(
            name='CustomSubtitle',
            parent=styles['Normal'],
            fontSize=12,
            textColor=colors.HexColor('#666666'),
            spaceAfter=20,
            alignment=TA_CENTER,
            fontName='Helvetica'
        ))

        return styles

    def _create_header(self, styles) -> List:
        """Crea el encabezado del reporte"""
        elements = []

        # Título
        title_text = Paragraph(self.title, styles['CustomTitle'])
        elements.append(title_text)

        # Fecha de generación
        fecha_generacion = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        subtitle = Paragraph(
            f"Fecha de generación: {fecha_generacion}",
            styles['CustomSubtitle']
        )
        elements.append(subtitle)
        elements.append(Spacer(1, 0.3 * inch))

        return elements

    def _create_table(
        self,
        headers: List[str],
        data: List[List[Any]],
        col_widths: Optional[List[float]] = None
    ) -> Table:
        """
        Crea una tabla formateada.

        Args:
            headers: Lista de encabezados de columna
            data: Lista de listas con los datos
            col_widths: Anchos personalizados para columnas (opcional)
        """
        # Preparar datos: headers + rows
        table_data = [headers] + data

        # Calcular anchos de columna si no se especifican
        if col_widths is None:
            available_width = self.page_size[0] - 2 * inch
            col_widths = [available_width / len(headers)] * len(headers)

        # Crear tabla
        table = Table(table_data, colWidths=col_widths, repeatRows=1)

        # Estilo de la tabla
        table.setStyle(TableStyle([
            # Estilo del encabezado
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#10367d")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('TOPPADDING', (0, 0), (-1, 0), 12),

            # Estilo del cuerpo
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
            ('ALIGN', (0, 1), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('TOPPADDING', (0, 1), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 8),

            ('WORDWRAP', (0, 0), (-1, -1), True),

            ('VALIGN', (0, 1), (-1, -1), 'MIDDLE'),

            # Líneas de la tabla
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            # ('LINEBELOW', (0, 0), (-1, 0), 2, colors.HexColor('#2c3e50')),

            # Alternar colores de fila
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')])
        ]))

        return table

    def _create_footer(self, canvas, doc):
        """Crea el pie de página con número de página"""
        canvas.saveState()

        # Información del pie de página
        page_num = canvas.getPageNumber()
        text = f"Página {page_num}"

        canvas.setFont('Helvetica', 9)
        canvas.setFillColor(colors.grey)
        canvas.drawCentredString(
            self.page_size[0] / 2.0,
            0.5 * inch,
            text
        )

        canvas.restoreState()

    def generate(
        self,
        headers: List[str],
        data: List[Dict[str, Any]],
        col_widths: Optional[List[float]] = None
    ) -> bytes:
        """
        Genera el PDF completo.

        Args:
            headers: Lista de encabezados de columna
            data: Lista de diccionarios con los datos
            col_widths: Anchos personalizados de columna (opcional)

        Returns:
            bytes: Contenido del PDF

        Example:
            generator = PDFReportGenerator(title="REPORTE DE USUARIOS")
            pdf_bytes = generator.generate(
                headers=["ID", "Nombre", "Email", "DPI"],
                data=[
                    {"id": 1, "nombre": "Juan", "email": "juan@mail.com", "dpi": "123..."},
                    {"id": 2, "nombre": "María", "email": "maria@mail.com", "dpi": "456..."}
                ]
            )
        """
        try:
            # Crear documento
            doc = SimpleDocTemplate(
            self.buffer,
            pagesize=self.page_size,
            rightMargin=inch,
            leftMargin=inch,
            topMargin=inch,
            bottomMargin=inch,
            title=self.title,
            author=self.author,
            subject=self.subject
        )

            # Elementos del documento
            elements = []
            styles = self._create_styles()

            # Agregar encabezado
            elements.extend(self._create_header(styles))

            cell_style = ParagraphStyle(
                'CellStyle',
                fontSize=9,
                fontName='Helvetica',
                leading=11,
                wordWrap='CJK',
                alignment=TA_CENTER
            )

            # Convertir diccionarios a lista de listas
            table_data = []
            for row in data:
                row_data = []
                for header in headers:
                    # Intentar diferentes formatos de key
                    key = header.lower().replace(' ', '_')
                    value = row.get(key, row.get(header, row.get(header.lower(), '')))

                    # Formatear valor
                    if value is None:
                        value = ''
                    elif isinstance(value, (int, float)):
                        value = str(value)
                    elif not isinstance(value, str):
                        value = str(value)

                    value = Paragraph(str(value), cell_style)

                    row_data.append(value)

                table_data.append(row_data)

            # Si no hay datos, agregar mensaje
            if not table_data:
                empty_msg = Paragraph("No hay datos disponibles", cell_style)
                table_data = [[empty_msg] + [Paragraph("", cell_style)] * (len(headers) - 1)]

            # Agregar tabla
            table = self._create_table(headers, table_data, col_widths)
            elements.append(table)

            # Agregar espacio al final
            elements.append(Spacer(1, 0.5 * inch))

            # Construir PDF con pie de página
            doc.build(elements, onFirstPage=self._create_footer, onLaterPages=self._create_footer)

            # Retornar bytes
            pdf_bytes = self.buffer.getvalue()
            self.buffer.close()

            logger.info(f"PDF generated successfully: {self.title}")
            return pdf_bytes
        except Exception as e:
            logger.exception(f"Error generating PDF: {str(e)}")
            raise Exception(f"Error al generar el PDF: {str(e)}")

def generate_simple_report(
    title: str,
    headers: List[str],
    data: List[Dict[str, Any]],
    filename: str = "reporte.pdf"
) -> bytes:
    """
    Función helper para generar reportes simples rápidamente.

    Args:
        title: Título del reporte
        headers: Encabezados de la tabla
        data: Datos a incluir
        filename: Nombre sugerido del archivo

    Returns:
        bytes: Contenido del PDF

    Example:
        pdf = generate_simple_report(
            title="REPORTE DE VENDEDORES",
            headers=["Nombre", "Email", "DPI"],
            data=[{"nombre": "Juan", "email": "juan@mail.com", "dpi": "123..."}]
        )
    """
    generator = PDFReportGenerator(
        title=title.upper(),
        page_size=letter,
        author="Sistema",
        subject=filename
    )

    return generator.generate(headers=headers, data=data)
