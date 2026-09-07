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
#
# Se derivan de los colores de clase de FAO (`config.CLASSES`), poniendo cada
# color en el **centro** de su banda y dejando que Plotly interpole entre ellos.
# Así hay un solo lugar donde vive el color de un indicador, y el degradado es
# monótono.
#
# La versión anterior del ASI ponía dos paradas casi juntas a cada lado de los
# umbrales (0,10 / 0,25 / 0,40) para que el color cambiara de familia justo ahí,
# y dentro de cada banda iba de claro a oscuro. El efecto no era el buscado: la
# luminosidad se reiniciaba en cada umbral —#ffb300 saltaba a #ffcc80, más
# claro— así que el degradado retrocedía tres veces y los bordes de banda se
# veían como costuras en vez de como transiciones.
def scale_from_classes(family: str) -> list[list]:
    """Escala continua a partir de los colores de clase de FAO.

    Cada color se ancla en el centro de su banda; los extremos se extienden
    planos hasta 0 y 1. Un valor dentro de una banda sale del color de esa
    banda, y al acercarse a la siguiente transita hacia ella sin saltos.
    """
    edges, _labels, colors = cfg.CLASSES[family]
    lo, hi = float(edges[0]), float(edges[-1])
    ancho = hi - lo
    paradas = [[0.0, colors[0]]]
    for i, color in enumerate(colors):
        centro = ((float(edges[i]) + float(edges[i + 1])) / 2 - lo) / ancho
        paradas.append([round(min(max(centro, 0.0), 1.0), 4), color])
    paradas.append([1.0, colors[-1]])
    # Sin paradas repetidas en 0 o en 1: Plotly las acepta, pero duplicar el
    # extremo es justo lo que producía la costura de la versión anterior.
    vistas, limpias = set(), []
    for pos, color in paradas:
        if pos in vistas:
            continue
        vistas.add(pos)
        limpias.append([pos, color])
    return limpias


SCALE_ASI = scale_from_classes("ASI")
SCALE_VCI = scale_from_classes("VCI")
MAP_CENTER = dict(lat=14.72, lon=-86.6)
_HAS_MAP = hasattr(px, "choropleth_map")     # plotly >= 5.24 usa maplibre


def scale_for(family: str):
    return SCALE_ASI if family == "ASI" else SCALE_VCI


def range_for(family: str):
    return (0, 100) if family == "ASI" else (0, 1)


def color_at(value: float, family: str) -> str:
    """El color exacto que la escala continua le da a un valor.

    Es la función que hace que la celda de un dekad en el mapa de calor y la
    cifra de encabezado de ese mismo dekad salgan del mismo color. Por eso el
    mapa de calor fija su rango al del indicador y no al de los datos en
    pantalla: si el máximo dependiera de la ventana, el mismo valor cambiaría
    de color al mover el rango, y ya no habría un color por valor.
    """
    lo, hi = range_for(family)
    t = min(max((float(value) - lo) / (hi - lo), 0.0), 1.0)
    paradas = scale_for(family)
    for (p0, c0), (p1, c1) in zip(paradas, paradas[1:]):
        if t <= p1:
            frac = 0.0 if p1 == p0 else (t - p0) / (p1 - p0)
            return _mix(c0, c1, frac)
    return paradas[-1][1]


def _mix(a: str, b: str, frac: float) -> str:
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * frac):02x}"
                         for x, y in zip(ca, cb))


