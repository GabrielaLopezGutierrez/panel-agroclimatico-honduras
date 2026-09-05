"""Panel agroclimático de Honduras — app de Streamlit.

Lee el panel ya construido de `data/` y no toca la red. Punto de entrada del
despliegue: `streamlit run streamlit_app.py`.

Es un tablero: la pantalla la ocupan los datos y los controles. Todo lo
explicativo vive en la pestaña "Cómo leer". Fuera de ahí solo aparecen los
avisos que dependen de la selección, que no son contexto general sino una
advertencia sobre la cifra que se está mirando.

El nivel gobierna la navegación y va de lo general a lo particular: país,
departamento, municipio.

Transparencia: cada figura trae la descarga de **sus** datos, los que están
dibujados en ella. Una sola descarga por nivel no alcanzaba, porque las figuras
muestran cortes distintos —otra ventana, otro nivel de agregación, otra fuente— y
ninguna descarga podía corresponder a todas.
"""
from __future__ import annotations

import sys

import pandas as pd
import plotly.express as px
import streamlit as st

# --- Modulos locales obsoletos en memoria, antes de importarlos --------------
# Tras un despliegue, Streamlit Cloud puede reejecutar el script nuevo en un
# proceso que ya tiene importados los modulos locales viejos. Si el commit
# agrego un nombre, el `from app.controls import ...` de abajo falla con
# ImportError en la linea 26 y la app cae sin dibujar nada: paso de verdad dos
# veces, con `texts.SOURCE_MD` y con `OVERVIEW_SERIES`.
#
# El reintento que ya existia al final del archivo no alcanza para esto: solo
# cubre el AttributeError que ocurre dentro de `main()`, y aqui el error pasa
# al importar, antes de que nada de eso corra.
#
# Son dos mecanismos y cada uno cubre un caso que el otro no:
#
# 1. La purga de una vez por proceso atrapa el codigo que cambio sin cambiar de
#    nombre. Ahi no hay ImportError que avise: el modulo viejo importa igual y
#    la app correria en silencio con la version anterior.
# 2. El reintento atrapa el segundo despliegue en el mismo proceso, donde la
#    purga de arriba ya corrio y su bandera impide repetirla. Sin esto, la
#    segunda vez volvia a caer con el mismo ImportError.
#
# No se purga en cada rerun: eso recrearia las funciones de `st.cache_data` y
# el panel se releeria del disco en cada clic.
def _purgar_modulos_locales() -> None:
    for name in [n for n in list(sys.modules)
                 if n.split(".")[0] in ("app", "asis")]:
        sys.modules.pop(name, None)


if not getattr(sys, "_asis_modulos_purgados", False):
    sys._asis_modulos_purgados = True
    _purgar_modulos_locales()

for _intento in (1, 2):
    try:
        from app import texts                                    # noqa: E402
        from app.controls import (MAX_FRAMES, OVERVIEW_SERIES,   # noqa: E402
                                  Query, dekads, geojson, load, manifest,
                                  national, season_window_label, sidebar,
                                  series_options)
        from asis import config as cfg, panel, viz               # noqa: E402
        from asis.aggregate import (at_level, climatology_frame,  # noqa: E402
                                    over_window, season_columns,
                                    severity_area, to_country)
        from asis.calendar import (dekad_label,                   # noqa: E402
                                   dekad_label_long, dekad_window)
        break
    except ImportError:
        if _intento == 2:
            raise
        _purgar_modulos_locales()

st.set_page_config(page_title=texts.TITLE, page_icon="🌾", layout="wide")

TABS = {
    "pais": ["Panorama nacional", "Datos", texts.HELP_TAB],
    "departamento": ["Mapa", "Series", "Datos", texts.HELP_TAB],
    "municipio": ["Mapa", "Ranking", "Datos", texts.HELP_TAB],
}
COUNTRY_WINDOW = 54           # 18 meses: mínimo para que una serie sea serie
PLURAL = {"municipio": "Municipios", "departamento": "Departamentos"}


# --- Ventana efectiva --------------------------------------------------------
def effective(query: Query) -> tuple[Query, bool]:
    """Ventana con la que se trabaja de verdad.

    A nivel país un solo dekad no da una serie, así que se amplía a 18 meses.
    Se amplía **la consulta entera** y no solo el gráfico: cuando solo se
    ampliaba el gráfico, la pestaña de datos mostraba una observación mientras
    la figura mostraba cincuenta y cuatro, y las dos decían ser lo mismo.
    """
    if query.level != "pais" or not query.single:
        return query, False
    available = dekads(query.series_id)
    inicio = max(dekad_window(query.end, COUNTRY_WINDOW)[0], available[0])
    if inicio == query.start:
        return query, False
    return Query(level=query.level, series_id=query.series_id, start=inicio,
                 end=query.end, departments=query.departments), True


