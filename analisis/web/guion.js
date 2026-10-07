/* Mapa de arriendos de Medellín.
   Todo va dentro de un solo archivo HTML: los datos, el estilo y este guion. Lo
   único que sale a la red son las teselas del mapa base, y si no cargan la
   página sigue siendo legible, porque los puntos de las manzanas dibujan la
   ciudad por sí solos. Ninguna fuente exige clave de API.

   La página es solo el mapa, a la manera del de consumo de EPM: puntos exactos,
   un panel corto para leerlo y nada de cifras de informe. La estadística vive
   en la consulta, enlazada desde el panel. */

(() => {
  "use strict";

  const { puntos } = DATOS;
  const resumen = puntos.resumen;
  const AV = puntos.avisos;
  const MZ = puntos.manzanas;
  const NA = AV.lat.length;
  const NM = MZ.lat.length;
  const RADIO = resumen.radio_m;

  // ── formato ────────────────────────────────────────────────
  const miles = (v) => (v == null ? "–" : Math.round(v).toLocaleString("es-CO"));
  const pesos = (v) => (v == null ? "–" : "$" + miles(v));
  const milPesos = (v) => "$" + miles(v / 1000) + " mil";
  const pct = (v, d = 1) => (v == null ? "–" : v.toFixed(d).replace(".", ",") + " %");
  const pctSig = (v, d = 0) =>
    v == null ? "–" : (v > 0 ? "+" : "−") + Math.abs(v).toFixed(d).replace(".", ",") + " %";
  const leerVar = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const $ = (id) => document.getElementById(id);

  document.getElementById("intro").innerHTML =
    `Cada punto es uno de los <b>${miles(NA)} avisos de arriendo</b> publicados en ` +
    `portales, en su ubicación exacta. Cambia la capa para ver el precio, dónde la ` +
    `ubicación encarece o en qué barrios no se anuncia nada. Pasa el cursor sobre un punto para ver sus datos.`;

  // ── capas ──────────────────────────────────────────────────
  // Rampas validadas del proyecto. Cálido es caro, frío es barato, en todas las
  // capas y también en la consulta, para que el color diga lo mismo en todo el sitio.
  const RAMPA = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"];
  const RAMPA_CALIDA = ["#f5efe0", "#f0d494", "#e5a75c", "#d4762f", "#a8401c", "#6d1f10"];
  const LISA = {
    "alto-alto": "#d03b3b",
    "alto-bajo": "#ec835a",
    "bajo-alto": "#86b6ef",
    "bajo-bajo": "#184f95",
    "no significativo": "#cfc6b6",
  };
  const ETIQUETA_LISA = {
    "alto-alto": "Caro rodeado de caros",
    "alto-bajo": "Caro rodeado de baratos",
    "bajo-alto": "Barato rodeado de caros",
    "bajo-bajo": "Barato rodeado de baratos",
    "no significativo": "Sin patrón",
  };

  function cuantiles(valores, n) {
    const s = valores.filter((v) => v != null && !isNaN(v)).sort(d3.ascending);
    return d3.range(n + 1).map((i) => d3.quantile(s, i / n));
  }

  /* Cada capa dice de qué puntos sale (avisos o manzanas), cómo se pinta cada
     uno y cómo se explica en el panel. `tenue` marca los puntos sin valor en
     esa capa: se dibujan pequeños y claros, sin competir con los que tienen dato. */
  const CAPAS = {
    precio: {
      fuente: "avisos",
      construir() {
        const cortes = cuantiles(AV.precio_m2, 7);
        const escala = d3.scaleThreshold().domain(cortes.slice(1, -1)).range(RAMPA);
        return {
          color: (i) => escala(AV.precio_m2[i]),
          tenue: () => false,
          titulo: "Precio pedido por metro cuadrado",
          rampa: RAMPA,
          pies: [`menos de ${milPesos(cortes[1])}`, `más de ${milPesos(cortes[cortes.length - 2])}`],
          nota: "Azul claro: los avisos más baratos por metro cuadrado. Azul oscuro: los más caros.",
        };
      },
    },

    sobreprecio: {
      fuente: "avisos",
      construir() {
        const vals = AV.sobreprecio.filter((v) => v != null);
        const tope = d3.quantile(vals.map(Math.abs).sort(d3.ascending), 0.95) || 30;
        const escala = d3
          .scaleLinear()
          .domain([-tope, 0, tope])
          .range([leerVar("--barato"), leerVar("--neutro"), leerVar("--caro")])
          .clamp(true);
        return {
          color: (i) => (AV.sobreprecio[i] == null ? leerVar("--sin-datos") : escala(AV.sobreprecio[i])),
          tenue: (i) => AV.sobreprecio[i] == null,
          titulo: "Lo que la ubicación le suma al precio",
          rampa: d3.range(7).map((k) => escala(-tope + (2 * tope * k) / 6)),
          pies: [`${pctSig(-tope)}`, "en línea", `${pctSig(tope)}`],
          extra: [{ color: leerVar("--sin-datos"), texto: "Aviso de hace más de 90 días" }],
          nota: "Rojo: el aviso pide más de lo que su tamaño, estrato y demás características explican; esa diferencia la pone el lugar. Azul: pide menos.",
        };
      },
    },

    conglomerado: {
      fuente: "avisos",
      construir: () => ({
        color: (i) =>
          AV.conglomerado[i] == null ? leerVar("--sin-datos") : LISA[puntos.conglomerados[AV.conglomerado[i]]],
        tenue: (i) => AV.conglomerado[i] == null,
        titulo: "Dónde se agrupan los precios",
        lista: Object.keys(ETIQUETA_LISA).map((k) => ({ color: LISA[k], texto: ETIQUETA_LISA[k] })),
        extra: [{ color: leerVar("--sin-datos"), texto: "Aviso de hace más de 90 días" }],
        nota: "Los arriendos caros tienden a estar junto a otros caros, y los baratos junto a baratos.",
      }),
    },

    cobertura: {
      fuente: "manzanas",
      construir() {
        const cortes = [0, 5, 15, 35, 70, 150];
        const escala = d3.scaleThreshold().domain(cortes.slice(1)).range(RAMPA_CALIDA);
        return {
          color: (i) => (!MZ.avisos_cerca[i] ? leerVar("--sin-datos") : escala(MZ.cobertura[i] ?? 0)),
          tenue: (i) => !MZ.viviendas[i],
          titulo: "Arriendos publicados cerca de cada manzana",
          rampa: RAMPA_CALIDA,
          pies: ["pocos", "muchos"],
          extra: [{ color: leerVar("--sin-datos"), texto: `Ningún aviso a menos de ${RADIO} m` }],
          nota: `Cada punto es una manzana del censo. En las grises vive el ${pct(
            resumen.pct_viviendas_sin_datos
          )} de las viviendas de la ciudad: ahí el arriendo no se anuncia en portales.`,
        };
      },
    },

    viviendas: {
      fuente: "manzanas",
      construir() {
        const cortes = cuantiles(MZ.viviendas.filter((v) => v > 0), 6);
        const escala = d3.scaleThreshold().domain(cortes.slice(1, -1)).range(RAMPA_CALIDA);
        return {
          color: (i) => (MZ.viviendas[i] ? escala(MZ.viviendas[i]) : leerVar("--sin-datos")),
          tenue: (i) => !MZ.viviendas[i],
          titulo: "Viviendas censadas por manzana",
          rampa: RAMPA_CALIDA,
          pies: [`menos de ${miles(cortes[1])}`, `más de ${miles(cortes[cortes.length - 2])}`],
          nota: "La ciudad que hay debajo de los avisos: cada manzana del censo del DANE, tenga arriendos publicados o no.",
        };
      },
    },
  };

  // ── mapa ───────────────────────────────────────────────────
  // El fondo satelital y la capa de puntos salen de mapa_satelite.js, común a
  // todo el sitio. Ahí está también por qué el mapa es MapLibre y no Leaflet.

  const esOscuro = () =>
    document.documentElement.dataset.tema === "oscuro" ||
    (!document.documentElement.dataset.tema && matchMedia("(prefers-color-scheme: dark)").matches);

  /* El encuadre se calcula sobre donde vive la gente, pesando cada manzana por
     sus viviendas censadas. Encuadrar por los avisos metería por la puerta de
     atrás el sesgo que el mapa denuncia, porque los avisos se amontonan en el sur. */
  function limitesUtiles(recorte = 0.015) {
    const total = d3.sum(MZ.viviendas) || 1;
    const cuantil = (eje, p) => {
      const orden = d3.range(NM).sort((a, b) => MZ[eje][a] - MZ[eje][b]);
      let acumulado = 0;
      for (const i of orden) {
        acumulado += MZ.viviendas[i] || 0;
        if (acumulado / total >= p) return MZ[eje][i];
      }
      return MZ[eje][orden[orden.length - 1]];
    };
    return [
      [cuantil("lng", recorte), cuantil("lat", recorte)],
      [cuantil("lng", 1 - recorte), cuantil("lat", 1 - recorte)],
    ];
  }
  const LIMITES = limitesUtiles();

  // El panel tapa la franja izquierda; el encuadre la descuenta para que la
  // ciudad quede centrada en lo que sí se ve.
  function margenes() {
    const panel = document.querySelector(".panel").getBoundingClientRect();
    return window.innerWidth <= 720
      ? { top: 70, left: 12, right: 12, bottom: panel.height + 12 }
      : { top: 24, left: panel.right + 250, right: 80, bottom: 24 };
  }

  const mapa = MapaSatelite.crear("mapa", { bounds: LIMITES, fitBoundsOptions: { padding: margenes() }, minZoom: 9 });
  const encuadrar = () => mapa.fitBounds(LIMITES, { padding: margenes(), duration: 600 });

  // ── buscar un barrio ───────────────────────────────────────
  // El centro de cada barrio es la mediana de sus avisos. La búsqueda no exige
  // tildes ni mayúsculas: "belen" encuentra Belen y "aguacatala" La Aguacatala.
  const normalizar = (t) => t.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();
  const CENTROS = (() => {
    const grupos = new Map();
    AV.barrio.forEach((b, i) => {
      if (!b) return;
      if (!grupos.has(b)) grupos.set(b, { lat: [], lng: [] });
      grupos.get(b).lat.push(AV.lat[i]);
      grupos.get(b).lng.push(AV.lng[i]);
    });
    return [...grupos].map(([nombre, g]) => ({ nombre, n: g.lat.length, lat: d3.median(g.lat), lng: d3.median(g.lng) }))
      .sort((a, b) => b.n - a.n);
  })();
  $("lista-barrios").innerHTML = CENTROS.map((c) => `<option value="${c.nombre}">`).join("");
  $("buscar-barrio").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const q = normalizar($("barrio-buscado").value);
    const hallado = q && (CENTROS.find((c) => normalizar(c.nombre) === q) || CENTROS.find((c) => normalizar(c.nombre).includes(q)));
    const nota = $("barrio-nota");
    if (!hallado) {
      nota.hidden = false;
      nota.textContent = "No hay avisos en un barrio con ese nombre.";
      return;
    }
    nota.hidden = false;
    nota.textContent = `${hallado.nombre}: ${miles(hallado.n)} avisos.`;
    $("barrio-buscado").value = hallado.nombre;
    mapa.flyTo({ center: [hallado.lng, hallado.lat], zoom: 15, padding: margenes(), speed: 1.4 });
  });

  $("mas").addEventListener("click", () => mapa.zoomIn());
  $("menos").addEventListener("click", () => mapa.zoomOut());
  $("todo").addEventListener("click", encuadrar);
  new ResizeObserver(() => mapa.resize()).observe($("mapa"));

  // ── puntos ─────────────────────────────────────────────────
  const separados = MapaSatelite.separar(AV.lat, AV.lng);
  const pilaAviso = separados.pila;
  const COORDENADAS = {
    avisos: { lat: separados.lat, lng: separados.lng },
    manzanas: { lat: MZ.lat, lng: MZ.lng },
  };

  let capaActual = "precio";
  let pintor = null;
  let fijado = null; // { fuente, i }
  const marcas = {};
  let listo = false; // la capa de puntos existe desde el evento load
  let opacidad = 0.8;

  // ── globo ──────────────────────────────────────────────────
  const globo = $("globo");

  function contenido(fuente, i, fija) {
    const filas = [];
    const f = (rot, val) => filas.push(`<dt>${rot}</dt><dd>${val}</dd>`);
    const marca = fija ? '<span class="fija">fijado</span>' : "";
    if (fuente === "avisos") {
      const cong = AV.conglomerado[i];
      f("Arriendo", pesos(AV.precio[i]));
      f("Por m²", pesos(AV.precio_m2[i]));
      f("Área", `${miles(AV.area[i])} m²`);
      if (AV.estrato[i] != null) f("Estrato", AV.estrato[i]);
      if (AV.sobreprecio[i] != null) f("Por la ubicación", pctSig(AV.sobreprecio[i]));
      if (AV.amoblado[i]) f("Amoblado", "sí");
      const pila = pilaAviso[i] > 1
        ? `<div class="aviso">Ubicación aproximada: ${miles(pilaAviso[i])} avisos comparten este punto.</div>` : "";
      return `<div class="tit">${AV.barrio[i] || "Aviso"}${marca}</div>` +
        (cong != null ? `<div class="sub">${ETIQUETA_LISA[puntos.conglomerados[cong]]}</div>` : "") +
        `<dl>${filas.join("")}</dl>${pila}`;
    }
    f("Viviendas", miles(MZ.viviendas[i]));
    f(`Avisos a ${RADIO} m`, miles(MZ.avisos_cerca[i]));
    const vacia = !MZ.avisos_cerca[i] && MZ.viviendas_cerca[i]
      ? `<div class="aviso">A su alrededor hay ${miles(MZ.viviendas_cerca[i])} viviendas y ningún arriendo publicado.</div>` : "";
    return `<div class="tit">Manzana del censo${marca}</div>` +
      (MZ.estrato[i] != null ? `<div class="sub">estrato ${MZ.estrato[i]}</div>` : "") +
      `<dl>${filas.join("")}</dl>${vacia}`;
  }

  function mostrarGlobo(fuente, i, fija = false) {
    globo.innerHTML = contenido(fuente, i, fija);
    const c = COORDENADAS[fuente];
    const p = mapa.project([c.lng[i], c.lat[i]]);
    const caja = $("mapa").getBoundingClientRect();
    const w = globo.offsetWidth, h = globo.offsetHeight;
    let x = p.x + 14, y = p.y + 14;
    if (x + w > caja.width - 8) x = p.x - w - 14;
    if (y + h > caja.height - 8) y = p.y - h - 14;
    globo.style.left = x + "px";
    globo.style.top = y + "px";
    globo.classList.add("visible");
  }
  const ocultarGlobo = () => globo.classList.remove("visible");

  function soltar() {
    if (fijado) marcas[fijado.fuente].marcar(null);
    fijado = null;
    ocultarGlobo();
  }

  // ── pintar ─────────────────────────────────────────────────
  function leyenda() {
    const l = pintor;
    $("leyenda-titulo").textContent = l.titulo;
    let html = "";
    if (l.rampa) {
      html += `<div class="rampa">${l.rampa.map((c) => `<div style="background:${c}"></div>`).join("")}</div>` +
        `<div class="rampa-pies">${l.pies.map((p) => `<span>${p}</span>`).join("")}</div>`;
    }
    if (l.lista) {
      html += `<ul class="lista">${l.lista.map((e) => `<li><span class="punto" style="background:${e.color}"></span>${e.texto}</li>`).join("")}</ul>`;
    }
    if (l.extra) {
      html += `<ul class="lista extra">${l.extra.map((e) => `<li><span class="punto" style="background:${e.color}"></span>${e.texto}</li>`).join("")}</ul>`;
    }
    $("leyenda").innerHTML = html;
    $("leyenda-nota").textContent = l.nota;
  }

  function pintar() {
    const capa = CAPAS[capaActual];
    pintor = capa.construir();
    if (fijado && fijado.fuente !== capa.fuente) soltar();
    const c = COORDENADAS[capa.fuente];
    mapa.getSource(capa.fuente).setData(MapaSatelite.rasgos(c.lat, c.lng, pintor.color, pintor.tenue));
    for (const fuente of ["avisos", "manzanas"]) {
      mapa.setLayoutProperty(fuente, "visibility", fuente === capa.fuente ? "visible" : "none");
    }
    if (fijado) mostrarGlobo(fijado.fuente, fijado.i, true);
    leyenda();
  }

  mapa.on("load", () => {
    MapaSatelite.capaPuntos(mapa, "manzanas", { radio: 2.2 });
    MapaSatelite.capaPuntos(mapa, "avisos", { radio: 2.5 });
    for (const fuente of ["avisos", "manzanas"]) {
      marcas[fuente] = MapaSatelite.alPasar(mapa, fuente, {
        entra: (i) => { if (!fijado) mostrarGlobo(fuente, i); },
        sale: () => { if (!fijado) ocultarGlobo(); },
      });
      mapa.on("click", fuente, (e) => {
        e.originalEvent.clicEnPunto = true;
        const i = e.features[0].id;
        if (fijado && fijado.fuente === fuente && fijado.i === i) return soltar();
        fijado = { fuente, i };
        marcas[fuente].marcar(i);
        mostrarGlobo(fuente, i, true);
      });
    }
    // Clic fuera de los puntos: suelta el que estaba fijo.
    mapa.on("click", (e) => { if (!e.originalEvent.clicEnPunto) soltar(); });
    mapa.on("move", () => { if (fijado) mostrarGlobo(fijado.fuente, fijado.i, true); else ocultarGlobo(); });
    listo = true;
    aplicarOpacidad();
    pintar();
  });

  // Opacidad: deja ver la calle o el satélite debajo de una zona muy cargada.
  function aplicarOpacidad() {
    for (const fuente of ["avisos", "manzanas"]) MapaSatelite.opacidad(mapa, fuente, opacidad);
  }
  $("opacidad").addEventListener("input", (e) => {
    opacidad = e.target.value / 100;
    $("opacidad-valor").textContent = `${e.target.value} %`;
    if (listo) aplicarOpacidad();
  });

  document.querySelectorAll(".capas button").forEach((b) =>
    b.addEventListener("click", () => {
      document.querySelectorAll(".capas button").forEach((o) => o.setAttribute("aria-pressed", "false"));
      b.setAttribute("aria-pressed", "true");
      capaActual = b.dataset.capa;
      if (listo) pintar();
    })
  );

  // ── tema ───────────────────────────────────────────────────
  $("tema").addEventListener("click", () => {
    document.documentElement.dataset.tema = esOscuro() ? "claro" : "oscuro";
    // Algunos colores de las capas salen de las variables del tema, así que se
    // repinta todo. El fondo satelital es el mismo en los dos modos.
    if (listo) pintar();
  });
})();
