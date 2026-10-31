import io
from dataclasses import dataclass

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

_BRAND_COLOR = colors.HexColor("#1e3a8a")


@dataclass(frozen=True)
class GlossaryContext:
    """Datos del analisis cuyos valores se muestran junto a cada definicion."""

    analysis_id: int
    athlete_code: str
    test_distance: float
    average_speed: float
    maximum_speed: float
    stride_length: float
    cadence: float
    posture_score: float
    detection_coverage: str | None = None


def _posture_level(score: float) -> str:
    if score >= 80:
        return "alta (postura adecuada durante casi toda la carrera)"
    if score >= 60:
        return "media (hay momentos con el tronco fuera de lo esperado)"
    return "baja (el tronco estuvo con frecuencia fuera de lo esperado)"


def _variables(context: GlossaryContext) -> list[dict[str, str]]:
    variables = [
        {
            "name": "Velocidad promedio",
            "unit": "m/s",
            "value": f"{context.average_speed:.2f} m/s ({context.average_speed * 3.6:.1f} km/h)",
            "meaning": "Qué tan rápido se desplazó el atleta mientras corría.",
            "how": (
                "Se sigue el punto medio de las caderas en cada cuadro del video. La velocidad de cada "
                "momento es la pendiente de la posición en una ventana de 0,2 s (esto elimina el temblor "
                "del detector). El promedio usa solo los cuadros en que el atleta se mueve (más de 0,5 m/s), "
                "así el tiempo de espera antes de la salida no baja el resultado."
            ),
            "read": "Mayor valor = atleta más rápido. Compárala con pruebas anteriores del mismo atleta.",
        },
        {
            "name": "Velocidad máxima",
            "unit": "m/s",
            "value": f"{context.maximum_speed:.2f} m/s ({context.maximum_speed * 3.6:.1f} km/h)",
            "meaning": "La mayor velocidad que alcanzó el atleta durante la prueba.",
            "how": "Es el valor más alto de la velocidad suavizada (la misma que se usa para el promedio).",
            "read": "Suele estar en la zona media o final de la carrera; indica la capacidad máxima del atleta.",
        },
        {
            "name": "Longitud de zancada",
            "unit": "m",
            "value": f"{context.stride_length:.2f} m",
            "meaning": "Distancia que avanza el atleta en un ciclo completo de carrera (dos pasos).",
            "how": (
                "Se detectan los apoyos de cada pie (el punto más bajo del tobillo en cada ciclo). La zancada "
                "es la distancia que recorre la cadera entre dos apoyos consecutivos del mismo pie, "
                "promediada para ambos pies. Vale 0 si no se detectaron al menos dos apoyos del mismo pie."
            ),
            "read": (
                "Zancada y cadencia se relacionan con la velocidad: velocidad ≈ cadencia × zancada ÷ 2. "
                "Una zancada más larga con la misma cadencia significa más velocidad."
            ),
        },
        {
            "name": "Cadencia",
            "unit": "pasos/s",
            "value": f"{context.cadence:.2f} pasos/s",
            "meaning": "Cuántos pasos da el atleta por segundo (cada apoyo de un pie cuenta como un paso).",
            "how": (
                "Se cuentan los apoyos de ambos pies entre el primer y el último detectado, y se dividen "
                "por el tiempo transcurrido entre ellos. Vale 0 si se detectaron menos de dos apoyos."
            ),
            "read": "Mayor cadencia = pasos más rápidos. En velocistas suele estar entre 4 y 5,5 pasos/s.",
        },
        {
            "name": "Postura",
            "unit": "%",
            "value": f"{context.posture_score:.1f} % — {_posture_level(context.posture_score)}",
            "meaning": "Qué tan cerca estuvo la inclinación del tronco de la inclinación esperada en cada momento.",
            "how": (
                "En cada cuadro se mide el ángulo entre la línea cadera-hombros y la vertical. En la salida se "
                "espera un tronco inclinado unos 45° y, a medida que el atleta gana velocidad, se va erguiendo "
                "hasta unos 10°. Cada cuadro recibe 100 % si está a 5° o menos de lo esperado, y baja "
                "linealmente hasta 0 % cuando está a 25° o más. El resultado es el promedio de los cuadros en "
                "movimiento."
            ),
            "read": (
                "Cerca de 100 % = tronco alineado con lo esperado. Es una referencia general de entrenamiento "
                "de velocidad, no un diagnóstico clínico."
            ),
        },
    ]
    if context.detection_coverage:
        variables.append(
            {
                "name": "Cuadros con detección del atleta",
                "unit": "%",
                "value": context.detection_coverage,
                "meaning": "Porcentaje de cuadros del video en los que el software encontró el cuerpo del atleta.",
                "how": (
                    "Se divide el número de cuadros con puntos corporales válidos entre el total de cuadros. "
                    "Un punto solo se acepta si el modelo lo ve con confianza de al menos 60 %."
                ),
                "read": "Mientras más alto, más confiables son todas las demás variables.",
            }
        )
    variables.extend(
        [
            {
                "name": "Velocidad actual (reproductor)",
                "unit": "m/s",
                "value": "Cambia en cada cuadro",
                "meaning": "La velocidad del atleta en el instante del video que se está viendo.",
                "how": "Es la velocidad suavizada de ese cuadro. Se muestra «—» si no se detectó al atleta.",
                "read": "Permite ver en qué momento acelera, mantiene o pierde velocidad.",
            },
            {
                "name": "Fase de la zancada (apoyo / vuelo)",
                "unit": "-",
                "value": "Cambia en cada cuadro",
                "meaning": "Apoyo: el cuadro donde un pie está en su punto más bajo. Vuelo: cualquier otro cuadro.",
                "how": "Se marca como apoyo cada cuadro donde se detectó un apoyo (ver Cadencia).",
                "read": "Es una aproximación visual; no mide el contacto real con el suelo.",
            },
            {
                "name": "Puntos corporales detectados",
                "unit": "puntos",
                "value": "Hasta 13 por cuadro",
                "meaning": "Nariz, hombros, codos, muñecas, caderas, rodillas y tobillos del atleta.",
                "how": (
                    "Los obtiene el modelo MediaPipe Pose Landmarker (versión Full) a partir de la imagen de "
                    "cada cuadro. Se descartan los puntos con baja confianza y los cuadros con una anatomía "
                    "imposible (por ejemplo, objetos del suelo)."
                ),
                "read": "Son el esqueleto que se dibuja sobre el video.",
            },
        ]
    )
    return variables


