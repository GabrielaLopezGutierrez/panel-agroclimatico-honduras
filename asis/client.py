"""Cliente de las fuentes primarias de FAO.

Tres accesos, uno por tipo de recurso. `catalog()` consulta los metadatos de los
rásteres; `export_tif()` descarga un ráster recortado a Honduras y alineado a la
malla nativa; `load_csv()` trae las series oficiales del portal GIEWS.

Solo el constructor usa este módulo. La app no toca la red: lee el panel ya
calculado del disco.
"""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from asis import config as cfg
from asis.calendar import dekad_code

# --- Sesión HTTP única, con reintentos ---------------------------------------
# www.fao.org está detrás de Cloudflare y rechaza el User-Agent de requests.
# Desde una IP de datacenter (un runner de CI, el hosting de la app) la
# probabilidad de 403 es mayor que desde una laptop, y por eso load_csv() tiene
# respaldo en disco.
def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/126.0.0.0 Safari/537.36"),
        "Accept": "text/csv,application/json,image/tiff,*/*",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8"})
    retry = Retry(total=4, backoff_factor=1.5, respect_retry_after_header=True,
                  status_forcelist=(429, 500, 502, 503, 504),
                  allowed_methods=frozenset(["GET", "POST"]))
    s.mount("https://", HTTPAdapter(max_retries=retry, pool_connections=16,
                                    pool_maxsize=16))
    return s


_SESSION: requests.Session | None = None


def session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        _SESSION = make_session()
    return _SESSION


def _cache_dir(sub: str) -> Path:
    p = cfg.CACHE / sub
    p.mkdir(parents=True, exist_ok=True)
    return p


def _cache_key(*parts) -> str:
    return hashlib.md5("|".join(map(str, parts)).encode()).hexdigest()[:20]


def cached_json(key, producer, subdir="meta", max_age_hours=None):
    """Memoiza en disco la respuesta de un servicio. Si el json quedó corrupto
    se descarta y se vuelve a pedir. Con max_age_hours la entrada caduca: el
    catálogo cambia cada vez que FAO publica, así que cachearlo para siempre
    congelaría el último dekad conocido."""
    p = _cache_dir(subdir) / f"{key}.json"
    if p.exists():
        fresh = (max_age_hours is None
                 or (time.time() - p.stat().st_mtime) < max_age_hours * 3600)
        if fresh:
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                p.unlink()
    value = producer()
    p.write_text(json.dumps(value), encoding="utf-8")
    return value


# --- Catálogo de rásteres ----------------------------------------------------
# maxRecordCount del servicio = 1000. Sin resultOffset solo se lee la primera
# página: ese era el origen del error de creer que el último dekad publicado de
# ASI_D era de 1997.
def catalog(svc, where="1=1", fields="OBJECTID,Name,Year", order="OBJECTID",
            page=1000, max_pages=80, max_age_hours=6) -> pd.DataFrame:
    key = _cache_key("cat", svc, where, fields, order)

    def fetch():
        rows, offset = [], 0
        for _ in range(max_pages):
            r = session().post(
                cfg.IMG_SERVER.format(svc=svc) + "/query", timeout=180,
                data={"where": where, "outFields": fields,
                      "returnGeometry": "false", "orderByFields": order,
                      "resultOffset": offset, "resultRecordCount": page,
                      "f": "json"})
            r.raise_for_status()
            js = r.json()
            if "error" in js:
                raise RuntimeError(f"{svc} :: {js['error']}")
            feats = js.get("features", [])
            rows += [f["attributes"] for f in feats]
            if len(feats) < page:
                break
            offset += page
        return rows

    return pd.DataFrame(cached_json(key, fetch, max_age_hours=max_age_hours))


# Convenciones de nombre, verificadas contra el catálogo:
#   ASIS.ASI-D.YYYY-MM-Dn.GSn.LC-C        ASIS.ASI-A.YYYY.GSn.LC-C
#   ASIS.VCI-D.YYYY-MM-Dn                 ASIS.VHI-D.YYYY-MM-Dn
# Atención: los campos Dekad y Year_Dekad son TEXTO; filtrar Dekad=27 da HTTP 400.
_RE_DEKAD = re.compile(r"\.(\d{4})-(\d{2})-D([123])")
_RE_SEASON = re.compile(r"\.(GS\d)")
_RE_LANDCOVER = re.compile(r"\.LC-([CG])")


