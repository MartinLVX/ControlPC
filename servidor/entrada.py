"""Mouse y teclado de Windows para el control remoto (ctypes, sin paquetes extra).

Las posiciones llegan normalizadas (0 a 1 sobre la pantalla principal), así no
importa a qué tamaño se ve la captura en el celular.
"""

import ctypes
import sys
import threading
from ctypes import wintypes

import acciones

SIMULAR = acciones.SIMULAR

if sys.platform == "win32":
    user32 = ctypes.windll.user32
    # Píxeles reales también con escala de pantalla (125 %, 150 %…), igual que la captura.
    try:
        if not user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        user32.SetProcessDPIAware()

ULONG_PTR = ctypes.c_size_t


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class _UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _UNION)]


INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP = 0x0008, 0x0010
MOUSEEVENTF_WHEEL = 0x0800
KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 0x0001, 0x0002, 0x0004

TECLAS = {
    "enter": 0x0D, "retroceso": 0x08, "tab": 0x09, "esc": 0x1B, "espacio": 0x20,
    "izquierda": 0x25, "arriba": 0x26, "derecha": 0x27, "abajo": 0x28,
    "inicio": 0x24, "fin": 0x23, "repag": 0x21, "avpag": 0x22, "suprimir": 0x2E,
    "win": 0x5B, "ctrl": 0x11, "alt": 0x12, "shift": 0x10,
    **{f"f{n}": 0x6F + n for n in range(1, 13)},
}
# Estas teclas necesitan la marca "extendida" para que Windows no las confunda con el teclado numérico.
EXTENDIDAS = {0x25, 0x26, 0x27, 0x28, 0x24, 0x23, 0x21, 0x22, 0x2E, 0x5B}

historial = acciones.historial
_bloqueo = threading.Lock()
_simulado = {"x": 500, "y": 300}


def _enviar(*entradas):
    arreglo = (INPUT * len(entradas))(*entradas)
    user32.SendInput(len(entradas), arreglo, ctypes.sizeof(INPUT))


def _raton(banderas, datos=0):
    entrada = INPUT(type=INPUT_MOUSE)
    entrada.u.mi = MOUSEINPUT(0, 0, ctypes.c_uint32(datos).value, banderas, 0, 0)
    return entrada


def _tecla(vk=0, escaneo=0, banderas=0):
    if vk in EXTENDIDAS:
        banderas |= KEYEVENTF_EXTENDEDKEY
    entrada = INPUT(type=INPUT_KEYBOARD)
    entrada.u.ki = KEYBDINPUT(vk, escaneo, banderas, 0, 0)
    return entrada


def tamano_pantalla():
    if SIMULAR:
        return 1920, 1080
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def _a_pixeles(x, y):
    ancho, alto = tamano_pantalla()
    x = min(max(float(x), 0.0), 1.0)
    y = min(max(float(y), 0.0), 1.0)
    return round(x * (ancho - 1)), round(y * (alto - 1))


# --- Mouse -----------------------------------------------------------------------------

def mover(x, y):
    """Lleva el cursor a la posición normalizada (x, y)."""
    px, py = _a_pixeles(x, y)
    if SIMULAR:
        _simulado.update(x=px, y=py)
        historial.append(f"mover {px},{py}")
        return
    user32.SetCursorPos(px, py)


def mover_relativo(dx, dy):
    """Mueve el cursor dx, dy píxeles de la pantalla (modo trackpad)."""
    ancho, alto = tamano_pantalla()
    if SIMULAR:
        _simulado.update(x=min(max(_simulado["x"] + round(dx), 0), ancho - 1),
                         y=min(max(_simulado["y"] + round(dy), 0), alto - 1))
        historial.append(f"mover {_simulado['x']},{_simulado['y']}")
        return
    punto = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(punto))
    user32.SetCursorPos(min(max(punto.x + round(dx), 0), ancho - 1), min(max(punto.y + round(dy), 0), alto - 1))


def boton(cual="izquierdo", accion="clic", veces=1):
    """accion: "clic", "bajar" o "subir" (para arrastrar)."""
    abajo, arriba = ((MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP) if cual == "derecho"
                     else (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP))
    if SIMULAR:
        historial.append(f"{accion} {cual}" + (f" x{veces}" if veces > 1 else ""))
        return
    if accion == "bajar":
        _enviar(_raton(abajo))
    elif accion == "subir":
        _enviar(_raton(arriba))
    else:
        _enviar(*[_raton(b) for _ in range(max(1, min(int(veces), 3))) for b in (abajo, arriba)])


def rueda(pasos):
    """Positivo = hacia arriba. Un paso equivale a un clic de la rueda (120)."""
    if SIMULAR:
        historial.append(f"rueda {pasos}")
        return
    _enviar(_raton(MOUSEEVENTF_WHEEL, int(round(float(pasos) * 120))))


# --- Teclado ---------------------------------------------------------------------------

def escribir(texto):
    """Escribe texto tal cual (acentos, ñ, emojis) con eventos Unicode."""
    texto = str(texto)[:500]
    if SIMULAR:
        historial.append(f"escribir {texto}")
        return
    entradas = []
    for caracter in texto:
        if caracter == "\n":
            entradas += [_tecla(TECLAS["enter"]), _tecla(TECLAS["enter"], banderas=KEYEVENTF_KEYUP)]
            continue
        codigo = caracter.encode("utf-16-le")
        for i in range(0, len(codigo), 2):  # los emojis ocupan dos unidades UTF-16
            unidad = int.from_bytes(codigo[i:i + 2], "little")
            entradas += [_tecla(0, unidad, KEYEVENTF_UNICODE), _tecla(0, unidad, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)]
    if entradas:
        _enviar(*entradas)


def _vk(nombre):
    nombre = str(nombre).lower()
    if nombre in TECLAS:
        return TECLAS[nombre]
    if len(nombre) == 1 and nombre.isascii() and nombre.isalnum():
        return ord(nombre.upper())
    raise ValueError(f"Tecla desconocida: {nombre}")


def teclas(nombres):
    """Pulsa una tecla o una combinación, p. ej. ["enter"], ["ctrl", "c"], ["alt", "tab"]."""
    if isinstance(nombres, str):
        nombres = [nombres]
    codigos = [_vk(n) for n in list(nombres)[:4]]
    if SIMULAR:
        historial.append("teclas " + "+".join(str(n).lower() for n in nombres))
        return
    _enviar(*[_tecla(c) for c in codigos], *[_tecla(c, banderas=KEYEVENTF_KEYUP) for c in reversed(codigos)])


# --- Punto de entrada para el servidor --------------------------------------------------

def ejecutar(datos):
    """Aplica una orden del celular. Devuelve un dict para la respuesta."""
    tipo = datos.get("tipo")
    with _bloqueo:
        if tipo == "mover":
            mover(datos["x"], datos["y"])
        elif tipo == "mover_relativo":
            mover_relativo(float(datos["dx"]), float(datos["dy"]))
        elif tipo == "boton":
            if "x" in datos and "y" in datos:
                mover(datos["x"], datos["y"])
            boton(datos.get("boton", "izquierdo"), datos.get("accion", "clic"), datos.get("veces", 1))
        elif tipo == "rueda":
            rueda(datos["pasos"])
        elif tipo == "escribir":
            escribir(datos["texto"])
        elif tipo == "teclas":
            teclas(datos["teclas"])
        else:
            raise ValueError("Orden desconocida")
    return {"ok": True}
