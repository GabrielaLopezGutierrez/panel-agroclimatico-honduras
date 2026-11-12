"""Las tablas anchas y los archivos que Flourish lee por URL.

Lo que estas pruebas protegen no es el calculo -ese ya lo cubren test_aggregate
y test_validation- sino la forma. Un grafico publicado en Flourish apunta a uno
de estos archivos por su nombre y lee sus columnas por su encabezado, asi que
nombre y encabezado dejan de ser detalle interno y pasan a ser interfaz: si
cambian, el grafico se rompe en silencio y nadie se entera hasta que alguien lo
mira. Es la misma razon por la que test_nota ata las constantes de la nota al
codigo.
"""
import pandas as pd
import pytest

from asis import config as cfg, panel, wide
from asis.aggregate import (climatology_frame, season_columns, to_country,
                            to_department)


def _marco(series_id="asi_gs1", dekads=18):
    """La serie nacional de una temporada, como la recibe la figura."""
    if series_id not in panel.stored_series():
        pytest.skip(f"no hay panel de {series_id}")
    todos = panel.dekads(series_id)
    df = panel.load(series_id, todos[-dekads], todos[-1])
    season = cfg.SERIES[series_id].season
    frame = climatology_frame(to_country(df), season)
    if season:
        frame = frame[frame["dekad_of_year"].isin(season_columns(season))]
    return frame, season


# --- La forma ---------------------------------------------------------------
def test_la_tabla_de_temporada_pone_los_dekads_en_filas_y_los_anios_en_columnas():
    """Es la vuelta del pivote del mapa de calor, que indexa por anio. Flourish
    lee la primera columna como eje y el resto como series, asi que la fila
    tiene que ser el dekad y la columna la campania, no al reves."""
    frame, season = _marco()
    t = wide.season_table(frame, season)
    assert list(t.columns)[0] == "dekad"
    assert len(t.columns) > 1, "al menos una campania"
    # Cada encabezado de campania es un anio o un par de anios, nunca un codigo
    # de columna del panel.
    for c in list(t.columns)[1:]:
        assert c[:4].isdigit(), c
    # Y el eje son etiquetas de dekad del anio, no fechas: cada columna es un
    # anio distinto y una fecha unica no existiria.
    assert all(" D" in v for v in t["dekad"])


def test_la_postrera_rotula_su_campania_con_los_dos_anios():
    """La postrera va de septiembre a enero. Rotulada solo con el primer anio
    se lee como atrasada: la columna diria 2025 y llega hasta enero de 2026."""
    frame, season = _marco("asi_gs2", dekads=40)
    t = wide.season_table(frame, season)
    assert any("-" in c for c in list(t.columns)[1:]), list(t.columns)


def test_la_referencia_entra_como_una_columna_mas():
    """El promedio de largo plazo no es un anio mas, pero en la tabla es una
    columna como las otras: es lo que Flourish sabe dibujar."""
    frame, _ = _marco()
    lta = pd.Series({d: 1.5 for d in frame["dekad_of_year"].unique()})
    t = wide.season_table(frame, "GS1", reference=lta,
                          reference_label="promedio de largo plazo")
    assert list(t.columns)[-1] == "promedio de largo plazo"
    assert (t["promedio de largo plazo"] == 1.5).all()


def test_el_ranking_sale_con_el_peor_primero():
    """La figura los dibuja al reves porque una barra horizontal de Plotly
    crece de abajo hacia arriba. En una tabla el orden de lectura es el otro."""
    if "asi_gs1" not in panel.stored_series():
        pytest.skip("no hay panel construido")
    dk = panel.dekads("asi_gs1")[-1]
    d = panel.load("asi_gs1", dk, dk)
    t = wide.ranking_table(d, "ASI %", family="ASI", top=10)
    assert list(t.columns) == ["municipio", "departamento", "ASI %"]
    assert len(t) == 10
    assert t["ASI %"].is_monotonic_decreasing, "el ASI va de peor a mejor"
    # En el VCI peor es mas bajo, asi que el orden se invierte.
    v = wide.ranking_table(d, "VCI", family="VCI", top=10)
    assert v["VCI"].is_monotonic_increasing


def test_el_contraste_de_coberturas_las_deja_en_columnas_separadas():
    """Nunca se promedian ni se restan: en la tabla conviven, cada una con la
    suya, que es lo que la dispersion dibuja."""
    if "asi_gs1_pasto" not in panel.stored_series():
        pytest.skip("no hay panel de pastizal")
    dk = panel.dekads("asi_gs1_pasto")[-1]
    t = wide.cover_table(panel.load("asi_gs1", dk, dk),
                         panel.load("asi_gs1_pasto", dk, dk))
    assert list(t.columns) == ["municipio", "departamento", "cultivo",
                               "pastizal"]


def test_la_anomalia_es_la_unica_con_fecha_de_verdad():
    """Su figura no es una climatologia: la lluvia no depende de la ventana de
    cultivo de ningun indicador y se grafica de corrido."""
    lluvia = panel.national("serie_nacional_lluvia")
    if not len(lluvia):
        pytest.skip("no hay serie de lluvia")
    t = wide.anomaly_table(lluvia.tail(20))
    assert list(t.columns) == ["fecha", "dekad", "anomalía (%)"]
    assert t["fecha"].is_monotonic_increasing