def catalog_parsed(svc, year_min=None, year_max=None) -> pd.DataFrame:
    """Catálogo con dekad, temporada y máscara de uso de suelo ya extraídos."""
    conditions = []
    if year_min is not None:
        conditions.append(f"Year>={int(year_min)}")
    if year_max is not None:
        conditions.append(f"Year<={int(year_max)}")
    df = catalog(svc, " AND ".join(conditions) if conditions else "1=1")
    if df.empty:
        return df
    parsed = df["Name"].str.extract(_RE_DEKAD)
    has_dekad = parsed[0].notna()
    df["dekad_id"] = np.where(
        has_dekad, parsed[0] + "-" + parsed[1] + "-D" + parsed[2], None)
    df["season"] = df["Name"].str.extract(_RE_SEASON)[0]
    df["landcover"] = df["Name"].str.extract(_RE_LANDCOVER)[0]
    _register_ids(svc, df)
    return df.sort_values(["Name"]).reset_index(drop=True)


# Registro de OBJECTID en memoria: evita una consulta HTTP por ráster.
_IDS: dict[tuple, int] = {}


def _register_ids(svc, df):
    if {"Name", "OBJECTID"} <= set(df.columns):
        for name, oid in zip(df["Name"], df["OBJECTID"]):
            _IDS[(svc, name)] = int(oid)


def raster_ids(svc, names) -> dict:
    """OBJECTID de una lista de rásteres, resolviendo en lotes."""
    missing = [n for n in dict.fromkeys(names) if (svc, n) not in _IDS]
    for i in range(0, len(missing), 80):
        batch = missing[i:i + 80]
        where = "Name IN (" + ",".join("'" + n + "'" for n in batch) + ")"
        found = catalog(svc, where, "OBJECTID,Name", max_age_hours=None)
        if not found.empty:
            _register_ids(svc, found)
    return {n: _IDS.get((svc, n)) for n in names}


def last_dekad(svc="ASI_D", season=None, landcover=None) -> str:
    """Último dekad realmente publicado. No se asume el calendario: FAO publica
    con retraso variable y a veces republica."""
    today = pd.Timestamp.today()
    for years_back in (1, 3, 10):
        df = catalog_parsed(svc, year_min=today.year - years_back)
        d = df.dropna(subset=["dekad_id"]) if not df.empty else df
        if len(d):
            if season:
                d = d[d["season"] == season]
            if landcover:
                d = d[d["landcover"] == landcover]
            if len(d):
                return str(d["dekad_id"].max())
    raise RuntimeError(f"{svc}: el catálogo no devolvió dekads")


def available_dekads(series: cfg.Series, year_min=None) -> list[str]:
    """Dekads publicados de una serie. Es la lista de trabajo del constructor:
    lo que FAO tiene, no lo que dictaría el calendario."""
    df = catalog_parsed(series.svc, year_min=year_min)
    if df.empty:
        return []
    d = df.dropna(subset=["dekad_id"])
    if series.season:
        d = d[d["season"] == series.season]
    if ".LC-C" in series.suffix:
        d = d[d["landcover"] == "C"]
    return sorted(d["dekad_id"].unique().tolist())


# --- Rásteres recortados -----------------------------------------------------
def snap_bbox(bbox=cfg.HND_BBOX) -> dict:
    """Alinea el bbox a la malla nativa de ASIS: sin remuestreo ni desplazamiento."""
    xmin, ymin, xmax, ymax = bbox
    step = cfg.GRID_STEP
    c0 = math.floor((xmin - cfg.GRID_X0) / step)
    c1 = math.ceil((xmax - cfg.GRID_X0) / step)
    r0 = math.floor((cfg.GRID_Y0 - ymax) / step)
    r1 = math.ceil((cfg.GRID_Y0 - ymin) / step)
    return dict(bbox=(cfg.GRID_X0 + c0 * step, cfg.GRID_Y0 - r1 * step,
                      cfg.GRID_X0 + c1 * step, cfg.GRID_Y0 - r0 * step),
                width=c1 - c0, height=r1 - r0)


