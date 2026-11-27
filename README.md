# ControlPC

Controla tu PC con Windows desde el iPhone, en tu misma red WiFi. La app abre en Multimedia y tiene cuatro pestañas:

- **Aplicaciones:** abre los programas de tu lista, cada uno con su icono.
- **Multimedia:** enlazada a Spotify de escritorio. Muestra la canción (título, artista y carátula), con anterior, reproducir/pausar y siguiente que van directo a Spotify aunque esté minimizado. Si Spotify está cerrado, hay un botón para abrirlo. El volumen se mueve de 1 en 1 (o con la barra) y muestra el nivel exacto.
- **Sistema:** uso en vivo del procesador, la memoria, la gráfica y los discos (las mismas cifras que el Administrador de tareas), cuánto tiempo lleva encendida y los componentes de la PC.
- **Equipo:** bloquear, suspender, reiniciar, apagar y actualizar ControlPC.

Son dos partes:

- **Servidor** (`servidor/`): un programa en Python que corre en la PC y recibe las órdenes. Solo usa la biblioteca estándar, así que no hay que instalar paquetes.
- **App** (`web/`): una PWA que el mismo servidor entrega al iPhone. Se agrega a la pantalla de inicio y se usa como una app.

## Instalación en la PC

1. Instala Python 3.10 o más nuevo desde [python.org](https://www.python.org/downloads/). En el instalador marca **"Add python.exe to PATH"**.
2. Descarga este repositorio (botón verde **Code → Download ZIP**) y descomprímelo en una carpeta fija, por ejemplo `C:\ControlPC`.
3. Abre **PowerShell como administrador**, entra a la carpeta y ejecuta:

   ```powershell
   cd C:\ControlPC
   powershell -ExecutionPolicy Bypass -File scripts\instalar.ps1
   ```

   El script:
   - crea `servidor\config.json` con un PIN aleatorio de 6 dígitos,
   - abre el puerto 8765 en el firewall **solo para equipos de tu red local**,
   - registra una tarea programada para que el servidor arranque solo cada vez que inicias sesión en Windows,
   - lo inicia y te muestra la dirección y el PIN.

¿Solo quieres probarlo sin instalar nada? Haz doble clic en `scripts\iniciar.bat`. Se abre una ventana con la dirección y el PIN, y el servidor funciona mientras esa ventana esté abierta. Windows puede preguntarte si permites el acceso a la red: acepta para **redes privadas**.

## Instalación en el iPhone

1. Conecta el iPhone a la misma red WiFi que la PC.
2. Abre **Safari** y entra a la dirección que mostró el script, por ejemplo `http://192.168.1.50:8765`.
3. Escribe el PIN.
4. Toca **Compartir → Agregar a pantalla de inicio**. Desde ahora se abre como una app.

> Consejo: en tu router, reserva una IP fija para la PC (se suele llamar "reserva DHCP"). Si la IP de la PC cambia, tendrás que volver a agregar la app con la nueva dirección.

## Configuración

Todo está en `servidor\config.json` (se crea en la primera ejecución). Después de cambiarlo, reinicia el servidor (o la PC).

```json
{
  "puerto": 8765,
  "pin": "482913",
  "multimedia_app": "Spotify",
  "multimedia_abrir": "spotify:",
  "apps": [
    { "id": "chrome",  "nombre": "Chrome",  "comando": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" },
    { "id": "spotify", "nombre": "Spotify", "comando": "%APPDATA%\\Spotify\\Spotify.exe" },
    { "id": "youtube", "nombre": "YouTube", "comando": "https://www.youtube.com" },
    { "id": "proyecto", "nombre": "Mi proyecto", "comando": "code", "argumentos": ["C:\\proyectos\\web"] }
  ]
}
```

- **`comando`** puede ser la ruta a un `.exe`, un acceso directo `.lnk`, un documento o una URL. Acepta variables como `%APPDATA%` o `%USERPROFILE%`. Recuerda escribir las barras invertidas dobles (`\\`).
- **`multimedia_app`**: la app que controla la pestaña Multimedia (por defecto `Spotify`). Si la dejas vacía (`""`), controla lo que Windows considere activo (por ejemplo YouTube en el navegador).
- **`multimedia_abrir`**: qué abrir con el botón "Abrir Spotify". `spotify:` sirve para Spotify de la Tienda o del instalador.
- **`argumentos`** es opcional, para pasarle cosas al programa.
- **`icono`** es opcional. Sin él, se usa el icono que Windows muestra para ese programa (o el favicon, si es una página web). Puedes poner la ruta a una imagen `.png`/`.jpg` propia, o a un `.exe`/`.ico` del que sacar el icono. Útil cuando el comando es algo como `code`, que no apunta directo al programa.
- Los iconos se guardan en `servidor\cache\`. Si cambias uno y no se actualiza, borra esa carpeta.
- Para encontrar la ruta de un programa: clic derecho en su acceso directo → **Propiedades** → campo **Destino**.
- Solo se pueden abrir las apps de esta lista. Desde el celular no se puede ejecutar ningún otro comando.

## Seguridad

- Cada orden lleva el PIN. Tras 5 intentos fallidos, esa dirección queda bloqueada 60 segundos.
- El firewall solo acepta conexiones de tu red local. No lo expongas a Internet (no abras el puerto en el router).
- La conexión es HTTP sin cifrar, algo razonable dentro de tu casa. Usa una red WiFi con contraseña.

## Notas

- **Suspender:** si Windows tiene la hibernación activada, el botón hiberna en lugar de suspender. Para que suspenda, ejecuta `powercfg /hibernate off` en una terminal de administrador.
- **Volumen:** cada toque sube o baja 1. Mantén presionado para que siga cambiando, o usa la barra. Cambia el volumen general de Windows (el del altavoz predeterminado).
- **Multimedia:** usa los controles de medios de Windows 10 u 11.
- **Reiniciar y apagar** piden confirmación y se ejecutan un segundo y medio después, sin esperar a que cierres programas.
- **Registro:** con el arranque automático, los mensajes del servidor quedan en `servidor\controlpc.log`.

## Actualizar

**Desde el iPhone:** pestaña **Equipo → Actualizar**. La PC descarga la última versión de GitHub, reinicia el servidor y la app se recarga sola.

**Desde la PC:** doble clic en `scripts\actualizar.bat`. Hace lo mismo y además sirve para reiniciar el servidor si algo se quedó trabado.

En los dos casos tu `servidor\config.json` (PIN y apps) y la caché de iconos no se tocan. La versión instalada queda anotada en `servidor\version.txt`.

## Desinstalar

```powershell
powershell -ExecutionPolicy Bypass -File scripts\desinstalar.ps1
```

## Desarrollo

Las pruebas corren en cualquier sistema, en modo simulado (no bloquean ni apagan nada):

```bash
python -m unittest discover tests
```

Para probar la interfaz fuera de Windows: `CONTROLPC_SIMULAR=1 python servidor/servidor.py`.
