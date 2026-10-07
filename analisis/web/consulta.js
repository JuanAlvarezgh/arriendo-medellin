"use strict";

// ---------------------------------------------------------------------------
// Datos y formatos
// ---------------------------------------------------------------------------

const M = DATOS.meta;
const A = DATOS.avisos;
const N = A.precio.length;
const BARRIOS = DATOS.barrios;
const SM = M.salario_minimo;
const REJILLA = DATOS.rejilla;

const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const entero = v => Math.round(v).toLocaleString("es-CO");
const pesos = v => "$" + Math.round(v).toLocaleString("es-CO");
const millones = v => "$" + (v / 1e6).toLocaleString("es-CO", { maximumFractionDigits: v < 1e7 ? 1 : 0 }) + " M";
const miles = v => "$" + Math.round(v / 1000).toLocaleString("es-CO") + " mil";
const dec = (v, d = 2) => v.toLocaleString("es-CO", { minimumFractionDigits: d, maximumFractionDigits: d });
const pct = (v, d = 0) => (v * 100).toLocaleString("es-CO", { minimumFractionDigits: d, maximumFractionDigits: d }) + " %";
const pctEje = v => pct(v, Math.abs(v * 100 - Math.round(v * 100)) > 1e-9 ? 1 : 0);
const pctSigno = (v, d = 0) => (v >= 0 ? "+" : "−") + pct(Math.abs(v), d);
const salarios = v => (v / SM).toLocaleString("es-CO", { maximumFractionDigits: 1 }) + " salarios mínimos";
const valorP = p => p < 0.0001 ? "< 0,0001" : dec(p, 4);
const fr = (a, b) => `<span class="fr"><span>${a}</span><span>${b}</span></span>`;
const $ = id => document.getElementById(id);
const leerNumero = s => { const v = Number(String(s ?? "").replace(/[^\d]/g, "")); return v > 0 ? v : null; };
const color = nombre => getComputedStyle(document.documentElement).getPropertyValue(nombre).trim();

// Índices de avisos por barrio, para no recorrer los 17 mil en cada consulta.
const POR_BARRIO = BARRIOS.map(() => []);
for (let i = 0; i < N; i++) if (A.barrio[i] >= 0) POR_BARRIO[A.barrio[i]].push(i);
const PRECIO_M2 = A.precio.map((p, i) => p / A.area[i]);

// ---------------------------------------------------------------------------
// Estado
// ---------------------------------------------------------------------------

const estado = {
  barrio: BARRIOS.includes("Laureles") ? "Laureles" : BARRIOS[0],
  alcobas: "todas",
  presupuesto: 3500000,
  precio: null,
  consultado: false, // el veredicto se muestra después de preguntar "¿Es justo?"
  area: null,
  rival: null,
  modoMapa: "alcanza",
  verTodos: false,
};

const idx = b => BARRIOS.indexOf(b);
const textoAlcobas = a => a === "todas" ? "" : a === "4" ? "de 4 alcobas o más" : a === "1" ? "de 1 alcoba" : `de ${a} alcobas`;

// Resumen del grupo barrio x alcobas, con respaldo en el barrio entero si hay
// pocos avisos de esas alcobas.
function grupo(barrio, alcobas) {
  const propio = DATOS.grupos[`${barrio}|${alcobas}`];
  const todo = DATOS.grupos[`${barrio}|todas`];
  if (propio) return { item: propio, conCdf: propio.cdf ? propio : todo, sinFiltro: false, cdfSinFiltro: !propio.cdf && alcobas !== "todas" };
  return { item: todo, conCdf: todo, sinFiltro: alcobas !== "todas", cdfSinFiltro: alcobas !== "todas" };
}

// CDF ajustada evaluada en x, interpolando en escala logarítmica sobre la rejilla.
function cdfEn(cdf, x) {
  if (x <= REJILLA[0]) return cdf[0] * x / REJILLA[0];
  if (x >= REJILLA[REJILLA.length - 1]) return cdf[cdf.length - 1];
  let k = 1;
  while (REJILLA[k] < x) k++;
  const t = (Math.log(x) - Math.log(REJILLA[k - 1])) / (Math.log(REJILLA[k]) - Math.log(REJILLA[k - 1]));
  return cdf[k - 1] + t * (cdf[k] - cdf[k - 1]);
}

function muestraPrecios(barrio, alcobas) {
  let ids = POR_BARRIO[idx(barrio)];
  let sinFiltro = false;
  if (alcobas !== "todas") {
    const filtrados = ids.filter(i => String(A.alcobas[i]) === alcobas);
    if (filtrados.length >= 10) ids = filtrados; else sinFiltro = true;
  }
  return { valores: ids.map(i => A.precio[i]).sort((a, b) => a - b), sinFiltro };
}

const proporcionHasta = (ordenados, x) => {
  let lo = 0, hi = ordenados.length;
  while (lo < hi) { const m = (lo + hi) >> 1; if (ordenados[m] <= x) lo = m + 1; else hi = m; }
  return lo / ordenados.length;
};

function visitas(f, p) {
  if (f <= 0) return Infinity;
  if (f >= 1) return 1;
  return Math.ceil(Math.log(1 - p) / Math.log(1 - f));
}

function claveDuelo(a, b) {
  return DATOS.duelos[`${a}|${b}`] ? { r: DATOS.duelos[`${a}|${b}`], invertido: false }
    : { r: DATOS.duelos[`${b}|${a}`], invertido: true };
}

// Terciles del coeficiente de variación, para las etiquetas de predecible o lotería.
const CVS = DATOS.variabilidad.barrios.map(v => v.cv).sort((a, b) => a - b);
const T1 = CVS[Math.floor(CVS.length / 3)], T2 = CVS[Math.floor(2 * CVS.length / 3)];
const etiquetaCv = cv => cv < T1 ? "predecible" : cv < T2 ? "intermedio" : "lotería";
const CV_DE = Object.fromEntries(DATOS.variabilidad.barrios.map(v => [v.barrio, v]));

// ---------------------------------------------------------------------------
// Globo de ayuda
// ---------------------------------------------------------------------------

const globo = $("globo");
function mostrarGlobo(html, ev) {
  globo.innerHTML = html;
  globo.style.display = "block";
  const w = globo.offsetWidth, h = globo.offsetHeight;
  let x = ev.clientX + 14, y = ev.clientY + 14;
  if (x + w > window.innerWidth - 8) x = ev.clientX - w - 14;
  if (y + h > window.innerHeight - 8) y = ev.clientY - h - 14;
  globo.style.left = x + "px";
  globo.style.top = y + "px";
}
const ocultarGlobo = () => { globo.style.display = "none"; };

// ---------------------------------------------------------------------------
// Barras en HTML
// ---------------------------------------------------------------------------

function barras(contenedor, items, opciones = {}) {
  queueMicrotask(() => crecerAlVer(contenedor));
  const max = opciones.max ?? Math.max(...items.map(it => it.sup ?? it.valor), 1e-9);
  contenedor.innerHTML = "";
  items.forEach(it => {
    const fila = document.createElement("div");
    fila.className = "barra" + (it.activa ? " activa" : "") + (it.tenue ? " tenue" : "");
    const nombre = document.createElement("span");
    nombre.className = "nombre";
    nombre.textContent = it.nombre;
    const pista = document.createElement("span");
    pista.className = "pista";
    const relleno = document.createElement("span");
    relleno.className = "relleno";
    relleno.style.width = Math.max(0, it.valor / max * 100) + "%";
    if (it.color) relleno.style.background = it.color;
    pista.appendChild(relleno);
    if (it.inf != null && it.sup != null) {
      const bigote = document.createElement("span");
      bigote.className = "bigote";
      bigote.style.left = (it.inf / max * 100) + "%";
      bigote.style.width = ((it.sup - it.inf) / max * 100) + "%";
      pista.appendChild(bigote);
    }
    const valor = document.createElement("span");
    valor.className = "valor";
    valor.textContent = it.texto;
    fila.append(nombre, pista, valor);
    if (it.globo) {
      fila.addEventListener("pointermove", ev => mostrarGlobo(it.globo, ev));
      fila.addEventListener("pointerleave", ocultarGlobo);
    }
    if (it.alClic) { fila.style.cursor = "pointer"; fila.addEventListener("click", it.alClic); }
    contenedor.appendChild(fila);
  });
}

// ---------------------------------------------------------------------------
// Gráfico de líneas en SVG, con línea de seguimiento
// ---------------------------------------------------------------------------

const SVG = "http://www.w3.org/2000/svg";
function nodo(tipo, attrs = {}, padre) {
  const el = document.createElementNS(SVG, tipo);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  if (padre) padre.appendChild(el);
  return el;
}

function ticksLineales(min, max, cuantos = 5) {
  const paso0 = (max - min) / cuantos;
  const mag = Math.pow(10, Math.floor(Math.log10(paso0)));
  const paso = [1, 2, 2.5, 5, 10].map(m => m * mag).find(p => p >= paso0) ?? 10 * mag;
  const salida = [];
  for (let v = Math.ceil(min / paso) * paso; v <= max + 1e-9; v += paso) salida.push(+v.toFixed(10));
  return salida;
}

const TICKS_PRECIO = [5e5, 1e6, 2e6, 3e6, 5e6, 1e7, 2e7, 4e7];
const TICKS_M2 = [15000, 20000, 30000, 40000, 60000, 80000, 120000, 160000, 250000];

// Valor de una serie en x: escalón (último punto <= x) o interpolación lineal.
function valorEn(serie, x) {
  const xs = serie.x;
  if (x < xs[0]) return serie.escalon ? 0 : null;
  if (x >= xs[xs.length - 1]) return serie.y[xs.length - 1];
  let lo = 0, hi = xs.length - 1;
  while (hi - lo > 1) { const m = (lo + hi) >> 1; if (xs[m] <= x) lo = m; else hi = m; }
  if (serie.escalon) return serie.y[lo];
  const t = (x - xs[lo]) / (xs[hi] - xs[lo]);
  return serie.y[lo] + t * (serie.y[hi] - serie.y[lo]);
}

function lineas(contenedor, cfg) {
  queueMicrotask(() => animarAlVer(contenedor));
  const ancho = Math.max(320, contenedor.clientWidth || 700);
  const alto = cfg.alto ?? 260;
  const m = { izq: 48, der: 16, sup: 12, inf: 30 };
  const iw = ancho - m.izq - m.der, ih = alto - m.sup - m.inf;
  const xlog = !!cfg.xlog;
  const tx = xlog ? Math.log : v => v;
  const x0 = tx(cfg.xmin), x1 = tx(cfg.xmax);
  const ymin = cfg.ymin ?? 0, ymax = cfg.ymax ?? 1;
  const X = v => m.izq + (tx(Math.min(Math.max(v, cfg.xmin), cfg.xmax)) - x0) / (x1 - x0) * iw;
  const Y = v => m.sup + ih - (v - ymin) / (ymax - ymin) * ih;

  contenedor.innerHTML = "";
  const svg = nodo("svg", { viewBox: `0 0 ${ancho} ${alto}`, role: "img", "aria-label": cfg.descripcion ?? "" }, contenedor);

  (cfg.ticksY ?? ticksLineales(ymin, ymax, 4)).forEach(v => {
    nodo("line", { x1: m.izq, x2: m.izq + iw, y1: Y(v), y2: Y(v), class: "rejilla-linea" }, svg);
    nodo("text", { x: m.izq - 6, y: Y(v) + 4, "text-anchor": "end" }, svg).textContent = (cfg.fy ?? (v => v))(v);
  });
  const ticksX = (cfg.ticksX ?? ticksLineales(cfg.xmin, cfg.xmax, 6))
    .filter(v => v >= cfg.xmin && v <= cfg.xmax && (!cfg.xEntero || Number.isInteger(v)));
  ticksX.forEach(v => {
    nodo("text", { x: X(v), y: m.sup + ih + 18, "text-anchor": "middle" }, svg).textContent = (cfg.fx ?? (v => v))(v);
  });
  nodo("line", { x1: m.izq, x2: m.izq + iw, y1: m.sup + ih, y2: m.sup + ih, class: "eje-linea" }, svg);

  (cfg.guiasY ?? []).forEach(g => {
    nodo("line", { x1: m.izq, x2: m.izq + iw, y1: Y(g.y), y2: Y(g.y), class: "guia" }, svg);
    if (g.etiqueta) nodo("text", { x: m.izq + iw - 2, y: Y(g.y) - 5, "text-anchor": "end" }, svg).textContent = g.etiqueta;
  });

  // Franjas sombreadas (rango intercuartílico, colas) detrás de todo lo demás.
  (cfg.bandas ?? []).forEach(b => {
    const xa = X(b.x0), xb = X(b.x1);
    nodo("rect", { x: Math.min(xa, xb), y: m.sup, width: Math.abs(xb - xa), height: ih,
      style: `fill:${b.color};opacity:${b.opacidad ?? 0.14}` }, svg);
    if (b.etiqueta) nodo("text", { x: (xa + xb) / 2, y: m.sup + ih - 6, "text-anchor": "middle" }, svg).textContent = b.etiqueta;
  });
  // Barras de histograma: una por bin, desde x0 hasta x1.
  (cfg.columnas ?? []).forEach(col => {
    col.x0.forEach((a, k) => {
      const b = col.x1[k];
      if (b <= cfg.xmin || a >= cfg.xmax) return;
      const xa = X(a), xb = X(b);
      nodo("rect", { x: xa + 0.5, y: Y(col.y[k]), width: Math.max(0.5, xb - xa - 1), height: Math.max(0, Y(ymin) - Y(col.y[k])),
        style: `fill:${col.color};opacity:${col.opacidad ?? 0.5}` }, svg);
    });
  });
  // Nubes de puntos.
  // Los puntos fuera de los ejes se omiten: recortados se apilarían en el borde.
  (cfg.puntos ?? []).forEach(pt => pt.x.forEach((xv, k) => {
    if (xv < cfg.xmin || xv > cfg.xmax || pt.y[k] < ymin || pt.y[k] > ymax) return;
    nodo("circle", { cx: X(xv), cy: Y(pt.y[k]), r: pt.r ?? 2, style: `fill:${pt.color};opacity:${pt.opacidad ?? 0.5}` }, svg);
  }));

  cfg.series.forEach(s => {
    let d = "";
    s.x.forEach((xv, k) => {
      const px = X(xv), py = Y(s.y[k]);
      if (k === 0) d += `M${px},${s.escalon ? Y(0) : py}` + (s.escalon ? `V${py}` : "");
      else if (s.escalon) d += `H${px}V${py}`;
      else d += `L${px},${py}`;
    });
    if (s.escalon) d += `H${m.izq + iw}`;
    if (s.relleno) {
      const area = d + `V${Y(ymin)}H${X(s.x[0])}Z`;
      nodo("path", { d: area, style: `fill:${s.color};opacity:.12;stroke:none` }, svg);
    }
    nodo("path", { d, style: `fill:none;stroke:${s.color};stroke-width:${s.grosor ?? 2};stroke-linejoin:round;stroke-linecap:round${s.guiones ? ";stroke-dasharray:5 4" : ""}` }, svg);
  });

  (cfg.guias ?? []).forEach(g => {
    nodo("line", { x1: X(g.x), x2: X(g.x), y1: m.sup, y2: m.sup + ih, class: "guia" }, svg);
    if (g.etiqueta) {
      const derecha = X(g.x) > m.izq + iw * 0.7;
      nodo("text", { x: X(g.x) + (derecha ? -5 : 5), y: m.sup + 10, "text-anchor": derecha ? "end" : "start" }, svg).textContent = g.etiqueta;
    }
  });

  (cfg.segmentos ?? []).forEach(sg => {
    nodo("line", { x1: X(sg.x), x2: X(sg.x), y1: Y(sg.y1), y2: Y(sg.y2), style: "stroke:var(--tinta);stroke-width:2" }, svg);
    if (sg.etiqueta) nodo("text", { x: X(sg.x) + 6, y: (Y(sg.y1) + Y(sg.y2)) / 2 + 4, style: "fill:var(--tinta)" }, svg).textContent = sg.etiqueta;
  });

  (cfg.marcas ?? []).forEach(mk => {
    nodo("circle", { cx: X(mk.x), cy: Y(mk.y), r: 5, style: `fill:${mk.color};stroke:var(--sup);stroke-width:2` }, svg);
    if (mk.etiqueta) nodo("text", { x: X(mk.x) + 8, y: Y(mk.y) + 14, style: "fill:var(--tinta)" }, svg).textContent = mk.etiqueta;
  });

  // Línea de seguimiento: busca la x más cercana y lista todas las series.
  const cruz = nodo("line", { y1: m.sup, y2: m.sup + ih, class: "cruz", visibility: "hidden" }, svg);
  const zona = nodo("rect", { x: m.izq, y: m.sup, width: iw, height: ih, fill: "transparent" }, svg);
  zona.addEventListener("pointermove", ev => {
    const caja = svg.getBoundingClientRect();
    const px = (ev.clientX - caja.left) * ancho / caja.width;
    const t = (px - m.izq) / iw;
    let xv = x0 + t * (x1 - x0);
    xv = xlog ? Math.exp(xv) : xv;
    if (cfg.xEntero) xv = Math.round(xv);
    cruz.setAttribute("x1", X(xv)); cruz.setAttribute("x2", X(xv));
    cruz.setAttribute("visibility", "visible");
    const formato = cfg.fyGlobo ?? cfg.fy ?? (v => v);
    const columnas = (cfg.columnas ?? []).map(col => {
      const k = col.x0.findIndex((a, j) => xv >= a && xv < col.x1[j]);
      return k < 0 ? "" : `<div class="fila"><i style="background:${col.color}"></i><b>${formato(col.y[k])}</b>&nbsp;${esc(col.nombre)}</div>`;
    }).join("");
    const filas = columnas + cfg.series.map(s => {
      const v = valorEn(s, xv);
      return v == null ? "" : `<div class="fila"><i style="background:${s.color}"></i><b>${formato(v)}</b>&nbsp;${esc(s.nombre)}</div>`;
    }).join("");
    mostrarGlobo(`<div class="titulo">${(cfg.fxGlobo ?? cfg.fx ?? (v => v))(xv)}</div>${filas}`, ev);
  });
  zona.addEventListener("pointerleave", () => { cruz.setAttribute("visibility", "hidden"); ocultarGlobo(); });
}

