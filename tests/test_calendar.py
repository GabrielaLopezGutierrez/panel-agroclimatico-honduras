"""El calendario de dekads es la clave temporal de todo el panel: si la
aritmética de dekads se equivoca, el resto del proyecto se equivoca en
silencio."""
import pandas as pd
import pytest

from asis.calendar import (dekad_between, dekad_code, dekad_date,
                           dekad_from_index, dekad_index, dekad_label,
                           dekad_label_long, dekad_of_date, dekad_of_year,
                           dekad_range, dekad_window, dekad_year,
                           last_closed_dekad)


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
    """La herramienta dice "dekad" en todas partes, nunca "dekadal": es el
    termino de FAO GIEWS y la clave temporal del panel. "dek" es su abreviatura
    y se usa solo donde el ancho aprieta. Los ordinales van en masculino,
    porque el sustantivo lo es."""
    assert dekad_label("2019-09-D3") == "3er dek sep 2019"
    assert dekad_label("2019-09-D1") == "1er dek sep 2019"
    assert dekad_label_long("2019-09-D3") == "3er dekad de septiembre 2019"
    assert dekad_year("2019-09-D3") == 2019


def test_dekad_range_cruza_anios():
    r = dekad_range(2020, 10, 1, 2021, 2, 3)
    assert r[0] == "2020-10-D1" and r[-1] == "2021-02-D3"
    assert len(r) == 15


# --- Ultimo dekad cerrado -----------------------------------------------------
# Gobierna la actualizacion automatica: es el techo de lo que FAO puede haber
# publicado, y por lo tanto la diferencia entre "no hay nada" y "todavia no
# llega".
@pytest.mark.parametrize("dia, esperado", [
    # El dekad que contiene a hoy sigue corriendo: el ultimo cerrado es el
    # anterior. Los bordes son los tres dias en que cambia.
    ("2026-09-10", "2026-08-D3"),   # ultimo dia de D1, D1 aun abierto
    ("2026-09-11", "2026-09-D1"),   # primer dia de D2, D1 ya cerro
    ("2026-09-20", "2026-09-D1"),
    ("2026-09-21", "2026-09-D2"),
    ("2026-09-30", "2026-09-D2"),
    ("2026-10-01", "2026-09-D3"),   # cruza de mes
    ("2027-01-01", "2026-12-D3"),   # cruza de anio
])
def test_el_ultimo_dekad_cerrado_es_el_anterior_al_de_hoy(dia, esperado):
    assert last_closed_dekad(dia) == esperado


def test_el_ultimo_dekad_cerrado_sin_argumento_no_es_futuro():
    """Sin fecha usa el reloj del runner. Lo unico que se puede fijar es que no
    devuelva un dekad que todavia no cerro."""
    hoy = pd.Timestamp.now(tz="UTC").tz_localize(None)
    assert dekad_index(last_closed_dekad()) < dekad_index(dekad_of_date(hoy))
