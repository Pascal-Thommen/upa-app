#!/usr/bin/env python3
"""Generador de la presentacion final de UPA App en formato PowerPoint (.pptx).

Construye `docs/UPA_App_Presentacion_Final.pptx` con exactamente 7 diapositivas
en formato panoramico 16:9 bajo el diseno corporativo de la Universidad Paraguayo
Alemana (UPA), incluyendo tarjetas visuales, comparativas, guia de demostracion
en vivo (formato 5 + 5 minutos) y notas de orador detalladas para Pascal Thommen.
"""

from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

REPO_ROOT = Path(__file__).resolve().parent.parent
PPTX_OUTPUT_PATH = REPO_ROOT / "docs" / "UPA_App_Presentacion_Final.pptx"
UPA_LOGO_PATH = REPO_ROOT / "web-admin" / "upa-logo.png"

# Paleta Corporativa UPA (alineada con web-admin/style.css y web-app/campus.css)
COLOR_UPA_GREEN = RGBColor(108, 147, 57)       # #6C9339
COLOR_UPA_GREEN_DARK = RGBColor(90, 123, 46)   # #5A7B2E
COLOR_UPA_GREEN_SOFT = RGBColor(242, 247, 236) # #F2F7EC
COLOR_NAVY_900 = RGBColor(15, 23, 42)          # #0F172A
COLOR_NAVY_800 = RGBColor(30, 41, 59)          # #1E293B
COLOR_SLATE_600 = RGBColor(71, 85, 105)        # #475569
COLOR_BLUE_UPA = RGBColor(30, 64, 175)         # #1E40AF
COLOR_BLUE_SOFT = RGBColor(239, 246, 255)      # #EFF6FF
COLOR_AMBER = RGBColor(180, 83, 9)             # #B45309
COLOR_AMBER_SOFT = RGBColor(254, 243, 199)     # #FEF3C7
COLOR_RED_URGENT = RGBColor(185, 28, 28)       # #B91C1C
COLOR_RED_SOFT = RGBColor(254, 242, 242)       # #FEF2F2
COLOR_BG_LIGHT = RGBColor(248, 250, 252)       # #F8FAFC
COLOR_WHITE = RGBColor(255, 255, 255)          # #FFFFFF
COLOR_BORDER = RGBColor(203, 213, 225)         # #CBD5E1


def _set_slide_background(slide, color: RGBColor) -> None:
    background = slide.background
    fill = background.fill
    fill.solid()
    fill.fore_color.rgb = color


def _add_header_and_footer(
    slide,
    slide_num: int,
    title_text: str,
    subtitle_text: str,
    timing_badge_text: str,
) -> None:
    """Agrega la barra superior institucional UPA, insignia de tiempo y pie de pagina."""
    _set_slide_background(slide, COLOR_BG_LIGHT)

    # Franja superior verde institucional UPA
    top_bar = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(0.14)
    )
    top_bar.fill.solid()
    top_bar.fill.fore_color.rgb = COLOR_UPA_GREEN
    top_bar.line.fill.background()

    # Bloque de encabezado
    header_box = slide.shapes.add_textbox(Inches(0.55), Inches(0.28), Inches(9.5), Inches(0.95))
    tf = header_box.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_top = tf.margin_right = tf.margin_bottom = 0

    p_title = tf.paragraphs[0]
    p_title.text = title_text
    p_title.font.name = "Arial"
    p_title.font.size = Pt(24)
    p_title.font.bold = True
    p_title.font.color.rgb = COLOR_NAVY_900

    p_sub = tf.add_paragraph()
    p_sub.text = subtitle_text
    p_sub.font.name = "Arial"
    p_sub.font.size = Pt(12.5)
    p_sub.font.color.rgb = COLOR_SLATE_600

    # Insignia de tiempo (Timing Badge arriba a la derecha)
    badge = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE, Inches(10.25), Inches(0.34), Inches(2.55), Inches(0.46)
    )
    badge.fill.solid()
    badge.fill.fore_color.rgb = COLOR_NAVY_900
    badge.line.color.rgb = COLOR_UPA_GREEN
    badge.line.width = Pt(1.5)
    btf = badge.text_frame
    btf.word_wrap = False
    btf.vertical_anchor = MSO_ANCHOR.MIDDLE
    bp = btf.paragraphs[0]
    bp.alignment = PP_ALIGN.CENTER
    bp.text = timing_badge_text
    bp.font.name = "Arial"
    bp.font.size = Pt(11)
    bp.font.bold = True
    bp.font.color.rgb = COLOR_WHITE

    # Linea divisoria sutil bajo el encabezado
    divider = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(0.55), Inches(1.22), Inches(12.23), Inches(0.02)
    )
    divider.fill.solid()
    divider.fill.fore_color.rgb = COLOR_BORDER
    divider.line.fill.background()

    # Pie de pagina institucional
    footer_bar = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(0), Inches(7.08), Inches(13.333), Inches(0.42)
    )
    footer_bar.fill.solid()
    footer_bar.fill.fore_color.rgb = COLOR_NAVY_900
    footer_bar.line.fill.background()

    footer_tb = slide.shapes.add_textbox(Inches(0.55), Inches(7.12), Inches(12.23), Inches(0.32))
    ftf = footer_tb.text_frame
    ftf.margin_left = ftf.margin_top = ftf.margin_right = ftf.margin_bottom = 0
    fp = ftf.paragraphs[0]
    fp.text = (
        f"Universidad Paraguayo Alemana (UPA)  |  UPA App: Plataforma Digital y Campus Movil  "
        f"|  Pascal Thommen, Theresa Bauer, Natasha Colman  |  Diapositiva {slide_num} de 7"
    )
    fp.font.name = "Arial"
    fp.font.size = Pt(9.5)
    fp.font.color.rgb = RGBColor(203, 213, 225)


