"""Pruebas del servidor en modo simulado (no bloquea ni apaga nada).

Ejecutar desde la raíz del repositorio:  python -m unittest discover tests
"""

import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

os.environ["CONTROLPC_SIMULAR"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "servidor"))

import acciones  # noqa: E402
import servidor  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402


class PruebasServidor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        ruta = Path(cls.tmp.name) / "config.json"
        ruta.write_text(json.dumps({
            "pin": "1234",
            "apps": [{"id": "bloc", "nombre": "Bloc de notas", "comando": "notepad.exe"}],
        }), encoding="utf-8")
        cls.config = servidor.cargar_config(ruta)
        cls.http = ThreadingHTTPServer(("127.0.0.1", 0), servidor.crear_manejador(cls.config))
        cls.base = f"http://127.0.0.1:{cls.http.server_address[1]}"
        threading.Thread(target=cls.http.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.tmp.cleanup()

    def setUp(self):
        acciones.historial.clear()

    def pedir(self, ruta, datos=None, pin="1234"):
        cuerpo = json.dumps(datos).encode() if datos is not None else None
        peticion = urllib.request.Request(self.base + ruta, data=cuerpo, headers={"X-PIN": pin})
        try:
            with urllib.request.urlopen(peticion) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def test_ping_sin_pin(self):
        self.assertEqual(self.pedir("/api/ping", pin="")[0], 200)

    def test_info_requiere_pin(self):
        self.assertEqual(self.pedir("/api/info", pin="0000")[0], 401)
        estado, cuerpo = self.pedir("/api/info")
        self.assertEqual(estado, 200)
        self.assertEqual(json.loads(cuerpo)["apps"], [{"id": "bloc", "nombre": "Bloc de notas"}])

    def test_acciones(self):
        for nombre in acciones.ACCIONES:
            self.assertEqual(self.pedir("/api/accion", {"accion": nombre})[0], 200, nombre)
        self.assertIn("bloquear", acciones.historial)
        self.assertIn("apagar", acciones.historial)

    def test_accion_desconocida(self):
        self.assertEqual(self.pedir("/api/accion", {"accion": "formatear"})[0], 400)

    def test_abrir_app(self):
        self.assertEqual(self.pedir("/api/abrir", {"id": "bloc"})[0], 200)
        self.assertTrue(acciones.historial[-1].startswith("abrir notepad.exe"))
        self.assertEqual(self.pedir("/api/abrir", {"id": "cmd"})[0], 400)

    def test_accion_con_pin_malo_no_se_ejecuta(self):
        self.assertEqual(self.pedir("/api/accion", {"accion": "apagar"}, pin="9999")[0], 401)
        self.assertEqual(acciones.historial, [])

    def test_sirve_la_pwa(self):
        estado, cuerpo = self.pedir("/", pin="")
        self.assertEqual(estado, 200)
        self.assertIn(b"ControlPC", cuerpo)

    def test_no_sirve_archivos_fuera_de_web(self):
        self.assertEqual(self.pedir("/../servidor/servidor.py", pin="")[0], 404)
        self.assertEqual(self.pedir("/%2e%2e/servidor/servidor.py", pin="")[0], 404)


class PruebasBloqueo(unittest.TestCase):
    def test_bloquea_tras_varios_fallos(self):
        fallos = servidor.Fallos()
        for _ in range(servidor.MAX_FALLOS):
            self.assertFalse(fallos.bloqueada("1.2.3.4"))
            fallos.fallo("1.2.3.4")
        self.assertTrue(fallos.bloqueada("1.2.3.4"))
        self.assertFalse(fallos.bloqueada("5.6.7.8"))


class PruebasConfig(unittest.TestCase):
    def test_genera_pin_si_falta(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "config.json"
            config = servidor.cargar_config(ruta)
            self.assertRegex(config["pin"], r"^\d{6}$")
            self.assertEqual(json.loads(ruta.read_text(encoding="utf-8"))["pin"], config["pin"])


if __name__ == "__main__":
    unittest.main()
