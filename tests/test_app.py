"""Coherencia entre lo que la app grafica y lo que ofrece descargar.

El principio es de transparencia: todo dato graficado tiene que poder
descargarse, y la descarga tiene que ser de ese dato y no de otro corte.
"""
import pandas as pd
import pytest

import streamlit_app as app
from app import texts
from app.controls import OVERVIEW, Query
from asis import config as cfg, panel
from asis.aggregate import to_country


def q(level, series_id, start, end, departments=()):
    return Query(level=level, series_id=series_id, start=start, end=end,
                 departments=list(departments))


@pytest.fixture(scope="module")
def last():
    if not panel.stored_series():
        pytest.skip("no hay panel construido")
    return panel.dekads("asi_gs1")[-1]


def test_pais_con_un_dekad_amplia_la_ventana(last):
    """Un solo dekad no forma una serie, asi que a nivel pais se amplia."""
    query, ampliada = app.effective(q("pais", "asi_gs1", last, last))
    assert ampliada
    assert query.start < query.end
    assert query.end == last


def test_la_grafica_y_la_descarga_de_pais_tienen_las_mismas_filas(last):
    """El defecto que esto fija: la figura mostraba 54 dekads y la pestana de
    datos una sola observacion, y las dos decian ser lo mismo."""
    query, _ = app.effective(q("pais", "asi_gs1", last, last))
    _muni, cut = app.slice_for(query)
    serie = to_country(panel.load(query.series_id, query.start, query.end))
    assert len(cut) == len(serie)
    assert set(cut["dekad_id"]) == set(serie["dekad_id"])


def test_los_otros_niveles_no_se_amplian(last):
    for level in ("departamento", "municipio"):
        query, ampliada = app.effective(q(level, "asi_gs1", last, last))
        assert not ampliada
        assert query.single


def test_un_rango_explicito_no_se_toca(last):
    query, ampliada = app.effective(q("pais", "asi_gs1",
                                      "2019-05-D1", last))
    assert not ampliada
    assert query.start == "2019-05-D1"


def test_toda_columna_mostrada_tiene_definicion(last):
    """Si una columna nueva aparece en el panel sin definicion, la pestana de
    datos la mostraria vacia."""
    for level in ("pais", "departamento", "municipio"):
        query, _ = app.effective(q(level, "asi_gs1", last, last))
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


# --- Resumen nacional: dos temporadas, nunca una cifra combinada -------------
def test_el_pais_ofrece_el_resumen_y_ninguna_serie_combinada():
    from app.controls import indicator_options
    opciones = indicator_options("pais", panel.available_series())
    assert list(opciones)[0] == OVERVIEW
    assert cfg.ASI_COMBINED not in opciones


def test_los_niveles_menores_no_ofrecen_el_resumen():
    from app.controls import indicator_options
    for level in ("departamento", "municipio"):
        assert OVERVIEW not in indicator_options(level, panel.available_series())


def test_el_resumen_da_una_columna_por_temporada(last):
    """El defecto que esto fija: el mapa de calor decia 27,0 y el KPI 25,2 para
    el mismo dekad, porque una figura leia la serie oficial de FAO y la otra el
    panel propio con las dos temporadas combinadas."""
    query, _ = app.effective(q("pais", OVERVIEW, last, last))
    tabla = app.overview_table(query)
    assert not tabla.empty
    for sid in ("asi_gs1", "asi_gs2"):
        if sid in panel.stored_series():
            assert panel.label_of(sid) in tabla.columns


def test_toda_columna_del_resumen_tiene_definicion(last):
    query, _ = app.effective(q("pais", OVERVIEW, last, last))
    shown = app.for_display(app.overview_table(query))
    sin_definir = [c for c in shown.columns if not texts.describe_column(c)]
    assert not sin_definir, f"columnas sin definicion {sin_definir}"


# --- Arranque con modulos locales viejos en memoria --------------------------
def test_un_modulo_local_viejo_en_memoria_no_tumba_el_arranque():
    """Tras un despliegue, Streamlit Cloud puede correr el script nuevo en un
    proceso que ya tiene importados los modulos locales viejos. Si el commit
    agrego un nombre, el import de arriba del script falla y la app cae sin
    dibujar nada. Paso dos veces en produccion: con texts.SOURCE_MD y con
    OVERVIEW_SERIES.

    Se corre en un subproceso porque hay que ensuciar sys.modules a proposito.
    """
    import subprocess
    import sys as _sys
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[1]
    codigo = (
        "import sys, types\n"
        # Un app.controls viejo, sin el nombre que el script nuevo importa.
        "sys.modules['app.controls'] = types.ModuleType('app.controls')\n"
        "import streamlit_app\n"
        "assert hasattr(streamlit_app, 'OVERVIEW_SERIES')\n"
        "print('arranco')\n"
    )
    r = subprocess.run([_sys.executable, "-c", codigo], cwd=raiz,
                       capture_output=True, text=True)
    assert r.returncode == 0, f"la app no arranco:\n{r.stderr[-2000:]}"
    assert "arranco" in r.stdout


# --- Controles de rango ------------------------------------------------------
def test_el_atajo_toma_los_ultimos_dekads(last):
    from app.controls import preset_range
    disponibles = panel.dekads("asi_gs1")
    desde, hasta = preset_range(disponibles, 36)
    assert hasta == disponibles[-1]
    assert len([d for d in disponibles if desde <= d <= hasta]) <= 36


def test_el_atajo_todo_cubre_la_serie_completa():
    from app.controls import preset_range
    disponibles = panel.dekads("asi_gs1")
    assert preset_range(disponibles, None) == (disponibles[0], disponibles[-1])


