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
import queue
import threading
import time
import traceback
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


# --- Volumen -------------------------------------------------------------------

PASO_VOLUMEN = 1
_volumen_simulado = {"nivel": 40, "silencio": False}


def _volumen(operacion, *argumentos, tecla=None, **opciones):
    """Usa el volumen exacto de Windows; si falla, pulsa la tecla de volumen como respaldo."""
    if SIMULAR:
        if operacion == "cambiar":
            paso, nivel = opciones.get("paso", 0), opciones.get("nivel")
            nuevo = _volumen_simulado["nivel"] + paso if nivel is None else nivel
            _volumen_simulado.update(nivel=max(0, min(100, int(nuevo))), silencio=False)
            _registrar(f"volumen {_volumen_simulado['nivel']}")
        elif operacion == "alternar_silencio":
            _volumen_simulado["silencio"] = not _volumen_simulado["silencio"]
            _registrar(f"silencio {_volumen_simulado['silencio']}")
        return dict(_volumen_simulado)
    try:
        import volumen  # solo en Windows
        return getattr(volumen, operacion)(*argumentos, **opciones)
    except Exception:  # noqa: BLE001 - se registra y se usa la tecla de respaldo
        print(f"[volumen] fallo en {operacion}:\n{traceback.format_exc()}", file=sys.stderr, flush=True)
        if tecla:
            _tecla(tecla)
        return {}


def subir_volumen():
    return _volumen("cambiar", paso=PASO_VOLUMEN, tecla=VK_VOLUME_UP)


def bajar_volumen():
    return _volumen("cambiar", paso=-PASO_VOLUMEN, tecla=VK_VOLUME_DOWN)


def silenciar():
    return _volumen("alternar_silencio", tecla=VK_VOLUME_MUTE)


def leer_volumen():
    return _volumen("leer")


def poner_volumen(nivel):
    return _volumen("cambiar", nivel=nivel)


# --- Controles de reproducción --------------------------------------------------
# Se envían a la app configurada (Spotify por defecto). Si no se puede, se usan
# las teclas multimedia, que van a la app que Windows tenga activa.

def _control(orden, tecla):
    if SIMULAR:
        _tecla(tecla)
        return {}
    respuesta = _ayudante.pedir(orden)
    if not respuesta or not respuesta.get("abierta"):
        _tecla(tecla)
    return {}


def reproducir_pausar():
    return _control("play_pausa", VK_MEDIA_PLAY_PAUSE)


def siguiente():
    return _control("siguiente", VK_MEDIA_NEXT)


def anterior():
    return _control("anterior", VK_MEDIA_PREV)


def abrir_reproductor():
    """Abre la app de música configurada (Spotify por defecto)."""
    destino = _config["multimedia_abrir"]
    if SIMULAR:
        _registrar(f"abrir {destino}")
        return {}
    os.startfile(destino)
    return {}


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
    "abrir_reproductor": abrir_reproductor,
}

# Ajustes que vienen de config.json (los pone servidor.py al arrancar).
_config = {"multimedia_app": "Spotify", "multimedia_abrir": "spotify:"}


def configurar(config):
    for clave in _config:
        if clave in config:
            _config[clave] = config[clave]


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

RUTA_PORTADA = CARPETA_CACHE / "portada.img"


class AyudantePS:
    """Un PowerShell que queda abierto (un script de ps/) y responde órdenes por línea.

    Arrancar PowerShell cuesta cerca de un segundo; con el proceso abierto, cada
    consulta o botón tarda milisegundos. Si se cierra o se cuelga, se vuelve a abrir.
    """

    def __init__(self, script="multimedia.ps1", argumentos=lambda: ["-App", _config["multimedia_app"] or ""]):
        self.script = script
        self.argumentos = argumentos
        self.proceso = None
        self.respuestas = None
        self.bloqueo = threading.Lock()

    def comando(self):
        return ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                "-File", str(CARPETA_PS / self.script), *self.argumentos()]

    def _arrancar(self):
        self.proceso = subprocess.Popen(
            self.comando(), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", bufsize=1, creationflags=SIN_VENTANA if sys.platform == "win32" else 0,
        )
        self.respuestas = queue.Queue()
        proceso, respuestas = self.proceso, self.respuestas

        def leer():
            for linea in proceso.stdout:
                respuestas.put(linea)

        def errores():  # lo que PowerShell escriba como error va al registro del servidor
            for linea in proceso.stderr:
                if linea.strip():
                    print(f"[{self.script}] {linea.rstrip()}", file=sys.stderr, flush=True)
        threading.Thread(target=leer, daemon=True).start()
        threading.Thread(target=errores, daemon=True).start()
        inicio = self._esperar(20)  # primera línea: {"listo": true}
        if not inicio or not inicio.get("listo"):
            print(f"[{self.script}] no arrancó bien: {inicio}", file=sys.stderr, flush=True)

    def _esperar(self, segundos):
        """Siguiente respuesta JSON. Las líneas que no son JSON (avisos) se registran y se saltan."""
        limite = time.monotonic() + segundos
        while (restante := limite - time.monotonic()) > 0:
            try:
                linea = self.respuestas.get(timeout=restante)
            except queue.Empty:
                return None
            try:
                return json.loads(linea.lstrip("\ufeff"))  # PowerShell puede anteponer la marca BOM
            except json.JSONDecodeError:
                if linea.strip():
                    print(f"[{self.script}] {linea.rstrip()}", file=sys.stderr, flush=True)
        return None

    def _cerrar(self):
        if self.proceso:
            self.proceso.kill()
        self.proceso = None

    def pedir(self, orden, espera=8):
        with self.bloqueo:
            for _ in range(2):  # si falla, un reintento con un proceso nuevo
                try:
                    if not self.proceso or self.proceso.poll() is not None:
                        self._arrancar()
                    self.proceso.stdin.write(orden + "\n")
                    self.proceso.stdin.flush()
                    respuesta = self._esperar(espera)
                    if respuesta is not None:
                        return respuesta
                except OSError:
                    pass
                self._cerrar()
            return None


_AyudanteMultimedia = AyudantePS  # nombre anterior
_ayudante = AyudantePS()

# Respuesta de ejemplo para el modo simulado.
MULTIMEDIA_SIMULADA = {
    "activo": True,
    "abierta": True,
    "titulo": "Canción de prueba",
    "artista": "Artista de prueba",
    "album": "Álbum de prueba",
    "app": "Spotify.exe",
    "estado": "Playing",
    "posicion": 72,
    "duracion": 215,
    "portada": None,
}


def multimedia():
    """Título, artista, estado, posición y carátula de lo que suena en la app configurada.

    "portada" es un identificador que cambia cuando cambia la carátula (o None).
    "abierta" es False si la app (Spotify) no está abierta.
    """
    if SIMULAR:
        datos = dict(MULTIMEDIA_SIMULADA)
    else:
        CARPETA_CACHE.mkdir(exist_ok=True)
        datos = _ayudante.pedir(f"estado {RUTA_PORTADA}") or {"activo": False, "abierta": False}
        if datos.get("portada") and RUTA_PORTADA.exists():
            datos["portada"] = hashlib.sha1(RUTA_PORTADA.read_bytes()).hexdigest()[:12]
        else:
            datos["portada"] = None
    datos["reproductor"] = _config["multimedia_app"] or ""
    return datos


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
