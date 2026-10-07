"use strict";
/* Animación: vuelo 3D sobre el Valle de Aburrá y lluvia de avisos.

   Todo depende de un solo reloj, t en segundos: la cámara, la lluvia, los
   rótulos y el contador se calculan a partir de t, sin animaciones sueltas. Así
   la misma escena se reproduce en vivo y también se puede grabar cuadro por
   cuadro (grabar_video.py fija t, espera a que el mapa termine de cargar y toma
   la captura), y el video sale nítido aunque el equipo sea lento. */

const D = DATOS;
const N = D.n;
const DURACION = 36;
const $ = id => document.getElementById(id);
const entero = v => Math.round(v).toLocaleString("es-CO");
const limitar = (v, a, b) => Math.min(b, Math.max(a, v));
const suave = x => x * x * (3 - 2 * x);
const GRABANDO = new URLSearchParams(location.search).has("grabar");
if (GRABANDO) document.body.classList.add("grabando");

$("r-titulo-sub").textContent = `${entero(N)} avisos de arriendo, uno por uno`;
$("r-medellin-sub").textContent = `${entero(N)} avisos en ${entero(D.barrios)} barrios`;
$("r-poblado-sub").textContent =
  `De los avisos más caros por metro cuadrado, ${D.pct_caros_poblado} de cada 100 están aquí (del total, ${D.pct_todos_poblado})`;
$("c-rampa").innerHTML = D.rampa.map(c => `<div style="background:${c}"></div>`).join("");

// ── cámara ───────────────────────────────────────────────────
// Puntos de paso: centro [lng, lat], zoom, inclinación y rumbo en cada momento.
const PASOS = [
  { t: 0, c: [-75.575, 6.240], z: 9.7, p: 0, b: 0 },
  { t: 4, c: [-75.575, 6.240], z: 10.0, p: 0, b: 0 },
  { t: 11, c: [-75.588, 6.238], z: 12.0, p: 60, b: -22 },
  { t: 23, c: [-75.582, 6.236], z: 12.35, p: 62, b: 8 },
  { t: 30, c: [-75.568, 6.208], z: 13.6, p: 64, b: 32 },
  { t: 36, c: [-75.566, 6.204], z: 13.85, p: 64, b: 44 },
];
function camara(t) {
  let k = 0;
  while (k < PASOS.length - 2 && t > PASOS[k + 1].t) k++;
  const a = PASOS[k], b = PASOS[k + 1];
  const e = suave(limitar((t - a.t) / (b.t - a.t), 0, 1));
  const mezcla = (x, y) => x + (y - x) * e;
  return {
    center: [mezcla(a.c[0], b.c[0]), mezcla(a.c[1], b.c[1])],
    zoom: mezcla(a.z, b.z), pitch: mezcla(a.p, b.p), bearing: mezcla(a.b, b.b),
  };
}

// ── lluvia ───────────────────────────────────────────────────
// Entre estos segundos caen los avisos, del más barato al más caro por m².
const LLUVIA = [12, 23];
const ESTELA = Math.max(300, Math.round(N * 0.05)); // cuántos avisos tarda un punto en "asentarse"
const umbral = t => t <= LLUVIA[0] ? 0 : t >= LLUVIA[1] ? N
  : Math.round(N * suave((t - LLUVIA[0]) / (LLUVIA[1] - LLUVIA[0])));
// Después de la lluvia los últimos avisos (los más caros) no tienen quién caiga
// detrás de ellos; se les da un segundo y medio para encoger a su tamaño.
const asiento = t => t <= LLUVIA[1] ? umbral(t) : N + Math.round(ESTELA * limitar((t - LLUVIA[1]) / 1.5, 0, 1));

// ── rótulos ──────────────────────────────────────────────────
const ROTULOS = [
  ["r-titulo", 0.6, 4.6], ["r-valle", 5.0, 8.2], ["r-medellin", 8.6, 11.6],
  ["r-lluvia", 12.4, 17.5], ["r-poblado", 24.5, 30.0], ["r-final", 31.0, 37.0],
];
const aparicion = (t, a, b, f = 0.6) => limitar(Math.min((t - a) / f, (b - t) / f), 0, 1);

// ── mapa ─────────────────────────────────────────────────────
const inicio = camara(0);
const mapa = MapaSatelite.crear("escena", {
  ...inicio, interactive: false, maxPitch: 70, fadeDuration: 0,
  // Para grabar hace falta leer el lienzo después de dibujar.
  preserveDrawingBuffer: GRABANDO,
});

/* Qué avisos se ven va en un filtro y no en la opacidad: cambiar una propiedad de
   pintura que depende de cada punto obliga a recalcular los 17 mil en cada cuadro
   (en vivo bajaba a 41 FPS); el filtro es más barato. */