function leyenda(contenedor, items) {
  contenedor.innerHTML = items.map(it =>
    `<span><i class="${it.tipo ?? ""}" style="background:${it.color}"></i>${esc(it.nombre)}</span>`).join("");
}

function ecdf(valores) {
  const xs = [...valores].sort((a, b) => a - b);
  return { x: xs, y: xs.map((_, k) => (k + 1) / xs.length) };
}

// ---------------------------------------------------------------------------
// Controles
// ---------------------------------------------------------------------------

const selBarrio = $("c-barrio"), selAlcobas = $("c-alcobas"), selRival = $("c-rival");
BARRIOS.forEach(b => selBarrio.add(new Option(`${b} (${entero(POR_BARRIO[idx(b)].length)})`, b)));
$("min-barrio").textContent = M.minimo_barrio;

function entradaNumero(id, clave) {
  const el = $(id);
  el.value = estado[clave] ? entero(estado[clave]) : "";
  el.addEventListener("input", () => { estado[clave] = leerNumero(el.value); actualizar(); });
  el.addEventListener("blur", () => { if (estado[clave]) el.value = entero(estado[clave]); });
}
entradaNumero("c-presupuesto", "presupuesto");
entradaNumero("c-precio", "precio");
entradaNumero("c-area", "area");
selBarrio.addEventListener("change", () => { estado.barrio = selBarrio.value; actualizar(); });
selAlcobas.addEventListener("change", () => { estado.alcobas = selAlcobas.value; actualizar(); });
selRival.addEventListener("change", () => { estado.rival = selRival.value; pintarDuelo(); pintarTarjetas(); pintarFondo(); });

function elegirBarrio(b) {
  estado.barrio = b;
  selBarrio.value = b;
  actualizar();
  $("p-normal").scrollIntoView({ behavior: "smooth" });
}

// ---------------------------------------------------------------------------
// 1. Lo normal (cuartiles e intervalo) y 19. salarios mínimos
// ---------------------------------------------------------------------------

function pintarNormal() {
  const g = grupo(estado.barrio, estado.alcobas);
  const it = g.item;
  const alc = textoAlcobas(estado.alcobas);
  $("normal-cifras").innerHTML = `
    <div><div class="etiqueta">Lo más común (mediana)${alc ? " " + esc(alc) : ""}</div>
      <div class="cifra">${pesos(it.mediana)}</div><div class="smmlv">${salarios(it.mediana)}</div></div>
    <div><div class="etiqueta">La mitad de los avisos está entre</div>
      <div class="cifra-sm">${pesos(it.q1)} y ${pesos(it.q3)}</div>
      <div class="smmlv">${salarios(it.q1).replace(" salarios mínimos", "")} y ${salarios(it.q3)}</div></div>
    <div><div class="etiqueta">Promedio, con 95 % de confianza</div>
      <div class="cifra-sm">${it.ic_inf ? `${millones(it.ic_inf)} a ${millones(it.ic_sup)}` : millones(it.media)}</div>
      <div class="smmlv">${entero(it.n)} avisos</div></div>`;

  // Franja: rango intercuartílico sobre una escala que incluye la ciudad y el presupuesto.
  const valores = [it.q1, it.q3, M.mediana_ciudad, estado.presupuesto].filter(Boolean);
  const lo = Math.min(...valores) * 0.8, hi = Math.max(...valores) * 1.15;
  const P = v => ((v - lo) / (hi - lo) * 100).toFixed(2) + "%";
  const presu = estado.presupuesto
    ? `<div class="marca" style="left:${P(estado.presupuesto)};background:var(--serie2)"></div>` : "";
  $("normal-franja").innerHTML = `
    <div class="eje"></div>
    <div class="rango" style="left:${P(it.q1)};width:calc(${P(it.q3)} - ${P(it.q1)})"></div>
    <div class="marca ciudad" style="left:${P(M.mediana_ciudad)}"></div>
    <div class="marca" style="left:${P(it.mediana)}"></div>${presu}
    <div class="rotulo arriba" style="left:${P(it.mediana)}">${esc(estado.barrio)}: ${millones(it.mediana)}</div>
    <div class="rotulo abajo" style="left:${P(M.mediana_ciudad)}">Ciudad: ${millones(M.mediana_ciudad)}</div>`;
  const notas = ["Barra azul: la mitad central de los avisos. Línea alta: mediana del barrio. Línea gris: mediana de Medellín."];
  if (estado.presupuesto) notas.push(`Naranja: tu presupuesto (${millones(estado.presupuesto)}).`);
  if (g.sinFiltro) notas.push(`Hay pocos avisos ${alc} en este barrio; se muestran todos.`);
  $("normal-nota").textContent = notas.join(" ");
}

// ---------------------------------------------------------------------------
// 2. ¿Es justo? (distribución empírica), 6. precio raro y 22. ECDF
// ---------------------------------------------------------------------------

/* Veredicto a partir del percentil del aviso entre los avisos parecidos. Justo es
   la mitad central (entre Q1 y Q3), lo mismo que la sección "Lo normal"; por
   fuera de ella, el 10 % de cada extremo se nombra aparte. Si además se dio el
   área y el precio por m² cae en una cola de la distribución de la ciudad, eso
   manda: un precio así puede ser un error o un aviso falso. */
function veredicto(p, m2) {
  const at = DATOS.atipicos;
  if (m2 != null && m2 < at.corte_bajo) return { clase: "alerta", texto: "Sospechosamente barato" };
  if (m2 != null && m2 > at.corte_alto) return { clase: "caro", texto: "Muy caro" };
  if (p <= 0.10) return { clase: "bueno", texto: "Barato para la zona" };
  if (p <= 0.25) return { clase: "bueno", texto: "Buen precio" };
  if (p < 0.75) return { clase: "justo", texto: "Precio justo" };
  if (p < 0.90) return { clase: "medio", texto: "Algo caro" };
  return { clase: "caro", texto: "Caro" };
}

function pintarPercentil() {
  const { valores, sinFiltro } = muestraPrecios(estado.barrio, estado.alcobas);
  const alc = sinFiltro ? "" : textoAlcobas(estado.alcobas);
  const ciudad = DATOS._ecdfCiudad ??= ecdf(A.precio);
  const caja = $("justo-resultado");
  // El resultado aparece al preguntar, y desde ahí sigue al barrio, las alcobas y el precio.
  if (!estado.consultado || !estado.precio) { caja.hidden = true; return; }
  caja.hidden = false;

  const it = grupo(estado.barrio, estado.alcobas).item;
  const p = proporcionHasta(valores, estado.precio);
  const pc = proporcionHasta(ciudad.x, estado.precio);
  const m2 = estado.area ? estado.precio / estado.area : null;
  const v = veredicto(p, m2);
  const sello = $("justo-sello");
  sello.className = `sello ${v.clase}`;
  sello.textContent = v.texto;

  const consejo = v.clase === "medio" || v.clase === "caro"
    ? ` Vale la pena negociar: la mitad de los avisos parecidos pide ${pesos(it.mediana)} o menos.`
    : p <= 0.05 ? " Está muy por debajo de lo normal: confirma que el aviso sea real antes de pagar nada." : "";
  $("percentil-frase").innerHTML = `Por un arriendo ${esc(alc)} en ${esc(estado.barrio)} lo justo está entre
    <b>${pesos(it.q1)}</b> y <b>${pesos(it.q3)}</b>. Este pide <b>${pesos(estado.precio)}</b>: más que el
    <b>${pct(p)}</b> de los ${entero(valores.length)} avisos parecidos.${consejo}
    <span class="smmlv">Frente a toda la ciudad, más que el ${pct(pc)}. Son ${salarios(estado.precio)}.</span>`;

  const at = DATOS.atipicos, raro = $("percentil-raro");
  if (m2 != null) {
    let texto;
    if (m2 < at.corte_bajo) texto = `<b>Precio raro:</b> ${pesos(m2)} por m² es menos de lo que pide el 95 % de los avisos de Medellín. Puede ser una ganga, un error de digitación o un aviso falso. Revísalo antes de pagar nada.`;
    else if (m2 > at.corte_alto) texto = `<b>Precio raro:</b> ${pesos(m2)} por m² es más de lo que pide el 95 % de los avisos de Medellín.`;
    else {
      const medBarrio = DATOS.fichas[estado.barrio].mediana_m2;
      const dif = m2 / medBarrio - 1;
      const frente = Math.abs(dif) < 0.05 ? `casi igual a la mediana de ${esc(estado.barrio)}`
        : `${pct(Math.abs(dif))} ${dif > 0 ? "más" : "menos"} que la mediana de ${esc(estado.barrio)} (${pesos(medBarrio)})`;
      texto = `${pesos(m2)} por m² no es un precio raro para Medellín (lo común va de ${pesos(at.corte_bajo)} a ${pesos(at.corte_alto)}). Es ${frente}.`;
    }
    raro.innerHTML = `<div class="aviso-raro">${texto}</div>`;
  } else {
    raro.innerHTML = `<p class="nota">Si pones también el área, te decimos si el precio por metro cuadrado es sospechoso.</p>`;
  }

  // La gráfica solo se dibuja con la comparación abierta: cerrada no tiene ancho.
  if (!$("justo-detalle").open) return;
  const barrio = ecdf(valores);
  leyenda($("percentil-leyenda"), [
    { nombre: `${estado.barrio}${alc ? " " + alc : ""}`, color: "var(--serie1)" },
    { nombre: "Toda Medellín", color: "var(--serie2)" },
  ]);
  lineas($("percentil-grafico"), {
    series: [
      { nombre: estado.barrio, x: barrio.x, y: barrio.y, escalon: true, color: "var(--serie1)" },
      { nombre: "Medellín", x: ciudad.x, y: ciudad.y, escalon: true, color: "var(--serie2)" },
    ],
    xlog: true, xmin: 8e5, xmax: 3e7, ymin: 0, ymax: 1, ticksX: TICKS_PRECIO, fx: millones, fy: v => pct(v),
    fyGlobo: v => `${pct(v)} pide esto o menos`,
    guias: [{ x: estado.precio, etiqueta: "Este aviso" }],
    marcas: [{ x: estado.precio, y: p, color: "var(--serie1)" }],
    descripcion: "Distribución acumulada del precio en el barrio y en la ciudad",
  });
}
$("form-justo").addEventListener("submit", (ev) => {
  ev.preventDefault();
  estado.consultado = true;
  pintarPercentil();
  $("justo-resultado").scrollIntoView({ behavior: "smooth", block: "nearest" });
});
$("justo-detalle").addEventListener("toggle", pintarPercentil);

// ---------------------------------------------------------------------------
// 8. ¿Cuántos tienes que ver?
// ---------------------------------------------------------------------------

function fPresupuesto(barrio, alcobas) {
  const g = grupo(barrio, alcobas);
  return { f: Math.min(1, Math.max(0, cdfEn(g.conCdf.cdf, estado.presupuesto))), g };
}