SNAP = snap_bbox()


def raster_name(svc, dekad, suffix="") -> str:
    return f"ASIS.{svc.replace('_', '-')}.{dekad}{suffix}"


def export_tif(svc, name, oid=None, mask=True, overwrite=False) -> Path:
    """GeoTIFF F32 recortado a Honduras. Con mask=True el servidor devuelve
    NoData en las banderas 251-255, de modo que ninguna bandera entra como valor
    del índice en la estadística zonal."""
    out = _cache_dir("tif") / f"{svc}__{name}{'' if mask else '_raw'}.tif"
    if out.exists() and out.stat().st_size > 2048 and not overwrite:
        return out
    if oid is None:
        oid = raster_ids(svc, [name])[name]
    if oid is None:
        raise KeyError(f"{svc}: no existe el ráster {name}")
    params = {"bbox": ",".join(f"{v:.7f}" for v in SNAP["bbox"]),
              "bboxSR": cfg.WKID, "imageSR": cfg.WKID,
              "size": f"{SNAP['width']},{SNAP['height']}",
              "format": "tiff", "pixelType": "F32",
              "noData": cfg.NODATA,
              "noDataInterpretation": "esriNoDataMatchAny",
              "interpolation": "RSP_NearestNeighbor",
              "mosaicRule": json.dumps({"mosaicMethod": "esriMosaicLockRaster",
                                        "lockRasterIds": [int(oid)]}),
              "f": "image"}
    if mask and svc in cfg.VALID_RANGE:
        lo, hi = cfg.VALID_RANGE[svc]
        params["renderingRule"] = json.dumps({
            "rasterFunction": "Mask",
            "rasterFunctionArguments": {"IncludedRanges": [lo, hi],
                                        "NoDataValues": []},
            "variableName": "Raster"})
    r = session().get(cfg.IMG_SERVER.format(svc=svc) + "/exportImage",
                      params=params, timeout=300)
    r.raise_for_status()
    if r.content[:2] not in (b"II", b"MM"):
        raise RuntimeError(f"{name}: la respuesta no es TIFF -> {r.content[:160]}")
    tmp = out.with_suffix(".part")
    tmp.write_bytes(r.content)
    tmp.replace(out)          # atómico: un Ctrl-C no deja un tif truncado
    return out


def export_tifs(svc, names, workers=None, mask=True, verbose=True,
                overwrite=False):
    """Descarga en paralelo. Devuelve (rutas_ok, faltantes) sin abortar el lote:
    un dekad que FAO no publicó no debe tumbar la corrida entera."""
    workers = workers or cfg.WORKERS
    ids = raster_ids(svc, names)
    ok, missing = {}, []
    pending = [n for n in names if ids.get(n) is not None]
    missing += [n for n in names if ids.get(n) is None]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(export_tif, svc, n, ids[n], mask, overwrite): n
                   for n in pending}
        for future in as_completed(futures):
            name = futures[future]
            try:
                ok[name] = future.result()
            except Exception as err:
                missing.append(name)
                if verbose:
                    print(f"   ! {name}: {type(err).__name__} {str(err)[:90]}")
    if verbose:
        print(f"   {svc}: {len(ok)}/{len(names)} rasteres en cache"
              + (f" - {len(missing)} no disponibles" if missing else ""))
    return ok, missing