def _add_card(
    slide,
    left: float,
    top: float,
    width: float,
    height: float,
    header_title: str,
    bullets: list[tuple[str, str]],
    header_color: RGBColor = COLOR_NAVY_900,
    card_bg: RGBColor = COLOR_WHITE,
    border_color: RGBColor = COLOR_BORDER,
    font_size_pt: float = 12.0,
) -> None:
    """Dibuja una tarjeta ejecutiva con barra de titulo y lista de puntos con subtitulo en negrita."""
    card = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE,
        Inches(left),
        Inches(top),
        Inches(width),
        Inches(height),
    )
    card.adjustments[0] = 0.02
    card.fill.solid()
    card.fill.fore_color.rgb = card_bg
    card.line.color.rgb = border_color
    card.line.width = Pt(1.25)

    header = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE,
        Inches(left),
        Inches(top),
        Inches(width),
        Inches(0.48),
    )
    header.adjustments[0] = 0.02
    header.fill.solid()
    header.fill.fore_color.rgb = header_color
    header.line.fill.background()

    htf = header.text_frame
    htf.vertical_anchor = MSO_ANCHOR.MIDDLE
    htf.margin_left = Inches(0.18)
    hp = htf.paragraphs[0]
    hp.text = header_title
    hp.font.name = "Arial"
    hp.font.size = Pt(13)
    hp.font.bold = True
    hp.font.color.rgb = COLOR_WHITE

    body_tb = slide.shapes.add_textbox(
        Inches(left + 0.16),
        Inches(top + 0.56),
        Inches(width - 0.32),
        Inches(height - 0.64),
    )
    btf = body_tb.text_frame
    btf.word_wrap = True
    btf.margin_left = btf.margin_top = btf.margin_right = btf.margin_bottom = 0

    for idx, (lead, detail) in enumerate(bullets):
        p = btf.paragraphs[0] if idx == 0 else btf.add_paragraph()
        p.space_before = Pt(3)
        p.space_after = Pt(5)
        if lead:
            r_lead = p.add_run()
            r_lead.text = f"• {lead}: "
            r_lead.font.name = "Arial"
            r_lead.font.size = Pt(font_size_pt)
            r_lead.font.bold = True
            r_lead.font.color.rgb = COLOR_NAVY_900

            r_det = p.add_run()
            r_det.text = detail
            r_det.font.name = "Arial"
            r_det.font.size = Pt(font_size_pt)
            r_det.font.bold = False
            r_det.font.color.rgb = COLOR_NAVY_800
        else:
            r_det = p.add_run()
            r_det.text = f"• {detail}"
            r_det.font.name = "Arial"
            r_det.font.size = Pt(font_size_pt)
            r_det.font.color.rgb = COLOR_NAVY_800


def _set_speaker_notes(slide, notes_text: str) -> None:
    notes_slide = slide.notes_slide
    tf = notes_slide.notes_text_frame
    tf.text = notes_text


