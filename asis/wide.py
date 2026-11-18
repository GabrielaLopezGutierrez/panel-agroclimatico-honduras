"""Las tablas que dibujan las figuras, en la forma que esperan las de afuera.

El panel es largo: una fila por unidad y dekad, con los píxeles, el área, la
media, los percentiles y los porcentajes sobre umbral. Es la forma correcta
para analizar y es la que ofrece la pestaña Datos.

Una herramienta de gráficos quiere lo contrario: una fila por punto del eje
horizontal y una columna por serie, con el encabezado ya escrito como va a
leerse en la leyenda. Eso es lo que arma este módulo, y es lo que entrega el
botón de cada figura, para que la tabla se pegue en Flourish sin pivotear ni
renombrar nada.

Nada de esto recalcula. Cada función es un pivote de lo que la figura ya
recibió, así que la cifra que sale por este camino y la que se dibuja en
pantalla son la misma por construcción. Es la misma regla de siempre: el
cálculo vive una vez, en `asis/`, y acá vive una sola forma de la tabla, usada
por el botón de la app y por el archivo que se publica para Flourish.

Los encabezados que salen de aquí son una interfaz. Un gráfico publicado que
apunta a uno de estos archivos se rompe en silencio si una columna cambia de
nombre, y nadie se entera hasta que alguien lo mira; `tests/test_flourish.py`
los fija por eso.
"""
from __future__ import annotations

import pandas as pd

from asis import config as cfg
from asis.aggregate import classify, narrowest_band, season_columns
from asis.calendar import dekad_label, dekad_labels, season_labels

# Dos decimales en todo. Flourish formatea la presentación por su cuenta -el
# separador decimal y el de miles se fijan en su pestaña Datos-, así que lo
# único que hay que decidir aquí es cuánta precisión se afirma. Más decimales
# no son más exactitud: la media ponderada del ASI no la tiene, y el CSV de
# departamentos del repo, escrito sin redondear, publica cosas como
# 4420.590000000001, que es ruido de punto flotante en pantalla.
DECIMALS = 2

# El municipio sin dato del mapa. Es una clase más y no un hueco: una
# herramienta de afuera pinta de blanco lo que no encuentra, y en un mapa de
# sequía un hueco blanco se lee como calma. Nombrándolo, entra a la leyenda.
NO_DATA_LABEL = "sin dato"


def season_table(frame: pd.DataFrame, season: str | None, value_col="mean",
                 reference: pd.Series | None = None, reference_label="",
                 drop_partial_start: bool = False,
                 decimals: int = DECIMALS) -> pd.DataFrame:
    """Una fila por dekad de la temporada y una columna por campaña.

    Es la misma tabla que dibujan el mapa de calor y las líneas por temporada:
    la fila de un año en la matriz es una línea en la otra figura, y acá es una
    columna. Por eso las dos figuras comparten una sola descarga.

    El eje es la posición dentro de la temporada y no una fecha. No hay una
    fecha que valga para todas las columnas: cada una es un año distinto, y
    entre el cierre de una campaña y la apertura de la siguiente no hay dato.

    `reference` es una serie común a todos los años, indexada por dekad del
    año, y entra como una columna más. La usa la precipitación para el promedio
    de largo plazo, que no es un año más sino la vara contra la que se compara.
    """
    d = frame.dropna(subset=[value_col]) if len(frame) else frame
    if not len(d):
        return pd.DataFrame()
    columnas = season_columns(season)
    presentes = set(d["dekad_of_year"])
    orden = [c for c in columnas if c in presentes]
    if not orden:
        return pd.DataFrame()

    m = (d.pivot_table(index="dekad_of_year", columns="Year",
                       values=value_col)
          .reindex(index=orden))
    if drop_partial_start and len(m.columns) and pd.isna(m.iloc[0, 0]):
        # La primera campaña no empieza donde empieza la temporada. En la
        # postrera pasa siempre: la que abrió en septiembre de 2004 entra al
        # panel solo por su cola de enero de 2005, porque START_YEAR es 2005.
        # Esa columna no es una campaña, es su último tercio.
        #
        # Lo pide quien publica, no esta función: con una ventana elegida en
        # pantalla la primera campaña casi siempre empieza a mitad, y
        # descartarla ahí borraría justo lo que la persona pidió ver.
        m = m.drop(columns=m.columns[0])
    anios = list(m.columns)
    m.columns = season_labels(anios, columnas)
    if reference is not None and len(reference):
        m[reference_label or "referencia"] = [
            reference.get(c, float("nan")) for c in orden]
    m.index = dekad_labels(orden)
    out = m.round(decimals).reset_index()
    out.columns = ["dekad", *list(out.columns)[1:]]
    return out


