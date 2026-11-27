"""Acciones que el servidor puede ejecutar en Windows.

Si la variable de entorno CONTROLPC_SIMULAR=1 está definida (o el sistema no
es Windows), las acciones no se ejecutan: solo se registran. Esto permite
probar el servidor en cualquier equipo sin bloquear ni apagar nada.
"""

import ctypes
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

SIMULAR = os.environ.get("CONTROLPC_SIMULAR") == "1" or sys.platform != "win32"

# Registro de lo que se habría ejecutado en modo simulado (útil en pruebas).
historial = []

# Teclas virtuales de Windows para el volumen.
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
VK_MEDIA_NEXT = 0xB0
VK_MEDIA_PREV = 0xB1
VK_MEDIA_PLAY_PAUSE = 0xB3
KEYEVENTF_KEYUP = 0x0002


def _registrar(descripcion):
    historial.append(descripcion)
    print(f"[simulado] {descripcion}")


def _diferido(funcion, segundos=1.5):
    """Ejecuta la función un poco después, para que el celular reciba la respuesta antes."""
    temporizador = threading.Timer(segundos, funcion)
    temporizador.daemon = True
    temporizador.start()


def _tecla(codigo, veces=1):
    if SIMULAR:
        _registrar(f"tecla 0x{codigo:02X} x{veces}")
        return
    user32 = ctypes.windll.user32
    for _ in range(veces):
        user32.keybd_event(codigo, 0, 0, 0)
        user32.keybd_event(codigo, 0, KEYEVENTF_KEYUP, 0)


def bloquear():
    if SIMULAR:
        _registrar("bloquear")
        return
    ctypes.windll.user32.LockWorkStation()


def apagar():
    if SIMULAR:
        _registrar("apagar")
        return
    _diferido(lambda: subprocess.run(["shutdown", "/s", "/t", "0"], check=False))


def reiniciar():
    if SIMULAR:
        _registrar("reiniciar")
        return
    _diferido(lambda: subprocess.run(["shutdown", "/r", "/t", "0"], check=False))


def suspender():
    if SIMULAR:
        _registrar("suspender")
        return
    # Si la hibernación está activada en Windows, esto hiberna en lugar de suspender.
    # Para suspender de verdad: en una terminal de administrador, `powercfg /hibernate off`.
    _diferido(lambda: ctypes.windll.powrprof.SetSuspendState(0, 1, 0))


def subir_volumen():
    _tecla(VK_VOLUME_UP, 5)  # cada pulsación sube 2 %, así que sube 10 %


def bajar_volumen():
    _tecla(VK_VOLUME_DOWN, 5)


def silenciar():
    _tecla(VK_VOLUME_MUTE)


def reproducir_pausar():
    _tecla(VK_MEDIA_PLAY_PAUSE)


def siguiente():
    _tecla(VK_MEDIA_NEXT)


def anterior():
    _tecla(VK_MEDIA_PREV)


ACCIONES = {
    "bloquear": bloquear,
    "apagar": apagar,
    "reiniciar": reiniciar,
    "suspender": suspender,
    "subir_volumen": subir_volumen,
    "bajar_volumen": bajar_volumen,
    "silenciar": silenciar,
    "reproducir_pausar": reproducir_pausar,
    "siguiente": siguiente,
    "anterior": anterior,
}


def abrir_app(app):
    """Abre una aplicación de la lista configurada.

    `app` es un diccionario con "comando" (ruta a un .exe, .lnk, URL, etc.) y,
    opcionalmente, "argumentos" (lista de textos).
    """
    comando = os.path.expandvars(app["comando"])
    argumentos = app.get("argumentos", [])
    if SIMULAR:
        _registrar(f"abrir {comando} {argumentos}")
        return
    if argumentos:
        subprocess.Popen([comando, *argumentos])
    else:
        # os.startfile funciona con .exe, accesos directos (.lnk), documentos y URLs.
        os.startfile(comando)


# --- PowerShell (multimedia e iconos) ----------------------------------------

CARPETA_PS = Path(__file__).resolve().parent / "ps"
CARPETA_CACHE = Path(__file__).resolve().parent / "cache"
SIN_VENTANA = 0x08000000  # CREATE_NO_WINDOW: que no parpadee una consola al llamar a PowerShell