def _build_slide_1_cover(prs: Presentation, blank_layout) -> None:
    slide = prs.slides.add_slide(blank_layout)
    _set_slide_background(slide, COLOR_NAVY_900)

    # Barra lateral decorativa verde UPA
    left_accent = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(0.38), Inches(7.5)
    )
    left_accent.fill.solid()
    left_accent.fill.fore_color.rgb = COLOR_UPA_GREEN
    left_accent.line.fill.background()

    # Tarjeta central de portada
    hero_card = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.95), Inches(0.75), Inches(11.65), Inches(5.95)
    )
    hero_card.adjustments[0] = 0.02
    hero_card.fill.solid()
    hero_card.fill.fore_color.rgb = COLOR_NAVY_800
    hero_card.line.color.rgb = COLOR_UPA_GREEN
    hero_card.line.width = Pt(2)

    # Logo UPA si existe en el repositorio
    if UPA_LOGO_PATH.exists():
        slide.shapes.add_picture(str(UPA_LOGO_PATH), Inches(1.4), Inches(1.1), height=Inches(0.85))

    # Insignia superior de formato 5+5
    format_badge = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE, Inches(8.15), Inches(1.15), Inches(4.0), Inches(0.5)
    )
    format_badge.fill.solid()
    format_badge.fill.fore_color.rgb = COLOR_UPA_GREEN
    format_badge.line.fill.background()
    ftf = format_badge.text_frame
    ftf.vertical_anchor = MSO_ANCHOR.MIDDLE
    fp = ftf.paragraphs[0]
    fp.alignment = PP_ALIGN.CENTER
    fp.text = "Formato 10 Min: 5 Min Presentacion + 5 Min Demo"
    fp.font.name = "Arial"
    fp.font.size = Pt(11.5)
    fp.font.bold = True
    fp.font.color.rgb = COLOR_WHITE

    # Titulo Principal y Subtitulo
    title_tb = slide.shapes.add_textbox(Inches(1.4), Inches(2.2), Inches(10.7), Inches(2.3))
    ttf = title_tb.text_frame
    ttf.word_wrap = True

    p1 = ttf.paragraphs[0]
    p1.text = "UPA App: Plataforma Digital y Campus Movil"
    p1.font.name = "Arial"
    p1.font.size = Pt(36)
    p1.font.bold = True
    p1.font.color.rgb = COLOR_WHITE
    p1.space_after = Pt(10)

    p2 = ttf.add_paragraph()
    p2.text = (
        "Fuente Unica de Verdad (Single Source of Truth) con PWA Estudiantil, "
        "Integracion Google Workspace y Web-Admin Cockpit Asistido por IA"
    )
    p2.font.name = "Arial"
    p2.font.size = Pt(18)
    p2.font.color.rgb = RGBColor(163, 201, 58)
    p2.space_after = Pt(14)

    # Bloque de Autores y Metadatos
    meta_card = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1.4), Inches(4.65), Inches(10.7), Inches(1.65)
    )
    meta_card.adjustments[0] = 0.03
    meta_card.fill.solid()
    meta_card.fill.fore_color.rgb = COLOR_NAVY_900
    meta_card.line.color.rgb = COLOR_BORDER
    meta_card.line.width = Pt(1)

    mtf = meta_card.text_frame
    mtf.word_wrap = True
    mtf.margin_left = Inches(0.28)
    mtf.margin_top = Inches(0.2)

    mp1 = mtf.paragraphs[0]
    mp1.text = "Autores del Proyecto:  Pascal Thommen  |  Theresa Bauer  |  Natasha Colman"
    mp1.font.name = "Arial"
    mp1.font.size = Pt(15.5)
    mp1.font.bold = True
    mp1.font.color.rgb = COLOR_WHITE
    mp1.space_after = Pt(6)

    mp2 = mtf.add_paragraph()
    mp2.text = "Universidad Paraguayo Alemana (UPA) - Carrera de Informatica Empresarial (Business Informatics)"
    mp2.font.name = "Arial"
    mp2.font.size = Pt(13)
    mp2.font.color.rgb = RGBColor(203, 213, 225)
    mp2.space_after = Pt(4)

    mp3 = mtf.add_paragraph()
    mp3.text = (
        "Presentacion Final: Jueves, 5 de noviembre de 2026  |  "
        "Produccion: https://upa.eu1.netbird.services"
    )
    mp3.font.name = "Arial"
    mp3.font.size = Pt(12)
    mp3.font.color.rgb = RGBColor(163, 201, 58)

    _set_speaker_notes(
        slide,
        "FOLIE 1 (00:00 - 00:35 | 35 Sek.):\n"
        "- Begruessung und Vorstellung des Teams: Pascal Thommen, Theresa Bauer, Natasha Colman.\n"
        "- Kurz-Pitch: UPA App ist die zentrale Progressive Web App (PWA) und Redaktionsplattform der UPA.\n"
        "- Ablauf: 5 Minuten Praesentation der Architektur & Entscheidungen + 5 Minuten Live-Demo auf Produktion.",
    )


def _build_slide_2_problem(prs: Presentation, blank_layout) -> None:
    slide = prs.slides.add_slide(blank_layout)
    _add_header_and_footer(
        slide,
        slide_num=2,
        title_text="2. Problemstellung & Zielgruppe: Fragmentierte Kommunikation",
        subtitle_text="Situacion operativa actual en el campus de la UPA (< 1.000 estudiantes) y dolor por audiencia",
        timing_badge_text="Tiempo: 00:35 - 01:20 (45s)",
    )

    # Columna Izquierda: Los 3 Problemas Criticos
    _add_card(
        slide,
        left=0.55,
        top=1.42,
        width=6.0,
        height=5.38,
        header_title="Fragmentacion Comunicacional en 4 Canales Aislados",
        header_color=COLOR_RED_URGENT,
        card_bg=COLOR_WHITE,
        border_color=COLOR_BORDER,
        font_size_pt=12.0,
        bullets=[
            (
                "Dispersion Multicanal (< 1.000 Estudiantes)",
                "La informacion circula separada entre grupos de WhatsApp, Instagram (@upalemana), "
                "correos institucionales y cursos individuales en Google Classroom.",
            ),
            (
                "1. Perdida de Anuncios y Cancelaciones",
                "Cambios de aula, alertas urgentes o suspensiones de clases se entierran entre "
                "cientos de mensajes informales de WhatsApp o correos no leidos a tiempo.",
            ),
            (
                "2. Aviso Presencial Aula por Aula",
                "Por falta de alcance digital efectivo, el personal de la UPA debe recorrer "
                "fisicamente los pasillos y aulas para recordar a los alumnos charlas inminentes.",
            ),
            (
                "3. Sin Registro RSVP ni Agenda Unificada",
                "No existe confirmacion rapida de asistencia para prever el aforo de eventos, y las "
                "entregas de Classroom estan desconectadas del calendario universitario.",
            ),
        ],
    )

    # Columna Derecha Arriba: Audiencia 1 (Estudiantes y Docentes)
    _add_card(
        slide,
        left=6.8,
        top=1.42,
        width=5.98,
        height=2.58,
        header_title="Zielgruppe 1: Estudiantes y Docentes (@upa.edu.py)",
        header_color=COLOR_BLUE_UPA,
        card_bg=COLOR_BLUE_SOFT,
        border_color=COLOR_BLUE_UPA,
        font_size_pt=11.8,
        bullets=[
            (
                "Cero Perdida de Fechas Criticas",
                "Un unico punto de consulta oficial para alertas de emergencia, noticias de su "
                "carrera (TIE, PI, TI) y plazos de entrega de Google Classroom.",
            ),
            (
                "Acceso Movil sin Friccion",
                "Apertura instantanea mediante codigo QR en iPhone y Android sin descargar "
                "aplicaciones pesadas ni exponer su numero de telefono privado.",
            ),
        ],
    )

    # Columna Derecha Abajo: Audiencia 2 (Personal Administrativo y Marketing)
    _add_card(
        slide,
        left=6.8,
        top=4.22,
        width=5.98,
        height=2.58,
        header_title="Zielgruppe 2: Marketing, Coordinacion y Administracion",
        header_color=COLOR_UPA_GREEN,
        card_bg=COLOR_UPA_GREEN_SOFT,
        border_color=COLOR_UPA_GREEN,
        font_size_pt=11.8,
        bullets=[
            (
                "Fin del Trabajo Duplicado",
                "Sincronizacion del feed de Instagram (@upalemana) y extraccion automatica de "
                "datos de afiches con IA en segundos desde el navegador de escritorio.",
            ),
            (
                "Segmentacion y Control de Aforo Real",
                "Envio dirigido por grupos de Google Workspace y lectura nominal de inscritos "
                "(RSVP) protegida exclusivamente para administradores.",
            ),
        ],
    )

    _set_speaker_notes(
        slide,
        "FOLIE 2 (00:35 - 01:20 | 45 Sek.):\n"
        "- An der UPA (< 1.000 Studierende) ist die Kommunikation ueber WhatsApp, Instagram, Mail und Classroom zersplittert.\n"
        "- Konkrete Folge: Wichtige Terminaenderungen gehen unter; Mitarbeitende muessen teils persoenlich von Hoersaal zu Hoersaal gehen.\n"
        "- Zwei klare Zielgruppen: Studierende/Dozierende (Fristen & Events an einem Ort) und Marketing/Verwaltung (weniger Pflegeaufwand, gezielte Reichweite).",
    )


