#!/usr/bin/env python3
"""Generador de la Parte 3 de la documentacion UPA App: Informe del Proyecto (.docx).

Lee la fuente Markdown `docs/UPA_App_Informe_del_Proyecto.md`, genera un diagrama
visual de interaccion arquitectonica a nivel de gestion en memoria mediante Pillow
y construye `docs/UPA_App_Informe_del_Proyecto.docx` con formato academico y
alineacion justificada (Blocksatz) para la entrega final del curso.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import docx
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Inches, Pt, RGBColor
from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parent.parent
MD_SOURCE_PATH = REPO_ROOT / "docs" / "UPA_App_Informe_del_Proyecto.md"
DOCX_OUTPUT_PATH = REPO_ROOT / "docs" / "UPA_App_Informe_del_Proyecto.docx"

COLOR_NAVY = RGBColor(15, 23, 42)
COLOR_BLUE = RGBColor(30, 58, 138)
COLOR_SLATE = RGBColor(51, 65, 85)
COLOR_TEXT = RGBColor(30, 41, 59)
COLOR_CODE = RGBColor(15, 118, 110)
COLOR_WHITE = RGBColor(255, 255, 255)


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ]
        if bold
        else [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]
    )
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def build_management_architecture_png() -> io.BytesIO:
    """Genera un diagrama ejecutivo de las 4 capas de la arquitectura UPA App."""
    width, height = 1600, 520
    img = Image.new("RGB", (width, height), (248, 250, 252))
    draw = ImageDraw.Draw(img)

    f_title = _load_font(22, bold=True)
    f_box_title = _load_font(16, bold=True)
    f_text = _load_font(13, bold=False)
    f_small = _load_font(12, bold=True)

    draw.rectangle([20, 20, width - 20, height - 20], outline=(203, 213, 225), width=2)
    draw.text(
        (45, 35),
        "Interaccion Arquitectonica en Nivel de Gestion (UPA App: 4 Capas Desacopladas)",
        fill=(15, 23, 42),
        font=f_title,
    )

    def draw_card(
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        header_bg: tuple[int, int, int],
        title: str,
        lines: list[str],
    ) -> None:
        draw.rectangle([x1, y1, x2, y2], fill=(255, 255, 255), outline=header_bg, width=2)
        draw.rectangle([x1, y1, x2, y1 + 38], fill=header_bg)
        draw.text((x1 + 12, y1 + 9), title, fill=(255, 255, 255), font=f_box_title)
        cy = y1 + 50
        for line in lines:
            draw.text((x1 + 12, cy), line, fill=(30, 41, 59), font=f_text)
            cy += 22

    draw_card(
        45,
        100,
        380,
        460,
        (30, 58, 138),
        "1. Tunel Zero-Trust NetBird",
        [
            "Dominio: upa.eu1.netbird.services",
            "Cifrado TLS / HTTPS automatico",
            "Sin puertos entrantes abiertos",
            "",
            "Clientes:",
            "- PWA Movil (Android / iOS)",
            "- Landing Desktop con QR",
            "- Web-Admin Cockpit (/dashboard/)",
        ],
    )

    draw_card(
        435,
        100,
        770,
        460,
        (15, 118, 110),
        "2. Contenedor Nginx Frontend",
        [
            "Imagen: upa-frontend (:80)",
            "Entrega estatica de baja latencia:",
            "- PWA (/sw.js, /manifest.webmanifest)",
            "- Cockpit (/dashboard/* Deep Links)",
            "",
            "Proxy Inverso Same-Origin:",
            "- Redirige /api/* y /uploads/*",
            "- Elimina bloqueos CORS / Mixed",
        ],
    )

    draw_card(
        825,
        100,
        1165,
        460,
        (29, 78, 216),
        "3. Contenedor FastAPI Backend",
        [
            "Imagen: upa-backend (Python 3.11)",
            "Validacion Pydantic v2 + Pyright",
            "Gobernanza RBAC (6 permisos)",
            "",
            "Integraciones y Logica Real:",
            "- Google OAuth 2.0 (@upa.edu.py)",
            "- Google Classroom + Refresh Token",
            "- Gemini Flash + Gemma 4 Multimodal",
            "- SociableKIT Feed (@upalemana)",
        ],
    )

    draw_card(
        1220,
        100,
        1555,
        460,
        (15, 23, 42),
        "4. PostgreSQL 16 (ACID)",
        [
            "Imagen: upa-postgres (:5432)",
            "Aislado en 127.0.0.1:5432",
            "SQLAlchemy 2.0 + Alembic",
            "",
            "9 Tablas Productivas Depuradas:",
            "- users, posts (Single Source)",
            "- event_registrations, post_views",
            "- audience_groups, user_roles",
            "- admin_audit_logs, device_tokens",
            "- app_settings",
        ],
    )

    arrow_color = (51, 65, 85)
    draw.line([(380, 280), (435, 280)], fill=arrow_color, width=3)
    draw.text((386, 255), "HTTPS", fill=arrow_color, font=f_small)
    draw.line([(770, 280), (825, 280)], fill=arrow_color, width=3)
    draw.text((778, 255), "Proxy", fill=arrow_color, font=f_small)
    draw.line([(1165, 280), (1220, 280)], fill=arrow_color, width=3)
    draw.text((1176, 255), "SQL", fill=arrow_color, font=f_small)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def _set_cell_background(cell, hex_color: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tc_pr.append(shd)


def _set_cell_margins(
    cell, top: int = 100, bottom: int = 100, left: int = 140, right: int = 140
) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_mar = OxmlElement("w:tcMar")
    for side, val in (("top", top), ("bottom", bottom), ("left", left), ("right", right)):
        node = OxmlElement(f"w:{side}")
        node.set(qn("w:w"), str(val))
        node.set(qn("w:type"), "dxa")
        tc_mar.append(node)
    tc_pr.append(tc_mar)


def _add_formatted_runs(
    paragraph, text: str, base_size_pt: float = 10.5, text_color: RGBColor = COLOR_TEXT
) -> None:
    """Procesa negritas (**...**), cursivas (*...*) y codigo en linea (`...`)."""
    tokens = re.split(r"(\*\*[^*]+\*\*|`[^`]+`)", text)
    for token in tokens:
        if not token:
            continue
        if token.startswith("**") and token.endswith("**") and len(token) > 4:
            inner = token[2:-2]
            sub_tokens = re.split(r"(`[^`]+`)", inner)
            for st in sub_tokens:
                if not st:
                    continue
                is_code = st.startswith("`") and st.endswith("`")
                run = paragraph.add_run(st[1:-1] if is_code else st)
                run.bold = True
                run.font.name = "Consolas" if is_code else "Arial"
                run.font.size = Pt(base_size_pt - 0.5 if is_code else base_size_pt)
                run.font.color.rgb = COLOR_CODE if is_code else text_color
        elif token.startswith("`") and token.endswith("`") and len(token) > 2:
            run = paragraph.add_run(token[1:-1])
            run.font.name = "Consolas"
            run.font.size = Pt(base_size_pt - 0.5)
            run.font.color.rgb = COLOR_CODE
        else:
            run = paragraph.add_run(token)
            run.font.name = "Arial"
            run.font.size = Pt(base_size_pt)
            run.font.color.rgb = text_color


def _add_markdown_table(doc: docx.Document, rows: list[list[str]]) -> None:
    if not rows:
        return
    num_cols = max(len(r) for r in rows)
    table = doc.add_table(rows=len(rows), cols=num_cols)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    for r_idx, row_values in enumerate(rows):
        row = table.rows[r_idx]
        is_header = r_idx == 0
        bg_hex = "1E3A8A" if is_header else ("F8FAFC" if r_idx % 2 == 1 else "FFFFFF")
        for c_idx in range(num_cols):
            cell = row.cells[c_idx]
            _set_cell_background(cell, bg_hex)
            _set_cell_margins(cell, top=90, bottom=90, left=120, right=120)
            raw_cell = row_values[c_idx] if c_idx < len(row_values) else ""
            parts = [p.strip() for p in raw_cell.split("<br>")]
            cell.text = ""
            for p_idx, part in enumerate(parts):
                p = cell.paragraphs[0] if p_idx == 0 else cell.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.LEFT
                p.paragraph_format.space_before = Pt(1)
                p.paragraph_format.space_after = Pt(2)
                if is_header:
                    clean_header = part.replace("**", "").replace("`", "")
                    run = p.add_run(clean_header)
                    run.bold = True
                    run.font.name = "Arial"
                    run.font.size = Pt(9.5)
                    run.font.color.rgb = COLOR_WHITE
                else:
                    _add_formatted_runs(p, part, base_size_pt=9.5, text_color=COLOR_TEXT)

    spacer = doc.add_paragraph()
    spacer.paragraph_format.space_before = Pt(0)
    spacer.paragraph_format.space_after = Pt(4)


def _add_callout_box(doc: docx.Document, quote_lines: list[str]) -> None:
    table = doc.add_table(rows=1, cols=1)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = table.rows[0].cells[0]
    _set_cell_background(cell, "EFF6FF")
    _set_cell_margins(cell, top=130, bottom=130, left=170, right=170)

    cell.text = ""
    for idx, line in enumerate(quote_lines):
        p = cell.paragraphs[0] if idx == 0 else cell.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.line_spacing = 1.15
        _add_formatted_runs(p, line, base_size_pt=10.5, text_color=COLOR_NAVY)

    spacer = doc.add_paragraph()
    spacer.paragraph_format.space_before = Pt(0)
    spacer.paragraph_format.space_after = Pt(6)


def generate_docx(md_path: Path = MD_SOURCE_PATH, docx_path: Path = DOCX_OUTPUT_PATH) -> Path:
    md_text = md_path.read_text(encoding="utf-8")
    lines = md_text.splitlines()

    doc = docx.Document()

    for section in doc.sections:
        section.page_width = Cm(21.0)
        section.page_height = Cm(29.7)
        section.top_margin = Cm(2.0)
        section.bottom_margin = Cm(2.0)
        section.left_margin = Cm(2.2)
        section.right_margin = Cm(2.2)

    normal_style = doc.styles["Normal"]
    normal_style.font.name = "Arial"
    normal_style.font.size = Pt(10.5)
    normal_style.font.color.rgb = COLOR_TEXT
    normal_style.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    normal_style.paragraph_format.line_spacing = 1.16
    normal_style.paragraph_format.space_after = Pt(5)

    i = 0
    n = len(lines)

    while i < n:
        raw_line = lines[i]
        stripped = raw_line.strip()

        if not stripped:
            i += 1
            continue

        if stripped.startswith("```"):
            lang = stripped[3:].strip().lower()
            i += 1
            while i < n and not lines[i].strip().startswith("```"):
                i += 1
            if i < n:
                i += 1
            if lang == "mermaid":
                arch_png = build_management_architecture_png()
                p_img = doc.add_paragraph()
                p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
                p_img.add_run().add_picture(arch_png, width=Inches(6.3))
            continue

        if stripped.startswith(">"):
            quote_lines: list[str] = []
            while i < n and lines[i].strip().startswith(">"):
                q_line = lines[i].strip().lstrip(">").strip()
                if q_line:
                    quote_lines.append(q_line)
                i += 1
            _add_callout_box(doc, quote_lines)
            continue

        if stripped.startswith("|") and stripped.endswith("|"):
            table_rows: list[list[str]] = []
            while i < n and lines[i].strip().startswith("|"):
                t_line = lines[i].strip()
                cells = [c.strip() for c in t_line.strip("|").split("|")]
                if not all(re.match(r"^:?-{2,}:?$", c) for c in cells):
                    table_rows.append(cells)
                i += 1
            _add_markdown_table(doc, table_rows)
            continue

        if stripped.startswith("# "):
            title_text = stripped[2:].strip()
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            p.paragraph_format.space_before = Pt(4)
            p.paragraph_format.space_after = Pt(4)
            run = p.add_run(title_text)
            run.bold = True
            run.font.name = "Arial"
            run.font.size = Pt(18)
            run.font.color.rgb = COLOR_NAVY
            i += 1
            continue

        if stripped.startswith("## "):
            h1_text = stripped[3:].strip()
            p = doc.add_heading(level=1)
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            p.paragraph_format.space_before = Pt(13)
            p.paragraph_format.space_after = Pt(5)
            run = p.add_run(h1_text)
            run.bold = True
            run.font.name = "Arial"
            run.font.size = Pt(13.5)
            run.font.color.rgb = COLOR_NAVY
            i += 1
            continue

        if stripped.startswith("### "):
            h2_text = stripped[4:].strip()
            p = doc.add_heading(level=2)
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            p.paragraph_format.space_before = Pt(9)
            p.paragraph_format.space_after = Pt(4)
            run = p.add_run(h2_text)
            run.bold = True
            run.font.name = "Arial"
            run.font.size = Pt(11.5)
            run.font.color.rgb = COLOR_BLUE
            i += 1
            continue

        if stripped.startswith("#### "):
            h3_text = stripped[5:].strip()
            p = doc.add_heading(level=3)
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            p.paragraph_format.space_before = Pt(7)
            p.paragraph_format.space_after = Pt(3)
            run = p.add_run(h3_text.replace("`", ""))
            run.bold = True
            run.font.name = "Arial"
            run.font.size = Pt(10.5)
            run.font.color.rgb = COLOR_SLATE
            i += 1
            continue

        if stripped.startswith(("* ", "- ")):
            indent_spaces = len(raw_line) - len(raw_line.lstrip(" "))
            item_text = stripped[2:].strip()
            p = doc.add_paragraph(style="List Bullet")
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            p.paragraph_format.left_indent = Cm(0.75 if indent_spaces < 2 else 1.35)
            p.paragraph_format.space_before = Pt(1)
            p.paragraph_format.space_after = Pt(3)
            p.paragraph_format.line_spacing = 1.14
            _add_formatted_runs(p, item_text, base_size_pt=10.5)
            i += 1
            continue

        num_match = re.match(r"^(\d+\.)\s+(.*)$", stripped)
        if num_match:
            prefix, item_text = num_match.group(1), num_match.group(2)
            indent_spaces = len(raw_line) - len(raw_line.lstrip(" "))
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            p.paragraph_format.left_indent = Cm(0.6 if indent_spaces < 2 else 1.2)
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(3)
            p.paragraph_format.line_spacing = 1.14
            r_num = p.add_run(f"{prefix} ")
            r_num.bold = True
            r_num.font.name = "Arial"
            r_num.font.size = Pt(10.5)
            r_num.font.color.rgb = COLOR_BLUE
            _add_formatted_runs(p, item_text, base_size_pt=10.5)
            i += 1
            continue

        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after = Pt(5)
        p.paragraph_format.line_spacing = 1.16
        _add_formatted_runs(p, stripped, base_size_pt=10.5)
        i += 1

    docx_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(docx_path))
    return docx_path


if __name__ == "__main__":
    output = generate_docx()
    print(f"Informe del Proyecto generado exitosamente en: {output} ({output.stat().st_size} bytes)")
