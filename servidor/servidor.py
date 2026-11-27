"""Servidor de ControlPC.

Corre en la PC con Windows, sirve la PWA y recibe órdenes del celular por la
red local. Solo usa la biblioteca estándar de Python: no hay que instalar nada.

Uso:  python servidor.py
"""

import hmac
import json
import mimetypes
import os
import secrets
import shutil
import socket
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import acciones
import actualizar
import sistema

CARPETA = Path(__file__).resolve().parent
CARPETA_WEB = (CARPETA.parent / "web").resolve()
RUTA_CONFIG = Path(os.environ.get("CONTROLPC_CONFIG", CARPETA / "config.json"))

# Tras MAX_FALLOS PIN incorrectos, esa IP queda bloqueada BLOQUEO_SEGUNDOS.
MAX_FALLOS = 5
BLOQUEO_SEGUNDOS = 60

mimetypes.add_type("application/manifest+json", ".webmanifest")
mimetypes.add_type("text/javascript", ".js")


def cargar_config(ruta=RUTA_CONFIG):
    """Lee config.json. Si no existe, lo crea a partir del ejemplo con un PIN aleatorio."""
    ruta = Path(ruta)
    if not ruta.exists():
        shutil.copy(CARPETA / "config.example.json", ruta)
    config = json.loads(ruta.read_text(encoding="utf-8"))
    if not str(config.get("pin", "")).strip():
        config["pin"] = f"{secrets.randbelow(10**6):06d}"
        ruta.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    config["pin"] = str(config["pin"]).strip()
    config.setdefault("puerto", 8765)
    config.setdefault("apps", [])
    return config


class Fallos:
    """Cuenta los PIN incorrectos por IP para frenar a quien intente adivinarlo."""

    def __init__(self):
        self.por_ip = {}

    def bloqueada(self, ip):
        cantidad, desde = self.por_ip.get(ip, (0, 0))
        if cantidad >= MAX_FALLOS:
            if time.monotonic() - desde < BLOQUEO_SEGUNDOS:
                return True
            del self.por_ip[ip]
        return False

    def fallo(self, ip):
        cantidad, _ = self.por_ip.get(ip, (0, 0))
        self.por_ip[ip] = (cantidad + 1, time.monotonic())

    def acierto(self, ip):
        self.por_ip.pop(ip, None)