def _build_slide_3_solution(prs: Presentation, blank_layout) -> None:
    slide = prs.slides.add_slide(blank_layout)
    _add_header_and_footer(
        slide,
        slide_num=3,
        title_text="3. Die Loesung: Single Source of Truth PWA + Web-Admin Cockpit",
        subtitle_text="Dos superficies conectadas al mismo nucleo relacional (FastAPI Python 3.11 + PostgreSQL 16)",
        timing_badge_text="Tiempo: 01:20 - 02:10 (50s)",
    )

    # Columna 1: Campus PWA
    _add_card(
        slide,
        left=0.55,
        top=1.42,
        width=3.95,
        height=5.38,
        header_title="1. Campus PWA (web-app/)",
        header_color=COLOR_UPA_GREEN,
        card_bg=COLOR_WHITE,
        border_color=COLOR_UPA_GREEN,
        font_size_pt=11.5,
        bullets=[
            (
                "Landing QR + PWA Instalable",
                "Vista previa movil en escritorio con codigo QR dinamico, Service Worker v1.0.3 (/sw.js) y Web Manifest.",
            ),
            (
                "Muro Unificado (Inicio)",
                "Banners urgentes fijados con vencimiento (expires_at), comunicados UPA y posts de Instagram (@upalemana).",
            ),
            (
                "RSVP de 1 Clic (2 Botones)",
                "Confirmacion inmediata ('Si, asistire' / 'No asistire') con privacidad de conteo para el alumnado.",
            ),
            (
                "Agenda + Google Classroom",
                "Calendario mensual que fusiona eventos UPA y entregas de Classroom en zona horaria America/Asuncion.",
            ),
        ],
    )

    # Columna 2: Nucleo Backend & Base de Datos
    _add_card(
        slide,
        left=4.68,
        top=1.42,
        width=3.95,
        height=5.38,
        header_title="2. Nucleo FastAPI + PostgreSQL 16",
        header_color=COLOR_NAVY_900,
        card_bg=COLOR_BG_LIGHT,
        border_color=COLOR_NAVY_900,
        font_size_pt=11.5,
        bullets=[
            (
                "Arquitectura de 3 Contenedores",
                "upa-frontend (Nginx Alpine), upa-backend (FastAPI :8000) y upa-postgres (PostgreSQL 16 en 127.0.0.1:5432).",
            ),
            (
                "Esquema Depurado (9 Tablas)",
                "users, posts (Single Source of Truth), event_registrations, post_views, admin_audit_logs, device_tokens, audience_groups, user_roles, app_settings.",
            ),
            (
                "SSO @upa.edu.py + Resiliencia",
                "Google OAuth 2.0 estricto con JWT, auto-refresh de Classroom y cache de respaldo en base de datos.",
            ),
            (
                "Integracion Real SociableKIT",
                "Ingesta de @upalemana con descarga local de medios para evitar enlaces caducados del CDN.",
            ),
        ],
    )

    # Columna 3: Web-Admin Cockpit
    _add_card(
        slide,
        left=8.81,
        top=1.42,
        width=3.97,
        height=5.38,
        header_title="3. Web-Admin Cockpit (/dashboard/)",
        header_color=COLOR_BLUE_UPA,
        card_bg=COLOR_WHITE,
        border_color=COLOR_BLUE_UPA,
        font_size_pt=11.5,
        bullets=[
            (
                "Editor Unificado + Deep Linking",
                "Rutas directas (/dashboard/publicaciones/:id y /nueva) con soporte de historial HTML5 y recarga F5.",
            ),
            (
                "Autocompletar con IA (Gemini)",
                "Analiza afiches subidos (JPG/PNG/WEBP) y rellena titulo, resumen, fecha, hora, lugar y RSVP sin alucinar.",
            ),
            (
                "Matriz RBAC de 6 Permisos",
                "Minimo privilegio: publicaciones, grupos, roles, ia, apis e historial con proteccion del ultimo admin.",
            ),
            (
                "Auditoria y Diagnostico en Vivo",
                "Trazabilidad inmutable campo por campo en Historial y monitor de salud de APIs y PostgreSQL.",
            ),
        ],
    )

    _set_speaker_notes(
        slide,
        "FOLIE 3 (01:20 - 02:10 | 50 Sek.):\n"
        "- Unsere Loesung vereint alles in einer Single Source of Truth (Tabelle posts in PostgreSQL 16 mit 9 bereinigten Tabellen).\n"
        "- Links die Studenten-PWA: QR-Code Einstieg, Eilmeldungen, Instagram-Feed, 1-Klick RSVP und Google Classroom Agenda.\n"
        "- Rechts das Web-Admin Cockpit fuer Marketing: Deep Linking, KI-Plakat-Autocomplete via Gemini und 6-Rechte RBAC-Matrix.",
    )


