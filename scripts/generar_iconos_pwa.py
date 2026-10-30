#!/usr/bin/env python3
"""Genera los iconos de la PWA Campus a partir del logo institucional (requiere Pillow)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

RAIZ = Path(__file__).resolve().parent.parent
LOGO = RAIZ / "web-admin" / "upa-logo.png"
DESTINO = RAIZ / "web-app" / "icons"
FONDO = (255, 255, 255, 255)


def componer(tamano: int, proporcion: float) -> Image.Image:
    """Centra el logo sobre fondo blanco; `proporcion` es el ancho del logo respecto al lienzo."""
    logo = Image.open(LOGO).convert("RGBA")
    ancho = int(tamano * proporcion)
    alto = int(logo.height * ancho / logo.width)
    logo = logo.resize((ancho, alto), Image.LANCZOS)
    lienzo = Image.new("RGBA", (tamano, tamano), FONDO)
    lienzo.alpha_composite(logo, ((tamano - ancho) // 2, (tamano - alto) // 2))
    return lienzo.convert("RGB")


def main() -> None:
    DESTINO.mkdir(parents=True, exist_ok=True)
    componer(192, 0.78).save(DESTINO / "icon-192.png", optimize=True)
    componer(512, 0.78).save(DESTINO / "icon-512.png", optimize=True)
    # Zona segura maskable: el contenido debe caber en el circulo central del 80 por ciento
    componer(512, 0.58).save(DESTINO / "icon-maskable-512.png", optimize=True)
    componer(180, 0.78).save(DESTINO / "apple-touch-icon.png", optimize=True)
    componer(32, 0.95).save(DESTINO / "favicon-32.png", optimize=True)


if __name__ == "__main__":
    main()
