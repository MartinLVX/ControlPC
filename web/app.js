// ControlPC: interfaz del celular. Habla con el servidor que sirvió esta página.
"use strict";

const $ = (id) => document.getElementById(id);
const CLAVE_PIN = "controlpc-pin";
const CLAVE_PESTANA = "controlpc-pestana";

function leer(clave) {
  try { return localStorage.getItem(clave) || ""; } catch { return ""; }
}
function guardar(clave, valor) {
  try { valor ? localStorage.setItem(clave, valor) : localStorage.removeItem(clave); } catch { /* sin almacenamiento */ }
}

let pin = leer(CLAVE_PIN);
let temporizadorAviso;

function avisar(texto, mal = false) {
  const aviso = $("aviso");
  aviso.textContent = texto;
  aviso.classList.toggle("mal", mal);
  aviso.classList.add("visible");
  clearTimeout(temporizadorAviso);
  temporizadorAviso = setTimeout(() => aviso.classList.remove("visible"), 2200);
}

async function pedir(ruta, datos) {
  const opciones = { headers: { "X-PIN": pin }, cache: "no-store" };
  if (datos !== undefined) {
    opciones.method = "POST";
    opciones.headers["Content-Type"] = "application/json";
    opciones.body = JSON.stringify(datos);
  }
  const respuesta = await fetch(ruta, opciones);
  if (!respuesta.ok) {
    const cuerpo = await respuesta.json().catch(() => ({}));
    const error = new Error(cuerpo.error || `Error ${respuesta.status}`);
    error.estado = respuesta.status;
    throw error;
  }
  return respuesta;
}
const api = async (ruta, datos) => (await pedir(ruta, datos)).json();

// Las imágenes también llevan el PIN, así que se piden con fetch y se muestran como blob.
async function imagen(ruta) {
  try {
    const respuesta = await pedir(ruta);
    return URL.createObjectURL(await respuesta.blob());
  } catch { return null; }
}

function mostrar(vista) {
  $("vista-pin").hidden = vista !== "pin";
  $("vista-panel").hidden = vista !== "panel";
}

// --- Pestañas ---------------------------------------------------------------

function abrirPestana(nombre) {
  document.querySelectorAll(".pestana").forEach((p) => { p.hidden = p.id !== `pestana-${nombre}`; });
  document.querySelectorAll("[data-pestana]").forEach((b) => b.classList.toggle("activa", b.dataset.pestana === nombre));
  guardar(CLAVE_PESTANA, nombre);
  window.scrollTo(0, 0);
  if (nombre === "multimedia") actualizarMultimedia();
}
document.querySelectorAll("[data-pestana]").forEach((boton) => {
  boton.addEventListener("click", () => abrirPestana(boton.dataset.pestana));
});
const pestanaVisible = (nombre) => !$("vista-panel").hidden && !$(`pestana-${nombre}`).hidden;

// --- Aplicaciones -------------------------------------------------------------

function pintarApps(apps) {
  const contenedor = $("apps");
  contenedor.replaceChildren();
  if (!apps.length) {
    const vacio = document.createElement("p");
    vacio.className = "vacio";
    vacio.textContent = "No hay aplicaciones. Agrégalas en servidor/config.json de tu PC.";
    contenedor.append(vacio);
    return;
  }
  for (const app of apps) {
    const boton = document.createElement("button");
    boton.className = "app";

    // Mientras llega el icono real (o si no hay), se muestra la inicial.
    const inicial = document.createElement("span");
    inicial.className = "app-inicial";
    inicial.textContent = app.nombre.trim().charAt(0).toUpperCase();

    const nombre = document.createElement("span");
    nombre.className = "app-nombre";
    nombre.textContent = app.nombre;

    boton.append(inicial, nombre);
    boton.addEventListener("click", () => ejecutar(boton, "/api/abrir", { id: app.id }, `Abriendo ${app.nombre}`));
    contenedor.append(boton);

    imagen(`/api/icono/${encodeURIComponent(app.id)}`).then((url) => {
      if (!url) return;
      const img = document.createElement("img");
      img.className = "app-icono";
      img.alt = "";
      img.src = url;
      img.onload = () => inicial.replaceWith(img);
    });
  }
}

// --- Acciones -------------------------------------------------------------------

async function ejecutar(boton, ruta, datos, textoOk) {
  if (navigator.vibrate) navigator.vibrate(12);
  boton.disabled = true;
  try {
    await api(ruta, datos);
    if (textoOk) avisar(textoOk);
    return true;
  } catch (error) {
    if (error.estado === 401) cerrarSesion("El PIN cambió. Vuelve a escribirlo.");
    else avisar(error.estado ? error.message : "No se pudo conectar con la PC", true);
    return false;
  } finally {
    boton.disabled = false;
  }
}

const TEXTOS = {
  bloquear: "PC bloqueada",
  suspender: "Suspendiendo…",
  reiniciar: "Reiniciando…",
  apagar: "Apagando…",
  subir_volumen: "Volumen +10 %",
  bajar_volumen: "Volumen −10 %",
  silenciar: "Silencio",
};

