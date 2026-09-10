"""Reescala las columnas de superficie del panel al área de píxel corregida.

`PIX_KM2` pasó de 0,988 (el área de la celda en el ecuador) a 0,9494 (el área
media sobre Honduras). Ver DECISIONES.md, sección 24. El panel ya construido
quedó con las superficies infladas un 4,1%, así que hay que rescribirlo: si no,
los dekads viejos y los nuevos usan constantes distintas.

No se vuelve a descargar nada. Las columnas de superficie son un conteo entero
de píxeles multiplicado por la constante, de modo que el conteo se recupera
exacto de lo guardado —el redondeo a un decimal deja un error de 0,05 km2, diez
veces menor que el píxel— y se vuelve a multiplicar. Ningún valor del índice se
toca: media, percentiles y porcentajes no dependen de la constante.

    python scripts/reescalar_area.py            # dice qué haría
    python scripts/reescalar_area.py --escribir # lo hace

No es idempotente: corre una sola vez, de 0,988 al valor vigente. Correrlo dos
veces dividiría por una constante que ya no es la del archivo, y por eso lo
primero que hace con cada columna es comprobar que el conteo de píxeles salga
entero. Sobre un panel ya reescalado esa comprobación falla y aborta sin
escribir nada.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from asis import config as cfg      # noqa: E402

VIEJO = 0.988


def columnas(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c == "km2" or c.startswith("km2_")]


def reescalar(df: pd.DataFrame, viejo: float = VIEJO) -> tuple[pd.DataFrame, dict]:
    """Devuelve el panel reescalado y el conteo de celdas que cambiaron."""
    out = df.copy()
    cambios = {}
    for c in columnas(df):
        px = np.round(df[c].to_numpy() / viejo)          # conteo entero de píxeles
        # El conteo tiene que salir limpio: si no, la columna no venía de esta
        # constante y reescalarla a ciegas seria inventar una cifra.
        resto = np.abs(df[c].to_numpy() - px * viejo)
        peor = np.nanmax(resto) if len(resto) else 0.0
        if peor > 0.051:
            raise SystemExit(f"{c}: resto de {peor:.4f} km2, no cuadra con "
                             f"{viejo}; revisar antes de escribir")
        if c == "km2":
            # n_px está guardado: se usa el conteo real, no el reconstruido.
            assert (px == df["n_px"].to_numpy()).all(), "km2 no cuadra con n_px"
            px = df["n_px"].to_numpy()
        nuevo = np.round(px * cfg.PIX_KM2, 1)
        cambios[c] = int((nuevo != df[c].to_numpy()).sum())
        out[c] = nuevo
    return out, cambios


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--escribir", action="store_true",
                    help="sobrescribe los parquet; sin esto solo informa")
    args = ap.parse_args()

    archivos = sorted(cfg.PANEL_DIR.glob("*/*.parquet"))
    if not archivos:
        raise SystemExit(f"no hay panel en {cfg.PANEL_DIR}")

    print(f"{VIEJO} -> {cfg.PIX_KM2} km2 por píxel "
          f"({100 * (cfg.PIX_KM2 / VIEJO - 1):+.1f}%)\n")
    total_filas = total_celdas = 0
    antes = despues = 0.0
    for p in archivos:
        df = pd.read_parquet(p)
        cols = columnas(df)
        if not cols:
            continue
        nuevo, cambios = reescalar(df)
        total_filas += len(df)
        total_celdas += sum(cambios.values())
        antes += df["km2"].sum()
        despues += nuevo["km2"].sum()
        if args.escribir:
            nuevo.to_parquet(p, index=False)
    verbo = "reescritas" if args.escribir else "por reescribir"
    print(f"{len(archivos)} archivos, {total_filas:,} filas, "
          f"{total_celdas:,} celdas {verbo}")
    print(f"suma de km2 del panel: {antes:,.0f} -> {despues:,.0f}")
    if not args.escribir:
        print("\nnada escrito; repetir con --escribir")
    return 0


if __name__ == "__main__":
    sys.exit(main())
