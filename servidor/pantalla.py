"""Captura de pantalla para el control remoto, con ps/pantalla.ps1 (queda abierto)."""

import base64
import threading

import acciones
import entrada

SIMULAR = acciones.SIMULAR
_ayudante = acciones.AyudantePS("pantalla.ps1", lambda: [])
_bloqueo = threading.Lock()


def _simulada():
    """Un "escritorio" de prueba en SVG, con el cursor donde lo dejó el mouse simulado."""
    x, y = entrada._simulado["x"], entrada._simulado["y"]
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080" viewBox="0 0 1920 1080">
<defs><linearGradient id="f" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#2b3a55"/><stop offset="1" stop-color="#0d1117"/></linearGradient></defs>
<rect width="1920" height="1080" fill="url(#f)"/>
<rect x="360" y="180" width="1200" height="680" rx="12" fill="#f3f3f3"/>
<rect x="360" y="180" width="1200" height="48" rx="12" fill="#e1e1e1"/>
<text x="400" y="212" font-family="Segoe UI, sans-serif" font-size="22" fill="#333">Escritorio de prueba</text>
<text x="400" y="300" font-family="Segoe UI, sans-serif" font-size="40" fill="#222">ControlPC: control remoto (modo simulado)</text>
<rect x="0" y="1032" width="1920" height="48" fill="#1c1c1c"/>
<path d="M{x} {y} l0 34 l9 -8 l7 15 l6 -3 l-7 -15 l12 0 z" fill="#fff" stroke="#000" stroke-width="2"/>
</svg>"""
    return svg.encode("utf-8"), "image/svg+xml", 1920, 1080


def capturar(ancho_maximo=1280, calidad=60):
    """(bytes, tipo, ancho_real, alto_real) o None si no se pudo (p. ej. PC bloqueada)."""
    if SIMULAR:
        return _simulada()
    ancho_maximo = max(320, min(int(ancho_maximo), 2560))
    calidad = max(20, min(int(calidad), 90))
    with _bloqueo:
        respuesta = _ayudante.pedir(f"captura {ancho_maximo} {calidad}", espera=15)
    if not respuesta or "jpeg" not in respuesta:
        return None
    return base64.b64decode(respuesta["jpeg"]), "image/jpeg", respuesta["ancho"], respuesta["alto"]
