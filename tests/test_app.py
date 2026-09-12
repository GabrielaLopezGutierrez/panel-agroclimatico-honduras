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


def test_el_mapa_con_rango_se_anima_en_vez_de_promediar(last):
    """El promedio respondia otra pregunta: en un mapa lo que se busca es
    cuando empezo y cuando aflojo, y colapsar la ventana lo escondia."""
    from app.controls import MAX_FRAMES

    for level in ("departamento", "municipio"):
        query = q(level, "asi_gs1", "2026-01-D1", last)
        _muni, cut = app.slice_for(query)
        datos = _muni if level == "municipio" else cut
        todos = sorted(datos["dekad_id"].unique())
        marcos = app._animation_frames(todos, MAX_FRAMES)
        assert len(marcos) == len(todos) <= MAX_FRAMES, level
        assert marcos[-1] == todos[-1], level


def test_los_cuadros_de_la_animacion_tienen_tope():
    """Cada cuadro viaja al navegador con un valor por unidad: la ventana
    completa son 779 dekads por 290 municipios."""
    dekads = [f"20{y:02d}-{m:02d}-D{d}" for y in range(5, 27)
              for m in range(1, 13) for d in (1, 2, 3)]
    marcos = app._animation_frames(dekads, 48)
    assert len(marcos) <= 49          # el tope, mas el ultimo si no cayo justo
    assert marcos[0] == dekads[0]
    assert marcos[-1] == dekads[-1]   # el ultimo dekad siempre esta


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
    # El de la barra lateral, explicito: la figura de anomalia tiene el suyo.
    at.sidebar.select_slider[0].set_range("2024-01-D1", "2026-08-D3").run()
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
    return (query, frame, app._matrix_fig(query, frame, series_id, alto),
            app._lines_fig(query, frame, series_id, alto))


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
        puntos = sum(int(np.isfinite(np.array(t.y, dtype=float)).sum())
                     for t in linea.data)
        assert celdas == len(frame), series_id
        assert puntos == len(frame), series_id


def test_las_dos_figuras_comparten_el_eje_de_dekads(last):
    """Son la misma matriz en dos codificaciones, color y posicion: si el eje
    horizontal no coincide, no se pueden leer en paralelo."""
    for series_id in ("asi_gs1", "asi_gs2"):
        _query, _frame, matriz, linea = _frame_y_figuras(series_id, last)
        assert list(matriz.data[0].x) == list(linea.data[0].x), series_id


def test_el_kpi_es_el_ultimo_dekad_que_la_temporada_grafica(last):
    """El KPI mostraba el ultimo dekad de la ventana sin mirar si caia dentro
    de la temporada. En 2026-08-D3 eso daba un valor congelado del cierre de la
    postrera anterior mientras sus figuras terminaban en enero."""
    for series_id in ("asi_gs1", "asi_gs2"):
        query, frame, _m, _l = _frame_y_figuras(series_id, last)
        dekad, valor = app.season_kpi(query, series_id)
        ultimo = frame.sort_values("dekad_id").iloc[-1]
        assert dekad == ultimo["dekad_id"], series_id
        assert valor == pytest.approx(ultimo["mean"]), series_id


def test_la_temporada_no_grafica_dekads_congelados(last):
    """Fuera de la ventana de cultivo el raster trae valores, pero congelados
    en el cierre de la temporada: no describen esa fecha."""
    from asis.aggregate import season_columns

    for series_id in ("asi_gs1", "asi_gs2"):
        _query, frame, _m, _l = _frame_y_figuras(series_id, last)
        propios = set(season_columns(cfg.SERIES[series_id].season))
        assert set(frame["dekad_of_year"]) <= propios, series_id


def test_hay_una_linea_entera_por_temporada(last):
    """Antes las temporadas se encadenaban en un eje de fechas continuo y la
    linea quedaba cortada en los meses fuera de la ventana de cultivo.
    Superpuestas sobre el eje de dekads, cada temporada es una linea entera."""
    _query, frame, _m, linea = _frame_y_figuras("asi_gs1", last)
    assert len(linea.data) == frame["Year"].nunique() > 1


