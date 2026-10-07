/* Mapa base común de todo el sitio, sobre MapLibre GL.

   Por qué MapLibre y no Leaflet. Se midió en Chromium con la GPU del equipo y los
   17.178 avisos reales, haciendo zoom con la rueda:

     Leaflet (lienzo) con redibujo por cuadro   25 FPS   26 tirones de más de 50 ms
     Leaflet (lienzo) sin tocar                 48 FPS    6 tirones, y los puntos se inflan
     Leaflet.glify (WebGL)                      60 FPS    0 tirones, pero se inflan igual
     deck.gl                                    60 FPS    0 tirones, tamaño fijo
     MapLibre GL                                60 FPS    0 tirones, tamaño fijo

   Leaflet anima el zoom estirando con CSS la capa de puntos como una foto, y con
   tantos puntos no hay forma barata de evitarlo. MapLibre dibuja el mapa entero en
   la tarjeta gráfica en cada cuadro, así que el zoom es continuo y el radio de un
   círculo se queda en los píxeles que se le digan. deck.gl también cumplía, pero
   pesa más y no trae ventanas emergentes ni controles de mapa.

   Fondo: la imagen satelital libre de Esri, la misma del tablero de incendios, con
   las referencias de calles y lugares encima. Esri sirve hasta el zoom 16; por
   encima MapLibre estira esa tesela en vez de dejar el fondo vacío. */
const MapaSatelite = (() => {
  const ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services/";
  const tesela = (ruta, atribucion) => ({
    type: "raster", tiles: [ESRI + ruta + "/MapServer/tile/{z}/{y}/{x}"], tileSize: 256, maxzoom: 16,
    ...(atribucion ? { attribution: atribucion } : {}),
  });

  const ESTILO = {
    version: 8,
    sources: {
      satelite: tesela("World_Imagery", "Esri, Maxar, Earthstar Geographics"),
      calles: tesela("Reference/World_Transportation"),
      lugares: tesela("Reference/World_Boundaries_and_Places", "Etiquetas &copy; Esri"),
    },
    layers: [
      { id: "satelite", type: "raster", source: "satelite" },
      { id: "calles", type: "raster", source: "calles", paint: { "raster-opacity": 0.55 } },
      { id: "lugares", type: "raster", source: "lugares" },
    ],
  };

  function crear(contenedor, opciones = {}) {
    return new maplibregl.Map({
      container: contenedor,
      style: ESTILO,
      maxZoom: 19,
      dragRotate: false,
      pitchWithRotate: false,
      touchPitch: false,
      ...opciones,
    });
  }

  /* Una capa de círculos de radio fijo en píxeles. Cada punto trae su color (c)
     y si es tenue (t: sin dato en esa capa). El punto bajo el cursor crece un
     poco y se rodea de oscuro, sin que su tamaño base dependa nunca del zoom.

     El orden de dibujo no va en `circle-sort-key`: con miles de valores distintos
     MapLibre reordena en cada nivel de zoom y el mapa da tirones (se midió: 22
     FPS con él, 60 sin él). Se da en el orden de los datos, que MapLibre respeta. */
  function capaPuntos(mapa, id, { radio = 2.5, radioTenue = 1.5, borde = 0.8, opacidad = 0.8 } = {}) {
    const encima = ["boolean", ["feature-state", "encima"], false];
    const tenue = ["==", ["get", "t"], 1];
    mapa.addSource(id, { type: "geojson", data: { type: "FeatureCollection", features: [] } });
    mapa.addLayer({
      id, type: "circle", source: id,
      paint: {
        "circle-color": ["get", "c"],
        "circle-radius": ["+", ["case", tenue, radioTenue, radio], ["case", encima, 1.5, 0]],
        "circle-opacity": ["case", tenue, 0.45, opacidad],
        "circle-stroke-color": ["case", encima, "#151515", "#ffffff"],
        "circle-stroke-width": ["case", encima, 1.6, tenue, 0, borde],
        "circle-stroke-opacity": 0.9,
      },
    });
  }

  /* Colección GeoJSON a partir de columnas; el id del rasgo es el índice del
     punto. Los tenues van primero para que los puntos con dato queden encima. */
  function rasgos(lat, lng, color, tenue = () => false) {
    const debajo = [], encima = [];
    for (let i = 0; i < lat.length; i++) {
      const t = tenue(i) ? 1 : 0;
      (t ? debajo : encima).push({
        type: "Feature", id: i,
        properties: { c: color(i), t },
        geometry: { type: "Point", coordinates: [lng[i], lat[i]] },
      });
    }
    return { type: "FeatureCollection", features: debajo.concat(encima) };
  }

  /* Cursor sobre los puntos: marca el de encima con feature-state y avisa con su
     índice. Funciona igual para cualquier capa de puntos del sitio. */
  function alPasar(mapa, id, { entra, sale }) {
    let actual = null;
    const soltar = () => {
      if (actual !== null) mapa.setFeatureState({ source: id, id: actual }, { encima: false });
      actual = null;
    };
    mapa.on("mousemove", id, (e) => {
      const i = e.features[0].id;
      if (i !== actual) {
        soltar();
        actual = i;
        mapa.setFeatureState({ source: id, id: i }, { encima: true });
      }
      mapa.getCanvas().style.cursor = "pointer";
      if (entra) entra(i, e);
    });
    mapa.on("mouseleave", id, () => {
      soltar();
      mapa.getCanvas().style.cursor = "";
      if (sale) sale();
    });
    return { marcar: (i) => { soltar(); if (i !== null) { actual = i; mapa.setFeatureState({ source: id, id: i }, { encima: true }); } } };
  }

  /* Girasol de Vogel: varios avisos geocodificados en la misma coordenada (el
     centro de un barrio o de un edificio) se reparten a pocos metros de su punto,
     para que no se tapen. Devuelve las coordenadas separadas y cuántos comparten. */
  function separar(lat, lng, metros = 8) {
    const n = lat.length, la = new Float64Array(n), ln = new Float64Array(n), pila = new Int32Array(n);
    const angulo = Math.PI * (3 - Math.sqrt(5)), grupos = new Map();
    for (let i = 0; i < n; i++) {
      const clave = lat[i] + "," + lng[i];
      if (!grupos.has(clave)) grupos.set(clave, []);
      grupos.get(clave).push(i);
    }
    for (const miembros of grupos.values()) {
      miembros.forEach((i, k) => {
        pila[i] = miembros.length;
        const r = metros * Math.sqrt(k), t = k * angulo;
        la[i] = lat[i] + (r * Math.cos(t)) / 111320;
        ln[i] = lng[i] + (r * Math.sin(t)) / (111320 * Math.cos((lat[i] * Math.PI) / 180));
      });
    }
    return { lat: la, lng: ln, pila };
  }

  /* Opacidad de una capa de puntos, de 0 a 1. Los tenues siguen un poco más
     claros que los demás, y el borde blanco acompaña para que no quede un aro
     brillante alrededor de un punto casi transparente. */
  function opacidad(mapa, id, valor) {
    if (!mapa.getLayer(id)) return;
    mapa.setPaintProperty(id, "circle-opacity", ["case", ["==", ["get", "t"], 1], valor * 0.55, valor]);
    mapa.setPaintProperty(id, "circle-stroke-opacity", Math.min(0.9, valor));
  }

  return { crear, capaPuntos, rasgos, alPasar, separar, opacidad };
})();
