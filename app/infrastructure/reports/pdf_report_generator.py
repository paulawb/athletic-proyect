import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.core.timezone import format_local
from app.domain.services.report_generator import AnalysisReportData, ReportGenerator

_BRAND_COLOR = colors.HexColor("#1e3a8a")


def _table_style(header: bool = True) -> TableStyle:
    commands = [
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
    ]
    if header:
        commands += [
            ("BACKGROUND", (0, 0), (-1, 0), _BRAND_COLOR),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ]
    return TableStyle(commands)


class PdfReportGenerator(ReportGenerator):
    """Informe en PDF de un analisis: datos del atleta y de la prueba, las
    variables medidas por el software y, si hay pruebas anteriores del mismo
    atleta, una tabla comparativa. Solo contiene valores medidos, sin graficas.
    """

    def generate(self, report_data: AnalysisReportData) -> bytes:
        buffer = io.BytesIO()
        document = SimpleDocTemplate(
            buffer, pagesize=A4, topMargin=2 * cm, bottomMargin=2 * cm, leftMargin=2 * cm, rightMargin=2 * cm
        )
        styles = getSampleStyleSheet()
        story = [
            Paragraph("Informe de Análisis — Carrera de Velocidad", styles["Title"]),
            Spacer(1, 0.4 * cm),
            *self._build_header(report_data, styles),
            Spacer(1, 0.6 * cm),
            Paragraph("Variables medidas", styles["Heading2"]),
            Spacer(1, 0.2 * cm),
            self._build_metrics_table(report_data),
        ]

        if report_data.previous_tests:
            story.append(Spacer(1, 0.7 * cm))
            story.append(Paragraph("Comparación con pruebas anteriores", styles["Heading2"]))
            story.append(Spacer(1, 0.2 * cm))
            story.append(self._build_comparison_table(report_data))

        story.append(Spacer(1, 0.7 * cm))
        story.append(
            Paragraph(
                "Para conocer qué significa cada variable y cómo se calcula, descarga el "
                "glosario de variables del análisis.",
                styles["Italic"],
            )
        )

        document.build(story)
        return buffer.getvalue()

    @staticmethod
    def _build_header(report_data: AnalysisReportData, styles) -> list:
        date_label = format_local(report_data.test_date, report_data.timezone_name)
        return [
            Paragraph(
                f"<b>Atleta:</b> {report_data.athlete_full_name} ({report_data.athlete_identification})",
                styles["Normal"],
            ),
            Paragraph(f"<b>Fecha de la prueba:</b> {date_label}", styles["Normal"]),
            Paragraph(
                f"<b>Prueba:</b> {report_data.test_label} — {report_data.test_type} — "
                f"{report_data.technique} — {report_data.test_distance} m",
                styles["Normal"],
            ),
            Paragraph(f"<b>Video:</b> {report_data.video_filename}", styles["Normal"]),
        ]

    @staticmethod
    def _detection_coverage(report_data: AnalysisReportData) -> str | None:
        frames = report_data.frame_metrics
        if not frames or all(frame.keypoints is None for frame in frames):
            return None
        detected = sum(1 for frame in frames if frame.keypoints)
        return f"{detected / len(frames) * 100:.1f} % ({detected} de {len(frames)} cuadros)"

    def _build_metrics_table(self, report_data: AnalysisReportData) -> Table:
        metrics = report_data.metrics
        data = [
            ["Variable", "Valor"],
            ["Velocidad promedio", f"{metrics.average_speed:.2f} m/s"],
            ["Velocidad máxima", f"{metrics.maximum_speed:.2f} m/s"],
            ["Longitud de zancada", f"{metrics.stride_length:.2f} m"],
            ["Cadencia", f"{metrics.cadence:.2f} pasos/s"],
            ["Postura", f"{metrics.posture_score:.1f} %"],
        ]
        coverage = self._detection_coverage(report_data)
        if coverage:
            data.append(["Cuadros con detección del atleta", coverage])
        table = Table(data, colWidths=[8 * cm, 8 * cm])
        table.setStyle(_table_style())
        return table

    @staticmethod
    def _build_comparison_table(report_data: AnalysisReportData) -> Table:
        data = [["Prueba", "Fecha", "Vel. promedio", "Zancada", "Cadencia", "Postura"]]
        for point in report_data.previous_tests:
            date_label = format_local(point.test_date, report_data.timezone_name)
            data.append(
                [
                    point.test_label,
                    date_label,
                    f"{point.average_speed:.2f} m/s",
                    f"{point.stride_length:.2f} m",
                    f"{point.cadence:.2f} p/s",
                    f"{point.posture_score:.1f} %",
                ]
            )
        table = Table(data, colWidths=[3 * cm, 2.8 * cm, 3 * cm, 2.6 * cm, 2.6 * cm, 2.4 * cm])
        table.setStyle(_table_style())
        return table