# Los tres grupos de la dispersión de coberturas, que son los que colorea la
# figura de la app. Van acá y no en la herramienta de afuera por lo mismo que
# la clase del mapa: el rótulo y el criterio son del cálculo, no del gráfico.
SAME_LABEL = "coinciden"
PASTURE_WORSE_LABEL = "el pastizal está peor"
CROP_WORSE_LABEL = "el cultivo está peor"

ABOVE_LABEL = "por encima del promedio"
BELOW_LABEL = "por debajo del promedio"


def heatmap_table(frame: pd.DataFrame, season: str | None, label: str,
                  family="ASI", value_col="mean",
                  decimals: int = DECIMALS) -> pd.DataFrame:
    """La misma matriz de `season_table`, pero larga: una fila por celda.

    Es la única tabla de este módulo que sale larga, y no por capricho. Las
    demás salen anchas porque una herramienta de gráficos lee la primera
    columna como eje y el resto como series; un mapa de calor no tiene series,
    tiene celdas, y pide las dos coordenadas y el valor en columnas aparte.

    Sale de `season_table` y se derrite: así la matriz publicada y la que
    dibuja la figura son la misma por construcción, igual que la línea y la
    matriz de la app comparten una sola descarga porque son la misma tabla
    vista de dos maneras.

    Las celdas sin dato no se publican. Una campaña en curso termina donde
    llegó el panel, y una fila con la coordenada puesta y el valor vacío no es
    una observación: es la ausencia de una.
    """
    ancha = season_table(frame, season, value_col=value_col,
                         drop_partial_start=True, decimals=decimals)
    if not len(ancha):
        return pd.DataFrame()
    larga = ancha.melt(id_vars="dekad", var_name="campaña", value_name=label)
    larga = larga.dropna(subset=[label])
    if not len(larga):
        return pd.DataFrame()
    larga = larga[["campaña", "dekad", label]].reset_index(drop=True)
    # La clase, que es por lo que colorea el gráfico publicado. Una escala
    # numérica afuera interpola entre dos colores, y los cuatro de FAO no
    # caben ahí: el degradado salía verde, oliva, marrón y rojo, que no son
    # los colores de la leyenda. Con la clase, los cuatro intervalos salen
    # planos y con el color que les toca, como en el visor de FAO.
    larga["clase"] = classify(larga[label], family).astype(str).values
    return larga


def _qualified(d: pd.DataFrame, name_col: str,
               group_col: str | None) -> pd.Series:
    """El nombre de la unidad, con el de su departamento si hace falta.

    Veintiséis nombres de municipio se repiten en Honduras, alguno en tres
    departamentos a la vez. Afuera, una rejilla separa paneles por el valor
    de una columna, así que dos municipios homónimos caerían en el mismo
    panel y sus series se mezclarían sin que nada lo diga. Es la misma
    etiqueta que arma `viz.heatmap_panel` para su eje, por el mismo motivo.
    """
    nombre = d[name_col].astype(str)
    if group_col and group_col in d and group_col != name_col:
        return nombre + " · " + d[group_col].astype(str)
    return nombre


def unit_series_table(frame: pd.DataFrame, label: str, family="ASI",
                      value_col="mean", name_col="adm2_name",
                      group_col: str | None = "adm1_name",
                      with_class: bool = False,
                      decimals: int = DECIMALS) -> pd.DataFrame:
    """Una fila por unidad y dekad: la forma de una rejilla o de un mapa de
    calor de unidades.

    Es larga por el mismo motivo que `heatmap_table`: afuera, una rejilla se
    arma declarando qué columna separa los paneles, y un mapa de calor pide
    las dos coordenadas aparte. En los dos casos la unidad es una columna y
    no un encabezado.

    Lleva la fecha además de la etiqueta del dekad. La etiqueta se lee, la
    fecha ordena: sin ella "1er dek abr" se ordena antes que "1er dek ene".
    """
    d = frame.dropna(subset=[value_col]) if len(frame) else frame
    if not len(d):
        return pd.DataFrame()
    d = d.sort_values([name_col, "dekad_id"])
    nombres = {"adm2_name": "municipio", "adm1_name": "departamento"}
    out = pd.DataFrame({
        nombres.get(name_col, name_col): _qualified(d, name_col,
                                                    group_col).values,
        "fecha": pd.to_datetime(d["date"]).dt.date.values,
        "dekad": [dekad_label(c) for c in d["dekad_id"]],
    })
    valores = d[value_col].round(decimals)
    out[label] = valores.values
    if with_class:
        out["clase"] = classify(valores, family).astype(str).values
    return out