# --- Encabezado --------------------------------------------------------------
def header(mf: dict):
    """Título, procedencia y qué es esta herramienta.

    El aviso de dato preliminar vive aquí y no en una caja por consulta: es una
    propiedad permanente de la fuente, no de lo que se está mirando. Como caja
    aparecía y desaparecía al mover la ventana, que lo hacía leer como una
    alerta sobre esa selección.
    """
    ultimo = max((s.get("ultimo") or "" for s in mf.get("series", {}).values()),
                 default="")
    st.title(texts.TITLE)
    st.caption(texts.HEADER_SOURCE)
    st.caption(texts.HEADER_UPDATED.format(
        dekad=dekad_label_long(ultimo) if ultimo else "sin datos"))
    st.caption(texts.PRELIMINARY_HEADER)
    st.write(texts.INTRO)


def notices(query: Query, ampliada: bool):
    """Lo único que sigue dependiendo de la consulta.

    El aviso de fuera de temporada se retiró de aquí: no era una propiedad de
    la selección sino del indicador, y ahora se explica una vez en la
    definición del ASI, debajo de las cifras de encabezado.
    """
    if ampliada:
        st.caption(f"Ventana ampliada a 18 meses ({query.window_label}): a "
                   f"nivel país un solo dekad no forma una serie.")


def summary(query: Query, muni: pd.DataFrame, cut: pd.DataFrame):
    """Cifras de encabezado del último dekad de la ventana.

    El promedio sale del agregado ponderado por píxeles válidos y no del
    promedio de las medias municipales: sin ponderar, un municipio diminuto
    pesaría igual que uno con diez veces más área de cultivo, y son más de tres
    puntos de diferencia.

    A nivel país con un indicador estacional, la cifra es la del último dekad
    **dentro de la temporada**, que es el que cierran sus figuras. En los otros
    niveles se conserva el último dekad de la ventana, porque ahí las figuras sí
    muestran los valores congelados de fuera de temporada.
    """
    with_data = cut.dropna(subset=["mean"])
    if with_data.empty:
        return
    estacional = (query.level == "pais"
                  and cfg.SERIES.get(query.series_id)
                  and cfg.SERIES[query.series_id].season)
    ultimo = season_kpi(query, query.series_id) if estacional else None
    referencia = ultimo[0] if ultimo else query.end
    nacional = to_country(muni)
    nacional = nacional[nacional["dekad_id"] == referencia]
    at_last = with_data[with_data["dekad_id"] == referencia]
    c1, c2, c3 = st.columns(3)
    if len(nacional):
        etiqueta = ("Promedio del área filtrada" if query.departments
                    else "Promedio nacional")
        c1.metric(f"{etiqueta} · {dekad_label(referencia)}",
                  f"{nacional['mean'].iloc[0]:.2f}",
                  help=f"{query.unit}. Ponderado por píxeles válidos.")
    if query.level == "pais":
        aportan = int(at_last["n_muni"].iloc[0]) if len(at_last) else 0
        c2.metric("Municipios que aportan", f"{aportan:,}")
    else:
        c2.metric(f"{PLURAL[query.level]} con dato", f"{len(at_last):,}")
    if estacional:
        # Los que se grafican, no los de la ventana: fuera de la temporada no
        # se dibuja nada, y contarlos aquí prometería puntos que no están.
        graficados = _season_frame(query, query.series_id)
        c3.metric("Dekads en la temporada",
                  f"{graficados['dekad_id'].nunique():,}")
    else:
        c3.metric("Dekads en la ventana",
                  f"{with_data['dekad_id'].nunique():,}")


def indicator_definition(query: Query):
    """Definición del indicador activo, junto a las cifras de encabezado.

    Vivía en la pestaña "Cómo leer"; se movió aquí porque es lo primero que
    hace falta para interpretar el número que se acaba de ver arriba, y para no
    obligar a salir de la vista para entenderlo.

    Va plegada. Suelta eran dos párrafos largos entre las cifras y las figuras,
    y la primera pantalla quedaba más texto que datos, que es justo lo que este
    tablero trata de evitar. Plegada sigue a un clic de distancia.
    """
    familias = ("ASI", "VCI") if query.overview else (query.family,)
    with st.expander(texts.DEFINITIONS_BOX):
        for familia in familias:
            nombre, definicion = texts.INDICATOR_DEFINITIONS[familia]
            st.markdown(f"**{nombre}** — {definicion}")


