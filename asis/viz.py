"""Capa de visualización: Plotly con un estilo único.

Las figuras son las mismas para la app y para los cuadernos. Recibe geometría ya
simplificada como diccionario GeoJSON, de modo que dibujar un mapa no obliga a
tener geopandas instalado.

Identificadores en inglés, texto de figuras en español.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots

from asis import config as cfg
from asis.aggregate import classify, severity_area
from asis.calendar import MONTH_ES, dekad_label

pio.templates["asis"] = pio.templates["plotly_white"]
pio.templates["asis"].layout.update(
    font=dict(family="Inter, Roboto, Helvetica, Arial, sans-serif", size=12,
              color="#1f2430"),
    colorway=["#0b6fa4", "#e07b39", "#3f9b52", "#b0413e", "#7a5195",
              "#8c7f6b", "#c9a227", "#4f8ea3"],
    hoverlabel=dict(font_size=12))
pio.templates.default = "asis"

# Escalas continuas coherentes con la semántica del indicador: en el ASI el rojo
# es más estrés, en el VCI el rojo es peor vegetación.
SCALE_ASI = [[0.00, "#2fcd00"], [0.10, "#9ae713"], [0.25, "#ffff30"],
             [0.40, "#ffba20"], [0.55, "#ff7510"], [0.70, "#ff2a02"],
             [0.85, "#c40000"], [1.00, "#7d0000"]]
SCALE_VCI = [[0.0, "#9a0000"], [0.15, "#ff0000"], [0.30, "#ff8900"],
             [0.45, "#ffff00"], [0.60, "#66ff00"], [0.80, "#009a00"],
             [1.0, "#217400"]]
MAP_CENTER = dict(lat=14.72, lon=-86.6)
_HAS_MAP = hasattr(px, "choropleth_map")     # plotly >= 5.24 usa maplibre


def scale_for(family: str):
    return SCALE_ASI if family == "ASI" else SCALE_VCI


def range_for(family: str):
    return (0, 100) if family == "ASI" else (0, 1)


def style_fig(fig, title, subtitle="", source=cfg.SOURCE_NOTE, y_source=-0.14,
              legend="h", top=100):
    """Título, subtítulo y nota de fuente, sin repetir código en cada figura."""
    text = f"<b>{title}</b>"
    if subtitle:
        text += ("<br><span style='font-size:12.5px;color:#5b6270'>"
                 f"{subtitle}</span>")
    fig.update_layout(title=dict(text=text, x=0.01, xanchor="left", y=0.97,
                                 yanchor="top"),
                      margin=dict(l=70, r=30, t=top, b=80))
    if legend == "h":
        fig.update_layout(legend=dict(orientation="h", y=y_source + 0.09, x=0,
                                      xanchor="left", title_text=""))
    elif legend == "off":
        fig.update_layout(showlegend=False)
    if source:
        fig.add_annotation(text=source, xref="paper", yref="paper", x=0,
                           y=y_source, showarrow=False, align="left",
                           font=dict(size=10, color="#8b93a1"))
    return fig


def _choropleth(d, **kw):
    if _HAS_MAP:
        return px.choropleth_map(d, map_style="carto-positron", **kw)
    return px.choropleth_mapbox(d, mapbox_style="carto-positron", **kw)


def class_map(df, geojson, family, title, subtitle="", value_col="mean",
              animation="dekad_id", hover_extra=None, height=620,
              y_source=-0.16, code_col="adm2_code", name_col="adm2_name"):
    """Coropleta con las clases y colores oficiales de FAO.

    `code_col` decide el nivel: adm2_code dibuja municipios y adm1_code
    departamentos, con la geometría que corresponda. Un mapa departamental con
    las fronteras municipales encima insinuaría un detalle que el dato agregado
    no tiene.

    Con animation='dekad_id' produce la secuencia temporal del evento. Las
    unidades sin dato quedan en blanco y eso no es lo mismo que sin estrés:
    puede ser fuera de temporada o sin área de cultivo.
    """
    _, labels, _ = cfg.CLASSES[family]
    d = df.dropna(subset=[value_col]).copy()
    if d.empty:
        return None
    d["severidad"] = classify(d[value_col], family).astype(str)
    if "dekad_id" in d:
        d = d.sort_values("dekad_id")
    orders = {"severidad": labels}
    if animation and animation in d:
        orders[animation] = sorted(d[animation].unique())
    hover = {value_col: ":.2f", code_col: False}
    if "km2" in d:
        hover["km2"] = ":.0f"
    if name_col != "adm1_name" and "adm1_name" in d:
        hover["adm1_name"] = True
    hover.update(hover_extra or {})
    kw = dict(geojson=geojson, locations=code_col,
              featureidkey=f"properties.{code_col}", color="severidad",
              labels={"severidad": "clase"},
              color_discrete_map=cfg.PALETTE[family], category_orders=orders,
              center=MAP_CENTER, zoom=5.7, hover_name=name_col,
              hover_data=hover, opacity=0.88, height=height)
    if animation and animation in d:
        kw["animation_frame"] = animation
    fig = _choropleth(d, **kw)
    fig.update_traces(marker_line_width=0.3, marker_line_color="white")
    style_fig(fig, title, subtitle, y_source=y_source, top=95)
    fig.update_layout(margin=dict(l=0, r=0, t=95, b=125),
                      legend=dict(orientation="h", y=-0.04, x=0.5,
                                  xanchor="center", title_text="",
                                  font=dict(size=11)))
    if fig.layout.updatemenus:
        fig.layout.updatemenus[0].buttons[0].args[1]["frame"]["duration"] = 850
        fig.layout.updatemenus[0].buttons[0].args[1]["transition"]["duration"] = 300
    if fig.layout.sliders:
        fig.layout.sliders[0].currentvalue = dict(prefix="Dekad: ",
                                                  font=dict(size=14))
    return fig


def continuous_map(df, geojson, value_col, title, subtitle="", family="ASI",
                   value_range=None, bar_label="", animation=None, height=620,
                   hover_extra=None, scale=None):
    """Coropleta continua: útil para anomalías, cambios y promedios de periodo.

    `scale` permite pasar una escala distinta a la del indicador. Un cambio o una
    anomalía necesita una escala divergente, con el cero en el centro y un color
    a cada lado, porque el signo importa: la escala del ASI, que va de verde a
    rojo en un solo sentido, no puede expresar "mejoró".
    """
    d = df.dropna(subset=[value_col]).copy()
    if d.empty:
        return None
    hover = {"adm1_name": True, value_col: ":.2f", "adm2_code": False}
    hover.update(hover_extra or {})
    kw = dict(geojson=geojson, locations="adm2_code",
              featureidkey="properties.adm2_code", color=value_col,
              color_continuous_scale=scale or scale_for(family),
              range_color=value_range or range_for(family),
              center=MAP_CENTER, zoom=5.7, hover_name="adm2_name",
              hover_data=hover, opacity=0.88, height=height)
    if animation and animation in d:
        kw["animation_frame"] = animation
        kw["category_orders"] = {animation: sorted(d[animation].unique())}
    fig = _choropleth(d, **kw)
    fig.update_traces(marker_line_width=0.25, marker_line_color="white")
    fig.update_coloraxes(colorbar=dict(title=bar_label or value_col,
                                       thickness=14, len=0.75, y=0.5))
    style_fig(fig, title, subtitle, y_source=-0.11, legend="off", top=95)
    fig.update_layout(margin=dict(l=0, r=0, t=95, b=90))
    return fig


def heatmap_panel(df, value_col, title, subtitle="", family="ASI", top=30,
                  ref_dekad=None, value_range=None, height=720, label=""):
    """Matriz municipio x dekad: muestra a la vez el cuándo y el dónde."""
    d = df.dropna(subset=[value_col]).copy()
    if d.empty or "dekad_id" not in d:
        return None
    d["etiqueta"] = d["adm2_name"] + " · " + d["adm1_name"]
    # En el ASI interesan los peores por arriba; en el VCI, por abajo.
    peor = "max" if family == "ASI" else "min"
    if ref_dekad and ref_dekad in set(d["dekad_id"]):
        # Ranking de un dekad concreto: es la foto de ese momento.
        at_ref = d[d["dekad_id"] == ref_dekad]
        orden = at_ref.set_index("adm2_code")[value_col]
        selected = (at_ref.nlargest(top, value_col)["adm2_code"]
                    if family == "ASI"
                    else at_ref.nsmallest(top, value_col)["adm2_code"])
    else:
        # Ranking de toda la ventana: se ordena por el peor valor que cada
        # municipio alcanzo en el periodo, no por el del ultimo dekad, que
        # dejaria fuera a quien tuvo el pico a mitad del rango.
        orden = d.groupby("adm2_code", observed=True)[value_col].agg(peor)
        selected = (orden.nlargest(top).index if family == "ASI"
                    else orden.nsmallest(top).index)
    matrix = (d[d["adm2_code"].isin(selected)]
              .pivot_table(index="etiqueta", columns="dekad_id",
                           values=value_col))
    # Las filas se ordenan por el mismo criterio con el que se eligieron.
    clave = (d[d["adm2_code"].isin(selected)]
             .drop_duplicates("adm2_code").set_index("etiqueta")["adm2_code"]
             .map(orden))
    matrix = matrix.reindex(clave.sort_values(
        ascending=(family == "ASI")).index).dropna(how="all")
    lo, hi = value_range or range_for(family)
    fig = go.Figure(go.Heatmap(
        z=matrix.values, x=[dekad_label(c) for c in matrix.columns],
        y=matrix.index, colorscale=scale_for(family),
        zmin=lo, zmax=hi, xgap=1, ygap=1,
        colorbar=dict(title=label or value_col, thickness=14, len=0.8),
        hovertemplate="%{y}<br>%{x}<br>" + (label or value_col)
                      + ": %{z:.2f}<extra></extra>"))
    fig.update_layout(height=height, xaxis=dict(tickangle=-45),
                      yaxis=dict(tickfont=dict(size=10)))
    return style_fig(fig, title, subtitle, y_source=-0.13, legend="off")


def severity_area_fig(df, family, title, subtitle="", value_col="mean",
                      height=430):
    """Área apilada: km2 en cada clase de severidad por dekad.

    Responde cuánta superficie y no solo cuán intenso, que es la pregunta de
    quien tiene que asignar recursos.
    """
    _, labels, colors = cfg.CLASSES[family]
    g = severity_area(df, family, value_col)
    if g.empty:
        return None
    fig = go.Figure()
    x = [dekad_label(c) for c in g.index]
    for cl, color in zip(labels, colors):
        if cl in g:
            fig.add_scatter(x=x, y=g[cl], name=cl, mode="lines",
                            stackgroup="uno",
                            line=dict(width=0.5, color=color), fillcolor=color,
                            hovertemplate="%{x}<br>" + cl
                                          + ": %{y:,.0f} km2<extra></extra>")
    fig.update_layout(height=height, yaxis_title="km2",
                      xaxis=dict(tickangle=-45))
    return style_fig(fig, title, subtitle, y_source=-0.28)


def series_fig(df, value_col, title, subtitle="", label="", family="ASI",
               height=420, threshold=None, threshold_label=""):
    """Serie de tiempo de un nivel agregado, con banda de referencia opcional."""
    d = df.dropna(subset=[value_col]).sort_values("dekad_id")
    if d.empty:
        return None
    color = "#b0413e" if family == "ASI" else "#2f8f4e"
    fig = go.Figure()
    fig.add_scatter(x=d["date"], y=d[value_col], mode="lines+markers",
                    name=label or value_col,
                    line=dict(color=color, width=2.4),
                    fill="tozeroy" if family == "ASI" else None,
                    fillcolor="rgba(176,65,62,.18)" if family == "ASI" else None,
                    hovertemplate="%{x|%d %b %Y}<br>" + (label or value_col)
                                  + ": %{y:.2f}<extra></extra>")
    if threshold is not None:
        fig.add_hline(y=threshold,
                      line=dict(color="#ff8900", width=1.2, dash="dot"))
        if threshold_label:
            fig.add_annotation(x=d["date"].iloc[0], y=threshold,
                               text=threshold_label, showarrow=False, yshift=10,
                               xanchor="left",
                               font=dict(size=10, color="#ff8900"))
    fig.update_layout(height=height, yaxis_title=label or value_col)
    return style_fig(fig, title, subtitle, y_source=-0.20, legend="off")


def climatology_fig(national, pctl, n_baseline, years, title, subtitle="",
                    value_col="value", y_title="ASI nacional (%)", height=460):
    """Un año contra su propia climatología: franja p10-p90 y mediana."""
    if pctl.empty:
        return None
    labels = [f"{MONTH_ES[(k - 1) // 3 + 1]} D{(k - 1) % 3 + 1}"
              for k in pctl["dekad_of_year"]]
    fig = go.Figure()
    fig.add_scatter(x=labels, y=pctl["p90"], name="p90",
                    line=dict(width=0, color="#c9d6e3"), showlegend=False)
    fig.add_scatter(x=labels, y=pctl["p10"],
                    name=f"rango habitual p10-p90 (n={n_baseline} años)",
                    fill="tonexty", fillcolor="rgba(11,111,164,.15)",
                    line=dict(width=0, color="#c9d6e3"))
    fig.add_scatter(x=labels, y=pctl["p50"], name="mediana histórica",
                    line=dict(color="#0b6fa4", width=2, dash="dot"))
    palette = ["#b0413e", "#e07b39", "#7a5195", "#3f9b52"]
    for year, color in zip(years, palette):
        s = national[national["Year"] == year]
        if len(s):
            fig.add_scatter(
                x=[f"{MONTH_ES[(k - 1) // 3 + 1]} D{(k - 1) % 3 + 1}"
                   for k in s["dekad_of_year"]],
                y=s[value_col], name=str(year), mode="lines+markers",
                line=dict(color=color, width=2.6))
    fig.update_layout(height=height, yaxis_title=y_title)
    return style_fig(fig, title, subtitle, y_source=-0.24)


def climatology_matrix(national, title, subtitle="", value_col="value",
                       dekad_from=13, dekad_to=30, height=600):
    """Año x dekad: cada franja roja horizontal es una sequía agrícola."""
    d = national[national["dekad_of_year"].between(dekad_from, dekad_to)]
    if d.empty:
        return None
    matrix = d.pivot_table(index="Year", columns="dekad_of_year",
                           values=value_col)
    labels = [f"{MONTH_ES[(k - 1) // 3 + 1]} D{(k - 1) % 3 + 1}"
              for k in matrix.columns]
    top = float(np.nanpercentile(matrix.values, 99.5))
    fig = go.Figure(go.Heatmap(
        z=matrix.values, x=labels, y=matrix.index.astype(int),
        colorscale=SCALE_ASI, zmin=0, zmax=top if top > 0 else 1,
        xgap=0.5, ygap=0.5,
        colorbar=dict(title="ASI %", thickness=14, len=0.85),
        hovertemplate="%{y} · %{x}<br>ASI %{z:.1f}%<extra></extra>"))
    fig.update_layout(height=height, yaxis=dict(dtick=1, autorange="reversed"),
                      xaxis=dict(tickangle=-45))
    return style_fig(fig, title, subtitle, y_source=-0.13, legend="off")


def rainfall_fig(rain, title, subtitle="", height=440):
    """Lluvia observada, promedio de largo plazo y anomalía en el mismo eje.

    La LTA es la que publica FAO y no se recalcula: es la referencia oficial
    contra la que compara GIEWS.
    """
    d = rain.dropna(subset=["value"]).sort_values("dekad_id")
    if d.empty:
        return None
    labels = [dekad_label(c) for c in d["dekad_id"]]
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_bar(x=labels, y=d["value"], name="lluvia observada",
                marker_color="#3b7dd8", opacity=0.9,
                hovertemplate="%{x}<br>%{y:.0f} mm<extra></extra>")
    if "lta" in d:
        fig.add_scatter(x=labels, y=d["lta"], name="promedio histórico (LTA)",
                        mode="lines+markers",
                        line=dict(color="#0b3d91", dash="dot"),
                        hovertemplate="%{x}<br>LTA %{y:.0f} mm<extra></extra>")
    if "anom_pct" in d:
        fig.add_scatter(x=labels, y=d["anom_pct"], name="anomalía (%)",
                        mode="lines", line=dict(color="#b0413e", width=2),
                        secondary_y=True,
                        hovertemplate="%{x}<br>anomalía %{y:+.0f}%<extra></extra>")
        fig.update_yaxes(title_text="anomalía sobre la LTA (%)",
                         secondary_y=True, showgrid=False)
    fig.update_yaxes(title_text="mm por dekad", secondary_y=False)
    fig.update_layout(height=height, xaxis=dict(tickangle=-45))
    return style_fig(fig, title, subtitle, y_source=-0.30)


def dashboard_fig(asi, vci, rain, title, subtitle="", height=720):
    """Los tres indicadores sobre el mismo eje temporal.

    Leerlos juntos evita los dos errores típicos: creer que no pasa nada donde
    el ASI no aplica, y confundir un exceso de agua con una sequía.
    """
    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.07,
        subplot_titles=("ASI nacional · % del área de cultivo bajo estrés hídrico",
                        "VCI nacional · condición de la vegetación (0-1)",
                        "Anomalía de lluvia sobre el promedio histórico (%)"))
    if asi is not None and len(asi):
        fig.add_scatter(x=asi["date"], y=asi["mean"], name="ASI",
                        mode="lines+markers",
                        line=dict(color="#b0413e", width=2.4), fill="tozeroy",
                        fillcolor="rgba(176,65,62,.18)",
                        hovertemplate="%{x|%d %b %Y}<br>ASI %{y:.1f}%<extra></extra>",
                        row=1, col=1)
    if vci is not None and len(vci):
        fig.add_scatter(x=vci["date"], y=vci["mean"], name="VCI", mode="lines",
                        line=dict(color="#2f8f4e", width=2.4),
                        hovertemplate="%{x|%d %b %Y}<br>VCI %{y:.3f}<extra></extra>",
                        row=2, col=1)
        fig.add_hline(y=0.35, line=dict(color="#ff8900", width=1.1, dash="dot"),
                      row=2, col=1)
    if rain is not None and len(rain) and "anom_pct" in rain:
        fig.add_bar(x=rain["date"], y=rain["anom_pct"], name="anomalía",
                    marker_color=np.where(rain["anom_pct"] >= 0, "#3b7dd8",
                                          "#c98b3b"),
                    hovertemplate="%{x|%d %b %Y}<br>%{y:+.0f}%<extra></extra>",
                    row=3, col=1)
        fig.add_hline(y=0, line=dict(color="#666", width=1), row=3, col=1)
    fig.update_layout(height=height, showlegend=False)
    fig.update_annotations(font_size=12, x=0, xanchor="left")
    return style_fig(fig, title, subtitle, y_source=-0.11, legend="off")


def raster_detail(source, title, subtitle="", family="ASI", label="",
                  bbox=None, height=560):
    """Vista a resolución nativa (~1 km): lo que el promedio municipal esconde.

    Acepta un arreglo ya leído o la ruta de un GeoTIFF. Con una ruta importa
    rasterio en el momento, de modo que la app —que nunca pasa por aquí— no
    necesita tenerlo instalado.
    """
    if isinstance(source, np.ndarray):
        arr = source
    else:
        from asis.zonal import read_tif
        arr = read_tif(source)
    if bbox is None:
        from asis.client import SNAP
        bbox = SNAP["bbox"]
    lon = np.linspace(bbox[0], bbox[2], arr.shape[1])
    lat = np.linspace(bbox[1], bbox[3], arr.shape[0])
    lo, hi = range_for(family)
    # La fila 0 del ráster es el norte: se invierte para dejar el norte arriba.
    fig = px.imshow(arr[::-1], x=lon, y=lat, origin="lower", aspect="equal",
                    color_continuous_scale=scale_for(family),
                    zmin=lo, zmax=hi, height=height)
    fig.update_traces(hovertemplate="lon %{x:.2f} · lat %{y:.2f}<br>"
                                    + (label or "valor")
                                    + " %{z:.2f}<extra></extra>")
    fig.update_coloraxes(cmin=lo, cmax=hi,
                         colorbar=dict(title=label or "valor", thickness=14,
                                       len=0.8))
    fig.update_xaxes(title="longitud", showgrid=False)
    fig.update_yaxes(title="latitud", showgrid=False)
    return style_fig(fig, title, subtitle, y_source=-0.13, legend="off")


def ranking_fig(df, value_col, title, subtitle="", family="ASI", top=20,
                label="", height=560):
    """Los municipios extremos de un dekad, ordenados. Es la vista que se lleva
    a una reunión: nombres, no un mapa."""
    d = df.dropna(subset=[value_col]).copy()
    if d.empty:
        return None
    d = (d.nlargest(top, value_col) if family == "ASI"
         else d.nsmallest(top, value_col))
    d["etiqueta"] = d["adm2_name"] + " · " + d["adm1_name"]
    d = d.sort_values(value_col, ascending=(family == "ASI"))
    lo, hi = range_for(family)
    fig = go.Figure(go.Bar(
        x=d[value_col], y=d["etiqueta"], orientation="h",
        marker=dict(color=d[value_col], colorscale=scale_for(family),
                    cmin=lo, cmax=hi,
                    colorbar=dict(title=label or value_col, thickness=12,
                                  len=0.7)),
        hovertemplate="%{y}<br>" + (label or value_col)
                      + ": %{x:.2f}<extra></extra>"))
    fig.update_layout(height=height, xaxis_title=label or value_col,
                      yaxis=dict(tickfont=dict(size=10)))
    return style_fig(fig, title, subtitle, y_source=-0.13, legend="off")