def cover_grid_table(crop: pd.DataFrame, pasture: pd.DataFrame,
                     value_col="mean",
                     decimals: int = DECIMALS) -> pd.DataFrame:
    """Las dos coberturas de cada municipio dekad a dekad.

    Es la rejilla: un panel por municipio y dos líneas dentro. Como en
    `cover_table`, las dos cifras conviven en columnas y nunca se promedian
    ni se restan; lo que cambia es que aquí hay una fila por dekad.
    """
    if crop is None or pasture is None or not len(crop) or not len(pasture):
        return pd.DataFrame()
    llaves = ["adm2_code", "adm2_name", "adm1_name", "dekad_id", "date"]
    a = crop.dropna(subset=[value_col])[llaves + [value_col]]
    b = pasture.dropna(subset=[value_col])[["adm2_code", "dekad_id",
                                            value_col]]
    d = a.merge(b, on=["adm2_code", "dekad_id"], suffixes=("_c", "_p"))
    if not len(d):
        return pd.DataFrame()
    d = d.sort_values(["adm2_code", "dekad_id"])
    return pd.DataFrame({
        "municipio": _qualified(d, "adm2_name", "adm1_name").values,
        "fecha": pd.to_datetime(d["date"]).dt.date.values,
        "dekad": [dekad_label(c) for c in d["dekad_id"]],
        "cultivo": d[f"{value_col}_c"].round(decimals).values,
        "pastizal": d[f"{value_col}_p"].round(decimals).values,
    })


def severity_table(frame: pd.DataFrame, family: str, season: str | None,
                   decimals: int = DECIMALS) -> pd.DataFrame:
    """Kilómetros cuadrados en cada clase, dekad a dekad y por campaña.

    Sale de `aggregate.severity_area`, que es la misma función que alimenta
    la figura. Las cuatro clases ya vienen como columnas, que es justo lo que
    una herramienta de afuera necesita para apilarlas, y la campaña va al
    lado para poder separar los paneles: la figura de la app dibuja uno por
    campaña, porque entre el cierre de una y la apertura de la siguiente no
    hay dato y una sola serie corrida afirmaría una caída que nadie midió.
    """
    from asis.aggregate import campaign_year, severity_area

    if not len(frame):
        return pd.DataFrame()
    g = severity_area(frame, family).reset_index()
    if not len(g):
        return pd.DataFrame()
    clases = [c for c in g.columns if c != "dekad_id"]
    out = pd.DataFrame({
        "campaña": campaign_year(g["dekad_id"], season).astype(str).values,
        "dekad": [dekad_label(c) for c in g["dekad_id"]],
    })
    for c in clases:
        out[c] = g[c].round(decimals).values
    return out


def anomaly_table(frame: pd.DataFrame, value_col="anom_pct",
                  label="anomalía (%)", split_sign: bool = False,
                  year_column: bool = False,
                  decimals: int = DECIMALS) -> pd.DataFrame:
    """Una fila por dekad sobre el eje del tiempo corrido.

    Es la única de estas tablas que no es una climatología, porque la figura
    que la dibuja tampoco lo es: la anomalía de lluvia no depende de la ventana
    de cultivo de ningún indicador y se grafica de corrido. Por eso lleva fecha
    de verdad además de la etiqueta, y por eso la precipitación necesita dos
    descargas y no una: sus dos figuras tienen ejes distintos.
    """
    d = frame.dropna(subset=[value_col]).sort_values("dekad_id") \
        if len(frame) else frame
    if not len(d):
        return pd.DataFrame()
    out = pd.DataFrame({
        "fecha": pd.to_datetime(d["date"]).dt.date.values,
        "dekad": [dekad_label(c) for c in d["dekad_id"]],
    })
    if year_column:
        # Para el control de filtro de la herramienta de afuera, que filtra
        # filas por el valor de una columna. La fecha ya trae el año, pero no
        # sirve de filtro: son setecientas ochenta y siete fechas distintas.
        out["año"] = [str(c)[:4] for c in d["dekad_id"]]
    v = d[value_col].round(decimals)
    if not split_sign:
        out[label] = v.values
        return out
    # Dos columnas por el mismo motivo que el ranking lleva cuatro: la figura
    # de la app codifica el signo en el color y afuera el color es la columna.
    # Partida en dos, la barra sale azul arriba del promedio y ocre abajo, que
    # es lo que se ve en pantalla.
    out[ABOVE_LABEL] = v.where(v >= 0).values
    out[BELOW_LABEL] = v.where(v < 0).values
    return out