# --- Preparación del corte ---------------------------------------------------
def slice_for(query: Query) -> tuple[pd.DataFrame, pd.DataFrame]:
    muni = load(query.series_id, query.start, query.end)
    if len(muni) and query.departments:
        muni = muni[muni["adm1_name"].isin(query.departments)]
    if muni.empty:
        return muni, muni
    return muni, at_level(muni, query.level)


DISPLAY_NAMES = {
    "adm2_code": "código municipio", "adm2_name": "municipio",
    "adm1_code": "código departamento", "adm1_name": "departamento",
    "dekad_id": "dekad", "date": "fecha", "series": "serie",
    "season": "temporada", "n_px": "píxeles válidos", "km2": "km2",
    "mean": "media", "median": "mediana", "n_muni": "municipios",
}


def for_display(df: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in df.columns if c != "series"]
    out = df[cols].rename(columns=DISPLAY_NAMES)
    if "fecha" in out:
        out["fecha"] = pd.to_datetime(out["fecha"]).dt.date
    return out


def figure(fig, data: pd.DataFrame, slug: str, key: str, narrow: bool = False):
    """Dibuja una figura y ofrece exactamente los datos que muestra.

    El botón va en una columna angosta a la derecha: es una salida, no una
    acción principal, y no debe competir con la figura. Con `narrow` se omite
    esa columna, para cuando la figura ya vive dentro de una: anidar columnas
    dos niveles no está permitido, y a ese ancho el botón tampoco necesita
    achicarse.
    """
    if fig is None:
        st.info(texts.NO_DATA)
        return
    st.plotly_chart(fig, width="stretch")
    download(data, slug, key, narrow=narrow)


def download(data: pd.DataFrame, slug: str, key: str, narrow: bool = False):
    """La descarga de una figura, aparte para poder colgarla de un par de
    figuras que comparten datos: dos botones identicos invitan a pensar que
    detras hay dos cortes distintos."""
    shown = for_display(data)
    boton = st if narrow else st.columns([3, 1])[1]
    boton.download_button(
        f"{texts.FIG_DOWNLOAD} ({len(shown):,})",
        shown.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"asis_{slug}.csv", mime="text/csv", key=key,
        width="stretch")


# --- Vistas: detalle territorial ---------------------------------------------
def view_map(query: Query, muni: pd.DataFrame, cut: pd.DataFrame):
    """Coropleta del nivel seleccionado, con su propia geometría.

    Con una ventana corta el mapa se anima, un cuadro por dekad. Con una larga
    no: una animación de cientos de cuadros no se puede leer y obliga al
    navegador a cargar la geometría una vez por dekad. En ese caso se pinta el
    peor valor de la ventana.
    """
    data = muni if query.level == "municipio" else cut
    if data.empty:
        st.info(texts.NO_DATA)
        return
    n_dekads = data["dekad_id"].nunique()
    # A nivel departamento el mapa de un rango muestra el promedio de la
    # ventana, no el peor valor ni una animación: son dieciocho unidades y la
    # pregunta ahí es cómo le fue al departamento en el periodo, no en qué
    # dekad tocó fondo. El peor valor sigue siendo el resumen a nivel
    # municipal, donde un pico aislado sí importa para la alerta.
    promedio = query.level == "departamento" and not query.single
    resumen = not query.single and n_dekads > MAX_FRAMES and not promedio
    peor = "mayor" if query.family == "ASI" else "menor"
    extra = {c: ":.0f" for c in ("pct_gt40", "pct_lt0.35")
             if c in data.columns}

    if promedio or resumen:
        # El promedio se toma sobre los dekads: cada uno pesa igual, porque la
        # pregunta es por el periodo y no por el área.
        agg = "mean" if promedio else ("max" if query.family == "ASI" else "min")
        data = over_window(
            data, [query.code_col, query.name_col, "adm1_name"], how=agg)
        titulo = (f"{query.label} · promedio de la ventana" if promedio
                  else f"{query.label} · {peor} valor de la ventana")
        subtitulo = f"{query.window_label} · {n_dekads} dekads"
        extra = {}
    else:
        titulo = f"{query.label} · {query.window_label}"
        subtitulo = ""

    estatico = promedio or resumen
    if query.family == "ASI":
        # El ASI usa un degradado continuo: un valor apenas sobre un umbral se
        # ve apenas distinto del umbral, en vez de saltar a un color plano
        # nuevo. El VCI sigue con las clases discretas de FAO, sin cambios.
        fig = viz.continuous_map(
            data, geojson(query.level), "mean", titulo, subtitulo,
            family="ASI", bar_label=query.unit_short,
            animation=None if (query.single or estatico) else "dekad_id",
            hover_extra=extra, code_col=query.code_col,
            name_col=query.name_col)
    else:
        fig = viz.class_map(
            data, geojson(query.level), query.family, titulo, subtitulo,
            animation=None if (query.single or estatico) else "dekad_id",
            hover_extra=extra, code_col=query.code_col,
            name_col=query.name_col)
    figure(fig, data, f"mapa_{query.slug()}", "dl_mapa")