def style_fig(fig, title, subtitle="", source=cfg.SOURCE_NOTE, y_source=-0.14,
              legend="top", top=90, source_shift=None):
    """Título, subtítulo y nota de fuente, sin repetir código en cada figura.

    Modos de leyenda, elegidos por legibilidad y no por costumbre:

    `top` pone la leyenda horizontal debajo del título. Es el modo por omisión
    porque no compite con la nota de fuente, que va abajo a la izquierda; la
    versión anterior las ponía a las dos en el pie y se pisaban.

    `v` la pone vertical a la derecha. Es la única que sirve cuando hay muchas
    series: dieciocho departamentos en una fila horizontal no se leen.

    `bottom` la deja abajo, que es la convención en los mapas de clases.

    `source_shift` ancla la nota de fuente a tantos píxeles bajo el eje, en vez
    de a una fracción del área de dibujo. Lo necesitan las figuras de eje
    categórico: sus etiquetas van rotadas y crecen hacia abajo, y con la nota
    puesta en fracción terminaban encimadas —entre ocho y diecisiete píxeles,
    medidos en el navegador—. En píxeles la separación no depende del alto de
    la figura, que además cambia con la cantidad de temporadas.
    """
    text = f"<b>{title}</b>"
    if subtitle:
        text += ("<br><span style='font-size:12px;color:#5b6270'>"
                 f"{subtitle}</span>")
    margin = dict(l=70, r=30, t=top,
                  b=70 if source_shift is None else source_shift + 26)
    if legend == "top":
        fig.update_layout(legend=dict(
            orientation="h", y=1.0, yanchor="bottom", x=0, xanchor="left",
            title_text="", font=dict(size=11)))
        margin["t"] = top + 26          # espacio para la fila de la leyenda
    elif legend == "v":
        fig.update_layout(legend=dict(
            orientation="v", y=1, yanchor="top", x=1.01, xanchor="left",
            title_text="", font=dict(size=10)))
        margin["r"] = 160
    elif legend == "bottom":
        fig.update_layout(legend=dict(
            orientation="h", y=y_source + 0.09, x=0, xanchor="left",
            title_text="", font=dict(size=10)))
    elif legend == "off":
        fig.update_layout(showlegend=False)
    fig.update_layout(title=dict(text=text, x=0.01, xanchor="left", y=0.97,
                                 yanchor="top"), margin=margin)
    if source:
        posicion = (dict(y=y_source) if source_shift is None
                    else dict(y=0, yanchor="top", yshift=-source_shift))
        fig.add_annotation(text=source, xref="paper", yref="paper", x=0,
                           showarrow=False, align="left",
                           font=dict(size=9, color="#9aa1ad"), **posicion)
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
    style_fig(fig, title, subtitle, y_source=y_source, legend="off", top=88)
    fig.update_layout(margin=dict(l=0, r=0, t=88, b=104), showlegend=True,
                      legend=dict(orientation="h", y=-0.02, x=0.5,
                                  xanchor="center", title_text="",
                                  font=dict(size=10),
                                  itemsizing="constant"))
    if fig.layout.updatemenus:
        fig.layout.updatemenus[0].buttons[0].args[1]["frame"]["duration"] = 850
        fig.layout.updatemenus[0].buttons[0].args[1]["transition"]["duration"] = 300
    if fig.layout.sliders:
        fig.layout.sliders[0].currentvalue = dict(prefix="Dekad: ",
                                                  font=dict(size=14))
    return fig


def continuous_map(df, geojson, value_col, title, subtitle="", family="ASI",
                   value_range=None, bar_label="", animation=None, height=620,
                   hover_extra=None, scale=None, code_col="adm2_code",
                   name_col="adm2_name"):
    """Coropleta continua: útil para anomalías, cambios y promedios de periodo,
    y es la que usa el ASI para que el color refleje qué tan cerca está un valor
    del siguiente umbral de alerta, en vez de una clase plana.

    `code_col`/`name_col` deciden el nivel, igual que en `class_map`: adm2_code
    dibuja municipios y adm1_code departamentos, con la geometría que
    corresponda.

    `scale` permite pasar una escala distinta a la del indicador. Un cambio o una
    anomalía necesita una escala divergente, con el cero en el centro y un color
    a cada lado, porque el signo importa: la escala del ASI, que va de verde a
    rojo en un solo sentido, no puede expresar "mejoró".
    """
    d = df.dropna(subset=[value_col]).copy()
    if d.empty:
        return None
    hover = {value_col: ":.2f", code_col: False}
    if name_col != "adm1_name" and "adm1_name" in d:
        hover["adm1_name"] = True
    hover.update(hover_extra or {})
    kw = dict(geojson=geojson, locations=code_col,
              featureidkey=f"properties.{code_col}", color=value_col,
              color_continuous_scale=scale or scale_for(family),
              range_color=value_range or range_for(family),
              center=MAP_CENTER, zoom=5.7, hover_name=name_col,
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
    # astype(str): los nombres vienen como categoria para que el panel ocupe
    # un tercio en memoria, y una categoria no se concatena con texto.
    d["etiqueta"] = (d["adm2_name"].astype(str) + " · "
                     + d["adm1_name"].astype(str))
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
    fig.update_layout(height=height, xaxis=dict(tickangle=-45, tickfont=dict(size=9)),
                      yaxis=dict(tickfont=dict(size=9.5), automargin=True))
    return style_fig(fig, title, subtitle, y_source=-0.10, legend="off")


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
                      xaxis=dict(tickangle=-45, tickfont=dict(size=9)))
    return style_fig(fig, title, subtitle, y_source=-0.22, legend="top")


