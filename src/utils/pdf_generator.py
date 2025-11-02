# pdf_generator.py - Agregar esta clase al archivo existente

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, PageBreak
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from io import BytesIO
from datetime import datetime
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class PDFReportOrder:
    """
    Generador de reportes PDF específico para órdenes con estadísticas.
    """

    def __init__(
        self,
        title: str,
        page_size=letter,
        author: str = "Sistema",
        subject: str = "Reporte"
    ):
        self.title = title
        self.page_size = page_size
        self.author = author
        self.subject = subject
        self.buffer = BytesIO()

        # Colores coordinados - tonalidades del azul principal
        self.primary_blue = colors.HexColor('#2e93d1')
        self.light_blue = colors.HexColor('#E3F2FD')
        self.medium_blue = colors.HexColor('#BBDEFB')
        self.header_blue = colors.HexColor('#1976D2')

        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    def _setup_custom_styles(self):
        """Configurar estilos personalizados."""
        # Título principal
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=22,
            textColor=self.primary_blue,
            spaceAfter=8,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        ))

        # Subtítulo
        self.styles.add(ParagraphStyle(
            name='CustomSubtitle',
            parent=self.styles['Normal'],
            fontSize=9,
            textColor=colors.grey,
            spaceAfter=20,
            alignment=TA_CENTER,
            fontName='Helvetica'
        ))

        # Título de sección
        self.styles.add(ParagraphStyle(
            name='SectionTitle',
            parent=self.styles['Normal'],
            fontSize=11,
            textColor=colors.HexColor('#424242'),
            spaceAfter=10,
            spaceBefore=5,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        ))

        # Estadística
        self.styles.add(ParagraphStyle(
            name='StatLabel',
            parent=self.styles['Normal'],
            fontSize=7,
            textColor=colors.grey,
            alignment=TA_CENTER,
            fontName='Helvetica',
            spaceAfter=2
        ))

        self.styles.add(ParagraphStyle(
            name='StatValue',
            parent=self.styles['Normal'],
            fontSize=18,
            textColor=self.primary_blue,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold',
            spaceBefore=2
        ))

        self.styles.add(ParagraphStyle(
            name='StatPercentage',
            parent=self.styles['Normal'],
            fontSize=11,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        ))

    def _create_stats_section(self, stats: Dict[str, Any]) -> List:
        """
        Crea una sección visual de estadísticas con diseño limpio.
        """
        elements = []

        # Título de estadísticas
        stats_title = Paragraph("RESUMEN ESTADÍSTICO", self.styles['SectionTitle'])
        elements.append(stats_title)
        elements.append(Spacer(1, 0.15 * inch))

        # Crear tabla de estadísticas con diseño mejorado
        stats_data = [
            # Encabezados
            [
                Paragraph("<b>TOTAL<br/>ÓRDENES</b>", self.styles['StatLabel']),
                Paragraph("<b>ÓRDENES<br/>ACTIVAS</b>", self.styles['StatLabel']),
                Paragraph("<b>ÓRDENES<br/>CANCELADAS</b>", self.styles['StatLabel']),
            ],
            # Valores
            [
                Paragraph(f"<b>{stats['total']}</b>", self.styles['StatValue']),
                Paragraph(f"<b>{stats['activas']}</b>", self.styles['StatValue']),
                Paragraph(f"<b>{stats['canceladas']}</b>", self.styles['StatValue']),
            ],
            # Porcentajes
            [
                "",  # Sin porcentaje para total
                Paragraph(
                    f"<font color='#059669'><b>{stats['porcentaje_activas']}%</b></font>",
                    self.styles['StatPercentage']
                ),
                Paragraph(
                    f"<font color='#dc2626'><b>{stats['porcentaje_canceladas']}%</b></font>",
                    self.styles['StatPercentage']
                ),
            ]
        ]

        stats_table = Table(stats_data, colWidths=[2.3*inch, 2.3*inch, 2.3*inch])
        stats_table.setStyle(TableStyle([
            # Fila de encabezados - tonos de azul
            ('BACKGROUND', (0, 0), (2, 0), self.light_blue),

            # Fila de valores
            ('BACKGROUND', (0, 1), (2, 1), colors.white),

            # Fila de porcentajes
            ('BACKGROUND', (0, 2), (2, 2), colors.white),

            # Bordes externos más marcados
            ('BOX', (0, 0), (-1, -1), 1.5, self.primary_blue),

            # Separadores verticales
            ('LINEAFTER', (0, 0), (0, -1), 1, self.medium_blue),
            ('LINEAFTER', (1, 0), (1, -1), 1, self.medium_blue),

            # Separadores horizontales
            ('LINEAFTER', (0, 0), (-1, 0), 1, self.medium_blue),
            ('LINEAFTER', (0, 1), (-1, 1), 1, self.medium_blue),

            # Alineación
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),

            # Padding
            ('TOPPADDING', (0, 0), (-1, 0), 8),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING', (0, 1), (-1, 1), 10),
            ('BOTTOMPADDING', (0, 1), (-1, 1), 4),
            ('TOPPADDING', (0, 2), (-1, 2), 4),
            ('BOTTOMPADDING', (0, 2), (-1, 2), 10),
        ]))

        elements.append(stats_table)
        elements.append(Spacer(1, 0.3 * inch))

        return elements

    def generate(
        self,
        headers: List[str],
        data: List[Dict[str, Any]],
        col_widths: Optional[List[float]] = None,
        stats: Optional[Dict[str, Any]] = None
    ) -> bytes:
        """
        Genera el PDF con los datos proporcionados.
        """
        try:
            # Usar landscape (horizontal) para mejor visualización de tablas anchas
            doc = SimpleDocTemplate(
                self.buffer,
                pagesize=landscape(letter),
                rightMargin=0.5 * inch,
                leftMargin=0.5 * inch,
                topMargin=0.6 * inch,
                bottomMargin=0.5 * inch,
                title=self.title,
                author=self.author,
                subject=self.subject
            )

            elements = []

            # Título
            title = Paragraph(self.title, self.styles['CustomTitle'])
            elements.append(title)

            # Fecha de generación
            fecha_generacion = datetime.now().strftime("%d/%m/%Y %H:%M")
            subtitle = Paragraph(
                f"Generado el {fecha_generacion}",
                self.styles['CustomSubtitle']
            )
            elements.append(subtitle)

            # 📊 Agregar estadísticas si se proporcionan
            if stats and stats.get('total', 0) > 0:
                elements.extend(self._create_stats_section(stats))

            # Preparar datos de la tabla
            if not data:
                no_data_msg = Paragraph(
                    "<i>No hay datos disponibles para mostrar.</i>",
                    self.styles['Normal']
                )
                elements.append(no_data_msg)
            else:
                table_data = [headers]

                for row in data:
                    table_row = []
                    for header in headers:
                        value = row.get(header, "")

                        # Formatear celdas especiales
                        if header == "Vigencia":
                            if value == "CANCELADA":
                                cell_value = Paragraph(
                                    f"<font color='#dc2626'><b>CANCELADA</b></font>",
                                    self.styles['Normal']
                                )
                            else:
                                cell_value = Paragraph(
                                    f"<font color='#059669'><b>Activa</b></font>",
                                    self.styles['Normal']
                                )
                        else:
                            # Limitar longitud de texto para evitar desbordamiento
                            str_value = str(value) if value is not None else ""
                            if len(str_value) > 50:
                                str_value = str_value[:47] + "..."
                            cell_value = str_value

                        table_row.append(cell_value)
                    table_data.append(table_row)

                # Ajustar anchos de columna si no se proporcionan
                if col_widths is None:
                    available_width = doc.width
                    col_widths = [available_width / len(headers)] * len(headers)

                table = Table(table_data, colWidths=col_widths, repeatRows=1)

                # Estilo de tabla con colores coordinados
                table.setStyle(TableStyle([
                    # Encabezado - usar el azul principal
                    ('BACKGROUND', (0, 0), (-1, 0), self.header_blue),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 9),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                    ('TOPPADDING', (0, 0), (-1, 0), 10),

                    # Cuerpo
                    ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
                    ('ALIGN', (0, 1), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 1), (-1, -1), 8),
                    ('TOPPADDING', (0, 1), (-1, -1), 7),
                    ('BOTTOMPADDING', (0, 1), (-1, -1), 7),

                    # Bordes
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                    ('BOX', (0, 0), (-1, -1), 1.5, self.primary_blue),

                    # Alternar colores de fila con tonos de azul suave
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, self.light_blue]),
                ]))

                elements.append(table)

            # Generar PDF
            doc.build(elements)
            pdf_bytes = self.buffer.getvalue()
            self.buffer.close()

            logger.info(f"PDF generated successfully: {len(pdf_bytes)} bytes")
            return pdf_bytes

        except Exception as e:
            logger.exception(f"Error generating PDF: {str(e)}")
            raise Exception(f"Error al generar PDF: {str(e)}")