def view_municipal_ranking(query: Query, muni: pd.DataFrame):
    """Los municipios en el extremo, seguidos en el tiempo.

    Con un rango es una matriz municipio por dekad, ordenada por el peor valor
    alcanzado en la ventana y no por el del último dekad, que dejaría fuera a
    quien tuvo el pico a mitad del periodo.
    """
    if muni.empty:
        st.info(texts.NO_DATA)
        return
    peor = "mayor" if query.family == "ASI" else "menor"
    top = st.slider("Municipios en el ranking", 10, 100, 50, 10,
                    key="top_ranking")
    agg = "max" if query.family == "ASI" else "min"

    if query.single:
        base = muni[muni["dekad_id"] == query.end]
        elegidos = (base.nlargest(top, "mean") if query.family == "ASI"
                    else base.nsmallest(top, "mean"))
        fig = viz.ranking_fig(
            base, "mean", f"Los {top} municipios con {peor} valor",
            dekad_label(query.end), family=query.family, top=top,
            label=query.unit_short, height=max(420, 17 * top))
    else:
        orden = muni.groupby("adm2_code", observed=True)["mean"].agg(agg)
        codigos = (orden.nlargest(top).index if query.family == "ASI"
                   else orden.nsmallest(top).index)
        elegidos = muni[muni["adm2_code"].isin(codigos)]
        fig = viz.heatmap_panel(
            muni, "mean", f"Los {top} municipios con {peor} valor",
            f"{query.window_label} · orden por el {peor} valor del periodo",
            family=query.family, top=top, ref_dekad=None,
            label=query.unit_short, height=max(480, 16 * top))
    figure(fig, elegidos, f"ranking_{query.slug()}", "dl_ranking")

    if not query.single:
        area = viz.severity_area_fig(
            muni, query.family, "Superficie por clase de severidad",
            "km2 en cada clase, dekad por dekad")
        figure(area, severity_area(muni, query.family).reset_index(),
               f"superficie_{query.slug()}", "dl_area")


def view_department_series(query: Query, cut: pd.DataFrame):
    """Una línea por departamento, o el ranking si la ventana es un dekad."""
    if cut.empty:
        st.info(texts.NO_DATA)
        return
    if query.single:
        d = cut[cut["dekad_id"] == query.end]
        etiquetado = d.copy()
        etiquetado["adm2_name"] = etiquetado["adm1_name"]   # ranking_fig lo usa
        fig = viz.ranking_fig(
            etiquetado, "mean", f"{query.label} por departamento",
            dekad_label(query.end), family=query.family, top=18,
            label=query.unit_short, height=520)
        figure(fig, d, f"departamentos_{query.slug()}", "dl_dept")
        return

    d = cut.dropna(subset=["mean"]).sort_values(["adm1_name", "dekad_id"])
    figure(_department_grid_fig(query, d), d,
           f"departamentos_{query.slug()}", "dl_dept")


GRID_COLUMNS = 3          # 18 departamentos entran en seis filas de tres
SIDE_BY_SIDE_HEIGHT = 420   # alto minimo de las dos figuras pareadas de pais