def series_fig(df, value_col, title, subtitle="", label="", family="ASI",
               height=420, threshold=None, threshold_label=""):
    """Serie de tiempo de un nivel agregado, con banda de referencia opcional.

    Es la serie cronológica de un tirón. Las vistas de país no la usan: ahí las
    series se superponen por temporada o por año con `season_lines_fig()`, que
    permite comparar un ciclo contra otro. Esta la siguen usando los cuadernos.
    """
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
    fig.update_layout(height=height, yaxis_title=y_title,
                      xaxis=dict(tickfont=dict(size=9)))
    return style_fig(fig, title, subtitle, y_source=-0.20, legend="top")


def thin_ticks(labels, maximo=12) -> list[str]:
    """Etiquetas espaciadas para un eje categórico de dekads.

    Un eje con una etiqueta por dekad deja de leerse mucho antes de dejar de
    caber: con la ventana completa serían setecientas setenta y nueve. Además,
    rotadas a -45° crecen hacia abajo y terminan invadiendo la nota de fuente
    del pie. Se muestra una de cada N y el resto sigue en el hover.
    """
    labels = list(labels)
    if len(labels) <= maximo:
        return labels
    paso = -(-len(labels) // maximo)
    return labels[::paso]


def season_wraps(columns) -> bool:
    """Si la temporada cruza el año, como la postrera (sep a ene)."""
    columns = list(columns)
    return bool(columns) and columns[0] > columns[-1]


def season_labels(years, columns) -> list[str]:
    """Rótulo de cada temporada: "2025" si cabe en un año, "2025-26" si no.

    Una temporada que cruza el año se guarda bajo el año en que **empieza**,
    porque es una sola campaña agrícola. Rotularla solo con ese año la hacía
    leer como atrasada: la fila decía 2025 cuando llegaba hasta enero de 2026.
    """
    if not season_wraps(columns):
        return [str(int(y)) for y in years]
    return [f"{int(y)}-{str(int(y) + 1)[-2:]}" for y in years]


def dekad_labels(codes) -> list[str]:
    """Etiquetas de dekad del año: 13 -> "may D1". Las comparte el mapa de calor
    con las líneas por temporada, para que el mismo dekad se lea igual en las
    dos figuras."""
    return [f"{MONTH_ES[(k - 1) // 3 + 1]} D{(k - 1) % 3 + 1}" for k in codes]


def season_lines_fig(frame, columns, title, subtitle="", label="",
                     value_col="mean", season_col="Year",
                     dekad_col="dekad_of_year", family="ASI", height=420,
                     threshold=None, threshold_label="", color=None,
                     reference=None, reference_label="",
                     reference_color="#0b3d91"):
    """Una línea por temporada sobre el eje de dekads de la temporada.

    Es la misma matriz que dibuja `climatology_matrix()`, codificada en posición
    en vez de color. Al compartir el eje horizontal, las dos figuras se leen en
    paralelo: la fila de un año en el mapa de calor es una línea aquí.

    Superponer las temporadas, en lugar de encadenarlas en un eje de fechas
    continuo, evita el corte que aparecía entre el cierre de una y la apertura
    de la siguiente: entre ellas no hay dato, y una línea continua afirmaba una
    evolución que nadie midió.

    La temporada más reciente va en el color del indicador y el resto en gris:
    con veinte años en pantalla, todas del mismo color no se distinguen, y la
    pregunta casi siempre es cómo va esta contra las anteriores.

    `reference` dibuja encima una serie de referencia común a todos los años,
    indexada por dekad del año. La usa la precipitación para el promedio de
    largo plazo, que no es un año más sino la vara contra la que se comparan.
    """
    d = frame.dropna(subset=[value_col])
    if d.empty:
        return None
    orden = [c for c in columns if c in set(d[dekad_col])]
    if not orden:
        return None
    etiquetas = dekad_labels(orden)
    temporadas = sorted(d[season_col].unique())
    nombres = dict(zip(temporadas, season_labels(temporadas, orden)))
    reciente = temporadas[-1]
    color = color or ("#b0413e" if family == "ASI" else "#2f8f4e")
    fig = go.Figure()
    for anio in temporadas:
        serie = (d[d[season_col] == anio].set_index(dekad_col)[value_col]
                 .reindex(orden))
        ultima = anio == reciente
        fig.add_scatter(
            x=etiquetas, y=serie.values, mode="lines+markers",
            name=nombres[anio], connectgaps=False,
            line=dict(color=color if ultima else "#b9c0c7",
                      width=2.8 if ultima else 1.4),
            marker=dict(size=6 if ultima else 4),
            hovertemplate="%{x}<br>" + (label or value_col)
                          + ": %{y:.2f}<extra>%{fullData.name}</extra>")
    if reference is not None and len(reference):
        fig.add_scatter(
            x=etiquetas, y=pd.Series(reference).reindex(orden).values,
            mode="lines", name=reference_label or "referencia",
            line=dict(color=reference_color, width=2.4, dash="dot"),
            hovertemplate="%{x}<br>" + (reference_label or "referencia")
                          + ": %{y:.1f}<extra></extra>")
    if threshold is not None:
        fig.add_hline(y=threshold,
                      line=dict(color="#ff8900", width=1.2, dash="dot"))
        if threshold_label:
            fig.add_annotation(x=etiquetas[0], y=threshold, text=threshold_label,
                               showarrow=False, yshift=10, xanchor="left",
                               font=dict(size=10, color="#ff8900"))
    # Con los 36 dekads del año, una etiqueta por punto se amontona hasta ser
    # ilegible: se muestra una de cada tres, que deja una por mes. En la ventana
    # de una temporada caben todas. `automargin` evita que las etiquetas
    # rotadas invadan la nota de fuente del pie.
    fig.update_layout(
        height=height, yaxis_title=label or value_col,
        xaxis=dict(tickangle=-45, tickmode="array",
                   tickvals=thin_ticks(etiquetas)))
    return style_fig(fig, title, subtitle, legend="v", source_shift=78)


def climatology_matrix(national, title, subtitle="", value_col="value",
                       dekad_from=13, dekad_to=30, height=600, columns=None,
                       family="ASI", unit="%"):
    """Año x dekad: cada franja roja horizontal es una alerta roja de ASI
    (estrés extremo), no una declaratoria oficial de sequía.

    `columns` permite pasar el orden de dekads de una temporada que cruza el
    año, como la postrera: ahí la ventana va de septiembre a enero y un rango
    creciente dejaría la matriz vacía.

    El rango de color es el del indicador, no el de los datos en pantalla. Antes
    el máximo salía del percentil 99,5 de la ventana: el mismo valor cambiaba de
    color al mover el rango, dos temporadas no se podían comparar entre sí y el
    color de una celda no coincidía con el de la cifra de encabezado.
    """
    orden = (list(columns) if columns is not None
             else list(range(dekad_from, dekad_to + 1)))
    d = national[national["dekad_of_year"].isin(orden)]
    if d.empty:
        return None
    matrix = d.pivot_table(index="Year", columns="dekad_of_year",
                           values=value_col)
    matrix = matrix.reindex(columns=[c for c in orden if c in matrix.columns])
    labels = dekad_labels(matrix.columns)
    lo, hi = range_for(family)
    fig = go.Figure(go.Heatmap(
        z=matrix.values, x=labels,
        y=season_labels(matrix.index, orden),
        colorscale=scale_for(family), zmin=lo, zmax=hi,
        xgap=0.5, ygap=0.5,
        colorbar=dict(title=f"{family} {unit}".strip(), thickness=14, len=0.85),
        hovertemplate="%{y} · %{x}<br>" + family
                      + " %{z:.1f}" + unit + "<extra></extra>"))
    fig.update_layout(
        height=height, yaxis=dict(dtick=1, autorange="reversed"),
        xaxis=dict(tickangle=-45, tickmode="array",
                   tickvals=thin_ticks(labels)))
    return style_fig(fig, title, subtitle, legend="off", source_shift=78)


def anomaly_bars_fig(rain, title, subtitle="", height=420, value_col="anom_pct",
                     label="anomalía (%)"):
    """Anomalía de lluvia por dekad, sobre el eje del tiempo completo.

    Va aparte de las líneas por año y no en un eje secundario encima de ellas:
    tres lecturas superpuestas —barras de lluvia, línea del promedio y línea de
    anomalía— no dejaban leer ninguna con comodidad.

    El signo se codifica en el color, y el cero queda marcado: la pregunta que
    responde es de qué lado del promedio cayó cada dekad.

    Lleva el control de rango de Plotly debajo del eje, en vez de un deslizador
    de Streamlit encima de la figura. Es el mismo gesto pero dentro del gráfico:
    acercarse no vuelve a correr la app, así que responde al instante, y la
    figura sigue conteniendo toda la ventana, de modo que su descarga sigue
    siendo la de lo que muestra.

    El eje va en fechas y no en etiquetas de dekad: el control de rango necesita
    un eje continuo para tener sentido, y de paso las marcas de tiempo las
    espacia Plotly solo.
    """
    d = rain.dropna(subset=[value_col]).sort_values("dekad_id")
    if d.empty:
        return None
    colores = ["#3b7dd8" if v >= 0 else "#d99a2b" for v in d[value_col]]
    # Ancho explícito, en milisegundos: sobre un eje de fechas Plotly lo deduce
    # del hueco más chico entre puntos, y como los dekads miden 8, 10 u 11 días
    # tomaba el más corto de todos y dejaba las barras flacas y separadas. Nueve
    # días llenan el dekad y dejan una rendija para distinguirlas.
    ancho_dekad = 9 * 24 * 60 * 60 * 1000
    fig = go.Figure(go.Bar(
        x=d["date"], y=d[value_col], marker_color=colores, width=ancho_dekad,
        hovertemplate="%{x|%d %b %Y}<br>" + label
                      + ": %{y:+.0f}%<extra></extra>"))
    fig.add_hline(y=0, line=dict(color="#5b6270", width=1))
    fig.update_layout(
        height=height, yaxis_title=label,
        xaxis=dict(type="date", tickfont=dict(size=9),
                   rangeselector=_range_buttons(d["date"])))
    return style_fig(fig, title, subtitle, legend="off", source_shift=104,
                     top=124)


# Atajos del eje de tiempo, en meses. Los mismos tramos redondos del selector de
# la consulta, porque son los que se piden de verdad.
_RANGE_BUTTONS = ((6, "6 meses"), (12, "1 año"), (36, "3 años"),
                  (60, "5 años"))


def _range_buttons(fechas) -> dict:
    """Botones de acercamiento del eje de tiempo.

    Reemplazan al control de rango de Plotly, que dibujaba una miniatura de las
    propias barras dentro de la banda: a esta densidad no es un asa que se pueda
    agarrar, es una mancha. Un botón dice a las claras qué periodo deja a la
    vista, y el gráfico sigue admitiendo el arrastre para acotar cualquier otro.

    Solo se ofrecen los tramos más cortos que el periodo disponible: un botón de
    cinco años sobre una ventana de dieciocho meses no haría nada.
    """
    fechas = pd.to_datetime(pd.Series(fechas))
    meses = (fechas.max() - fechas.min()).days / 30.4
    botones = [dict(count=n, label=etiqueta, step="month", stepmode="backward")
               for n, etiqueta in _RANGE_BUTTONS if n < meses]
    return dict(
        buttons=botones + [dict(step="all", label="Todo")],
        x=0, xanchor="left", y=1.06, yanchor="bottom",
        font=dict(size=11), bgcolor="#eef0f3", activecolor="#d7dce3",
        bordercolor="#e6e8ec", borderwidth=1)


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
    # Ancho completo: caben mas etiquetas que en las figuras pareadas, pero no
    # una por dekad. Con la ventana completa serian setecientas setenta y nueve.
    fig.update_layout(
        height=height,
        xaxis=dict(tickangle=-45, tickfont=dict(size=9),
                   tickmode="array", tickvals=thin_ticks(labels, 16)))
    return style_fig(fig, title, subtitle, legend="top", source_shift=104)


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
    # astype(str): los nombres vienen como categoria para que el panel ocupe
    # un tercio en memoria, y una categoria no se concatena con texto.
    d["etiqueta"] = (d["adm2_name"].astype(str) + " · "
                     + d["adm1_name"].astype(str))
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
                      yaxis=dict(tickfont=dict(size=9.5), automargin=True))
    return style_fig(fig, title, subtitle, y_source=-0.10, legend="off")