function confirmar(titulo, detalle, textoSi) {
  return new Promise((resolver) => {
    $("confirmacion-titulo").textContent = titulo;
    $("confirmacion-detalle").textContent = detalle || "";
    $("confirmacion-detalle").hidden = !detalle;
    $("confirmacion-si").textContent = textoSi;
    $("confirmacion").hidden = false;
    const cerrar = (valor) => {
      $("confirmacion").hidden = true;
      $("confirmacion-si").onclick = $("confirmacion-no").onclick = $("confirmacion").onclick = null;
      resolver(valor);
    };
    $("confirmacion-si").onclick = () => cerrar(true);
    $("confirmacion-no").onclick = () => cerrar(false);
    $("confirmacion").onclick = (e) => { if (e.target === $("confirmacion")) cerrar(false); };
  });
}

document.querySelectorAll("[data-accion]").forEach((boton) => {
  boton.addEventListener("click", async () => {
    const accion = boton.dataset.accion;
    if (boton.dataset.confirmar) {
      const etiqueta = boton.querySelector("span")?.textContent || "Sí";
      if (!(await confirmar(boton.dataset.confirmar, boton.dataset.detalle, etiqueta))) return;
    }
    const ok = await ejecutar(boton, "/api/accion", { accion }, TEXTOS[accion]);
    if (ok && ["reproducir_pausar", "siguiente", "anterior"].includes(accion)) {
      setTimeout(actualizarMultimedia, 700);
    }
  });
});

// --- Multimedia -------------------------------------------------------------------

const NOMBRES_APPS = {
  spotify: "Spotify", chrome: "Chrome", msedge: "Edge", firefox: "Firefox", opera: "Opera",
  brave: "Brave", vlc: "VLC", zunemusic: "Reproductor multimedia", zunevideo: "Películas y TV",
  applemusic: "Apple Music", itunes: "iTunes",
};
function nombreApp(id) {
  if (!id) return "";
  let nombre = id.split("!").pop().replace(/\.exe$/i, "").split(/[.\\]/).pop();
  return NOMBRES_APPS[nombre.toLowerCase()] || nombre;
}

let portadaActual = null;
let consultandoMultimedia = false;

async function actualizarMultimedia() {
  if (consultandoMultimedia || !pestanaVisible("multimedia")) return;
  consultandoMultimedia = true;
  try {
    const m = await api("/api/multimedia");
    const activo = m.activo && (m.titulo || m.artista);
    $("pista-titulo").textContent = activo ? (m.titulo || "Sin título") : "Nada en reproducción";
    $("pista-artista").textContent = activo ? (m.artista || "") : "Reproduce algo en tu PC";
    $("pista-app").textContent = activo ? nombreApp(m.app) : "";
    const sonando = m.estado === "Playing";
    $("boton-play").querySelector("use").setAttribute("href", sonando ? "#i-pausa" : "#i-play");
    $("boton-play").setAttribute("aria-label", sonando ? "Pausar" : "Reproducir");

    if (m.portada !== portadaActual) {
      portadaActual = m.portada;
      const url = m.portada ? await imagen(`/api/multimedia/portada?v=${m.portada}`) : null;
      const img = $("portada");
      if (img.src.startsWith("blob:")) URL.revokeObjectURL(img.src);
      if (url) img.src = url; else img.removeAttribute("src");
      img.hidden = !url;
      $("portada-vacia").hidden = !!url;
    }
  } catch (error) {
    if (error.estado === 401) cerrarSesion("El PIN cambió. Vuelve a escribirlo.");
  } finally {
    consultandoMultimedia = false;
  }
}

// --- Estado de la PC -------------------------------------------------------------

async function comprobarEstado() {
  let encendida = false;
  try {
    const control = new AbortController();
    const espera = setTimeout(() => control.abort(), 3000);
    const r = await fetch("/api/ping", { cache: "no-store", signal: control.signal });
    clearTimeout(espera);
    encendida = r.ok;
  } catch { /* sin respuesta */ }
  $("punto").className = "punto " + (encendida ? "encendida" : "apagada");
  $("texto-estado").textContent = encendida ? "Encendida" : "Sin conexión";
  // Si la PC volvió y aún no se cargaron las apps, se cargan ahora.
  if (encendida && !$("apps").childElementCount) entrar();
}

// --- Sesión ------------------------------------------------------------------

async function entrar() {
  try {
    const info = await api("/api/info");
    $("nombre-equipo").textContent = info.equipo;
    pintarApps(info.apps);
    mostrar("panel");
    abrirPestana(leer(CLAVE_PESTANA) || "apps");
    comprobarEstado();
    return true;
  } catch (error) {
    if (error.estado === 401 || error.estado === 429) {
      cerrarSesion(error.message);
    } else {
      mostrar("panel");
      comprobarEstado();
    }
    return false;
  }
}

function cerrarSesion(mensaje = "") {
  pin = "";
  guardar(CLAVE_PIN, "");
  $("error-pin").textContent = mensaje;
  $("campo-pin").value = "";
  mostrar("pin");
}

$("form-pin").addEventListener("submit", async (evento) => {
  evento.preventDefault();
  pin = $("campo-pin").value.trim();
  if (await entrar()) guardar(CLAVE_PIN, pin);
});

$("salir").addEventListener("click", () => cerrarSesion());

setInterval(() => { if (!$("vista-panel").hidden && !document.hidden) comprobarEstado(); }, 5000);
setInterval(() => { if (!document.hidden) actualizarMultimedia(); }, 3000);
document.addEventListener("visibilitychange", () => {
  if (document.hidden || $("vista-panel").hidden) return;
  comprobarEstado();
  actualizarMultimedia();
});

if (pin) entrar(); else mostrar("pin");