def _powershell(script, *argumentos, espera=15):
    resultado = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-File", str(CARPETA_PS / script), *argumentos],
        capture_output=True, timeout=espera, creationflags=SIN_VENTANA,
    )
    return resultado.stdout.decode("utf-8", errors="replace").strip()


# --- Lo que se está reproduciendo ---------------------------------------------

_bloqueo_multimedia = threading.Lock()
_ultimo_multimedia = {"cuando": 0.0, "datos": {"activo": False}}
RUTA_PORTADA = CARPETA_CACHE / "portada.img"

# Respuesta de ejemplo para el modo simulado.
MULTIMEDIA_SIMULADA = {
    "activo": True,
    "titulo": "Canción de prueba",
    "artista": "Artista de prueba",
    "album": "Álbum de prueba",
    "app": "Spotify.exe",
    "estado": "Playing",
    "portada": None,
}


def multimedia():
    """Título, artista, app y estado de lo que suena en la PC.

    El resultado se guarda 2 segundos para no lanzar PowerShell en cada consulta.
    "portada" es un identificador que cambia cuando cambia la carátula (o None).
    """
    if SIMULAR:
        return dict(MULTIMEDIA_SIMULADA)
    with _bloqueo_multimedia:
        if time.monotonic() - _ultimo_multimedia["cuando"] < 2:
            return dict(_ultimo_multimedia["datos"])
        CARPETA_CACHE.mkdir(exist_ok=True)
        try:
            datos = json.loads(_powershell("multimedia.ps1", "-Portada", str(RUTA_PORTADA)) or "{}")
        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as error:
            datos = {"activo": False, "error": str(error)}
        if datos.get("portada") and RUTA_PORTADA.exists():
            datos["portada"] = hashlib.sha1(RUTA_PORTADA.read_bytes()).hexdigest()[:12]
        else:
            datos["portada"] = None
        _ultimo_multimedia.update(cuando=time.monotonic(), datos=datos)
        return dict(datos)


def portada():
    """Bytes de la carátula actual, o None."""
    if SIMULAR or not RUTA_PORTADA.exists():
        return None
    return RUTA_PORTADA.read_bytes()


# --- Iconos de las apps --------------------------------------------------------

_bloqueo_iconos = threading.Lock()


def _es_url(texto):
    return urllib.parse.urlparse(texto).scheme in ("http", "https")


def _ruta_para_icono(app):
    """Qué archivo usar para sacar el icono de una app de la lista."""
    if app.get("icono"):
        return os.path.expandvars(app["icono"])
    comando = os.path.expandvars(app["comando"])
    if _es_url(comando) or comando.lower().startswith("shell:"):
        return comando
    if os.path.isabs(comando):
        return comando
    return shutil.which(comando) or comando


def icono(app):
    """PNG con el icono de la app, o None si no se pudo obtener.

    Se genera una sola vez y se guarda en servidor/cache/.
    - "icono" en config.json: una imagen propia (.png/.jpg) o un .exe/.ico/.lnk del que sacarlo.
    - URLs: se descarga el favicon del sitio.
    - Programas, accesos directos y apps de la Tienda: el icono que muestra Windows.
    """
    origen = _ruta_para_icono(app)
    if origen.lower().endswith((".png", ".jpg", ".jpeg")) and os.path.isfile(origen):
        return Path(origen).read_bytes()
    if SIMULAR and not _es_url(origen):
        return None
    clave = hashlib.sha1(origen.encode("utf-8")).hexdigest()[:16]
    destino = CARPETA_CACHE / f"icono-{clave}.png"
    fallido = CARPETA_CACHE / f"icono-{clave}.fallo"
    with _bloqueo_iconos:
        if destino.exists():
            return destino.read_bytes()
        if fallido.exists():
            return None
        CARPETA_CACHE.mkdir(exist_ok=True)
        try:
            if _es_url(origen):
                dominio = urllib.parse.urlparse(origen).hostname
                url = "https://www.google.com/s2/favicons?" + urllib.parse.urlencode({"domain": dominio, "sz": 128})
                with urllib.request.urlopen(url, timeout=5) as respuesta:
                    destino.write_bytes(respuesta.read())
            else:
                _powershell("icono.ps1", "-Ruta", origen, "-Salida", str(destino), "-Tam", "128")
        except Exception:  # noqa: BLE001 - sin icono se muestra la inicial
            pass
        if destino.exists() and destino.stat().st_size > 0:
            return destino.read_bytes()
        fallido.touch()
        return None
