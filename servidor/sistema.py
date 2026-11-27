"""Datos de la PC para la pestaña "Sistema": componentes y uso actual.

- Uso de procesador, memoria, discos y tiempo encendida: ctypes (instantáneo).
- Uso de la gráfica y lista de componentes: ps/sistema.ps1, un PowerShell que queda abierto.
"""

import ctypes
import shutil
import string
import sys
import threading
import time

import acciones

SIMULAR = acciones.SIMULAR

_ayudante = acciones.AyudantePS("sistema.ps1", lambda: [])
_specs = None
_bloqueo_specs = threading.Lock()


# --- Procesador ------------------------------------------------------------------

class _FILETIME(ctypes.Structure):
    _fields_ = [("bajo", ctypes.c_uint32), ("alto", ctypes.c_uint32)]

    def valor(self):
        return (self.alto << 32) | self.bajo


_ultima_muestra = None
_bloqueo_cpu = threading.Lock()


def _tiempos_cpu():
    inactivo, nucleo, usuario = _FILETIME(), _FILETIME(), _FILETIME()
    ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(inactivo), ctypes.byref(nucleo), ctypes.byref(usuario))
    # El tiempo de núcleo ya incluye el inactivo.
    return inactivo.valor(), nucleo.valor() + usuario.valor()


def uso_cpu():
    """% de uso del procesador desde la consulta anterior (o en 0,3 s si es la primera)."""
    global _ultima_muestra
    with _bloqueo_cpu:
        if _ultima_muestra is None:
            _ultima_muestra = _tiempos_cpu()
            time.sleep(0.3)
        inactivo, total = _tiempos_cpu()
        inactivo0, total0 = _ultima_muestra
        _ultima_muestra = (inactivo, total)
        delta = total - total0
        if delta <= 0:
            return 0
        return round(max(0.0, min(100.0, (1 - (inactivo - inactivo0) / delta) * 100)))


# --- Memoria, discos y tiempo encendida ---------------------------------------------

class _ESTADO_MEMORIA(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_uint32), ("dwMemoryLoad", ctypes.c_uint32),
        ("ullTotalPhys", ctypes.c_uint64), ("ullAvailPhys", ctypes.c_uint64),
        ("ullTotalPageFile", ctypes.c_uint64), ("ullAvailPageFile", ctypes.c_uint64),
        ("ullTotalVirtual", ctypes.c_uint64), ("ullAvailVirtual", ctypes.c_uint64),
        ("ullAvailExtendedVirtual", ctypes.c_uint64),
    ]


def uso_memoria():
    estado = _ESTADO_MEMORIA()
    estado.dwLength = ctypes.sizeof(estado)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(estado))
    usada = estado.ullTotalPhys - estado.ullAvailPhys
    return {"total": estado.ullTotalPhys, "usada": usada, "porcentaje": round(usada * 100 / estado.ullTotalPhys)}


def uso_discos():
    """Unidades fijas (C:, D:, …) con su espacio usado."""
    discos = []
    mascara = ctypes.windll.kernel32.GetLogicalDrives()
    for i, letra in enumerate(string.ascii_uppercase):
        if not mascara & (1 << i):
            continue
        raiz = f"{letra}:\\"
        if ctypes.windll.kernel32.GetDriveTypeW(raiz) != 3:  # 3 = disco fijo
            continue
        try:
            total, usado, _libre = shutil.disk_usage(raiz)
        except OSError:
            continue
        nombre = ctypes.create_unicode_buffer(261)
        ctypes.windll.kernel32.GetVolumeInformationW(raiz, nombre, 261, None, None, None, None, 0)
        discos.append({"unidad": f"{letra}:", "nombre": nombre.value, "total": total, "usado": usado,
                       "porcentaje": round(usado * 100 / total) if total else 0})
    return discos


def encendida_segundos():
    ctypes.windll.kernel32.GetTickCount64.restype = ctypes.c_uint64
    return ctypes.windll.kernel32.GetTickCount64() // 1000


# --- Componentes -----------------------------------------------------------------------

