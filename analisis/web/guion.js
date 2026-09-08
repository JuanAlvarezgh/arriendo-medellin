/* Tablero de arriendos de Medellín.
   Todo va dentro de un solo archivo HTML: los datos, el estilo y este guion. Lo
   único que sale a la red son las teselas del mapa base, y si no cargan la
   página sigue siendo legible, porque los hexágonos dibujan la ciudad por sí
   solos. Ninguna fuente exige clave de API. */

(() => {
  "use strict";

  const { rejilla, resumen, modelo, barrios, ipc, turismo, amoblados } = DATOS;
  const celdas = rejilla.celdas;

  // ── formato ────────────────────────────────────────────────
  const miles = (v) => (v == null ? "–" : d3.format(",.0f")(v).replace(/,/g, "."));
  const pesos = (v) => (v == null ? "–" : "$" + miles(v));
  const pct = (v, d = 1) => (v == null ? "–" : v.toFixed(d).replace(".", ",") + " %");
  const pctSig = (v, d = 1) =>
    v == null ? "–" : (v > 0 ? "+" : "−") + Math.abs(v).toFixed(d).replace(".", ",") + " %";

  const leerVar = (n) => getComputedStyle(document.body).getPropertyValue(n).trim();

  // ── indicadores de portada ─────────────────────────────────
  // Todas estas cifras salen del modelo recién estimado. Estuvieron escritas a
  // mano hasta que una corrección de datos las dejó obsoletas en silencio.
  const NOMBRE_PORTALES = { 1: "un portal", 2: "dos portales", 3: "tres portales", 4: "cuatro portales" };
  const decimal = (v, d = 4) => v.toFixed(d).replace(".", ",");

  const INDICADORES = [
    {
      cifra: miles(modelo.avisos_recogidos),
      rotulo: "avisos recogidos",
      nota: "de " + (NOMBRE_PORTALES[modelo.portales_recogidos] || modelo.portales_recogidos + " portales"),
    },
    { cifra: pesos(modelo.precio_m2_mediano), rotulo: "precio mediano por m²", nota: "en arriendo" },
    {
      cifra: pct(modelo.r2_ajustado * 100),
      rotulo: "de la varianza explicada",
      nota: `modelo hedónico sobre ${miles(modelo.avisos_modelo)} avisos`,
    },
    {
      cifra: `${Math.round(modelo.banda_ubicacion_pp)} pp`,
      rotulo: "cuesta la ubicación",
      nota: `de ${modelo.barrio_mas_caro.barrio} a ${modelo.barrio_mas_barato.barrio}`,
    },
    {
      cifra: "+" + decimal(modelo.moran_i),
      rotulo: "índice de Moran",
      nota: "el precio depende del de los vecinos",
    },
  ];

  d3.select("#indicadores")
    .selectAll("div")
    .data(INDICADORES)
    .join("div")
    .attr("class", "ind vidrio")
    .html(
      (d) =>
        `<span class="cifra">${d.cifra}</span>
         <div class="rotulo">${d.rotulo}</div>
         <div class="nota">${d.nota}</div>`
    );

  if (resumen.pct_viviendas_sin_datos != null) {
    document.getElementById("hallazgo-cifra").textContent =
      pct(resumen.pct_viviendas_sin_datos);
    document.getElementById("h-total").textContent = miles(resumen.celdas_totales);
    document.getElementById("h-sin").textContent = miles(resumen.celdas_sin_avisos);
    document.getElementById("h-viv").textContent = miles(resumen.viviendas_sin_ningun_aviso);
  }

  // ── definición de capas ────────────────────────────────────
  const RAMPA = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"];
  const RAMPA_CALIDA = ["#f5efe0", "#f0d494", "#e5a75c", "#d4762f", "#a8401c", "#6d1f10"];
  const LISA = {
    "alto-alto": "#184f95",
    "bajo-bajo": "#d03b3b",
    "alto-bajo": "#86b6ef",
    "bajo-alto": "#ec835a",
    "no significativo": "#d9d3c8",
  };
  const ETIQUETA_LISA = {
    "alto-alto": "Caro entre caros",
    "bajo-bajo": "Barato entre baratos",
    "alto-bajo": "Caro entre baratos",
    "bajo-alto": "Barato entre caros",
    "no significativo": "Sin patrón local",
  };

  function cuantiles(valores, n) {
    const s = valores.filter((v) => v != null && !isNaN(v)).sort(d3.ascending);
    return d3.range(n + 1).map((i) => d3.quantile(s, i / n));
  }

  const CAPAS = {
    precio: {
      titulo: "El precio del metro cuadrado",
      sub: "Mediana del precio pedido en celdas hexagonales de 174 m de arista",
      campo: "precio_m2",
      construir() {
        const cortes = cuantiles(celdas.map((c) => c.p.precio_m2), 7);
        const escala = d3.scaleThreshold().domain(cortes.slice(1, -1)).range(RAMPA);
        return {
          color: (p) => (p.precio_m2 == null ? leerVar("--sin-datos") : escala(p.precio_m2)),
          leyenda: RAMPA.map((c, i) => ({
            color: c,
            texto: `${pesos(cortes[i])} a ${pesos(cortes[i + 1])}`,
          })).concat([{ color: leerVar("--sin-datos"), texto: "Sin avisos" }]),
          titulo: "pesos por m²",
        };
      },
    },

    cobertura: {
      titulo: "Dónde llega el mercado formal",
      sub: "Avisos publicados por cada mil viviendas censadas. Es la capa del hallazgo",
      campo: "cobertura",
      construir() {
        const cortes = [0, 5, 15, 35, 70, 150];
        const escala = d3.scaleThreshold().domain(cortes.slice(1)).range(RAMPA_CALIDA);
        return {
          color: (p) =>
            !p.avisos ? leerVar("--sin-datos") : escala(p.cobertura ?? 0),
          leyenda: [{ color: leerVar("--sin-datos"), texto: "Ningún aviso publicado" }].concat(
            RAMPA_CALIDA.map((c, i) => ({
              color: c,
              texto:
                i === RAMPA_CALIDA.length - 1
                  ? `más de ${cortes[i]}`
                  : `${cortes[i]} a ${cortes[i + 1]}`,
            }))
          ),
          titulo: "avisos por mil viviendas",
        };
      },
    },

    sobreprecio: {
      titulo: "Cuánto cuesta la ubicación",
      sub: "Lo que el precio supera a lo que predicen los atributos del inmueble",
      campo: "sobreprecio",
      construir() {
        const vals = celdas.map((c) => c.p.sobreprecio).filter((v) => v != null);
        const tope = d3.quantile(vals.map(Math.abs).sort(d3.ascending), 0.95) || 30;
        const escala = d3
          .scaleLinear()
          .domain([-tope, 0, tope])
          .range([leerVar("--polo-bajo"), leerVar("--arena-2"), leerVar("--polo-alto")])
          .clamp(true);
        return {
          color: (p) => (p.sobreprecio == null ? leerVar("--sin-datos") : escala(p.sobreprecio)),
          leyenda: [
            { color: leerVar("--polo-alto"), texto: `hasta +${Math.round(tope)} %` },
            { color: leerVar("--arena-2"), texto: "en línea con sus atributos" },
            { color: leerVar("--polo-bajo"), texto: `hasta −${Math.round(tope)} %` },
            { color: leerVar("--sin-datos"), texto: "Sin dato" },
          ],
          titulo: "sobreprecio de la celda",
        };
      },
    },

    conglomerado: {
      titulo: "El precio está agrupado, no disperso",
      sub: "Conglomerados locales, significativos al 5 % por permutaciones",
      campo: "conglomerado",
      construir: () => ({
        color: (p) => LISA[p.conglomerado] || leerVar("--sin-datos"),
        leyenda: Object.entries(ETIQUETA_LISA)
          .map(([k, v]) => ({ color: LISA[k], texto: v }))
          .concat([{ color: leerVar("--sin-datos"), texto: "Sin avisos" }]),
        titulo: "tipo de conglomerado",
      }),
    },

    viviendas: {
      titulo: "La ciudad que hay debajo",
      sub: "Viviendas censadas por el DANE en cada celda, tenga avisos o no",
      campo: "viviendas",
      construir() {
        const cortes = cuantiles(celdas.map((c) => c.p.viviendas), 6);
        const escala = d3.scaleThreshold().domain(cortes.slice(1, -1)).range(RAMPA_CALIDA);
        return {
          color: (p) => (p.viviendas ? escala(p.viviendas) : leerVar("--sin-datos")),
          // La celda sin viviendas censadas se pinta con el gris de "sin dato" y
          // por tanto tiene que aparecer en la leyenda: si no, el mapa muestra
          // un color que la leyenda no explica.
          leyenda: RAMPA_CALIDA.map((c, i) => ({
            color: c,
            texto: `${miles(cortes[i])} a ${miles(cortes[i + 1])}`,
          })).concat([{ color: leerVar("--sin-datos"), texto: "Sin viviendas censadas" }]),
          titulo: "viviendas censadas",
        };
      },
    },
  };

  // ── mapa ───────────────────────────────────────────────────
  /* El mapa va sobre teselas reales, y esa es la diferencia con la versión
     anterior. Los hexágonos por sí solos dibujaban la silueta de la ciudad,
     pero no decían dónde estaba uno: sin calles ni nombres, una celda cara al
     sur podía ser El Poblado, Envigado o Sabaneta, y el lector no tenía cómo
     saberlo. Las teselas de CARTO, levantadas sobre OpenStreetMap, ponen ese
     contexto.

     Van en tres pisos y el orden importa:

       1. el terreno SIN rótulos, abajo;
       2. los hexágonos en medio, translúcidos;
       3. los rótulos otra vez ENCIMA.

     Si los rótulos fueran parte del fondo, el color del dato los taparía justo
     donde el dato es más intenso, que es donde más falta hace leer el nombre
     de la calle. Separándolos, la nomenclatura sobrevive al color. */

  /* Sobre la eleccion de proveedor, que costo un intento fallido.
     Las teselas de CARTO parecian la opcion evidente por estetica, y contestaban
     con codigo 200. Pero la imagen que devuelven lleva estampado 'API KEY
     REQUIRED': el servidor responde bien y entrega una tesela inservible. Un
     200 no dice que el contenido sirva, y comprobarlo solo con el codigo de
     respuesta dejo el mapa con marca de agua sin que ninguna prueba fallara.
     Se verificaron mirando los pixeles.

     Quedan dos que funcionan sin clave y traen nomenclatura completa: el mapa
     estandar de OpenStreetMap para el tema claro, y el lienzo oscuro de Esri
     para el tema oscuro, porque OpenStreetMap no publica version oscura. */
  const TESELAS = {
    claro: {
      url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
      credito: '<a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      maxZoom: 19,
    },
    oscuro: {
      url:
        "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/" +
        "World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
      credito: "Esri · HERE · Garmin · OpenStreetMap",
      maxZoom: 16,
    },
  };

  const esOscuro = () =>
    document.documentElement.dataset.tema === "oscuro" ||
    (!document.documentElement.dataset.tema &&
      matchMedia("(prefers-color-scheme: dark)").matches);

  // Capa activa y función de color en curso. La construye `pintar()` a partir
  // de la definición de la capa, y `estilo()` la consulta en cada repintado.
  let capaActual = "precio";
  let pintor = null;

  /* Las celdas se pasan tal cual vienen del GeoJSON.
     Aquí hubo que invertir el anillo mientras el mapa lo dibujaba d3-geo, que
     trabaja sobre la esfera y usa el convenio contrario al de la norma RFC 7946.
     Leaflet proyecta en el plano y no atiende al sentido de giro, así que esa
     inversión sobra: dejarla puesta no rompía nada, pero escondía de dónde
     venía el problema. */
  const coleccion = {
    type: "FeatureCollection",
    features: celdas.map((c) => ({
      type: "Feature",
      properties: c.p,
      geometry: { type: "Polygon", coordinates: [c.g] },
    })),
  };

  /* El encuadre se calcula sobre donde vive la gente, no sobre los extremos
     del municipio ni sobre donde hay avisos.

     Medellín incluye corregimientos rurales que se extienden mucho más allá del
     valle: ajustar a la extensión total dejaba el hexágono en cinco píxeles y la
     ciudad ilegible. Encuadrar por los avisos habría corregido eso, pero metería
     por la puerta de atrás justo el sesgo que esta página denuncia, porque los
     avisos se amontonan en el sur. Se pesa por viviendas censadas: entra el 97 %
     del parque, comunas populares incluidas, y quedan fuera los corregimientos.

     Las celdas de afuera se siguen dibujando; aparecen al alejar el zoom. */
  function limitesUtiles(recorte = 0.015) {
    const centros = celdas.map((c) => ({
      lon: d3.mean(c.g, (p) => p[0]),
      lat: d3.mean(c.g, (p) => p[1]),
      // El +1 evita que una celda con avisos y sin censo pese cero y desaparezca
      // del encuadre por completo.
      peso: (c.p.viviendas || 0) + 1,
    }));
    const total = d3.sum(centros, (c) => c.peso);

    // Cuantil ponderado: se ordena por la coordenada y se avanza acumulando
    // peso hasta cruzar la proporción buscada.
    const cuantil = (eje, p) => {
      const orden = centros.slice().sort((a, b) => a[eje] - b[eje]);
      let acumulado = 0;
      for (const c of orden) {
        acumulado += c.peso;
        if (acumulado / total >= p) return c[eje];
      }
      return orden[orden.length - 1][eje];
    };

    return L.latLngBounds(
      [cuantil("lat", recorte), cuantil("lon", recorte)],
      [cuantil("lat", 1 - recorte), cuantil("lon", 1 - recorte)]
    );
  }

  const mapa = L.map("mapa", {
    // La rueda no debe secuestrar el desplazamiento de la página: se habilita
    // solo cuando el lector hace clic dentro del mapa, y se suelta al salir.
    scrollWheelZoom: false,
    zoomSnap: 0.25,
    minZoom: 10,
    maxZoom: 17,
    renderer: L.svg({ padding: 0.3 }),
  });
  mapa.attributionControl.setPrefix("");
  mapa.fitBounds(limitesUtiles(), { padding: [6, 6] });

  let capaFondo = null;
  let avisadoSinRed = false;

  function ponerTeselas() {
    const t = TESELAS[esOscuro() ? "oscuro" : "claro"];
    if (capaFondo) mapa.removeLayer(capaFondo);

    capaFondo = L.tileLayer(t.url, {
      attribution: t.credito,
      maxZoom: t.maxZoom,
      // Por encima del zoom que sirve el proveedor, Leaflet estira la última
      // tesela disponible en vez de dejar el fondo en blanco.
      maxNativeZoom: t.maxZoom,
    }).addTo(mapa);

    /* Las teselas vienen de la red, y son lo único de esta página que la
       necesita. Sin conexión el mapa sigue siendo legible, porque los hexágonos
       dibujan la silueta, pero conviene decir por qué no hay calles en vez de
       dejar al lector pensando que algo se rompió. */
    capaFondo.on("tileerror", () => {
      if (avisadoSinRed) return;
      avisadoSinRed = true;
      document.getElementById("pista-mapa").textContent =
        "Sin conexión: el mapa base no cargó. Los hexágonos siguen dibujando la ciudad.";
    });
  }
  ponerTeselas();

  // ── celdas ─────────────────────────────────────────────────
  let opacidad = 0.68;
  let fijada = null;
  let clicEnCelda = false;

  function estilo(rasgo) {
    const p = rasgo.properties;
    const vacia = !p.avisos;
    return {
      fillColor: pintor ? pintor.color(p) : leerVar("--sin-datos"),
      /* Las celdas sin un solo aviso se dejan más transparentes a propósito.
         Debajo se ven las calles y las manzanas, así que se lee que ahí hay un
         barrio real del que no tenemos ni un dato, y no un hueco del mapa. */
      fillOpacity: vacia ? opacidad * 0.5 : opacidad,
      color: leerVar("--trazo-celda"),
      weight: 0.4,
      opacity: 0.5,
    };
  }

  function resaltar(capa) {
    capa.setStyle({ weight: 2.2, color: leerVar("--tinta"), opacity: 1 });
    capa.bringToFront();
  }

  const capaCeldas = L.geoJSON(coleccion, {
    style: estilo,
    smoothFactor: 0.3,
    onEachFeature: (rasgo, capa) => {
      capa.on({
        mouseover: () => {
          if (fijada) return;
          resaltar(capa);
          mostrarDetalle(rasgo.properties);
        },
        mouseout: () => {
          if (!fijada) capaCeldas.resetStyle(capa);
        },
        click: () => {
          clicEnCelda = true;
          if (fijada === capa) {
            soltar();
            return;
          }
          if (fijada) capaCeldas.resetStyle(fijada);
          fijada = capa;
          resaltar(capa);
          mostrarDetalle(rasgo.properties, true);
        },
      });
    },
  }).addTo(mapa);

  function soltar() {
    if (fijada) capaCeldas.resetStyle(fijada);
    fijada = null;
    detalleInicial();
  }

  /* El clic de la celda sube hasta el mapa. En vez de cortar la propagación,
     que en Leaflet obliga a manejar el evento original, se marca la bandera:
     la celda avisa de que ya atendió el clic y el mapa no deshace la fijación. */
  mapa.on("click", () => {
    mapa.scrollWheelZoom.enable();
    if (!clicEnCelda) soltar();
    clicEnCelda = false;
  });
  mapa.getContainer().addEventListener("mouseleave", () => {
    mapa.scrollWheelZoom.disable();
  });

  function pintar() {
    const capa = CAPAS[capaActual];
    pintor = capa.construir();
    capaCeldas.setStyle(estilo);
    if (fijada) resaltar(fijada);

    document.getElementById("mapa-titulo").textContent = capa.titulo;
    document.getElementById("mapa-sub").textContent = capa.sub;

    d3.select("#leyenda").html(
      `<div class="titulo">${pintor.titulo}</div><ul>` +
        pintor.leyenda
          .map(
            (l) =>
              `<li><span class="muestra" style="background:${l.color}"></span>${l.texto}</li>`
          )
          .join("") +
        "</ul>"
    );
  }

  function detalleInicial() {
    document.getElementById("detalle").innerHTML =
      '<div class="titulo">Señala una celda</div>' +
      '<div class="vacio">Cada hexágono cubre unos 174 m de lado. Al pasar el cursor' +
      " se muestran sus cifras, y al hacer clic quedan fijas.</div>";
  }

  function mostrarDetalle(p, fija = false) {
    const filas = [];
    const f = (rot, val) => filas.push(`<dt>${rot}</dt><dd>${val}</dd>`);

    if (p.avisos) {
      f("Avisos", miles(p.avisos));
      f("Precio mediano", pesos(p.precio_mediano));
      f("Por m²", pesos(p.precio_m2));
      if (p.area_mediana) f("Área mediana", `${Math.round(p.area_mediana)} m²`);
      if (p.sobreprecio != null) f("Sobreprecio", pctSig(p.sobreprecio));
      if (p.pct_amoblado != null) f("Amoblados", pct(p.pct_amoblado, 0));
    }
    f("Viviendas censadas", miles(p.viviendas));
    if (p.avisos) f("Avisos por mil", (p.cobertura ?? 0).toFixed(1).replace(".", ","));
    if (p.estrato_censo) f("Estrato del censo", p.estrato_censo);

    /* El título solo lleva barrio cuando de verdad lo hay. Antes se colaba aquí
       'Arriendo En', que no era un barrio sino el resto de una URL sin barrio
       mal troceada. Esas celdas se rotulan ahora por lo que son. */
    const titulo = p.barrio || (p.avisos ? "Celda con avisos" : "Zona sin avisos");
    const marca = fija ? '<span class="chincheta">fijada</span>' : "";
    const aviso = p.avisos
      ? ""
      : `<div class="vacio" style="margin-top:10px">Aquí viven ${miles(
          p.viviendas
        )} hogares y no se publicó ningún arriendo.</div>`;

    document.getElementById("detalle").innerHTML =
      `<div class="titulo">${titulo}${marca}</div>` +
      `<div class="tenue">${
        p.conglomerado ? ETIQUETA_LISA[p.conglomerado] : "celda de 174 m"
      }</div>` +
      `<dl>${filas.join("")}</dl>${aviso}`;
  }

  document.querySelectorAll(".capa").forEach((b) =>
    b.addEventListener("click", () => {
      document.querySelectorAll(".capa").forEach((o) => o.setAttribute("aria-pressed", "false"));
      b.setAttribute("aria-pressed", "true");
      capaActual = b.dataset.capa;
      pintar();
    })
  );

  // Deslizador de opacidad: sirve para contrastar contra la calle lo que dice
  // el dato, que es justo la pregunta que uno se hace al ver una celda cara.
  const deslizador = document.getElementById("opacidad");
  deslizador.addEventListener("input", () => {
    opacidad = +deslizador.value / 100;
    capaCeldas.setStyle(estilo);
    if (fijada) resaltar(fijada);
  });

  // ── gráficas de las secciones ──────────────────────────────

  function tarjeta(id, titulo, apunte, cuerpo) {
    document.getElementById(id).innerHTML =
      `<div class="tarjeta vidrio"><h2>${titulo}</h2><p class="apunte">${apunte}</p>${cuerpo}</div>`;
  }

  function lineas(datos, series, opciones = {}) {
    const an = 640,
      al = 260,
      m = { t: 14, d: 78, b: 34, i: 52 };
    const x = d3
      .scalePoint()
      .domain(datos.map(opciones.x))
      .range([m.i, an - m.d]);
    const todos = series.flatMap((s) => datos.map(s.y).filter((v) => v != null));
    const y = d3
      .scaleLinear()
      .domain([d3.min(todos) * 0.94, d3.max(todos) * 1.04])
      .range([al - m.b, m.t]);

    const eje = (v) =>
      `<line x1="${m.i}" x2="${an - m.d}" y1="${y(v)}" y2="${y(v)}" stroke="${leerVar(
        "--arena-3"
      )}" stroke-width="1"/>
       <text x="${m.i - 8}" y="${y(v) + 4}" text-anchor="end" font-size="10.5" fill="${leerVar(
        "--tinta-3"
      )}">${opciones.formatoY ? opciones.formatoY(v) : v}</text>`;

    const lineaG = d3
      .line()
      .defined((d, i, a) => a[i] != null)
      .x((d) => x(opciones.x(d)))
      .curve(d3.curveMonotoneX);

    const trazos = series
      .map((s) => {
        const g = lineaG.y((d) => y(s.y(d)))(datos.filter((d) => s.y(d) != null));
        const ult = datos[datos.length - 1];
        return `<path d="${g}" fill="none" stroke="${s.color}" stroke-width="2.4" stroke-linecap="round"/>
                <circle cx="${x(opciones.x(ult))}" cy="${y(s.y(ult))}" r="4" fill="${s.color}"/>
                <text x="${x(opciones.x(ult)) + 9}" y="${y(s.y(ult)) + 4}" font-size="11.5"
                      font-weight="600" fill="${leerVar("--tinta")}">${s.nombre}</text>`;
      })
      .join("");

    const marcas = y.ticks(4).map(eje).join("");
    const etiquetasX = datos
      .filter((d, i) => i % Math.ceil(datos.length / 6) === 0)
      .map(
        (d) =>
          `<text x="${x(opciones.x(d))}" y="${al - 10}" text-anchor="middle" font-size="10.5"
                 fill="${leerVar("--tinta-3")}">${opciones.etiquetaX(d)}</text>`
      )
      .join("");

    return `<svg viewBox="0 0 ${an} ${al}" style="width:100%;height:auto;margin-top:10px">${marcas}${trazos}${etiquetasX}</svg>`;
  }

  function barras(datos, opciones) {
    const an = 640,
      alFila = 21,
      m = { i: 150, d: 60, t: 6 };
    const al = datos.length * alFila + 24;
    const max = d3.max(datos, (d) => Math.abs(opciones.v(d)));
    const x = d3.scaleLinear().domain([-max, max]).range([m.i, an - m.d]);
    const cero = x(0);

    return (
      `<svg viewBox="0 0 ${an} ${al}" style="width:100%;height:auto;margin-top:10px">` +
      `<line x1="${cero}" x2="${cero}" y1="0" y2="${al - 16}" stroke="${leerVar(
        "--tinta-3"
      )}" stroke-width="1"/>` +
      datos
        .map((d, i) => {
          const v = opciones.v(d);
          const y = i * alFila + m.t;
          const ancho = Math.abs(x(v) - cero);
          const ix = v >= 0 ? cero : cero - ancho;
          const color = v >= 0 ? leerVar("--polo-alto") : leerVar("--polo-bajo");
          return `<rect x="${ix}" y="${y}" width="${ancho}" height="${alFila - 7}" rx="3" fill="${color}"/>
            <text x="${m.i - 10}" y="${y + 11}" text-anchor="end" font-size="11"
                  fill="${leerVar("--tinta-2")}">${opciones.n(d)}</text>
            <text x="${v >= 0 ? x(v) + 7 : x(v) - 7}" y="${y + 11}"
                  text-anchor="${v >= 0 ? "start" : "end"}" font-size="10.5" font-weight="600"
                  fill="${leerVar("--tinta")}">${pctSig(v)}</text>`;
        })
        .join("") +
      "</svg>"
    );
  }

  function construirSecciones() {
    // 1. El alza
    if (ipc.length) {
      const ult = ipc[ipc.length - 1];
      tarjeta(
        "seccion-alza",
        "Cuánto subió, y dónde se separa Medellín",
        "Un raspado da una fotografía de hoy. La magnitud del alza viene del índice de precios del DANE. El arriendo nacional viene desacelerando; Medellín hace lo contrario.",
        lineas(
          ipc,
          [
            {
              nombre: "Medellín",
              y: (d) => d.alojamiento_medellin_anual,
              color: leerVar("--serie-1"),
            },
            {
              nombre: "Nacional",
              y: (d) => d.alojamiento_nacional_anual,
              color: leerVar("--serie-2"),
            },
          ],
          {
            x: (d) => d.periodo,
            etiquetaX: (d) => String(d.periodo).slice(0, 7),
            formatoY: (v) => v.toFixed(0) + " %",
          }
        ) +
          `<p class="tenue" style="margin-top:6px">Variación anual del IPC, división de alojamiento.
           La brecha con el país pasó de −0,09 a +2,02 puntos porcentuales.</p>`
      );
    }

    // 2. Sobreprecio por barrio
    if (barrios.length) {
      const orden = barrios.slice().sort((a, b) => b.sobreprecio_pct - a.sobreprecio_pct);
      const sel = orden.slice(0, 9).concat(orden.slice(-9));
      tarjeta(
        "seccion-ubicacion",
        "Cuánto vale la ubicación",
        `Sobreprecio de cada barrio sobre lo que predicen área, alcobas, baños, estrato y
         amenidades. El modelo se estima sin efectos de barrio, porque con ellos dentro el
         residual valdría cero por construcción. La banda va de
         ${pctSig(modelo.barrio_mas_caro.sobreprecio)} en ${modelo.barrio_mas_caro.barrio} a
         ${pctSig(modelo.barrio_mas_barato.sobreprecio)} en ${modelo.barrio_mas_barato.barrio}.`,
        barras(sel, { n: (d) => d.barrio, v: (d) => d.sobreprecio_pct })
      );
    }

    // 3. Renta corta
    if (turismo.length) {
      const med = turismo.filter((d) => d.ciudad === "Medellin");
      const bog = turismo.filter((d) => d.ciudad === "Bogota");
      const porAnio = med.map((d) => ({
        anio: d.anio,
        med: d.viviendas_turisticas,
        bog: (bog.find((b) => b.anio === d.anio) || {}).viviendas_turisticas,
      }));
      tarjeta(
        "seccion-turismo",
        "La presión de la renta corta",
        "InsideAirbnb ya no cubre Medellín. La alternativa es el Registro Nacional de Turismo, obligatorio para toda vivienda que se alquile a turistas.",
        lineas(
          porAnio,
          [
            { nombre: "Medellín", y: (d) => d.med, color: leerVar("--serie-1") },
            { nombre: "Bogotá", y: (d) => d.bog, color: leerVar("--serie-2") },
          ],
          { x: (d) => d.anio, etiquetaX: (d) => d.anio, formatoY: miles }
        ) +
          `<p class="tenue" style="margin-top:6px">Las viviendas turísticas registradas en Medellín
           pasaron de 521 en 2019 a 8.766 en 2024: se multiplicaron por 16,8 y hoy equivalen al
           0,94 % del parque de vivienda. Los barrios con más oferta amoblada muestran mayor
           sobreprecio de ubicación, con una correlación de rangos de
           +${decimal(modelo.correlacion_amoblado, 3)} sobre ${miles(barrios.length)} barrios.
           Es asociación, no causa.</p>`
      );
    }

    // 4. Qué encarece
    // Solo los efectos significativos al 5 %: dibujar una barra para un
    // coeficiente que no se distingue de cero invita a leerla como si dijera
    // algo, y no lo dice.
    const EFECTOS = (modelo.efectos || [])
      .filter((e) => e.significativo)
      .map((e) => ({ n: e.nombre.replace("bano", "baño").replace("Porteria", "Portería")
                       .replace("antiguedad", "antigüedad"), v: e.efecto }));
    const elasticidad = modelo.elasticidad_area || 0;
    const noSignificativos = (modelo.efectos || []).filter((e) => !e.significativo).length;

    tarjeta(
      "seccion-modelo",
      "Qué encarece un arriendo",
      `Efecto de cada atributo sobre el precio, con todo lo demás constante. El área
       entra en logaritmo y no aparece aquí: su coeficiente es una elasticidad de
       ${decimal(elasticidad, 3)}, es decir que un inmueble 10 % más grande cuesta
       ${decimal(elasticidad * 10, 1)} % más.`,
      barras(EFECTOS, { n: (d) => d.n, v: (d) => d.v }) +
        `<p class="tenue" style="margin-top:6px">Se muestran los ${EFECTOS.length} atributos
         significativos al 5 %. Otros ${noSignificativos} —piscina, ascensor, zonas verdes y
         el número de alcobas una vez fijada el área— no se distinguen de cero.</p>`
    );
  }

  // ── tema ───────────────────────────────────────────────────
  const btnTema = document.getElementById("tema");
  btnTema.addEventListener("click", () => {
    document.documentElement.dataset.tema = esOscuro() ? "claro" : "oscuro";
    // Las gráficas leen los colores del tema al construirse, de modo que hay
    // que rehacerlas; no basta con repintar el mapa. Las teselas también
    // cambian de juego, porque el mapa base tiene su propia versión oscura.
    ponerTeselas();
    pintar();
    construirSecciones();
  });

  // ── aparición al desplazar ─────────────────────────────────
  const observador = new IntersectionObserver(
    (entradas) =>
      entradas.forEach((e) => e.isIntersecting && e.target.classList.add("visible")),
    { threshold: 0.06 }
  );
  document.querySelectorAll(".aparece").forEach((e) => observador.observe(e));

  // ── arranque ───────────────────────────────────────────────
  detalleInicial();
  pintar();
  construirSecciones();

  // Leaflet mide el contenedor al crearse. Si la ventana cambia de tamaño hay
  // que decírselo, o el mapa se queda con las medidas viejas y las teselas
  // aparecen recortadas.
  addEventListener("resize", () => mapa.invalidateSize());
})();
