/* Buscador de convenios — JS vanilla, sin dependencias.
   Carga datos/convenios.json (generado por el scraper) y filtra en cliente. */

"use strict";

const FUENTES = {
  "BOE":    { nombre: "BOE · Estatal",        url: "https://www.boe.es",
              clase: "bg-ctp-blue text-ctp-base" },
  "DOGV":   { nombre: "DOGV · C. Valenciana", url: "https://dogv.gva.es",
              clase: "bg-ctp-peach text-ctp-base" },
  "BOP-CS": { nombre: "BOP Castelló",         url: "https://bop.dipcas.es/PortalBOP/",
              clase: "bg-ctp-green text-ctp-base" },
  "BOP-V":  { nombre: "BOP València",         url: "https://bop.dival.es/bop/",
              clase: "bg-ctp-teal text-ctp-base" },
  "BOP-A":  { nombre: "BOP Alicante",         url: "https://sede.diputacionalicante.es/consultas-bop/",
              clase: "bg-ctp-mauve text-ctp-base" },
  "BORM":   { nombre: "BORM · Murcia",        url: "https://www.borm.es",
              clase: "bg-ctp-maroon text-ctp-base" },
};
const MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
               "agosto", "septiembre", "octubre", "noviembre", "diciembre"];
const PAGINA = 50;

const $ = (id) => document.getElementById(id);
let todos = [];          // todos los convenios
let filtrados = [];      // resultado del filtro actual
let visibles = 0;        // cuántos se muestran ya
let mesPintado = "";     // último subtítulo de mes añadido a la lista
const activas = new Set(Object.keys(FUENTES));

/* ---------- utilidades ---------- */

function fechaBonita(iso) {
  if (!iso) return "";
  const [a, m, d] = iso.split("-");
  return `${d}/${m}/${a}`;
}

function mesLargo(iso) {
  const [a, m] = iso.split("-");
  return `${MESES[Number(m) - 1]} de ${a}`;
}