# --- Definiciones de las series ----------------------------------------------
def test_las_definiciones_van_plegadas_y_una_sola_vez():
    """Sueltas eran dos parrafos largos entre las cifras y las figuras, y la
    primera pantalla quedaba mas texto que datos."""
    at = _app()
    caja = at.expander[0]
    assert caja.label == texts.DEFINITIONS_BOX
    assert len(caja.markdown) == 2          # ASI y VCI en el resumen nacional
    frase = "Porcentaje del área de cultivo"
    assert len([m for m in at.markdown if frase in m.value]) == 1


def test_las_fichas_llevan_el_nombre_completo_de_la_serie():
    """La sigla sola no le dice nada a quien llega por primera vez, y tampoco
    permite buscar el indicador en el portal de FAO."""
    for familia, esperado in (("ASI", "Agricultural Stress Index"),
                              ("VCI", "Vegetation Condition Index")):
        nombre, _definicion = texts.INDICATOR_DEFINITIONS[familia]
        assert esperado in nombre
        assert familia in nombre            # la sigla sigue, entre parentesis
    assert "Agricultural Stress Index" in texts.INTRO
    assert "Vegetation Condition Index" in texts.INTRO


# --- Titulos de las figuras de temporada -------------------------------------
def test_las_dos_figuras_comparten_titulo_y_nombran_el_indicador(last):
    """Titularlas distinto las hacia leer como dos indicadores. Lo unico que
    cambia es la cola del subtitulo, que dice como esta codificada cada una."""
    query, _frame, matriz, linea = _frame_y_figuras("asi_gs1", last)
    titulos = [f.layout.title.text for f in (matriz, linea)]
    for titulo in titulos:
        assert "Índice de estrés agrícola" in titulo
        assert "(ASI)" in titulo
        assert query.window_compact in titulo
    encabezado = [t.split("<br>")[0] for t in titulos]
    assert encabezado[0] == encabezado[1]
    subtitulos = [t.split("<br>")[1] for t in titulos]
    assert subtitulos[0] != subtitulos[1]


def test_el_rango_del_titulo_va_en_forma_corta(last):
    """A media pantalla, "1er dek mar 2025 a 3er dek ago 2026" partia el titulo
    en dos renglones y le comia sitio a la figura."""
    query, _f, matriz, _l = _frame_y_figuras("asi_gs1", last)
    assert query.window_compact in matriz.layout.title.text
    assert query.window_label not in matriz.layout.title.text
    assert "dek " not in query.window_compact


def test_la_temporada_y_sus_meses_se_explican_bajo_las_figuras(last):
    """Salieron del subtitulo para acortarlo, pero no se perdieron: la nota de
    abajo se lee una vez para las dos figuras."""
    assert "{temporada}" in texts.SEASON_PAIR_NOTE
    assert "{meses}" in texts.SEASON_PAIR_NOTE
    assert "píxeles válidos" in texts.SEASON_PAIR_NOTE


def test_la_herramienta_dice_dekad_y_nunca_dekadal():
    """Un solo termino en toda la interfaz. Se eligio "dekad": es el de FAO
    GIEWS, es la clave temporal del panel y ya era la palabra en el resto de
    los textos."""
    for nombre in dir(texts):
        if nombre.startswith("_"):
            continue
        valor = getattr(texts, nombre)
        textos = ([valor] if isinstance(valor, str)
                  else [x for x in valor if isinstance(x, str)]
                  if isinstance(valor, (list, tuple)) else [])
        for t in textos:
            assert "dekadal" not in t.lower(), f"{nombre} dice dekadal"


# --- Precipitacion -----------------------------------------------------------
def test_la_seccion_de_lluvia_tiene_una_sola_descarga(last):
    """Las dos figuras contienen la misma ventana: el acercamiento de la
    anomalia es de vista, no de datos. Dos botones identicos invitarian a
    pensar que detras hay dos cortes distintos."""
    at = _app()
    nombres = [d.label for d in at.get("download_button")]
    por_figura = [n for n in nombres if texts.FIG_DOWNLOAD in n]
    # Dos temporadas, cada una con su serie y su superficie por clase; el VCI,
    # que no tiene temporada ni superficie; y la lluvia, que es una sola para
    # sus dos figuras.
    assert len(por_figura) == 6, nombres
    # Lo que esta prueba fija de verdad: la lluvia no tiene dos. Sus dos
    # figuras comparten ventana, asi que comparten descarga.
    claves = [d.key for d in at.get("download_button") if d.key]
    assert sum(1 for k in claves if "lluvia" in k) <= 1, claves


