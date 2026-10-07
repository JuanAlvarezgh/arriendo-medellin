"""Tablero del analisis de arriendos de Medellin.

Es la herramienta de trabajo sobre los datos: filtrar, ordenar, mirar una tabla
entera. El relato terminado, con el mapa de la ciudad sobre el callejero, vive
aparte en `datos/salidas/web/arriendos_medellin.html`; aqui se enlaza pero no se
duplica.

Comparte el lenguaje visual de esa pagina a traves de `analisis/estilo.py`, de
modo que las dos se reconozcan como el mismo proyecto.

    streamlit run analisis/tablero.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Streamlit ejecuta este archivo como guion suelto y pone en la ruta de busqueda
# la carpeta del archivo, no la raiz del proyecto. Sin esto, `import analisis`
# falla cuando el tablero se abre con `streamlit run`, aunque funcione al
# importarlo desde la raiz. Se anade la raiz antes de cualquier import propio.
RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import json

import pandas as pd
import streamlit as st

from analisis.cifras import cargar as cargar_cifras
from analisis.estilo import aplicar, barra_proporcion, encabezado, paleta, panel

aplicar("Arriendos en Medellin", icono=":material/home_work:")

# Las cifras del estudio, leidas del resumen que escribe `analisis.graficos`.
# Estuvieron escritas a mano aqui, y quedaron obsoletas cuando el modelo cambio.
C = cargar_cifras()

SALIDAS = RAIZ / "datos" / "salidas"
FIGURAS = SALIDAS / "figuras"
CRUDO = RAIZ / "datos" / "crudo"
PAGINA = SALIDAS / "web" / "arriendos_medellin.html"


# --- carga ---


@st.cache_data(show_spinner="Cargando avisos...")
def cargar_avisos() -> pd.DataFrame:
    """Prefiere el parquet enriquecido; si no esta, lee los jsonl."""
    enriquecido = SALIDAS / "geo_enriquecido.parquet"
    if enriquecido.exists():
        df = pd.read_parquet(enriquecido)
    else:
        registros = []
        for arch in sorted(CRUDO.glob("*.jsonl")):
            with arch.open(encoding="utf-8") as fh:
                for linea in fh:
                    linea = linea.strip()
                    if linea.startswith("{"):
                        try:
                            registros.append(json.loads(linea))
                        except json.JSONDecodeError:
                            continue
        if not registros:
            return pd.DataFrame()
        df = pd.DataFrame(registros).drop_duplicates(subset=["portal", "id_fuente"])

    df["area"] = df["area_privada"].fillna(df.get("area_construida"))
    df = df[df["precio"].notna() & df["area"].notna() & (df["area"] > 0)]
    df["precio_m2"] = df["precio"] / df["area"]

    def limpio(v) -> bool:
        try:
            return len(v) == 0
        except TypeError:
            return not bool(v)

    if "sospechoso" in df.columns:
        df = df[df["sospechoso"].apply(limpio)]

    if "amenidades" in df.columns:
        from analisis.hedonico import tiene_amenidad

        df["amoblado"] = df["amenidades"].apply(lambda v: int(tiene_amenidad(v, "amoblado")))
    return df


@st.cache_data
def cargar_csv(nombre: str) -> pd.DataFrame:
    ruta = SALIDAS / nombre
    return pd.read_csv(ruta) if ruta.exists() else pd.DataFrame()


# --- formato ---


def miles(v) -> str:
    """Separador de miles a la colombiana.

    Aplicar .replace(",", ".") sobre la frase entera, y no solo sobre el numero,
    se comia tambien las comas de la redaccion.
    """
    return f"{v:,.0f}".replace(",", ".")


def decimal(v, dec: int = 1) -> str:
    return f"{v:.{dec}f}".replace(".", ",")


def pesos(v: float, dec: int = 0) -> str:
    return ("$" + f"{v:,.{dec}f}").replace(",", "@").replace(".", ",").replace("@", ".")


def puntos(v: float) -> str:
    """Puntos porcentuales con signo tipografico."""
    return ("+" if v >= 0 else "−") + decimal(abs(v)) + " pp"


def figura(nombre: str) -> None:
    ruta = FIGURAS / nombre
    if not ruta.exists():
        ruta = SALIDAS / nombre
    if ruta.exists():
        st.image(str(ruta), use_container_width=True)
    else:
        st.info(
            f"Falta la figura {nombre}. Genérala con `python -m analisis.graficos`.",
            icon=":material/image_not_supported:",
        )


def mapa_html(nombre: str, alto: int = 620) -> None:
    ruta = SALIDAS / nombre
    if not ruta.exists():
        st.info(
            f"Falta {nombre}. Genéralo con `python -m analisis.mapas`.",
            icon=":material/map:",
        )
        return
    st.components.v1.html(ruta.read_text(encoding="utf-8"), height=alto, scrolling=False)


def nota(texto: str) -> None:
    st.markdown(f'<p class="nota-pie">{texto}</p>', unsafe_allow_html=True)


df = cargar_avisos()
if df.empty:
    st.error(
        "No hay avisos. Corre primero `python -m rastreador.cli raspar --portal fincaraiz`.",
        icon=":material/error:",
    )
    st.stop()

P = paleta()


# --- cabecera ---

encabezado(
    "Por qué subió el precio de los arriendos",
    f"{miles(len(df))} avisos con coordenadas, de {df['portal'].nunique()} portales. "
    "Son precios pedidos, no pactados.",
    etiqueta="Análisis de datos · Medellín",
)

tabs = st.tabs(
    [
        "Resumen",
        "El alza",
        "Dónde está caro",
        "Qué lo encarece",
        "La ubicación",
        "Conglomerados",
        "Renta corta",
        "Explorador",
    ]
)


# --- 1. Resumen ---

with tabs[0]:
    # Las métricas ya son tarjetas de cristal: envolverlas además en un panel
    # apila dos cristales y ensucia la superficie. El panel se reserva para los
    # bloques que agrupan cosas de distinta naturaleza.
    c = st.columns(4)
    c[0].metric("Avisos", miles(len(df)))
    c[1].metric("Precio mediano", pesos(df["precio"].median()))
    c[2].metric("Por m²", pesos(df["precio_m2"].median()))
    c[3].metric("Barrios", miles(df["barrio"].nunique()))

    c = st.columns(4)
    c[0].metric("Ajuste del modelo", C.r2, help="R cuadrado ajustado del modelo hedónico")
    c[1].metric(
        "I de Moran",
        C.moran,
        help=f"Autocorrelación espacial de los residuales, p = {C.moran_p}",
    )
    c[2].metric(
        "Banda de ubicación",
        f"{C.banda} pp",
        help=f"De {C.sobreprecio_caro} en {C.barrio_caro} a "
        f"{C.sobreprecio_barato} en {C.barrio_barato}",
    )
    c[3].metric(
        "Parque sin un aviso",
        C.pct_sin_datos,
        help=f"{C.viviendas_sin_avisos} viviendas censadas en celdas sin oferta publicada",
    )

    st.subheader("Los cuatro hallazgos")
    izq, der = st.columns(2, gap="medium")
    with izq:
        with panel():
            st.markdown(
                f"""
