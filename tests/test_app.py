"""Coherencia entre lo que la app grafica y lo que ofrece descargar.

El principio es de transparencia: todo dato graficado tiene que poder
descargarse, y la descarga tiene que ser de ese dato y no de otro corte.
"""
import pandas as pd
import pytest

import streamlit_app as app
from app import texts
from app.controls import Query
from asis import config as cfg, panel
from asis.aggregate import to_country


def q(level, series_id, start, end, departments=()):
    return Query(level=level, series_id=series_id, start=start, end=end,
                 departments=list(departments))


@pytest.fixture(scope="module")
def last():
    if not panel.stored_series():
        pytest.skip("no hay panel construido")
    return panel.dekads(cfg.ASI_COMBINED)[-1]


def test_pais_con_un_dekad_amplia_la_ventana(last):
    """Un solo dekad no forma una serie, asi que a nivel pais se amplia."""
    query, ampliada = app.effective(q("pais", cfg.ASI_COMBINED, last, last))
    assert ampliada
    assert query.start < query.end
    assert query.end == last


def test_la_grafica_y_la_descarga_de_pais_tienen_las_mismas_filas(last):
    """El defecto que esto fija: la figura mostraba 54 dekads y la pestana de
    datos una sola observacion, y las dos decian ser lo mismo."""
    query, _ = app.effective(q("pais", cfg.ASI_COMBINED, last, last))
    _muni, cut = app.slice_for(query)
    serie = to_country(panel.load(query.series_id, query.start, query.end))
    assert len(cut) == len(serie)
    assert set(cut["dekad_id"]) == set(serie["dekad_id"])


def test_los_otros_niveles_no_se_amplian(last):
    for level in ("departamento", "municipio"):
        query, ampliada = app.effective(q(level, cfg.ASI_COMBINED, last, last))
        assert not ampliada
        assert query.single


def test_un_rango_explicito_no_se_toca(last):
    query, ampliada = app.effective(q("pais", cfg.ASI_COMBINED,
                                      "2019-05-D1", last))
    assert not ampliada
    assert query.start == "2019-05-D1"


def test_toda_columna_mostrada_tiene_definicion(last):
    """Si una columna nueva aparece en el panel sin definicion, la pestana de
    datos la mostraria vacia."""
    for level in ("pais", "departamento", "municipio"):
        query, _ = app.effective(q(level, cfg.ASI_COMBINED, last, last))
        _muni, cut = app.slice_for(query)
        shown = app.for_display(cut)
        sin_definir = [c for c in shown.columns
                       if not texts.describe_column(c)]
        assert not sin_definir, f"{level}: columnas sin definicion {sin_definir}"


def test_las_definiciones_no_estan_vacias():
    for nombre, texto in texts.COLUMNS.items():
        assert texto.strip(), f"{nombre} sin definicion"


def test_el_nivel_pais_no_ofrece_mapa():
    """Un mapa nacional seria una sola clase para todo el pais."""
    assert "Mapa" not in app.TABS["pais"]
    assert "municipio" in panel.LEVEL_GEO and "pais" not in panel.LEVEL_GEO


def test_cada_nivel_termina_en_la_pestana_de_ayuda():
    for level, tabs in app.TABS.items():
        assert tabs[-1] == texts.HELP_TAB, level
        assert "Datos" in tabs, level
