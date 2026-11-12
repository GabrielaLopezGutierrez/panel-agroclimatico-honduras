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

from asis.aggregate import classify, season_columns
from asis.calendar import (dekad_label, dekad_labels, dekad_window,
                           season_labels)

# Dos decimales en todo. Flourish formatea la presentación por su cuenta -el
# separador decimal y el de miles se fijan en su pestaña Datos-, así que lo
# único que hay que decidir aquí es cuánta precisión se afirma. Más decimales
# no son más exactitud: la media ponderada del ASI no la tiene, y el CSV de
# departamentos del repo, escrito sin redondear, publica cosas como
# 4420.590000000001, que es ruido de punto flotante en pantalla.
DECIMALS = 2

# Dieciocho meses son cincuenta y cuatro dekads.
WINDOW_DEKADS = 54

# El municipio sin dato del mapa. Es una clase más y no un hueco: una
# herramienta de afuera pinta de blanco lo que no encuentra, y en un mapa de
# sequía un hueco blanco se lee como calma. Nombrándolo, entra a la leyenda.
NO_DATA_LABEL = "sin dato"


def window(last: str, dekads: int = WINDOW_DEKADS) -> tuple[str, str]:
    """La ventana móvil que publican los archivos vivos.

    Se cuenta hacia atrás desde el último dekad publicado y no desde una fecha
    del calendario: el archivo lo escribe un proceso sin interfaz, y anclarlo al
    dato hace que la ventana avance sola y solo cuando hay dato nuevo.
    """
    tramo = dekad_window(last, dekads)
    return tramo[0], tramo[-1]


def season_table(frame: pd.DataFrame, season: str | None, value_col="mean",
                 reference: pd.Series | None = None, reference_label="",
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
    anios = list(m.columns)
    m.columns = season_labels(anios, columnas)
    if reference is not None and len(reference):
        m[reference_label or "referencia"] = [
            reference.get(c, float("nan")) for c in orden]
    m.index = dekad_labels(orden)
    out = m.round(decimals).reset_index()
    out.columns = ["dekad", *list(out.columns)[1:]]
    return out


def anomaly_table(frame: pd.DataFrame, value_col="anom_pct",
                  label="anomalía (%)",
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
    return pd.DataFrame({
        "fecha": pd.to_datetime(d["date"]).dt.date.values,
        "dekad": [dekad_label(c) for c in d["dekad_id"]],
        label: d[value_col].round(decimals).values,
    })


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
    return out


def cover_table(crop: pd.DataFrame, pasture: pd.DataFrame, value_col="mean",
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
    return pd.DataFrame({
        "municipio": d["adm2_name"].astype(str).values,
        "departamento": d["adm1_name"].astype(str).values,
        "cultivo": d[f"{value_col}_c"].round(decimals).values,
        "pastizal": d[f"{value_col}_p"].round(decimals).values,
    })


def map_table(frame: pd.DataFrame, label: str, family="ASI", value_col="mean",
              code_col="adm2_code", name_col="adm2_name",
              group_col: str | None = "adm1_name",
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
    d = frame.sort_values(code_col)
    nombres = {"adm2_name": "municipio", "adm1_name": "departamento"}
    out = pd.DataFrame({
        "código": d[code_col].astype(str).values,
        nombres.get(name_col, name_col): d[name_col].astype(str).values,
    })
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