def test_la_anomalia_ya_no_usa_un_deslizador_de_la_pagina(last):
    """Vivia encima de la figura y obligaba a un rerun por cada acercamiento."""
    at = _app()
    etiquetas = [sl.label for sl in at.select_slider]
    assert texts.RAIN_BARS_RANGE not in etiquetas


# --- Recorrido completo de la interfaz ---------------------------------------
def test_todos_los_niveles_y_ventanas_dibujan_sin_error():
    """La prueba que faltaba. Al compactar el panel, los nombres pasaron a
    categoria y una etiqueta que los concatenaba con texto reventaba en
    departamento y en municipio: `Categorical + str`. Ninguna prueba recorria
    esas vistas, asi que el fallo llego a produccion.
    """
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    guion = str(Path(__file__).resolve().parents[1] / "streamlit_app.py")
    for nivel in ("pais", "departamento", "municipio"):
        for modo in ("Un dekad", "Rango"):
            at = AppTest.from_file(guion, default_timeout=300)
            at.run()
            at.radio(key="nivel").set_value(nivel).run()
            at.radio(key=f"modo_{nivel}").set_value(modo).run()
            assert not at.exception, (
                f"{nivel}/{modo}: {str(at.exception[0].value)[:200]}")


def test_cada_indicador_dibuja_en_cada_nivel():
    """Cambiar de indicador tampoco puede romper ninguna vista."""
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    guion = str(Path(__file__).resolve().parents[1] / "streamlit_app.py")
    for nivel in ("pais", "departamento", "municipio"):
        # Las ofrecidas, no las guardadas: el selector no acepta un valor que
        # no este entre sus opciones, y hay series construidas sin publicar.
        for serie in panel.available_series():
            at = AppTest.from_file(guion, default_timeout=300)
            at.run()
            at.radio(key="nivel").set_value(nivel).run()
            at.selectbox(key="serie").set_value(serie).run()
            assert not at.exception, (
                f"{nivel}/{serie}: {str(at.exception[0].value)[:200]}")


# --- Toda figura explica que esta mostrando ----------------------------------
def test_cada_figura_lleva_su_nota_en_cada_vista():
    """El principio es el mismo que el de la descarga por figura: quien mira una
    cifra tiene que poder saber de donde sale sin salir de la vista. Cada
    combinacion de nivel y ventana dibuja figuras distintas, asi que la nota que
    corresponde tambien cambia."""
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    guion = str(Path(__file__).resolve().parents[1] / "streamlit_app.py")
    esperado = {
        ("departamento", "Un dekad"): ("El mapa pinta",
                                       "Los dieciocho departamentos ordenados"),
        ("departamento", "Rango"): ("El mapa pinta",
                                    "Cada recuadro es un departamento"),
        ("municipio", "Un dekad"): ("El mapa pinta", "municipios de "),
        # En rango el municipio ya no muestra la matriz de calor sino la
        # cuadricula con las dos coberturas, y la superficie por clase se
        # mudo al resumen nacional.
        ("municipio", "Rango"): ("El mapa pinta", "Una celda por municipio"),
    }
    for (nivel, modo), marcas in esperado.items():
        at = AppTest.from_file(guion, default_timeout=300)
        at.run()
        at.radio(key="nivel").set_value(nivel).run()
        at.radio(key=f"modo_{nivel}").set_value(modo).run()
        assert not at.exception, f"{nivel}/{modo}"
        texto = " ".join(c.value for c in at.caption)
        for marca in marcas:
            assert marca in texto, f"{nivel}/{modo}: falta la nota '{marca}'"


def test_las_figuras_de_pais_tambien_llevan_nota():
    at = _app()
    texto = " ".join(c.value for c in at.caption)
    assert "Las dos figuras grafican el mismo dato" in texto   # ASI
    assert "La figura grafica el índice de condición" in texto  # VCI
    assert "Las dos figuras grafican la lluvia" in texto        # precipitacion