function normaliza(s) {
  return (s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
}

function esc(s) {
  const d = document.createElement("span");
  d.textContent = s || "";
  return d.innerHTML.replaceAll('"', "&quot;");
}

/* ---------- filtro ---------- */

function filtrosActivos() {
  let n = 0;
  if ($("desde").value) n++;
  if ($("hasta").value) n++;
  if (activas.size < Object.keys(FUENTES).length) n++;
  return n;
}

function aplicarFiltro() {
  const q = normaliza($("q").value.trim());
  const desde = $("desde").value;
  const hasta = $("hasta").value;
  const palabras = q.split(/\s+/).filter(Boolean);

  filtrados = todos.filter((c) => {
    if (!activas.has(c.fuente)) return false;
    if (desde && c.fecha_publicacion < desde) return false;
    if (hasta && c.fecha_publicacion > hasta) return false;
    if (palabras.length) {
      const pajar = normaliza(
        `${c.titulo} ${c.codigo_convenio} ${c.numero_diario} ` +
        `${c.fecha_publicacion} ${c.fuente} ${FUENTES[c.fuente]?.nombre || ""}`);
      if (!palabras.every((p) => pajar.includes(p))) return false;
    }
    return true;
  });

  visibles = 0;
  mesPintado = "";
  $("lista").innerHTML = "";
  mostrarMas();

  $("recuento").textContent =
    `${filtrados.length.toLocaleString("es")} de ${todos.length.toLocaleString("es")}`;
  $("vacio").classList.toggle("hidden", filtrados.length > 0);

  const n = filtrosActivos();
  $("num-filtros").textContent = String(n);
  $("num-filtros").classList.toggle("hidden", n === 0);
}

/* ---------- pintado ---------- */

function esqueleto() {
  const frag = document.createDocumentFragment();
  for (let i = 0; i < 4; i++) {
    const div = document.createElement("div");
    div.className = "mb-3 animate-pulse rounded-xl bg-ctp-base p-4 shadow-sm";
    div.setAttribute("aria-hidden", "true");
    div.innerHTML = `
      <div class="flex justify-between">
        <div class="h-5 w-28 rounded-full bg-ctp-surface0"></div>
        <div class="h-4 w-20 rounded bg-ctp-surface0"></div>
      </div>
      <div class="mt-3 h-4 w-full rounded bg-ctp-surface0"></div>
      <div class="mt-2 h-4 w-2/3 rounded bg-ctp-surface0"></div>`;
    frag.appendChild(div);
  }
  $("lista").appendChild(frag);
}

function tarjeta(c) {
  const art = document.createElement("article");
  art.className =
    "rounded-xl bg-ctp-base p-4 shadow-sm ring-1 ring-ctp-surface0";

  const f = FUENTES[c.fuente] || { nombre: c.fuente, clase: "bg-ctp-surface1 text-ctp-text" };
  const codigo = c.codigo_convenio
    ? `<span class="text-xs text-ctp-subtext0">Código
         <code class="rounded bg-ctp-mantle px-1">${esc(c.codigo_convenio)}</code>
       </span>`
    : "<span></span>";

  art.innerHTML = `
    <div class="flex items-center justify-between gap-2">
      <span class="rounded-full px-2.5 py-0.5 text-xs font-semibold ${f.clase}">${f.nombre}</span>
      <time datetime="${c.fecha_publicacion}"
            class="text-xs font-medium text-ctp-subtext0">
        ${fechaBonita(c.fecha_publicacion)}
      </time>
    </div>
    <h3 class="mt-2 leading-snug">${esc(c.titulo)}</h3>
    <div class="mt-3 flex items-center justify-between gap-2">
      ${codigo}
      <a href="${esc(c.url_pdf)}" target="_blank" rel="noopener"
         class="shrink-0 rounded-lg bg-ctp-mantle px-3 py-1.5 text-sm font-semibold text-ctp-red
                ring-1 ring-inset ring-ctp-surface0 hover:bg-ctp-crust
                focus:outline-none focus:ring-2 focus:ring-ctp-red">
        Mostrar PDF&nbsp;↗
      </a>
    </div>`;
  return art;
}

function mostrarMas() {
  const trozo = filtrados.slice(visibles, visibles + PAGINA);
  const frag = document.createDocumentFragment();
  for (const c of trozo) {
    const mes = mesLargo(c.fecha_publicacion);
    if (mes !== mesPintado) {
      mesPintado = mes;
      const h = document.createElement("h2");
      h.className =
        "mt-6 mb-2 text-sm font-bold uppercase tracking-wide text-ctp-subtext0 first:mt-0";
      h.textContent = mes;
      frag.appendChild(h);
    }
    const envoltorio = document.createElement("div");
    envoltorio.className = "mb-3";
    envoltorio.appendChild(tarjeta(c));
    frag.appendChild(envoltorio);
  }
  $("lista").appendChild(frag);
  visibles += trozo.length;
  $("mas").classList.toggle("hidden", visibles >= filtrados.length);
  $("mas").textContent =
    `Mostrar más (${(filtrados.length - visibles).toLocaleString("es")} restantes)`;
}

/* ---------- pie: diarios con su último boletín ---------- */

function pintarDiarios(ultimos) {
  const cont = $("diarios");
  cont.innerHTML = "";
  for (const [clave, f] of Object.entries(FUENTES)) {
    const u = ultimos?.[clave];
    const detalle = u
      ? `Último: nº ${esc(u.numero)} · ${fechaBonita(u.fecha)}`
      : "Último número no disponible";
    const li = document.createElement("li");
    li.innerHTML = `
      <a href="${f.url}" target="_blank" rel="noopener"
         class="group flex items-center justify-between gap-3 rounded-lg border border-ctp-surface1 px-3 py-2
                hover:border-ctp-red hover:bg-ctp-mantle focus:outline-none focus:ring-2 focus:ring-ctp-red">
        <span>
          <span class="font-semibold text-ctp-subtext1 group-hover:text-ctp-red">${f.nombre}</span>
          <span class="block text-xs text-ctp-subtext0">${detalle}</span>
        </span>
        <span aria-hidden="true" class="text-ctp-overlay0 group-hover:text-ctp-red">↗</span>
      </a>`;
    cont.appendChild(li);
  }
}

/* ---------- tema claro / oscuro ---------- */

const consultaOscuro = window.matchMedia("(prefers-color-scheme: dark)");

function temaActual() {
  return document.documentElement.dataset.theme ||
         (consultaOscuro.matches ? "dark" : "light");
}

function pintarBotonTema() {
  const oscuro = temaActual() === "dark";
  // El icono anuncia a dónde vas, no dónde estás.
  $("tema-icono").textContent = oscuro ? "☀️" : "🌙";
  $("tema").setAttribute(
    "aria-label", oscuro ? "Cambiar a modo claro" : "Cambiar a modo oscuro");
  $("tema").title = oscuro ? "Modo claro" : "Modo oscuro";
}

function prepararTema() {
  pintarBotonTema();
  $("tema").addEventListener("click", () => {
    const nuevo = temaActual() === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = nuevo;
    try {
      localStorage.setItem("tema", nuevo);
    } catch (e) {
      // Modo privado o almacenamiento bloqueado: el cambio vale para
      // esta visita, simplemente no se recuerda.
    }
    pintarBotonTema();
  });
  // Si no se ha elegido nada, seguir al sistema cuando cambie.
  consultaOscuro.addEventListener("change", () => {
    if (!document.documentElement.dataset.theme) pintarBotonTema();
  });
}

/* ---------- filtros: panel y botones de fuente ---------- */

function estiloBoton(btn, clave, activa) {
  const f = FUENTES[clave];
  btn.textContent = (activa ? "✓ " : "") + f.nombre;
  btn.setAttribute("aria-pressed", String(activa));
  btn.className = "boton-fuente rounded-full px-3 py-1.5 text-sm font-semibold " +
    "focus:outline-none focus:ring-2 focus:ring-ctp-red " +
    (activa
      ? f.clase
      : "bg-ctp-base text-ctp-overlay0 ring-1 ring-inset ring-ctp-surface1");
}

function pintarFuentes() {
  const cont = $("fuentes");
  for (const clave of Object.keys(FUENTES)) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.dataset.fuente = clave;
    estiloBoton(btn, clave, true);
    btn.addEventListener("click", () => {
      const activa = activas.has(clave);
      if (activa && activas.size === 1) return;   // siempre una activa
      activa ? activas.delete(clave) : activas.add(clave);
      estiloBoton(btn, clave, !activa);
      aplicarFiltro();
    });
    cont.appendChild(btn);
  }
}

