"""Panel agroclimático de Honduras — app de Streamlit.

Lee el panel ya construido de `data/` y no toca la red. Punto de entrada del
despliegue: `streamlit run streamlit_app.py`.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app import texts
from app.controls import (LEVELS, Query, load, geojson, manifest, national,
                          season_status, sidebar, series_options)
from asis import config as cfg, panel, viz
from asis.aggregate import at_level, climatology
from asis.calendar import dekad_label, dekad_year

st.set_page_config(page_title=texts.TITLE, page_icon="🌾", layout="wide")


# --- Encabezado --------------------------------------------------------------
def header(mf: dict):
    st.title(texts.TITLE)
    st.caption(texts.SUBTITLE)
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
    st.info(texts.HOW_TO_READ)


def season_notice(query: Query):
    """Aviso explícito de fuera de temporada. Nunca un mapa vacío que se lea
    como ausencia de estrés."""
    status = season_status(query)
    if not status["seasonal"] or not status["outside"]:
        return
    if status["outside"] == status["total"]:
        st.warning(texts.OUT_OF_SEASON.format(
            serie=query.label, temporada=status["season_name"],
            ventana=status["window"], dekad=query.window_label))
    else:
        st.warning(texts.PARTIAL_SEASON.format(
            n=status["outside"], total=status["total"],
            temporada=status["season_name"]))


# --- Preparación del corte ---------------------------------------------------
def slice_for(query: Query) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Devuelve (panel municipal filtrado, corte al nivel pedido)."""
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


# --- Vistas ------------------------------------------------------------------
def view_map(query: Query, muni: pd.DataFrame, cut: pd.DataFrame):
    if query.level == "pais":
        st.info(texts.COUNTRY_MAP)
        return
    gj = geojson()
    if query.level == "departamento":
        st.caption(texts.DEPARTMENT_MAP)
        # Se reparte el valor departamental sobre sus municipios: la geometría
        # versionada es municipal y basta para mostrar el reparto territorial.
        base = muni[["adm2_code", "adm2_name", "adm1_code", "adm1_name",
                     "dekad_id"]].drop_duplicates()
        data = base.merge(cut[["adm1_code", "dekad_id", "mean", "km2"]],
                          on=["adm1_code", "dekad_id"], how="inner")
    else:
        data = muni
    if data.empty:
        st.info(texts.NO_DATA)
        return
    extra = {}
    for c in ("pct_gt40", "pct_lt0.35", "p90"):
        if c in data:
            extra[c] = ":.0f"
    fig = viz.class_map(
        data, gj, query.family,
        f"{query.label} · {query.window_label}",
        "Clases y colores oficiales de FAO. En blanco, municipios sin dato: "
        "fuera de temporada o sin área de cultivo, que no es lo mismo que sin "
        "estrés.",
        animation="dekad_id" if not query.single else None,
        hover_extra=extra)
    if fig is None:
        st.info(texts.NO_DATA)
        return
    st.plotly_chart(fig, use_container_width=True)


def view_series(query: Query, muni: pd.DataFrame, cut: pd.DataFrame):
    if query.single:
        st.caption("La serie de tiempo necesita un rango. Cambie la ventana a "
                   "«Rango» en el panel de la izquierda.")
        return
    unit = panel.unit_of(query.series_id)
    if query.level == "pais":
        fig = viz.series_fig(
            cut, "mean", f"{query.label} · nacional",
            f"Ponderado por píxeles válidos. {query.window_label}.",
            label=unit, family=query.family,
            threshold=0.35 if query.family == "VCI" else None,
            threshold_label="umbral FAO VCI 0,35" if query.family == "VCI" else "")
        if fig:
            st.plotly_chart(fig, use_container_width=True)
    elif query.level == "departamento":
        import plotly.express as px
        d = cut.dropna(subset=["mean"]).sort_values("dekad_id")
        fig = px.line(d, x="date", y="mean", color="adm1_name",
                      labels={"mean": unit, "date": "", "adm1_name": ""},
                      height=520)
        viz.style_fig(fig, f"{query.label} · por departamento",
                      f"{query.window_label}. Cada línea es un departamento, "
                      "ponderado por píxeles válidos.", y_source=-0.16)
        st.plotly_chart(fig, use_container_width=True)
    else:
        top = st.slider("Municipios a mostrar", 10, 60, 30, 5,
                        key="top_matriz")
        fig = viz.heatmap_panel(
            muni, "mean", f"{query.label} · municipio por dekad",
            f"Los {top} municipios más afectados en el último dekad de la "
            f"ventana. {query.window_label}.",
            family=query.family, top=top, ref_dekad=query.end,
            label=unit)
        if fig is None:
            st.info(texts.NO_DATA)
        else:
            st.plotly_chart(fig, use_container_width=True)

    area = viz.severity_area_fig(
        muni, query.family, "Superficie por clase de severidad",
        "km2 en cada clase, dekad por dekad. Responde cuánta superficie y no "
        "solo cuán intenso.")
    if area:
        st.plotly_chart(area, use_container_width=True)


def view_ranking(query: Query, muni: pd.DataFrame, cut: pd.DataFrame):
    if query.level == "pais":
        st.info("El ranking compara unidades territoriales. Cambie el nivel a "
                "departamento o municipio.")
        return
    last = query.end
    unit = panel.unit_of(query.series_id)
    d = cut[cut["dekad_id"] == last]
    if d.empty:
        st.info(texts.NO_DATA)
        return
    name_col = "adm2_name" if query.level == "municipio" else "adm1_name"
    d = d.copy()
    if query.level == "departamento":
        d["adm2_name"] = d["adm1_name"]
    fig = viz.ranking_fig(
        d, "mean",
        f"{query.label} · {LEVELS[query.level].lower()}s en el extremo",
        f"{dekad_label(last)}. "
        + ("Mayor estrés arriba." if query.family == "ASI"
           else "Peor condición de la vegetación arriba."),
        family=query.family, top=20, label=unit)
    if fig:
        st.plotly_chart(fig, use_container_width=True)