# --- CSV oficiales del portal ------------------------------------------------
CSV_FILES = {
    "asi_dekad_s1":   "MAP_ASI/DATA/ASI_Dekad_Season1_data.csv",
    "asi_dekad_s2":   "MAP_ASI/DATA/ASI_Dekad_Season2_data.csv",
    "asi_annual_s1":  "MAP_ASI/DATA/ASI_AnnualSummary_Season1_data.csv",
    "asi_annual_s2":  "MAP_ASI/DATA/ASI_AnnualSummary_Season2_data.csv",
    "mvhi_dekad_s1":  "MAP_ASI/DATA/MVHI_Dekad_Season1_data.csv",
    "mvhi_annual_s1": "MAP_ASI/DATA/Mean-VHI_AnnualSummary_Season1_data.csv",
    "mvhi_annual_s2": "MAP_ASI/DATA/Mean-VHI_AnnualSummary_Season2_data.csv",
    "ndvi":           "GRAPH_NDVI_AGRI/ndvi_adm1_data.csv",
    "vhi_dekad":      "MAP_NDVI_ANOMALY/DATA/vhi_adm1_dekad_data.csv",
    "vci_dekad":      "MAP_NDVI_ANOMALY/DATA/vci_adm1_dekad_data.csv",
    "rain_dekad":     "GRAPH_RAIN_AGRI/rain_adm1_data.csv",
}
NUM_COLS = ("Year", "Month", "Dekad", "Data", "Data_long_term_Average",
            "ADM1_CODE", "VALUE", "value")

SNAPSHOT_INDEX = cfg.OFICIAL_DIR / "_fuentes.json"

# De los once CSV del portal, estos son los que alimentan la app: la serie
# nacional oficial del ASI, la lluvia con su promedio de largo plazo (que no
# tiene equivalente en los rásteres) y el VCI departamental, que sirve de
# contraste. Los demás quedan declarados en CSV_FILES para quien los necesite
# desde el cuaderno, pero no se versionan: son 21 MB que se reescribirían en
# cada actualización.
OFFICIAL_KEYS = ("asi_dekad_s1", "rain_dekad", "vci_dekad")