function pintarVisitas() {
  const frase = $("visitas-frase");
  if (!estado.presupuesto) {
    frase.textContent = "Escribe tu presupuesto arriba.";
    $("visitas-cifras").innerHTML = ""; $("visitas-grafico").innerHTML = ""; $("visitas-nota").textContent = "";
    return;
  }
  const { f, g } = fPresupuesto(estado.barrio, estado.alcobas);
  const alc = g.cdfSinFiltro ? "" : textoAlcobas(estado.alcobas);
  if (f < 0.005) {
    frase.innerHTML = `Con <b>${pesos(estado.presupuesto)}</b> casi ningún aviso ${esc(alc)} de ${esc(estado.barrio)} te alcanza. Mira los barrios gemelos o la lista de dónde te alcanza.`;
  } else {
    frase.innerHTML = `Con <b>${pesos(estado.presupuesto)}</b>, el <b>${pct(f)}</b> de los avisos ${esc(alc)} de ${esc(estado.barrio)} te alcanza: más o menos <b>1 de cada ${entero(Math.max(1, 1 / f))}</b>.`;
  }
  const metas = [0.5, 0.8, 0.95];
  $("visitas-cifras").innerHTML = metas.map(p => {
    const n = visitas(f, p);
    return `<div><div class="etiqueta">Para tener ${pct(p)} de probabilidad</div>
      <div class="cifra-sm">${Number.isFinite(n) && n < 1000 ? `${entero(n)} ${n === 1 ? "aviso" : "avisos"}` : "Más de mil"}</div></div>`;
  }).join("");

  const nMax = Math.min(60, Math.max(15, Number.isFinite(visitas(f, 0.95)) ? visitas(f, 0.95) + 5 : 60));
  const xs = Array.from({ length: nMax }, (_, k) => k + 1);
  const ys = xs.map(n => 1 - Math.pow(1 - f, n));
  const n80 = visitas(f, 0.8);
  lineas($("visitas-grafico"), {
    series: [{ nombre: "probabilidad de encontrar uno", x: xs, y: ys, color: "var(--serie1)", relleno: true }],
    xmin: 1, xmax: nMax, ymin: 0, ymax: 1, xEntero: true,
    fx: v => `${v}`, fxGlobo: v => `Si ves ${v} ${v === 1 ? "aviso" : "avisos"}`, fy: v => pct(v),
    guiasY: [{ y: 0.8, etiqueta: "80 %" }],
    marcas: Number.isFinite(n80) && n80 <= nMax ? [{ x: n80, y: 1 - Math.pow(1 - f, n80), color: "var(--serie2)", etiqueta: `${n80} avisos` }] : [],
    alto: 220, descripcion: "Probabilidad de encontrar un aviso dentro del presupuesto según cuántos se vean",
  });
  const notas = ["Eje horizontal: cuántos avisos del barrio revisas. Supone que cada uno es un aviso al azar del barrio."];
  if (g.cdfSinFiltro) notas.push(`Hay menos de ${M.minimo_grupo} avisos ${textoAlcobas(estado.alcobas)} aquí; el cálculo usa todo el barrio.`);
  $("visitas-nota").textContent = notas.join(" ");
}

// ---------------------------------------------------------------------------
// 9. ¿Dónde te alcanza?
// ---------------------------------------------------------------------------

function pintarAlcanza() {
  const cont = $("alcanza-barras");
  if (!estado.presupuesto) { cont.innerHTML = `<p class="nota">Escribe tu presupuesto arriba.</p>`; return; }
  const filas = BARRIOS.map(b => { const { f, g } = fPresupuesto(b, estado.alcobas); return { b, f, sin: g.cdfSinFiltro }; })
    .sort((a, b) => b.f - a.f);
  let visibles = estado.verTodos ? filas : filas.slice(0, 12);
  if (!visibles.some(r => r.b === estado.barrio)) visibles = [...visibles, filas.find(r => r.b === estado.barrio)];
  barras(cont, visibles.map(r => ({
    nombre: r.b + (r.sin && estado.alcobas !== "todas" ? " *" : ""), valor: r.f, texto: pct(r.f),
    activa: r.b === estado.barrio,
    globo: `<b>${pct(r.f)}</b> de los avisos te alcanza<div class="titulo">${esc(r.b)} · puesto ${filas.indexOf(r) + 1} de ${filas.length}</div>`,
    alClic: () => elegirBarrio(r.b),
  })), { max: 1 });
  $("alcanza-mas").textContent = estado.verTodos ? "Ver solo los primeros" : `Ver los ${BARRIOS.length} barrios`;
  if (estado.alcobas !== "todas" && filas.some(r => r.sin)) {
    const nota = document.createElement("p");
    nota.className = "nota";
    nota.textContent = `* Pocos avisos ${textoAlcobas(estado.alcobas)}: se usa todo el barrio.`;
    cont.appendChild(nota);
  }
}
$("alcanza-mas").addEventListener("click", () => { estado.verTodos = !estado.verTodos; pintarAlcanza(); });

// ---------------------------------------------------------------------------
// Mapa: 9. me alcanza, 12. caro para su zona, 6. precio raro
// ---------------------------------------------------------------------------

// Fondo satelital y capa de puntos comunes del sitio (mapa_satelite.js), sobre
// MapLibre: los puntos se quedan del mismo tamaño en todo el zoom y sin tirones.
// Encuadre sobre el 1 % al 99 % de los avisos, para que unos pocos mal ubicados no alejen la vista.
const cuantil = (arr, q) => { const s = [...arr].sort((a, b) => a - b); return s[Math.floor(q * (s.length - 1))]; };
const LIMITES = [[cuantil(A.lng, 0.01), cuantil(A.lat, 0.01)], [cuantil(A.lng, 0.99), cuantil(A.lat, 0.99)]];
const mapa = MapaSatelite.crear("mapa", { bounds: LIMITES, fitBoundsOptions: { padding: 20 } });
mapa.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-left");
new ResizeObserver(() => mapa.resize()).observe($("mapa"));

const { lat: LAT_SEP, lng: LNG_SEP, pila } = MapaSatelite.separar(A.lat, A.lng);

function popup(i) {
  const z = A.z[i];
  const zona = z == null ? `sin vecinos suficientes a ${M.radio_vecinos_m} m`
    : z <= -M.z_critico ? `ganga para su zona (z = ${dec(z)})` : z >= M.z_critico ? `caro para su zona (z = ${dec(z)})` : `normal para su zona (z = ${dec(z)})`;
  return `<div class="popup"><h3>${pesos(A.precio[i])}</h3>
    <div class="meta">${salarios(A.precio[i])} · ${esc(A.nombre_barrio[i])}</div>
    <table>
      <tr><td>Área</td><td>${dec(A.area[i], 0)} m²</td></tr>
      <tr><td>Precio por m²</td><td>${pesos(PRECIO_M2[i])}</td></tr>
      <tr><td>Alcobas</td><td>${A.alcobas[i] >= 4 ? "4 o más" : A.alcobas[i]}</td></tr>
      <tr><td>Estrato</td><td>${A.estrato[i] ?? "sin dato"}</td></tr>
      <tr><td>Frente a su zona</td><td>${zona}</td></tr>
      ${A.cola[i] ? `<tr><td>Precio por m²</td><td>raro para la ciudad (${A.cola[i] < 0 ? "muy bajo" : "muy alto"})</td></tr>` : ""}
      ${pila[i] > 1 ? `<tr><td>Ubicación</td><td>aproximada: ${pila[i]} avisos comparten este punto</td></tr>` : ""}
    </table>
    <p style="margin:6px 0 0"><a href="${esc(A.url[i])}" target="_blank" rel="noopener">Ver el aviso</a></p></div>`;
}

let mapaListo = false;
let opacidadMapa = 0.8;
$("opacidad").addEventListener("input", (e) => {
  opacidadMapa = e.target.value / 100;
  $("opacidad-valor").textContent = `${e.target.value} %`;
  if (mapaListo) MapaSatelite.opacidad(mapa, "avisos", opacidadMapa);
});
mapa.on("load", () => {
  MapaSatelite.capaPuntos(mapa, "avisos", { radio: 2.5 });
  MapaSatelite.alPasar(mapa, "avisos", {});
  mapa.on("click", "avisos", (e) => {
    const i = e.features[0].id;
    new maplibregl.Popup({ maxWidth: "300px" }).setLngLat([LNG_SEP[i], LAT_SEP[i]]).setHTML(popup(i)).addTo(mapa);
  });
  mapaListo = true;
  MapaSatelite.opacidad(mapa, "avisos", opacidadMapa);
  pintarMapa();
});

const MODOS = {
  alcanza: {
    ir: "e-alcanza",
    nota: "Azul: avisos que caben en tu presupuesto. Si elegiste alcobas, los demás quedan en gris claro.",
    clases: () => {
      const tope = estado.presupuesto ?? Infinity;
      return [
        { nombre: "Te alcanza", color: color("--serie1"), resalta: true, prueba: i => estado.alcobas === "todas" || String(A.alcobas[i]) === estado.alcobas ? (A.precio[i] <= tope) : null },
        { nombre: "Se pasa de tu presupuesto", color: color("--neutro"), prueba: i => estado.alcobas === "todas" || String(A.alcobas[i]) === estado.alcobas ? (A.precio[i] > tope) : null },
        { nombre: "Otras alcobas", color: color("--neutro"), tenue: true, prueba: () => true },
      ];
    },
  },
  zona: {
    ir: "e-zona",
    nota: `Cada aviso se compara con los que están a menos de ${M.radio_vecinos_m} m. Rojo: caro para su zona; azul: ganga para su zona.`,
    clases: () => [
      { nombre: "Caro para su zona", color: color("--polo-alto"), resalta: true, prueba: i => A.z[i] != null && A.z[i] >= M.z_critico },
      { nombre: "Ganga para su zona", color: color("--polo-bajo"), resalta: true, prueba: i => A.z[i] != null && A.z[i] <= -M.z_critico },
      { nombre: "Normal para su zona", color: color("--neutro"), prueba: i => A.z[i] != null },
      { nombre: "Sin vecinos suficientes", color: color("--neutro"), tenue: true, prueba: () => true },
    ],
  },
  raro: {
    ir: "e-atipicos",
    nota: "Precio por m² comparado con toda la ciudad. Los puntos de color están en el 5 % más bajo o el 5 % más alto de lo esperado.",
    clases: () => [
      { nombre: "Muy alto para Medellín", color: color("--polo-alto"), resalta: true, prueba: i => A.cola[i] === 1 },
      { nombre: "Muy bajo para Medellín", color: color("--polo-bajo"), resalta: true, prueba: i => A.cola[i] === -1 },
      { nombre: "Dentro de lo común", color: color("--neutro"), prueba: () => true },
    ],
  },
};

