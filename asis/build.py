"""Construcción incremental del panel versionado.

Uso habitual:

    python -m asis.build                       # agrega lo que FAO haya publicado
    python -m asis.build --desde 2005-01-D1    # relleno histórico completo
    python -m asis.build --series vci          # una sola serie
    python -m asis.build --solo-oficiales      # solo refresca las series de FAO

Es lo que corre la actualización automática. Dos reglas gobiernan el diseño:

Nunca se sobrescribe en silencio. FAO republica dekads, así que los últimos se
vuelven a descargar y se comparan contra lo guardado; si difieren por encima de
`TOLERANCE` la corrida falla y lo reporta, en vez de cambiar una cifra que
alguien ya pudo haber citado. Se acepta con `--aceptar-republicacion`.

Excepción, y es a propósito: el dekad más reciente que FAO tiene publicado para
una serie es, por definición, un dato preliminar —FAO sigue completando esa
imagen mientras llega más información— y se revisa solo, sin pedir
`--aceptar-republicacion`, con un aviso en el log y una marca en
`manifest.json` para que la app lo diga. Esto se midió antes de implementarlo:
en 2,5 meses de historia reciente de las tres series, el único dekad que cambió
alguna vez fue el que en ese momento era el más nuevo; ninguno de los anteriores
se movió. Un dekad que ya no es el más reciente y aun así cambia sigue
deteniendo la corrida igual que antes, porque eso sería genuinamente anómalo.

Nunca se inventan filas. Un dekad que FAO no publicó no aparece en el panel. Sin
dato no es cero, y rellenar con ceros fabricaría una calma que el índice no
afirma.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from asis import client, config as cfg
from asis.aggregate import (department_weights, national_from_csv,
                            to_department)
from asis.calendar import dekad_index, dekad_year
from asis.panel import MANIFEST, series_dir

# Series oficiales derivadas que la app lee, con el CSV del que salen.
NATIONAL = {
    "serie_nacional_asi": dict(key="asi_dekad_s1", value="Data", lta=None,
                               land_type="Crop"),
    "serie_nacional_lluvia": dict(key="rain_dekad", value="Data",
                                  lta="Data_long_term_Average",
                                  land_type="Crop"),
    "serie_nacional_vci": dict(key="vci_dekad", value="Data", lta=None,
                               land_type=None),
}


def log(msg=""):
    print(msg, flush=True)


# --- Estado en disco ---------------------------------------------------------
def stored_dekads(series_id: str) -> set[str]:
    """Dekads ya calculados. Se lee solo la columna del código: abrir veinte
    parquets completos para saber qué falta sería absurdo."""
    d = series_dir(series_id)
    if not d.exists():
        return set()
    out: set[str] = set()
    for p in sorted(d.glob("*.parquet")):
        try:
            out |= set(pd.read_parquet(p, columns=["dekad_id"])["dekad_id"])
        except Exception as err:
            log(f"   ! {p.name} ilegible ({type(err).__name__}); se reconstruye")
    return out


def write_year(series_id: str, year: int, new_rows: pd.DataFrame,
               replace: set[str]) -> int:
    """Reescribe la partición de un año fundiendo lo nuevo con lo que ya había.

    Se particiona por año por el tamaño del historial, no del panel: git guarda
    el binario completo en cada commit que lo toca, así que con un archivo único
    cada actualización mensual reescribiría el panel entero.
    """
    d = series_dir(series_id)
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{year}.parquet"
    frames = []
    if p.exists():
        old = pd.read_parquet(p)
        if replace:
            old = old[~old["dekad_id"].isin(replace)]
        frames.append(old)
    frames.append(new_rows)
    out = pd.concat([f for f in frames if len(f)], ignore_index=True)
    out = (out.sort_values(["dekad_id", "adm1_name", "adm2_name"])
              .reset_index(drop=True))
    out["season"] = out["season"].astype("string")
    out.to_parquet(p, index=False, compression="zstd")
    return len(out)


# --- Construcción de una serie ----------------------------------------------
def is_preliminary(dekad_id: str, catalog_latest: str | None) -> bool:
    """Si un dekad es el más reciente que FAO tiene publicado ahora para la
    serie, sin importar hasta dónde se pidió construir (`--hasta`).

    Se compara contra el catálogo sin acotar por arriba, no contra el último
    dekad del rango que se estaba construyendo: un `--hasta` histórico no debe
    hacer que un dekad viejo se marque como preliminar.
    """
    return catalog_latest is not None and dekad_id == catalog_latest


def build_series(series_id: str, start: str, end: str, recheck: int,
                 accept_republication: bool, workers=None) -> dict:
    from asis.zonal import municipal_series      # importa rasterio: solo aquí

    series = cfg.SERIES[series_id]
    log(f"\n=== {series_id} ({series.label}) ===")
    # Sin cota superior: es el catálogo real de FAO en este momento, para saber
    # cuál es el dekad todavía preliminar aunque esta corrida solo pida
    # construir hasta uno anterior.
    all_available = client.available_dekads(series, year_min=dekad_year(start))
    catalog_latest = all_available[-1] if all_available else None
    published = [d for d in all_available if start <= d <= end]
    if not published:
        log("   el catalogo no publica dekads en la ventana pedida")
        return {"nuevos": 0, "republicados": [], "preliminares": [],
                "dekads": [], "ultimo_publicado_fao": catalog_latest}

    have = stored_dekads(series_id)
    missing = [d for d in published if d not in have]
    # Los ultimos dekads se revisan aunque ya esten: son los que FAO republica.
    revisit = [d for d in published[-recheck:] if d in have] if recheck else []
    log(f"   publicados {len(published)} ({published[0]} a {published[-1]}) - "
        f"en disco {len(have & set(published))} - nuevos {len(missing)}"
        + (f" - a revisar {len(revisit)}" if revisit else ""))

    republished: list[dict] = []
    preliminary_changes: list[dict] = []
    total_new = 0
    todo = sorted(set(missing) | set(revisit))
    by_year: dict[int, list[str]] = {}
    for dk in todo:
        by_year.setdefault(dekad_year(dk), []).append(dk)

    for year in sorted(by_year):
        dekads = sorted(by_year[year])
        again = [d for d in dekads if d in have]
        fresh = [d for d in dekads if d not in have]
        log(f"   {year}: {len(fresh)} nuevos"
            + (f", {len(again)} revisados" if again else ""))
        rows = municipal_series(series, dekads, workers=workers,
                                overwrite=bool(again))
        if rows.empty:
            continue
        accepted = set(fresh)
        if again:
            changed = compare_stored(series_id, year, rows, again)
            for c in changed:
                if is_preliminary(c["dekad_id"], catalog_latest):
                    # El dekad más reciente de FAO se revisa solo: no hay
                    # cifra previa que proteger, porque nadie pudo haber
                    # citado algo que hoy mismo se marca como preliminar.
                    preliminary_changes.append(c)
                    accepted.add(c["dekad_id"])
                else:
                    republished.append(c)
                    if accept_republication:
                        accepted.add(c["dekad_id"])
            unchanged = set(again) - {c["dekad_id"] for c in changed}
            accepted |= unchanged        # idénticos: reescribir no cambia nada
        keep = rows[rows["dekad_id"].isin(accepted)]
        if len(keep):
            n = write_year(series_id, year, keep,
                           replace=accepted & set(again))
            total_new += int(keep["dekad_id"].nunique() - len(
                accepted & set(again)))
            log(f"      -> {series_id}/{year}.parquet: {n:,} filas")

    if preliminary_changes:
        log(f"   dato preliminar revisado y aceptado sin intervención "
            f"({len(preliminary_changes)} dekad(s), es el más nuevo de FAO):")
        for c in preliminary_changes:
            log(f"      {c['dekad_id']}: dif_max={c['dif_max']} "
                f"(tolerancia {c['tolerancia']:g}) - "
                f"{c['municipios_afectados']} municipios")

    return {"nuevos": total_new, "republicados": republished,
            "preliminares": preliminary_changes,
            "dekads": sorted(stored_dekads(series_id)),
            "ultimo_publicado_fao": catalog_latest}


def diff_dekad(old: pd.Series, fresh: pd.Series, tol: float) -> dict | None:
    """Diferencias reales entre la media municipal guardada y la recién bajada.

    Devuelve None si no hay nada que reportar. Es función aparte y sin disco
    para poder probarla: de su exactitud depende que la actualización automática
    avance o se detenga.

    Un municipio sin dato en las dos versiones no es un cambio. Contar todos los
    nulos de cada lado, en vez de los que cruzan de nulo a valor, hacía que el
    aviso saltara en cada corrida: el ASI tiene municipios fuera de temporada
    siempre, y con eso la actualización nunca habría podido avanzar sola.
    """
    joined = pd.concat([old.rename("viejo"), fresh.rename("nuevo")], axis=1)
    if joined.empty:
        return None
    diff = (joined["nuevo"] - joined["viejo"]).abs()
    worst = float(diff.max()) if diff.notna().any() else 0.0
    appeared = int((joined["viejo"].isna() & joined["nuevo"].notna()).sum())
    vanished = int((joined["viejo"].notna() & joined["nuevo"].isna()).sum())
    over = int((diff > tol).sum())
    if not over and not appeared and not vanished:
        return None
    return {"dif_max": round(worst, 4), "tolerancia": tol,
            "municipios_afectados": over, "aparecen": appeared,
            "desaparecen": vanished}


def compare_stored(series_id: str, year: int, fresh: pd.DataFrame,
                   dekads: list[str]) -> list[dict]:
    """Compara los dekads recién bajados contra los guardados.

    La comparación es sobre la media municipal, que es la cifra que se publica;
    por debajo de la tolerancia de la serie es ruido de redondeo del servicio. La
    tolerancia se escala al rango del indicador: el ASI va de 0 a 100 y el VCI de
    0 a 1.
    """
    p = series_dir(series_id) / f"{year}.parquet"
    if not p.exists():
        return []
    tol = cfg.tolerance_for(cfg.SERIES[series_id])
    old = pd.read_parquet(p)
    out = []
    for dk in dekads:
        a = old[old["dekad_id"] == dk].set_index("adm2_code")["mean"]
        b = fresh[fresh["dekad_id"] == dk].set_index("adm2_code")["mean"]
        if a.empty or b.empty:
            continue
        found = diff_dekad(a, b, tol)
        if found:
            out.append({"serie": series_id, "dekad_id": dk, **found})
    return out


# --- Series oficiales de FAO -------------------------------------------------
def build_official(weights: pd.Series, refresh=True) -> dict:
    """Refresca las instantáneas de los CSV del portal y las series nacionales.

    Estas series son el dato de FAO, no un agregado propio, y son la referencia
    contra la cual se valida el panel. Por eso se versionan aparte.
    """
    log("\n=== series oficiales de GIEWS ===")
    info: dict = {}
    for key in client.OFFICIAL_KEYS:
        try:
            text, origin = client.csv_text(key, refresh=refresh)
        except client.NoPublicado as err:
            log(f"   - {key}: {err}")
            info[key] = {"estado": "no publicado"}
            continue
        except Exception as err:
            log(f"   ! {key}: {type(err).__name__}: {str(err)[:110]}")
            info[key] = {"estado": "error", "detalle": str(err)[:200]}
            continue
        if origin == "vivo":
            _p, changed = client.write_snapshot(key, text)
            log(f"   {key}: {'actualizado' if changed else 'sin cambios'}")
        info[key] = {"estado": "ok", "origen": origin,
                     "descargado": client.snapshot_date(key)}

    if weights.empty:
        log("   ! sin panel de ASI en disco: no se pueden ponderar las series "
            "nacionales por area de cultivo")
        return info

    cfg.OFICIAL_DIR.mkdir(parents=True, exist_ok=True)
    weights.rename("n_px").to_frame().to_csv(
        cfg.OFICIAL_DIR / "pesos_departamento.csv", lineterminator="\n")
    for name, spec in NATIONAL.items():
        if info.get(spec["key"], {}).get("estado") != "ok":
            continue
        df = client.load_csv(spec["key"], refresh=False)
        if spec["land_type"] and "Land_Type" in df:
            df = df[df["Land_Type"].astype(str).str.contains(
                spec["land_type"], case=False, na=False)]
        national = national_from_csv(client.clip_period(df), weights,
                                     value_col=spec["value"],
                                     lta_col=spec["lta"])
        national.to_parquet(cfg.OFICIAL_DIR / f"{name}.parquet", index=False)
        log(f"   {name}: {len(national):,} dekads "
            f"({int(national['Year'].min())}-{int(national['Year'].max())})")
    return info


def validate(panel: pd.DataFrame) -> dict:
    """Contrasta el agregado propio contra la serie departamental de FAO.

    Es la única cifra que dice si el panel sigue reproduciendo el dato oficial.
    Conviene mirarla antes de citar cualquier número fuera de la app.
    """
    if panel.empty:
        return {}
    try:
        official = client.load_csv("asi_dekad_s1", refresh=False)
    except Exception as err:
        return {"estado": f"sin CSV oficial: {type(err).__name__}"}
    official = official[official["Land_Type"].astype(str).str.contains(
        "Crop", case=False, na=False)].dropna(subset=["Data"])
    official = official[["ADM1_CODE", "dekad_id", "Data"]].copy()
    official["adm1_code"] = official["ADM1_CODE"].astype("int64").astype(str)
    mine = to_department(panel)
    if mine.empty:
        return {}
    check = mine.merge(official[["adm1_code", "dekad_id", "Data"]],
                       on=["adm1_code", "dekad_id"], how="inner")
    check = check.dropna(subset=["mean", "Data"])
    if len(check) < 10:
        return {"estado": "muestra insuficiente", "pares": int(len(check))}
    diff = check["mean"] - check["Data"]
    corr = float(np.corrcoef(check["mean"], check["Data"])[0, 1])
    out = {"pares": int(len(check)), "r": round(corr, 4),
           "r2": round(corr ** 2, 4), "mae_pp": round(float(diff.abs().mean()), 3),
           "sesgo_pp": round(float(diff.mean()), 3)}
    log(f"\n=== validacion contra el CSV oficial de FAO ===")
    log(f"   n={out['pares']} pares departamento-dekad - r={out['r']:.3f} "
        f"(R2={out['r2']:.3f}) - MAE={out['mae_pp']:.2f} pp - "
        f"sesgo={out['sesgo_pp']:+.2f} pp")
    return out


# --- Geometría y manifiesto --------------------------------------------------
def build_geometry():
    """Exporta la geometría de los dos niveles que dibuja la app."""
    from asis.zonal import export_geometry
    from asis.panel import (DEPT_GEOJSON_PATH, DEPT_PATH, GEOJSON_PATH,
                            MUNI_PATH)

    cfg.GEO_DIR.mkdir(parents=True, exist_ok=True)
    log("")
    n_muni = 0
    for level, gj_path, ref_path, etiqueta in (
            (2, GEOJSON_PATH, MUNI_PATH, "municipios"),
            (1, DEPT_GEOJSON_PATH, DEPT_PATH, "departamentos")):
        geojson, ref = export_geometry(level)
        gj_path.write_text(json.dumps(geojson, ensure_ascii=False),
                           encoding="utf-8", newline="\n")
        ref.to_csv(ref_path, index=False, lineterminator="\n")
        log(f"geometria: {len(ref)} {etiqueta} -> {gj_path.name} "
            f"({gj_path.stat().st_size // 1024} KB)")
        if level == 2:
            n_muni = len(ref)
    return n_muni


def write_manifest(series_info: dict, official: dict, validation: dict,
                   n_muni: int | None):
    previous = {}
    if MANIFEST.exists():
        previous = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest = {
        "actualizado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "start_year": cfg.START_YEAR,
        "pais": cfg.GAUL_COUNTRY,
        "municipios": n_muni or previous.get("municipios"),
        "tolerancia_fraccion": cfg.TOLERANCE_FRAC,
        "series": {**previous.get("series", {})},
        "oficiales": {**previous.get("oficiales", {}), **official},
        "validacion": validation or previous.get("validacion", {}),
    }
    for sid, info in series_info.items():
        dekads = info["dekads"]
        catalog_latest = info.get("ultimo_publicado_fao")
        if catalog_latest is not None:
            # Se consultó el catálogo esta corrida: la marca es exacta.
            preliminar = bool(dekads) and dekads[-1] == catalog_latest
        else:
            # No se consultó (rama "al día" o --solo-oficiales): se conserva
            # lo que ya decía el manifiesto anterior en vez de asumir nada.
            preliminar = (previous.get("series", {}).get(sid, {})
                         .get("preliminar", False))
        manifest["series"][sid] = {
            "etiqueta": cfg.SERIES[sid].label,
            "familia": cfg.SERIES[sid].family,
            "temporada": cfg.SERIES[sid].season,
            "estacional": cfg.SERIES[sid].seasonal,
            "unidad": cfg.SERIES[sid].unit,
            "primero": dekads[0] if dekads else None,
            "ultimo": dekads[-1] if dekads else None,
            "n_dekads": len(dekads),
            "dekads": dekads,
            # El último dekad de FAO es, por definición, un dato que todavía
            # puede revisarse: se marca aquí para que la app sea transparente
            # sobre eso en vez de mostrarlo como si fuera definitivo.
            "preliminar": preliminar,
        }
    # Si nada cambio salvo la hora, se conserva la anterior. De lo contrario el
    # manifiesto seria el unico archivo distinto en cada corrida y la
    # actualizacion automatica commitearia una linea de fecha tres veces al mes:
    # `actualizado` pasaria a significar "ultima vez que se miro" en vez de
    # "ultima vez que el panel cambio", que es lo que interesa a quien cita una
    # cifra.
    if previous:
        sin_fecha = {k: v for k, v in manifest.items() if k != "actualizado"}
        antes = {k: v for k, v in previous.items() if k != "actualizado"}
        if sin_fecha == antes and previous.get("actualizado"):
            manifest["actualizado"] = previous["actualizado"]
            log("manifiesto: sin cambios, se conserva la fecha anterior")

    cfg.DATA.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False),
                        encoding="utf-8", newline="\n")
    log(f"manifiesto: {MANIFEST}")
    return manifest


# --- CLI ---------------------------------------------------------------------
def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="python -m asis.build",
        description="Construye el panel municipal versionado del ASIS.")
    p.add_argument("--desde", metavar="DEKAD", default=None,
                   help="primer dekad a construir (YYYY-MM-Dn). Por omisión "
                        "sigue desde donde quedó el panel.")
    p.add_argument("--hasta", metavar="DEKAD", default=None,
                   help="último dekad. Por omisión, el último publicado.")
    p.add_argument("--series", default=None,
                   help="lista separada por comas; por omisión todas.")
    p.add_argument("--revisar", type=int, default=3, metavar="N",
                   help="cuántos dekads finales se vuelven a bajar para "
                        "detectar republicaciones de FAO (0 desactiva).")
    p.add_argument("--aceptar-republicacion", action="store_true",
                   help="sobrescribe los dekads republicados en vez de fallar.")
    p.add_argument("--solo-oficiales", action="store_true",
                   help="solo refresca los CSV de GIEWS y las series nacionales.")
    p.add_argument("--sin-red-oficiales", action="store_true",
                   help="usa las instantáneas versionadas sin llamar a fao.org.")
    p.add_argument("--sin-geometria", action="store_true",
                   help="no regenera la geometría simplificada.")
    p.add_argument("--workers", type=int, default=cfg.WORKERS)
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    ids = ([s.strip() for s in args.series.split(",")] if args.series
           else list(cfg.SERIES))
    unknown = [s for s in ids if s not in cfg.SERIES]
    if unknown:
        log(f"serie desconocida: {unknown}. Conocidas: {list(cfg.SERIES)}")
        return 2

    log(f"panel: {cfg.PANEL_DIR}")
    log(f"cache de rasteres: {cfg.CACHE}")

    series_info, republished, preliminares = {}, [], []
    if not args.solo_oficiales:
        end = args.hasta or client.last_dekad("ASI_D", season="GS1",
                                              landcover="C")
        for sid in ids:
            have = stored_dekads(sid)
            if args.desde:
                start = args.desde
            elif have:
                # Se retoma en el dekad siguiente al último guardado.
                start = max(have)
            else:
                start = f"{cfg.START_YEAR}-01-D1"
            series_end = end
            if dekad_index(start) > dekad_index(series_end):
                log(f"\n=== {sid} === al dia ({start} > {series_end})")
                series_info[sid] = {"nuevos": 0, "republicados": [],
                                    "preliminares": [], "dekads": sorted(have),
                                    # No se consultó el catálogo en esta rama:
                                    # write_manifest() conserva la marca de
                                    # preliminar que ya tenía del manifiesto
                                    # anterior en vez de perderla.
                                    "ultimo_publicado_fao": None}
                continue
            info = build_series(sid, start, series_end, args.revisar,
                                args.aceptar_republicacion, args.workers)
            series_info[sid] = info
            republished += info["republicados"]
            preliminares += info["preliminares"]

    # Los pesos departamentales salen del panel del ASI de la primera: es el
    # área de cultivo que el propio ráster reconoce.
    from asis.panel import load as load_panel
    try:
        asi_panel = load_panel("asi_gs1")
    except Exception:
        asi_panel = pd.DataFrame()
    weights = department_weights(asi_panel) if len(asi_panel) else pd.Series(
        dtype="float64")

    official = build_official(weights, refresh=not args.sin_red_oficiales)
    validation = validate(asi_panel) if len(asi_panel) else {}
    n_muni = None if args.sin_geometria or args.solo_oficiales else build_geometry()
    write_manifest(series_info, official, validation, n_muni)

    if preliminares:
        log("\n" + "-" * 68)
        log("DATO PRELIMINAR: FAO todavía puede revisar el dekad más reciente "
            "de estas series. Se aceptó sin pedir confirmación, y queda "
            "marcado en manifest.json para que la app lo diga.")
        for p in preliminares:
            log(f"   {p['serie']} {p['dekad_id']}: dif_max={p['dif_max']} "
                f"(tolerancia {p['tolerancia']:g}) - "
                f"{p['municipios_afectados']} municipios")
        log("-" * 68)

    if republished:
        log("\n" + "=" * 68)
        log("REPUBLICACION DETECTADA: FAO cambio dekads que ya estaban "
            "guardados.")
        for r in republished:
            log(f"   {r['serie']} {r['dekad_id']}: dif_max={r['dif_max']} "
                f"(tolerancia {r['tolerancia']:g}) - "
                f"{r['municipios_afectados']} municipios sobre tolerancia - "
                f"aparecen {r['aparecen']}, desaparecen {r['desaparecen']}")
        log("Revise a mano. Para aceptar los valores nuevos vuelva a correr "
            "con --aceptar-republicacion.")
        log("=" * 68)
        if not args.aceptar_republicacion:
            return 1

    nuevos = sum(i["nuevos"] for i in series_info.values())
    log(f"\nlisto - {nuevos} dekads nuevos en total")
    return 0


if __name__ == "__main__":
    sys.exit(main())