def view_context(query: Query):
    """Contexto nacional oficial de FAO: climatología, lluvia y tablero."""
    asi_nat = national("serie_nacional_asi")
    rain = national("serie_nacional_lluvia")
    if asi_nat.empty and rain.empty:
        st.info("Las series nacionales oficiales no están construidas en este "
                "despliegue.")
        return

    if not asi_nat.empty:
        year = dekad_year(query.end)
        pctl, n_base = climatology(asi_nat, year_max=year)
        years = [y for y in (year, 2019, 2020) if y in set(asi_nat["Year"])]
        fig = viz.climatology_fig(
            asi_nat, pctl, n_base, years,
            "El año seleccionado frente a la norma histórica",
            f"ASI nacional de la temporada primera, mayo a octubre. Franja "
            f"azul: rango habitual p10-p90 sobre {n_base} años previos a "
            f"{year}. Serie oficial de GIEWS ponderada por área de cultivo.")
        if fig:
            st.plotly_chart(fig, use_container_width=True)

        matrix = viz.climatology_matrix(
            asi_nat, "Climatología del estrés agrícola",
            "ASI nacional por dekad de la temporada primera. Cada franja roja "
            "horizontal es una sequía agrícola.")
        if matrix:
            st.plotly_chart(matrix, use_container_width=True)

    if not rain.empty:
        window = rain[(rain["dekad_id"] >= query.start)
                      & (rain["dekad_id"] <= query.end)]
        if len(window) < 3:
            window = rain.tail(54)
        fig = viz.rainfall_fig(
            window, "Lluvia observada frente a su promedio histórico",
            "Lluvia dekadal nacional ponderada por área de cultivo. La LTA es "
            "la que publica FAO y no se recalcula.")
        if fig:
            st.plotly_chart(fig, use_container_width=True)
    st.caption(texts.WEIGHTING)


def view_data(query: Query, cut: pd.DataFrame):
    if cut.empty:
        st.info(texts.NO_DATA)
        return
    shown = for_display(cut)
    st.caption(f"{len(shown):,} filas · {LEVELS[query.level].lower()} · "
               f"{query.label} · {query.window_label}")
    st.dataframe(shown, use_container_width=True, hide_index=True,
                 height=460)
    csv = shown.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "Descargar CSV del corte en pantalla", csv,
        file_name=f"asis_{query.slug()}.csv", mime="text/csv",
        help=texts.DOWNLOAD_HELP, type="primary")
    st.caption(texts.WEIGHTING)


def summary(query: Query, muni: pd.DataFrame, cut: pd.DataFrame):
    """Cifras de encabezado del último dekad de la ventana.

    El promedio se toma siempre del agregado ponderado por píxeles válidos, no
    del promedio de las medias municipales: promediar municipios sin ponderar
    le daría a un municipio diminuto el mismo peso que a uno con diez veces más
    área de cultivo.
    """
    from asis.aggregate import to_country

    with_data = cut.dropna(subset=["mean"])
    if with_data.empty:
        return
    last = to_country(muni)
    last = last[last["dekad_id"] == query.end]
    scope = ("del área seleccionada" if query.departments else "nacional")
    c1, c2, c3 = st.columns(3)
    if len(last):
        c1.metric(f"Promedio {scope} · {dekad_label(query.end)}",
                  f"{last['mean'].iloc[0]:.2f}",
                  help=f"{panel.unit_of(query.series_id)}. Ponderado por "
                       "píxeles válidos.")
    at_last = with_data[with_data["dekad_id"] == query.end]
    c2.metric(f"{LEVELS[query.level]}s con dato", f"{len(at_last):,}")
    c3.metric("Dekads en la ventana", f"{with_data['dekad_id'].nunique():,}")


def limits_panel():
    st.divider()
    st.subheader("Limitaciones")
    st.caption("Lo que este panel no dice. Conviene leerlo antes de citar "
               "cualquier cifra fuera de la app.")
    left, right = st.columns(2)
    for i, (title, body) in enumerate(texts.LIMITS):
        with (left if i % 2 == 0 else right):
            with st.container(border=True):
                st.markdown(f"**{title}**")
                st.caption(body)
    src = panel.sources()
    if src:
        vintages = ", ".join(
            f"{k} ({v.get('descargado', '?')})" for k, v in sorted(src.items())
            if v.get("descargado"))
        if vintages:
            st.caption(f"Instantáneas de los CSV oficiales de GIEWS: {vintages}.")
    st.caption(texts.AI_NOTE)


# --- Página ------------------------------------------------------------------
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

    header(mf)
    query = sidebar(options)
    season_notice(query)
    muni, cut = slice_for(query)

    if muni.empty:
        st.info(texts.NO_DATA)
        limits_panel()
        return

    summary(query, muni, cut)

    tabs = st.tabs(["Mapa", "Serie", "Ranking", "Contexto nacional", "Datos"])
    with tabs[0]:
        view_map(query, muni, cut)
    with tabs[1]:
        view_series(query, muni, cut)
    with tabs[2]:
        view_ranking(query, muni, cut)
    with tabs[3]:
        view_context(query)
    with tabs[4]:
        view_data(query, cut)

    limits_panel()


if __name__ == "__main__":
    main()