function pintarMapa() {
  const modo = MODOS[estado.modoMapa];
  const clases = modo.clases();
  const cuenta = new Array(clases.length).fill(0);
  const clase = new Int8Array(N);
  for (let i = 0; i < N; i++) {
    const k = clases.findIndex(c => c.prueba(i) === true);
    cuenta[k]++;
    clase[i] = k;
  }
  // Los puntos de color van con borde blanco fino y encima; los demás, pequeños
  // y claros, para que el color sea lo que se lea sobre la imagen satelital.
  if (mapaListo) {
    mapa.getSource("avisos").setData(MapaSatelite.rasgos(LAT_SEP, LNG_SEP,
      i => clases[clase[i]].color, i => !clases[clase[i]].resalta));
  }
  $("mapa-leyenda").innerHTML = clases.map((c, k) => cuenta[k] ? `<div class="fila"><i style="background:${c.color};opacity:${c.tenue ? .5 : 1}"></i>${esc(c.nombre)}<span class="cuenta">${entero(cuenta[k])}</span></div>` : "").join("");
  $("mapa-nota").textContent = modo.nota + " Toca un punto para ver el aviso.";
  $("mapa-ir").dataset.ir = modo.ir;
  document.querySelectorAll("#mapa-modos button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.modo === estado.modoMapa)));
}
document.querySelectorAll("#mapa-modos button").forEach(b => b.addEventListener("click", () => { estado.modoMapa = b.dataset.modo; pintarMapa(); }));

// ---------------------------------------------------------------------------
// 10. Barrios gemelos
// ---------------------------------------------------------------------------

function pintarGemelos() {
  const gem = DATOS.gemelos.gemelos[estado.barrio];
  const base = DATOS.fichas[estado.barrio];
  const colores = ["var(--serie2)", "var(--serie3)", null];
  $("gemelos-tarjetas").innerHTML = gem.map((g, k) => {
    const f = DATOS.fichas[g.barrio];
    const dif = f.mediana_m2 / base.mediana_m2 - 1;
    const comp = Math.abs(dif) < 0.02 ? "casi lo mismo por m²" : `${pct(Math.abs(dif))} ${dif < 0 ? "más barato" : "más caro"} por m²`;
    return `<button class="mini carta" type="button" data-barrio="${esc(g.barrio)}">
      <div class="tit">${colores[k] ? `<i style="background:${colores[k]}"></i>` : ""}${esc(g.barrio)}</div>
      <div class="cifra-sm" style="margin-top:6px">${pesos(f.mediana_precio)}</div>
      <div class="smmlv">${salarios(f.mediana_precio)}</div>
      <div class="etiqueta" style="margin-top:6px">${comp} · parecido ${pct(1 - g.hellinger)}</div></button>`;
  }).join("");
  document.querySelectorAll("#gemelos-tarjetas [data-barrio]").forEach(b => b.addEventListener("click", () => elegirBarrio(b.dataset.barrio)));

  const xs = DATOS.gemelos.centros_m2;
  const series = [{ nombre: estado.barrio, x: xs, y: DATOS.gemelos.histogramas[estado.barrio], color: "var(--serie1)", relleno: true }]
    .concat(gem.slice(0, 2).map((g, k) => ({ nombre: g.barrio, x: xs, y: DATOS.gemelos.histogramas[g.barrio], color: colores[k] })));
  leyenda($("gemelos-leyenda"), series.map(s => ({ nombre: s.nombre, color: s.color })));
  const ymax = Math.max(...series.flatMap(s => s.y)) * 1.1;
  lineas($("gemelos-grafico"), {
    series, xlog: true, xmin: xs[0], xmax: xs[xs.length - 1], ymin: 0, ymax,
    ticksX: TICKS_M2, fx: miles, fxGlobo: v => `${miles(v)} por m²`, fy: pctEje, fyGlobo: v => pct(v, 1) + " de sus avisos",
    descripcion: "Distribución del precio por metro cuadrado del barrio y sus gemelos",
  });
}

// ---------------------------------------------------------------------------
// 3. Duelo de barrios
// ---------------------------------------------------------------------------

function pintarDuelo() {
  if (!estado.rival || estado.rival === estado.barrio || !BARRIOS.includes(estado.rival)) {
    estado.rival = estado.barrio === "El Poblado" ? (BARRIOS.includes("Laureles") ? "Laureles" : BARRIOS[1]) : (BARRIOS.includes("El Poblado") ? "El Poblado" : BARRIOS[0]);
  }
  selRival.innerHTML = "";
  BARRIOS.filter(b => b !== estado.barrio).forEach(b => selRival.add(new Option(b, b)));
  selRival.value = estado.rival;

  const a = estado.barrio, b = estado.rival;
  const { r } = claveDuelo(a, b);
  const ma = DATOS.fichas[a].mediana_m2, mb = DATOS.fichas[b].mediana_m2;
  const caro = ma >= mb ? a : b, barato = ma >= mb ? b : a;
  const dif = Math.max(ma, mb) / Math.min(ma, mb) - 1;
  const sigT = r.p_t < 0.05, sigKs = r.p_ks < 0.05;
  let texto;
  if (sigT && sigKs) texto = `<b>Sí hay diferencia real.</b> ${esc(caro)} pide en mediana ${pct(dif)} más por m² que ${esc(barato)}, y no es casualidad.`;
  else if (!sigT && !sigKs) texto = `<b>No se puede decir que uno sea más caro.</b> La diferencia de ${pct(dif)} por m² cabe dentro de lo que el azar produce.`;
  else texto = `<b>Resultado mixto.</b> ${sigKs ? "Los precios se reparten distinto, pero los promedios no se distinguen" : "Los promedios difieren, pero la forma completa de los precios es parecida"}. Diferencia de medianas: ${pct(dif)} por m².`;
  $("duelo-veredicto").innerHTML = texto + ` <span class="chip">${pesos(ma)} contra ${pesos(mb)} por m²</span>`;

  const ea = ecdf(POR_BARRIO[idx(a)].map(i => PRECIO_M2[i]));
  const eb = ecdf(POR_BARRIO[idx(b)].map(i => PRECIO_M2[i]));
  // Punto de máxima separación entre las acumuladas: es la D de Kolmogorov-Smirnov.
  let dMax = 0, xD = ea.x[0];
  for (const x of [...ea.x, ...eb.x]) {
    const d = Math.abs(valorEn({ ...ea, escalon: true }, x) - valorEn({ ...eb, escalon: true }, x));
    if (d > dMax) { dMax = d; xD = x; }
  }
  leyenda($("duelo-leyenda"), [{ nombre: a, color: "var(--serie1)" }, { nombre: b, color: "var(--serie2)" }]);
  lineas($("duelo-grafico"), {
    series: [
      { nombre: a, x: ea.x, y: ea.y, escalon: true, color: "var(--serie1)" },
      { nombre: b, x: eb.x, y: eb.y, escalon: true, color: "var(--serie2)" },
    ],
    xlog: true, xmin: 15000, xmax: 160000, ymin: 0, ymax: 1, ticksX: TICKS_M2, fx: miles,
    fxGlobo: v => `${miles(v)} por m²`, fy: v => pct(v), fyGlobo: v => `${pct(v)} pide esto o menos`,
    segmentos: [{ x: xD, y1: valorEn({ ...ea, escalon: true }, xD), y2: valorEn({ ...eb, escalon: true }, xD), etiqueta: `mayor separación: ${pct(dMax)}` }],
    descripcion: "Distribuciones acumuladas del precio por metro cuadrado de los dos barrios",
  });
}

// ---------------------------------------------------------------------------
// 7, 14 y 13. ¿Qué hace subir el precio?
// ---------------------------------------------------------------------------

function pintarSube() {
  barras($("sube-correlacion"), DATOS.correlaciones.map(c => ({
    nombre: c.nombre, valor: Math.abs(c.r), texto: dec(c.r),
    globo: `<b>r = ${dec(c.r, 3)}</b><div class="titulo">${esc(c.nombre)} contra el precio · ${entero(c.n)} avisos</div>`,
  })), { max: 1 });
  barras($("sube-anova"), DATOS.anovas.map(a => ({
    nombre: a.nombre, valor: a.eta2, texto: pct(a.eta2),
    globo: `<b>${pct(a.eta2, 1)}</b> de las diferencias<div class="titulo">${esc(a.nombre)} · ${a.k} grupos</div>`,
  })), { max: 1 });
  barras($("sube-gemelos"), DATOS.caracteristicas.map(c => ({
    nombre: c.nombre, valor: Math.max(0, c.efecto), texto: pctSigno(c.efecto),
    inf: Math.max(0, c.efecto_inf), sup: Math.max(0, c.efecto_sup),
    globo: `<b>${pctSigno(c.efecto, 1)}</b> en el arriendo<div class="titulo">${esc(c.nombre)} · ${entero(c.n)} parejas · entre ${pctSigno(c.efecto_inf, 1)} y ${pctSigno(c.efecto_sup, 1)}</div>`,
  })));
}

// ---------------------------------------------------------------------------
// 15. ¿Predecible o lotería?
// ---------------------------------------------------------------------------

function pintarLoteria() {
  const lista = DATOS.variabilidad.barrios;
  const v = CV_DE[estado.barrio];
  const puesto = lista.findIndex(x => x.barrio === estado.barrio) + 1;
  const etiqueta = etiquetaCv(v.cv);
  const consejo = etiqueta === "lotería" ? "Hay mucha diferencia entre avisos parecidos: compara bastante y negocia."
    : etiqueta === "predecible" ? "Casi todos piden parecido: un aviso muy por encima de la mediana difícilmente se justifica." : "";
  $("loteria-frase").innerHTML = `En ${esc(estado.barrio)} el precio por m² se aleja en promedio un <b>${pct(v.cv)}</b> de su media:
    precio <b>${etiqueta}</b>. Puesto ${puesto} de ${lista.length}, donde 1 es el más predecible. ${consejo}`;
  const fila = x => ({
    nombre: x.barrio, valor: x.cv, texto: pct(x.cv), activa: x.barrio === estado.barrio,
    globo: `<b>${pct(x.cv, 1)}</b> de variación<div class="titulo">${esc(x.barrio)} · ${entero(x.n)} avisos</div>`,
    alClic: () => elegirBarrio(x.barrio),
  });
  const max = lista[lista.length - 1].cv;
  barras($("loteria-bajos"), lista.slice(0, 6).map(fila), { max });
  barras($("loteria-altos"), lista.slice(-6).reverse().map(fila), { max });

  const varianza = Object.fromEntries(DATOS.variabilidad.estratos.map(e => [e.estrato, e.varianza]));
  const distintos = DATOS.variabilidad.comparaciones.filter(c => c.p < 0.05).map(c => {
    const mayor = varianza[c.a] > varianza[c.b] ? c.a : c.b;
    return `entre estrato ${c.a} y ${c.b} la dispersión cambia, y es mayor en estrato ${mayor}`;
  });
  $("loteria-estratos").textContent = distintos.length
    ? `Por estrato: ${distintos.join("; ")}. En los demás pasos de estrato la dispersión es parecida.`
    : "Por estrato, la dispersión del precio por m² es parecida en todos.";
}

// ---------------------------------------------------------------------------
// 18. Estrato declarado contra censo
// ---------------------------------------------------------------------------

function pintarEstrato() {
  const ed = DATOS.estrato_declarado;
  $("estrato-frase").innerHTML = `El <b>${pct(ed.pct_mayor)}</b> de los avisos declara un estrato más alto que el que el censo registra para su manzana, y el ${pct(ed.pct_menor)} uno más bajo.`;
  leyenda($("estrato-leyenda"), [
    { nombre: "Declara el estrato del censo", color: "var(--serie1)", tipo: "caja" },
    { nombre: "Declara uno más alto", color: "var(--serie2)", tipo: "caja" },
  ]);
  const max = Math.max(...ed.comparaciones.map(c => c.mediana_mayor));
  const items = [];
  ed.comparaciones.forEach(c => {
    items.push({ nombre: `Manzana estrato ${c.estrato_censo}: igual`, valor: c.mediana_igual, texto: miles(c.mediana_igual), color: "var(--serie1)",
      globo: `<b>${pesos(c.mediana_igual)}</b> por m² (mediana)<div class="titulo">${entero(c.n_igual)} avisos que declaran estrato ${c.estrato_censo}</div>` });
    items.push({ nombre: `más alto (${pctSigno(c.diferencia)})`, valor: c.mediana_mayor, texto: miles(c.mediana_mayor), color: "var(--serie2)",
      globo: `<b>${pesos(c.mediana_mayor)}</b> por m² (mediana)<div class="titulo">${entero(c.n_mayor)} avisos que declaran más de ${c.estrato_censo} · ${pctSigno(c.diferencia)}</div>` });
  });
  barras($("estrato-barras"), items, { max });
}

// ---------------------------------------------------------------------------
// 21. Cartas de barrio
// ---------------------------------------------------------------------------

function pintarCartas() {
  const filtro = $("cartas-buscar").value.trim().toLowerCase();
  const orden = $("cartas-orden").value;
  const criterio = {
    barato: b => DATOS.fichas[b].mediana_precio, caro: b => -DATOS.fichas[b].mediana_precio,
    avisos: b => -POR_BARRIO[idx(b)].length, predecible: b => CV_DE[b].cv, gangas: b => -(DATOS.fichas[b].pct_ganga ?? 0),
  }[orden];
  const lista = BARRIOS.filter(b => b.toLowerCase().includes(filtro)).sort((a, b) => criterio(a) - criterio(b));
  $("cartas").innerHTML = lista.map(b => {
    const f = DATOS.fichas[b];
    const gem = DATOS.gemelos.gemelos[b][0].barrio;
    return `<button class="carta${b === estado.barrio ? " activa" : ""}" type="button" data-barrio="${esc(b)}">
      <h3>${esc(b)}</h3><div class="est">Estrato ${f.estrato_moda} · ${entero(POR_BARRIO[idx(b)].length)} avisos</div>
      <div class="precio">${millones(f.mediana_precio)}</div><div class="smmlv">${salarios(f.mediana_precio)}</div>
      <dl>
        <dt>Por m²</dt><dd>${pesos(f.mediana_m2)}</dd>
        <dt>Precio</dt><dd>${etiquetaCv(CV_DE[b].cv)}</dd>
        <dt>Gangas en su zona</dt><dd>${f.pct_ganga == null ? "sin dato" : pct(f.pct_ganga, 1)}</dd>
        <dt>Caros en su zona</dt><dd>${f.pct_caro == null ? "sin dato" : pct(f.pct_caro, 1)}</dd>
        <dt>Amoblados</dt><dd>${pct(f.pct_amoblado)}</dd>
        <dt>Gemelo</dt><dd>${esc(gem)}</dd>
        ${f.asimetria > 0.6 ? `<dt>Ojo</dt><dd>el promedio engaña</dd>` : ""}
      </dl></button>`;
  }).join("") || `<p class="nota">Ningún barrio coincide.</p>`;
  document.querySelectorAll("#cartas [data-barrio]").forEach(el => el.addEventListener("click", () => elegirBarrio(el.dataset.barrio)));
}
$("cartas-buscar").addEventListener("input", pintarCartas);
$("cartas-orden").addEventListener("change", pintarCartas);

// ---------------------------------------------------------------------------
// 5. Pareto y 22. crestas por estrato
// ---------------------------------------------------------------------------

function pintarOferta() {
  const p = DATOS.pareto;
  $("pareto-titulo").textContent = `${p.barrios_80} de ${p.total_barrios} barrios (${pct(p.fraccion_barrios_80)}) concentran el 80 % de los avisos`;
  const xs = p.acumulado.map((_, k) => k + 1);
  lineas($("pareto-grafico"), {
    series: [{ nombre: "de los avisos", x: xs, y: p.acumulado, color: "var(--serie1)", relleno: true }],
    xmin: 1, xmax: xs.length, ymin: 0, ymax: 1, xEntero: true, fx: v => `${v}`,
    fxGlobo: v => `Los ${v} barrios con más avisos${v <= 3 ? ": " + p.barrios.slice(0, v).join(", ") : ""}`,
    fy: v => pct(v), guiasY: [{ y: 0.8, etiqueta: "80 %" }], guias: [{ x: p.barrios_80, etiqueta: `${p.barrios_80} barrios` }],
    alto: 240, descripcion: "Porcentaje acumulado de avisos por barrio, de mayor a menor",
  });
  pintarCrestas();
}

function pintarCrestas() {
  const cont = $("crestas-grafico");
  const c = DATOS.crestas;
  const ancho = Math.max(320, cont.clientWidth || 600);
  const filas = c.estratos.length;
  const altoFila = 30, solape = 2.2;
  const m = { izq: 70, der: 14, sup: altoFila * (solape - 1) + 6, inf: 28 };
  const alto = m.sup + filas * altoFila + m.inf;
  const iw = ancho - m.izq - m.der;
  const xs = c.centros_m2, lx0 = Math.log(xs[0]), lx1 = Math.log(xs[xs.length - 1]);
  const X = v => m.izq + (Math.log(v) - lx0) / (lx1 - lx0) * iw;
  const maxF = Math.max(...c.estratos.flatMap(e => e.frecuencia));
  cont.innerHTML = "";
  const svg = nodo("svg", { viewBox: `0 0 ${ancho} ${alto}`, role: "img", "aria-label": "Polígonos de frecuencia del precio por metro cuadrado por estrato" }, cont);
  TICKS_M2.filter(v => v >= xs[0] && v <= xs[xs.length - 1]).forEach(v => {
    nodo("line", { x1: X(v), x2: X(v), y1: 0, y2: alto - m.inf, class: "rejilla-linea" }, svg);
    nodo("text", { x: X(v), y: alto - 8, "text-anchor": "middle" }, svg).textContent = miles(v);
  });
  c.estratos.forEach((e, k) => {
    const base = m.sup + (k + 1) * altoFila;
    const Y = f => base - f / maxF * altoFila * solape;
    let d = `M${X(xs[0])},${base}`;
    e.frecuencia.forEach((f, j) => { d += `L${X(xs[j])},${Y(f)}`; });
    d += `L${X(xs[xs.length - 1])},${base}Z`;
    const g = nodo("g", {}, svg);
    nodo("path", { d, style: "fill:var(--serie1);fill-opacity:.18;stroke:var(--serie1);stroke-width:1.6;stroke-linejoin:round" }, g);
    nodo("line", { x1: X(e.mediana_m2), x2: X(e.mediana_m2), y1: base, y2: base - altoFila * 0.9, style: "stroke:var(--tinta);stroke-width:1.5" }, g);
    nodo("text", { x: m.izq - 8, y: base - 4, "text-anchor": "end", style: "fill:var(--tinta)" }, g).textContent = `Estrato ${e.estrato}`;
    const zona = nodo("rect", { x: 0, y: base - altoFila, width: ancho, height: altoFila, fill: "transparent" }, g);
    zona.addEventListener("pointermove", ev => mostrarGlobo(`<b>${pesos(e.mediana_m2)}</b> por m² (mediana)<div class="titulo">Estrato ${e.estrato} · ${entero(e.n)} avisos</div>`, ev));
    zona.addEventListener("pointerleave", ocultarGlobo);
  });
}

// ---------------------------------------------------------------------------
// Ventana de estadística
// ---------------------------------------------------------------------------

const CURSO = "Curso: ";

function tarjetasEstadistica() {
  const g = grupo(estado.barrio, estado.alcobas), it = g.item;
  const at = DATOS.atipicos;
  const fam = g.conCdf;
  const fB = estado.presupuesto ? cdfEn(fam.cdf, estado.presupuesto) : null;
  const gem = DATOS.gemelos.gemelos[estado.barrio];
  // El estadístico t se guardó con el primer barrio de la clave arriba; aquí se
  // orienta para que el positivo signifique que el barrio elegido es el más caro.
  const { r: duelo, invertido } = claveDuelo(estado.barrio, estado.rival);
  const tDuelo = duelo ? (invertido ? -duelo.t : duelo.t) : null;
  const nombreFamilia = { fisk: "log-logística (fisk)", lognorm: "lognormal", gamma: "gamma" };
  const filasTabla = (cab, filas) => `<table><tr>${cab.map(c => `<th>${c}</th>`).join("")}</tr>${filas.map(f => `<tr>${f.map(v => `<td>${v}</td>`).join("")}</tr>`).join("")}</table>`;
  const muestra = muestraPrecios(estado.barrio, estado.alcobas);
  const pAviso = estado.precio ? proporcionHasta(muestra.valores, estado.precio) : null;
  const alcanza = estado.presupuesto ? BARRIOS.map(b => [b, cdfEn(grupo(b, estado.alcobas).conCdf.cdf, estado.presupuesto)]).sort((a, b) => b[1] - a[1]) : [];
  const norm = DATOS.normalidad;
  const ed = DATOS.estrato_declarado;

  return [
    {
      id: "e-normal", titulo: "Lo normal: cuartiles e intervalo de confianza", para: "Lo normal en el barrio", volver: "p-normal",
      formula: `Q<sub>1</sub> = F̂<sup>−1</sup>(0,25) &nbsp; Me = F̂<sup>−1</sup>(0,50) &nbsp; Q<sub>3</sub> = F̂<sup>−1</sup>(0,75)`,
      formula2: `x̄ ± t<sub>α/2, n−1</sub> · ${fr("s", "√n")}`,
      texto: "Los cuartiles parten los avisos ordenados en cuatro partes iguales; entre Q₁ y Q₃ está la mitad central. El intervalo dice dónde está el promedio real con 95 % de confianza, usando la t con n − 1 grados de libertad.",
      resultado: `${esc(estado.barrio)} ${esc(textoAlcobas(estado.alcobas))}: n = ${entero(it.n)}, Q₁ = ${pesos(it.q1)}, Me = ${pesos(it.mediana)}, Q₃ = ${pesos(it.q3)}, x̄ = ${pesos(it.media)}, s = ${pesos(it.s)}` +
        (it.t ? `, t<sub>0,025; ${it.gl}</sub> = ${dec(it.t, 3)}, intervalo = [${pesos(it.ic_inf)}; ${pesos(it.ic_sup)}].` : "."),
      curso: "diapositivas 39 a 45 (tendencia central y dispersión), 50 (cuantiles), 74 (intervalos de confianza) y 94 (grados de libertad).",
    },
    {
      id: "e-salario", titulo: "El precio en salarios mínimos", para: "Todas las cifras de precio", volver: "p-normal",
      formula: `salarios = ${fr("precio", "SMMLV")} &nbsp;&nbsp; SMMLV 2026 = ${pesos(SM)}`,
      texto: "Divide el arriendo por el salario mínimo vigente (Decreto 1469 de 2025). Es un cambio de unidad: no cambia la forma de la distribución ni el orden de los avisos. Va siempre debajo del precio, que es la cifra principal.",
      resultado: `Mediana de ${esc(estado.barrio)}: ${pesos(it.mediana)} = ${salarios(it.mediana)}. Mediana de Medellín: ${salarios(M.mediana_ciudad)}.`,
      curso: "transformación lineal de una variable aleatoria (diapositiva 31).",
    },
    {
      id: "e-percentil", titulo: "¿Es justo?: distribución empírica", para: "¿Viste un arriendo? Te digo si es justo", volver: "p-percentil",
      formula: `F̂<sub>n</sub>(x) = ${fr("#{ x<sub>i</sub> ≤ x }", "n")}`,
      formula2: `justo si Q<sub>1</sub> ≤ x ≤ Q<sub>3</sub> &nbsp;·&nbsp; algo caro si F̂<sub>n</sub>(x) ≥ 0,75 &nbsp;·&nbsp; caro si F̂<sub>n</sub>(x) ≥ 0,90`,
      texto: "F̂ es la fracción de avisos parecidos (mismo barrio y alcobas) que pide lo mismo o menos. Se construye solo con los datos, sin suponer ninguna distribución teórica. Justo es la mitad central, entre los cuartiles; buen precio y barato son los mismos cortes por abajo (0,25 y 0,10). Con el área, si el precio por m² cae en una cola de la CDF de la ciudad, el veredicto pasa a muy caro o sospechosamente barato.",
      resultado: pAviso == null ? "Escribe en la otra ventana cuánto piden por un aviso y pulsa «¿Es justo?»." :
        `Precio ${pesos(estado.precio)} frente a ${entero(muestra.valores.length)} avisos de ${esc(estado.barrio)}: F̂ = ${dec(pAviso, 3)}, es decir, más que el ${pct(pAviso)}.`,
      curso: "diapositivas 35 a 37 (no paramétrica), 52 (distribución empírica) y 57 (qué fracción de mis datos es menor o igual a x).",
    },
    {
      id: "e-atipicos", titulo: "Precio raro: colas de la CDF contra el IQR", para: "Precio raro (mapa y comparador)", volver: "p-mapa",
      formula: `F(x) &lt; 0,05 &nbsp; o &nbsp; 1 − F(x) &lt; 0,05`,
      formula2: `x &lt; Q<sub>1</sub> − 1,5·IQR &nbsp; o &nbsp; x &gt; Q<sub>3</sub> + 1,5·IQR`,
      texto: `F es la acumulada de la distribución ${nombreFamilia[at.familia] ?? at.familia} ajustada al precio por m² de toda la ciudad (la de menor distancia de Bhattacharyya). Con un precio con cola a la derecha, el corte inferior del IQR cae casi en cero y no ve los precios sospechosamente bajos; las colas de la CDF sí.`,
      resultado: filasTabla(["Criterio", "Corte bajo", "Corte alto", "Bajos", "Altos"], [
        ["CDF", pesos(at.corte_bajo), pesos(at.corte_alto), entero(at.n_bajo), entero(at.n_alto)],
        ["IQR", pesos(at.iqr_bajo), pesos(at.iqr_alto), entero(at.n_iqr_bajo), entero(at.n_iqr_alto)],
      ]),
      curso: "diapositivas 56 a 58 (CDF) y 105 (atípicos por rango intercuartílico).",
    },
    {
      id: "e-visitas", titulo: "Cuántos ver: probabilidad con la CDF", para: "¿Cuántos apartamentos tienes que ver?", volver: "p-visitas",
      formula: `P(n) = 1 − (1 − F(b))<sup>n</sup> &nbsp;&nbsp;&nbsp; n = ⌈ ${fr("ln(1 − P)", "ln(1 − F(b))")} ⌉`,
      formula2: `D<sub>B</sub> = −ln Σ<sub>i</sub> √(p<sub>i</sub> q<sub>i</sub>)`,
      texto: "F(b) es la probabilidad de que un aviso al azar cueste b o menos. Si cada aviso que ves es independiente, la probabilidad de que ninguno te alcance es (1 − F)ⁿ. F sale de la familia (lognormal, log-logística o gamma) más cercana a los datos según la distancia de Bhattacharyya entre el histograma (p) y la familia (q).",
      resultado: fB == null ? "Escribe un presupuesto en la otra ventana." :
        `${esc(estado.barrio)}: familia ${nombreFamilia[fam.familia] ?? fam.familia}, D<sub>B</sub> = ${dec(fam.bhattacharyya, 4)}. F(${pesos(estado.presupuesto)}) = ${dec(fB, 3)}. Visitas para 50 %, 80 % y 95 %: ${[0.5, 0.8, 0.95].map(p => Number.isFinite(visitas(fB, p)) ? visitas(fB, p) : "∞").join(", ")}.`,
      curso: "diapositivas 31 (variable aleatoria), 56 a 58 (función de probabilidad acumulada) y 62 (distancia de Bhattacharyya).",
    },
    {
      id: "e-alcanza", titulo: "Dónde te alcanza: la CDF de cada barrio", para: "¿Dónde te alcanza? y el mapa", volver: "p-alcanza",
      formula: `F<sub>barrio</sub>(presupuesto) = P(precio ≤ presupuesto | barrio)`,
      texto: `La misma acumulada ajustada, evaluada en tu presupuesto para cada barrio con al menos ${M.minimo_barrio} avisos. Si un barrio tiene menos de ${M.minimo_grupo} avisos con las alcobas elegidas, se usa la de todo el barrio.`,
      resultado: alcanza.length ? `Donde más te alcanza: ${alcanza.slice(0, 3).map(([b, f]) => `${esc(b)} (${pct(f)})`).join(", ")}.` : "Escribe un presupuesto en la otra ventana.",
      curso: "diapositivas 56 a 58.",
    },
    {
      id: "e-zona", titulo: "Caro o ganga para su zona: puntaje z local", para: "El mapa, modo caro o ganga", volver: "p-mapa",
      formula: `z<sub>i</sub> = ${fr("x<sub>i</sub> − x̄<sub>vecinos</sub>", "s<sub>vecinos</sub>")} &nbsp;&nbsp; ganga si z ≤ −1,96 · caro si z ≥ 1,96`,
      texto: `Cada aviso se compara con los avisos a menos de ${M.radio_vecinos_m} m (al menos ${M.minimo_vecinos}), sin contarse a sí mismo, sobre x = ln(precio/m²). Es la primera ley de Tobler hecha prueba: lo caro se mide contra lo cercano. |z| ≥ 1,96 deja un 5 % de probabilidad bajo la normal.`,
      resultado: `${entero(DATOS.z_local.n_con_z)} avisos con vecinos suficientes: ${entero(DATOS.z_local.n_caro)} caros y ${entero(DATOS.z_local.n_ganga)} gangas para su zona.`,
      curso: "diapositivas 28 (primera ley de la geografía) y 55 (puntuación z y valor p).",
    },
    {
      id: "e-gemelos", titulo: "Barrios gemelos: distancia de Hellinger", para: "Barrios gemelos", volver: "p-gemelos",
      formula: `BC = Σ<sub>i</sub> √(p<sub>i</sub> q<sub>i</sub>) &nbsp;&nbsp;&nbsp; H = √(1 − BC)`,
      texto: "p y q son los histogramas del precio por m² de dos barrios, sobre la misma rejilla de 30 intervalos en escala logarítmica. H vale 0 si son idénticos y 1 si no se tocan. El parecido que se muestra es 1 − H. Compara la forma completa, no solo la mediana.",
      resultado: `Gemelos de ${esc(estado.barrio)}: ${gem.map(x => `${esc(x.barrio)} (H = ${dec(x.hellinger, 3)})`).join(", ")}.`,
      curso: "diapositivas 62 (Bhattacharyya) y 66 (Hellinger).",
    },
    {
      id: "e-duelo", titulo: "Duelo de barrios: F, t y Kolmogorov-Smirnov", para: "Duelo de barrios", volver: "p-duelo",
      formula: `F = ${fr("s<sub>1</sub><sup>2</sup>", "s<sub>2</sub><sup>2</sup>")} &nbsp;&nbsp; t = ${fr("x̄<sub>1</sub> − x̄<sub>2</sub>", "√(s<sub>1</sub><sup>2</sup>/n<sub>1</sub> + s<sub>2</sub><sup>2</sup>/n<sub>2</sub>)")}`,
      formula2: `D = máx<sub>x</sub> | F<sub>1</sub>(x) − F<sub>2</sub>(x) |`,
      texto: "Primero la F revisa si las varianzas son iguales (varianza constante). Si lo son, la t usa la varianza combinada; si no, la de arriba, con varianzas separadas. La KS compara las acumuladas completas y no necesita normalidad. H₀: no hay diferencia; se rechaza si p < 0,05.",
      resultado: duelo ? filasTabla(["Prueba", "Estadístico", "p"], [
        ["F de varianzas", dec(duelo.f, 3), valorP(duelo.p_f)],
        [`t (${duelo.varianzas_iguales ? "varianza combinada" : "varianzas separadas"}, gl = ${dec(duelo.gl, 1)})`, dec(tDuelo, 3), valorP(duelo.p_t)],
        ["Kolmogorov-Smirnov", `D = ${dec(duelo.d_ks, 3)}`, valorP(duelo.p_ks)],
      ]) + `<p class="nota">${esc(estado.barrio)} (1) contra ${esc(estado.rival)} (2), sobre el precio por m². Una t negativa indica que el barrio 1 es el más barato.</p>` : "",
      curso: "diapositivas 37 (paramétrica contra no paramétrica), 65 y 80 (KS), 69 a 73 (pruebas de hipótesis), 103 (estadística F) y 108 (varianza constante).",
    },
    {
      id: "e-correlacion", titulo: "Lo que se mueve con el precio: correlación", para: "¿Qué hace subir el precio?", volver: "p-sube",
      formula: `r = ${fr("Σ (x<sub>i</sub> − x̄)(y<sub>i</sub> − ȳ)", "√( Σ (x<sub>i</sub> − x̄)<sup>2</sup> · Σ (y<sub>i</sub> − ȳ)<sup>2</sup> )")} &nbsp;&nbsp; y = ln(precio)`,
      texto: "r mide qué tan en línea recta se mueven dos variables, de −1 a 1. Se usa el logaritmo del precio (y del área) porque el precio crudo tiene una cola larga y unos pocos avisos de lujo dominarían el coeficiente.",
      resultado: filasTabla(["Variable", "r", "p", "n"], DATOS.correlaciones.map(c => [esc(c.nombre) + (c.en_log ? " (ln)" : ""), dec(c.r, 3), valorP(c.p), entero(c.n)])),
      curso: "diapositivas 86 (correlación) y 107 (no normalidad).",
    },
    {
      id: "e-anova", titulo: "Qué explica las diferencias: ANOVA de un factor", para: "¿Qué hace subir el precio?", volver: "p-sube",
      formula: `SS<sub>T</sub> = SS<sub>E</sub> + SS<sub>D</sub> &nbsp;&nbsp; F = ${fr("SS<sub>E</sub> / (k − 1)", "SS<sub>D</sub> / (n − k)")} &nbsp;&nbsp; η<sup>2</sup> = ${fr("SS<sub>E</sub>", "SS<sub>T</sub>")}`,
      texto: "Se separa la variación total de ln(precio) en la que hay entre grupos y la que queda dentro de cada grupo. η² es la parte que explica el factor. No se suman entre factores porque se traslapan: los barrios caros también son de estrato alto y tienen más baños.",
      resultado: filasTabla(["Factor", "k", "F", "p", "η²"], DATOS.anovas.map(a => [esc(a.nombre), a.k, dec(a.f, 1), valorP(a.p), pct(a.eta2, 1)])),
      curso: "diapositivas 95 a 103 (análisis de varianza y estadística F).",
    },
    {
      id: "e-pareados", titulo: "Cuánto suma cada cosa: prueba t pareada", para: "¿Qué hace subir el precio?", volver: "p-sube",
      formula: `d<sub>i</sub> = ln p<sub>i</sub>(con) − ln p<sub>i</sub>(sin) &nbsp;&nbsp; t = ${fr("d̄", "s<sub>d</sub> / √n")} &nbsp;&nbsp; efecto = e<sup>d̄</sup> − 1`,
      texto: `Cada aviso con la característica se empareja con un gemelo sin ella: mismo barrio, tipo, estrato, alcobas y baños, y área a menos de ${pct(M.tolerancia_area)}. La diferencia de logaritmos se lee como porcentaje. Es una asociación: quien tiene piscina suele tener otras cosas que no se ven en el aviso.`,
      resultado: filasTabla(["Característica", "Parejas", "Efecto", "Intervalo 95 %", "t"], DATOS.caracteristicas.map(c => [esc(c.nombre), entero(c.n), pctSigno(c.efecto, 1), `${pctSigno(c.efecto_inf, 1)} a ${pctSigno(c.efecto_sup, 1)}`, dec(c.t, 1)])),
      curso: "diapositivas 69 a 75 (prueba de hipótesis sobre una media, como el ejercicio del café).",
    },
    {
      id: "e-variabilidad", titulo: "Predecible o lotería: coeficiente de variación y F", para: "¿Precio predecible o lotería?", volver: "p-loteria",
      formula: `CV = ${fr("s", "x̄")} &nbsp;&nbsp;&nbsp; F = ${fr("s<sub>a</sub><sup>2</sup>", "s<sub>b</sub><sup>2</sup>")}`,
      texto: "El CV es la desviación estándar en proporción a la media, y permite comparar barrios caros con baratos. Entre estratos se prueba si la varianza de ln(precio/m²) es la misma (homocedasticidad) con la F. Predecible, intermedio y lotería son los tercios del CV.",
      resultado: `${esc(estado.barrio)}: CV = ${pct(CV_DE[estado.barrio].cv, 1)}.` + filasTabla(["Estratos", "F", "gl", "p"], DATOS.variabilidad.comparaciones.map(c => [`${c.a} y ${c.b}`, dec(c.f, 2), `${c.gl1}, ${c.gl2}`, valorP(c.p)])),
      curso: "diapositivas 44 y 45 (varianza y desviación), 103 (estadística F) y 108 (varianza constante).",
    },
    {
      id: "e-estrato", titulo: "Estrato del aviso contra el censo: prueba t", para: "El estrato del aviso contra el estrato real", volver: "p-estrato",
      formula: `t = ${fr("x̄<sub>más alto</sub> − x̄<sub>igual</sub>", "√(s<sub>1</sub><sup>2</sup>/n<sub>1</sub> + s<sub>2</sub><sup>2</sup>/n<sub>2</sub>)")} &nbsp; sobre ln(precio/m²)`,
      texto: `Dentro de las manzanas de un mismo estrato del censo, se comparan los avisos que declaran ese estrato con los que declaran uno mayor. ${entero(ed.n)} avisos tienen estrato del censo.`,
      resultado: filasTabla(["Censo", "Igual", "Más alto", "Diferencia", "t", "p"], ed.comparaciones.map(c => [c.estrato_censo, entero(c.n_igual), entero(c.n_mayor), pctSigno(c.diferencia), dec(c.t, 1), valorP(c.p)])),
      curso: "diapositivas 69 a 73 (pruebas de hipótesis).",
    },
    {
      id: "e-pareto", titulo: "Dónde se publica: diagrama de Pareto", para: "Cómo está repartida la oferta", volver: "p-oferta",
      formula: `% acumulado<sub>k</sub> = ${fr("Σ<sub>j ≤ k</sub> n<sub>j</sub>", "N")}`,
      texto: "Se ordenan los barrios de más a menos avisos y se acumula su participación. Muestra que la oferta en portales se concentra en pocos barrios: el resto de la ciudad arrienda por otros medios.",
      resultado: `${DATOS.pareto.barrios_80} de ${DATOS.pareto.total_barrios} barrios reúnen el 80 % de los ${entero(M.n)} avisos. Los tres primeros: ${DATOS.pareto.barrios.slice(0, 3).map((b, k) => `${esc(b)} (${entero(DATOS.pareto.avisos[k])})`).join(", ")}.`,
      curso: "diapositiva 93 (análisis de Pareto).",
    },
    {
      id: "e-forma", titulo: "La forma del precio: por qué medianas y logaritmos", para: "Toda la página", volver: "p-oferta", grafico: true,
      formula: `asimetría = ${fr("3 (x̄ − Me)", "s")} &nbsp;&nbsp; D<sub>B</sub>(datos, normal)`,
      texto: "Si la media queda muy por encima de la mediana, unos pocos avisos caros arrastran el promedio, y por eso la página muestra medianas. Al sacar logaritmo el precio se parece mucho más a una normal, que es lo que piden las pruebas t y F. Las crestas del estrato son polígonos de frecuencia de ln(precio/m²).",
      resultado: filasTabla(["Variable", "Media", "Mediana", "D<sub>B</sub> contra normal"], [
        ["Precio", pesos(norm.precio.media), pesos(norm.precio.mediana), dec(norm.precio.bhattacharyya, 4)],
        ["ln(precio)", dec(norm.log_precio.media, 3), dec(norm.log_precio.mediana, 3), dec(norm.log_precio.bhattacharyya, 4)],
      ]),
      curso: "diapositivas 39 a 41 (media, mediana y moda), 62 (Bhattacharyya) y 107 (implicaciones de la no normalidad).",
    },
    {
      id: "e-cartas", titulo: "Cartas de barrio: de dónde sale cada dato", para: "Cartas de barrio", volver: "p-cartas",
      formula: `carta = { Me, Me<sub>m²</sub>, CV, % z ≤ −1,96, % z ≥ 1,96, gemelo }`,
      texto: "Precio y precio por m²: medianas. Predecible o lotería: tercios del coeficiente de variación. Gangas y caros en su zona: porcentaje de avisos del barrio con z local fuera de ±1,96. Gemelo: el de menor distancia de Hellinger. «El promedio engaña» aparece si la asimetría de Pearson pasa de 0,6.",
      resultado: `Barrios con carta: ${BARRIOS.length}, los que tienen al menos ${M.minimo_barrio} avisos.`,
      curso: "reúne las tarjetas anteriores.",
    },
  ];
}

// ---------------------------------------------------------------------------
// Gráficas de la ventana de estadística: cada tarjeta muestra, debajo de su
// resultado, la gráfica del método que usa, con el barrio elegido.
// ---------------------------------------------------------------------------

// Cuantil con interpolación lineal sobre una lista ya ordenada.
function cuantilOrdenado(ordenados, q) {
  const pos = (ordenados.length - 1) * q, k = Math.floor(pos), f = pos - k;
  return k + 1 < ordenados.length ? ordenados[k] + f * (ordenados[k + 1] - ordenados[k]) : ordenados[k];
}

// Histograma en proporciones del total, con bins iguales entre lo y hi.
function histogramaDe(valores, lo, hi, bins) {
  const ancho = (hi - lo) / bins, y = new Array(bins).fill(0);
  for (const v of valores) if (v >= lo && v < hi) y[Math.floor((v - lo) / ancho)]++;
  return {
    x0: y.map((_, k) => lo + k * ancho), x1: y.map((_, k) => lo + (k + 1) * ancho),
    y: y.map(c => c / valores.length),
  };
}

const NOMBRE_FAMILIA = { fisk: "log-logística", lognorm: "lognormal", gamma: "gamma" };
const COLOR_FAMILIA = { fisk: "var(--serie2)", lognorm: "var(--serie3)", gamma: "var(--tinta2)" };

/* Histograma de los datos contra el histograma teórico de cada familia candidata,
   sobre los mismos bins con que se calculó la distancia de Bhattacharyya. La
   ganadora va más gruesa. */
function graficaMejorAjuste(c, l, comp, xmin, xmax, fx, nota, extra = {}) {
  const centros = comp.p.map((_, k) => (comp.bordes[k] + comp.bordes[k + 1]) / 2);
  const orden = Object.keys(comp.familias).sort((a, b) => comp.familias[a].distancia - comp.familias[b].distancia);
  leyenda(l, [{ nombre: "Datos (histograma)", color: "var(--serie1)", tipo: "caja" }].concat(orden.map(n => ({
    nombre: `${NOMBRE_FAMILIA[n] ?? n}: D_B = ${dec(comp.familias[n].distancia, 4)}${n === comp.ganadora ? " · ganadora" : ""}`,
    color: COLOR_FAMILIA[n] ?? "var(--tinta3)",
  }))).concat(extra.leyenda ?? []));
  const visibles = comp.p.filter((_, k) => comp.bordes[k + 1] > xmin && comp.bordes[k] < xmax);
  const maxQ = Math.max(...orden.flatMap(n => comp.familias[n].q.filter((_, k) => comp.bordes[k + 1] > xmin && comp.bordes[k] < xmax)));
  lineas(c, {
    columnas: [{ nombre: "de los datos", x0: comp.bordes.slice(0, -1), x1: comp.bordes.slice(1), y: comp.p, color: "var(--serie1)" }],
    series: orden.map(n => ({
      nombre: NOMBRE_FAMILIA[n] ?? n, x: centros, y: comp.familias[n].q,
      color: COLOR_FAMILIA[n] ?? "var(--tinta3)", grosor: n === comp.ganadora ? 3 : 1.5, guiones: n !== comp.ganadora,
    })),
    xmin, xmax, ymin: 0, ymax: Math.max(...visibles, maxQ) * 1.12, fx, fy: pctEje, fyGlobo: v => pct(v, 1),
    alto: 230, descripcion: nota, bandas: extra.bandas, guias: extra.guias,
  });
}

// Diagrama de caja por grupo: caja de Q1 a Q3, línea en la mediana, bigotes del
// percentil 5 al 95 y, si se pide, un punto en la media.
function cajas(contenedor, grupos, cfg) {
  const ancho = Math.max(320, contenedor.clientWidth || 600), alto = cfg.alto ?? 230;
  const m = { izq: 56, der: 12, sup: 12, inf: 30 }, iw = ancho - m.izq - m.der, ih = alto - m.sup - m.inf;
  const Y = v => m.sup + ih - (v - cfg.ymin) / (cfg.ymax - cfg.ymin) * ih;
  contenedor.innerHTML = "";
  const svg = nodo("svg", { viewBox: `0 0 ${ancho} ${alto}`, role: "img", "aria-label": cfg.descripcion ?? "" }, contenedor);
  (cfg.ticksY ?? ticksLineales(cfg.ymin, cfg.ymax, 4)).filter(v => v >= cfg.ymin && v <= cfg.ymax).forEach(v => {
    nodo("line", { x1: m.izq, x2: m.izq + iw, y1: Y(v), y2: Y(v), class: "rejilla-linea" }, svg);
    nodo("text", { x: m.izq - 6, y: Y(v) + 4, "text-anchor": "end" }, svg).textContent = cfg.fy(v);
  });
  (cfg.guiasY ?? []).forEach(g => {
    nodo("line", { x1: m.izq, x2: m.izq + iw, y1: Y(g.y), y2: Y(g.y), class: "guia" }, svg);
    if (g.etiqueta) nodo("text", { x: m.izq + 4, y: Y(g.y) - 5, "text-anchor": "start" }, svg).textContent = g.etiqueta;
  });
  const paso = iw / grupos.length;
  grupos.forEach((g, k) => {
    const cx = m.izq + paso * (k + 0.5), w = Math.min(44, paso * 0.5);
    nodo("line", { x1: cx, x2: cx, y1: Y(g.p95), y2: Y(g.p5), style: "stroke:var(--tinta2);stroke-width:1.2" }, svg);
    nodo("rect", { x: cx - w / 2, y: Y(g.q3), width: w, height: Math.max(1, Y(g.q1) - Y(g.q3)), rx: 3,
      style: "fill:var(--serie1);fill-opacity:.28;stroke:var(--serie1);stroke-width:1.2" }, svg);
    nodo("line", { x1: cx - w / 2, x2: cx + w / 2, y1: Y(g.me), y2: Y(g.me), style: "stroke:var(--tinta);stroke-width:2" }, svg);
    if (cfg.medias) nodo("circle", { cx, cy: Y(g.media), r: 3.5, style: "fill:var(--serie2);stroke:var(--sup);stroke-width:1.5" }, svg);
    nodo("text", { x: cx, y: m.sup + ih + 18, "text-anchor": "middle" }, svg).textContent = g.nombre;
    const zona = nodo("rect", { x: cx - paso / 2, y: m.sup, width: paso, height: ih, fill: "transparent" }, svg);
    zona.addEventListener("pointermove", ev => mostrarGlobo(`<div class="titulo">${esc(g.nombre)} · ${entero(g.n)} avisos</div>
      <div>Mediana <b>${cfg.fy(g.me)}</b></div><div>Q₁ a Q₃: ${cfg.fy(g.q1)} a ${cfg.fy(g.q3)}</div>
      ${cfg.medias ? `<div>Media: ${cfg.fy(g.media)}</div>` : ""}`, ev));
    zona.addEventListener("pointerleave", ocultarGlobo);
  });
}

// ln(valor) por estrato, con lo necesario para los diagramas de caja.
function cajasPorEstrato(valorDe) {
  const grupos = new Map();
  for (let i = 0; i < N; i++) {
    const e = A.estrato[i];
    if (e == null) continue;
    if (!grupos.has(e)) grupos.set(e, []);
    grupos.get(e).push(Math.log(valorDe(i)));
  }
  return [...grupos.keys()].sort((a, b) => a - b).map(e => {
    const v = grupos.get(e).sort((a, b) => a - b);
    return {
      nombre: `Estrato ${e}`, n: v.length, media: v.reduce((s, x) => s + x, 0) / v.length,
      p5: cuantilOrdenado(v, 0.05), q1: cuantilOrdenado(v, 0.25), me: cuantilOrdenado(v, 0.5),
      q3: cuantilOrdenado(v, 0.75), p95: cuantilOrdenado(v, 0.95),
    };
  });
}

// Densidad normal estándar, para comparar contra el histograma de z.
const normalEstandar = z => Math.exp(-z * z / 2) / Math.sqrt(2 * Math.PI);

const GRAFICAS = {
  "e-normal": (c, l) => {
    const { valores } = muestraPrecios(estado.barrio, estado.alcobas);
    const it = grupo(estado.barrio, estado.alcobas).item;
    const lo = cuantilOrdenado(valores, 0.01), hi = cuantilOrdenado(valores, 0.99);
    const h = histogramaDe(valores, lo, hi, 28);
    leyenda(l, [{ nombre: "Avisos (histograma)", color: "var(--serie1)", tipo: "caja" },
      { nombre: "Mitad central, de Q₁ a Q₃", color: "var(--serie3)", tipo: "caja" }]);
    lineas(c, {
      columnas: [{ nombre: "de los avisos", ...h, color: "var(--serie1)" }], series: [],
      bandas: [{ x0: it.q1, x1: it.q3, color: "var(--serie3)" }],
      guias: [{ x: it.mediana, etiqueta: "Me" }, { x: it.media, etiqueta: "x̄" }],
      xmin: lo, xmax: hi, ymin: 0, ymax: Math.max(...h.y) * 1.18, fx: millones, fy: pctEje, fyGlobo: v => pct(v, 1),
      alto: 210, descripcion: "Histograma del precio en el barrio con sus cuartiles y su media",
    });
  },

  "e-percentil": (c, l) => {
    const { valores } = muestraPrecios(estado.barrio, estado.alcobas);
    const it = grupo(estado.barrio, estado.alcobas).item;
    const e = ecdf(valores);
    leyenda(l, [{ nombre: "F̂ₙ(x): avisos parecidos", color: "var(--serie1)" },
      { nombre: "Precio justo (Q₁ a Q₃)", color: "var(--serie3)", tipo: "caja" }]);
    lineas(c, {
      series: [{ nombre: "pide esto o menos", x: e.x, y: e.y, escalon: true, color: "var(--serie1)" }],
      bandas: [{ x0: it.q1, x1: it.q3, color: "var(--serie3)" }],
      guiasY: [{ y: 0.25, etiqueta: "0,25" }, { y: 0.75, etiqueta: "0,75" }],
      guias: estado.precio ? [{ x: estado.precio, etiqueta: "Este aviso" }] : [],
      xlog: true, xmin: cuantilOrdenado(valores, 0.01), xmax: cuantilOrdenado(valores, 0.99), ymin: 0, ymax: 1,
      ticksX: TICKS_PRECIO, fx: millones, fy: v => pct(v), alto: 210,
      descripcion: "Distribución empírica del precio de los avisos parecidos",
    });
  },

  "e-atipicos": (c, l) => {
    // El mismo mejor ajuste, sobre el precio por m² de toda la ciudad, con las
    // colas de la ganadora sombreadas: lo que cae ahí es "precio raro".
    const at = DATOS.atipicos, comp = at.comparacion;
    graficaMejorAjuste(c, l, comp, comp.bordes[0], 160000, miles,
      "Precio por metro cuadrado de la ciudad contra las familias ajustadas, con las colas sombreadas", {
        bandas: [{ x0: comp.bordes[0], x1: at.corte_bajo, color: "var(--polo-alto)", etiqueta: "5 %" },
          { x0: at.corte_alto, x1: 160000, color: "var(--polo-alto)", etiqueta: "5 %" }],
        guias: [{ x: at.iqr_alto, etiqueta: "corte IQR" }],
        leyenda: [{ nombre: "Colas: precio raro", color: "var(--polo-alto)", tipo: "caja" }],
      });
  },

  "e-visitas": (c, l) => {
    const comp = DATOS.grupos[`${estado.barrio}|todas`].comparacion;
    const { valores } = muestraPrecios(estado.barrio, "todas");
    graficaMejorAjuste(c, l, comp, cuantilOrdenado(valores, 0.01), cuantilOrdenado(valores, 0.99), millones,
      "Mejor ajuste: histograma del precio del barrio contra las tres familias candidatas");
  },

  "e-alcanza": (c, l) => {
    if (!estado.presupuesto) { c.innerHTML = ""; l.innerHTML = ""; return; }
    const filas = BARRIOS.map(b => ({ b, f: fPresupuesto(b, estado.alcobas).f })).sort((x, y) => y.f - x.f).slice(0, 8);
    l.innerHTML = "";
    barras(c, filas.map(r => ({ nombre: r.b, valor: r.f, texto: `F = ${dec(r.f, 2)}`, activa: r.b === estado.barrio })), { max: 1 });
  },

  "e-zona": (c, l) => {
    const z = A.z.filter(v => v != null);
    const h = histogramaDe(z, -4, 4, 32), anchoBin = 8 / 32;
    const densidad = h.y.map(v => v / anchoBin);
    const xs = Array.from({ length: 81 }, (_, k) => -4 + k * 0.1);
    leyenda(l, [{ nombre: "z de los avisos (histograma)", color: "var(--serie1)", tipo: "caja" },
      { nombre: "Normal estándar", color: "var(--serie2)" }, { nombre: "Caro o ganga: |z| ≥ 1,96", color: "var(--polo-alto)", tipo: "caja" }]);
    lineas(c, {
      columnas: [{ nombre: "densidad de los avisos", x0: h.x0, x1: h.x1, y: densidad, color: "var(--serie1)" }],
      series: [{ nombre: "normal estándar", x: xs, y: xs.map(normalEstandar), color: "var(--serie2)" }],
      bandas: [{ x0: -4, x1: -1.96, color: "var(--polo-alto)" }, { x0: 1.96, x1: 4, color: "var(--polo-alto)" }],
      guias: [{ x: -1.96, etiqueta: "−1,96" }, { x: 1.96, etiqueta: "1,96" }],
      xmin: -4, xmax: 4, ymin: 0, ymax: Math.max(...densidad, 0.4) * 1.1, ticksX: [-4, -3, -2, -1, 0, 1, 2, 3, 4],
      fx: v => dec(v, 0), fy: v => dec(v, 2), fyGlobo: v => dec(v, 3), alto: 210,
      descripcion: "Histograma del puntaje z local contra la normal estándar",
    });
  },

  "e-gemelos": (c, l) => {
    const g = DATOS.gemelos, gemelo = g.gemelos[estado.barrio][0];
    leyenda(l, [{ nombre: estado.barrio, color: "var(--serie1)" },
      { nombre: `${gemelo.barrio} (H = ${dec(gemelo.hellinger, 3)})`, color: "var(--serie2)" }]);
    const p = g.histogramas[estado.barrio], q = g.histogramas[gemelo.barrio];
    lineas(c, {
      series: [{ nombre: estado.barrio, x: g.centros_m2, y: p, color: "var(--serie1)", relleno: true },
        { nombre: gemelo.barrio, x: g.centros_m2, y: q, color: "var(--serie2)", relleno: true }],
      xlog: true, xmin: g.centros_m2[0], xmax: g.centros_m2[g.centros_m2.length - 1], ymin: 0,
      ymax: Math.max(...p, ...q) * 1.12, ticksX: TICKS_M2, fx: miles, fy: pctEje, fyGlobo: v => pct(v, 1), alto: 210,
      descripcion: "Histogramas del precio por metro cuadrado de un barrio y su gemelo",
    });
  },

  "e-duelo": (c, l) => {
    const a = estado.barrio, b = estado.rival;
    if (!b) return;
    const ea = ecdf(POR_BARRIO[idx(a)].map(i => PRECIO_M2[i])), eb = ecdf(POR_BARRIO[idx(b)].map(i => PRECIO_M2[i]));
    let dMax = 0, xD = ea.x[0];
    for (const x of [...ea.x, ...eb.x]) {
      const d = Math.abs(valorEn({ ...ea, escalon: true }, x) - valorEn({ ...eb, escalon: true }, x));
      if (d > dMax) { dMax = d; xD = x; }
    }
    leyenda(l, [{ nombre: a, color: "var(--serie1)" }, { nombre: b, color: "var(--serie2)" }]);
    lineas(c, {
      series: [{ nombre: a, x: ea.x, y: ea.y, escalon: true, color: "var(--serie1)" },
        { nombre: b, x: eb.x, y: eb.y, escalon: true, color: "var(--serie2)" }],
      segmentos: [{ x: xD, y1: valorEn({ ...ea, escalon: true }, xD), y2: valorEn({ ...eb, escalon: true }, xD), etiqueta: `D = ${dec(dMax, 3)}` }],
      xlog: true, xmin: 15000, xmax: 160000, ymin: 0, ymax: 1, ticksX: TICKS_M2, fx: miles, fy: v => pct(v), alto: 210,
      descripcion: "Distribuciones acumuladas de los dos barrios y la distancia de Kolmogorov-Smirnov",
    });
  },

  "e-correlacion": (c, l) => {
    const paso = Math.max(1, Math.ceil(N / 1500)), xs = [], ys = [];
    for (let i = 0; i < N; i += paso) { xs.push(A.area[i]); ys.push(Math.log(A.precio[i])); }
    const r = DATOS.correlaciones.find(v => v.variable === "area");
    leyenda(l, [{ nombre: `Un aviso de cada ${paso} · r = ${dec(r.r, 3)}`, color: "var(--serie1)", tipo: "punto" }]);
    lineas(c, {
      series: [], puntos: [{ x: xs, y: ys, color: "var(--serie1)", r: 1.8, opacidad: 0.35 }],
      xlog: true, xmin: 20, xmax: 500, ymin: Math.log(5e5), ymax: Math.log(4e7),
      ticksX: [20, 40, 80, 150, 300, 500], ticksY: [1e6, 2e6, 5e6, 1e7, 2e7].map(Math.log),
      fx: v => `${entero(v)} m²`, fy: v => millones(Math.exp(v)), alto: 230,
      descripcion: "Dispersión del área contra el precio, ambos en escala logarítmica",
    });
  },

  "e-anova": (c, l) => {
    const grupos = cajasPorEstrato(i => A.precio[i]);
    const todos = A.precio.map(Math.log), media = todos.reduce((s, x) => s + x, 0) / todos.length;
    leyenda(l, [{ nombre: "Caja: Q₁ a Q₃ · línea: mediana", color: "var(--serie1)", tipo: "caja" },
      { nombre: "Media de cada estrato", color: "var(--serie2)", tipo: "punto" }]);
    cajas(c, grupos, {
      ymin: Math.log(8e5), ymax: Math.log(3e7), ticksY: [1e6, 2e6, 5e6, 1e7, 2e7].map(Math.log),
      fy: v => millones(Math.exp(v)), medias: true, guiasY: [{ y: media, etiqueta: "media general" }],
      descripcion: "Precio por estrato: variación entre grupos y dentro de cada grupo",
    });
  },

  "e-pareados": (c, l) => {
    l.innerHTML = "";
    barras(c, DATOS.caracteristicas.map(x => ({
      nombre: x.nombre, valor: Math.max(0, x.efecto), texto: pctSigno(x.efecto),
      inf: Math.max(0, x.efecto_inf), sup: Math.max(0, x.efecto_sup),
      globo: `<b>${pctSigno(x.efecto, 1)}</b><div class="titulo">intervalo 95 %: ${pctSigno(x.efecto_inf, 1)} a ${pctSigno(x.efecto_sup, 1)}</div>`,
    })));
  },

  "e-variabilidad": (c, l) => {
    const grupos = cajasPorEstrato(i => PRECIO_M2[i]);
    leyenda(l, [{ nombre: "Dispersión de ln(precio/m²) por estrato", color: "var(--serie1)", tipo: "caja" }]);
    cajas(c, grupos, {
      ymin: Math.log(12000), ymax: Math.log(160000), ticksY: [15000, 30000, 60000, 120000].map(Math.log),
      fy: v => miles(Math.exp(v)), descripcion: "Precio por metro cuadrado por estrato: qué tan dispersos están",
    });
  },

  "e-estrato": (c, l) => {
    const ed = DATOS.estrato_declarado;
    leyenda(l, [{ nombre: "Declara el estrato del censo", color: "var(--serie1)", tipo: "caja" },
      { nombre: "Declara uno más alto", color: "var(--serie2)", tipo: "caja" }]);
    const items = [];
    ed.comparaciones.forEach(x => {
      items.push({ nombre: `Censo ${x.estrato_censo}: igual`, valor: x.mediana_igual, texto: miles(x.mediana_igual), color: "var(--serie1)" });
      items.push({ nombre: `más alto (${pctSigno(x.diferencia)})`, valor: x.mediana_mayor, texto: miles(x.mediana_mayor), color: "var(--serie2)" });
    });
    barras(c, items, { max: Math.max(...items.map(x => x.valor)) });
  },

  "e-pareto": (c, l) => {
    const p = DATOS.pareto, xs = p.acumulado.map((_, k) => k + 1);
    l.innerHTML = "";
    lineas(c, {
      series: [{ nombre: "de los avisos", x: xs, y: p.acumulado, color: "var(--serie1)", relleno: true }],
      xmin: 1, xmax: xs.length, ymin: 0, ymax: 1, xEntero: true, fx: v => `${v}`, fy: v => pct(v),
      guiasY: [{ y: 0.8, etiqueta: "80 %" }], guias: [{ x: p.barrios_80, etiqueta: `${p.barrios_80} barrios` }],
      alto: 210, descripcion: "Porcentaje acumulado de avisos por barrio",
    });
  },
};

function pintarTarjetas() {
  const lista = tarjetasEstadistica();
  $("indice").innerHTML = lista.map(t => `<a href="#${t.id}">${esc(t.titulo.split(":")[0])}</a>`).join("");
  $("tarjetas").innerHTML = lista.map(t => `
    <article class="tarjeta${t.grafico ? " ancho" : ""}" id="${t.id}">
      <h3>${esc(t.titulo)}</h3>
      <p class="para">En la búsqueda: ${esc(t.para)}</p>
      <div class="formula">${t.formula}</div>${t.formula2 ? `<div class="formula">${t.formula2}</div>` : ""}
      <p>${esc(t.texto)}</p>
      ${t.grafico ? `<div class="rejilla2"><div><div class="leyenda" id="forma-leyenda"></div><div class="grafico" id="forma-precio"></div></div><div><div class="leyenda"></div><div class="grafico" id="forma-log"></div></div></div>` : ""}
      <div class="resultado">${t.resultado}</div>
      ${GRAFICAS[t.id] ? `<div class="grafica-tarjeta"><div class="leyenda" id="l-${t.id}"></div><div class="grafico" id="g-${t.id}"></div></div>` : ""}
      <div class="curso">${CURSO}${esc(t.curso)}</div>
      <button class="ir-estadistica" data-volver="${t.volver}">Ver en la búsqueda</button>
    </article>`).join("");
  document.querySelectorAll("#tarjetas [data-volver]").forEach(b => b.addEventListener("click", () => irA("buscar", b.dataset.volver)));
  if (!$("v-estadistica").hidden) {
    pintarForma();
    for (const t of lista) if (GRAFICAS[t.id]) GRAFICAS[t.id]($(`g-${t.id}`), $(`l-${t.id}`));
  }
}

function pintarForma() {
  const n = DATOS.normalidad;
  leyenda($("forma-leyenda"), [{ nombre: "Datos", color: "var(--serie1)" }, { nombre: "Normal ajustada", color: "var(--serie2)" }]);
  [["forma-precio", n.precio, millones, "Precio"], ["forma-log", n.log_precio, v => dec(v, 1), "ln(precio)"]].forEach(([id, d, fx, nombre]) => {
    const centros = d.bordes.slice(0, -1).map((b, k) => (b + d.bordes[k + 1]) / 2);
    lineas($(id), {
      series: [
        { nombre: "datos", x: centros, y: d.empirica, color: "var(--serie1)", relleno: true },
        { nombre: "normal", x: centros, y: d.normal, color: "var(--serie2)" },
      ],
      xmin: centros[0], xmax: centros[centros.length - 1], ymin: 0, ymax: Math.max(...d.empirica, ...d.normal) * 1.1,
      fx, fy: pctEje, fyGlobo: v => pct(v, 1), alto: 200,
      guias: [{ x: d.media, etiqueta: "media" }, { x: d.mediana }],
      descripcion: `Histograma de ${nombre} contra la normal`,
    });
  });
}

// ---------------------------------------------------------------------------
// Pestañas, tema y orquestación
// ---------------------------------------------------------------------------

function irA(ventana, ancla, instantaneo = false) {
  const buscar = ventana === "buscar";
  $("v-buscar").hidden = !buscar;
  $("v-estadistica").hidden = buscar;
  $("t-buscar").setAttribute("aria-selected", String(buscar));
  $("t-estadistica").setAttribute("aria-selected", String(!buscar));
  marcarEncabezado(buscar);
  // En la estadística el fondo vuelve al barrio elegido.
  seccionActual = buscar ? seccionActual : "estadistica";
  pintarFondo();
  history.replaceState(null, "", buscar ? "#buscar" : "#estadistica");
  if (buscar) { mapa.resize(); repintarGraficos(); } else { pintarTarjetas(); }
  if (ancla) {
    const el = $(ancla);
    // "instant" y no "auto": con auto manda el scroll-behavior: smooth de la hoja.
    const ir = () => {
      el.scrollIntoView({ behavior: instantaneo ? "instant" : "smooth", block: "start" });
      if (!buscar) { el.classList.add("destacada"); setTimeout(() => el.classList.remove("destacada"), 1600); }
    };
    if (instantaneo) ir(); else requestAnimationFrame(ir);
  } else {
    window.scrollTo({ top: 0 });
  }
}
// El encabezado común enlaza cada ventana por su ancla (#buscar, #estadistica).
// Se marca la que está abierta y se abre la que pida la dirección.
function marcarEncabezado(buscar) {
  document.querySelectorAll('.sitio [data-pagina="buscar"], .sitio [data-pagina="estadistica"]').forEach(a => {
    if ((a.dataset.pagina === "buscar") === buscar) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
}
function abrirSegunAncla(alCargar = false) {
  const ancla = location.hash.slice(1);
  if (ancla === "estadistica") irA("estadistica");
  else if (ancla.startsWith("e-") && $(ancla)) irA("estadistica", ancla, alCargar === true);
  else if (ancla === "buscar" && $("v-buscar").hidden) irA("buscar");
}
window.addEventListener("hashchange", abrirSegunAncla);

$("t-buscar").addEventListener("click", () => irA("buscar"));
$("t-estadistica").addEventListener("click", () => irA("estadistica"));
document.querySelectorAll(".ir-estadistica[data-ir]").forEach(b => b.addEventListener("click", () => irA("estadistica", b.dataset.ir)));

function esOscuro() {
  const t = document.documentElement.dataset.theme;
  return t ? t === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
}
function rotularTema() { $("tema").textContent = esOscuro() ? "Cambiar a modo claro" : "Cambiar a modo oscuro"; }
$("tema").addEventListener("click", () => {
  document.documentElement.dataset.theme = esOscuro() ? "light" : "dark";
  rotularTema(); pintarMapa();
});
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { rotularTema(); pintarMapa(); });

function repintarGraficos() {
  pintarPercentil(); pintarVisitas(); pintarGemelos(); pintarDuelo(); pintarOferta();
}

// ---------------------------------------------------------------------------
// Fondo satelital que acompaña cada sección
// ---------------------------------------------------------------------------

/* Teselas de la imagen satelital de Esri (la misma del mapa, sin puntos),
   difuminadas con CSS. El lugar depende de la sección que se está leyendo: el
   barrio elegido, su gemelo, el barrio donde más te alcanza, los dos barrios del
   duelo partidos en dos mitades, o la ciudad entera en las secciones generales.
   Al cambiar, la vista nueva entra con un fundido encima de la anterior. */
const FONDO_ZOOM = 14;
const TESELA_PX = 256;
const CIUDAD = { lat: 6.245, lng: -75.575, zoom: 12 };
let fondoClave = null;
let seccionActual = "p-percentil";

const lugar = nombre => DATOS.fichas[nombre] ? { lat: DATOS.fichas[nombre].lat, lng: DATOS.fichas[nombre].lng, zoom: FONDO_ZOOM } : null;

function enfoqueDe(seccion) {
  switch (seccion) {
    case "p-alcanza": {
      if (!estado.presupuesto) return [lugar(estado.barrio)];
      let mejor = estado.barrio, fMax = -1;
      for (const b of BARRIOS) { const { f } = fPresupuesto(b, estado.alcobas); if (f > fMax) { fMax = f; mejor = b; } }
      return [lugar(mejor)];
    }
    case "p-gemelos": return [lugar(DATOS.gemelos.gemelos[estado.barrio][0].barrio)];
    case "p-duelo": return estado.rival ? [lugar(estado.barrio), lugar(estado.rival)] : [lugar(estado.barrio)];
    case "p-sube": case "p-oferta": return [CIUDAD];
    default: return [lugar(estado.barrio)];
  }
}

// Teselas alrededor de un lugar, con ese lugar en la fracción `fx` del ancho de la pantalla.
function capaTeselas(sitio, fx) {
  const n = 2 ** sitio.zoom, rad = sitio.lat * Math.PI / 180;
  const xt = (sitio.lng + 180) / 360 * n;
  const yt = (1 - Math.log(Math.tan(rad) + 1 / Math.cos(rad)) / Math.PI) / 2 * n;
  // El difuminado y la deriva dejan bordes al aire: se cubre de más por cada lado.
  const cols = Math.ceil(window.innerWidth / TESELA_PX) + 3, filas = Math.ceil(window.innerHeight / TESELA_PX) + 3;
  const x0 = Math.floor(xt - cols * fx), y0 = Math.floor(yt - filas / 2);
  const capa = document.createElement("div");
  capa.className = "teselas";
  capa.style.width = `${cols * TESELA_PX}px`;
  capa.style.height = `${filas * TESELA_PX}px`;
  capa.style.left = `calc(${fx * 100}% - ${(xt - x0) * TESELA_PX}px)`;
  capa.style.top = `calc(50% - ${(yt - y0) * TESELA_PX}px)`;
  for (let j = 0; j < filas; j++) {
    for (let i = 0; i < cols; i++) {
      const img = new Image();
      img.alt = "";
      img.decoding = "async";
      img.src = `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/${sitio.zoom}/${y0 + j}/${x0 + i}`;
      img.style.left = `${i * TESELA_PX}px`;
      img.style.top = `${j * TESELA_PX}px`;
      capa.appendChild(img);
    }
  }
  return capa;
}

function pintarFondo() {
  const lugares = enfoqueDe(seccionActual).filter(Boolean);
  if (!lugares.length) return;
  const clave = lugares.map(l => `${l.lat},${l.lng},${l.zoom}`).join("|") + `|${window.innerWidth}x${window.innerHeight}`;
  if (clave === fondoClave) return;
  fondoClave = clave;
  const vista = document.createElement("div");
  vista.className = "vista";
  vista.style.opacity = "0";
  if (lugares.length === 2) {
    lugares.forEach((sitio, k) => {
      const mitad = document.createElement("div");
      mitad.className = "teselas-mitad " + (k === 0 ? "izquierda" : "derecha");
      mitad.appendChild(capaTeselas(sitio, k === 0 ? 0.25 : 0.75));
      vista.appendChild(mitad);
    });
  } else {
    vista.appendChild(capaTeselas(lugares[0], 0.5));
  }
  const fondo = $("fondo-satelite");
  const anteriores = [...fondo.querySelectorAll(".vista")];
  fondo.appendChild(vista);
  requestAnimationFrame(() => requestAnimationFrame(() => { vista.style.opacity = "1"; }));
  setTimeout(() => anteriores.forEach(a => a.remove()), 1000);
}

// La sección que cruza la franja central de la pantalla es la que manda en el fondo.
const vigiaSecciones = new IntersectionObserver(entradas => {
  for (const e of entradas) {
    if (e.isIntersecting && e.target.id && e.target.id !== seccionActual) {
      seccionActual = e.target.id;
      pintarFondo();
    }
  }
}, { rootMargin: "-45% 0px -45% 0px" });
document.querySelectorAll("#v-buscar .bloque").forEach(b => vigiaSecciones.observe(b));

// ---------------------------------------------------------------------------
// Animaciones al entrar en vista
// ---------------------------------------------------------------------------

const sinMovimiento = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// Las tarjetas suben y aparecen la primera vez que llegan a la pantalla.
const vigiaEntradas = new IntersectionObserver(entradas => {
  for (const e of entradas) {
    if (e.isIntersecting) { e.target.classList.add("visible"); vigiaEntradas.unobserve(e.target); }
  }
}, { threshold: 0.08 });
function observarEntrada(el) {
  if (sinMovimiento || el.classList.contains("visible")) return;
  el.classList.add("aparece");
  vigiaEntradas.observe(el);
}
document.querySelectorAll("#v-buscar .bloque").forEach(observarEntrada);

/* Las gráficas se dibujan solas la primera vez que se ven: cada línea se traza de
   izquierda a derecha y los rellenos aparecen. Solo la primera vez por gráfica,
   para que escribir un presupuesto no las haga redibujarse a cada tecla. */
const vigiaGraficas = new IntersectionObserver(entradas => {
  for (const e of entradas) {
    if (!e.isIntersecting) continue;
    vigiaGraficas.unobserve(e.target);
    trazar(e.target);
  }
}, { threshold: 0.25 });
function animarAlVer(contenedor) {
  if (sinMovimiento || contenedor.dataset.animado) return;
  contenedor.dataset.animado = "pendiente";
  vigiaGraficas.observe(contenedor);
}
function trazar(contenedor) {
  contenedor.dataset.animado = "hecho";
  for (const p of contenedor.querySelectorAll("path")) {
    const estilo = p.getAttribute("style") || "";
    // Las líneas punteadas aparecen con un fundido: trazarlas con dasharray les borraría el punteado.
    if (estilo.includes("fill:none") && !estilo.includes("stroke-dasharray")) {
      const largo = p.getTotalLength();
      p.style.strokeDasharray = `${largo}`;
      p.style.strokeDashoffset = `${largo}`;
      p.getBoundingClientRect();
      p.style.transition = "stroke-dashoffset 1.1s cubic-bezier(.3,.7,.2,1)";
      p.style.strokeDashoffset = "0";
    } else {
      p.style.opacity = "0";
      p.getBoundingClientRect();
      p.style.transition = "opacity 1.1s ease";
      p.style.opacity = "";
    }
  }
  for (const c of contenedor.querySelectorAll("circle")) {
    c.style.opacity = "0";
    c.getBoundingClientRect();
    c.style.transition = "opacity .4s ease .9s";
    c.style.opacity = "";
  }
}

// Las barras crecen desde cero la primera vez que se ven.
function crecerAlVer(contenedor) {
  if (sinMovimiento || contenedor.dataset.crecido) return;
  contenedor.dataset.crecido = "pendiente";
  const rellenos = [...contenedor.querySelectorAll(".relleno")];
  const metas = rellenos.map(r => r.style.width);
  rellenos.forEach(r => { r.style.width = "0%"; });
  const vigia = new IntersectionObserver(entradas => {
    if (!entradas.some(e => e.isIntersecting)) return;
    vigia.disconnect();
    contenedor.dataset.crecido = "hecho";
    rellenos.forEach((r, k) => { r.classList.add("creciendo"); r.style.width = metas[k]; });
  }, { threshold: 0.2 });
  vigia.observe(contenedor);
}

/* Las cifras grandes cuentan desde su valor anterior hasta el nuevo cuando
   cambian: al elegir otro barrio, la mediana sube o baja en vez de saltar. */
const cifrasPrevias = new Map();
function contarCifras(contenedor) {
  const cifras = [...contenedor.querySelectorAll(".cifra, .cifra-sm")];
  cifras.forEach((el, k) => {
    const m = el.textContent.match(/^(\D*?)(\d{1,3}(?:\.\d{3})+|\d+)(\D*)$/);
    if (!m) return;
    const destino = Number(m[2].replace(/\./g, ""));
    const clave = `${contenedor.id}|${k}`;
    const origen = cifrasPrevias.get(clave) ?? 0;
    cifrasPrevias.set(clave, destino);
    if (sinMovimiento || origen === destino) return;
    const inicio = performance.now(), duracion = 700;
    const paso = ahora => {
      const t = Math.min(1, (ahora - inicio) / duracion), e = 1 - Math.pow(1 - t, 3);
      el.textContent = m[1] + entero(origen + (destino - origen) * e) + m[3];
      if (t < 1) requestAnimationFrame(paso);
    };
    requestAnimationFrame(paso);
  });
}

function actualizar() {
  pintarFondo();
  document.querySelectorAll(".nombre-barrio").forEach(el => { el.textContent = estado.barrio; });
  const n = POR_BARRIO[idx(estado.barrio)].length;
  $("c-barrio-ayuda").textContent = `${entero(n)} avisos`;
  $("c-presupuesto-ayuda").textContent = estado.presupuesto ? salarios(estado.presupuesto) : "";
  $("c-precio-ayuda").textContent = estado.precio ? salarios(estado.precio) : "";
  pintarNormal(); pintarPercentil(); pintarVisitas(); pintarAlcanza(); pintarMapa();
  contarCifras($("normal-cifras")); contarCifras($("visitas-cifras"));
  pintarGemelos(); pintarDuelo(); pintarLoteria(); pintarCartas();
  if (!$("v-estadistica").hidden) pintarTarjetas();
}

let esperaRedimension;
window.addEventListener("resize", () => {
  clearTimeout(esperaRedimension);
  esperaRedimension = setTimeout(() => { pintarFondo(); if (!$("v-buscar").hidden) repintarGraficos(); else pintarTarjetas(); }, 150);
});

$("subtitulo").textContent = `${entero(M.n)} avisos de vivienda en arriendo recogidos de portales inmobiliarios el ${M.captura.split("-").reverse().join("/")}, en ${entero(M.n_barrios_total)} barrios.`;
$("pie").textContent = `Precios pedidos en los avisos, no precios pactados. Los portales sobrerrepresentan la oferta formal e intermediada. Salario mínimo 2026: ${pesos(SM)}. Imagen satelital de fondo: Esri, Maxar, Earthstar Geographics.`;
selBarrio.value = estado.barrio;
rotularTema();
pintarSube();
pintarEstrato();
pintarOferta();
actualizar();
if (location.hash.slice(1).startsWith("e-")) pintarTarjetas(); // las tarjetas existen antes de buscar su ancla
abrirSegunAncla(true);