def ranking_table(frame: pd.DataFrame, label: str, family="ASI",
                  value_col="mean", name_col="adm2_name",
                  group_col: str | None = "adm1_name", top: int | None = None,
                  decimals: int = DECIMALS) -> pd.DataFrame:
    """Una fila por unidad, en el orden en que la figura las apila.

    Peor primero, que en el ASI es el valor más alto y en el VCI el más bajo.
    La figura las dibuja al revés porque una barra horizontal de Plotly crece
    de abajo hacia arriba; en una tabla el orden de lectura es el otro.
    """
    d = frame.dropna(subset=[value_col]) if len(frame) else frame
    if not len(d):
        return pd.DataFrame()
    peor_primero = family == "ASI"
    # El nombre desempata. Sin el, el orden entre municipios con la misma
    # cifra -y en el ASI el tope son ocho municipios en 100- depende de como
    # venga el panel, asi que el archivo publicado cambiaba de orden en
    # corridas que no cambiaban ninguna cifra.
    d = d.sort_values([value_col, name_col],
                      ascending=[not peor_primero, True])
    if top:
        d = d.head(top)
    nombres = {"adm2_name": "municipio", "adm1_name": "departamento"}
    out = pd.DataFrame({
        nombres.get(name_col, name_col): d[name_col].astype(str).values,
    })
    if group_col and group_col in d:
        out["departamento"] = d[group_col].astype(str).values
    out[label] = d[value_col].round(decimals).values
    # Aquí no se reparte la cifra entre las clases, aunque eso haría que la
    # barra publicada llevara el color de FAO como lo lleva la de la app.
    # Se probó: una columna por clase, la cifra en la suya y vacío en las
    # demás. Se descartó porque una clase sin ningún municipio en el dekad
    # deja su columna entera vacía, la herramienta de afuera la tipa como
    # texto y el gráfico deja de dibujarse. Y pasa de entrada: los
    # veinticinco municipios con más estrés están todos sobre 40, así que
    # tres de las cuatro columnas salen vacías el primer día.
    #
    # La barra publicada va entonces de un solo color, el del indicador. Es
    # menos de lo que muestra la app, que la pinta con el degradado, y es lo
    # que esta plantilla sabe sostener sin romperse.
    return out


def cover_table(crop: pd.DataFrame, pasture: pd.DataFrame, value_col="mean",
                family="ASI", group: bool = False,
                decimals: int = DECIMALS) -> pd.DataFrame:
    """Las dos coberturas de un dekad, una columna cada una.

    Es la tabla de la dispersión: cada fila es un municipio con su cifra de
    cultivo y la de pastizal. No se promedian ni se restan, que es la regla de
    las dos máscaras; acá conviven en columnas separadas por lo mismo.
    """
    if crop is None or pasture is None or not len(crop) or not len(pasture):
        return pd.DataFrame()
    llaves = ["adm2_code", "adm2_name", "adm1_name"]
    a = crop.dropna(subset=[value_col])[llaves + [value_col]]
    b = pasture.dropna(subset=[value_col])[llaves + [value_col]]
    d = a.merge(b, on=llaves, suffixes=("_c", "_p"))
    if not len(d):
        return pd.DataFrame()
    d = d.sort_values(f"{value_col}_c", ascending=False)
    out = pd.DataFrame({
        "municipio": d["adm2_name"].astype(str).values,
        "departamento": d["adm1_name"].astype(str).values,
        "cultivo": d[f"{value_col}_c"].round(decimals).values,
        "pastizal": d[f"{value_col}_p"].round(decimals).values,
    })
    if group:
        # Cuál de las dos está peor, con el mismo criterio que usa la figura:
        # una diferencia menor que la banda de clase más angosta no alcanza
        # para separarlas ni en la clase más estrecha de la leyenda, así que
        # cuenta como que coinciden. Es la columna por la que el gráfico de
        # afuera colorea, igual que la clase en el mapa.
        banda = narrowest_band(family)
        brecha = out["pastizal"] - out["cultivo"]
        out["grupo"] = SAME_LABEL
        out.loc[brecha > banda, "grupo"] = PASTURE_WORSE_LABEL
        out.loc[brecha < -banda, "grupo"] = CROP_WORSE_LABEL
    return out