def test_el_kpi_estacional_se_fecha_dentro_de_la_temporada_en_todo_nivel(last):
    """Fuera de la ventana de cultivo el raster repite el valor con que cerro la
    temporada. Fechar la cifra en el ultimo dekad del rango la ponia a nombre de
    una fecha que ese valor no midio: en departamento y municipio la postrera
    aparecia fechada en agosto cuando su ultimo dato real era de enero.
    """
    from asis.aggregate import season_columns
    from asis.calendar import dekad_of_year

    for level in ("pais", "departamento", "municipio"):
        for series_id in ("asi_gs1", "asi_gs2"):
            query = q(level, series_id, "2025-03-D1", last)
            dekad, _valor = app.season_kpi(query, series_id)
            propios = season_columns(cfg.SERIES[series_id].season)
            assert dekad_of_year(dekad) in propios, f"{level}/{series_id}"


def test_el_kpi_no_estacional_se_fecha_en_su_ultimo_dato(last):
    """El VCI es continuo todo el anio: su ultimo dato es el de la ventana."""
    query = q("pais", "vci", "2025-03-D1", last)
    dekad, _valor = app.season_kpi(query, "vci")
    serie = panel.load("vci", query.start, query.end)
    assert dekad == max(serie["dekad_id"])


def test_un_dekad_fuera_de_temporada_no_fecha_el_kpi_en_ese_dekad(last):
    """El caso que quedaba roto: con la ventana en un solo dekad de agosto, la
    postrera no tiene ningun dato real dentro de esa ventana, y el KPI caia al
    extremo del rango. Ahora se mira hacia atras hasta el ultimo dekad en
    temporada, que es el que la cifra representa de verdad.
    """
    from asis.aggregate import season_columns
    from asis.calendar import dekad_of_year

    for level in ("pais", "departamento", "municipio"):
        query = q(level, "asi_gs2", last, last)      # un solo dekad, agosto
        assert dekad_of_year(last) not in season_columns("GS2"), (
            "el dekad de prueba deberia caer fuera de la postrera")
        dekad, valor = app.season_kpi(query, "asi_gs2")
        assert dekad_of_year(dekad) in season_columns("GS2"), level
        assert dekad < last, level
        assert valor == valor, level                 # no es NaN


def test_la_serie_de_pastizal_se_declara_como_forraje_y_no_como_cultivo():
    """El pastizal comparte familia con el cultivo, asi que la caja de
    definiciones dice "area de cultivo" por su cuenta. Sin la nota de cobertura,
    la pantalla mostraria pastura mientras el texto habla de cosecha."""
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    from app import texts

    if "asi_gs1_pasto" not in panel.available_series():
        pytest.skip("el pastizal esta construido pero no se ofrece en el "
                    "selector (config.SERIES, offered=False); esta prueba "
                    "vuelve sola en cuanto se publique")
    guion = str(Path(__file__).resolve().parents[1] / "streamlit_app.py")
    at = AppTest.from_file(guion, default_timeout=300)
    at.run()
    at.selectbox(key="serie").set_value("asi_gs1_pasto").run()
    assert not at.exception, str(at.exception[0].value)[:200]
    texto = " ".join(m.value for m in at.markdown)
    assert texts.COVER_DEFINITIONS["pastizal"][0] in texto
    assert "forraje del ganado" in texto
    # Y la de cultivo no debe arrastrar la nota de pastura.
    at2 = AppTest.from_file(guion, default_timeout=300)
    at2.run()
    at2.selectbox(key="serie").set_value("asi_gs1").run()
    assert texts.COVER_DEFINITIONS["pastizal"][0] not in " ".join(
        m.value for m in at2.markdown)