**El alza es real y Medellín tiene ritmo propio.** El arriendo nacional acumuló
10,5 % en dos años mientras desaceleraba. Medellín se desacopló a mediados de
2025 y hoy corre dos puntos por encima del país.
"""
            )
        with panel():
            st.markdown(
                f"""
**Los atributos explican mucho, pero no la diferencia entre barrios.** El modelo
captura el {C.r2} de la varianza. Aun así quedan {C.banda} puntos porcentuales
entre {C.barrio_caro} y {C.barrio_barato}, a igualdad de inmueble.
"""
            )
    with der:
        with panel():
            st.markdown(
                f"""
**El mercado está segmentado en el espacio.** La autocorrelación espacial es
significativa y el parámetro del modelo espacial llega a {C.lambda_espacial}. Los
precios forman zonas con bordes reconocibles, no puntos dispersos.
"""
            )
        with panel():
            st.markdown(
                f"""
**Y hay una parte de la ciudad que no aparece.** El {C.pct_sin_datos} del parque
de vivienda no tiene un solo aviso publicado. Todo lo demás describe el mercado
formal e intermediado, no su totalidad.
"""
            )

    with panel():
        st.markdown(
            "**El informe completo, con el mapa de la ciudad sobre el callejero**, "
            "es un archivo que se abre con doble clic:"
        )
        st.code(str(PAGINA), language=None)
        if not PAGINA.exists():
            nota("Todavía no está generado. Créalo con `python -m analisis.pagina`.")

    with st.expander("Qué no dice este trabajo"):
        st.markdown(
            """