function quitarFiltros() {
  $("q").value = ""; $("desde").value = ""; $("hasta").value = "";
  activas.clear();
  Object.keys(FUENTES).forEach((k) => activas.add(k));
  document.querySelectorAll("#fuentes button").forEach((b) =>
    estiloBoton(b, b.dataset.fuente, true));
  aplicarFiltro();
}

/* ---------- arranque ---------- */

async function arrancar() {
  prepararTema();
  pintarFuentes();
  pintarDiarios(null);
  esqueleto();

  $("abrir-filtros").addEventListener("click", () => {
    const panel = $("filtros");
    const abierto = !panel.hidden;
    panel.hidden = abierto;
    $("abrir-filtros").setAttribute("aria-expanded", String(!abierto));
  });

  // "/" enfoca el buscador desde cualquier punto de la página
  document.addEventListener("keydown", (e) => {
    if (e.key === "/" && !/^(input|textarea|select)$/i.test(e.target.tagName)) {
      e.preventDefault();
      $("q").focus();
    }
  });

  let datos;
  try {
    // Sin "no-store": así el navegador puede reaprovechar su copia y
    // revalidarla con el ETag (respuesta 304, casi cero bytes) en vez de
    // volver a bajarse el fichero entero en cada visita. Los datos
    // cambian una vez al día; GitHub Pages los da con max-age=600.
    const r = await fetch("datos/convenios.json");
    datos = await r.json();
  } catch {
    $("lista").innerHTML = "";
    $("meta").textContent = "No se han podido cargar los datos.";
    return;
  }

  todos = datos.items || [];
  const gen = (datos.generado || "").slice(0, 10);
  $("meta").textContent =
    `${(datos.total || 0).toLocaleString("es")} convenios y acuerdos laborales · ` +
    `actualizado el ${fechaBonita(gen)}`;
  pintarDiarios(datos.ultimos);

  const conError = Object.entries(datos.estado || {})
    .filter(([, v]) => String(v).startsWith("error")).map(([k]) => k);
  if (conError.length) {
    $("estado-fuentes").textContent =
      `⚠️ En la última actualización fallaron: ${conError.join(", ")}.`;
  }

  let temporizador;
  $("q").addEventListener("input", () => {
    clearTimeout(temporizador);
    temporizador = setTimeout(aplicarFiltro, 200);
  });
  $("desde").addEventListener("change", aplicarFiltro);
  $("hasta").addEventListener("change", aplicarFiltro);
  $("mas").addEventListener("click", mostrarMas);
  $("limpiar").addEventListener("click", quitarFiltros);
  $("limpiar-vacio").addEventListener("click", quitarFiltros);

  // Nada de carga automática al llegar al final: con scroll infinito el
  // pie (los diarios y su último boletín) se aleja cada vez que te
  // acercas y no hay manera de llegar. Se amplía solo al pulsar.

  aplicarFiltro();
}

arrancar();