SPECS_SIMULADAS = {
    "equipo": "MI-PC", "fabricante": "ASUS", "modelo": "System Product Name",
    "procesador": {"nombre": "AMD Ryzen 7 5800X 8-Core Processor", "nucleos": 8, "hilos": 16, "mhz": 3801},
    "graficas": [{"nombre": "NVIDIA GeForce RTX 3070", "memoria": 8 * 1024**3, "driver": "32.0.15.6094"}],
    "memoria": {"total": 32 * 1024**3, "modulos": [
        {"capacidad": 16 * 1024**3, "velocidad": 3200, "fabricante": "Kingston"},
        {"capacidad": 16 * 1024**3, "velocidad": 3200, "fabricante": "Kingston"}]},
    "discos": [{"modelo": "Samsung SSD 980 PRO 1TB", "tamano": 1000 * 1000**3, "interfaz": "SCSI"},
               {"modelo": "ST2000DM008-2FR102", "tamano": 2000 * 1000**3, "interfaz": "IDE"}],
    "discos_tipo": [{"modelo": "Samsung SSD 980 PRO 1TB", "tipo": "SSD", "bus": "NVMe"},
                    {"modelo": "ST2000DM008-2FR102", "tipo": "HDD", "bus": "SATA"}],
    "placa": {"fabricante": "ASUSTeK COMPUTER INC.", "modelo": "TUF GAMING B550-PLUS"},
    "windows": {"nombre": "Microsoft Windows 11 Pro", "version": "10.0.26100", "compilacion": "26100"},
}


def componentes(bloquear=False):
    """Lista de componentes. Se pide una sola vez (no cambian) y se guarda.

    Sin `bloquear`, devuelve None mientras se cargan (tarda unos segundos la primera vez).
    """
    global _specs
    if SIMULAR:
        return SPECS_SIMULADAS
    if not bloquear:
        return _specs
    with _bloqueo_specs:
        if _specs is None:
            respuesta = _ayudante.pedir("specs", espera=40)
            if respuesta and "error" not in respuesta:
                _specs = respuesta
        return _specs


# --- Todo junto ------------------------------------------------------------------------

def _simulado():
    t = time.time()
    return {
        "cpu": round(25 + 15 * abs((t % 20) - 10) / 10),
        "memoria": {"total": 32 * 1024**3, "usada": 13 * 1024**3, "porcentaje": 41},
        "gpu": {"uso": 12, "memoria_usada": 2 * 1024**3, "memoria_tipo": "dedicada"},
        "discos": [
            {"unidad": "C:", "nombre": "Windows", "total": 1000 * 1000**3, "usado": 612 * 1000**3, "porcentaje": 61},
            {"unidad": "D:", "nombre": "Juegos", "total": 2000 * 1000**3, "usado": 1430 * 1000**3, "porcentaje": 72},
        ],
        "encendida": 3 * 3600 + 25 * 60,
    }


# El ayudante de PowerShell tarda de 0,5 a 1 s (y más la primera vez), así que se consulta
# en segundo plano mientras alguien mira la pestaña, y la petición del celular responde
# al instante con el último dato.
_ultimo_ps = {"cpu": None, "gpu": None, "fallo": False}
_ultima_peticion = 0.0
_hilo_fondo = None
_bloqueo_fondo = threading.Lock()


def _bucle_fondo():
    while time.monotonic() - _ultima_peticion < 15:
        if _specs is None:
            componentes(bloquear=True)
        respuesta = _ayudante.pedir("uso", espera=30)
        if respuesta and "error" not in respuesta:
            _ultimo_ps.update(cpu=respuesta.get("cpu"), gpu=respuesta.get("gpu"), fallo=False)
        else:
            _ultimo_ps["fallo"] = True
        time.sleep(1.5)


def _despertar_fondo():
    global _hilo_fondo, _ultima_peticion
    with _bloqueo_fondo:
        _ultima_peticion = time.monotonic()
        if _hilo_fondo is None or not _hilo_fondo.is_alive():
            _hilo_fondo = threading.Thread(target=_bucle_fondo, daemon=True)
            _hilo_fondo.start()


def uso():
    """Uso actual. Cada parte falla por separado: si una no se puede leer, viene en None."""
    if SIMULAR:
        return _simulado()
    _despertar_fondo()
    datos = {}
    for clave, funcion in (("memoria", uso_memoria), ("discos", uso_discos), ("encendida", encendida_segundos)):
        try:
            datos[clave] = funcion()
        except Exception as error:  # noqa: BLE001
            print(f"[sistema] {clave}: {error}", file=sys.stderr, flush=True)
            datos[clave] = None
    # Procesador: la cifra del Administrador de tareas. Mientras llega el primer dato se
    # devuelve None (la app muestra "–"); solo si PowerShell falla se usa el tiempo ocupado,
    # que da una cifra más baja.
    datos["cpu"] = _ultimo_ps["cpu"]
    if datos["cpu"] is None and _ultimo_ps["fallo"]:
        try:
            datos["cpu"] = uso_cpu()
        except Exception:  # noqa: BLE001
            datos["cpu"] = None
    datos["gpu"] = _ultimo_ps["gpu"]
    return datos


def todo():
    return {"componentes": componentes(), "uso": uso()}