class GlossaryReportGenerator:
    """PDF aparte que explica cada variable que entrega el software, con el
    valor obtenido en el analisis. No contiene graficas."""

    def generate(self, context: GlossaryContext) -> bytes:
        buffer = io.BytesIO()
        document = SimpleDocTemplate(
            buffer, pagesize=A4, topMargin=2 * cm, bottomMargin=2 * cm, leftMargin=2 * cm, rightMargin=2 * cm
        )
        styles = getSampleStyleSheet()
        label = ParagraphStyle("label", parent=styles["Normal"], fontSize=8.5, textColor=colors.HexColor("#5b6678"))
        body = ParagraphStyle("body", parent=styles["Normal"], fontSize=9.5, leading=12.5)

        story = [
            Paragraph("Glosario de variables del análisis", styles["Title"]),
            Paragraph(
                f"<b>Atleta:</b> {context.athlete_code} · <b>Análisis:</b> #{context.analysis_id} · "
                f"<b>Distancia de la prueba:</b> {context.test_distance:g} m",
                styles["Normal"],
            ),
            Spacer(1, 0.5 * cm),
            Paragraph(
                "Este documento explica qué significa cada variable que entrega el software, cómo se calcula "
                "a partir del video y el valor que obtuvo este análisis.",
                body,
            ),
            Spacer(1, 0.4 * cm),
        ]

        for variable in _variables(context):
            rows = [
                [Paragraph(f"<b>{variable['name']}</b> ({variable['unit']})", body), ""],
                [Paragraph("Valor obtenido", label), Paragraph(f"<b>{variable['value']}</b>", body)],
                [Paragraph("Qué significa", label), Paragraph(variable["meaning"], body)],
                [Paragraph("Cómo se calcula", label), Paragraph(variable["how"], body)],
                [Paragraph("Cómo interpretarla", label), Paragraph(variable["read"], body)],
            ]
            table = Table(rows, colWidths=[3.4 * cm, 13.6 * cm])
            table.setStyle(
                TableStyle(
                    [
                        ("SPAN", (0, 0), (1, 0)),
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eefc")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), _BRAND_COLOR),
                        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c9d1e0")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ]
                )
            )
            story.append(KeepTogether([table, Spacer(1, 0.35 * cm)]))

        story.append(Paragraph("Consideraciones sobre la precisión", styles["Heading2"]))
        for note in (
            f"Escala: los metros se calculan suponiendo que el atleta recorre la distancia de la prueba "
            f"({context.test_distance:g} m) de la salida al final dentro del encuadre. Si recorre más o "
            "menos que eso, las velocidades y zancadas cambian en la misma proporción.",
            "El análisis es en 2D: funciona mejor con la cámara fija, a la altura de la cadera y de lado "
            "respecto a la trayectoria del atleta, sin zoom ni movimiento.",
            "La postura y los apoyos requieren ver bien las caderas, los hombros y los tobillos; si el atleta "
            "sale parcialmente del encuadre o hay mala iluminación, el porcentaje de detección baja.",
            "Los resultados describen lo medido en este video. No sustituyen la evaluación de un entrenador.",
        ):
            story.append(Paragraph(f"• {note}", body))
            story.append(Spacer(1, 0.15 * cm))

        document.build(story)
        return buffer.getvalue()