def map_table(frame: pd.DataFrame, label: str, family="ASI", value_col="mean",
              code_col="adm2_code", name_col="adm2_name",
              group_col: str | None = "adm1_name",
              roster: pd.DataFrame | None = None, with_dekad: bool = False,
              decimals: int = DECIMALS) -> pd.DataFrame:
    """Una fila por unidad del mapa, con el código que empata la geometría.

    Es la misma tabla que pinta la coropleta de la app, que también colorea por
    `value_col` y localiza por `code_col`. Lo que cambia es que acá el código
    viaja como columna y no como índice: afuera la geometría es otra hoja de
    datos y el empate se declara entre las dos, columna contra columna.

    El código sale como texto a propósito. En la geometría de GAUL es una
    cadena -«17209»- y si una de las dos partes lo lee como número el empate
    falla en silencio y el mapa sale gris, que es el mismo modo de falla que
    tuvimos con los tipos de columna.

    El orden es por código y no por valor. Un mapa no se lee en orden, y
    anclarlo al código hace que el archivo solo cambie cuando cambian las
    cifras, no cuando cambia el ranking.
    """
    if not len(frame):
        return pd.DataFrame()
    if roster is not None and len(roster):
        # El padrón es la lista de polígonos que el mapa va a dibujar. Sin él,
        # una unidad que el panel no cubre -un departamento sin superficie de
        # cultivo, por ejemplo- no sale en la tabla, y entonces el mapa la
        # pinta del color de fondo. Reindexando contra el padrón, esa unidad
        # existe como fila y se puede nombrar.
        llaves = [c for c in (code_col, name_col, group_col)
                  if c and c in roster.columns]
        base = roster[llaves].copy()
        for c in llaves:
            base[c] = base[c].astype(str)
        aparte = frame.copy()
        for c in llaves:
            aparte[c] = aparte[c].astype(str)
        d = base.merge(aparte.drop(columns=[c for c in llaves if c in aparte
                                            and c != code_col]),
                       on=code_col, how="left")
    else:
        d = frame
    orden = ([code_col, "dekad_id"] if with_dekad and "dekad_id" in d
             else [code_col])
    d = d.sort_values(orden)
    nombres = {"adm2_name": "municipio", "adm1_name": "departamento"}
    out = pd.DataFrame({
        "código": d[code_col].astype(str).values,
        nombres.get(name_col, name_col): d[name_col].astype(str).values,
    })
    if with_dekad and "dekad_id" in d:
        # Con un rango el mapa se recorre dekad por dekad, así que una fila
        # por unidad no alcanza: la descarga tiene que decir de cuándo es
        # cada cifra.
        out["dekad"] = [dekad_label(c) for c in d["dekad_id"]]
    if group_col and group_col in d and group_col != name_col:
        out["departamento"] = d[group_col].astype(str).values
    out[label] = d[value_col].round(decimals).values
    # La clase va al lado de la cifra porque la escala de color de afuera no
    # sabe hacer el degradado de la app: interpola entre dos colores y los
    # cuatro de FAO no caben ahí. Coloreando por clase el mapa publicado dice
    # exactamente lo que dice la leyenda de FAO, y la cifra exacta sigue
    # estando, en la columna de al lado y en el globo.
    #
    # Y a diferencia de las demás tablas, acá el municipio sin dato se queda,
    # con la cifra vacía y la clase nombrada. Es lo contrario de rellenar con
    # ceros: la fila existe para poder decir que no hay dato. Si se la quita,
    # el mapa la pinta del color de fondo y un hueco blanco en un mapa de
    # sequía se lee como que ahí no pasa nada.
    clase = classify(d[value_col], family).astype(str)
    out["clase"] = clase.where(d[value_col].notna(), NO_DATA_LABEL).values
    return out
