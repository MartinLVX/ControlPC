// ControlPC: interfaz del celular. Habla con el servidor que sirvió esta página.
"use strict";

const $ = (id) => document.getElementById(id);
const CLAVE_PIN = "controlpc-pin";

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
  window.scrollTo(0, 0);
  if (nombre === "multimedia") { actualizarMultimedia(); leerVolumen(); }
  if (nombre === "sistema") actualizarSistema();
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
    const reproductor = m.reproductor || "";
    $("abrir-reproductor").hidden = m.abierta !== false || !reproductor;
    $("abrir-reproductor").textContent = `Abrir ${reproductor}`;
    $("controles").hidden = m.abierta === false && !!reproductor;
    if (m.abierta === false && reproductor) {
      $("pista-titulo").textContent = `${reproductor} está cerrado`;
      $("pista-artista").textContent = "Ábrelo para ver y controlar lo que suena";
    } else {
      $("pista-titulo").textContent = activo ? (m.titulo || "Sin título") : "Nada en reproducción";
      $("pista-artista").textContent = activo ? (m.artista || "") : `Pon algo en ${reproductor || "tu PC"}`;
    }
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

$("abrir-reproductor").addEventListener("click", async () => {
  const boton = $("abrir-reproductor");
  if (await ejecutar(boton, "/api/accion", { accion: "abrir_reproductor" }, `Abriendo ${boton.textContent.replace("Abrir ", "")}…`)) {
    setTimeout(actualizarMultimedia, 2500);
    setTimeout(actualizarMultimedia, 6000);
  }
});

// --- Volumen (de 1 en 1) -----------------------------------------------------------

let arrastrandoVolumen = false;

function pintarVolumen(v) {
  if (v.nivel === undefined) return;
  $("volumen-valor").textContent = v.silencio ? "Silencio" : `${v.nivel} %`;
  $("boton-silencio").classList.toggle("activo", !!v.silencio);
  const barra = $("volumen-barra");
  barra.classList.toggle("silencio", !!v.silencio);
  if (!arrastrandoVolumen) barra.value = v.nivel;
  barra.style.setProperty("--lleno", `${barra.value}%`);
}

async function leerVolumen() {
  if (arrastrandoVolumen || !pestanaVisible("multimedia")) return;
  try { pintarVolumen(await api("/api/volumen")); } catch { /* sin conexión */ }
}

async function accionVolumen(accion) {
  try { pintarVolumen(await api("/api/accion", { accion })); }
  catch (error) {
    if (error.estado === 401) cerrarSesion("El PIN cambió. Vuelve a escribirlo.");
    else avisar("No se pudo cambiar el volumen", true);
  }
}

// Un toque cambia 1; mantener presionado repite.
document.querySelectorAll("[data-volumen]").forEach((boton) => {
  const accion = boton.dataset.volumen;
  let espera, repeticion;
  const parar = () => { clearTimeout(espera); clearInterval(repeticion); };
  boton.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    if (navigator.vibrate) navigator.vibrate(8);
    accionVolumen(accion);
    if (accion === "silenciar") return;
    espera = setTimeout(() => { repeticion = setInterval(() => accionVolumen(accion), 110); }, 400);
  });
  ["pointerup", "pointerleave", "pointercancel"].forEach((ev) => boton.addEventListener(ev, parar));
  boton.addEventListener("contextmenu", (e) => e.preventDefault());
});

// Barra: se envía mientras se arrastra (como mucho cada 120 ms) y al soltar.
let ultimoEnvio = 0, envioPendiente;
function enviarNivel() {
  const nivel = Number($("volumen-barra").value);
  ultimoEnvio = Date.now();
  api("/api/volumen", { nivel }).then(pintarVolumen).catch(() => {});
}
$("volumen-barra").addEventListener("input", () => {
  arrastrandoVolumen = true;
  const barra = $("volumen-barra");
  barra.style.setProperty("--lleno", `${barra.value}%`);
  $("volumen-valor").textContent = `${barra.value} %`;
  clearTimeout(envioPendiente);
  const falta = 120 - (Date.now() - ultimoEnvio);
  if (falta <= 0) enviarNivel(); else envioPendiente = setTimeout(enviarNivel, falta);
});
$("volumen-barra").addEventListener("change", () => {
  clearTimeout(envioPendiente);
  arrastrandoVolumen = false;
  enviarNivel();
});

// --- Sistema: componentes y uso ------------------------------------------------------

function tamano(bytes, decimal = false) {
  if (bytes == null) return "";
  const base = decimal ? 1000 : 1024;
  const gb = bytes / base ** 3;
  if (gb >= 1000) return `${(gb / base).toFixed(gb / base >= 10 ? 0 : 1).replace(/\.0$/, "")} TB`;
  if (gb >= 1) return `${gb >= 100 ? Math.round(gb) : gb.toFixed(1).replace(/\.0$/, "")} GB`;
  return `${Math.round(bytes / base ** 2)} MB`;
}