# --- Series que no cubren el mismo periodo -----------------------------------
def test_un_periodo_fuera_de_cobertura_se_detecta_antes_de_recortarlo():
    """El defecto que esto fija: `_clamp` lleva cualquier codigo fuera de rango
    al primer dekad disponible, asi que despues de recortar, un periodo de 2005
    a 2008 sobre una serie que arranca en 2010 es indistinguible de haber pedido
    ese primer dekad. La deteccion tiene que ocurrir sobre lo pedido."""
    from app.controls import outside_coverage

    disponibles = ["2010-01-D1", "2010-01-D2", "2010-01-D3"]
    # Entero antes y entero despues: no hay nada que mostrar.
    assert outside_coverage(("2005-01-D1", "2008-12-D3"), disponibles) == \
        ("2005-01-D1", "2008-12-D3")
    assert outside_coverage(("2026-01-D1", "2026-02-D1"), disponibles)
    # Solapamiento parcial y contencion: ahi si hay dato y se recorta.
    assert outside_coverage(("2008-01-D1", "2010-01-D2"), disponibles) is None
    assert outside_coverage(("2010-01-D1", "2010-01-D3"), disponibles) is None
    assert outside_coverage(("2010-01-D2", "2010-01-D2"), disponibles) is None


def test_el_pastizal_fuera_de_su_periodo_queda_en_blanco_y_dice_por_que():
    """El pastizal arranca cinco anios despues que el cultivo. Al cambiar de
    indicador con una ventana vieja, la app mostraba el primer dekad del
    pastizal como si fuera el periodo pedido. Ahora no dibuja nada y lo explica.

    Se comprueba contra la app corriendo porque el defecto estaba en la
    reconciliacion entre `session_state` y los widgets, que es justo lo que un
    test de funcion pura no ve."""
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    if "asi_gs1_pasto" not in panel.available_series():
        pytest.skip("hace falta una serie ofrecida con otra cobertura temporal; "
                    "el pastizal la tiene pero hoy no se ofrece. La logica "
                    "sigue fijada por test_un_periodo_fuera_de_cobertura_*")
    primero = panel.dekads("asi_gs1_pasto")[0]
    anterior = panel.dekads("asi_gs1")[0]
    assert anterior < primero, "el pastizal deberia arrancar despues"

    guion = str(Path(__file__).resolve().parents[1] / "streamlit_app.py")
    at = AppTest.from_file(guion, default_timeout=300)
    at.run()
    at.radio(key="nivel").set_value("pais").run()
    at.selectbox(key="serie").set_value("asi_gs1").run()
    at.session_state["ventana"] = (anterior, "2008-12-D3")
    at.run()
    assert at.tabs, "el cultivo si cubre ese periodo"

    at.selectbox(key="serie").set_value("asi_gs1_pasto").run()
    assert not at.exception, str(at.exception[0].value)[:200]
    assert not at.tabs, "sin cobertura no se dibuja ninguna vista"
    aviso = " ".join(i.value for i in at.info)
    assert "se publica desde" in aviso
    assert "queda entero fuera" in aviso


def test_el_encuadre_de_forraje_dice_niveles_y_cobertura():
    """La nota de pastizal responde tres cosas: que mide, donde se puede ver y
    desde cuando. La fecha sale del panel y no de un anio escrito a mano."""
    from app.controls import series_help
    from asis.calendar import dekad_label

    if "asi_gs1_pasto" not in panel.stored_series():
        pytest.skip("no hay panel de pastizal construido")
    # Esta no depende de que se ofrezca: el texto y su relleno existen igual, y
    # es lo que hay que tener listo para cuando se publique.
    desde = dekad_label(panel.dekads("asi_gs1_pasto")[0])
    nota = texts.COVER_DEFINITIONS["pastizal"][1].format(desde=desde)
    assert "forraje del ganado" in nota
    assert "país, departamento y municipio" in nota
    assert desde in nota
    assert "{" not in nota
    # Y la ayuda del selector tambien se llena sola.
    for sid in ("asi_gs1_pasto", "asi_gs2_pasto"):
        ayuda = series_help(sid)
        assert desde in ayuda and "{" not in ayuda