def test_los_atajos_no_se_salen_de_la_serie():
    """Pedir cinco anios sobre una serie mas corta debe quedarse en el primer
    dekad que existe, no inventar uno anterior."""
    from app.controls import preset_range
    corta = ["2026-08-D1", "2026-08-D2", "2026-08-D3"]
    assert preset_range(corta, 180) == ("2026-08-D1", "2026-08-D3")


# --- Figuras de departamento -------------------------------------------------
def test_la_cuadricula_trae_un_recuadro_por_departamento(last):
    """Una sola figura con todos los departamentos, y por eso una sola
    descarga."""
    query = q("departamento", "asi_gs1", "2026-01-D1", last)
    _muni, cut = app.slice_for(query)
    d = cut.dropna(subset=["mean"]).sort_values(["adm1_name", "dekad_id"])
    fig = app._department_grid_fig(query, d)
    assert fig is not None
    assert len(fig.data) == d["adm1_name"].nunique()


def test_el_mapa_de_departamento_con_rango_muestra_el_promedio(last):
    """Lo que el mapa pinta tiene que ser el promedio de la ventana y no el
    ultimo dekad ni el peor valor."""
    from asis.aggregate import over_window
    query = q("departamento", "asi_gs1", "2026-01-D1", last)
    _muni, cut = app.slice_for(query)
    promedio = over_window(cut, ["adm1_code", "adm1_name"], how="mean")
    esperado = cut.groupby("adm1_code")["mean"].mean()
    obtenido = promedio.set_index("adm1_code")["mean"]
    assert obtenido.round(6).equals(esperado.reindex(obtenido.index).round(6))


# --- Controles de rango, sobre la app corriendo ------------------------------
# Estos dos defectos no los veia ninguna prueba de funcion pura: salian de como
# Streamlit reconcilia el estado de los widgets, asi que hay que correr la app.
def _app():
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    # Ruta absoluta: AppTest resuelve las relativas contra este archivo.
    guion = Path(__file__).resolve().parents[1] / "streamlit_app.py"
    at = AppTest.from_file(str(guion), default_timeout=180)
    at.run()
    return at


def _estado(at, clave):
    try:
        return at.session_state[clave]
    except KeyError:
        return None


def test_el_atajo_elegido_no_se_marca_solo_como_personalizado():
    """Al mover el deslizador escribiendole la llave de su widget, Streamlit
    disparaba su on_change como si lo hubiera movido alguien, y el atajo recien
    elegido se marcaba solo como Personalizado."""
    at = _app()
    at.selectbox(key="atajo").set_value("5 años").run()
    assert not at.exception
    assert _estado(at, "atajo") == "5 años"
    desde, hasta = _estado(at, "ventana")
    assert desde < hasta


def test_mover_el_deslizador_no_revienta():
    """select_slider sin `value` explicito se declara de un solo extremo: al
    interactuar colapsaba la tupla a una cadena y la corrida siguiente reventaba
    al leer esa cadena como par de dekads."""
    at = _app()
    at.select_slider[0].set_range("2024-01-D1", "2026-08-D3").run()
    assert not at.exception
    assert _estado(at, "ventana") == ("2024-01-D1", "2026-08-D3")
    assert _estado(at, "atajo") == "Personalizado"


def test_el_atajo_describe_la_ventana_y_no_lo_ultimo_que_se_toco():
    """Se calcula, no se recuerda: si el deslizador queda justo en la ventana
    de un atajo, la etiqueta lo dice."""
    from app.controls import matching_preset, preset_range
    from asis import panel as _panel

    disponibles = _panel.dekads("asi_gs1")
    doce = preset_range(disponibles, 36)
    assert matching_preset(doce, disponibles) == "12 meses"
    assert matching_preset((disponibles[3], disponibles[-2]),
                           disponibles) == "Personalizado"


# --- Las dos vistas de una temporada, a nivel pais ---------------------------
def _frame_y_figuras(series_id, last):
    query = q("pais", series_id, "2025-03-D1", last)
    frame = app._season_frame(query, series_id)
    alto = min(600, max(app.SIDE_BY_SIDE_HEIGHT,
                        130 + 26 * frame["Year"].nunique()))
    return (query, frame, app._matrix_fig(frame, series_id, alto),
            app._country_series_fig(query, series_id, frame, alto))


def test_las_dos_figuras_de_la_temporada_grafican_el_mismo_dato(last):
    """El defecto que esto fija: el mapa de calor recortaba a la ventana de
    cultivo y la linea no, asi que la linea mostraba una meseta de valores
    congelados que el mapa de calor no tenia, y las dos decian ser el mismo
    indicador."""
    import numpy as np

    for series_id in ("asi_gs1", "asi_gs2"):
        _query, frame, matriz, linea = _frame_y_figuras(series_id, last)
        assert not frame.empty
        celdas = int(np.isfinite(matriz.data[0].z).sum())
        puntos = sum(len(t.x) for t in linea.data)
        assert celdas == len(frame), series_id
        assert puntos == len(frame), series_id


def test_la_temporada_no_grafica_dekads_congelados(last):
    """Fuera de la ventana de cultivo el raster trae valores, pero congelados
    en el cierre de la temporada: no describen esa fecha."""
    from asis.aggregate import season_columns

    for series_id in ("asi_gs1", "asi_gs2"):
        _query, frame, _m, _l = _frame_y_figuras(series_id, last)
        propios = set(season_columns(cfg.SERIES[series_id].season))
        assert set(frame["dekad_of_year"]) <= propios, series_id


def test_la_linea_se_corta_entre_temporadas(last):
    """Una linea continua uniria el cierre de una temporada con la apertura de
    la siguiente, como si el indice hubiera evolucionado entremedio."""
    _query, frame, _m, linea = _frame_y_figuras("asi_gs1", last)
    assert len(linea.data) == frame["Year"].nunique() > 1