def _build_slide_4_pivot(prs: Presentation, blank_layout) -> None:
    slide = prs.slides.add_slide(blank_layout)
    _add_header_and_footer(
        slide,
        slide_num=4,
        title_text="4. Strategischer Pivot: Warum PWA statt nativer Android-App",
        subtitle_text="Decision arquitectonica clave para maximizar adopcion estudiantil, compatibilidad iOS/Android y agilidad",
        timing_badge_text="Tiempo: 02:10 - 03:00 (50s)",
    )

    # Tres tarjetas horizontales para los 3 pilares del Pivot
    _add_card(
        slide,
        left=0.55,
        top=1.42,
        width=3.95,
        height=3.65,
        header_title="1. Eliminacion de Barrera de Tiendas",
        header_color=COLOR_UPA_GREEN,
        card_bg=COLOR_WHITE,
        border_color=COLOR_UPA_GREEN,
        font_size_pt=11.5,
        bullets=[
            (
                "Cero Costos y Burocracia",
                "Evita la suscripcion anual de Apple App Store (99 USD/ano + hardware Mac) y las demoras de revision en Google Play.",
            ),
            (
                "Adopcion en 2 Segundos via QR",
                "Los estudiantes rechazan instalar apps pesadas solo para avisos. Con la PWA escanean el QR y anclan el icono a su pantalla (standalone).",
            ),
        ],
    )

    _add_card(
        slide,
        left=4.68,
        top=1.42,
        width=3.95,
        height=3.65,
        header_title="2. Independencia de Plataforma",
        header_color=COLOR_BLUE_UPA,
        card_bg=COLOR_WHITE,
        border_color=COLOR_BLUE_UPA,
        font_size_pt=11.5,
        bullets=[
            (
                "Alta Presencia de iPhone en la UPA",
                "Una app nativa solo para Android habria dejado fuera a la gran proporcion de alumnos con iOS en el campus.",
            ),
            (
                "Base de Codigo Unica (Single Codebase)",
                "Un solo frontend estandar funciona con paridad del 100% en iOS (Safari), Android (Chrome) y computadoras de escritorio.",
            ),
        ],
    )

    _add_card(
        slide,
        left=8.81,
        top=1.42,
        width=3.97,
        height=3.65,
        header_title="3. Velocidad de Despliegue y Futuro",
        header_color=COLOR_NAVY_900,
        card_bg=COLOR_WHITE,
        border_color=COLOR_NAVY_900,
        font_size_pt=11.5,
        bullets=[
            (
                "Actualizaciones Instantaneas",
                "El Service Worker (v1.0.3) activa mejoras al instante al abrir la app, sin depender de descargas manuales del usuario.",
            ),
            (
                "TWA + Python AI-First Backend",
                "Incluye assetlinks.json para empaquetado futuro en Play Store (TWA) y backend Python ideal para IA con Gemini.",
            ),
        ],
    )

    # Tabla resumen comparativa inferior
    tbl_shape = slide.shapes.add_table(3, 4, Inches(0.55), Inches(5.22), Inches(12.23), Inches(1.58))
    table = tbl_shape.table
    table.columns[0].width = Inches(2.63)
    table.columns[1].width = Inches(3.2)
    table.columns[2].width = Inches(3.2)
    table.columns[3].width = Inches(3.2)

    rows_data = [
        [
            "Criterio Evaluado",
            "Barrera de Entrada (Onboarding)",
            "Cobertura de Dispositivos UPA",
            "Ciclo de Actualizacion y Mantenimiento",
        ],
        [
            "App Android Nativa (Idea Inicial)",
            "Alta: Descarga de tienda o APK manual bloqueado por seguridad",
            "Parcial: Excluye usuarios de iPhone (iOS) y requiere doble desarrollo",
            "Lento: Requiere compilacion, revision de tienda y descarga manual",
        ],
        [
            "UPA Campus PWA (Solucion Final)",
            "Nula: Escaneo de codigo QR e instalacion directa en 2 segundos",
            "Total (100%): Android, iPhone (iOS), Windows, macOS y Linux",
            "Instantaneo: Despliegue continuo en Docker y Service Worker v1.0.3",
        ],
    ]

    for r_idx, row in enumerate(rows_data):
        for c_idx, val in enumerate(row):
            cell = table.cell(r_idx, c_idx)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.fill.solid()
            if r_idx == 0:
                cell.fill.fore_color.rgb = COLOR_NAVY_900
            elif r_idx == 1:
                cell.fill.fore_color.rgb = COLOR_RED_SOFT
            else:
                cell.fill.fore_color.rgb = COLOR_UPA_GREEN_SOFT

            p = cell.text_frame.paragraphs[0]
            p.text = val
            p.font.name = "Arial"
            p.font.size = Pt(10.0)
            p.font.bold = r_idx == 0 or c_idx == 0
            p.font.color.rgb = COLOR_WHITE if r_idx == 0 else COLOR_NAVY_900

    _set_speaker_notes(
        slide,
        "FOLIE 4 (02:10 - 03:00 | 50 Sek.):\n"
        "- Warum der strategische Wechsel von einer nativen Android-App zur PWA?\n"
        "- 1. Store-Huerde: Keine 99 USD/Jahr Apple-Gebuehr, kein Store-Zwang; direkter Einstieg per QR-Code.\n"
        "- 2. Plattformunabhaengigkeit: Viele UPA-Studierende nutzen iPhones (iOS); unsere PWA laeuft auf iOS, Android und Desktop identisch.\n"
        "- 3. Deployment-Geschwindigkeit: Sofortige Updates via Service Worker v1.0.3; TWA-Unterstuetzung fuer spaeteres Play-Store-Listing ist integriert.",
    )