function duracion(segundos) {
  if (segundos == null) return "";
  const d = Math.floor(segundos / 86400), h = Math.floor((segundos % 86400) / 3600), m = Math.floor((segundos % 3600) / 60);
  if (d) return `${d} d ${h} h`;
  if (h) return `${h} h ${m} min`;
  return `${m} min`;
}

function pintarMedidor(id, porcentaje) {
  const medidor = $(id);
  const valor = porcentaje == null ? null : Math.max(0, Math.min(100, porcentaje));
  medidor.querySelector(".medidor-valor").textContent = valor == null ? "–" : `${valor}%`;
  medidor.querySelector(".anillo").style.strokeDashoffset = 263.9 * (1 - (valor || 0) / 100);
  medidor.classList.toggle("alto", (valor || 0) >= 85);
}

function fila(etiqueta, valor, extra) {
  const div = document.createElement("div");
  div.className = "fila-lista";
  const e = document.createElement("p"); e.className = "fila-etiqueta"; e.textContent = etiqueta;
  const v = document.createElement("p"); v.className = "fila-valor"; v.textContent = valor || "Desconocido";
  div.append(e, v);
  if (extra) { const x = document.createElement("p"); x.className = "fila-extra"; x.textContent = extra; div.append(x); }
  return div;
}

// Windows a veces da el fabricante de la RAM como código JEDEC (p. ej. "01980000802C").
const FABRICANTES_RAM = [["0198", "Kingston"], ["9801", "Kingston"], ["80CE", "Samsung"], ["CE00", "Samsung"],
  ["80AD", "SK hynix"], ["AD00", "SK hynix"], ["859B", "Crucial"], ["9B05", "Crucial"], ["802C", "Micron"],
  ["2C00", "Micron"], ["04CD", "G.Skill"], ["CD04", "G.Skill"], ["029E", "Corsair"], ["9E02", "Corsair"],
  ["0B83", "ADATA"], ["04CB", "ADATA"]];
function fabricanteRam(texto) {
  const t = (texto || "").trim();
  if (!/^[0-9A-F]{4,}$/i.test(t)) return t;
  const hallado = FABRICANTES_RAM.find(([codigo]) => t.toUpperCase().includes(codigo));
  return hallado ? hallado[1] : "";
}

const limpiar = (texto) => (texto || "").replace(/\(R\)|\(TM\)|®|™/gi, "").replace(/\s+/g, " ").trim();
const generico = (texto) => !texto || /system (product|manufacturer)|to be filled|default string/i.test(texto);

let componentesPintados = false;

function pintarComponentes(c) {
  const lista = $("sistema-componentes");
  lista.replaceChildren();
  const p = c.procesador || {};
  lista.append(fila("Procesador", limpiar(p.nombre),
    [p.nucleos && `${p.nucleos} núcleos`, p.hilos && `${p.hilos} hilos`, p.mhz && `${(p.mhz / 1000).toFixed(1)} GHz`].filter(Boolean).join(" · ")));
  for (const g of c.graficas || []) {
    lista.append(fila("Gráfica", limpiar(g.nombre), [g.memoria && `${tamano(g.memoria)} de memoria`, g.driver && `Driver ${g.driver}`].filter(Boolean).join(" · ")));
  }
  const m = c.memoria || {};
  const modulos = m.modulos || [];
  const velocidad = modulos.find((x) => x.velocidad)?.velocidad;
  const iguales = modulos.length && modulos.every((x) => x.capacidad === modulos[0].capacidad);
  lista.append(fila("Memoria RAM", tamano(m.total),
    [modulos.length && (iguales ? `${modulos.length} × ${tamano(modulos[0].capacidad)}` : `${modulos.length} módulos`),
     velocidad && `${velocidad} MHz`, limpiar(fabricanteRam(modulos[0]?.fabricante))].filter(Boolean).join(" · ")));
  const tipos = c.discos_tipo || [];
  for (const d of c.discos || []) {
    const t = tipos.find((x) => x.modelo && d.modelo && (x.modelo.includes(d.modelo) || d.modelo.includes(x.modelo)));
    const tipo = t && t.tipo && !/unspecified|^0$/i.test(t.tipo) ? t.tipo : "";
    const bus = t && t.bus && !/unknown/i.test(t.bus) ? t.bus : "";
    lista.append(fila("Disco", limpiar(d.modelo), [tamano(d.tamano, true), tipo, bus].filter(Boolean).join(" · ")));
  }
  if (c.placa) lista.append(fila("Placa base", limpiar([c.placa.fabricante, c.placa.modelo].filter(Boolean).join(" "))));
  if (!generico(c.modelo)) lista.append(fila("Equipo", limpiar([c.fabricante, c.modelo].filter(Boolean).join(" "))));
  if (c.windows) lista.append(fila("Sistema operativo", limpiar(c.windows.nombre).replace(/^Microsoft /, ""),
    c.windows.compilacion && `Compilación ${c.windows.compilacion}`));
  componentesPintados = true;
}

