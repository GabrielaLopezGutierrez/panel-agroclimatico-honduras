"""Geometrías GAUL y estadística zonal vectorizada.

Convierte un ráster de ~1 km en una fila por municipio. Es la única parte del
proyecto que necesita rasterio y geopandas, y solo corre en la construcción: la
app lee el resultado ya calculado.

La malla de zonas se arma una vez y se reutiliza para todos los dekads, que es
lo que hace viable recorrer veinte años de rásteres.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_origin

from asis import config as cfg
from asis.calendar import dekad_date
from asis.client import SNAP, export_tifs, raster_name, session

TRANSFORM = from_origin(SNAP["bbox"][0], SNAP["bbox"][3],
                        cfg.GRID_STEP, cfg.GRID_STEP)
SHAPE = (SNAP["height"], SNAP["width"])


def gaul_gdf(level=2, adm0=cfg.GAUL_COUNTRY) -> gpd.GeoDataFrame:
    """Límites administrativos GAUL 2015 en EPSG:4326.

    srsName es obligatorio: sin él, el WFS entrega Web Mercator en silencio.
    """
    cache_dir = cfg.CACHE / "geo"
    cache_dir.mkdir(parents=True, exist_ok=True)
    p = cache_dir / f"gaul_{level}_{adm0.lower().replace(' ', '_')}.geojson"
    if not p.exists():
        r = session().get(cfg.WFS_GAUL, timeout=300, params={
            "service": "WFS", "version": "2.0.0", "request": "GetFeature",
            "typeNames": f"gaul:g2015_2014_{level}",
            "outputFormat": "application/json", "srsName": "EPSG:4326",
            "CQL_FILTER": f"adm0_name='{adm0}'"})
        r.raise_for_status()
        p.write_text(r.text, encoding="utf-8")
    g = gpd.read_file(p).set_crs(4326, allow_override=True)
    # GAUL trae astillas sin nombre en los dos niveles. Hay que quitarlas en
    # ambos: la de nivel 1 no aparece en el nivel 2, y si no se filtra la app
    # ofrece un departamento fantasma en el selector.
    if "adm2_name" in g.columns:
        g = g[g["adm2_name"] != "Name Unknown"].copy()   # astilla de ~3 km2
        g["adm2_code"] = g["adm2_code"].astype("int64").astype(str)
    if "adm1_name" in g.columns:
        g = g[g["adm1_name"] != "Name Unknown"].copy()
    if "adm1_code" in g.columns:
        g["adm1_code"] = g["adm1_code"].astype("int64").astype(str)
    g = g.sort_values([c for c in ("adm1_name", "adm2_name") if c in g.columns])
    return g.reset_index(drop=True)


def build_zones(gdf) -> np.ndarray:
    """id de municipio por píxel (0 = fuera). Los municipios que no capturan
    ningún centro de píxel se rellenan con all_touched para no perderlos: son
    los más chicos y son justo los que un promedio nacional ya invisibiliza."""
    nz = len(gdf)
    z = rasterize(((geom, i + 1) for i, geom in enumerate(gdf.geometry)),
                  out_shape=SHAPE, transform=TRANSFORM, fill=0,
                  dtype="int32", all_touched=False)
    counts = np.bincount(z.ravel(), minlength=nz + 1)
    orphans = np.where(counts[1:] == 0)[0]
    for i in orphans:
        extra = rasterize([(gdf.geometry.iloc[i], 1)], out_shape=SHAPE,
                          transform=TRANSFORM, fill=0, dtype="int32",
                          all_touched=True)
        z = np.where((z == 0) & (extra == 1), i + 1, z)
    return z


@dataclass
class Grid:
    """Municipios, departamentos y la malla de zonas que los liga al ráster."""
    muni: gpd.GeoDataFrame
    dept: gpd.GeoDataFrame
    zones: np.ndarray

    @property
    def nz(self) -> int:
        return len(self.muni)


@cache
def grid() -> Grid:
    """Se construye una sola vez por proceso: descarga GAUL, calcula áreas y
    rasteriza. Cuesta unos segundos y lo pagan todos los dekads."""
    muni = gaul_gdf(2)
    dept = gaul_gdf(1)
    # Área real en proyección igual-área, no en grados.
    muni["area_km2"] = (muni.to_crs(6933).area / 1e6).round(2)
    zones = build_zones(muni)
    muni["zone_px"] = np.bincount(zones.ravel(),
                                  minlength=len(muni) + 1)[1:]
    return Grid(muni=muni, dept=dept, zones=zones)


def read_tif(path) -> np.ndarray:
    with rasterio.open(path) as src:
        a = src.read(1, out_dtype="float32")
        nd = src.nodata
    a = a.astype("float64")
    if nd is not None:
        a[a == nd] = np.nan
    a[a <= cfg.NODATA + 1] = np.nan          # NoData explícito de exportImage
    return a


def zonal_stats(arr, valid, g: Grid | None = None, thresholds_gt=(),
                thresholds_lt=(), nbins=100) -> pd.DataFrame:
    """Estadística por municipio en tres pasadas vectorizadas.

    Devuelve n_px, km2, media, mediana, p10, p90 y superficie por umbral. Solo
    entran píxeles dentro del rango válido del indicador: las banderas 251-255
    nunca contaminan la media.
    """
    g = g or grid()
    zones, nz = g.zones, g.nz
    lo, hi = valid
    ok = np.isfinite(arr) & (zones > 0) & (arr >= lo) & (arr <= hi)
    zone = zones[ok] - 1
    values = arr[ok]
    n = np.bincount(zone, minlength=nz).astype("float64")
    total = np.bincount(zone, weights=values, minlength=nz)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = np.where(n > 0, total / np.maximum(n, 1), np.nan)
    # histograma zona x bin -> cuantiles sin ordenar (coste lineal)
    bins = np.linspace(lo, hi, nbins + 1)
    binned = np.clip(np.digitize(values, bins) - 1, 0, nbins - 1)
    hist = np.bincount(zone * nbins + binned,
                       minlength=nz * nbins).reshape(nz, nbins)
    cum = hist.cumsum(axis=1)
    cum_total = np.maximum(cum[:, -1:], 1)
    centers = (bins[:-1] + bins[1:]) / 2

    def quantile_at(q):
        idx = (cum >= cum_total * q).argmax(axis=1)
        return np.where(n > 0, centers[idx], np.nan)

    out = {"n_px": n.astype("int32"),
           "km2": np.round(n * cfg.PIX_KM2, 1),
           "mean": np.round(mean, 3),
           "p10": np.round(quantile_at(0.10), 3),
           "median": np.round(quantile_at(0.50), 3),
           "p90": np.round(quantile_at(0.90), 3)}
    for t in thresholds_gt:
        c = np.bincount(zone, weights=(values > t).astype("float64"),
                        minlength=nz)
        out[f"pct_gt{t}"] = np.round(
            np.where(n > 0, 100 * c / np.maximum(n, 1), np.nan), 1)
        out[f"km2_gt{t}"] = np.round(c * cfg.PIX_KM2, 1)
    for t in thresholds_lt:
        c = np.bincount(zone, weights=(values < t).astype("float64"),
                        minlength=nz)
        out[f"pct_lt{t}"] = np.round(
            np.where(n > 0, 100 * c / np.maximum(n, 1), np.nan), 1)
        out[f"km2_lt{t}"] = np.round(c * cfg.PIX_KM2, 1)
    df = pd.DataFrame(out)
    df.insert(0, "adm2_code", g.muni["adm2_code"].values)
    df.insert(1, "adm2_name", g.muni["adm2_name"].values)
    df.insert(2, "adm1_name", g.muni["adm1_name"].values)
    df.insert(3, "adm1_code", g.muni["adm1_code"].values)
    df.loc[df["n_px"] == 0, ["mean", "p10", "median", "p90"]] = np.nan
    return df


def municipal_series(series: cfg.Series, dekads, workers=None, verbose=True,
                     overwrite=False) -> pd.DataFrame:
    """Panel municipio x dekad de una serie, en formato largo.

    Los dekads sin ráster publicado simplemente no aparecen: nunca se inventan
    filas ni se rellenan con ceros. Sin dato no es cero.
    """
    dekads = list(dekads)
    names = [raster_name(series.svc, dk, series.suffix) for dk in dekads]
    paths, _missing = export_tifs(series.svc, names, workers=workers,
                                  verbose=verbose, overwrite=overwrite)
    g = grid()
    parts = []
    for dk, name in zip(dekads, names):
        if name not in paths:
            continue
        d = zonal_stats(read_tif(paths[name]), series.valid_range, g,
                        series.thresholds_gt, series.thresholds_lt)
        d["dekad_id"] = dk
        parts.append(d)
    if not parts:
        return pd.DataFrame()
    out = pd.concat(parts, ignore_index=True)
    out["date"] = out["dekad_id"].map(dekad_date)
    out["series"] = series.id
    out["season"] = series.season
    assert not out.duplicated(["adm2_code", "dekad_id"]).any(), \
        f"{series.id}: hay filas duplicadas municipio-dekad"
    return (out.sort_values(["dekad_id", "adm1_name", "adm2_name"])
               .reset_index(drop=True))


def export_geometry(tol=cfg.GEOJSON_TOL) -> tuple[dict, pd.DataFrame]:
    """Geometría municipal simplificada y tabla de referencia de municipios.

    Se versiona en data/geo/ para que la app dibuje coropletas sin geopandas ni
    red. A 0,004 grados (~400 m) la forma se mantiene y el archivo pesa unas
    diez veces menos.
    """
    g = grid()
    gj = g.muni[["adm2_code", "adm2_name", "adm1_code", "adm1_name",
                 "geometry"]].copy()
    gj["geometry"] = gj.geometry.simplify(tol, preserve_topology=True)
    geojson = json.loads(gj.to_json())
    ref = (g.muni[["adm2_code", "adm2_name", "adm1_code", "adm1_name",
                   "area_km2", "zone_px"]]
           .sort_values(["adm1_name", "adm2_name"]).reset_index(drop=True))
    return geojson, ref
