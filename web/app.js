// ControlPC: interfaz del celular. Habla con el servidor que sirvió esta página.
"use strict";

const $ = (id) => document.getElementById(id);
const CLAVE_PIN = "controlpc-pin";

function leerPin() {
  try { return localStorage.getItem(CLAVE_PIN) || ""; } catch { return ""; }
}
function guardarPin(pin) {
  try { pin ? localStorage.setItem(CLAVE_PIN, pin) : localStorage.removeItem(CLAVE_PIN); } catch { /* sin almacenamiento */ }
}

let pin = leerPin();
let temporizadorAviso;

function avisar(texto, mal = false) {
  const aviso = $("aviso");
  aviso.textContent = texto;
  aviso.classList.toggle("mal", mal);
  aviso.classList.add("visible");
  clearTimeout(temporizadorAviso);
  temporizadorAviso = setTimeout(() => aviso.classList.remove("visible"), 2200);
}

async function api(ruta, datos) {
  const opciones = { headers: { "X-PIN": pin }, cache: "no-store" };
  if (datos !== undefined) {
    opciones.method = "POST";
    opciones.headers["Content-Type"] = "application/json";
    opciones.body = JSON.stringify(datos);
  }
  const respuesta = await fetch(ruta, opciones);
  const cuerpo = await respuesta.json().catch(() => ({}));
  if (!respuesta.ok) {
    const error = new Error(cuerpo.error || `Error ${respuesta.status}`);
    error.estado = respuesta.status;
    throw error;
  }
  return cuerpo;
}

function mostrar(vista) {
  $("vista-pin").hidden = vista !== "pin";
  $("vista-panel").hidden = vista !== "panel";
}

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
    boton.className = "boton app";
    boton.textContent = app.nombre;
    boton.addEventListener("click", () => ejecutar(boton, "/api/abrir", { id: app.id }, `Abriendo ${app.nombre}`));
    contenedor.append(boton);
  }
}

async function ejecutar(boton, ruta, datos, textoOk) {
  if (navigator.vibrate) navigator.vibrate(15);
  boton.disabled = true;
  try {
    await api(ruta, datos);
    avisar(textoOk);
  } catch (error) {
    if (error.estado === 401) return cerrarSesion("El PIN cambió. Vuelve a escribirlo.");
    avisar(error.estado ? error.message : "No se pudo conectar con la PC", true);
  } finally {
    boton.disabled = false;
  }
}

const TEXTOS = {
  bloquear: "PC bloqueada",
  suspender: "Suspendiendo…",
  reiniciar: "Reiniciando…",
  apagar: "Apagando…",
  subir_volumen: "Volumen +",
  bajar_volumen: "Volumen −",
  silenciar: "Silencio activado/desactivado",
};

document.querySelectorAll("[data-accion]").forEach((boton) => {
  boton.addEventListener("click", () => {
    const pregunta = boton.dataset.confirmar;
    if (pregunta && !confirm(pregunta)) return;
    const accion = boton.dataset.accion;
    ejecutar(boton, "/api/accion", { accion }, TEXTOS[accion] || "Hecho");
  });
});

// Indicador de encendido: consulta la PC cada 5 segundos.
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

async function entrar() {
  try {
    const info = await api("/api/info");
    $("nombre-equipo").textContent = info.equipo;
    pintarApps(info.apps);
    mostrar("panel");
    comprobarEstado();
    return true;
  } catch (error) {
    if (error.estado === 401 || error.estado === 429) {
      cerrarSesion(error.message);
    } else {
      // La PC no responde: se muestra el panel con el estado "Sin conexión".
      mostrar("panel");
      comprobarEstado();
    }
    return false;
  }
}

function cerrarSesion(mensaje = "") {
  pin = "";
  guardarPin("");
  $("error-pin").textContent = mensaje;
  $("campo-pin").value = "";
  mostrar("pin");
}

$("form-pin").addEventListener("submit", async (evento) => {
  evento.preventDefault();
  pin = $("campo-pin").value.trim();
  if (await entrar()) guardarPin(pin);
});

$("salir").addEventListener("click", () => cerrarSesion());

setInterval(() => { if (!$("vista-panel").hidden) comprobarEstado(); }, 5000);
document.addEventListener("visibilitychange", () => {
  if (!document.hidden && !$("vista-panel").hidden) comprobarEstado();
});

if (pin) entrar(); else mostrar("pin");
