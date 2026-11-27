"""Actualiza ControlPC con la última versión publicada en GitHub.

Lo usa el botón "Actualizar" de la app (a través del servidor) y también se puede
ejecutar a mano con scripts\\actualizar.bat:

    python actualizar.py            descarga, copia y reinicia el servidor
    python actualizar.py --revisar  solo dice si hay una versión nueva

Nunca se tocan tus datos: servidor\\config.json (PIN y apps), la caché de iconos ni el registro.
"""

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

CARPETA_SERVIDOR = Path(__file__).resolve().parent
RAIZ = CARPETA_SERVIDOR.parent
RUTA_VERSION = CARPETA_SERVIDOR / "version.txt"
REPOSITORIO = "MartinLVX/ControlPC"
RAMA = "main"

# Rutas (relativas a la raíz) que la actualización nunca sobrescribe.
PROTEGIDAS = {
    "servidor/config.json",
    "servidor/version.txt",
    "servidor/controlpc.log",
}
CARPETAS_PROTEGIDAS = ("servidor/cache/", ".git/")


def _pedir(url, espera=20):
    peticion = urllib.request.Request(url, headers={"User-Agent": "ControlPC-actualizador"})
    with urllib.request.urlopen(peticion, timeout=espera) as respuesta:
        return respuesta.read()


def version_instalada():
    try:
        return RUTA_VERSION.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def version_disponible(repositorio=REPOSITORIO, rama=RAMA):
    """SHA del último commit de la rama en GitHub."""
    datos = json.loads(_pedir(f"https://api.github.com/repos/{repositorio}/commits/{rama}"))
    return datos["sha"]


def revisar(repositorio=REPOSITORIO, rama=RAMA):
    instalada = version_instalada()
    disponible = version_disponible(repositorio, rama)
    return {
        "instalada": instalada[:7] if instalada else None,
        "disponible": disponible[:7],
        "hay_nueva": instalada != disponible,
    }


def _protegida(relativa):
    relativa = relativa.replace("\\", "/")
    if relativa in PROTEGIDAS or "__pycache__/" in relativa:
        return True
    return relativa.startswith(CARPETAS_PROTEGIDAS)


def instalar_zip(contenido, raiz=RAIZ):
    """Copia los archivos de un ZIP de GitHub sobre `raiz`. Devuelve cuántos copió."""
    with zipfile.ZipFile(io.BytesIO(contenido)) as archivo, tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for miembro in archivo.infolist():
            # GitHub mete todo en una carpeta "ControlPC-<sha>/": se quita ese primer nivel.
            partes = Path(miembro.filename).parts[1:]
            if not partes or miembro.is_dir():
                continue
            relativa = "/".join(partes)
            if ".." in partes or Path(relativa).is_absolute() or _protegida(relativa):
                continue
            destino = tmp / relativa
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(archivo.read(miembro))

        # Primero se extrae todo a una carpeta temporal; si algo falla antes, no se toca nada.
        copiados = 0
        for origen in tmp.rglob("*"):
            if origen.is_file():
                destino = Path(raiz) / origen.relative_to(tmp)
                destino.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(origen, destino)
                copiados += 1
        return copiados


def actualizar(repositorio=REPOSITORIO, rama=RAMA):
    """Descarga e instala la última versión. No reinicia el servidor."""
    disponible = version_disponible(repositorio, rama)
    if version_instalada() == disponible:
        return {"actualizado": False, "version": disponible[:7], "archivos": 0}
    contenido = _pedir(f"https://codeload.github.com/{repositorio}/zip/{disponible}", espera=60)
    archivos = instalar_zip(contenido)
    RUTA_VERSION.write_text(disponible, encoding="utf-8")
    return {"actualizado": True, "version": disponible[:7], "archivos": archivos}


# --- Reinicio ---------------------------------------------------------------------

def _python_sin_ventana():
    """pythonw.exe junto al Python actual (para que el servidor no abra una ventana)."""
    candidato = Path(sys.executable).with_name("pythonw.exe")
    return str(candidato) if candidato.exists() else sys.executable


def lanzar_servidor():
    """Inicia un servidor nuevo, separado de este proceso y sin ventana."""
    banderas = 0
    if sys.platform == "win32":
        banderas = 0x00000008 | 0x00000200 | 0x08000000  # DETACHED | NEW_PROCESS_GROUP | NO_WINDOW
    subprocess.Popen(
        [_python_sin_ventana(), str(CARPETA_SERVIDOR / "servidor.py")],
        cwd=str(CARPETA_SERVIDOR), creationflags=banderas, close_fds=True,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def detener_otros_servidores():
    """Cierra los servidor.py que estén corriendo (menos este proceso). Solo Windows."""
    script = (
        "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*servidor.py*' "
        f"-and $_.ProcessId -ne {os.getpid()} }} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force }}"
    )
    subprocess.run(["powershell.exe", "-NoProfile", "-Command", script], check=False, timeout=30,
                   creationflags=0x08000000)
    time.sleep(1)


def main():
    if "--revisar" in sys.argv:
        print(json.dumps(revisar(), ensure_ascii=False))
        return
    print("Buscando la última versión de ControlPC…")
    resultado = actualizar()
    if resultado["actualizado"]:
        print(f"Actualizado a la versión {resultado['version']} ({resultado['archivos']} archivos).")
    else:
        print(f"Ya tienes la última versión ({resultado['version']}).")
    print("Reiniciando el servidor…")
    detener_otros_servidores()
    lanzar_servidor()
    print("Listo. Cierra y vuelve a abrir la app en el iPhone.")


if __name__ == "__main__":
    main()