def _build_slide_5_live_demo(prs: Presentation, blank_layout) -> None:
    slide = prs.slides.add_slide(blank_layout)
    _add_header_and_footer(
        slide,
        slide_num=5,
        title_text="5. Live-Demonstration Leitplan: Die 5-Minuten User Journey",
        subtitle_text="Recorrido interactivo en vivo sobre la instancia productiva (https://upa.eu1.netbird.services)",
        timing_badge_text="Intro 30s + Demo 05:00 Min",
    )

    steps = [
        (
            "Paso 1 (Min 00:00 - 01:00)",
            "QR-Code Scan am Desktop",
            COLOR_NAVY_900,
            COLOR_WHITE,
            [
                (
                    "Landing Page Interactiva",
                    "Apertura en escritorio con vista previa del telefono en vivo (#phone-mockup).",
                ),
                (
                    "Escaneo QR Instantaneo",
                    "Acceso movil inmediato sin tiendas de apps y guia de instalacion en pantalla de inicio.",
                ),
                (
                    "SSO Institucional",
                    "Inicio de sesion seguro con Google OAuth 2.0 restringido al dominio @upa.edu.py.",
                ),
            ],
        ),
        (
            "Paso 2 (Min 01:00 - 02:15)",
            "PWA Feed & Eilmeldung",
            COLOR_RED_URGENT,
            COLOR_WHITE,
            [
                (
                    "Banner de Alerta Urgente",
                    "Visualizacion destacada en la parte superior con fecha de expiracion automatica.",
                ),
                (
                    "Muro Unificado + Instagram",
                    "Comunicados oficiales combinados con posts sincronizados de @upalemana via SociableKIT.",
                ),
                (
                    "Filtros por Audiencia",
                    "Segmentacion automatica segun carrera y grupos de Google Workspace del alumno.",
                ),
            ],
        ),
        (
            "Paso 3 (Min 02:15 - 03:30)",
            "1-Klick RSVP & Agenda",
            COLOR_BLUE_UPA,
            COLOR_WHITE,
            [
                (
                    "Inscripcion en 1 Toque",
                    "Patron de dos botones ('Si, asistire' / 'No asistire') con persistencia inmediata.",
                ),
                (
                    "Privacidad Estudiantil",
                    "El conteo y la lista nominal de asistentes quedan ocultos al publico y visibles solo a admins.",
                ),
                (
                    "Agenda + Classroom Sync",
                    "Calendario mensual con eventos confirmados y entregas de Google Classroom (America/Asuncion).",
                ),
            ],
        ),
        (
            "Paso 4 (Min 03:30 - 05:00)",
            "Web-Admin KI-Extraktion",
            COLOR_UPA_GREEN,
            COLOR_WHITE,
            [
                (
                    "Subida de Afiche Real",
                    "Ingreso a /dashboard/publicaciones/nueva y carga del flyer grafico de un evento.",
                ),
                (
                    "Boton Autocompletar con IA",
                    "Gemini analiza imagen y texto (768px optimizado) y extrae titulo, fecha, hora y lugar.",
                ),
                (
                    "Publicacion y Auditoria",
                    "Guardado en la Fuente Unica de Verdad, aparicion en la PWA y registro en Historial.",
                ),
            ],
        ),
    ]

    col_w = 2.92
    gap = 0.18
    start_x = 0.55

    for idx, (time_label, step_title, hdr_color, bg_color, bullets) in enumerate(steps):
        x = start_x + idx * (col_w + gap)

        # Insignia de tiempo del paso de demo
        time_pill = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(1.42), Inches(col_w), Inches(0.42)
        )
        time_pill.fill.solid()
        time_pill.fill.fore_color.rgb = COLOR_UPA_GREEN_SOFT
        time_pill.line.color.rgb = hdr_color
        time_pill.line.width = Pt(1.5)
        ptf = time_pill.text_frame
        ptf.vertical_anchor = MSO_ANCHOR.MIDDLE
        pp = ptf.paragraphs[0]
        pp.alignment = PP_ALIGN.CENTER
        pp.text = time_label
        pp.font.name = "Arial"
        pp.font.size = Pt(11)
        pp.font.bold = True
        pp.font.color.rgb = hdr_color

        _add_card(
            slide,
            left=x,
            top=1.94,
            width=col_w,
            height=4.85,
            header_title=step_title,
            header_color=hdr_color,
            card_bg=bg_color,
            border_color=hdr_color,
            font_size_pt=11.0,
            bullets=bullets,
        )

    _set_speaker_notes(
        slide,
        "FOLIE 5 (03:00 - 03:30 Intro + 03:30 - 08:30 Live-Demo | 5 Minuten Live-Demonstration):\n"
        "- Station 1 (1 Min): Desktop Landingpage zeigen, QR-Code Scan demonstrieren und Google Login (@upa.edu.py).\n"
        "- Station 2 (1:15 Min): PWA Feed mit roter Eilmeldung (Banner urgente) und synchronisierten Instagram-Beitraegen (@upalemana).\n"
        "- Station 3 (1:15 Min): 1-Klick RSVP ('Si, asistire') anklicken und im Tab 'Agenda' das Event + Google Classroom Fristen zeigen.\n"
        "- Station 4 (1:30 Min): Im Web-Admin (/dashboard/publicaciones/nueva) ein Plakat hochladen, 'Autocompletar con IA' klicken und live veroeffentlichen.",
    )


