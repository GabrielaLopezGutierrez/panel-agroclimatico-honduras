"""Escribe en `data/flourish/` las tablas que Flourish lee por URL.

Son los mismos objetos que entrega el botón de cada figura en la app: las arma
`asis.wide`, así que la cifra publicada y la dibujada no pueden divergir. Lo
único que cambia es la ventana, y cambia por un motivo concreto: el botón sigue
el periodo que la persona eligió en pantalla, y acá no hay pantalla. La ventana
se fija en el archivo, dieciocho meses contados hacia atrás desde el último
dekad publicado.

Tres de los nueve archivos no llevan ventana sino el último dekad: los rankings
y el mapa son la foto de un instante, no una serie, y "los últimos dieciocho
meses" no significa nada para ellos. Se actualizan igual, cada vez que llega un
dekad.

Lo corre el workflow diario después de construir y antes de commitear, de modo
que los CSV viajan en el mismo commit que los datos de los que salen. Como la
ventana se ancla al último dekad publicado, los archivos solo cambian cuando
llega un dekad nuevo: no generan commits de ruido.

Uso:

    python -m scripts.tablas_flourish
    python scripts/tablas_flourish.py --salida otra/carpeta
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from asis import config as cfg, panel, wide                    # noqa: E402
from asis.aggregate import (climatology_frame, season_columns,  # noqa: E402
                            to_country, to_department)

SALIDA = cfg.DATA / "flourish"

# Los nombres de archivo son parte de la interfaz: un grafico publicado apunta
# a uno de ellos y se rompe en silencio si cambian. No se renombran sin mirar
# que gráficos los están usando.
SERIES_NACIONALES = {
    "asi_gs1": "serie_nacional_asi_primera.csv",
    "asi_gs2": "serie_nacional_asi_postrera.csv",
    "vci": "serie_nacional_vci.csv",
}
LLUVIA = "lluvia_nacional.csv"
ANOMALIA = "lluvia_anomalia.csv"
RANKING_MUNI = "ranking_municipios.csv"
RANKING_DEPT = "ranking_departamentos.csv"
COBERTURAS = "coberturas.csv"
MAPA_MUNI = "mapa_municipios.csv"

TOP_MUNICIPIOS = 25


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

    ultimo = max(panel.dekads(s)[-1] for s in panel.stored_series())
    inicio, fin = wide.window(ultimo)
    lineas.append(f"ventana: {inicio} a {fin} ({wide.WINDOW_DEKADS} dekads)")

    for sid, archivo in SERIES_NACIONALES.items():
        if sid not in panel.stored_series():
            continue
        df = panel.load(sid, inicio, fin)
        if df.empty:
            continue
        season = cfg.SERIES[sid].season
        frame = climatology_frame(to_country(df), season)
        if season:
            frame = frame[frame["dekad_of_year"].isin(season_columns(season))]
        lineas.append(_escribir(wide.season_table(frame, season),
                                salida / archivo))

    lluvia = panel.national("serie_nacional_lluvia")
    if len(lluvia):
        v = lluvia[(lluvia["dekad_id"] >= inicio) & (lluvia["dekad_id"] <= fin)]
        lta = v.groupby("dekad_of_year")["lta"].mean()
        lineas.append(_escribir(
            wide.season_table(v, None, value_col="value", reference=lta,
                              reference_label="promedio de largo plazo"),
            salida / LLUVIA))
        lineas.append(_escribir(wide.anomaly_table(v), salida / ANOMALIA))

    # Los rankings y el contraste son del ultimo dekad del ASI de la primera,
    # que es el indicador principal de la app.
    muni = panel.load("asi_gs1", fin, fin)
    if muni.empty:                    # el ultimo dekad puede ser de otra serie
        ultimo_asi = panel.dekads("asi_gs1")[-1]
        muni = panel.load("asi_gs1", ultimo_asi, ultimo_asi)
    if len(muni):
        unidad = cfg.SERIES["asi_gs1"].unit_short
        lineas.append(_escribir(
            wide.ranking_table(muni, unidad, top=TOP_MUNICIPIOS),
            salida / RANKING_MUNI))
        lineas.append(_escribir(
            wide.ranking_table(to_department(muni), unidad,
                               name_col="adm1_name", group_col=None),
            salida / RANKING_DEPT))
        # El mapa es el mismo corte que los rankings, con el codigo que
        # empata la geometria. La geometria no viaja por aca: vive en
        # data/geo/municipios.geojson, no cambia nunca y se sube una sola vez
        # a la hoja de geometria del grafico.
        lineas.append(_escribir(wide.map_table(muni, unidad),
                                salida / MAPA_MUNI))
        dekad = muni["dekad_id"].iloc[0]
        pasto = panel.load("asi_gs1_pasto", dekad, dekad) \
            if "asi_gs1_pasto" in panel.stored_series() else None
        if pasto is not None:
            lineas.append(_escribir(wide.cover_table(muni, pasto),
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