let ultimo = "";
function pintarLluvia(u, a) {
  if (`${u}|${a}` === ultimo || !mapa.getLayer("avisos")) return;
  ultimo = `${u}|${a}`;
  mapa.setFilter("avisos", ["<", ["get", "k"], u]);
  // Cada aviso cae grande y se asienta a su tamaño a medida que caen los siguientes.
  if (a < N + ESTELA) mapa.setPaintProperty("avisos", "circle-radius", ["interpolate", ["linear"], ["-", a, ["get", "k"]], 0, 9, ESTELA, 2.6]);
  else mapa.setPaintProperty("avisos", "circle-radius", 2.6);
}

/* En vivo, la lluvia se actualiza 12 veces por segundo y no en cada cuadro: con
   cada cuadro la reproducción caía a 28 FPS, y así se queda en 60 (medido con la
   caché caliente). Caen unos 130 avisos por actualización, la diferencia no se ve.
   Al grabar se actualiza en todos los cuadros. */
const LLUVIA_VIVO_MS = 83;
let ultimaLluvia = -Infinity;
function aplicar(t, vivo = false) {
  mapa.jumpTo(camara(t));
  const u = umbral(t);
  const ahora = performance.now();
  if (!vivo || ahora - ultimaLluvia >= LLUVIA_VIVO_MS || t >= LLUVIA[1] + 1.5) {
    ultimaLluvia = ahora;
    pintarLluvia(u, asiento(t));
  }
  for (const [id, a, b] of ROTULOS) {
    const o = aparicion(t, a, b);
    const el = $(id);
    el.style.opacity = o;
    el.style.transform = `translateY(${(1 - o) * 10}px)`;
  }
  const oc = aparicion(t, LLUVIA[0] - 0.2, 29.5, 0.5);
  $("contador").style.opacity = oc;
  if (u > 0) {
    $("c-n").textContent = entero(u);
    $("c-precio").textContent = `Último: $${entero(D.precio_m2[u - 1])} por m²`;
    const tramo = D.tramo[u - 1];
    [...$("c-rampa").children].forEach((el, k) => el.classList.toggle("lleno", k <= tramo));
  }
  $("b-tiempo").style.width = `${(t / DURACION) * 100}%`;
}

const cargado = new Promise(resolver => {
  mapa.on("load", () => {
    // Relieve libre de AWS (Mapzen Terrain Tiles): sin clave, codificado en terrarium.
    mapa.addSource("relieve", {
      type: "raster-dem", encoding: "terrarium", tileSize: 256, maxzoom: 15,
      tiles: ["https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"],
      attribution: "Relieve: Mapzen Terrain Tiles, AWS Open Data",
    });
    mapa.setTerrain({ source: "relieve", exaggeration: 1.4 });
    const rasgos = D.lat.map((la, k) => ({
      type: "Feature", id: k, properties: { k, c: D.rampa[D.tramo[k]] },
      geometry: { type: "Point", coordinates: [D.lng[k], la] },
    }));
    mapa.addSource("avisos", { type: "geojson", data: { type: "FeatureCollection", features: rasgos } });
    mapa.addLayer({ id: "avisos", type: "circle", source: "avisos", paint: {
      "circle-color": ["get", "c"], "circle-stroke-color": "#ffffff", "circle-stroke-width": 0.6,
      "circle-opacity": 0.92, "circle-stroke-opacity": 0.8, "circle-radius": 2.6,
      // Con la cámara inclinada, MapLibre agranda por defecto los puntos cercanos;
      // aquí todos miden lo mismo en pantalla.
      "circle-pitch-scale": "viewport",
    }, filter: ["<", ["get", "k"], 0] });
    aplicar(0);
    mapa.once("idle", resolver);
  });
});

// ── grabación cuadro por cuadro ──────────────────────────────
// Fija el reloj en t y resuelve cuando el mapa terminó de cargar y dibujar ese cuadro.
window.DURACION = DURACION;
window.listoParaGrabar = cargado;
window.fijarTiempo = t => new Promise(resolver => {
  aplicar(t);
  const espera = setTimeout(resolver, 6000); // por si una tesela no llega nunca
  mapa.once("idle", () => { clearTimeout(espera); resolver(); });
  mapa.triggerRepaint();
});

// ── reproducción en vivo ─────────────────────────────────────
let origen = null, pausado = false, tPausa = 0, cuadro = 0;
function reproducir(ahora) {
  if (!pausado) {
    if (origen === null) origen = ahora;
    const t = Math.min((ahora - origen) / 1000, DURACION);
    aplicar(t, true);
    if (t >= DURACION) return;
  }
  cuadro = requestAnimationFrame(reproducir);
}
$("b-pausa").addEventListener("click", () => {
  pausado = !pausado;
  $("b-pausa").textContent = pausado ? "Seguir" : "Pausa";
  if (pausado) tPausa = performance.now();
  else if (origen !== null) origen += performance.now() - tPausa;
});
$("b-repetir").addEventListener("click", () => {
  cancelAnimationFrame(cuadro);
  origen = null; pausado = false;
  $("b-pausa").textContent = "Pausa";
  cuadro = requestAnimationFrame(reproducir);
});
if (!GRABANDO) cargado.then(() => { cuadro = requestAnimationFrame(reproducir); });
