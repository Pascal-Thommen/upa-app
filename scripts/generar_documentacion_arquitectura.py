#!/usr/bin/env python3
"""Generador del documento oficial de arquitectura de UPA App en formato MS Word (.docx).

Lee la fuente Markdown `docs/UPA_App_Documentacion_Arquitectura.md`, genera los diagramas
visuales de arquitectura y esquema relacional (9 tablas de `backend/src/models.py`) en
memoria mediante Pillow y construye `docs/UPA_App_Documentacion_Arquitectura.docx` con
formato academico y alineacion justificada (Blocksatz).
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import docx
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_COLOR_INDEX
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Inches, Pt, RGBColor
from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parent.parent
MD_SOURCE_PATH = REPO_ROOT / "docs" / "UPA_App_Documentacion_Arquitectura.md"
DOCX_OUTPUT_PATH = REPO_ROOT / "docs" / "UPA_App_Documentacion_Arquitectura.docx"
MD_V3_SOURCE_PATH = REPO_ROOT / "docs" / "UPA_App_Documentacion_Arquitectura_v3.md"
DOCX_V3_OUTPUT_PATH = REPO_ROOT / "docs" / "UPA_App_Documentacion_Arquitectura_v3.docx"

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


def build_architecture_diagram_png() -> io.BytesIO:
    """Genera un diagrama visual claro de la arquitectura de 3 contenedores e integraciones."""
    width, height = 1600, 680
    img = Image.new("RGB", (width, height), (248, 250, 252))
    draw = ImageDraw.Draw(img)

    f_title = _load_font(22, bold=True)
    f_box_title = _load_font(17, bold=True)
    f_text = _load_font(14, bold=False)
    f_small = _load_font(13, bold=True)

    draw.rectangle([20, 20, width - 20, height - 20], outline=(203, 213, 225), width=2)
    draw.text(
        (45, 35),
        "Arquitectura Productiva UPA App: 3 Contenedores Docker, Proxy Nginx e Integraciones",
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
        draw.rectangle([x1, y1, x2, y1 + 40], fill=header_bg)
        draw.text((x1 + 14, y1 + 10), title, fill=(255, 255, 255), font=f_box_title)
        cy = y1 + 52
        for line in lines:
            draw.text((x1 + 14, cy), line, fill=(30, 41, 59), font=f_text)
            cy += 22

    # Clientes (Columna 1)
    draw_card(
        45,
        110,
        355,
        320,
        (30, 58, 138),
        "Clientes PWA Estudiantil",
        [
            "Android / iOS / Escritorio",
            "Ruta: / y /?app=1",
            "Service Worker v1.0.3 (/sw.js)",
            "Manifest (/manifest.webmanifest)",
            "Landing QR + Inicio, Agenda, Perfil",
        ],
    )
    draw_card(
        45,
        370,
        355,
        580,
        (30, 58, 138),
        "Web-Admin Cockpit (SPA)",
        [
            "Redaccion y Administracion",
            "Ruta: /dashboard/*",
            "Publicaciones + Autocompletar IA",
            "Grupos, Roles (6 permisos RBAC)",
            "Control de IA, APIs e Historial",
        ],
    )

    # Nginx Frontend (Columna 2)
    draw_card(
        435,
        195,
        745,
        495,
        (15, 118, 110),
        "Contenedor 1: upa-frontend",
        [
            "Nginx Alpine (:80)",
            "Acceso TLS Zero-Trust NetBird:",
            "upa.eu1.netbird.services (:8085)",
            "upa-beta.eu1.netbird.services (:8185)",
            "",
            "Sirve estaticos PWA y Cockpit",
            "Proxy Inverso (/api, /uploads, /docs)",
        ],
    )

    # Backend FastAPI (Columna 3)
    draw_card(
        825,
        160,
        1155,
        530,
        (29, 78, 216),
        "Contenedor 2: upa-backend",
        [
            "Python 3.11 + FastAPI (:8000)",
            "Validacion Pydantic v2 + Pyright",
            "OpenAPI 3.1 en /docs",
            "",
            "Modulos REST Productivos:",
            "- /api/auth (Google OAuth + JWT)",
            "- /api/v1/feed y /api/v1/agenda",
            "- /api/publications y /api/events",
            "- /api/ai (Gemini Flash Multimodal)",
            "- /api/groups, /api/roles, /api/history",
        ],
    )

    # PostgreSQL + Servicios Externos (Columna 4)
    draw_card(
        1235,
        95,
        1555,
        295,
        (15, 23, 42),
        "Contenedor 3: upa-postgres",
        [
            "PostgreSQL 16 Alpine",
            "Bind local: 127.0.0.1:5432",
            "SQLAlchemy 2.0 + Alembic",
            "9 Tablas Relacionales ACID",
            "Cache persistente de Classroom",
        ],
    )
    draw_card(
        1235,
        320,
        1555,
        620,
        (71, 85, 105),
        "Servicios Externos Integrados",
        [
            "1. Google OAuth 2.0 (@upa.edu.py)",
            "2. Google Workspace Directory API",
            "3. Google Classroom REST API",
            "   (Auto-Refresh + DB Fallback)",
            "4. Google Gemini Flash API",
            "   (Autocompletado + Extractor IA)",
            "5. SociableKIT API (@upalemana)",
            "   (Sync manual en Free Tier)",
            "6. Firebase Cloud Messaging (FCM)",
        ],
    )

    # Flechas de conexion
    arrow_color = (51, 65, 85)
    draw.line([(355, 215), (435, 290)], fill=arrow_color, width=3)
    draw.line([(355, 475), (435, 390)], fill=arrow_color, width=3)
    draw.line([(745, 345), (825, 345)], fill=arrow_color, width=4)
    draw.text((755, 320), "HTTP Proxy", fill=arrow_color, font=f_small)
    draw.line([(1155, 260), (1235, 195)], fill=arrow_color, width=3)
    draw.text((1162, 195), "SQL", fill=arrow_color, font=f_small)
    draw.line([(1155, 420), (1235, 465)], fill=arrow_color, width=3)
    draw.text((1160, 445), "HTTPS", fill=arrow_color, font=f_small)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def build_er_diagram_png() -> io.BytesIO:
    """Genera el Diagrama Entidad-Relacion (ERD) de alta resolucion con las 9 tablas reales."""
    width, height = 1800, 1320
    img = Image.new("RGB", (width, height), (248, 250, 252))
    draw = ImageDraw.Draw(img)

    f_title = _load_font(24, bold=True)
    f_sub = _load_font(15, bold=False)
    f_tbl = _load_font(17, bold=True)
    f_col = _load_font(13, bold=False)
    f_badge = _load_font(12, bold=True)

    draw.rectangle([18, 18, width - 18, height - 18], outline=(203, 213, 225), width=2)
    draw.text(
        (40, 32),
        "Esquema Relacional Depurado UPA App (PostgreSQL 16 - 9 Tablas en backend/src/models.py)",
        fill=(15, 23, 42),
        font=f_title,
    )
    draw.text(
        (40, 64),
        "Fuente Unica de Verdad (Single Source of Truth) sin columnas huerfanas. Claves: PK (Primaria), FK (Foranea), UK (Unica).",
        fill=(71, 85, 105),
        font=f_sub,
    )

    def draw_table_box(
        x: int,
        y: int,
        w: int,
        name: str,
        header_color: tuple[int, int, int],
        columns: list[tuple[str, str, str]],
    ) -> tuple[int, int, int, int]:
        row_h = 22
        h = 38 + len(columns) * row_h + 8
        draw.rectangle([x, y, x + w, y + h], fill=(255, 255, 255), outline=header_color, width=2)
        draw.rectangle([x, y, x + w, y + 34], fill=header_color)
        draw.text((x + 12, y + 8), name, fill=(255, 255, 255), font=f_tbl)

        cy = y + 38
        for idx, (key_tag, col_name, col_type) in enumerate(columns):
            if idx % 2 == 1:
                draw.rectangle([x + 2, cy, x + w - 2, cy + row_h], fill=(241, 245, 249))
            if key_tag:
                tag_color = (
                    (180, 83, 9)
                    if "PK" in key_tag
                    else (29, 78, 216)
                    if "FK" in key_tag
                    else (15, 118, 110)
                )
                draw.text((x + 10, cy + 3), key_tag, fill=tag_color, font=f_badge)
            draw.text((x + 68, cy + 3), col_name, fill=(15, 23, 42), font=f_col)
            draw.text((x + w - 155, cy + 3), col_type, fill=(71, 85, 105), font=f_col)
            cy += row_h
        return (x, y, x + w, y + h)

    # Columna Izquierda: users, device_tokens, admin_audit_logs
    b_users = draw_table_box(
        40,
        110,
        520,
        "1. users",
        (30, 58, 138),
        [
            ("PK", "id", "Integer"),
            ("UK", "email", "String(255) NOT NULL"),
            ("", "full_name", "String(255) NOT NULL"),
            ("", "role", "String(50) 'user'"),
            ("", "groups", "JSON NOT NULL"),
            ("", "google_groups", "JSON NOT NULL"),
            ("", "classroom_token", "Text NULL"),
            ("", "classroom_refresh_token", "Text NULL"),
            ("", "classroom_deadlines_cache", "JSON NOT NULL"),
            ("", "classroom_synced_at", "DateTime(tz) NULL"),
            ("", "created_at", "DateTime(tz) NOT NULL"),
            ("", "updated_at", "DateTime(tz) NULL"),
        ],
    )

    b_tokens = draw_table_box(
        40,
        460,
        520,
        "6. device_tokens (uq_user_device_token)",
        (15, 118, 110),
        [
            ("PK", "id", "Integer"),
            ("FK,UK", "user_id -> users.id", "Integer CASCADE"),
            ("UK", "device_token", "String(512) NOT NULL"),
            ("", "platform", "String(50) 'android'"),
            ("", "created_at", "DateTime(tz) NOT NULL"),
            ("", "updated_at", "DateTime(tz) NOT NULL"),
        ],
    )

    draw_table_box(
        40,
        680,
        520,
        "5. admin_audit_logs",
        (51, 65, 85),
        [
            ("PK", "id", "Integer"),
            ("FK", "admin_id -> users.id", "Integer NOT NULL"),
            ("", "action", "String(100) NOT NULL"),
            ("", "target_type", "String(50) NOT NULL"),
            ("", "target_id", "Integer NULL"),
            ("", "target_key", "String(255) NULL"),
            ("", "details", "JSON NOT NULL"),
            ("", "created_at", "DateTime(tz) NOT NULL"),
        ],
    )

    draw_table_box(
        40,
        945,
        520,
        "9. app_settings",
        (71, 85, 105),
        [
            ("PK", "key", "String(100)"),
            ("", "value", "Text NOT NULL"),
            ("", "updated_by", "String(255) NULL"),
            ("", "updated_at", "DateTime(tz) NOT NULL"),
        ],
    )

    # Columna Central: posts (Fuente Unica de Verdad)
    b_posts = draw_table_box(
        640,
        110,
        540,
        "2. posts (Single Source of Truth)",
        (29, 78, 216),
        [
            ("PK", "id", "Integer"),
            ("", "title", "String(255) NOT NULL"),
            ("", "caption", "Text NULL"),
            ("", "content", "Text NULL"),
            ("", "post_type", "String(50) 'MANUAL'"),
            ("", "category", "String(50) NULL"),
            ("", "is_news", "Boolean default=True"),
            ("", "is_event", "Boolean default=False"),
            ("", "is_pinned", "Boolean default=False"),
            ("", "published_at", "DateTime(tz) NULL"),
            ("", "expires_at", "DateTime(tz) NULL"),
            ("", "event_start", "DateTime(tz) NULL"),
            ("", "event_end", "DateTime(tz) NULL"),
            ("", "location", "String(255) NULL"),
            ("", "target_groups", "JSON NOT NULL"),
            ("", "has_registration", "Boolean default=False"),
            ("", "send_push_notification", "Boolean default=False"),
            ("", "reminders", "JSON NULL"),
            ("", "notify_groups", "JSON NULL"),
            ("", "event_notify_groups", "JSON NULL"),
            ("", "link_url", "Text NULL"),
            ("", "link_label", "String(100) NULL"),
            ("", "is_edited", "Boolean default=False"),
            ("", "is_ai_generated", "Boolean default=False"),
            ("UK", "instagram_id", "String(100) NULL"),
            ("", "media_type", "String(50) NULL"),
            ("", "media_url", "Text NULL"),
            ("", "permalink", "Text NULL"),
            ("FK", "author_id -> users.id", "Integer NULL"),
            ("", "created_at", "DateTime(tz) NOT NULL"),
            ("", "updated_at", "DateTime(tz) NULL"),
        ],
    )

    # Columna Derecha: event_registrations, post_views, audience_groups, user_roles
    b_reg = draw_table_box(
        1250,
        110,
        510,
        "3. event_registrations (uq_post_user_registration)",
        (15, 118, 110),
        [
            ("PK", "id", "Integer"),
            ("FK,UK", "post_id -> posts.id", "Integer CASCADE"),
            ("FK,UK", "user_id -> users.id", "Integer CASCADE"),
            ("", "status", "String(50) 'attending'"),
            ("", "created_at", "DateTime(tz) NOT NULL"),
            ("", "updated_at", "DateTime(tz) NULL"),
        ],
    )

    b_views = draw_table_box(
        1250,
        345,
        510,
        "4. post_views (uq_post_user_view)",
        (15, 118, 110),
        [
            ("PK", "id", "Integer"),
            ("FK,UK", "post_id -> posts.id", "Integer CASCADE"),
            ("FK,UK", "user_id -> users.id", "Integer CASCADE"),
            ("", "viewed_at", "DateTime(tz) NOT NULL"),
        ],
    )

    draw_table_box(
        1250,
        545,
        510,
        "7. audience_groups",
        (51, 65, 85),
        [
            ("PK", "id", "String(50)"),
            ("", "name", "String(100) NOT NULL"),
            ("", "description", "Text NULL"),
            ("", "google_groups", "JSON NULL"),
            ("", "emails", "JSON NOT NULL"),
            ("", "created_at", "DateTime(tz) NOT NULL"),
            ("", "updated_at", "DateTime(tz) NULL"),
        ],
    )

    draw_table_box(
        1250,
        795,
        510,
        "8. user_roles (Matriz RBAC 6 Permisos)",
        (51, 65, 85),
        [
            ("PK", "id", "Integer"),
            ("UK", "email", "String(255) NOT NULL"),
            ("", "name", "String(255) NOT NULL"),
            ("", "permissions", "JSON NOT NULL"),
            ("", "is_primary", "Boolean default=False"),
            ("", "created_at", "DateTime(tz) NOT NULL"),
            ("", "updated_at", "DateTime(tz) NULL"),
        ],
    )

    # Conectores visuales de llaves foraneas (FK)
    line_color = (29, 78, 216)
    # users -> posts (author_id)
    draw.line([(b_users[2], 240), (b_posts[0], 735)], fill=line_color, width=3)
    # posts -> event_registrations (post_id)
    draw.line([(b_posts[2], 200), (b_reg[0], 175)], fill=(15, 118, 110), width=3)
    # posts -> post_views (post_id)
    draw.line([(b_posts[2], 410), (b_views[0], 410)], fill=(15, 118, 110), width=3)
    # users -> device_tokens
    draw.line([(300, b_users[3]), (300, b_tokens[1])], fill=(15, 118, 110), width=3)
    # users -> admin_audit_logs
    draw.line([(560, 320), (600, 320), (600, 740), (560, 740)], fill=(71, 85, 105), width=2)

    # Leyenda inferior en Columna Central/Derecha
    draw.rectangle([640, 910, 1760, 1265], fill=(239, 246, 255), outline=(147, 197, 253), width=2)
    draw.text(
        (665, 930),
        "Resumen de Relaciones de Integridad Referencial y Propiedades Hibridas (models.py):",
        fill=(30, 58, 138),
        font=f_tbl,
    )
    legend_lines = [
        "1. users (1) ---> (N) posts [posts.author_id -> users.id]: Autor o redactor de la publicacion.",
        "2. posts (1) ---> (N) event_registrations [ON DELETE CASCADE, uq_post_user_registration]: Respuestas RSVP ('attending' / 'declined').",
        "3. users (1) ---> (N) event_registrations [ON DELETE CASCADE]: Inscripciones a eventos por cada estudiante.",
        "4. posts (1) ---> (N) post_views [ON DELETE CASCADE, uq_post_user_view]: Conteo unico de visualizaciones por publicacion.",
        "5. users (1) ---> (N) post_views [ON DELETE CASCADE]: Registro de lecturas unicas por estudiante.",
        "6. users (1) ---> (N) admin_audit_logs [admin_audit_logs.admin_id -> users.id]: Trazabilidad de acciones en Cockpit.",
        "7. users (1) ---> (N) device_tokens [ON DELETE CASCADE, uq_user_device_token]: Tokens FCM multi-dispositivo.",
        "8. Propiedades calculadas en ORM (sin columna redundante): Post.image_url (@hybrid_property sobre media_url) y Post.status.",
        "9. Visualizacion web interactiva: Pegar el bloque DBML de la Seccion 5.4 en https://dbdiagram.io/d para reordenar cajas.",
    ]
    ly = 970
    for l_item in legend_lines:
        draw.text((665, ly), l_item, fill=(30, 41, 59), font=f_col)
        ly += 30

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


def _set_cell_margins(cell, top: int = 100, bottom: int = 100, left: int = 140, right: int = 140) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_mar = OxmlElement("w:tcMar")
    for side, val in (("top", top), ("bottom", bottom), ("left", left), ("right", right)):
        node = OxmlElement(f"w:{side}")
        node.set(qn("w:w"), str(val))
        node.set(qn("w:type"), "dxa")
        tc_mar.append(node)
    tc_pr.append(tc_mar)


def _add_formatted_runs_segment(
    paragraph,
    text: str,
    base_size_pt: float = 10.5,
    text_color: RGBColor = COLOR_TEXT,
    highlight_yellow: bool = False,
) -> None:
    """Procesa negritas (**...**) y codigo en linea (`...`) dentro de un segmento de texto."""
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
                if highlight_yellow:
                    run.font.highlight_color = WD_COLOR_INDEX.YELLOW
        elif token.startswith("`") and token.endswith("`") and len(token) > 2:
            run = paragraph.add_run(token[1:-1])
            run.font.name = "Consolas"
            run.font.size = Pt(base_size_pt - 0.5)
            run.font.color.rgb = COLOR_CODE
            if highlight_yellow:
                run.font.highlight_color = WD_COLOR_INDEX.YELLOW
        else:
            run = paragraph.add_run(token)
            run.font.name = "Arial"
            run.font.size = Pt(base_size_pt)
            run.font.color.rgb = text_color
            if highlight_yellow:
                run.font.highlight_color = WD_COLOR_INDEX.YELLOW


def _add_formatted_runs(paragraph, text: str, base_size_pt: float = 10.5, text_color: RGBColor = COLOR_TEXT) -> None:
    """Procesa resaltado amarillo (==...==), negritas (**...**) y codigo (`...`) dentro de un parrafo."""
    hl_segments = re.split(r"(==.+?==)", text)
    for seg in hl_segments:
        if not seg:
            continue
        if seg.startswith("==") and seg.endswith("==") and len(seg) > 4:
            _add_formatted_runs_segment(
                paragraph,
                seg[2:-2],
                base_size_pt=base_size_pt,
                text_color=text_color,
                highlight_yellow=True,
            )
        else:
            _add_formatted_runs_segment(
                paragraph,
                seg,
                base_size_pt=base_size_pt,
                text_color=text_color,
                highlight_yellow=False,
            )


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


def _add_screenshot_placeholder_box(doc: docx.Document, quote_lines: list[str]) -> None:
    table = doc.add_table(rows=1, cols=1)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = table.rows[0].cells[0]
    _set_cell_background(cell, "EFF6FF")
    _set_cell_margins(cell, top=140, bottom=140, left=180, right=180)

    cell.text = ""
    for idx, line in enumerate(quote_lines):
        p = cell.paragraphs[0] if idx == 0 else cell.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after = Pt(3)
        p.paragraph_format.line_spacing = 1.15
        text_color = COLOR_BLUE if idx == 0 else COLOR_TEXT
        _add_formatted_runs(p, line, base_size_pt=10.0, text_color=text_color)

    spacer = doc.add_paragraph()
    spacer.paragraph_format.space_before = Pt(0)
    spacer.paragraph_format.space_after = Pt(6)


def _add_code_block_box(doc: docx.Document, code_lines: list[str]) -> None:
    table = doc.add_table(rows=1, cols=1)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = table.rows[0].cells[0]
    _set_cell_background(cell, "F1F5F9")
    _set_cell_margins(cell, top=120, bottom=120, left=150, right=150)

    cell.text = ""
    p = cell.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.line_spacing = 1.05
    run = p.add_run("\n".join(code_lines))
    run.font.name = "Consolas"
    run.font.size = Pt(8.5)
    run.font.color.rgb = COLOR_NAVY

    spacer = doc.add_paragraph()
    spacer.paragraph_format.space_before = Pt(0)
    spacer.paragraph_format.space_after = Pt(6)


def generate_docx(md_path: Path = MD_SOURCE_PATH, docx_path: Path = DOCX_OUTPUT_PATH) -> Path:
    md_text = md_path.read_text(encoding="utf-8")
    lines = md_text.splitlines()

    doc = docx.Document()

    # Configurar margenes A4 academicos
    for section in doc.sections:
        section.page_width = Cm(21.0)
        section.page_height = Cm(29.7)
        section.top_margin = Cm(2.2)
        section.bottom_margin = Cm(2.2)
        section.left_margin = Cm(2.3)
        section.right_margin = Cm(2.3)

    # Estilo Normal base con alineacion justificada (Blocksatz)
    normal_style = doc.styles["Normal"]
    normal_style.font.name = "Arial"
    normal_style.font.size = Pt(10.5)
    normal_style.font.color.rgb = COLOR_TEXT
    normal_style.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    normal_style.paragraph_format.line_spacing = 1.18
    normal_style.paragraph_format.space_after = Pt(6)

    i = 0
    n = len(lines)
    current_section_h3 = ""

    while i < n:
        raw_line = lines[i]
        stripped = raw_line.strip()

        if not stripped:
            i += 1
            continue

        # Bloques de codigo (```mermaid o ```dbml)
        if stripped.startswith("```"):
            lang = stripped[3:].strip().lower()
            i += 1
            code_lines: list[str] = []
            while i < n and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            if i < n:
                i += 1  # saltar cierre ```

            if lang == "mermaid":
                if "4.6" in current_section_h3:
                    arch_png = build_architecture_diagram_png()
                    p_img = doc.add_paragraph()
                    p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    p_img.add_run().add_picture(arch_png, width=Inches(6.3))
                elif "5.2" in current_section_h3:
                    er_png = build_er_diagram_png()
                    p_img = doc.add_paragraph()
                    p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    p_img.add_run().add_picture(er_png, width=Inches(6.3))
            else:
                _add_code_block_box(doc, code_lines)
            continue

        # Bloques de cita / Placeholders de Captura (> ...)
        if stripped.startswith(">"):
            quote_lines: list[str] = []
            while i < n and lines[i].strip().startswith(">"):
                q_line = lines[i].strip().lstrip(">").strip()
                if q_line:
                    quote_lines.append(q_line)
                i += 1
            _add_screenshot_placeholder_box(doc, quote_lines)
            continue

        # Tablas Markdown (| ... |)
        if stripped.startswith("|") and stripped.endswith("|"):
            table_rows: list[list[str]] = []
            while i < n and lines[i].strip().startswith("|"):
                t_line = lines[i].strip()
                cells = [c.strip() for c in t_line.strip("|").split("|")]
                # Omitir fila separadora |---|---|
                if not all(re.match(r"^:?-{2,}:?$", c) for c in cells):
                    table_rows.append(cells)
                i += 1
            _add_markdown_table(doc, table_rows)
            continue

        # Encabezados (#, ##, ###, ####)
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
            p.paragraph_format.space_before = Pt(14)
            p.paragraph_format.space_after = Pt(6)
            run = p.add_run(h1_text)
            run.bold = True
            run.font.name = "Arial"
            run.font.size = Pt(14)
            run.font.color.rgb = COLOR_NAVY
            i += 1
            continue

        if stripped.startswith("### "):
            h2_text = stripped[4:].strip()
            current_section_h3 = h2_text
            p = doc.add_heading(level=2)
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            p.paragraph_format.space_before = Pt(10)
            p.paragraph_format.space_after = Pt(4)
            run = p.add_run(h2_text)
            run.bold = True
            run.font.name = "Arial"
            run.font.size = Pt(12)
            run.font.color.rgb = COLOR_BLUE
            i += 1
            continue

        if stripped.startswith("#### "):
            h3_text = stripped[5:].strip()
            p = doc.add_heading(level=3)
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            p.paragraph_format.space_before = Pt(8)
            p.paragraph_format.space_after = Pt(3)
            run = p.add_run(h3_text.replace("`", ""))
            run.bold = True
            run.font.name = "Arial"
            run.font.size = Pt(11)
            run.font.color.rgb = COLOR_SLATE
            i += 1
            continue

        # Listas con vinetas (* o -)
        if stripped.startswith(("* ", "- ")):
            indent_spaces = len(raw_line) - len(raw_line.lstrip(" "))
            item_text = stripped[2:].strip()
            p = doc.add_paragraph(style="List Bullet")
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            p.paragraph_format.left_indent = Cm(0.8 if indent_spaces < 2 else 1.4)
            p.paragraph_format.space_before = Pt(1)
            p.paragraph_format.space_after = Pt(3)
            p.paragraph_format.line_spacing = 1.15
            _add_formatted_runs(p, item_text, base_size_pt=10.5)
            i += 1
            continue

        # Listas numeradas (1. , 2. , etc.)
        num_match = re.match(r"^(\d+\.)\s+(.*)$", stripped)
        if num_match:
            prefix, item_text = num_match.group(1), num_match.group(2)
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            p.paragraph_format.left_indent = Cm(0.6)
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(4)
            p.paragraph_format.line_spacing = 1.15
            r_num = p.add_run(f"{prefix} ")
            r_num.bold = True
            r_num.font.name = "Arial"
            r_num.font.size = Pt(10.5)
            r_num.font.color.rgb = COLOR_BLUE
            _add_formatted_runs(p, item_text, base_size_pt=10.5)
            i += 1
            continue

        # Parrafo estandar justificado (Blocksatz)
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after = Pt(6)
        p.paragraph_format.line_spacing = 1.18
        _add_formatted_runs(p, stripped, base_size_pt=10.5)
        i += 1

    docx_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(docx_path))
    return docx_path


if __name__ == "__main__":
    output_v4 = generate_docx(MD_SOURCE_PATH, DOCX_OUTPUT_PATH)
    print(f"Documento Word generado exitosamente en: {output_v4} ({output_v4.stat().st_size} bytes)")
    if MD_V3_SOURCE_PATH.exists():
        output_v3 = generate_docx(MD_V3_SOURCE_PATH, DOCX_V3_OUTPUT_PATH)
        print(f"Documento Word v3 generado exitosamente en: {output_v3} ({output_v3.stat().st_size} bytes)")
