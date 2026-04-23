"""PDF generation helpers for pathfinder module — NPC stat card via ReportLab Platypus."""
import io
import logging

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

logger = logging.getLogger(__name__)


def build_npc_pdf(fields: dict, stats: dict, token_image_bytes: bytes | None = None) -> bytes:
    """Build a one-page PF2e NPC stat card PDF (OUT-04, D-18, D-19, D-20).

    Returns raw PDF bytes via buffer.getvalue() — never buffer.read() (Pitfall 6).
    Stats grid is omitted when stats is falsy (D-20: header-only PDF for stub NPCs).
    Skills accept dict OR string (Pitfall 7).
    If token_image_bytes is provided (from vault via ObsidianClient.get_binary),
    a 1.5"×1.5" image is embedded before the Title. Bad image bytes raise at
    doc.build() time — ReportLab's own validation (plan non-goal #2).
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )
    styles = getSampleStyleSheet()
    italic_style = ParagraphStyle(
        "italic_style",
        parent=styles["Normal"],
        fontName="Helvetica-Oblique",
    )

    story = []

    if token_image_bytes:
        story.append(Image(io.BytesIO(token_image_bytes), width=1.5 * inch, height=1.5 * inch))
        story.append(Spacer(1, 0.1 * inch))

    story.append(Paragraph(fields.get("name", "Unknown"), styles["Title"]))
    subtitle = (
        f"Level {fields.get('level', '?')} "
        f"{fields.get('ancestry', '')} {fields.get('class', '')}"
    )
    story.append(Paragraph(subtitle, styles["Heading2"]))

    traits = fields.get("traits")
    if traits:
        story.append(Paragraph(", ".join(traits), styles["Normal"]))

    personality = fields.get("personality") or ""
    if personality:
        story.append(Paragraph(personality[:150], italic_style))

    story.append(Spacer(1, 0.2 * inch))

    if stats:
        data = [
            ["AC", str(stats.get("ac", 0))],
            ["HP", str(stats.get("hp", 0))],
            [
                "Fort / Ref / Will",
                f"{stats.get('fortitude', 0)} / {stats.get('reflex', 0)} / {stats.get('will', 0)}",
            ],
            ["Speed", f"{stats.get('speed', 25)} ft."],
        ]

        skills = stats.get("skills")
        if isinstance(skills, dict):
            for k, v in skills.items():
                data.append([k.capitalize(), f"+{v}"])
        elif isinstance(skills, str):
            data.append(["Skills", skills[:100]])

        table = Table(data, colWidths=[2 * inch, 3.5 * inch])
        table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(table)

    doc.build(story)
    return buffer.getvalue()