# --- Contraste entre coberturas ----------------------------------------------
def test_la_pastura_se_empareja_por_temporada_y_no_por_el_nombre():
    """El id es una convencion. Emparejar por texto ataria el contraste a que
    nadie renombre una carpeta, y dejaria pasar una pareja de otra temporada."""
    assert panel.pasture_counterpart("asi_gs1") == "asi_gs1_pasto"
    assert panel.pasture_counterpart("asi_gs2") == "asi_gs2_pasto"
    for sid, s in cfg.SERIES.items():
        pareja = panel.pasture_counterpart(sid)
        if pareja is None:
            continue
        otra = cfg.SERIES[pareja]
        assert s.cover == "cultivo" and otra.cover == "pastizal"
        assert s.season == otra.season and s.family == otra.family
    # El VCI no tiene contraparte y una serie de pastura no es la suya propia.
    assert panel.pasture_counterpart("vci") is None
    assert panel.pasture_counterpart("asi_gs1_pasto") is None


def test_los_municipios_de_poca_muestra_se_marcan_y_no_se_borran():
    """Con pocos pixeles la media salta de a varios puntos y no distingue
    clases, pero borrarlos cambiaria en silencio cuantos municipios se ven."""
    from asis import viz

    if "asi_gs1_pasto" not in panel.stored_series():
        pytest.skip("no hay panel de pastizal construido")
    dk = panel.dekads("asi_gs1")[-1]
    cul = panel.load("asi_gs1", dk, dk)
    pas = panel.load("asi_gs1_pasto", dk, dk)
    fig = viz.cover_scatter(cul, pas, "t", min_px=cfg.MIN_PX_COMPARABLE)
    puntos = [t for t in fig.data if t.mode == "markers"]
    dibujados = sum(len(t.x) for t in puntos)
    # Ningun municipio con las dos coberturas queda fuera de la figura.
    juntos = cul.dropna(subset=["mean"]).merge(
        pas.dropna(subset=["mean"]), on="adm2_code", suffixes=("_c", "_p"))
    assert dibujados == len(juntos)
    # Y los de poca muestra estan, en su propia traza.
    flacos = ((juntos["n_px_c"] < cfg.MIN_PX_COMPARABLE)
              | (juntos["n_px_p"] < cfg.MIN_PX_COMPARABLE)).sum()
    if flacos:
        traza = [t for t in puntos if "píxeles" in t.name][0]
        assert len(traza.x) == flacos


def test_el_piso_de_pixeles_se_justifica_por_resolucion():
    """No es un umbral de calidad sino de resolucion: la media sobre n pixeles
    solo toma valores de 100/n en 100/n. El piso tiene que dejar el salto por
    debajo de la banda de alerta mas angosta del ASI, que son diez puntos."""
    cortes = cfg.CLASSES["ASI"][0]
    banda = min(b - a for a, b in zip(cortes, cortes[1:]))
    assert 100 / cfg.MIN_PX_COMPARABLE < banda


def test_en_rango_el_municipio_muestra_la_cuadricula_y_no_la_matriz():
    """El cambio de vista: con contraparte de pastura la matriz de calor deja
    su lugar a la cuadricula de series, que es la unica que puede mostrar las
    dos coberturas sin duplicar la figura. Sin contraparte, el VCI conserva la
    matriz."""
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    if "asi_gs1_pasto" not in panel.stored_series():
        pytest.skip("no hay panel de pastizal construido")
    guion = str(Path(__file__).resolve().parents[1] / "streamlit_app.py")
    at = AppTest.from_file(guion, default_timeout=300)
    at.run()
    at.radio(key="nivel").set_value("municipio").run()
    at.selectbox(key="serie").set_value("asi_gs1").run()
    at.radio(key="modo_municipio").set_value("Rango").run()
    assert not at.exception, str(at.exception[0].value)[:200]
    texto = " ".join(c.value for c in at.caption)
    assert "Una celda por municipio" in texto
    assert "Matriz de municipio por dekad" not in texto
    assert [m for m in at.multiselect if m.label == "Municipios en la figura"]

    at.selectbox(key="serie").set_value("vci").run()
    texto = " ".join(c.value for c in at.caption)
    assert "Matriz de municipio por dekad" in texto
    assert "pastura" not in texto


