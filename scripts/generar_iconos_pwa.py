#!/usr/bin/env python3
"""Genera los iconos de la PWA Campus a partir del signet vectorial UPA (requiere Pillow)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "web-app" / "icons"
FONDO = (255, 255, 255, 255)
COLOR_UPA = (108, 147, 57, 255)  # #6c9339


def _render_signet_mask(ancho: int, alto: int) -> Image.Image:
    """Renderiza con supersampling 4x el signet vectorial de 3 letras UPA (viewBox 0 0 152 58)."""
    escala = 4
    w = max(1, ancho * escala)
    h = max(1, alto * escala)
    sx = w / 152.0
    sy = h / 58.0

    def pt(x: float, y: float) -> tuple[float, float]:
        return (x * sx, y * sy)

    # U: M2 2 H20 V35 C20 41 21.8 44 25 44 C28.2 44 30 41 30 35 V2 H48 V35 C48 49.5 39 56 25 56 C11 56 2 49.5 2 35 Z
    def cubic(p0, p1, p2, p3, steps=24):
        out = []
        for i in range(1, steps + 1):
            t = i / steps
            mt = 1 - t
            x = mt**3 * p0[0] + 3 * mt**2 * t * p1[0] + 3 * mt * t**2 * p2[0] + t**3 * p3[0]
            y = mt**3 * p0[1] + 3 * mt**2 * t * p1[1] + 3 * mt * t**2 * p2[1] + t**3 * p3[1]
            out.append(pt(x, y))
        return out

    u_pts = [pt(2, 2), pt(20, 2), pt(20, 35)]
    u_pts.extend(cubic((20, 35), (20, 41), (21.8, 44), (25, 44)))
    u_pts.extend(cubic((25, 44), (28.2, 44), (30, 41), (30, 35)))
    u_pts.extend([pt(30, 2), pt(48, 2), pt(48, 35)])
    u_pts.extend(cubic((48, 35), (48, 49.5), (39, 56), (25, 56)))
    u_pts.extend(cubic((25, 56), (11, 56), (2, 49.5), (2, 35)))

    # P exterior y hueco interior
    p_outer = [pt(56, 2), pt(82, 2)]
    p_outer.extend(cubic((82, 2), (93, 2), (99, 8.5), (99, 20)))
    p_outer.extend(cubic((99, 20), (99, 31.5), (93, 38), (82, 38)))
    p_outer.extend([pt(74, 38), pt(74, 55), pt(56, 55)])

    p_inner = [pt(74, 14), pt(80, 14)]
    p_inner.extend(cubic((80, 14), (83.5, 14), (85.5, 16.2), (85.5, 20)))
    p_inner.extend(cubic((85.5, 20), (85.5, 23.8), (83.5, 26), (80, 26)))
    p_inner.extend([pt(74, 26)])

    # A exterior y hueco interior
    a_outer = [
        pt(116, 2),
        pt(134, 2),
        pt(150, 55),
        pt(132, 55),
        pt(129.2, 44),
        pt(120.8, 44),
        pt(118, 55),
        pt(100, 55),
    ]
    a_inner = [pt(125, 16), pt(128.2, 32), pt(121.8, 32)]

    outer = Image.new("L", (w, h), 0)
    draw_outer = ImageDraw.Draw(outer)
    draw_outer.polygon(u_pts, fill=255)
    draw_outer.polygon(p_outer, fill=255)
    draw_outer.polygon(a_outer, fill=255)

    holes = Image.new("L", (w, h), 0)
    draw_holes = ImageDraw.Draw(holes)
    draw_holes.polygon(p_inner, fill=255)
    draw_holes.polygon(a_inner, fill=255)

    mask = ImageChops.subtract(outer, holes)
    return mask.resize((ancho, alto), Image.LANCZOS)


def componer(tamano: int, proporcion: float) -> Image.Image:
    """Centra el signet vectorial UPA sobre fondo blanco limpio."""
    ancho = max(1, int(tamano * proporcion))
    alto = max(1, int(round(ancho * 58 / 152)))
    mask = _render_signet_mask(ancho, alto)
    capa_color = Image.new("RGBA", (ancho, alto), COLOR_UPA)
    signet = Image.new("RGBA", (ancho, alto), (0, 0, 0, 0))
    signet.paste(capa_color, (0, 0), mask)

    lienzo = Image.new("RGBA", (tamano, tamano), FONDO)
    lienzo.alpha_composite(signet, ((tamano - ancho) // 2, (tamano - alto) // 2))
    return lienzo.convert("RGB")


def main() -> None:
    DESTINO.mkdir(parents=True, exist_ok=True)
    componer(192, 0.78).save(DESTINO / "icon-192.png", optimize=True)
    componer(512, 0.78).save(DESTINO / "icon-512.png", optimize=True)
    # Zona segura maskable: el contenido debe caber en el circulo central del 80 por ciento
    componer(512, 0.58).save(DESTINO / "icon-maskable-512.png", optimize=True)
    componer(180, 0.78).save(DESTINO / "apple-touch-icon.png", optimize=True)
    componer(32, 0.92).save(DESTINO / "favicon-32.png", optimize=True)


if __name__ == "__main__":
    main()
    shutil_dst = RAIZ / "web-admin" / "favicon-32.png"
    componer(32, 0.92).save(shutil_dst, optimize=True)

