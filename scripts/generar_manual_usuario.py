#!/usr/bin/env python3
"""Generador del Manual de Usuario oficial de UPA App en formato MS Word (.docx).

Lee la fuente Markdown `docs/UPA_App_Manual_de_Usuario.md`, genera los 9 contenedores
visuales de pantallas clave (Screens 1 a 9: Parte A Campus PWA y Parte B Web-Admin Cockpit)
con indicadores de enfoque UI en memoria mediante Pillow, y construye
`docs/UPA_App_Manual_de_Usuario.docx` con alineacion justificada (Blocksatz), pies de
figura y cuadros de instrucciones de captura y marcado.
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
MD_SOURCE_PATH = REPO_ROOT / "docs" / "UPA_App_Manual_de_Usuario.md"
DOCX_OUTPUT_PATH = REPO_ROOT / "docs" / "UPA_App_Manual_de_Usuario.docx"

COLOR_NAVY = RGBColor(15, 23, 42)
COLOR_BLUE = RGBColor(30, 58, 138)
COLOR_GREEN = RGBColor(108, 147, 57)
COLOR_SLATE = RGBColor(51, 65, 85)
COLOR_TEXT = RGBColor(30, 41, 59)
COLOR_CODE = RGBColor(15, 118, 110)
COLOR_WHITE = RGBColor(255, 255, 255)


SCREEN_SPECS: dict[str, dict[str, object]] = {
    "screen_1": {
        "number": 1,
        "part": "PARTE A: CAMPUS PWA",
        "title": "Screen 1: Pagina de Aterrizaje de Escritorio (QR-Code y Login)",
        "route": "https://upa.eu1.netbird.services/",
        "header_rgb": (30, 58, 138),
        "left_title": "Vista Previa Interactiva (phone-mockup)",
        "left_items": [
            "[UPA] Cabecera Institucional + Actualizar",
            "Aviso: Inicia sesion con tu cuenta @upa.edu.py",
            "[Boton] Iniciar sesion con Google",
            "Tarjetas publicas de Instagram (@upalemana)",
            "Barra inferior: [Inicio]  [Agenda]  [Perfil]",
        ],
        "right_title": "Tarjeta de Acceso Movil (#qr-box) y Pie",
        "right_items": [
            "Titulo: Escanea con tu celular para abrir la app",
            "[Codigo QR Vectorial Dinamico] -> Abre PWA movil",
            "Enlace directo: /?app=1 (Volver al codigo QR)",
            "Pie derecho: [Acceso Administrativo] -> /dashboard/",
        ],
        "focus_badges": [
            ("1", "Marco movil interactivo y Login @upa.edu.py"),
            ("2", "Codigo QR dinamico para Android e iOS"),
            ("3", "Enlace Acceso Administrativo (/dashboard/)"),
        ],
    },
    "screen_2": {
        "number": 2,
        "part": "PARTE A: CAMPUS PWA",
        "title": "Screen 2: Campus Feed y Avisos Urgentes (Noticias, Eventos, Alertas)",
        "route": "https://upa.eu1.netbird.services/?app=1 (Pestana Inicio)",
        "header_rgb": (30, 58, 138),
        "left_title": "Jerarquia Superior del Muro (Prioridad)",
        "left_items": [
            "[AVISO URGENTE] Banner de emergencia con expiracion",
            "[FIJADO] Publicacion destacada arriba en el feed",
            "Banner opcional: Instalar en pantalla de inicio",
            "Boton superior derecho: Actualizar muro en vivo",
        ],
        "right_title": "Tarjetas del Muro y Vista Detallada (#detail)",
        "right_items": [
            "[Noticia] Comunicado oficial segmentado por grupo",
            "[Evento] Fecha, hora, lugar + Botones RSVP Si / No",
            "[Instagram @upalemana] Insignia de camara + Flyer",
            "Clic en tarjeta -> Modal completo (#detail) y video",
        ],
        "focus_badges": [
            ("1", "Bloque de Aviso Urgente (#urgent-list) y Fijados"),
            ("2", "Insignias por tipo: Noticia, Evento e Instagram"),
            ("3", "Barra inferior con pestana Inicio activa"),
        ],
    },
    "screen_3": {
        "number": 3,
        "part": "PARTE A: CAMPUS PWA",
        "title": "Screen 3: Agenda Interactiva (Classroom y RSVP 1 Clic con Si/No)",
        "route": "https://upa.eu1.netbird.services/?app=1 (Pestana Agenda)",
        "header_rgb": (30, 58, 138),
        "left_title": "Lista Cronologica y RSVP de 2 Botones",
        "left_items": [
            "Encabezado: Proximos eventos y tareas [Ver todo]",
            "[Evento UPA] Hora e inscripcion en America/Asuncion",
            "Accion RSVP 1 Clic: [Si, asistire]  [No asistire]",
            "[Google Classroom] Materia, fecha limite y enlace",
            "Privacidad: Conteo total oculto para estudiantes",
        ],
        "right_title": "Calendario Mensual Interactivo (#cal-grid)",
        "right_items": [
            "Navegacion mensual: [< Mes anterior] [Mes siguiente >]",
            "Cuadricula de dias con puntos indicadores de color",
            "Toque en un dia -> Filtra la lista superior al instante",
            "Boton [Ver todo] -> Restaura la agenda completa",
        ],
        "focus_badges": [
            ("1", "Eventos del campus + Entregas Google Classroom"),
            ("2", "Botones 1-Clic: [Si, asistire] y [No asistire]"),
            ("3", "Calendario mensual con puntos de actividad"),
        ],
    },
    "screen_4": {
        "number": 4,
        "part": "PARTE A: CAMPUS PWA",
        "title": "Screen 4: Perfil de Usuario (Identidad, Carrera y Tema de 3 Vias)",
        "route": "https://upa.eu1.netbird.services/?app=1 (Pestana Perfil)",
        "header_rgb": (30, 58, 138),
        "left_title": "Identidad Google Workspace (@upa.edu.py)",
        "left_items": [
            "Avatar circular con iniciales del usuario",
            "Nombre completo verificado via Google OAuth 2.0",
            "Correo institucional: estudiante@upa.edu.py",
            "Insignia de rol y carrera sincronizada (TIE/PI/TI)",
        ],
        "right_title": "Diseno (3-Wege-Theme), Avisos y Sesion",
        "right_items": [
            "Selector Diseno: [Sistema] | [Modo Claro] | [Modo Oscuro]",
            "Switch [x] Eventos (recordatorios de actividades)",
            "Switch [x] Avisos y comunicados (alertas y noticias)",
            "Switch [x] Fechas limite (entregas de Classroom)",
            "Boton rojo: [Cerrar sesion] (limpia cache local)",
        ],
        "focus_badges": [
            ("1", "Tarjeta de identidad verificada @upa.edu.py"),
            ("2", "Selector de tema: Sistema / Modo Claro / Modo Oscuro"),
            ("3", "Interruptores de notificaciones y Cerrar sesion"),
        ],
    },
    "screen_5": {
        "number": 5,
        "part": "PARTE B: WEB-ADMIN COCKPIT",
        "title": "Screen 5: Vista General del Cockpit (Tabla, Filtros y Deep Links)",
        "route": "https://upa.eu1.netbird.services/dashboard/publicaciones",
        "header_rgb": (15, 118, 110),
        "left_title": "Navegacion, Deep Links y Filtros Rapidos",
        "left_items": [
            "Menu lateral: Publicaciones | Grupos, Roles, APIs, IA",
            "Cabecera superior: [Ver Campus PWA] + Perfil activo",
            "Filtro de modo: [Todas]  [Noticias]  [Eventos]",
            "Accion principal: [+ Nueva publicacion]",
            "Deep Links: /dashboard/publicaciones/:id y /nueva",
        ],
        "right_title": "Tabla Unificada de Publicaciones y Metricas",
        "right_items": [
            "Columna Publicacion: Miniatura, titulo y fechas",
            "Columna Secciones: Etiquetas Noticia, Evento, Fijado",
            "Columna Tipo: Manual, Instagram o insignia [IA]",
            "Columna Alcance y RSVP: X vistas | Y inscritos | Z no asisten",
            "Columna Estado: [Editado] o [Pendiente]",
        ],
        "focus_badges": [
            ("1", "Menu de modulos y Deep Link en barra de URL"),
            ("2", "Filtros [Todas/Noticias/Eventos] y [+ Nueva publicacion]"),
            ("3", "Metricas reales: vistas, inscritos, bajas e insignia IA"),
        ],
    },
    "screen_6": {
        "number": 6,
        "part": "PARTE B: WEB-ADMIN COCKPIT",
        "title": "Screen 6: Smart Autocomplete con IA (Extraccion de Afiche con Gemini)",
        "route": "https://upa.eu1.netbird.services/dashboard/publicaciones/nueva",
        "header_rgb": (15, 118, 110),
        "left_title": "Subida de Afiche y Asistente Multimodal IA",
        "left_items": [
            "Dropzone: Imagen o video (JPG, PNG, WEBP, MP4, PDF <=10MB)",
            "Vista previa instantanea del flyer subido (/uploads/...)",
            "Boton destacado: [Autocompletar con IA] (Gemini Flash)",
            "Regla: Rellena solo campos vacios sin pisar al redactor",
        ],
        "right_title": "Campos Generados, Evento, RSVP y Participantes",
        "right_items": [
            "Completa: Titulo, Resumen corto, Texto y Grupos",
            "Activa [x] Activar Evento + [x] Permitir inscripcion RSVP",
            "Extrae: Inicio (DD/MM/YYYY HH:mm), Fin (HH:mm) y Lugar",
            "Recordatorios: 30m (Lun-Vie) o 1 dia + 30m (Sab-Dom)",
            "Al editar: Boton [Ver participantes] muestra lista nominal",
        ],
        "focus_badges": [
            ("1", "Dropzone con vista previa del afiche subido"),
            ("2", "Campos de Evento, RSVP activo y recordatorios"),
            ("3", "Boton [Autocompletar con IA] y [Ver participantes]"),
        ],
    },
    "screen_7": {
        "number": 7,
        "part": "PARTE B: WEB-ADMIN COCKPIT",
        "title": "Screen 7: Gestion de Grupos de Audiencia (Google Workspace Mapping)",
        "route": "https://upa.eu1.netbird.services/dashboard/grupos",
        "header_rgb": (15, 118, 110),
        "left_title": "Catalogo Alfabetico de Audiencias",
        "left_items": [
            "Buscador: Filtrar grupos alfabeticamente...",
            "Boton primario: [+ Nuevo grupo]",
            "Grupos base: ALL, estudiantes, docentes, staff, egresados",
            "Grupos de carrera: TIE, PI, TI, PROF",
        ],
        "right_title": "Mapeo con Google Workspace y Correos",
        "right_items": [
            "Selector: Grupos de Google Workspace (@upa.edu.py)",
            "Ej: estudiantes-activos@upa.edu.py, estudiantes-tie-2025@",
            "Campo para agregar otro grupo de Google Workspace",
            "Seccion: Cuentas individuales (@upa.edu.py) + [Guardar]",
        ],
        "focus_badges": [
            ("1", "Buscador alfabetico y boton [+ Nuevo grupo]"),
            ("2", "Selector de Grupos de Google Workspace (@upa.edu.py)"),
            ("3", "Asignacion de cuentas individuales y [Guardar]"),
        ],
    },
    "screen_8": {
        "number": 8,
        "part": "PARTE B: WEB-ADMIN COCKPIT",
        "title": "Screen 8: Matriz de Roles y Permisos (6 Permisos Canonicos)",
        "route": "https://upa.eu1.netbird.services/dashboard/roles",
        "header_rgb": (15, 118, 110),
        "left_title": "Alta de Cuentas y Principio de Minimo Privilegio",
        "left_items": [
            "Formulario: Correo institucional (nombre.apellido@upa.edu.py)",
            "Boton: [Autorizar] -> Crea fila con 0 permisos marcados",
            "Proteccion: Impide revocar al ultimo admin con permiso Roles",
            "Modulos asociados: Pestanas [IA] (Gemini) y [APIs] (Salud)",
        ],
        "right_title": "Las 6 Columnas de Permisos en la Tabla",
        "right_items": [
            "1. [x] Publicaciones (Noticias, eventos, IA y participantes)",
            "2. [x] Grupos (Audiencias y mapeo Google Workspace)",
            "3. [x] Roles (Matriz RBAC de cuentas administrativas)",
            "4. [x] APIs (Estado en vivo de conectores y diagnostico)",
            "5. [x] IA (Clave GEMINI_API_KEY y System Prompts)",
            "6. [x] Historial (Acceso a tablas de auditoria)",
        ],
        "focus_badges": [
            ("1", "Alta de correo @upa.edu.py con boton [Autorizar]"),
            ("2", "Matriz interactiva de las 6 casillas de permisos"),
            ("3", "Acciones por cuenta y proteccion del rol principal"),
        ],
    },
    "screen_9": {
        "number": 9,
        "part": "PARTE B: WEB-ADMIN COCKPIT",
        "title": "Screen 9: Historial y Registros de Auditoria (Bitacora Inmutable)",
        "route": "https://upa.eu1.netbird.services/dashboard/publicaciones | /grupos | /roles",
        "header_rgb": (15, 118, 110),
        "left_title": "Ubicacion y Alcance del Historial (admin_audit_logs)",
        "left_items": [
            "Visible para cuentas con el permiso [Historial]",
            "Integrado al pie de Publicaciones, Grupos y Roles",
            "Vista global por modulo y vista individual por registro",
            "Endpoints: GET /api/history/post, /group y /role",
        ],
        "right_title": "Estructura de Cada Fila en la Tabla Historial:",
        "right_items": [
            "Columna 1 (Fecha 24h): DD/MM/YYYY HH:mm exacto",
            "Columna 2 (Responsable): Nombre o correo @upa.edu.py",
            "Columna 3 (Accion): creo, actualizo, elimino, sincronizo",
            "Detalle de cambios: (title, event_start) o permisos (+/-)",
        ],
        "focus_badges": [
            ("1", "Marca temporal exacta en formato 24h (DD/MM/YYYY HH:mm)"),
            ("2", "Identidad verificada del administrador ejecutor"),
            ("3", "Accion realizada y lista exacta de campos modificados"),
        ],
    },
}


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


def build_screen_container_png(screen_key: str) -> io.BytesIO:
    """Genera un contenedor visual estructurado para la vista clave con sus 3 puntos de enfoque."""
    spec = SCREEN_SPECS[screen_key]
    width, height = 1600, 620
    img = Image.new("RGB", (width, height), (248, 250, 252))
    draw = ImageDraw.Draw(img)

    f_badge = _load_font(14, bold=True)
    f_title = _load_font(22, bold=True)
    f_route = _load_font(15, bold=False)
    f_box_title = _load_font(17, bold=True)
    f_item = _load_font(15, bold=False)
    f_focus = _load_font(15, bold=True)

    header_rgb = spec["header_rgb"]  # type: ignore[assignment]
    part_label = str(spec["part"])
    title_label = str(spec["title"])
    route_label = f"Ruta a capturar: {spec['route']}"

    # Marco exterior y barra superior del contenedor
    draw.rectangle([16, 16, width - 16, height - 16], outline=header_rgb, width=3)
    draw.rectangle([16, 16, width - 16, 108], fill=header_rgb)

    # Etiqueta de Parte y Titulo de la Pantalla
    draw.rectangle([38, 30, 310, 58], fill=(255, 255, 255))
    draw.text((50, 35), part_label, fill=header_rgb, font=f_badge)
    draw.text((330, 30), title_label, fill=(255, 255, 255), font=f_title)
    draw.text((38, 72), route_label, fill=(226, 232, 240), font=f_route)

    # Dos paneles centrales simulando la composicion de la pantalla y sus elementos UI
    def draw_panel(x1: int, y1: int, x2: int, y2: int, p_title: str, items: list[str]) -> None:
        draw.rectangle([x1, y1, x2, y2], fill=(255, 255, 255), outline=(203, 213, 225), width=2)
        draw.rectangle([x1, y1, x2, y1 + 42], fill=(241, 245, 249))
        draw.text((x1 + 16, y1 + 11), p_title, fill=(15, 23, 42), font=f_box_title)
        cy = y1 + 58
        for idx, line in enumerate(items, start=1):
            draw.ellipse([x1 + 18, cy + 2, x1 + 36, cy + 20], fill=header_rgb)
            draw.text((x1 + 23, cy + 1), str(idx), fill=(255, 255, 255), font=_load_font(12, bold=True))
            draw.text((x1 + 48, cy), line, fill=(30, 41, 59), font=f_item)
            cy += 42

    draw_panel(
        40,
        130,
        780,
        445,
        str(spec["left_title"]),
        list(spec["left_items"]),  # type: ignore[arg-type]
    )
    draw_panel(
        820,
        130,
        1560,
        445,
        str(spec["right_title"]),
        list(spec["right_items"]),  # type: ignore[arg-type]
    )

    # Franja inferior con los 3 Enfoques de Marcado (Callouts 1, 2, 3)
    draw.rectangle([40, 468, 1560, 584], fill=(239, 246, 255), outline=(147, 197, 253), width=2)
    draw.text(
        (60, 480),
        "ELEMENTOS UI A ENFOCAR Y RESALTAR EN LA CAPTURA DE PANTALLA:",
        fill=(30, 58, 138),
        font=f_badge,
    )

    focus_list: list[tuple[str, str]] = list(spec["focus_badges"])  # type: ignore[arg-type]
    col_w = 490
    for idx, (num_str, desc) in enumerate(focus_list):
        fx = 60 + idx * col_w
        fy = 518
        draw.rectangle([fx, fy, fx + 34, fy + 34], fill=(180, 83, 9))
        draw.text((fx + 11, fy + 7), num_str, fill=(255, 255, 255), font=f_focus)
        draw.text((fx + 46, fy + 8), desc, fill=(15, 23, 42), font=f_item)

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


def _add_formatted_runs(
    paragraph,
    text: str,
    base_size_pt: float = 10.5,
    text_color: RGBColor = COLOR_TEXT,
    italic: bool = False,
) -> None:
    """Procesa negritas (**...**) y codigo en linea (`...`) dentro de un parrafo."""
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
                run.italic = italic
                run.font.name = "Consolas" if is_code else "Arial"
                run.font.size = Pt(base_size_pt - 0.5 if is_code else base_size_pt)
                run.font.color.rgb = COLOR_CODE if is_code else text_color
        elif token.startswith("`") and token.endswith("`") and len(token) > 2:
            run = paragraph.add_run(token[1:-1])
            run.italic = italic
            run.font.name = "Consolas"
            run.font.size = Pt(base_size_pt - 0.5)
            run.font.color.rgb = COLOR_CODE
        else:
            run = paragraph.add_run(token)
            run.italic = italic
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

    while i < n:
        raw_line = lines[i]
        stripped = raw_line.strip()

        if not stripped:
            i += 1
            continue

        # Bloques ```screen para insertar contenedor visual de pantalla
        if stripped.startswith("```"):
            lang = stripped[3:].strip().lower()
            i += 1
            code_lines: list[str] = []
            while i < n and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i].strip())
                i += 1
            if i < n:
                i += 1

            if lang == "screen" and code_lines:
                screen_key = code_lines[0]
                if screen_key in SCREEN_SPECS:
                    png_buf = build_screen_container_png(screen_key)
                    p_img = doc.add_paragraph()
                    p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    p_img.paragraph_format.space_before = Pt(6)
                    p_img.paragraph_format.space_after = Pt(2)
                    p_img.add_run().add_picture(png_buf, width=Inches(6.3))
            continue

        # Pies de figura (*Figura X: ...*)
        if stripped.startswith("*Figura ") and stripped.endswith("*"):
            caption_text = stripped[1:-1].strip()
            p_cap = doc.add_paragraph()
            p_cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p_cap.paragraph_format.space_before = Pt(2)
            p_cap.paragraph_format.space_after = Pt(6)
            _add_formatted_runs(p_cap, caption_text, base_size_pt=9.5, text_color=COLOR_SLATE, italic=True)
            i += 1
            continue

        # Bloques de cita / Contenedores de Captura (> ...)
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
    output = generate_docx()
    print(f"Manual de Usuario Word generado exitosamente en: {output} ({output.stat().st_size} bytes)")
