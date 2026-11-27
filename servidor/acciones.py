"""Acciones que el servidor puede ejecutar en Windows.

Si la variable de entorno CONTROLPC_SIMULAR=1 está definida (o el sistema no
es Windows), las acciones no se ejecutan: solo se registran. Esto permite
probar el servidor en cualquier equipo sin bloquear ni apagar nada.
"""

import ctypes
import os
import subprocess
import sys
import threading

SIMULAR = os.environ.get("CONTROLPC_SIMULAR") == "1" or sys.platform != "win32"

# Registro de lo que se habría ejecutado en modo simulado (útil en pruebas).
historial = []

# Teclas virtuales de Windows para el volumen.
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
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


ACCIONES = {
    "bloquear": bloquear,
    "apagar": apagar,
    "reiniciar": reiniciar,
    "suspender": suspender,
    "subir_volumen": subir_volumen,
    "bajar_volumen": bajar_volumen,
    "silenciar": silenciar,
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