def test_las_tablas_vacias_no_inventan_columnas():
    """Sin dato la figura no se dibuja y la descarga no debe ofrecer un CSV con
    encabezados y nada debajo, que se lee como "no hubo estres"."""
    vacio = pd.DataFrame(columns=["dekad_of_year", "Year", "mean", "dekad_id",
                                  "date", "adm2_name", "adm1_name"])
    assert wide.season_table(vacio, "GS1").empty
    assert wide.anomaly_table(vacio, value_col="mean").empty
    assert wide.ranking_table(vacio, "ASI %").empty
    assert wide.cover_table(vacio, vacio).empty


def test_los_decimales_son_los_mismos_en_todas():
    """Dos decimales en todo: mas no son mas exactitud, y el ruido de punto
    flotante se publica tal cual si nadie redondea."""
    frame, season = _marco()
    t = wide.season_table(frame, season)
    for c in list(t.columns)[1:]:
        v = t[c].dropna()
        assert (v.round(wide.DECIMALS) == v).all(), c


# --- Los archivos publicados ------------------------------------------------
ENCABEZADOS = {
    "serie_nacional_asi_primera.csv": "dekad",
    "serie_nacional_asi_postrera.csv": "dekad",
    "serie_nacional_vci.csv": "dekad",
    "lluvia_nacional.csv": "dekad",
    "lluvia_anomalia.csv": "fecha",
    "ranking_municipios.csv": "municipio",
    "ranking_departamentos.csv": "departamento",
    "coberturas.csv": "municipio",
}


def test_la_ventana_publicada_son_dieciocho_meses():
    """Cincuenta y cuatro dekads contados hacia atras desde el ultimo
    publicado, no desde una fecha del calendario: el archivo lo escribe un
    proceso sin interfaz y la ventana tiene que avanzar sola."""
    inicio, fin = wide.window("2026-10-D3")
    assert fin == "2026-10-D3"
    assert inicio == "2025-05-D1"
    assert wide.WINDOW_DEKADS == 54


def test_los_archivos_publicados_conservan_su_nombre_y_su_primera_columna():
    """Un grafico de Flourish apunta a un nombre de archivo y lee un
    encabezado. Si alguno cambia, el grafico se rompe sin avisar."""
    carpeta = cfg.DATA / "flourish"
    if not carpeta.exists():
        pytest.skip("todavia no se generaron; corra scripts/tablas_flourish.py")
    for archivo, primera in ENCABEZADOS.items():
        ruta = carpeta / archivo
        assert ruta.exists(), f"falta {archivo}"
        cabecera = ruta.read_text(encoding="utf-8").splitlines()[0]
        assert not cabecera.startswith("﻿"), (
            f"{archivo} arranca con BOM: el primer encabezado le queda pegado")
        assert cabecera.split(",")[0] == primera, f"{archivo}: {cabecera}"


def test_los_archivos_publicados_caben_en_una_carga_de_flourish():
    """El limite de una carga en linea son unos 100 KB y mil filas. Estos van
    por URL y no por ahi, pero si alguno se acerca es senial de que la vista
    dejo de ser un grafico y paso a ser una descarga de datos."""
    carpeta = cfg.DATA / "flourish"
    if not carpeta.exists():
        pytest.skip("todavia no se generaron")
    for archivo in ENCABEZADOS:
        ruta = carpeta / archivo
        filas = len(ruta.read_text(encoding="utf-8").splitlines()) - 1
        assert filas <= 1000, f"{archivo}: {filas} filas"
        assert ruta.stat().st_size <= 100_000, f"{archivo}: {ruta.stat().st_size} bytes"


def test_el_script_y_la_app_arman_la_misma_tabla():
    """Es la promesa del modulo: lo que se copia de la app y lo que Flourish lee
    por URL son el mismo objeto. Si divergieran, la cifra publicada y la
    dibujada dejarian de ser la misma sin que nada lo detecte."""
    carpeta = cfg.DATA / "flourish"
    if not carpeta.exists() or "asi_gs1" not in panel.stored_series():
        pytest.skip("todavia no se generaron")
    ultimo = max(panel.dekads(s)[-1] for s in panel.stored_series())
    inicio, fin = wide.window(ultimo)
    df = panel.load("asi_gs1", inicio, fin)
    frame = climatology_frame(to_country(df), "GS1")
    frame = frame[frame["dekad_of_year"].isin(season_columns("GS1"))]
    esperado = wide.season_table(frame, "GS1")
    publicado = pd.read_csv(carpeta / "serie_nacional_asi_primera.csv")
    assert list(publicado.columns) == list(esperado.columns)
    assert len(publicado) == len(esperado)


def test_el_ranking_departamental_no_repite_la_columna_de_grupo():
    """Un departamento no tiene departamento encima: la tabla es de dos
    columnas, no de tres con una repetida."""
    if "asi_gs1" not in panel.stored_series():
        pytest.skip("no hay panel construido")
    dk = panel.dekads("asi_gs1")[-1]
    dep = to_department(panel.load("asi_gs1", dk, dk))
    t = wide.ranking_table(dep, "ASI %", name_col="adm1_name", group_col=None)
    assert list(t.columns) == ["departamento", "ASI %"]