def test_antes_de_2010_se_dibuja_el_cultivo_y_no_la_pastura():
    """La pastura se publica cinco anios despues. La vista no se vacia: la
    pregunta principal es el cultivo y el contraste es contexto."""
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    if "asi_gs1_pasto" not in panel.stored_series():
        pytest.skip("no hay panel de pastizal construido")
    guion = str(Path(__file__).resolve().parents[1] / "streamlit_app.py")
    at = AppTest.from_file(guion, default_timeout=300)
    at.run()
    at.radio(key="nivel").set_value("municipio").run()
    at.selectbox(key="serie").set_value("asi_gs1").run()
    at.radio(key="modo_municipio").set_value("Rango").run()
    at.session_state["ventana"] = ("2006-05-D1", "2008-10-D3")
    at.run()
    assert not at.exception, str(at.exception[0].value)[:200]
    assert at.get("plotly_chart"), "la figura del cultivo tiene que dibujarse"
    texto = " ".join(c.value for c in at.caption)
    assert "Solo se dibuja el cultivo" in texto


def test_la_superficie_por_clase_vive_en_pais_y_una_por_temporada():
    """Vivia en el ranking de municipio, donde se calculaba sobre los municipios
    en pantalla: con un filtro de departamento los km2 eran los de ese
    subconjunto y el titulo no lo decia. En pais la cifra es inequivoca, y va
    una por temporada porque las dos nunca se combinan."""
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    guion = str(Path(__file__).resolve().parents[1] / "streamlit_app.py")
    at = AppTest.from_file(guion, default_timeout=300)
    at.run()
    assert not at.exception, str(at.exception[0].value)[:200]
    notas = [c.value for c in at.caption if "clase de severidad" in c.value]
    assert len(notas) == 2, notas

    at2 = AppTest.from_file(guion, default_timeout=300)
    at2.run()
    at2.radio(key="nivel").set_value("municipio").run()
    at2.radio(key="modo_municipio").set_value("Rango").run()
    texto = " ".join(c.value for c in at2.caption)
    assert "clase de severidad" not in texto


# --- Acceso a la nota metodologica -------------------------------------------
def test_la_nota_metodologica_viaja_con_el_codigo():
    """El PDF esta en el repositorio y no en un sitio ajeno: la metodologia es
    parte de la herramienta, y un documento de afuera puede cambiar o caerse sin
    que este repositorio se entere."""
    from asis import config as cfg

    pdf = cfg.ROOT / texts.NOTE_PATH
    assert pdf.exists(), f"falta {pdf}"
    assert pdf.read_bytes()[:5] == b"%PDF-", "no parece un PDF"


def test_el_enlace_de_la_nota_apunta_al_archivo_que_esta_en_el_repositorio():
    """El enlace pasa por GitHub porque Streamlit Community Cloud no sirve la
    carpeta static/. Eso lo vuelve fragil de una forma concreta: si el archivo
    se mueve o se renombra, la URL queda apuntando a un 404 sin que nada falle
    en la app. Esto ata la URL a la ruta real."""
    from asis import config as cfg

    assert texts.NOTE_URL.startswith(f"{cfg.REPO_URL}/blob/main/")
    assert texts.NOTE_URL.endswith(texts.NOTE_PATH)
    # `blob` abre el PDF en un visor; `raw` lo entrega como octet-stream y el
    # navegador lo descarga, que no es lo que se quiere de un icono.
    assert "raw" not in texts.NOTE_URL


def test_no_queda_configuracion_que_prometa_el_servido_estatico():
    """Se probo `enableStaticServing` y en el despliegue la ruta app/static/
    devuelve el HTML de la app en vez del archivo. Dejar la opcion encendida
    invitaria a creer que esa ruta funciona."""
    from asis import config as cfg

    cfgtoml = (cfg.ROOT / ".streamlit" / "config.toml").read_text(
        encoding="utf-8")
    activas = [l for l in cfgtoml.splitlines()
               if "enableStaticServing" in l and not l.strip().startswith("#")]
    assert not activas, activas


def test_el_encabezado_ofrece_la_nota_en_la_esquina_superior():
    """Va antes del titulo: quien duda de una cifra tiene las ecuaciones a un
    clic sin salir de la herramienta."""
    at = _app()
    crudo = " ".join(m.value for m in at.markdown)
    assert texts.NOTE_URL in crudo
    assert texts.NOTE_LABEL in crudo
    assert 'target="_blank"' in crudo or "target='_blank'" in crudo