def _build_slide_6_challenges_ai(prs: Presentation, blank_layout) -> None:
    slide = prs.slides.add_slide(blank_layout)
    _add_header_and_footer(
        slide,
        slide_num=6,
        title_text="6. Herausforderungen & KI-Entwicklung: Qualitaet und Zero-Mock",
        subtitle_text="Aprendizajes reales de ingenieria: de modelos Flash iniciales a Gemini 4 Argon y ciclo autonomo verificado",
        timing_badge_text="Tiempo: 08:30 - 09:15 (45s)",
    )

    # Tarjeta 1: Cambio de Flash a Gemini 4 Argon
    _add_card(
        slide,
        left=0.55,
        top=1.42,
        width=3.95,
        height=5.38,
        header_title="1. De Flash a Gemini 4 Argon",
        header_color=COLOR_AMBER,
        card_bg=COLOR_WHITE,
        border_color=COLOR_AMBER,
        font_size_pt=11.5,
        bullets=[
            (
                "Dificultad Inicial con Flash",
                "En las primeras iteraciones se utilizaron modelos ligeros Flash para generar codigo, causando regresiones y alucinaciones.",
            ),
            (
                "Cambio Estricto a Gemini 4 Argon",
                "Se prohibio el uso de Flash/DeepSeek para ingenieria, adoptando exclusivamente Gemini 4 Argon con diseno guiado por pruebas.",
            ),
            (
                "IA Productiva sin Alucinacion",
                "En el backend productivo se implemento anclaje factual determinista (temperatura 0.0), optimizacion de imagen a 768px y fallback gemma-4-26b-a4b-it.",
            ),
        ],
    )

    # Tarjeta 2: Doctrina Zero-Mock
    _add_card(
        slide,
        left=4.68,
        top=1.42,
        width=3.95,
        height=5.38,
        header_title="2. Doctrina Zero-Mock Estricta",
        header_color=COLOR_NAVY_900,
        card_bg=COLOR_WHITE,
        border_color=COLOR_NAVY_900,
        font_size_pt=11.5,
        bullets=[
            (
                "Cero Botones Falsos o Datos Dummy",
                "Prohibicion absoluta de superficies simuladas, banderas MOCK_MODE o respuestas estaticas en el codigo productivo.",
            ),
            (
                "Persistencia Real de Extremo a Extremo",
                "Cada clic en la PWA y en el Cockpit ejecuta transacciones ACID reales sobre las 9 tablas de PostgreSQL 16.",
            ),
            (
                "Auditor Automatizado (Gatekeeper)",
                "El script scripts/audit_zero_mock.py analiza el arbol AST de Python y el codigo JS antes de permitir cualquier fusion.",
            ),
        ],
    )

    # Tarjeta 3: Ciclo de Desarrollo Autonomo
    _add_card(
        slide,
        left=8.81,
        top=1.42,
        width=3.97,
        height=5.38,
        header_title="3. Ciclo de Ingenieria Autonomo",
        header_color=COLOR_UPA_GREEN,
        card_bg=COLOR_WHITE,
        border_color=COLOR_UPA_GREEN,
        font_size_pt=11.5,
        bullets=[
            (
                "Orquestacion con Multica",
                "Flujo cerrado desde la especificacion del requerimiento hasta la verificacion en vivo y despliegue automatizado.",
            ),
            (
                "Mas de 230 Pruebas Automatizadas",
                "Suite completa en Pytest (backend/tests) y Node.js Test Runner (web-app/tests y web-admin/tests).",
            ),
            (
                "Calidad Estatica al 100%",
                "Verificacion obligatoria de tipos con Pyright y analisis con Ruff Linter antes de cada actualizacion de contenedores.",
            ),
        ],
    )

    _set_speaker_notes(
        slide,
        "FOLIE 6 (08:30 - 09:15 | 45 Sek.):\n"
        "- Groesstes Learning: Anfangs mit Flash-Modellen programmiert (fuehrte zu Fehlern/Halluzinationen) -> strikter Wechsel auf Gemini 4 Argon.\n"
        "- Zero-Mock Doktrin: Keine Dummy-Daten oder Scheinoberflaechen im Produktivkern, automatisiert geprueft durch audit_zero_mock.py.\n"
        "- Autonome Entwicklungsschleife ueber Multica mit ueber 230 automatisierten Tests (Pytest, Node.js, Pyright, Ruff).",
    )