- Son **precios pedidos**, no pactados.
- Es **un corte transversal** enriquecido con una serie oficial, no un panel propio.
- Los avisos **no son una muestra aleatoria**: sobrerrepresentan la oferta formal.
  Medido contra el censo, el estrato 6 aparece trece veces más representado que el 1.
- Las relaciones son **asociaciones, no efectos causales**.
- La serie del DANE para Medellín es de la división de alojamiento completa,
  que incluye servicios públicos, no de la subclase de arriendo.
"""
        )


# --- 2. El alza ---

with tabs[1]:
    st.subheader("Cuánto subió, y dónde se separa Medellín")
    st.markdown(
        "El raspado da una fotografía de hoy. La magnitud del alza viene del índice "
        "de precios del DANE, subclase **04130100, arriendo efectivo**."
    )

    ipc = cargar_csv("ipc_arriendo_dane.csv")
    if not ipc.empty:
        # Las tres cifras salen de la serie, no de una nota tomada al mirarla.
        primero, ultimo = ipc.iloc[0], ipc.iloc[-1]
        acumulado = 100 * (ultimo["indice_arriendo"] / primero["indice_arriendo"] - 1)
        med, nac = ultimo["alojamiento_medellin_anual"], ultimo["alojamiento_nacional_anual"]
        minimo_med = ipc["alojamiento_medellin_anual"].min()

        c = st.columns(4)
        c[0].metric(
            f"Acumulado nacional, {len(ipc)} meses",
            "+" + decimal(acumulado) + " %",
            help="Índice de arriendo efectivo, subclase 04130100",
        )
        c[1].metric(
            "Variación anual nacional",
            decimal(nac) + " %",
            puntos(nac - ipc.iloc[0]["alojamiento_nacional_anual"]),
        )
        c[2].metric(
            "Alojamiento en Medellín",
            decimal(med) + " %",
            puntos(med - minimo_med),
            help="Frente a su propio mínimo de la serie",
        )
        c[3].metric(
            "Brecha con el país",
            puntos(med - nac),
            puntos((med - nac) - (ipc.iloc[0]["alojamiento_medellin_anual"] - ipc.iloc[0]["alojamiento_nacional_anual"])),
        )

    figura("ipc_divergencia_medellin.png")

    if not ipc.empty:
        with st.expander("Ver la serie mensual"):
            st.dataframe(ipc, hide_index=True, use_container_width=True)


# --- 3. Donde esta caro ---

with tabs[2]:
    st.subheader("Dónde cuesta el metro cuadrado")
    st.markdown(
        "Rejilla hexagonal de 174 metros de arista. Se usan hexágonos y no barrios "
        "porque los barrios tienen tamaños muy dispares, y comparar medianas entre "
        "unidades desiguales confunde el precio con el tamaño de la unidad."
    )
    vista = st.radio(
        "Vista",
        ["Mapa interactivo", "Figura del informe"],
        horizontal=True,
        label_visibility="collapsed",
    )
    if vista == "Mapa interactivo":
        mapa_html("mapa_hexagonos.html")
        nota(
            "Este mapa solo dibuja celdas con avisos. El mapa completo, que incluye "
            "las zonas sin un solo aviso y las otras cuatro capas, está en la página "
            "del informe."
        )
    else:
        figura("02_mapa_hexagonos.png")


# --- 4. Que lo encarece ---

with tabs[3]:
    st.subheader("Qué encarece un arriendo, y cuánto")
    st.markdown(
        f"Modelo hedónico sobre {C.avisos_modelo} avisos de los últimos 90 días. "
        "Cada efecto es el del atributo **con todo lo demás constante**."
    )
    figura("03_efectos_hedonicos.png")
    st.info(
        f"El área entra en logaritmo, así que su coeficiente es una **elasticidad de "
        f"{C.elasticidad}**: un inmueble 10 % más grande cuesta {C.elasticidad_por_diez} "
        "más, no 10 % más. Que sea menor que uno significa que el precio por metro "
        "cuadrado disminuye con el tamaño.",
        icon=":material/functions:",
    )

    st.subheader("Cómo se distribuye el precio")
    figura("01_distribucion.png")


# --- 5. La ubicacion ---

with tabs[4]:
    st.subheader("Cuánto cuesta la ubicación, descontados los atributos")
    st.markdown(
        f"Si dos apartamentos tienen la misma área, alcobas, estrato y amenidades pero "
        f"uno cuesta más, esa diferencia no la explica el inmueble: la explica dónde "
        f"está. La banda va de **{C.sobreprecio_caro} en {C.barrio_caro}** a "
        f"**{C.sobreprecio_barato} en {C.barrio_barato}**."
    )
    figura("04_sobreprecio_barrios.png")

    sp = cargar_csv("sobreprecio_por_barrio.csv")
    if not sp.empty:
        st.subheader(f"Los {len(sp)} barrios con muestra suficiente")
        tabla = sp[["barrio", "avisos", "sobreprecio_pct", "precio_m2_mediano"]].copy()
        tabla.columns = ["Barrio", "Avisos", "Sobreprecio %", "Precio por m²"]
        st.dataframe(
            tabla.round(1).sort_values("Sobreprecio %", ascending=False),
            hide_index=True,
            use_container_width=True,
            height=420,
            column_config={
                "Sobreprecio %": st.column_config.NumberColumn(format="%.1f %%"),
                "Precio por m²": st.column_config.NumberColumn(format="$%d"),
            },
        )
        nota("Solo barrios con veinticinco avisos o más en la ventana del modelo.")

    with st.expander("Ver el mapa de sobreprecio"):
        mapa_html("mapa_sobreprecio.html", alto=560)


# --- 6. Conglomerados ---

with tabs[5]:
    st.subheader("El precio está agrupado, no disperso")
    st.markdown(
        f"El índice de Moran sobre los residuales del modelo da **{C.moran} con "
        f"p = {C.moran_p}**, por 999 permutaciones. El precio de un inmueble depende "
        "del de sus vecinos por encima de lo que explican sus atributos."
    )

    # Los conteos salen del archivo que produce el analisis, no de una nota
    # tomada al mirarlo una vez.
    cong = cargar_csv("conglomerados.csv")
    conteo = cong["conglomerado"].value_counts() if not cong.empty else pd.Series(dtype=int)

    with panel():
        c = st.columns(4)
        c[0].metric("Caro entre caros", miles(conteo.get("alto-alto", 0)))
        c[1].metric("Barato entre baratos", miles(conteo.get("bajo-bajo", 0)))
        c[2].metric(
            "Bordes de transición",
            miles(conteo.get("bajo-alto", 0) + conteo.get("alto-bajo", 0)),
            help="Caro entre baratos, o barato entre caros",
        )
        c[3].metric(
            "λ del modelo espacial",
            C.lambda_espacial,
            help="Dependencia espacial del error: cuánto de lo no explicado en un "
            "inmueble se explica por lo no explicado en sus vecinos",
        )

        if not conteo.empty:
            etiquetas = {
                "alto-alto": "Caro entre caros",
                "bajo-bajo": "Barato entre baratos",
                "alto-bajo": "Caro entre baratos",
                "bajo-alto": "Barato entre caros",
                "no significativo": "Sin patrón local",
            }
            colores = {
                "alto-alto": P["serie_1"],
                "bajo-bajo": P["alerta"],
                "alto-bajo": P["arcilla"],
                "bajo-alto": P["serie_2"],
                "no significativo": P["tinta_3"],
            }
            st.markdown(
                barra_proporcion(
                    [
                        (etiquetas[k], int(conteo.get(k, 0)), colores[k])
                        for k in etiquetas
                        if conteo.get(k, 0)
                    ]
                ),
                unsafe_allow_html=True,
            )

    vista = st.radio(
        "Vista",
        ["Figura del informe", "Mapa interactivo"],
        horizontal=True,
        label_visibility="collapsed",
        key="lisa",
    )
    if vista == "Figura del informe":
        figura("05_conglomerados.png")
    else:
        mapa_html("mapa_conglomerados.html")


# --- 7. Renta corta ---

with tabs[6]:
    st.subheader("La presión de la renta corta")
    st.markdown(
        "InsideAirbnb ya no cubre Medellín: de Colombia solo publica Bogotá. La "
        "alternativa es el **Registro Nacional de Turismo**, obligatorio para toda "
        "vivienda que se alquile a turistas."
    )

    rnt = cargar_csv("rnt_viviendas_turisticas.csv")
    med = rnt[rnt["ciudad"] == "Medellin"].sort_values("anio") if not rnt.empty else pd.DataFrame()
    if not med.empty:
        primero = med.iloc[0]
        pico = med.loc[med["viviendas_turisticas"].idxmax()]
        ultimo = med.iloc[-1]
        c = st.columns(4)
        c[0].metric(f"Viviendas turísticas, {int(primero['anio'])}", miles(primero["viviendas_turisticas"]))
        c[1].metric(
            f"Máximo, en {int(pico['anio'])}",
            miles(pico["viviendas_turisticas"]),
            f"×{pico['viviendas_turisticas'] / primero['viviendas_turisticas']:.1f}".replace(".", ","),
        )
        c[2].metric(f"Último dato, {int(ultimo['anio'])}", miles(ultimo["viviendas_turisticas"]))
        c[3].metric("Del parque de vivienda", "0,94 %", help="Sobre el censo del DANE")
        nota(
            "El registro se renueva cada año, así que el último dato puede estar "
            "incompleto: el crecimiento se lee del recorrido, no del último punto."
        )

    figura("07_vivienda_turistica.png")

    st.divider()
    st.subheader("Y dónde se concentra")
    if "amoblado" in df.columns:
        st.markdown(
            "El registro no publica direcciones. La dimensión espacial sale de los "
            f"propios avisos: el **{decimal(100 * df['amoblado'].mean())} %** declara "
            f"estar amoblado, y la correlación de rangos entre oferta amoblada y "
            f"sobreprecio del barrio es de **{C.correlacion_amoblado}** sobre "
            f"{C.barrios} barrios."
        )
    figura("08_amoblados_sobreprecio.png")
    st.warning(
        "El modelo ya controla si **cada inmueble** está amoblado, así que lo que se "
        "mide es un efecto de entorno: estar en un barrio con mucha oferta amoblada "
        "encarece también a los que no lo están. Es **asociación, no causa "
        "demostrada**: la dirección podría ser la contraria.",
        icon=":material/warning:",
    )


# --- 8. Explorador ---

with tabs[7]:
    st.subheader("Explorador de avisos")

    with panel():
        f1, f2, f3 = st.columns([2, 1, 1])
        barrios = sorted(b for b in df["barrio"].dropna().unique())
        elegidos = f1.multiselect("Barrio", barrios, default=[])
        tipos = sorted(df["tipo_inmueble"].dropna().unique())
        tipos_sel = f2.multiselect("Tipo", tipos, default=tipos)
        solo_amoblados = f3.selectbox("Amoblado", ["Todos", "Solo amoblados", "Sin amoblar"])

        g1, g2 = st.columns(2)
        estratos = sorted(int(e) for e in df["estrato"].dropna().unique())
        rango_e = (
            g1.select_slider("Estrato", options=estratos, value=(min(estratos), max(estratos)))
            if len(estratos) > 1
            else (1, 6)
        )
        tope = int(df["precio"].quantile(0.99))
        rango_p = g2.slider(
            "Precio mensual",
            int(df["precio"].min()),
            tope,
            (int(df["precio"].min()), tope),
            step=100_000,
        )

    d = df.copy()
    if elegidos:
        d = d[d["barrio"].isin(elegidos)]
    if tipos_sel:
        d = d[d["tipo_inmueble"].isin(tipos_sel)]
    d = d[d["estrato"].between(*rango_e) | d["estrato"].isna()]
    d = d[d["precio"].between(*rango_p)]
    if "amoblado" in d.columns and solo_amoblados != "Todos":
        d = d[d["amoblado"] == (1 if solo_amoblados == "Solo amoblados" else 0)]

    if d.empty:
        st.warning("Ningún aviso cumple los filtros.", icon=":material/filter_alt_off:")
        st.stop()

    with panel():
        c = st.columns(5)
        c[0].metric("Avisos", miles(len(d)))
        c[1].metric("Precio mediano", pesos(d["precio"].median()))
        c[2].metric("Por m²", pesos(d["precio_m2"].median()))
        c[3].metric("Área mediana", f"{d['area'].median():.0f} m²")
        if "amoblado" in d.columns:
            c[4].metric("Amoblados", f"{100 * d['amoblado'].mean():.0f} %")

    izq, der = st.columns([3, 2], gap="medium")
    with izq:
        mapa = (
            d[["latitud", "longitud"]]
            .dropna()
            .rename(columns={"latitud": "lat", "longitud": "lon"})
        )
        if not mapa.empty:
            from analisis.mapas import puntos_html

            st.components.v1.html(
                puntos_html(mapa["lat"], mapa["lon"], P["terracota"]), height=520, scrolling=False
            )
    with der:
        por_barrio = (
            d[d["barrio"].notna()]
            .groupby("barrio")
            .agg(avisos=("precio", "size"), precio_m2=("precio_m2", "median"))
            .query("avisos >= 5")
            .sort_values("precio_m2", ascending=False)
        )
        if not por_barrio.empty:
            # Tabla con barra y no `st.bar_chart`: la gráfica de barras ordena
            # el eje de categorías alfabéticamente, de modo que un ranking de
            # los más caros salía en orden de la A a la Z, que es exactamente
            # lo que un ranking no debe hacer.
            st.dataframe(
                por_barrio.head(15).reset_index(),
                hide_index=True,
                use_container_width=True,
                height=360,
                column_config={
                    "barrio": st.column_config.TextColumn("Barrio"),
                    "avisos": st.column_config.NumberColumn("Avisos", width="small"),
                    "precio_m2": st.column_config.ProgressColumn(
                        "Precio por m²",
                        format="$%d",
                        min_value=0,
                        max_value=float(por_barrio["precio_m2"].max()),
                    ),
                },
            )
        else:
            nota("Ningún barrio del filtro llega a cinco avisos.")

    columnas = [
        c
        for c in [
            "barrio", "tipo_inmueble", "precio", "area", "precio_m2",
            "alcobas", "banos", "estrato", "piso", "url",
        ]
        if c in d.columns
    ]
    st.dataframe(
        d[columnas].sort_values("precio_m2", ascending=False).round(0),
        hide_index=True,
        use_container_width=True,
        height=380,
        column_config={
            "url": st.column_config.LinkColumn("Aviso", display_text="ver"),
            "precio": st.column_config.NumberColumn("Precio", format="$%d"),
            "precio_m2": st.column_config.NumberColumn("Por m²", format="$%d"),
            "area": st.column_config.NumberColumn("Área", format="%d m²"),
        },
    )
