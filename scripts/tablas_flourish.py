"""Escribe en `data/flourish/` las tablas que Flourish lee por URL.

Las arma `asis.wide`, el mismo módulo que alimenta el botón de cada figura en
la app, así que la cifra publicada y la dibujada no pueden divergir.

No son el mismo archivo, y conviene decir en qué se separan. El periodo: el
botón sigue el que la persona eligió en pantalla y acá no hay pantalla, así que
las series van completas y las figuras por unidad llevan su propia ventana.

Y la forma, siempre por lo mismo: la herramienta de afuera colorea por columna
y no por valor, de modo que lo que la figura codifica en el color aquí tiene
que viajar como columna. La anomalía va partida en dos por signo y con el año
para el filtro; el contraste de coberturas lleva el grupo; los mapas y los
mapas de calor llevan la clase; y los dos rankings reparten la cifra entre las
cuatro columnas de clase.

Los valores son los mismos en todos los casos: lo que cambia es cómo están
dispuestos. Las dos últimas son además una aproximación y no una copia: la
figura de la app colorea la barra y el mapa con el degradado continuo del
indicador, y afuera salen los cuatro intervalos planos de FAO, que es lo que
esa herramienta sabe pintar.

Las series nacionales y los mapas de calor van completos, con todo lo que hay
en el panel. Afuera el lector elige qué campañas mirar con el control de
series, y acotarlas en el archivo le quitaría esa posibilidad sin darle nada a
cambio: son veintitantas columnas de dieciocho filas.

Los rankings, los mapas y el contraste de coberturas son otra cosa: la foto de
un instante, no una serie, y van con el último dekad publicado.

Lo corre el workflow diario después de construir y antes de commitear, de modo
que los CSV viajan en el mismo commit que los datos de los que salen. Como todo
se ancla al panel, los archivos solo cambian cuando llega un dekad nuevo: no
generan commits de ruido.

Uso:

    python -m scripts.tablas_flourish
    python scripts/tablas_flourish.py --salida otra/carpeta
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd                                            # noqa: E402

from asis import config as cfg, panel, wide                    # noqa: E402
from asis.aggregate import (climatology_frame, season_columns,  # noqa: E402
                            to_country, to_department)
from asis.calendar import dekad_of_year                         # noqa: E402

SALIDA = cfg.DATA / "flourish"

# Los nombres de archivo son parte de la interfaz: un grafico publicado apunta
# a uno de ellos y se rompe en silencio si cambian. No se renombran sin mirar
# que gráficos los están usando.
SERIES_NACIONALES = {
    "asi_gs1": "serie_nacional_asi_primera.csv",
    "asi_gs2": "serie_nacional_asi_postrera.csv",
    "vci": "serie_nacional_vci.csv",
}
MAPAS_CALOR = {
    "asi_gs1": "mapa_calor_asi_primera.csv",
    "asi_gs2": "mapa_calor_asi_postrera.csv",
}
LLUVIA = "lluvia_nacional.csv"
ANOMALIA = "lluvia_anomalia.csv"
RANKING_MUNI = "ranking_municipios.csv"
RANKING_DEPT = "ranking_departamentos.csv"
COBERTURAS = "coberturas.csv"
MAPA_MUNI = "mapa_municipios.csv"
MAPA_DEPT = "mapa_departamentos.csv"
GEOMETRIA_MUNI = "geometria_municipios.csv"
GEOMETRIA_DEPT = "geometria_departamentos.csv"

TOP_MUNICIPIOS = 25

# Las figuras por unidad -la rejilla, el mapa de calor municipal- no caben
# enteras: treinta municipios por ochocientos dekads son veinticuatro mil
# filas. Llevan ventana, y son dieciocho meses, los mismos que la app abre
# por defecto a nivel pais.
VENTANA_UNIDADES = 54
TOP_REJILLA = 30
SUPERFICIE = {
    "asi_gs1": "superficie_clase_asi_primera.csv",
    "asi_gs2": "superficie_clase_asi_postrera.csv",
}
MAPA_CALOR_MUNI = "mapa_calor_municipios.csv"
REJILLA_DEPT = "rejilla_departamentos.csv"
REJILLA_COBERTURAS = "rejilla_coberturas.csv"


def _geometria(salida: Path, nivel: str, archivo: str) -> str:
    """La geometría de un nivel en la forma que espera la hoja de geometría.

    Una fila por unidad, el polígono serializado en una celda y el código al
    lado. Es el mismo polígono de `data/geo/<nivel>.geojson`, que es la fuente;
    esto es solo otra serialización, como el resto de esta carpeta es otra
    forma de las tablas del panel.

    No cambia nunca, pero se escribe en cada corrida igual que las demás:
    es determinista, así que git no ve diferencia, y dejarla fuera obligaría a
    acordarse de regenerarla el día que la geometría se simplifique distinto.
    """
    origen = cfg.DATA / "geo" / f"{nivel}.geojson"
    clave = "adm2_code" if nivel == "municipios" else "adm1_code"
    if not origen.exists():
        return f"   ! {archivo}: no hay geometría, no se escribe"
    g = json.loads(origen.read_text(encoding="utf-8"))
    destino = salida / archivo
    with destino.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator=chr(10))
        w.writerow(["geometria", "código"])
        for f in g["features"]:
            w.writerow([json.dumps(f["geometry"], separators=(",", ":")),
                        f["properties"][clave]])
    kb = destino.stat().st_size // 1024
    return f"   {destino.name}: {len(g['features'])} filas, {kb} KB"


def _padron(nivel: str):
    """La lista de unidades que el mapa va a dibujar, con su nombre."""
    clave = "adm2_code" if nivel == "municipios" else "adm1_code"
    ruta = cfg.DATA / "geo" / f"{nivel}.csv"
    if not ruta.exists():
        return None
    return pd.read_csv(ruta, dtype={clave: str})


def _escribir(tabla, destino: Path) -> str:
    if not len(tabla):
        return f"   ! {destino.name}: sin datos, no se escribe"
    # utf-8 pelado, sin BOM. La tentacion es ponerlo para que Excel no parta
    # los acentos, pero estos archivos no los abre Excel: los lee Flourish por
    # URL. Y un BOM al frente puede terminar pegado al primer encabezado -
    # "﻿dekad" en vez de "dekad"-, que deja el grafico apuntando a una
    # columna que no existe. Para abrirlos a mano esta la descarga de la app.
    tabla.to_csv(destino, index=False, encoding="utf-8")
    return f"   {destino.name}: {len(tabla)} filas, {len(tabla.columns)} columnas"


def construir(salida: Path = SALIDA) -> list[str]:
    salida.mkdir(parents=True, exist_ok=True)
    lineas = []

    fin = max(panel.dekads(s)[-1] for s in panel.stored_series())
    lineas.append(f"ultimo dekad: {fin}")

    # Las series nacionales van completas, no acotadas a una ventana. Afuera
    # el lector elige qué campañas mirar con el control de series, y una
    # ventana fija en el archivo le quita esa posibilidad sin darle nada a
    # cambio: son veintitrés columnas de dieciocho filas, no pesa nada.
    for sid, archivo in SERIES_NACIONALES.items():
        if sid not in panel.stored_series():
            continue
        propios = panel.dekads(sid)
        df = panel.load(sid, propios[0], propios[-1])
        if df.empty:
            continue
        season = cfg.SERIES[sid].season
        frame = climatology_frame(to_country(df), season)
        if season:
            frame = frame[frame["dekad_of_year"].isin(season_columns(season))]
        lineas.append(_escribir(
            wide.season_table(frame, season, drop_partial_start=True),
            salida / archivo))

    # Los mapas de calor van sobre el panel entero y no sobre la ventana.
    # Es la unica excepcion de esta carpeta y tiene un motivo: la matriz
    # existe para situar la campania en curso entre todas las anteriores, y
    # con dieciocho meses son dos filas, que no es una matriz. La app hace lo
    # mismo cuando se le amplia la ventana; aca la ventana no se elige, asi
    # que se publica la historia completa.
    for sid, archivo in MAPAS_CALOR.items():
        if sid not in panel.stored_series():
            continue
        todos = panel.dekads(sid)
        df = panel.load(sid, todos[0], todos[-1])
        if df.empty:
            continue
        season = cfg.SERIES[sid].season
        frame = climatology_frame(to_country(df), season)
        frame = frame[frame["dekad_of_year"].isin(season_columns(season))]
        lineas.append(_escribir(
            wide.heatmap_table(frame, season, cfg.SERIES[sid].unit_short),
            salida / archivo))

    # Superficie por clase: una fila por dekad de la temporada, las cuatro
    # clases en columnas y la campania al lado para separar los paneles.
    for sid, archivo in SUPERFICIE.items():
        if sid not in panel.stored_series():
            continue
        propios = panel.dekads(sid)
        df = panel.load(sid, propios[0], propios[-1])
        season = cfg.SERIES[sid].season
        df = df[[dekad_of_year(d) in season_columns(season)
                 for d in df["dekad_id"]]]
        if df.empty:
            continue
        lineas.append(_escribir(
            wide.severity_table(df, cfg.SERIES[sid].family, season),
            salida / archivo))

    # Las figuras por unidad, con ventana.
    if "asi_gs1" in panel.stored_series():
        propios = panel.dekads("asi_gs1")
        tramo = propios[-VENTANA_UNIDADES:]
        v = panel.load("asi_gs1", tramo[0], tramo[-1])
        unidad = cfg.SERIES["asi_gs1"].unit_short
        peor = (v.groupby("adm2_code", observed=True)["mean"].max()
                 .nlargest(TOP_REJILLA).index)
        lineas.append(_escribir(
            wide.unit_series_table(v[v["adm2_code"].isin(peor)], unidad,
                                   with_class=True),
            salida / MAPA_CALOR_MUNI))
        lineas.append(_escribir(
            wide.unit_series_table(to_department(v), unidad,
                                   name_col="adm1_name", group_col=None),
            salida / REJILLA_DEPT))
        if "asi_gs1_pasto" in panel.stored_series():
            pastos = panel.dekads("asi_gs1_pasto")
            desde = max(tramo[0], pastos[0])
            lineas.append(_escribir(
                wide.cover_grid_table(
                    v[v["adm2_code"].isin(peor)],
                    panel.load("asi_gs1_pasto", desde, tramo[-1])),
                salida / REJILLA_COBERTURAS))

    lluvia = panel.national("serie_nacional_lluvia")
    if len(lluvia):
        v = lluvia
        lta = v.groupby("dekad_of_year")["lta"].mean()
        lineas.append(_escribir(
            wide.season_table(v, None, value_col="value", reference=lta,
                              reference_label="promedio de largo plazo"),
            salida / LLUVIA))
        lineas.append(_escribir(wide.anomaly_table(v, split_sign=True,
                                               year_column=True),
                                salida / ANOMALIA))

    # Los rankings y el contraste son del ultimo dekad del ASI de la primera,
    # que es el indicador principal de la app.
    muni = panel.load("asi_gs1", fin, fin)
    if muni.empty:                    # el ultimo dekad puede ser de otra serie
        ultimo_asi = panel.dekads("asi_gs1")[-1]
        muni = panel.load("asi_gs1", ultimo_asi, ultimo_asi)
    if len(muni):
        unidad = cfg.SERIES["asi_gs1"].unit_short
        dep = to_department(muni)
        lineas.append(_escribir(
            wide.ranking_table(muni, unidad, top=TOP_MUNICIPIOS,
                               spread_class=True),
            salida / RANKING_MUNI))
        lineas.append(_escribir(
            wide.ranking_table(dep, unidad, name_col="adm1_name",
                               group_col=None, spread_class=True),
            salida / RANKING_DEPT))
        # El mapa es el mismo corte que los rankings, con el codigo que
        # empata la geometria, y al lado la geometria misma: el grafico de
        # afuera la lee como una segunda hoja de datos, asi que tiene que
        # estar publicada igual que las cifras.
        lineas.append(_escribir(
            wide.map_table(muni, unidad, roster=_padron("municipios")),
            salida / MAPA_MUNI))
        lineas.append(_geometria(salida, "municipios", GEOMETRIA_MUNI))
        lineas.append(_escribir(
            wide.map_table(dep, unidad, code_col="adm1_code",
                           name_col="adm1_name", group_col=None,
                           roster=_padron("departamentos")),
            salida / MAPA_DEPT))
        lineas.append(_geometria(salida, "departamentos", GEOMETRIA_DEPT))
        dekad = muni["dekad_id"].iloc[0]
        pasto = panel.load("asi_gs1_pasto", dekad, dekad) \
            if "asi_gs1_pasto" in panel.stored_series() else None
        if pasto is not None:
            lineas.append(_escribir(wide.cover_table(muni, pasto, group=True),
                                    salida / COBERTURAS))
    return lineas


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m scripts.tablas_flourish",
        description="Escribe las tablas anchas que Flourish lee por URL.")
    p.add_argument("--salida", type=Path, default=SALIDA)
    args = p.parse_args(argv)
    if not panel.stored_series():
        print("no hay panel construido")
        return 1
    for linea in construir(args.salida):
        print(linea)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
