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
import actualizar  # noqa: E402
import servidor  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402


class PruebasServidor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.png = Path(cls.tmp.name) / "icono.png"
        cls.png.write_bytes(b"\x89PNG\r\n\x1a\nprueba")
        ruta = Path(cls.tmp.name) / "config.json"
        ruta.write_text(json.dumps({
            "pin": "1234",
            "apps": [
                {"id": "bloc", "nombre": "Bloc de notas", "comando": "notepad.exe"},
                {"id": "propia", "nombre": "Con icono", "comando": "x.exe", "icono": str(cls.png)},
            ],
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
        self.assertEqual(json.loads(cuerpo)["apps"][0], {"id": "bloc", "nombre": "Bloc de notas"})

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

    def test_multimedia(self):
        self.assertEqual(self.pedir("/api/multimedia", pin="0000")[0], 401)
        estado, cuerpo = self.pedir("/api/multimedia")
        self.assertEqual(estado, 200)
        datos = json.loads(cuerpo)
        self.assertTrue(datos["activo"])
        self.assertEqual(datos["titulo"], "Canción de prueba")
        # En modo simulado no hay carátula.
        self.assertEqual(self.pedir("/api/multimedia/portada")[0], 404)

    def test_volumen_de_uno_en_uno(self):
        estado, cuerpo = self.pedir("/api/volumen")
        self.assertEqual(estado, 200)
        inicial = json.loads(cuerpo)["nivel"]
        subido = json.loads(self.pedir("/api/accion", {"accion": "subir_volumen"})[1])
        self.assertEqual(subido["nivel"], inicial + 1)
        bajado = json.loads(self.pedir("/api/accion", {"accion": "bajar_volumen"})[1])
        self.assertEqual(bajado["nivel"], inicial)

    def test_fijar_volumen(self):
        estado, cuerpo = self.pedir("/api/volumen", {"nivel": 73})
        self.assertEqual((estado, json.loads(cuerpo)["nivel"]), (200, 73))
        self.assertEqual(json.loads(self.pedir("/api/volumen")[1])["nivel"], 73)
        self.assertEqual(self.pedir("/api/volumen", {"nivel": 150})[0], 400)
        self.assertEqual(self.pedir("/api/volumen", {"nivel": 50}, pin="0000")[0], 401)

    def test_silencio(self):
        antes = json.loads(self.pedir("/api/volumen")[1])["silencio"]
        despues = json.loads(self.pedir("/api/accion", {"accion": "silenciar"})[1])["silencio"]
        self.assertEqual(despues, not antes)
        self.pedir("/api/accion", {"accion": "silenciar"})

    def test_abrir_spotify(self):
        self.assertEqual(self.pedir("/api/accion", {"accion": "abrir_reproductor"})[0], 200)
        self.assertEqual(acciones.historial, ["abrir spotify:"])
        self.assertEqual(json.loads(self.pedir("/api/multimedia")[1])["reproductor"], "Spotify")

    def test_controles_multimedia(self):
        for accion in ("reproducir_pausar", "siguiente", "anterior"):
            self.assertEqual(self.pedir("/api/accion", {"accion": accion})[0], 200)
        self.assertEqual(acciones.historial, ["tecla 0xB3 x1", "tecla 0xB0 x1", "tecla 0xB1 x1"])

    def test_iconos(self):
        self.assertEqual(self.pedir("/api/icono/propia", pin="0000")[0], 401)
        estado, cuerpo = self.pedir("/api/icono/propia")
        self.assertEqual((estado, cuerpo), (200, self.png.read_bytes()))
        # Sin Windows no se puede sacar el icono de un .exe: el celular muestra la inicial.
        self.assertEqual(self.pedir("/api/icono/bloc")[0], 404)
        self.assertEqual(self.pedir("/api/icono/no-existe")[0], 404)

    def test_sistema(self):
        self.assertEqual(self.pedir("/api/sistema", pin="0000")[0], 401)
        estado, cuerpo = self.pedir("/api/sistema")
        self.assertEqual(estado, 200)
        datos = json.loads(cuerpo)
        self.assertIn("procesador", datos["componentes"])
        for clave in ("cpu", "memoria", "gpu", "discos", "encendida"):
            self.assertIn(clave, datos["uso"])
        self.assertTrue(0 <= datos["uso"]["cpu"] <= 100)

    def test_actualizar_simulado(self):
        self.assertEqual(self.pedir("/api/actualizacion", pin="0000")[0], 401)
        self.assertTrue(json.loads(self.pedir("/api/actualizacion")[1])["hay_nueva"])
        self.assertEqual(self.pedir("/api/actualizar", {}, pin="0000")[0], 401)
        estado, cuerpo = self.pedir("/api/actualizar", {})
        self.assertEqual(estado, 200)
        self.assertTrue(json.loads(cuerpo)["actualizado"])

    def test_saltar_en_la_cancion(self):
        m = json.loads(self.pedir("/api/multimedia")[1])
        self.assertGreater(m["duracion"], 0)
        self.assertTrue(m["buscable"])
        self.assertEqual(self.pedir("/api/multimedia/posicion", {"segundos": 120.5})[0], 200)
        self.assertIn("saltar 120.5", acciones.historial)
        self.assertAlmostEqual(json.loads(self.pedir("/api/multimedia")[1])["posicion"], 120.5, delta=1)
        for malo in ({"segundos": -1}, {"segundos": "10"}, {"segundos": True}, {}):
            self.assertEqual(self.pedir("/api/multimedia/posicion", malo)[0], 400, malo)
        self.assertEqual(self.pedir("/api/multimedia/posicion", {"segundos": 5}, pin="0000")[0], 401)

    def test_pantalla_simulada(self):
        self.assertEqual(self.pedir("/api/pantalla", pin="0000")[0], 401)
        peticion = urllib.request.Request(self.base + "/api/pantalla?ancho=800", headers={"X-PIN": "1234"})
        with urllib.request.urlopen(peticion) as r:
            self.assertEqual(r.headers["X-Pantalla-Ancho"], "1920")
            self.assertEqual(r.headers["X-Pantalla-Alto"], "1080")
            self.assertIn(b"<svg", r.read())

    def test_entrada_mouse_y_teclado(self):
        ordenes = [
            {"tipo": "mover", "x": 0.5, "y": 0.5},
            {"tipo": "boton", "boton": "derecho", "x": 0, "y": 0},
            {"tipo": "mover_relativo", "dx": 10, "dy": 5},
            {"tipo": "rueda", "pasos": -2},
            {"tipo": "escribir", "texto": "hola ñ"},
            {"tipo": "teclas", "teclas": ["ctrl", "c"]},
        ]
        for orden in ordenes:
            self.assertEqual(self.pedir("/api/entrada", orden)[0], 200, orden)
        self.assertEqual(acciones.historial, ["mover 960,540", "mover 0,0", "clic derecho", "mover 10,5",
                                              "rueda -2", "escribir hola ñ", "teclas ctrl+c"])

    def test_entrada_invalida(self):
        self.assertEqual(self.pedir("/api/entrada", {"tipo": "formatear"})[0], 400)
        self.assertEqual(self.pedir("/api/entrada", {"tipo": "teclas", "teclas": ["nada"]})[0], 400)
        self.assertEqual(self.pedir("/api/entrada", {"tipo": "mover"})[0], 400)
        self.assertEqual(self.pedir("/api/entrada", {"tipo": "mover", "x": 0.1, "y": 0.1}, pin="0000")[0], 401)

    def test_control_remoto_desactivado(self):
        self.config["control_remoto"] = False
        try:
            self.assertEqual(self.pedir("/api/pantalla")[0], 403)
            self.assertEqual(self.pedir("/api/entrada", {"tipo": "rueda", "pasos": 1})[0], 403)
        finally:
            self.config.pop("control_remoto")

    def test_sirve_la_pwa(self):
        estado, cuerpo = self.pedir("/", pin="")
        self.assertEqual(estado, 200)
        self.assertIn(b"ControlPC", cuerpo)

    def test_no_sirve_archivos_fuera_de_web(self):
        self.assertEqual(self.pedir("/../servidor/servidor.py", pin="")[0], 404)
        self.assertEqual(self.pedir("/%2e%2e/servidor/servidor.py", pin="")[0], 404)


# Un sustituto de multimedia.ps1 que habla el mismo protocolo (una línea por orden).
AYUDANTE_FALSO = r"""
import json, sys, time
print(json.dumps({"listo": True}), flush=True)
for linea in sys.stdin:
    orden = linea.strip()
    if orden == "colgarse":
        time.sleep(60)
    elif orden == "con_aviso":
        print("ADVERTENCIA: algo", flush=True)
        print("\ufeff" + json.dumps({"orden": orden, "abierta": True}), flush=True)
    elif orden == "morir":
        sys.exit(1)
    else:
        print(json.dumps({"orden": orden, "abierta": True}), flush=True)
"""


class PruebasAyudanteMultimedia(unittest.TestCase):
    def setUp(self):
        class Falso(acciones._AyudanteMultimedia):
            def comando(self):
                return [sys.executable, "-c", AYUDANTE_FALSO]
        self.ayudante = Falso()

    def tearDown(self):
        self.ayudante._cerrar()

    def test_responde_y_reutiliza_el_proceso(self):
        self.assertEqual(self.ayudante.pedir("estado C:\\portada.img"), {"orden": "estado C:\\portada.img", "abierta": True})
        proceso = self.ayudante.proceso
        self.assertEqual(self.ayudante.pedir("siguiente")["orden"], "siguiente")
        self.assertIs(self.ayudante.proceso, proceso)

    def test_ignora_lineas_que_no_son_json(self):
        self.assertEqual(self.ayudante.pedir("con_aviso")["orden"], "con_aviso")

    def test_se_recupera_si_el_proceso_muere(self):
        self.ayudante.pedir("estado")
        self.ayudante.proceso.kill()
        self.ayudante.proceso.wait()
        self.assertEqual(self.ayudante.pedir("anterior")["orden"], "anterior")


class PruebasActualizar(unittest.TestCase):
    def zip_de_github(self, archivos):
        import io
        import zipfile
        datos = io.BytesIO()
        with zipfile.ZipFile(datos, "w") as z:
            for ruta, contenido in archivos.items():
                z.writestr("ControlPC-abc123/" + ruta, contenido)
        return datos.getvalue()

    def test_copia_archivos_y_respeta_los_datos_del_usuario(self):
        with tempfile.TemporaryDirectory() as raiz:
            raiz = Path(raiz)
            (raiz / "servidor" / "cache").mkdir(parents=True)
            (raiz / "servidor" / "config.json").write_text("MI CONFIG")
            (raiz / "servidor" / "cache" / "icono.png").write_text("MI ICONO")
            (raiz / "web").mkdir()
            (raiz / "web" / "app.js").write_text("viejo")
            contenido = self.zip_de_github({
                "web/app.js": "nuevo",
                "servidor/nuevo.py": "x = 1",
                "servidor/config.json": "CONFIG DEL REPO",
                "servidor/cache/icono.png": "otro",
                "servidor/__pycache__/a.pyc": "basura",
                "../fuera.txt": "no",
            })
            copiados = actualizar.instalar_zip(contenido, raiz)
            self.assertEqual(copiados, 2)
            self.assertEqual((raiz / "web" / "app.js").read_text(), "nuevo")
            self.assertEqual((raiz / "servidor" / "nuevo.py").read_text(), "x = 1")
            self.assertEqual((raiz / "servidor" / "config.json").read_text(), "MI CONFIG")
            self.assertEqual((raiz / "servidor" / "cache" / "icono.png").read_text(), "MI ICONO")
            self.assertFalse((raiz / "servidor" / "__pycache__").exists())
            self.assertFalse((raiz.parent / "fuera.txt").exists())


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