function pintarDiscos(discos) {
  const lista = $("sistema-discos");
  lista.replaceChildren();
  if (!discos || !discos.length) { lista.append(fila("Discos", "Sin datos")); return; }
  for (const d of discos) {
    const div = document.createElement("div");
    div.className = "fila-lista";
    const cab = document.createElement("div"); cab.className = "disco-cabecera";
    const nombre = document.createElement("span"); nombre.textContent = d.nombre ? `${d.nombre} (${d.unidad})` : d.unidad;
    const cifra = document.createElement("span"); cifra.textContent = `${tamano(d.usado, true)} de ${tamano(d.total, true)}`;
    cab.append(nombre, cifra);
    const barra = document.createElement("div"); barra.className = "barra-uso" + (d.porcentaje >= 90 ? " alto" : "");
    const relleno = document.createElement("div"); relleno.style.width = `${d.porcentaje}%`;
    barra.append(relleno);
    div.append(cab, barra);
    lista.append(div);
  }
}

let consultandoSistema = false;

async function actualizarSistema() {
  if (consultandoSistema || !pestanaVisible("sistema")) return;
  consultandoSistema = true;
  try {
    const { componentes, uso } = await api("/api/sistema");
    pintarMedidor("medidor-cpu", uso.cpu);
    pintarMedidor("medidor-memoria", uso.memoria?.porcentaje);
    pintarMedidor("medidor-gpu", uso.gpu?.uso);
    const partes = [];
    if (uso.memoria) partes.push(`RAM ${tamano(uso.memoria.usada)} de ${tamano(uso.memoria.total)}`);
    if (uso.gpu?.memoria_usada) partes.push(`Gráfica ${tamano(uso.gpu.memoria_usada)}${uso.gpu.memoria_tipo === "compartida" ? " compartida" : ""}`);
    $("detalle-memoria").textContent = partes.join(" · ");
    $("sistema-encendida").textContent = uso.encendida != null ? `Encendida hace ${duracion(uso.encendida)}` : "";
    pintarDiscos(uso.discos);
    if (componentes && !componentesPintados) pintarComponentes(componentes);
  } catch (error) {
    if (error.estado === 401) cerrarSesion("El PIN cambió. Vuelve a escribirlo.");
  } finally {
    consultandoSistema = false;
  }
}

// --- Actualizar ControlPC -----------------------------------------------------------

const esperar = (ms) => new Promise((r) => setTimeout(r, ms));

async function servidorResponde() {
  try {
    const control = new AbortController();
    const espera = setTimeout(() => control.abort(), 2000);
    const r = await fetch("/api/ping", { cache: "no-store", signal: control.signal });
    clearTimeout(espera);
    return r.ok;
  } catch { return false; }
}

$("boton-actualizar").addEventListener("click", async () => {
  const boton = $("boton-actualizar");
  const estado = $("actualizacion-estado");
  boton.disabled = true;
  try {
    estado.textContent = "Buscando versión nueva…";
    const info = await api("/api/actualizacion");
    if (!info.hay_nueva) {
      estado.textContent = `Ya tienes la última versión (${info.disponible}).`;
      return;
    }
    if (!(await confirmar("¿Actualizar ControlPC?", "Se descarga la versión nueva y el servidor se reinicia. Tarda unos segundos.", "Actualizar"))) {
      estado.textContent = "Hay una versión nueva disponible.";
      return;
    }
    estado.textContent = "Descargando…";
    const r = await api("/api/actualizar", {});
    if (!r.actualizado) {
      estado.textContent = `Ya tienes la última versión (${r.version}).`;
      return;
    }
    estado.textContent = "Reiniciando el servidor…";
    // Se espera a que el servidor viejo se cierre y el nuevo responda; luego se recarga la app.
    await esperar(2500);
    for (let i = 0; i < 40 && !(await servidorResponde()); i++) await esperar(750);
    location.reload();
  } catch (error) {
    if (error.estado === 401) return cerrarSesion("El PIN cambió. Vuelve a escribirlo.");
    estado.textContent = error.estado ? error.message : "No se pudo conectar con la PC.";
  } finally {
    boton.disabled = false;
  }
});

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
    abrirPestana("multimedia");  // la app siempre abre en Multimedia
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
setInterval(() => { if (!document.hidden) { actualizarMultimedia(); leerVolumen(); } }, 3000);
setInterval(() => { if (!document.hidden) actualizarSistema(); }, 2500);
document.addEventListener("visibilitychange", () => {
  if (document.hidden || $("vista-panel").hidden) return;
  comprobarEstado();
  actualizarMultimedia();
  leerVolumen();
});

if (pin) entrar(); else mostrar("pin");
