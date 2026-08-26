"""El calendario dekadal es la clave temporal de todo el panel: si la aritmética
de dekads se equivoca, el resto del proyecto se equivoca en silencio."""
import pandas as pd
import pytest

from asis.calendar import (dekad_between, dekad_code, dekad_date,
                           dekad_from_index, dekad_index, dekad_label,
                           dekad_of_date, dekad_of_year, dekad_range,
                           dekad_window, dekad_year)


def test_index_ida_y_vuelta():
    for code in ("2005-01-D1", "2019-09-D3", "2026-08-D2", "2020-12-D3"):
        assert dekad_from_index(dekad_index(code)) == code


def test_indice_es_monotono_y_consecutivo():
    codes = dekad_between("2019-12-D2", "2020-01-D2")
    assert codes == ["2019-12-D2", "2019-12-D3", "2020-01-D1", "2020-01-D2"]
    idx = [dekad_index(c) for c in codes]
    assert idx == list(range(idx[0], idx[0] + 4))


def test_orden_alfabetico_igual_a_cronologico():
    """La app filtra rangos comparando cadenas. Si esto dejara de valer, un
    rango devolvería dekads de otras fechas sin dar error."""
    codes = dekad_between("2005-01-D1", "2026-08-D2")
    assert codes == sorted(codes)
    assert [dekad_index(c) for c in codes] == sorted(
        dekad_index(c) for c in codes)


def test_ventana_movil_termina_en_el_codigo_dado():
    w = dekad_window("2020-01-D1", 4)
    assert len(w) == 4 and w[-1] == "2020-01-D1"
    assert w[0] == "2019-12-D1"


def test_treinta_y_seis_dekads_por_anio():
    assert len(dekad_between("2019-01-D1", "2019-12-D3")) == 36
    assert dekad_of_year("2019-01-D1") == 1
    assert dekad_of_year("2019-12-D3") == 36


@pytest.mark.parametrize("day,expected", [(1, 1), (10, 1), (11, 2), (20, 2),
                                          (21, 3), (28, 3), (31, 3)])
def test_dekad_de_una_fecha(day, expected):
    code = dekad_of_date(pd.Timestamp(2020, 1, day))
    assert code == dekad_code(2020, 1, expected)


def test_fecha_de_inicio_del_dekad():
    assert dekad_date("2019-09-D1") == pd.Timestamp("2019-09-01")
    assert dekad_date("2019-09-D2") == pd.Timestamp("2019-09-11")
    assert dekad_date("2019-09-D3") == pd.Timestamp("2019-09-21")


def test_etiqueta_en_espanol():
    assert dekad_label("2019-09-D3") == "3a dek sep 2019"
    assert dekad_year("2019-09-D3") == 2019


def test_dekad_range_cruza_anios():
    r = dekad_range(2020, 10, 1, 2021, 2, 3)
    assert r[0] == "2020-10-D1" and r[-1] == "2021-02-D3"
    assert len(r) == 15
