"""Validación del panel contra el dato oficial de FAO.

Es la prueba que dice si el agregado propio sigue reproduciendo la serie
departamental que publica GIEWS. No toca la red: usa el panel versionado y la
instantánea versionada del CSV oficial.

Si esta prueba falla, algo cambió en la cadena —la máscara, los límites, la
ponderación, el propio dato de FAO— y ninguna cifra del panel debería citarse
hasta entender qué.
"""
import numpy as np
import pandas as pd
import pytest

from asis import client, panel
from asis.aggregate import to_department

# Umbrales holgados a propósito: la prueba busca una ruptura de la cadena, no
# una coincidencia exacta. El agregado propio parte de rásteres recortados a la
# malla nativa y FAO publica su propio agregado departamental, así que una
# diferencia pequeña es esperable.
MIN_R = 0.95
MAX_MAE_PP = 3.0
MAX_BIAS_PP = 2.0
MIN_PAIRS = 200


@pytest.fixture(scope="module")
def comparison() -> pd.DataFrame:
    if "asi_gs1" not in panel.stored_series():
        pytest.skip("no hay panel de asi_gs1 construido en data/")
    try:
        official = client.load_csv("asi_dekad_s1", refresh=False)
    except Exception as err:
        pytest.skip(f"no hay instantánea del CSV oficial: {err}")

    mine = to_department(panel.load("asi_gs1"))
    official = official[official["Land_Type"].astype(str).str.contains(
        "Crop", case=False, na=False)].dropna(subset=["Data"])
    official = official[["ADM1_CODE", "dekad_id", "Data"]].copy()
    official["adm1_code"] = official["ADM1_CODE"].astype("int64").astype(str)
    check = mine.merge(official[["adm1_code", "dekad_id", "Data"]],
                       on=["adm1_code", "dekad_id"], how="inner")
    return check.dropna(subset=["mean", "Data"])


def test_hay_muestra_suficiente(comparison):
    assert len(comparison) >= MIN_PAIRS, (
        f"solo {len(comparison)} pares departamento-dekad en común; "
        "revise que el panel y el CSV cubran el mismo periodo")


def test_correlacion_con_el_dato_oficial(comparison):
    r = float(np.corrcoef(comparison["mean"], comparison["Data"])[0, 1])
    assert r >= MIN_R, f"r={r:.4f} por debajo de {MIN_R}"


def test_error_absoluto_medio(comparison):
    mae = float((comparison["mean"] - comparison["Data"]).abs().mean())
    assert mae <= MAX_MAE_PP, f"MAE={mae:.2f} pp por encima de {MAX_MAE_PP}"


def test_sesgo_acotado(comparison):
    """Un sesgo sistemático apuntaría a un problema de máscara o de ponderación,
    no a ruido."""
    bias = float((comparison["mean"] - comparison["Data"]).mean())
    assert abs(bias) <= MAX_BIAS_PP, f"sesgo={bias:+.2f} pp"


def test_el_panel_no_inventa_filas():
    """Sin dato no es cero: ninguna fila municipio-dekad debe existir con media
    cero fabricada. Se comprueba que los NaN sigan siendo NaN."""
    if "asi_gs1" not in panel.stored_series():
        pytest.skip("no hay panel construido")
    df = panel.load("asi_gs1", "2019-01-D1", "2019-12-D3")
    sin_pixeles = df[df["n_px"] == 0]
    assert sin_pixeles["mean"].isna().all(), (
        "hay municipios sin píxeles válidos con media distinta de NaN")


def test_no_hay_duplicados_municipio_dekad():
    for sid in panel.stored_series():
        df = panel.load(sid)
        dup = df.duplicated(["adm2_code", "dekad_id"]).sum()
        assert dup == 0, f"{sid}: {dup} filas duplicadas municipio-dekad"


def test_valores_dentro_del_rango_del_indicador():
    """Si una bandera 251-255 se hubiera colado como dato, aparecería aquí."""
    from asis import config as cfg
    for sid in panel.stored_series():
        lo, hi = cfg.SERIES[sid].valid_range
        df = panel.load(sid)
        vals = df["mean"].dropna()
        assert vals.between(lo, hi).all(), (
            f"{sid}: valores fuera del rango [{lo}, {hi}] "
            f"(min={vals.min()}, max={vals.max()})")
