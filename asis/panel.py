"""Lectura del panel versionado. Es todo lo que la app necesita.

El panel municipal se construye fuera de línea y se versiona en
`data/municipal/<serie>/<año>.parquet`. Aquí se lee del disco: sin red, sin
autenticación y sin credenciales. Un analista que abre la app no espera minutos
frente a una pantalla en blanco mientras se descargan rásteres.

El código de dekad `YYYY-MM-Dn` ordena igual alfabética que cronológicamente, lo
que permite filtrar rangos comparando cadenas.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from asis import config as cfg
from asis.aggregate import worst_case
from asis.calendar import dekad_year

MANIFEST = cfg.DATA / "manifest.json"
GEOJSON_PATH = cfg.GEO_DIR / "municipios.geojson"
MUNI_PATH = cfg.GEO_DIR / "municipios.csv"
DEPT_GEOJSON_PATH = cfg.GEO_DIR / "departamentos.geojson"
DEPT_PATH = cfg.GEO_DIR / "departamentos.csv"

# Cómo se dibuja y se agrupa cada nivel. La app no vuelve a decidir esto en
# cada vista: pregunta aquí.
LEVEL_GEO = {
    "municipio": dict(geojson=GEOJSON_PATH, code="adm2_code",
                      name="adm2_name", label="municipio"),
    "departamento": dict(geojson=DEPT_GEOJSON_PATH, code="adm1_code",
                         name="adm1_name", label="departamento"),
}


class PanelVacio(RuntimeError):
    """El repo no trae datos construidos. Es un error de despliegue, no de uso,
    y la app lo dice con esas palabras en vez de mostrar una figura vacía."""


def manifest() -> dict:
    if not MANIFEST.exists():
        raise PanelVacio(
            f"No hay panel construido en {cfg.PANEL_DIR}. Corra "
            "`python -m asis.build --desde 2005-01-D1` y versione data/.")
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def series_dir(series_id: str) -> Path:
    return cfg.PANEL_DIR / series_id


def years_on_disk(series_id: str) -> list[int]:
    d = series_dir(series_id)
    if not d.exists():
        return []
    return sorted(int(p.stem) for p in d.glob("*.parquet")
                  if p.stem.isdigit())


def stored_series() -> list[str]:
    """Series con datos en disco, en el orden del registro de configuración."""
    return [s for s in cfg.SERIES if years_on_disk(s)]


def available_series() -> dict[str, str]:
    """Series ofrecidas al usuario, incluida la combinación de temporadas del
    ASI, que se deriva y no se guarda."""
    out = {s: cfg.SERIES[s].label for s in stored_series()}
    if {"asi_gs1", "asi_gs2"} <= set(out):
        out = {cfg.ASI_COMBINED: cfg.ASI_COMBINED_LABEL, **out}
    return out


def family_of(series_id: str) -> str:
    if series_id == cfg.ASI_COMBINED:
        return "ASI"
    return cfg.SERIES[series_id].family


def label_of(series_id: str) -> str:
    if series_id == cfg.ASI_COMBINED:
        return cfg.ASI_COMBINED_LABEL
    return cfg.SERIES[series_id].label


def unit_of(series_id: str) -> str:
    if series_id == cfg.ASI_COMBINED:
        return cfg.SERIES["asi_gs1"].unit
    return cfg.SERIES[series_id].unit


def unit_short_of(series_id: str) -> str:
    """Unidad abreviada, para barras de color y ejes donde la larga no cabe."""
    if series_id == cfg.ASI_COMBINED:
        return cfg.SERIES["asi_gs1"].unit_short
    return cfg.SERIES[series_id].unit_short


def _read_years(series_id: str, years) -> pd.DataFrame:
    parts = []
    for y in years:
        p = series_dir(series_id) / f"{y}.parquet"
        if p.exists():
            parts.append(pd.read_parquet(p))
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts, ignore_index=True)


def load(series_id: str, start: str | None = None,
         end: str | None = None) -> pd.DataFrame:
    """Corte del panel municipal de una serie entre dos dekads, inclusive."""
    if series_id == cfg.ASI_COMBINED:
        return worst_case(load("asi_gs1", start, end),
                          load("asi_gs2", start, end))
    years = years_on_disk(series_id)
    if start:
        years = [y for y in years if y >= dekad_year(start)]
    if end:
        years = [y for y in years if y <= dekad_year(end)]
    df = _read_years(series_id, years)
    if df.empty:
        return df
    if start:
        df = df[df["dekad_id"] >= start]
    if end:
        df = df[df["dekad_id"] <= end]
    return df.reset_index(drop=True)


def dekads(series_id: str) -> list[str]:
    """Dekads con dato en disco. Es lo que la app ofrece como ventana: nunca se
    ofrece un dekad que FAO no publicó."""
    if series_id == cfg.ASI_COMBINED:
        return sorted(set(dekads("asi_gs1")) | set(dekads("asi_gs2")))
    info = manifest().get("series", {}).get(series_id)
    if info and info.get("dekads"):
        return list(info["dekads"])
    df = _read_years(series_id, years_on_disk(series_id))
    return sorted(df["dekad_id"].unique().tolist()) if len(df) else []


def last_dekad(series_id: str) -> str | None:
    d = dekads(series_id)
    return d[-1] if d else None


def is_preliminary(series_id: str, dekad_id: str) -> bool:
    """Si `dekad_id` es el dekad más reciente que FAO tenía publicado la
    última vez que se construyó el panel, y por lo tanto todavía puede
    revisarse en una próxima actualización.

    Para el indicador combinado se mira si alguna de las dos temporadas
    todavía tiene ese dekad como el suyo más nuevo: el peor caso toma, por
    municipio, el mayor entre primera y postrera, así que basta con que una de
    las dos siga siendo preliminar para que el resultado también lo sea.
    """
    info = manifest().get("series", {})

    def flagged(sid: str) -> bool:
        s = info.get(sid, {})
        return bool(s.get("preliminar")) and s.get("ultimo") == dekad_id

    if series_id == cfg.ASI_COMBINED:
        return any(flagged(s) for s in ("asi_gs1", "asi_gs2"))
    return flagged(series_id)


def municipios() -> pd.DataFrame:
    if not MUNI_PATH.exists():
        raise PanelVacio(f"falta {MUNI_PATH}; reconstruya con asis.build")
    return pd.read_csv(MUNI_PATH, dtype={"adm2_code": str, "adm1_code": str})


def geojson(level: str = "municipio") -> dict:
    """Geometría del nivel pedido, ya simplificada y versionada."""
    p = LEVEL_GEO[level]["geojson"]
    if not p.exists():
        raise PanelVacio(f"falta {p}; reconstruya con asis.build")
    return json.loads(p.read_text(encoding="utf-8"))


def departamentos() -> pd.DataFrame:
    if not DEPT_PATH.exists():
        raise PanelVacio(f"falta {DEPT_PATH}; reconstruya con asis.build")
    return pd.read_csv(DEPT_PATH, dtype={"adm1_code": str})


def national(name: str) -> pd.DataFrame:
    """Serie nacional oficial de GIEWS ya ponderada por área de cultivo.

    Son las series que vienen de los CSV oficiales: el dato de FAO, no un
    agregado propio. Se versionan aparte del panel por eso mismo.
    """
    p = cfg.OFICIAL_DIR / f"{name}.parquet"
    if not p.exists():
        return pd.DataFrame()
    return pd.read_parquet(p)


def sources() -> dict:
    """Qué CSV oficial se usó y de cuándo, para citarlo en la app."""
    p = cfg.OFICIAL_DIR / "_fuentes.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))
