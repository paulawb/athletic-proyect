import io

import matplotlib

matplotlib.use("Agg")  # sin backend grafico: este proceso corre en un servidor sin pantalla
import matplotlib.pyplot as plt
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.domain.services.report_generator import AnalysisReportData, ReportGenerator

_BRAND_COLOR = colors.HexColor("#1e3a8a")


class PdfReportGenerator(ReportGenerator):
    """Primera implementacion de ReportGenerator (seccion 23): arma un PDF
    con reportlab -atleta, prueba, tabla de metricas, un grafico de
    velocidad durante la prueba, y si hay pruebas anteriores del mismo
    atleta, una tabla y un grafico de tendencia. La seccion 23 permitia
    dejar PDF para despues si complicaba la primera version; llegados a
    la Fase 11, con Metrics y FrameMetrics ya persistidos desde la Fase 7,
    se implementa completo.
    """

    def generate(self, report_data: AnalysisReportData) -> bytes:
        buffer = io.BytesIO()
        document = SimpleDocTemplate(
            buffer, pagesize=A4, topMargin=2 * cm, bottomMargin=2 * cm, leftMargin=2 * cm, rightMargin=2 * cm
        )
        styles = getSampleStyleSheet()
        story = []

        story.append(Paragraph("Informe de Análisis — Carrera de Velocidad", styles["Title"]))
        story.append(Spacer(1, 0.4 * cm))
        story.extend(self._build_header(report_data, styles))
        story.append(Spacer(1, 0.6 * cm))
        story.append(self._build_metrics_table(report_data))
        story.append(Spacer(1, 0.7 * cm))

        speed_chart = self._build_speed_chart(report_data)
        if speed_chart is not None:
            story.append(Paragraph("Velocidad durante la prueba", styles["Heading2"]))
            story.append(Spacer(1, 0.2 * cm))
            story.append(Image(speed_chart, width=16 * cm, height=6.5 * cm))
            story.append(Spacer(1, 0.7 * cm))

        if report_data.previous_tests:
            story.append(Paragraph("Comparación con pruebas anteriores", styles["Heading2"]))
            story.append(Spacer(1, 0.2 * cm))
            story.append(self._build_comparison_table(report_data))
            story.append(Spacer(1, 0.5 * cm))

            trend_chart = self._build_trend_chart(report_data)
            if trend_chart is not None:
                story.append(Image(trend_chart, width=16 * cm, height=6.5 * cm))

        document.build(story)
        return buffer.getvalue()

    @staticmethod
    def _build_header(report_data: AnalysisReportData, styles) -> list:
        date_label = report_data.test_date.strftime("%d/%m/%Y") if report_data.test_date else "-"
        return [
            Paragraph(
                f"<b>Atleta:</b> {report_data.athlete_full_name} "
                f"({report_data.athlete_identification})",
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
    def _build_metrics_table(report_data: AnalysisReportData) -> Table:
        metrics = report_data.metrics
        data = [
            ["Métrica", "Valor"],
            ["Velocidad promedio", f"{metrics.average_speed:.2f} m/s"],
            ["Velocidad máxima", f"{metrics.maximum_speed:.2f} m/s"],
            ["Longitud de zancada", f"{metrics.stride_length:.2f} m"],
            ["Cadencia", f"{metrics.cadence:.2f} pasos/s"],
            ["Postura", f"{metrics.posture_score:.1f} / 100"],
        ]
        table = Table(data, colWidths=[8 * cm, 6 * cm])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), _BRAND_COLOR),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
                ]
            )
        )
        return table

    @staticmethod
    def _build_comparison_table(report_data: AnalysisReportData) -> Table:
        data = [["Prueba", "Fecha", "Vel. promedio", "Cadencia", "Postura"]]
        for point in report_data.previous_tests:
            date_label = point.test_date.strftime("%d/%m/%Y") if point.test_date else "-"
            data.append(
                [
                    point.test_label,
                    date_label,
                    f"{point.average_speed:.2f} m/s",
                    f"{point.cadence:.2f} p/s",
                    f"{point.posture_score:.1f}",
                ]
            )
        table = Table(data, colWidths=[3.4 * cm, 3.2 * cm, 3.4 * cm, 3 * cm, 3 * cm])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), _BRAND_COLOR),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
                ]
            )
        )
        return table

    @staticmethod
    def _build_speed_chart(report_data: AnalysisReportData) -> io.BytesIO | None:
        if not report_data.frame_metrics:
            return None
        ordered = sorted(report_data.frame_metrics, key=lambda fm: fm.frame_number)
        timestamps = [fm.timestamp for fm in ordered]
        speeds = [fm.speed for fm in ordered]

        figure, axis = plt.subplots(figsize=(8, 3.2))
        axis.plot(timestamps, speeds, color="#1e3a8a", linewidth=1.5)
        axis.set_xlabel("Tiempo (s)")
        axis.set_ylabel("Velocidad (m/s)")
        axis.grid(True, alpha=0.3)
        figure.tight_layout()

        buffer = io.BytesIO()
        figure.savefig(buffer, format="png", dpi=150)
        plt.close(figure)
        buffer.seek(0)
        return buffer

    @staticmethod
    def _build_trend_chart(report_data: AnalysisReportData) -> io.BytesIO | None:
        points = report_data.previous_tests
        if not points:
            return None

        labels = [p.test_label for p in points]
        speeds = [p.average_speed for p in points]

        figure, axis = plt.subplots(figsize=(8, 3.2))
        axis.plot(labels, speeds, marker="o", color="#1e3a8a", linewidth=1.5)
        axis.set_ylabel("Velocidad promedio (m/s)")
        axis.set_title("Evolución de la velocidad promedio")
        axis.grid(True, alpha=0.3)
        figure.tight_layout()

        buffer = io.BytesIO()
        figure.savefig(buffer, format="png", dpi=150)
        plt.close(figure)
        buffer.seek(0)
        return buffer
