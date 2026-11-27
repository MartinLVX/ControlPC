"""Volumen exacto de Windows (Core Audio) con ctypes, sin paquetes extra.

Las teclas de volumen de Windows mueven el volumen de 2 en 2. Para subir o bajar
de 1 en 1 y saber el nivel actual se usa IAudioEndpointVolume del altavoz
predeterminado. Si algo falla, quien llama puede volver a las teclas.
"""

import ctypes
import sys
from ctypes import POINTER, byref, c_float, c_int, c_uint, c_void_p, wintypes

if sys.platform == "win32":
    ole32 = ctypes.windll.ole32
    HRESULT = ctypes.HRESULT
    ole32.CoCreateInstance.restype = HRESULT  # que un fallo lance OSError


class GUID(ctypes.Structure):
    _fields_ = [("Data1", c_uint), ("Data2", ctypes.c_ushort), ("Data3", ctypes.c_ushort),
                ("Data4", ctypes.c_ubyte * 8)]

    @classmethod
    def desde(cls, texto):
        guid = cls()
        ole32.CLSIDFromString(ctypes.c_wchar_p(texto), byref(guid))
        return guid


CLSID_MMDeviceEnumerator = "{BCDE0395-E52F-467C-8E3D-C4579291692E}"
IID_IMMDeviceEnumerator = "{A95664D2-9614-4F35-A746-DE8DB63617E6}"
IID_IAudioEndpointVolume = "{5CDF2C82-841E-4546-9722-0CF74078229A}"
CLSCTX_ALL = 23
E_RENDER = 0      # salida de audio
E_MULTIMEDIA = 1  # rol "multimedia" del dispositivo predeterminado


def _metodo(objeto, indice, *argumentos):
    """Prepara la llamada al método número `indice` de la vtable de un objeto COM."""
    vtable = ctypes.cast(objeto, POINTER(POINTER(c_void_p))).contents
    prototipo = ctypes.WINFUNCTYPE(HRESULT, c_void_p, *argumentos)
    return lambda *valores: prototipo(vtable[indice])(objeto, *valores)


def _liberar(objeto):
    if objeto:
        _metodo(objeto, 2)()  # IUnknown::Release


class _Altavoz:
    """Abre el altavoz predeterminado mientras dura el bloque `with`."""

    def __enter__(self):
        # Cada hilo del servidor inicializa COM (0 = ok, 1 = ya estaba; negativo = error).
        self.com = ole32.CoInitializeEx(None, 0x2) >= 0
        self.enumerador = c_void_p()
        self.dispositivo = c_void_p()
        self.volumen = c_void_p()
        try:
            self._abrir()
        except Exception:
            self.__exit__()
            raise
        return self

    def _abrir(self):
        ole32.CoCreateInstance(byref(GUID.desde(CLSID_MMDeviceEnumerator)), None, CLSCTX_ALL,
                               byref(GUID.desde(IID_IMMDeviceEnumerator)), byref(self.enumerador))
        # IMMDeviceEnumerator::GetDefaultAudioEndpoint
        _metodo(self.enumerador, 4, c_int, c_int, POINTER(c_void_p))(E_RENDER, E_MULTIMEDIA, byref(self.dispositivo))
        # IMMDevice::Activate
        _metodo(self.dispositivo, 3, POINTER(GUID), wintypes.DWORD, c_void_p, POINTER(c_void_p))(
            byref(GUID.desde(IID_IAudioEndpointVolume)), CLSCTX_ALL, None, byref(self.volumen))

    def __exit__(self, *_):
        for objeto in (self.volumen, self.dispositivo, self.enumerador):
            _liberar(objeto)
        if self.com:
            ole32.CoUninitialize()

    # IAudioEndpointVolume
    def nivel(self):
        valor = c_float()
        _metodo(self.volumen, 9, POINTER(c_float))(byref(valor))  # GetMasterVolumeLevelScalar
        return round(valor.value * 100)

    def poner_nivel(self, nivel):
        _metodo(self.volumen, 7, c_float, c_void_p)(c_float(nivel / 100), None)  # SetMasterVolumeLevelScalar

    def silencio(self):
        valor = wintypes.BOOL()
        _metodo(self.volumen, 15, POINTER(wintypes.BOOL))(byref(valor))  # GetMute
        return bool(valor.value)

    def poner_silencio(self, activo):
        _metodo(self.volumen, 14, wintypes.BOOL, c_void_p)(activo, None)  # SetMute


def leer():
    with _Altavoz() as a:
        return {"nivel": a.nivel(), "silencio": a.silencio()}


def cambiar(paso=0, nivel=None):
    """Sube/baja `paso` puntos o fija `nivel` (0-100). Quita el silencio al cambiarlo."""
    with _Altavoz() as a:
        nuevo = a.nivel() + paso if nivel is None else nivel
        nuevo = max(0, min(100, int(nuevo)))
        a.poner_nivel(nuevo)
        if a.silencio():
            a.poner_silencio(False)
        return {"nivel": nuevo, "silencio": False}


def alternar_silencio():
    with _Altavoz() as a:
        activo = not a.silencio()
        a.poner_silencio(activo)
        return {"nivel": a.nivel(), "silencio": activo}