def crear_manejador(config):
    fallos = Fallos()
    acciones.configurar(config)
    repositorio = {"repositorio": config.get("repositorio", actualizar.REPOSITORIO),
                   "rama": config.get("rama", actualizar.RAMA)}
    apps_por_id = {app["id"]: app for app in config["apps"]}

    class Manejador(BaseHTTPRequestHandler):
        server_version = "ControlPC"

        def log_message(self, formato, *args):
            sys.stderr.write(f"{self.client_address[0]} {formato % args}\n")

        # --- utilidades -------------------------------------------------
        def _json(self, estado, datos):
            cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
            self.send_response(estado)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(cuerpo)

        def _autorizado(self):
            ip = self.client_address[0]
            if fallos.bloqueada(ip):
                self._json(HTTPStatus.TOO_MANY_REQUESTS,
                           {"error": f"Demasiados intentos. Espera {BLOQUEO_SEGUNDOS} segundos."})
                return False
            pin = self.headers.get("X-PIN", "")
            if hmac.compare_digest(pin.encode(), config["pin"].encode()):
                fallos.acierto(ip)
                return True
            fallos.fallo(ip)
            self._json(HTTPStatus.UNAUTHORIZED, {"error": "PIN incorrecto"})
            return False

        def _leer_json(self):
            largo = int(self.headers.get("Content-Length") or 0)
            if largo > 10_000:
                return None
            try:
                return json.loads(self.rfile.read(largo) or b"{}")
            except json.JSONDecodeError:
                return None

        # --- rutas ------------------------------------------------------
        def do_GET(self):
            ruta = self.path.split("?", 1)[0]
            if ruta == "/api/ping":
                return self._json(HTTPStatus.OK, {"ok": True})
            if ruta == "/api/info":
                if not self._autorizado():
                    return
                return self._json(HTTPStatus.OK, {
                    "equipo": socket.gethostname(),
                    "apps": [{"id": a["id"], "nombre": a["nombre"]} for a in config["apps"]],
                    "acciones": list(acciones.ACCIONES),
                })
            if ruta == "/api/multimedia":
                if not self._autorizado():
                    return
                return self._json(HTTPStatus.OK, acciones.multimedia())
            if ruta == "/api/volumen":
                if not self._autorizado():
                    return
                return self._json(HTTPStatus.OK, acciones.leer_volumen())
            if ruta == "/api/sistema":
                if not self._autorizado():
                    return
                return self._json(HTTPStatus.OK, sistema.todo())
            if ruta == "/api/actualizacion":
                if not self._autorizado():
                    return
                if acciones.SIMULAR:  # en pruebas no se consulta GitHub
                    return self._json(HTTPStatus.OK, {"instalada": "abc1234", "disponible": "def5678", "hay_nueva": True})
                try:
                    return self._json(HTTPStatus.OK, actualizar.revisar(**repositorio))
                except Exception as error:  # noqa: BLE001
                    return self._json(HTTPStatus.BAD_GATEWAY, {"error": f"No se pudo consultar GitHub: {error}"})
            if ruta == "/api/multimedia/portada":
                if not self._autorizado():
                    return
                return self._imagen(acciones.portada())
            if ruta.startswith("/api/icono/"):
                if not self._autorizado():
                    return
                app = apps_por_id.get(ruta.removeprefix("/api/icono/"))
                return self._imagen(acciones.icono(app) if app else None, cache=True)
            return self._archivo(ruta)

        def _imagen(self, datos, cache=False):
            if not datos:
                return self._json(HTTPStatus.NOT_FOUND, {"error": "Sin imagen"})
            if datos.startswith(b"\x89PNG"):
                tipo = "image/png"
            elif datos.startswith(b"\xff\xd8"):
                tipo = "image/jpeg"
            else:
                tipo = "application/octet-stream"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(datos)))
            self.send_header("Cache-Control", "private, max-age=86400" if cache else "no-store")
            self.end_headers()
            self.wfile.write(datos)

        def do_POST(self):
            ruta = self.path.split("?", 1)[0]
            if ruta not in ("/api/accion", "/api/abrir", "/api/volumen", "/api/actualizar"):
                return self._json(HTTPStatus.NOT_FOUND, {"error": "No existe"})
            if not self._autorizado():
                return
            datos = self._leer_json()
            if not isinstance(datos, dict):
                return self._json(HTTPStatus.BAD_REQUEST, {"error": "Petición inválida"})

            if ruta == "/api/accion":
                nombre = datos.get("accion")
                funcion = acciones.ACCIONES.get(nombre)
                if funcion is None:
                    return self._json(HTTPStatus.BAD_REQUEST, {"error": "Acción desconocida"})
                try:
                    extra = funcion() or {}
                except Exception as error:  # noqa: BLE001 - se informa al celular
                    return self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(error)})
                return self._json(HTTPStatus.OK, {"ok": True, "accion": nombre, **extra})

            if ruta == "/api/actualizar":
                if acciones.SIMULAR:  # en pruebas no se descarga ni se sobrescribe nada
                    self._json(HTTPStatus.OK, {"ok": True, "actualizado": True, "version": "def5678", "archivos": 0})
                    return reiniciar_despues(self.server)
                try:
                    resultado = actualizar.actualizar(**repositorio)
                except Exception as error:  # noqa: BLE001
                    return self._json(HTTPStatus.BAD_GATEWAY, {"error": f"No se pudo actualizar: {error}"})
                self._json(HTTPStatus.OK, {"ok": True, **resultado})
                if resultado["actualizado"]:
                    reiniciar_despues(self.server)
                return

            if ruta == "/api/volumen":
                nivel = datos.get("nivel")
                if not isinstance(nivel, (int, float)) or not 0 <= nivel <= 100:
                    return self._json(HTTPStatus.BAD_REQUEST, {"error": "Nivel inválido"})
                return self._json(HTTPStatus.OK, {"ok": True, **acciones.poner_volumen(nivel)})

            app = apps_por_id.get(datos.get("id"))
            if app is None:
                return self._json(HTTPStatus.BAD_REQUEST, {"error": "App desconocida"})
            try:
                acciones.abrir_app(app)
            except Exception as error:  # noqa: BLE001
                return self._json(HTTPStatus.INTERNAL_SERVER_ERROR,
                                  {"error": f"No se pudo abrir {app['nombre']}: {error}"})
            return self._json(HTTPStatus.OK, {"ok": True, "app": app["id"]})

        def _archivo(self, ruta):
            if ruta in ("", "/"):
                ruta = "/index.html"
            destino = (CARPETA_WEB / ruta.lstrip("/")).resolve()
            # Evita que se lean archivos fuera de la carpeta web (p. ej. "/../servidor/config.json").
            if CARPETA_WEB not in destino.parents or not destino.is_file():
                return self._json(HTTPStatus.NOT_FOUND, {"error": "No existe"})
            cuerpo = destino.read_bytes()
            tipo = mimetypes.guess_type(destino.name)[0] or "application/octet-stream"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(cuerpo)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(cuerpo)

    return Manejador


def reiniciar_despues(servidor, segundos=1.0):
    """Cierra este servidor y arranca uno nuevo con el código recién descargado."""
    def reiniciar():
        if acciones.SIMULAR:
            print("[simulado] reiniciar servidor")
            return
        print("Reiniciando con la versión nueva…", flush=True)
        servidor.server_close()  # libera el puerto para el servidor nuevo
        actualizar.lanzar_servidor()
        os._exit(0)
    temporizador = threading.Timer(segundos, reiniciar)
    temporizador.daemon = True
    temporizador.start()


def escuchar(puerto, manejador, intentos=40):
    """Abre el puerto. Si está ocupado (p. ej. el servidor anterior aún se cierra), reintenta."""
    for intento in range(intentos):
        try:
            return ThreadingHTTPServer(("0.0.0.0", puerto), manejador)
        except OSError:
            if intento == intentos - 1:
                raise
            time.sleep(0.5)


def ip_local():
    """La IP de la PC en la red local (la que hay que abrir en el iPhone)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"


def main():
    # Con pythonw.exe (arranque automático, sin ventana) no hay consola: se escribe a un archivo.
    if sys.stdout is None or sys.stderr is None:
        registro = open(CARPETA / "controlpc.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = registro
    config = cargar_config()
    servidor = escuchar(config["puerto"], crear_manejador(config))
    print("ControlPC en marcha.")
    print(f"  Abre en el iPhone:  http://{ip_local()}:{config['puerto']}")
    print(f"  PIN:                {config['pin']}   (cámbialo en {RUTA_CONFIG})")
    if acciones.SIMULAR:
        print("  Modo simulado: las acciones solo se muestran, no se ejecutan.")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