def _build_slide_7_roadmap(prs: Presentation, blank_layout) -> None:
    slide = prs.slides.add_slide(blank_layout)
    _add_header_and_footer(
        slide,
        slide_num=7,
        title_text="7. Roadmap: Naechste 30 Tage und 6 Monate",
        subtitle_text="Plan de transicion hacia infraestructura oficial de la UPA y expansion al Portal UPA Academico",
        timing_badge_text="Tiempo: 09:15 - 10:00 (45s)",
    )

    # Columna Izquierda: 30 Dias (UPA Domain & Offizielles Hosting)
    _add_card(
        slide,
        left=0.55,
        top=1.42,
        width=5.95,
        height=4.45,
        header_title="Horizonte 1: Proximos 30 Dias (Go-Live Institucional UPA)",
        header_color=COLOR_UPA_GREEN,
        card_bg=COLOR_WHITE,
        border_color=COLOR_UPA_GREEN,
        font_size_pt=12.0,
        bullets=[
            (
                "Dominio Oficial y Hosting UPA",
                "Migracion de los 3 contenedores Docker al servidor institucional bajo el subdominio oficial app.upa.edu.py.",
            ),
            (
                "Activacion de Notificaciones Push (FCM)",
                "Conexion de credenciales productivas de Firebase Cloud Messaging sobre el servicio ya implementado (push.py y device_tokens).",
            ),
            (
                "API Oficial de Meta (Instagram Graph API)",
                "Reemplazo de la sincronizacion manual en SociableKIT Free Tier por ingesta automatica con cuenta comercial de la UPA.",
            ),
        ],
    )

    # Columna Derecha: 6 Meses (UPA Academico Portal)
    _add_card(
        slide,
        left=6.83,
        top=1.42,
        width=5.95,
        height=4.45,
        header_title="Horizonte 2: Proximos 6 Meses (Portal UPA Academico)",
        header_color=COLOR_BLUE_UPA,
        card_bg=COLOR_WHITE,
        border_color=COLOR_BLUE_UPA,
        font_size_pt=12.0,
        bullets=[
            (
                "Integracion con el Portal UPA Academico",
                "Consulta de calificaciones, inscripcion a materias y examenes, y estado administrativo directamente desde la PWA movil.",
            ),
            (
                "Carnet Estudiantil Digital y Encuestas",
                "Identificacion universitaria con codigo QR verificable en campus, reserva de salas de estudio y encuestas docentes.",
            ),
            (
                "Publicacion Opcional en Play Store (TWA)",
                "Empaquetado directo mediante Trusted Web Activity usando el archivo assetlinks.json ya incluido en la PWA.",
            ),
        ],
    )

    # Banner inferior de cierre
    closing_banner = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.55), Inches(6.05), Inches(12.23), Inches(0.82)
    )
    closing_banner.adjustments[0] = 0.04
    closing_banner.fill.solid()
    closing_banner.fill.fore_color.rgb = COLOR_NAVY_900
    closing_banner.line.color.rgb = COLOR_UPA_GREEN
    closing_banner.line.width = Pt(1.5)

    ctf = closing_banner.text_frame
    ctf.vertical_anchor = MSO_ANCHOR.MIDDLE
    cp = ctf.paragraphs[0]
    cp.alignment = PP_ALIGN.CENTER
    cp.text = (
        "UPA App esta hoy 100% operativa en produccion: una base solida, verificada y lista "
        "para escalar la experiencia digital de la Universidad Paraguayo Alemana. Muchas gracias."
    )
    cp.font.name = "Arial"
    cp.font.size = Pt(13)
    cp.font.bold = True
    cp.font.color.rgb = COLOR_WHITE

    _set_speaker_notes(
        slide,
        "FOLIE 7 (09:15 - 10:00 | 45 Sek.):\n"
        "- 30-Tage-Ziel: Umzug auf offizielles UPA-Hosting unter der Domain app.upa.edu.py, Aktivierung von Firebase Push und Meta Graph API.\n"
        "- 6-Monate-Ziel: Ausbau zum vollintegrierten UPA Academico Portal (Noten, Kurseinschreibung, digitaler Studierendenausweis, TWA Play Store).\n"
        "- Dank an das Plenum und Eröffnung der Fragerunde.",
    )


def generate_pptx(output_path: Path = PPTX_OUTPUT_PATH) -> Path:
    """Genera el archivo PowerPoint de 7 diapositivas en la ruta indicada."""
    target_path = Path(output_path)
    if target_path.suffix.lower() != ".pptx":
        raise ValueError("El archivo de salida debe tener extension .pptx")

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank_layout = prs.slide_layouts[6]

    _build_slide_1_cover(prs, blank_layout)
    _build_slide_2_problem(prs, blank_layout)
    _build_slide_3_solution(prs, blank_layout)
    _build_slide_4_pivot(prs, blank_layout)
    _build_slide_5_live_demo(prs, blank_layout)
    _build_slide_6_challenges_ai(prs, blank_layout)
    _build_slide_7_roadmap(prs, blank_layout)

    target_path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(target_path))
    return target_path


if __name__ == "__main__":
    generated = generate_pptx()
    print(f"Presentacion PowerPoint generada exitosamente en: {generated} ({generated.stat().st_size} bytes)")