def _department_grid_fig(query: Query, d: pd.DataFrame):
    """Una cuadrícula con la serie de cada departamento en su propio recuadro.

    Antes eran dieciocho líneas superpuestas en un solo eje con una leyenda de
    dieciocho colores: para seguir un departamento había que encontrar su color
    entre diecisiete parecidos, y las líneas se tapaban entre sí. Separadas,
    cada una se lee sola y siguen comparables porque comparten el eje vertical.

    Es una sola figura, así que lleva una sola descarga, con los datos de todos
    los departamentos.
    """
    if d.empty:
        return None
    filas = -(-d["adm1_name"].nunique() // GRID_COLUMNS)
    fig = px.line(d, x="date", y="mean", facet_col="adm1_name",
                  facet_col_wrap=GRID_COLUMNS,
                  labels={"mean": query.unit_short, "date": ""},
                  height=max(320, 200 * filas))
    # El nombre del departamento viene como "adm1_name=Atlántida".
    fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
    fig.update_traces(hovertemplate="%{x|%d %b %Y}<br>%{y:.2f}<extra></extra>")
    # Con seis filas, repetir la fecha bajo cada recuadro es ruido: basta la de
    # la fila de abajo, que es la que ancla la lectura.
    fig.update_xaxes(showticklabels=False, title_text="")
    for eje in fig.select_xaxes(row=1):
        eje.update(showticklabels=True)
    viz.style_fig(fig, f"{query.label} por departamento", query.window_label,
                  y_source=-0.06, legend="off")
    return fig


def _season_frame(query: Query, series_id: str) -> pd.DataFrame:
    """La serie nacional de una temporada, solo dentro de su ventana de cultivo.

    Es el unico dato de las dos figuras de la temporada. Antes cada una armaba
    el suyo: el mapa de calor recortaba a la ventana de cultivo y la linea no,
    asi que la linea mostraba una meseta de valores congelados que el mapa de
    calor no tenia, y las dos decian ser el mismo indicador.

    Fuera de la ventana el raster trae valores, pero congelados en el cierre de
    la temporada: no describen esa fecha, y por eso no se grafican.
    """
    df = load(series_id, query.start, query.end)
    if df.empty:
        return pd.DataFrame()
    season = cfg.SERIES[series_id].season
    frame = climatology_frame(to_country(df), season)
    if frame.empty or not season:
        return frame
    return frame[frame["dekad_of_year"].isin(season_columns(season))]


def _matrix_fig(frame: pd.DataFrame, series_id: str, height: int):
    """La matriz temporada x dekad codificada en color."""
    season = cfg.SERIES[series_id].season
    return viz.climatology_matrix(
        frame, texts.SEASON_MATRIX_TITLE, texts.SEASON_MATRIX_SUBTITLE,
        value_col="mean", columns=season_columns(season), height=height)


def _lines_fig(frame: pd.DataFrame, series_id: str, height: int):
    """La misma matriz codificada en posicion: una linea por temporada.

    Antes era una serie cronologica con la linea cortada en los meses fuera de
    la ventana de cultivo. Superponer las temporadas sobre el eje de dekads
    quita el corte y, de paso, deja las dos figuras con el mismo eje horizontal:
    la fila de un anio en el mapa de calor es una linea aqui.
    """
    season = cfg.SERIES[series_id].season
    return viz.season_lines_fig(
        frame, season_columns(season), texts.SEASON_LINE_TITLE,
        texts.SEASON_LINE_SUBTITLE, label=panel.unit_short_of(series_id),
        family=panel.family_of(series_id), height=height)


def season_kpi(query: Query, series_id: str) -> tuple[str, float] | None:
    """El ultimo dato de la temporada que las figuras realmente grafican.

    El KPI mostraba el ultimo dekad de la ventana sin mirar si caia dentro de
    la temporada. En 2026-08-D3 eso daba 13,22 para la postrera, un valor
    congelado del cierre de la temporada anterior, mientras sus figuras
    terminaban en 8,97 el 2026-01-D3: la cifra de titular y los graficos
    hablaban de fechas distintas.
    """
    frame = _season_frame(query, series_id)
    if frame.empty:
        return None
    ultimo = frame.sort_values("dekad_id").iloc[-1]
    return str(ultimo["dekad_id"]), float(ultimo["mean"])


# --- Vista: panorama nacional ------------------------------------------------
def view_country(query: Query, cut: pd.DataFrame):
    """Resumen nacional o el detalle de un indicador."""
    if query.overview:
        _view_country_overview(query)
    else:
        _view_country_indicator(query)


def _country_series_fig(query: Query, series_id: str, serie: pd.DataFrame,
                        height=SIDE_BY_SIDE_HEIGHT):
    """Los indicadores sin temporada, también con una línea por año.

    El VCI era una línea continua sobre un eje de fechas: con la ventana
    completa son veintiún años encadenados en un hilo que no deja comparar un
    año contra otro. Superpuestos sobre los 36 dekads del año, cada año es una
    línea y el ciclo estacional se lee de una vez.
    """
    familia = panel.family_of(series_id)
    return viz.season_lines_fig(
        serie, season_columns(None), texts.YEAR_LINE_TITLE,
        texts.YEAR_LINE_SUBTITLE, label=panel.unit_short_of(series_id),
        family=familia, height=height,
        threshold=0.35 if familia == "VCI" else None,
        threshold_label="umbral FAO 0,35" if familia == "VCI" else "")


def _country_indicator_block(query: Query, series_id: str):
    """Un indicador a nivel país.

    En una temporada son dos vistas del mismo dato, lado a lado: el mapa de
    calor la sitúa frente a las temporadas anteriores en la misma fecha, la
    línea muestra cómo evolucionó dentro de cada una. Comparten el dato y la
    escala, así que llevan **una sola descarga**: dos botones idénticos bajo dos
    figuras invitan a pensar que detrás hay dos cortes distintos, y no los hay.

    Los indicadores sin temporada no tienen mapa de calor, así que su serie
    ocupa el ancho completo en vez de dejar media pantalla vacía.
    """
    slug = f"{series_id}_{query.slug()}"
    if not cfg.SERIES[series_id].season:
        # `climatology_frame` sin temporada agrega Year y dekad_of_year, que es
        # lo que necesita la figura para trazar una línea por año.
        df = load(series_id, query.start, query.end)
        if df.empty:
            return
        serie = climatology_frame(to_country(df), None)
        figure(_country_series_fig(query, series_id, serie), serie,
               f"serie_nacional_{slug}", f"dl_serie_{series_id}")
        return

    frame = _season_frame(query, series_id)
    if frame.empty:
        st.info(texts.NO_DATA)
        return
    # El alto sigue a la cantidad de temporadas para que dos no queden
    # estiradas sobre 600 px, y lo comparten las dos figuras: pareadas con
    # alturas distintas se leen como si una estuviera incompleta.
    alto = min(600, max(SIDE_BY_SIDE_HEIGHT,
                        130 + 26 * frame["Year"].nunique()))
    izquierda, derecha = st.columns(2)
    with izquierda:
        matriz = _matrix_fig(frame, series_id, alto)
        if matriz is None:
            st.info(texts.NO_DATA)
        else:
            st.plotly_chart(matriz, width="stretch")
    with derecha:
        linea = _lines_fig(frame, series_id, alto)
        if linea is None:
            st.info(texts.NO_DATA)
        else:
            st.plotly_chart(linea, width="stretch")

    st.caption(texts.SEASON_PAIR_NOTE.format(
        indicador=panel.label_of(series_id), ventana=query.window_label,
        temporada=season_window_label(cfg.SERIES[series_id].season)))
    st.caption(texts.ALERT_DISCLAIMER)
    download(frame[["dekad_id", "date", "Year", "dekad_of_year", "mean",
                    "n_px", "n_muni"]],
             f"temporada_{slug}", f"dl_temporada_{series_id}")


def _view_country_overview(query: Query):
    """Las dos temporadas del ASI en paralelo, después el VCI y la lluvia.

    Cada temporada trae su serie nacional y su mapa de calor, y ninguna cifra
    mezcla las dos. Antes había aquí un indicador combinado que tomaba el mayor
    de las dos por municipio; se retiró porque al agregar a país ponderando por
    píxeles válidos terminaba por debajo de la primera sola. Ver DECISIONES.md.
    """
    for series_id in OVERVIEW_SERIES:
        if series_id not in panel.stored_series():
            continue
        st.subheader(panel.label_of(series_id))
        _country_indicator_block(query, series_id)

    rain = national("serie_nacional_lluvia")
    ventana = pd.DataFrame()
    if len(rain):
        ventana = rain[(rain["dekad_id"] >= query.start)
                       & (rain["dekad_id"] <= query.end)]
    if len(ventana):
        st.subheader("Lluvia")
        fig = viz.rainfall_fig(
            ventana, "Lluvia observada y su promedio histórico",
            "Ponderada por área de cultivo · el promedio de largo plazo es el "
            "que publica FAO y no se recalcula")
        figure(fig, ventana, f"lluvia_nacional_{query.slug()}", "dl_lluvia")


def _view_country_indicator(query: Query):
    """Solo las figuras del indicador elegido, nada del resumen."""
    _country_indicator_block(query, query.series_id)


def overview_table(query: Query) -> pd.DataFrame:
    """Una fila por dekad con la cifra nacional de cada indicador.

    Cada indicador es su propia columna. Las dos temporadas del ASI nunca se
    resumen en un solo número: son mediciones sobre máscaras de cultivo
    distintas, y colapsarlas obligaba a elegir un ponderador entre
    denominadores que no son comparables.
    """
    out = pd.DataFrame()
    for series_id in OVERVIEW_SERIES:
        if series_id not in panel.stored_series():
            continue
        df = load(series_id, query.start, query.end)
        if df.empty:
            continue
        serie = (to_country(df)[["dekad_id", "mean"]]
                 .rename(columns={"mean": panel.label_of(series_id)}))
        out = serie if out.empty else out.merge(serie, on="dekad_id",
                                                how="outer")
    rain = national("serie_nacional_lluvia")
    if len(rain):
        v = rain[(rain["dekad_id"] >= query.start)
                 & (rain["dekad_id"] <= query.end)]
        cols = [c for c in ("dekad_id", "value", "lta", "anom_pct")
                if c in v.columns]
        if len(v):
            v = v[cols].rename(columns={"value": "lluvia (mm)",
                                        "lta": "lluvia LTA (mm)",
                                        "anom_pct": "anomalía de lluvia (%)"})
            out = v if out.empty else out.merge(v, on="dekad_id", how="outer")
    return out.sort_values("dekad_id").reset_index(drop=True) if len(out) else out


def summary_overview(query: Query):
    """Una cifra por indicador, nunca una sola cifra para las dos temporadas.

    Cada una cita su propio dekad, y es el último que su sección grafica. En un
    indicador estacional el último dekad de la ventana puede caer fuera de la
    temporada, y ahí el índice está congelado en el cierre de la anterior: la
    cifra de titular y las figuras hablaban de fechas distintas.
    """
    disponibles = [s for s in OVERVIEW_SERIES if s in panel.stored_series()]
    if not disponibles:
        return
    for col, series_id in zip(st.columns(len(disponibles)), disponibles):
        ultimo = season_kpi(query, series_id)
        col.metric(panel.label_of(series_id),
                   "sin dato" if ultimo is None else f"{ultimo[1]:.2f}",
                   help=f"{panel.unit_of(series_id)}. Ponderado por píxeles "
                        f"válidos.")
        col.caption("" if ultimo is None else dekad_label(ultimo[0]))
    st.caption(texts.OVERVIEW_KPI_NOTE)


# --- Vista: datos ------------------------------------------------------------
def view_data(query: Query, cut: pd.DataFrame):
    """El corte completo del nivel, más la definición de cada columna."""
    if cut.empty:
        st.info(texts.NO_DATA)
        return
    shown = for_display(cut)
    st.download_button(
        f"Descargar el corte completo · {len(shown):,} filas",
        shown.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"asis_{query.slug()}.csv", mime="text/csv",
        help=texts.DOWNLOAD_HELP, type="primary", key="dl_completo")
    st.dataframe(shown, width="stretch", hide_index=True, height=420)

    definiciones = pd.DataFrame(
        [{"columna": c, "definición": texts.describe_column(c)}
         for c in shown.columns])
    with st.expander("Definición de cada columna"):
        st.dataframe(definiciones, width="stretch", hide_index=True,
                     height=min(430, 45 + 35 * len(definiciones)))


def view_help(mf: dict):
    """Todo lo explicativo, en un solo lugar y solo cuando se busca."""
    for titulo, fichas in (("Cómo leer los indicadores", texts.READING),
                           ("Limitaciones", texts.LIMITS)):
        st.subheader(titulo)
        left, right = st.columns(2)
        for i, (nombre, cuerpo) in enumerate(fichas):
            with (left if i % 2 == 0 else right):
                with st.container(border=True):
                    st.markdown(f"**{nombre}**")
                    st.caption(cuerpo)

    st.subheader("Procedencia y validación")
    st.caption(texts.PORTAL_MD)
    ultimo = max((s.get("ultimo") or "" for s in mf.get("series", {}).values()),
                 default="")
    st.caption(texts.SOURCE_TEMPLATE.format(
        construido=(mf.get("actualizado") or "")[:10],
        ultimo=dekad_label(ultimo) if ultimo else "sin datos"))
    v = mf.get("validacion") or {}
    if v.get("r") is not None:
        st.caption(texts.VALIDATION_TEMPLATE.format(
            r=v["r"], r2=v["r2"], mae=v["mae_pp"], sesgo=v["sesgo_pp"],
            pares=v["pares"]))
    src = panel.sources()
    vintages = ", ".join(f"{k} ({d.get('descargado')})"
                         for k, d in sorted(src.items())
                         if d.get("descargado"))
    if vintages:
        st.caption(f"Instantáneas de los CSV oficiales de GIEWS: {vintages}.")
    st.caption(texts.AI_NOTE)


# --- Página ------------------------------------------------------------------
def render(name: str, query: Query, muni: pd.DataFrame, cut: pd.DataFrame,
           mf: dict):
    if name == "Mapa":
        view_map(query, muni, cut)
    elif name == "Ranking":
        view_municipal_ranking(query, muni)
    elif name == "Series":
        view_department_series(query, cut)
    elif name == "Panorama nacional":
        view_country(query, cut)
    elif name == "Datos":
        view_data(query, cut)
    elif name == texts.HELP_TAB:
        view_help(mf)


def main():
    try:
        mf = manifest()
        options = series_options()
    except panel.PanelVacio:
        st.title(texts.TITLE)
        st.error(texts.EMPTY_PANEL)
        return
    if not options:
        st.title(texts.TITLE)
        st.error(texts.EMPTY_PANEL)
        return

    query, ampliada = effective(sidebar(options))
    header(mf)
    notices(query, ampliada)

    # El resumen nacional no es una serie, así que no pasa por slice_for: cada
    # indicador se carga por su cuenta y ninguna cifra mezcla temporadas.
    if query.overview:
        tabla = overview_table(query)
        if tabla.empty:
            st.info(texts.NO_DATA)
            return
        summary_overview(query)
        indicator_definition(query)
        names = TABS[query.level]
        for tab, name in zip(st.tabs(names), names):
            with tab:
                if name == "Panorama nacional":
                    view_country(query, tabla)
                elif name == "Datos":
                    view_data(query, tabla)
                elif name == texts.HELP_TAB:
                    view_help(mf)
        return

    muni, cut = slice_for(query)

    if muni.empty:
        st.info(texts.NO_DATA)
        return

    summary(query, muni, cut)
    indicator_definition(query)
    names = TABS[query.level]
    for tab, name in zip(st.tabs(names), names):
        with tab:
            render(name, query, muni, cut, mf)


# --- Modulos locales obsoletos en memoria ------------------------------------
# Streamlit reejecuta el script principal en cada interaccion y, tras un
# despliegue, puede hacerlo reutilizando los modulos locales que ya tenia
# importados. Si el commit agrego una constante, el script nuevo se encuentra con
# el modulo viejo y la app cae con AttributeError antes de dibujar nada. Paso de
# verdad: `texts.SOURCE_MD` no existia todavia en el `app/texts.py` en memoria.
#
# La recarga se hace solo cuando el error ya ocurrio, no en cada corrida: recargar
# `app.controls` en cada rerun recrearia las funciones de `st.cache_data` y el
# panel se releeria del disco en cada clic.
def _stale_module_error(err: BaseException) -> bool:
    msg = str(err)
    return "has no attribute" in msg and ("'app" in msg or "'asis" in msg)


def _reload_local_modules() -> bool:
    """Recarga en memoria los modulos propios. `asis` antes que `app`, porque
    `app` lo importa: al reves quedaria leyendo la version vieja de config."""
    import importlib
    import sys

    recargado = False
    for prefix in ("asis", "app"):
        nombres = sorted(n for n in list(sys.modules)
                         if n == prefix or n.startswith(prefix + "."))
        for name in nombres:
            mod = sys.modules.get(name)
            if mod is None:
                continue
            try:
                importlib.reload(mod)
                recargado = True
            except Exception:
                # Si no se puede recargar, se saca de la cache para que el
                # proximo import lo traiga limpio del disco.
                sys.modules.pop(name, None)
                recargado = True
    return recargado


if __name__ == "__main__":
    try:
        main()
    except AttributeError as err:
        if not _stale_module_error(err) or not _reload_local_modules():
            raise
        print(f"modulos locales obsoletos en memoria ({err}); recargados y "
              "reintentando", flush=True)
        main()
