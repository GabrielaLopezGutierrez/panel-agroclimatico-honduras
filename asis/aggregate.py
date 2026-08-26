"""Agregación de municipio a departamento y a país, y series derivadas.

Solo se guarda el nivel municipal. Departamental y nacional se derivan al vuelo
aquí, ponderando por píxeles válidos. Guardar los tres niveles serían tres
oportunidades de quedar inconsistentes y ninguna ganancia perceptible.

Este módulo es pandas puro: lo usan igual la app y el constructor.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from asis import config as cfg
from asis.calendar import dekad_date, dekad_of_year

KEY_COLS = ["adm2_code", "adm2_name", "adm1_code", "adm1_name"]
# Los percentiles municipales no se pueden promediar: el p90 de un departamento
# no es el promedio de los p90 de sus municipios. Se descartan al agregar en vez
# de publicar una cifra que no significa lo que parece.
NON_AGGREGABLE = ["p10", "median", "p90"]


def classify(values, family="ASI"):
    """Clase de severidad según los cortes oficiales de FAO."""
    cuts, labels, _ = cfg.CLASSES[family]
    return pd.cut(values, cuts, labels=labels, right=False)


def _aggregate(df, by, value_col="mean", weight_col="n_px"):
    """Media ponderada por píxeles válidos, más superficie por umbral.

    Promediar medias municipales sin ponderar sobreestima los municipios chicos.
    Las columnas km2_* son sumables, y de ellas se recalcula el porcentaje: eso
    permite conservar los umbrales de severidad al subir de nivel.
    """
    d = df.dropna(subset=[value_col]).copy()
    if d.empty:
        return d
    d["_num"] = d[value_col] * d[weight_col]
    km2_cols = [c for c in d.columns
                if c.startswith("km2_") and c != "km2"]
    spec = {"_num": ("_num", "sum"), "n_px": (weight_col, "sum"),
            "km2": ("km2", "sum"), "n_muni": ("adm2_code", "nunique")}
    for c in km2_cols:
        spec[c] = (c, "sum")
    g = d.groupby(by, as_index=False, observed=True).agg(**spec)
    g[value_col] = g["_num"] / g["n_px"].replace(0, np.nan)
    for c in km2_cols:
        pct = "pct_" + c.removeprefix("km2_")
        g[pct] = np.round(100 * g[c] / g["km2"].replace(0, np.nan), 1)
    g[value_col] = g[value_col].round(3)
    g["date"] = g["dekad_id"].map(dekad_date)
    return g.drop(columns="_num")


def to_department(df, value_col="mean", weight_col="n_px"):
    """Serie departamental ponderada por píxeles válidos."""
    return _aggregate(df, ["adm1_code", "adm1_name", "dekad_id"],
                      value_col, weight_col)


def to_country(df, value_col="mean", weight_col="n_px"):
    """Serie nacional ponderada por píxeles válidos, no por municipio."""
    return _aggregate(df, ["dekad_id"], value_col, weight_col)


def at_level(df, level: str, value_col="mean"):
    """Punto de entrada único de la app: municipio, departamento o país."""
    if level == "municipio":
        return df
    if level == "departamento":
        return to_department(df, value_col)
    if level == "pais":
        return to_country(df, value_col)
    raise ValueError(f"nivel desconocido: {level}")


def worst_case(*panels, value_col="mean"):
    """Une las dos temporadas del ASI conservando el peor caso vigente.

    En los dekads en que la primera y la postrera están activas a la vez se toma
    el ASI máximo, criterio conservador para alerta temprana, y se deja
    registrado de qué temporada viene la cifra.
    """
    frames = [p for p in panels if p is not None and len(p)]
    if not frames:
        return pd.DataFrame()
    out = (pd.concat(frames, ignore_index=True)
           .dropna(subset=[value_col])
           .sort_values(["adm2_code", "dekad_id", value_col],
                        ascending=[True, True, False])
           .drop_duplicates(["adm2_code", "dekad_id"], keep="first")
           .reset_index(drop=True))
    out["series"] = cfg.ASI_COMBINED
    return out.sort_values(["dekad_id", "adm1_name", "adm2_name"]).reset_index(
        drop=True)


def severity_area(df, family="ASI", value_col="mean"):
    """km2 en cada clase de severidad por dekad. Responde cuánta superficie y
    no solo cuán intenso."""
    _, labels, _ = cfg.CLASSES[family]
    d = df.dropna(subset=[value_col]).copy()
    d["clase"] = classify(d[value_col], family).astype(str)
    g = (d.groupby(["dekad_id", "clase"], as_index=False, observed=True)["km2"]
          .sum()
          .pivot(index="dekad_id", columns="clase", values="km2")
          .reindex(columns=labels)
          .fillna(0.0))
    return g


def department_weights(panel: pd.DataFrame) -> pd.Series:
    """Área de cultivo por departamento, en píxeles válidos del ráster.

    Es el peso con el que se agrega la serie departamental que publica GIEWS:
    ponderar por número de departamentos le daría a Islas de la Bahía el mismo
    peso que a Olancho. Se toma del dekad con más cobertura para que el peso no
    dependa de un dekad flojo.
    """
    if panel.empty:
        return pd.Series(dtype="float64")
    per_dekad = panel.groupby("dekad_id", observed=True)["n_px"].sum()
    ref = per_dekad.idxmax()
    return (panel[panel["dekad_id"] == ref]
            .groupby("adm1_code", observed=True)["n_px"].sum())


def national_from_csv(csv: pd.DataFrame, weights: pd.Series,
                      value_col="Data", lta_col=None) -> pd.DataFrame:
    """Serie nacional a partir del CSV departamental oficial de GIEWS.

    Este es el dato de FAO, no un agregado propio, y es la referencia contra la
    cual se valida el agregado municipal. Cuando el CSV trae promedio de largo
    plazo se conserva tal cual: la LTA es la referencia oficial de GIEWS y no se
    recalcula.
    """
    d = csv.dropna(subset=[value_col]).copy()
    d["adm1_code"] = d["ADM1_CODE"].astype("Int64").astype(str)
    d["weight"] = d["adm1_code"].map(weights).astype("float64").fillna(0.0)
    d["_num"] = d[value_col] * d["weight"]
    spec = {"_num": ("_num", "sum"), "weight": ("weight", "sum")}
    if lta_col and lta_col in d:
        d["_lta"] = d[lta_col] * d["weight"]
        spec["_lta"] = ("_lta", "sum")
    g = (d.groupby(["Year", "Month", "Dekad", "dekad_id"], as_index=False,
                   observed=True).agg(**spec))
    w = g["weight"].replace(0, np.nan)
    g["value"] = g["_num"] / w
    drop = ["_num"]
    if lta_col and lta_col in d:
        g["lta"] = g["_lta"] / w
        g["anom_pct"] = 100 * (g["value"] / g["lta"].replace(0, np.nan) - 1)
        drop.append("_lta")
    g["dekad_of_year"] = g["dekad_id"].map(dekad_of_year)
    g["date"] = g["dekad_id"].map(dekad_date)
    return (g.drop(columns=drop)
             .sort_values(["Year", "dekad_of_year"])
             .reset_index(drop=True))


def climatology(national: pd.DataFrame, dekad_from=13, dekad_to=30,
                year_max=None, value_col="value"):
    """Percentiles por dekad del año sobre la ventana de análisis.

    Devuelve p10, p50 y p90 y cuántos años los sostienen, porque una franja
    dibujada sobre catorce años no dice lo mismo que sobre cincuenta.
    """
    d = national[national["dekad_of_year"].between(dekad_from, dekad_to)]
    if year_max is not None:
        d = d[d["Year"] < year_max]
    if d.empty:
        return pd.DataFrame(), 0
    pctl = (d.groupby("dekad_of_year")[value_col]
             .quantile([.1, .5, .9]).unstack())
    pctl.columns = ["p10", "p50", "p90"]
    return pctl.reset_index(), int(d["Year"].nunique())
