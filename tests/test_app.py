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


# --- Cita de la fuente -------------------------------------------------------
def test_hay_una_sola_url_de_fuente():
    """El enlace vive en config y de ahi lo toman la app, las figuras y los
    cuadernos: si se duplicara, una copia quedaria vieja."""
    assert cfg.SOURCE_URL.startswith("https://www.fao.org/giews/")
    assert "code=HND" in cfg.SOURCE_URL


def test_la_nota_al_pie_de_las_figuras_enlaza_a_fao():
    """La nota va en cada figura, asi que es la cita mas vista del proyecto."""
    assert "<a href=" in cfg.SOURCE_NOTE
    assert cfg.SOURCE_NAME in cfg.SOURCE_NOTE
    # El ampersand escapado deja el atributo bien formado.
    assert "&amp;type=11" in cfg.SOURCE_NOTE


def test_las_citas_de_la_app_enlazan_a_fao():
    for nombre in ("SOURCE_MD", "PORTAL_MD", "SOURCE_TEMPLATE",
                   "VALIDATION_TEMPLATE", "AI_NOTE"):
        texto = getattr(texts, nombre)
        assert cfg.SOURCE_URL in texto, f"{nombre} cita FAO sin enlazarla"


def test_las_figuras_llevan_la_nota_con_el_enlace():
    """Se comprueba sobre una figura de verdad: si style_fig dejara de poner la
    anotacion, la cita desapareceria de todas las vistas a la vez."""
    import pandas as pd
    from asis import viz
    d = pd.DataFrame({"dekad_id": ["2026-08-D1", "2026-08-D2"],
                      "date": pd.to_datetime(["2026-08-01", "2026-08-11"]),
                      "mean": [10.0, 12.0]})
    fig = viz.series_fig(d, "mean", "t", family="ASI")
    notas = [a.text for a in fig.layout.annotations]
    assert any(cfg.SOURCE_URL.replace("&", "&amp;") in n for n in notas)
