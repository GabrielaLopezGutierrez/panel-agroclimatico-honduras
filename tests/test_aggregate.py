"""Reglas de agregación. Son las que convierten el panel municipal en la cifra
que alguien cita, así que conviene fijarlas por escrito."""
import numpy as np
import pandas as pd
import pytest

from asis import config as cfg
from asis.aggregate import (classify, severity_area, to_country, to_department,
                            worst_case)


def panel():
    """Dos municipios de un departamento, con áreas muy distintas.

    Grande tiene noventa veces más píxeles válidos que Chico: es el caso en el
    que ponderar o no ponderar cambia la respuesta.
    """
    rows = [
        dict(adm2_code="1", adm2_name="Grande", adm1_code="10",
             adm1_name="Dep", dekad_id="2019-09-D1", n_px=900, km2=900.0,
             mean=10.0, p10=5.0, median=9.0, p90=20.0, km2_gt40=90.0),
        dict(adm2_code="2", adm2_name="Chico", adm1_code="10",
             adm1_name="Dep", dekad_id="2019-09-D1", n_px=10, km2=10.0,
             mean=100.0, p10=90.0, median=100.0, p90=100.0, km2_gt40=10.0),
    ]
    return pd.DataFrame(rows)


def test_pais_pondera_por_pixeles_no_por_municipios():
    c = to_country(panel())
    esperado = (10.0 * 900 + 100.0 * 10) / 910          # 10,989
    assert c["mean"].iloc[0] == pytest.approx(esperado, abs=1e-3)
    # El promedio simple daría 55: cinco veces más alto. Es exactamente el
    # error que la ponderación evita.
    assert c["mean"].iloc[0] < 55


def test_departamento_suma_area_y_cuenta_municipios():
    d = to_department(panel())
    assert len(d) == 1
    assert d["n_px"].iloc[0] == 910
    assert d["km2"].iloc[0] == pytest.approx(910.0)
    assert d["n_muni"].iloc[0] == 2


def test_umbrales_se_recalculan_desde_los_km2():
    """pct_gt40 al agregar no es el promedio de los pct municipales: es el km2
    por encima del umbral sobre el km2 total."""
    d = to_department(panel())
    assert d["km2_gt40"].iloc[0] == pytest.approx(100.0)
    assert d["pct_gt40"].iloc[0] == pytest.approx(100 * 100.0 / 910.0, abs=0.1)


def test_percentiles_no_sobreviven_a_la_agregacion():
    """El p90 de un departamento no es el promedio de los p90 municipales, así
    que no se publica en vez de publicar algo que no significa eso."""
    d = to_department(panel())
    for col in ("p10", "median", "p90"):
        assert col not in d.columns


def test_agregacion_ignora_municipios_sin_dato():
    p = panel()
    p.loc[1, "mean"] = np.nan
    c = to_country(p)
    assert c["mean"].iloc[0] == pytest.approx(10.0)
    assert c["n_px"].iloc[0] == 900        # el municipio sin dato no pesa


def test_peor_caso_toma_el_maximo_de_las_temporadas():
    gs1 = panel().assign(series="asi_gs1", season="GS1")
    gs2 = panel().assign(series="asi_gs2", season="GS2")
    gs2["mean"] = [80.0, 5.0]
    out = worst_case(gs1, gs2)
    assert len(out) == 2                                  # un valor por municipio
    grande = out[out["adm2_code"] == "1"]["mean"].iloc[0]
    chico = out[out["adm2_code"] == "2"]["mean"].iloc[0]
    assert grande == 80.0        # gana la postrera
    assert chico == 100.0        # gana la primera
    assert set(out["series"]) == {cfg.ASI_COMBINED}


def test_peor_caso_conserva_la_temporada_de_origen():
    gs1 = panel().assign(series="asi_gs1", season="GS1")
    gs2 = panel().assign(series="asi_gs2", season="GS2")
    gs2["mean"] = [80.0, 5.0]
    out = worst_case(gs1, gs2).set_index("adm2_code")
    assert out.loc["1", "season"] == "GS2"
    assert out.loc["2", "season"] == "GS1"


def test_clases_usan_los_cortes_oficiales():
    s = pd.Series([0.0, 9.9, 10.0, 84.9, 85.0, 100.0])
    out = classify(s, "ASI").astype(str).tolist()
    assert out == ["<10", "<10", "10-25", "70-85", ">=85", ">=85"]


def test_area_por_severidad_suma_el_area_no_los_municipios():
    g = severity_area(panel(), "ASI")
    assert g.loc["2019-09-D1", "10-25"] == pytest.approx(900.0)
    assert g.loc["2019-09-D1", ">=85"] == pytest.approx(10.0)
