"""
Generador de PDFs específico para reportes de rutas.
"""
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, PageBreak, KeepTogether
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from io import BytesIO
from datetime import datetime
from typing import Dict, Any, List
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


class RoutePDFGenerator:
    """Generador de PDF especializado para reportes de rutas."""

    def __init__(self, route_data: Dict[str, Any]):
        """
        Args:
            route_data: Datos completos de la ruta (del servicio financiero)
        """
        self.route_data = route_data
        self.buffer = BytesIO()
        self.page_size = letter

    def _create_styles(self):
        """Crea estilos personalizados para el documento."""
        styles = getSampleStyleSheet()

        # Título principal
        styles.add(ParagraphStyle(
            name='RouteTitle',
            parent=styles['Heading1'],
            fontSize=20,
            textColor=colors.HexColor('#1a1a1a'),
            spaceAfter=10,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        ))

        # Subtítulo
        styles.add(ParagraphStyle(
            name='RouteSubtitle',
            parent=styles['Normal'],
            fontSize=11,
            textColor=colors.HexColor('#666666'),
            spaceAfter=20,
            alignment=TA_CENTER
        ))

        # Encabezado de sección
        styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#2c3e50'),
            spaceAfter=12,
            spaceBefore=20,
            fontName='Helvetica-Bold',
            borderPadding=5,
            leftIndent=0
        ))

        # Texto normal para celdas
        styles.add(ParagraphStyle(
            name='CellText',
            parent=styles['Normal'],
            fontSize=9,
            alignment=TA_CENTER,
            leading=11
        ))

        # Texto para valores destacados
        styles.add(ParagraphStyle(
            name='HighlightValue',
            parent=styles['Normal'],
            fontSize=12,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor('#2c3e50')
        ))

        return styles

    def _format_currency(self, value: float) -> str:
        """Formatea valores monetarios."""
        return f"Q {value:,.2f}"

    def _create_header(self, styles) -> List:
        """Crea el encabezado del reporte."""
        elements = []

        # Título
        title = f"REPORTE DE RUTA: {self.route_data['ruta_nombre'].upper()}"
        elements.append(Paragraph(title, styles['RouteTitle']))

        # Información básica
        fecha = self.route_data['fecha']
        estado = self.route_data['estado'].upper()
        fecha_generacion = datetime.now().strftime("%d/%m/%Y %H:%M")

        subtitle = f"Fecha de Ruta: {fecha} | Estado: {estado}<br/>Generado: {fecha_generacion}"
        elements.append(Paragraph(subtitle, styles['RouteSubtitle']))
        elements.append(Spacer(1, 0.3 * inch))

        return elements

    def _create_summary_boxes(self, styles) -> List:
        """Crea cajas de resumen con métricas clave."""
        elements = []

        resumen = self.route_data['resumen_financiero']
        clientes = self.route_data['resumen_clientes']
        inventario = self.route_data['resumen_inventario']

        # Datos para la tabla de resumen
        data = [
            # Encabezados
            ['RESUMEN FINANCIERO', 'CLIENTES', 'INVENTARIO'],
            # Valores
            [
                Paragraph(
                    f"<b>Total Esperado:</b><br/>{self._format_currency(resumen['total_esperado'])}<br/><br/>"
                    f"<b>Total Entregado:</b><br/>{self._format_currency(resumen['total_entregado'])}<br/><br/>"
                    f"<b>Pérdida:</b><br/>{self._format_currency(resumen['perdida'])}<br/><br/>"
                    f"<b>Efectividad:</b><br/>{resumen['porcentaje_cobrado']}%",
                    styles['CellText']
                ),
                Paragraph(
                    f"<b>Total:</b><br/>{clientes['total_clientes']}<br/><br/>"
                    f"<b>Entregados:</b><br/>{clientes['clientes_entregados']}<br/><br/>"
                    f"<b>No Entregados:</b><br/>{clientes['clientes_no_entregados']}<br/><br/>"
                    f"<b>Conversión:</b><br/>{clientes['tasa_conversion']}%",
                    styles['CellText']
                ),
                Paragraph(
                    f"<b>Cargadas:</b><br/>{inventario['total_unidades_cargadas']} unidades<br/><br/>"
                    f"<b>Entregadas:</b><br/>{inventario['total_unidades_entregadas']} unidades<br/><br/>"
                    f"<b>Devueltas:</b><br/>{inventario['total_unidades_devueltas']} unidades<br/><br/>"
                    f"<b>% Vendido:</b><br/>{inventario['porcentaje_vendido']}%",
                    styles['CellText']
                )
            ]
        ]

        # Crear tabla
        table = Table(data, colWidths=[2.3*inch, 2.3*inch, 2.3*inch])
        table.setStyle(TableStyle([
            # Encabezados
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#10367d')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('TOPPADDING', (0, 0), (-1, 0), 12),

            # Cuerpo
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
            ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 1), (-1, -1), 'TOP'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('TOPPADDING', (0, 1), (-1, -1), 15),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 15),
            ('LEFTPADDING', (0, 1), (-1, -1), 10),
            ('RIGHTPADDING', (0, 1), (-1, -1), 10),

            # Bordes
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('BOX', (0, 0), (-1, -1), 2, colors.HexColor('#2c3e50'))
        ]))

        elements.append(table)
        elements.append(Spacer(1, 0.4 * inch))

        return elements

    def _format_estado(self, estado: str) -> str:
        """Formatea estados para mostrar en PDF."""
        estados_map = {
            'entregado': 'ENTREGADO',
            'no_entregado': 'NO ENTREGADO',
            'pendiente': 'PENDIENTE',
            'en_proceso': 'EN PROCESO',
            'completada': 'COMPLETADA'
        }
        return estados_map.get(estado, estado.replace('_', ' ').upper())

    def _create_clients_table(self, styles) -> List:
        """Crea tabla detallada de clientes."""
        elements = []

        # Encabezado de sección
        section_header = Paragraph("DETALLE POR CLIENTE", styles['SectionHeader'])
        elements.append(section_header)
        elements.append(Spacer(1, 0.1 * inch))

        # Datos
        clientes = self.route_data['clientes']

        # Encabezados
        headers = ['Cliente', 'Estado', 'Esperado', 'Entregado', 'Diferencia']

        # Filas
        rows = [headers]
        for cliente in clientes:
            esperado = cliente['subtotal_esperado']
            entregado = cliente['subtotal_entregado']
            diferencia = esperado - entregado

            # Determinar color del estado
            if cliente['estado_entrega'] == 'entregado':
                estado_color = 'green'
            else:
                estado_color = 'red'

            estado_formateado = self._format_estado(cliente['estado_entrega'])

            rows.append([
                Paragraph(cliente['cliente_nombre'], styles['CellText']),
                Paragraph(
                    f'<font color="{estado_color}"><b>{estado_formateado}</b></font>',
                    styles['CellText']
                ),
                Paragraph(self._format_currency(esperado), styles['CellText']),
                Paragraph(self._format_currency(entregado), styles['CellText']),
                Paragraph(
                    f'<font color="red">{self._format_currency(diferencia)}</font>' if diferencia > 0
                    else self._format_currency(diferencia),
                    styles['CellText']
                )
            ])

        # Crear tabla
        table = Table(rows, colWidths=[2*inch, 1.3*inch, 1.3*inch, 1.3*inch, 1*inch])
        table.setStyle(TableStyle([
            # Encabezado
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#10367d')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('TOPPADDING', (0, 0), (-1, 0), 12),

            # Cuerpo
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('ALIGN', (0, 1), (-1, -1), 'CENTER'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('TOPPADDING', (0, 1), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 8),

            # Bordes y zebra
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')])
        ]))

        # Envolver tabla en KeepTogether para evitar cortes
        elements.append(KeepTogether(table))
        elements.append(Spacer(1, 0.3 * inch))

        return elements

    def _create_inventory_table(self, styles) -> List:
        """Crea tabla de inventario con manejo de páginas."""
        elements = []

        # Encabezado
        section_header = Paragraph("INVENTARIO DE PRODUCTOS", styles['SectionHeader'])

        # Datos
        productos = self.route_data['resumen_inventario']['productos']

        # Headers
        headers = ['Producto', 'Cargado', 'Entregado', 'Devuelto', '% Vendido']

        # Si hay muchos productos, dividir en tablas más pequeñas
        MAX_ROWS_PER_TABLE = 15  # Máximo de filas por tabla antes de hacer salto

        if len(productos) <= MAX_ROWS_PER_TABLE:
            # Si cabe en una sola tabla
            rows = [headers]
            for prod in productos:
                rows.append([
                    Paragraph(prod['producto_nombre'], styles['CellText']),
                    Paragraph(str(prod['cantidad_cargada']), styles['CellText']),
                    Paragraph(str(prod['cantidad_entregada']), styles['CellText']),
                    Paragraph(str(prod['cantidad_devuelta']), styles['CellText']),
                    Paragraph(f"{prod['porcentaje_vendido']}%", styles['CellText'])
                ])

            table = Table(rows, colWidths=[2.5*inch, 1*inch, 1*inch, 1*inch, 1.4*inch])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#10367d')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('TOPPADDING', (0, 0), (-1, 0), 12),

                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ('ALIGN', (0, 1), (-1, -1), 'CENTER'),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('TOPPADDING', (0, 1), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 8),

                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')])
            ]))

            # Mantener header y tabla juntos
            elements.append(KeepTogether([
                section_header,
                Spacer(1, 0.1 * inch),
                table
            ]))
        else:
            # Dividir en múltiples tablas
            elements.append(section_header)
            elements.append(Spacer(1, 0.1 * inch))

            for i in range(0, len(productos), MAX_ROWS_PER_TABLE):
                chunk = productos[i:i + MAX_ROWS_PER_TABLE]
                rows = [headers]

                for prod in chunk:
                    rows.append([
                        Paragraph(prod['producto_nombre'], styles['CellText']),
                        Paragraph(str(prod['cantidad_cargada']), styles['CellText']),
                        Paragraph(str(prod['cantidad_entregada']), styles['CellText']),
                        Paragraph(str(prod['cantidad_devuelta']), styles['CellText']),
                        Paragraph(f"{prod['porcentaje_vendido']}%", styles['CellText'])
                    ])

                table = Table(rows, colWidths=[2.5*inch, 1*inch, 1*inch, 1*inch, 1.4*inch])
                table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#10367d')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    ('TOPPADDING', (0, 0), (-1, 0), 12),

                    ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                    ('ALIGN', (0, 1), (-1, -1), 'CENTER'),
                    ('FONTSIZE', (0, 1), (-1, -1), 9),
                    ('TOPPADDING', (0, 1), (-1, -1), 8),
                    ('BOTTOMPADDING', (0, 1), (-1, -1), 8),

                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')])
                ]))

                elements.append(KeepTogether(table))

                # Si no es el último chunk, agregar salto de página
                if i + MAX_ROWS_PER_TABLE < len(productos):
                    elements.append(PageBreak())
                else:
                    elements.append(Spacer(1, 0.2 * inch))

        return elements

    def _create_footer(self, canvas, doc):
        """Pie de página."""
        canvas.saveState()
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

    def generate(self) -> bytes:
        """Genera el PDF completo."""
        try:
            # Crear documento
            doc = SimpleDocTemplate(
                self.buffer,
                pagesize=self.page_size,
                rightMargin=0.75*inch,
                leftMargin=0.75*inch,
                topMargin=0.75*inch,
                bottomMargin=0.75*inch,
                title=f"Reporte Ruta {self.route_data['ruta_nombre']}",
                author="Sistema DeliverIt"
            )

            elements = []
            styles = self._create_styles()

            # 1. Encabezado
            elements.extend(self._create_header(styles))

            # 2. Cajas de resumen
            elements.extend(self._create_summary_boxes(styles))

            # 3. Tabla de clientes
            elements.extend(self._create_clients_table(styles))

            # 4. Salto de página antes del inventario si es necesario
            # (opcional, pero ayuda a mantener el inventario en páginas limpias)
            if len(self.route_data['resumen_inventario']['productos']) > 10:
                elements.append(PageBreak())

            # 5. Tabla de inventario
            elements.extend(self._create_inventory_table(styles))

            # Construir PDF
            doc.build(
                elements,
                onFirstPage=self._create_footer,
                onLaterPages=self._create_footer
            )

            pdf_bytes = self.buffer.getvalue()
            self.buffer.close()

            logger.info(f"Route PDF generated: {self.route_data['ruta_nombre']}")
            return pdf_bytes

        except Exception as e:
            logger.exception(f"Error generating route PDF: {str(e)}")
            raise Exception(f"Error al generar PDF de ruta: {str(e)}")


def export_route_summary_to_pdf(route_data: Dict[str, Any]) -> bytes:
    """
    Función helper para exportar resumen de ruta a PDF.

    Args:
        route_data: Datos completos de la ruta (del servicio financiero)

    Returns:
        bytes: Contenido del PDF
    """
    generator = RoutePDFGenerator(route_data)
    return generator.generate()