def _snapshot_index() -> dict:
    if SNAPSHOT_INDEX.exists():
        try:
            return json.loads(SNAPSHOT_INDEX.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def snapshot_date(key) -> str | None:
    """Fecha en que se bajó la instantánea versionada de un CSV oficial."""
    return _snapshot_index().get(key, {}).get("descargado")


class NoPublicado(FileNotFoundError):
    """El portal no publica ese archivo para este país.

    Se distingue del bloqueo de Cloudflare a propósito: un 404 es una decisión
    editorial de FAO y no tiene arreglo desde aquí, mientras que un 403 sí puede
    resolverse con la instantánea versionada. Confundirlos haría que la
    construcción fallara por algo que nunca va a existir. Caso concreto:
    Honduras no tiene CSV dekadal de la temporada postrera.
    """


def fetch_text(url, tries=3, timeout=180) -> str:
    r = None
    for i in range(tries):
        r = session().get(url, timeout=timeout)
        if r.status_code == 200:
            r.encoding = r.encoding or "utf-8"
            return r.text
        if r.status_code == 404:
            raise NoPublicado(f"{url.rsplit('/', 1)[-1]}: no publicado para "
                              f"{cfg.ISO3} (HTTP 404)")
        if r.status_code in (403, 429, 503):
            time.sleep(1.5 * (i + 1))
            continue
        r.raise_for_status()
    code = r.status_code if r is not None else "?"
    raise RuntimeError(f"HTTP {code} al descargar {url.rsplit('/', 1)[-1]}. "
                       "www.fao.org está detrás de Cloudflare.")


def csv_text(key, iso3=cfg.ISO3, refresh=True) -> tuple[str, str]:
    """Texto de un CSV oficial y de dónde salió.

    Intenta primero la fuente viva y cae a la instantánea versionada en
    data/oficial/. El origen se devuelve para que quien llame lo muestre: un
    respaldo silencioso es peor que un error, porque el analista citaría una
    cifra vieja creyendo que es de hoy.
    """
    snap = snapshot_path(key)
    if refresh:
        try:
            url = cfg.CSV_DIR.format(iso3=iso3) + CSV_FILES[key]
            return fetch_text(url), "vivo"
        except NoPublicado:
            # No hay nada que respaldar: el archivo no existe para este país.
            raise
        except Exception as err:
            if not snap.exists():
                raise RuntimeError(
                    f"{key}: falló la descarga ({type(err).__name__}: "
                    f"{str(err)[:120]}) y no hay instantánea en {snap}. "
                    "Descargue el CSV en el navegador y guárdelo ahí.") from err
            print(f"   ! {key}: fuente viva inaccesible ({type(err).__name__});"
                  f" se usa la instantanea del {snapshot_date(key) or '?'}")
            return _read_snapshot(snap), "instantánea"
    if not snap.exists():
        raise RuntimeError(f"{key}: no hay instantánea versionada en {snap}")
    return _read_snapshot(snap), "instantánea"


def snapshot_path(key) -> Path:
    """Los CSV crudos se versionan comprimidos: el del ASI pesa 3,2 MB en texto
    y se reescribiría entero en cada actualización."""
    gz = cfg.OFICIAL_DIR / f"{key}.csv.gz"
    plain = cfg.OFICIAL_DIR / f"{key}.csv"
    if plain.exists() and not gz.exists():
        return plain          # instantánea puesta a mano en el navegador
    return gz


def _read_snapshot(p: Path) -> str:
    if p.suffix == ".gz":
        with gzip.open(p, "rt", encoding="utf-8", errors="replace") as f:
            return f.read()
    return p.read_text(encoding="utf-8", errors="replace")


def write_snapshot(key, text) -> tuple[Path, bool]:
    """Guarda la instantánea fechada del CSV oficial y dice si cambió.

    Se versiona en el repo: es la referencia auditable de qué publicaba FAO
    cuando se construyó el panel. Si el contenido es idéntico al que ya está en
    disco no se reescribe, porque un archivo tocado sin cambios es un commit que
    engorda el historial sin agregar información.
    """
    cfg.OFICIAL_DIR.mkdir(parents=True, exist_ok=True)
    out = cfg.OFICIAL_DIR / f"{key}.csv.gz"
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    index = _snapshot_index()
    if out.exists() and index.get(key, {}).get("sha256") == digest:
        return out, False
    # mtime fijo: gzip guarda la hora en la cabecera y eso solo cambiaría los
    # bytes del archivo sin que cambie el contenido.
    with gzip.GzipFile(out, "wb", compresslevel=9, mtime=0) as f:
        f.write(text.encode("utf-8"))
    index[key] = {"descargado": datetime.now(timezone.utc).date().isoformat(),
                  "url": cfg.CSV_DIR.format(iso3=cfg.ISO3) + CSV_FILES[key],
                  "filas": text.count("\n"), "sha256": digest}
    SNAPSHOT_INDEX.write_text(json.dumps(index, indent=2, ensure_ascii=False),
                              encoding="utf-8", newline="\n")
    return out, True


def parse_csv(text: str) -> pd.DataFrame:
    """CSV oficial -> DataFrame tipado.

    Ojo con las dos columnas de dekad: Dekad es el tercio del mes (1, 2 o 3) y
    viene del CSV de FAO; dekad_id es el código completo que arma el paquete.
    """
    df = pd.read_csv(io.StringIO(text))
    df.columns = [c.strip() for c in df.columns]
    # pandas 3 separa 'str' de 'object': hay que nombrar los dos para que las
    # columnas de texto se limpien igual en ambas versiones.
    for c in df.select_dtypes(include=["object", "str"]):
        df[c] = df[c].astype("string").str.strip()
    for c in NUM_COLS:
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    if "Date" in df:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce", format="mixed")
    if {"Year", "Month", "Dekad"} <= set(df.columns):
        ok = df[["Year", "Month", "Dekad"]].notna().all(axis=1)
        df["dekad_id"] = pd.Series(pd.NA, index=df.index, dtype="string")
        df.loc[ok, "dekad_id"] = [
            dekad_code(int(y), int(m), int(d)) for y, m, d
            in df.loc[ok, ["Year", "Month", "Dekad"]].to_numpy()]
    return df.drop_duplicates()


def load_csv(key, iso3=cfg.ISO3, refresh=True) -> pd.DataFrame:
    text, origin = csv_text(key, iso3, refresh=refresh)
    df = parse_csv(text)
    df.attrs["origen"] = origin
    return df


def clip_period(df, col="Year", min_year=None):
    """Deja solo las filas del periodo de análisis (Year >= START_YEAR). Las
    series CSV llegan completas desde 1984; recortarlas hace que toda la lectura
    histórica use la misma ventana."""
    y0 = cfg.START_YEAR if min_year is None else min_year
    if col not in df.columns:
        return df
    return df[df[col] >= y0].copy()
