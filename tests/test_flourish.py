"""Las tablas anchas y los archivos que Flourish lee por URL.

Lo que estas pruebas protegen no es el calculo -ese ya lo cubren test_aggregate
y test_validation- sino la forma. Un grafico publicado en Flourish apunta a uno
de estos archivos por su nombre y lee sus columnas por su encabezado, asi que
nombre y encabezado dejan de ser detalle interno y pasan a ser interfaz: si
cambian, el grafico se rompe en silencio y nadie se entera hasta que alguien lo
mira. Es la misma razon por la que test_nota ata las constantes de la nota al
codigo.
"""
import json

import pandas as pd
import pytest

from asis import config as cfg, panel, wide
from asis.aggregate import (climatology_frame, narrowest_band,
                            season_columns, to_country, to_department)


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
    assert any("–" in c for c in list(t.columns)[1:]), list(t.columns)
    # Con raya y no con guion: "2025-26" escrito con guion lo lee como fecha
    # cualquier herramienta que adivine tipos, y el eje de campanias sale como
    # una serie de meses inventados.
    assert not any("-" in c for c in list(t.columns)[1:]), list(t.columns)


def test_la_campania_que_arranca_a_medias_solo_se_poda_al_publicar():
    """La postrera que abrio en septiembre de 2004 entra al panel solo por su
    cola de enero de 2005. Publicada como campania desordena el eje y miente
    sobre lo que cubre, asi que se descarta. Pero con una ventana elegida en
    pantalla la primera campania casi siempre empieza a mitad, y descartarla
    ahi borraria justo lo que la persona pidio ver: por eso lo pide quien
    publica y no la funcion."""
    frame, season = _marco("asi_gs2", dekads=400)
    entera = wide.season_table(frame, season)
    podada = wide.season_table(frame, season, drop_partial_start=True)
    assert len(podada.columns) <= len(entera.columns)
    if pd.isna(entera.iloc[0, 1]):
        assert len(podada.columns) == len(entera.columns) - 1
        assert not pd.isna(podada.iloc[0, 1]), "la primera ya arranca entera"
    # Y por defecto no se poda nada.
    assert list(entera.columns) == list(
        wide.season_table(frame, season).columns)


def test_el_mapa_con_rango_fecha_cada_cifra():
    """Con un rango el mapa se recorre dekad por dekad, asi que una fila por
    unidad no alcanza: la descarga tiene que decir de cuando es cada cifra."""
    if "asi_gs1" not in panel.stored_series():
        pytest.skip("no hay panel construido")
    dks = panel.dekads("asi_gs1")[-3:]
    d = panel.load("asi_gs1", dks[0], dks[-1])
    uno = wide.map_table(d[d["dekad_id"] == dks[-1]], "ASI %")
    assert "dekad" not in uno.columns
    varios = wide.map_table(d, "ASI %", with_dekad=True)
    assert list(varios.columns)[2] == "dekad"
    assert varios["dekad"].nunique() == len(dks)
    assert len(varios) == len(d)


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
    # Repartida por clase, la cifra va en la columna de su clase y las otras
    # llevan cero. Es como el grafico de afuera colorea una barra, que es por
    # columna y no por valor; apiladas suman el valor.
    con = wide.ranking_table(d, "ASI %", family="ASI", top=10,
                             spread_class=True)
    assert list(con.columns) == ["municipio", "departamento",
                                 *cfg.CLASSES["ASI"][1]]
    clases = con[cfg.CLASSES["ASI"][1]]
    assert (clases != 0).sum(axis=1).max() <= 1, "una clase por fila"
    assert (clases.sum(axis=1).values == t["ASI %"].values).all()
    # Cero y no vacio: una clase sin nadie en el dekad seguiria siendo una
    # columna numerica. Vacia la tipan como texto y la serie deja de
    # dibujarse, que es como se rompio la primera version.
    assert clases.notna().all().all()
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
    # Con grupo, la columna por la que colorea el grafico publicado: el mismo
    # criterio que la figura de la app, que pinta de gris cuando las dos
    # coberturas no se separan mas que la banda de clase mas angosta.
    g = wide.cover_table(panel.load("asi_gs1", dk, dk),
                         panel.load("asi_gs1_pasto", dk, dk), group=True)
    assert list(g.columns)[-1] == "grupo"
    assert set(g["grupo"]) <= {wide.SAME_LABEL, wide.PASTURE_WORSE_LABEL,
                               wide.CROP_WORSE_LABEL}
    banda = narrowest_band("ASI")
    iguales = g[g["grupo"] == wide.SAME_LABEL]
    assert ((iguales["pastizal"] - iguales["cultivo"]).abs() <= banda).all()


def test_la_anomalia_es_la_unica_con_fecha_de_verdad():
    """Su figura no es una climatologia: la lluvia no depende de la ventana de
    cultivo de ningun indicador y se grafica de corrido."""
    lluvia = panel.national("serie_nacional_lluvia")
    if not len(lluvia):
        pytest.skip("no hay serie de lluvia")
    t = wide.anomaly_table(lluvia.tail(20))
    assert list(t.columns) == ["fecha", "dekad", "anomalía (%)"]
    assert t["fecha"].is_monotonic_increasing
    # Partida por signo para el archivo publicado: el color de esa figura es
    # el signo, y afuera el color es la columna.
    s = wide.anomaly_table(lluvia.tail(20), split_sign=True)
    assert list(s.columns) == ["fecha", "dekad", wide.ABOVE_LABEL,
                               wide.BELOW_LABEL]
    # Con el anio, que es la columna por la que filtra el grafico publicado:
    # la fecha ya lo trae, pero como filtro no sirve, son casi ochocientas.
    y = wide.anomaly_table(lluvia.tail(20), split_sign=True, year_column=True)
    assert list(y.columns)[2] == "año"
    assert (y["año"].str.len() == 4).all()
    par = s[[wide.ABOVE_LABEL, wide.BELOW_LABEL]]
    assert (par.notna().sum(axis=1) == 1).all(), "un signo por dekad"
    # Las dos columnas tienen que traer algo. Una columna entera vacia la
    # herramienta de afuera la tipa como texto, y entonces esa serie deja de
    # dibujarse: es el motivo por el que el ranking no se reparte por clase.
    # Con dieciocho meses de dekads no deberia pasar nunca; si pasa, el
    # grafico publicado se rompe y esto tiene que avisar antes.
    assert par.notna().any().all(), "un signo sin ningun dekad en la ventana"
    assert (s[wide.ABOVE_LABEL].dropna() >= 0).all()
    assert (s[wide.BELOW_LABEL].dropna() < 0).all()


def test_las_tablas_vacias_no_inventan_columnas():
    """Sin dato la figura no se dibuja y la descarga no debe ofrecer un CSV con
    encabezados y nada debajo, que se lee como "no hubo estres"."""
    vacio = pd.DataFrame(columns=["dekad_of_year", "Year", "mean", "dekad_id",
                                  "date", "adm2_name", "adm1_name"])
    assert wide.season_table(vacio, "GS1").empty
    assert wide.anomaly_table(vacio, value_col="mean").empty
    assert wide.ranking_table(vacio, "ASI %").empty
    assert wide.cover_table(vacio, vacio).empty
    assert wide.map_table(vacio, "ASI %").empty


def test_los_decimales_son_los_mismos_en_todas():
    """Dos decimales en todo: mas no son mas exactitud, y el ruido de punto
    flotante se publica tal cual si nadie redondea."""
    frame, season = _marco()
    t = wide.season_table(frame, season)
    for c in list(t.columns)[1:]:
        v = t[c].dropna()
        assert (v.round(wide.DECIMALS) == v).all(), c


def test_el_mapa_de_calor_es_la_misma_matriz_pero_larga():
    """Sale de season_table y se derrite, asi que no puede decir otra cosa que
    la figura. Larga y no ancha porque un mapa de calor no tiene series: tiene
    celdas, y pide las dos coordenadas y el valor en columnas aparte."""
    frame, season = _marco(dekads=120)
    ancha = wide.season_table(frame, season)
    larga = wide.heatmap_table(frame, season, "ASI %")
    assert list(larga.columns) == ["campaña", "dekad", "ASI %", "clase"]
    # La clase sale de config.CLASSES, no se teclea afuera: los cuatro
    # intervalos salen planos y con el color de la leyenda de FAO.
    assert set(larga["clase"]) <= set(cfg.CLASSES["ASI"][1])
    # Mismas coordenadas y mismas celdas que la version ancha, salvo la
    # campania del arranque si entro incompleta: esa no se publica.
    campanias = list(ancha.columns)[1:]
    assert set(larga["campaña"]) <= set(campanias)
    assert len(set(campanias) - set(larga["campaña"])) <= 1
    assert set(larga["dekad"]) <= set(ancha["dekad"])
    publicadas = ancha[[c for c in campanias if c in set(larga["campaña"])]]
    assert len(larga) == int(publicadas.notna().sum().sum())
    # Y ninguna celda sin dato: la ausencia no se publica como fila.
    assert larga["ASI %"].notna().all()


def test_el_mapa_de_calor_publicado_cubre_mas_que_la_ventana():
    """Es la unica excepcion de la carpeta. La matriz existe para situar la
    campania en curso entre las anteriores, y con dieciocho meses son dos
    filas, que no es una matriz."""
    carpeta = cfg.DATA / "flourish"
    if not (carpeta / "mapa_calor_asi_primera.csv").exists():
        pytest.skip("todavia no se genero")
    t = pd.read_csv(carpeta / "mapa_calor_asi_primera.csv")
    assert t["campaña"].nunique() > 2, "una matriz de dos filas no es una matriz"
    assert t["campaña"].nunique() >= 10

    # Y el orden de las filas es el del eje: la herramienta de afuera toma el
    # orden de aparicion, asi que la primera campania tiene que traer los
    # dekads de la temporada en su orden, desde el primero.
    pos = pd.read_csv(carpeta / "mapa_calor_asi_postrera.csv")
    primera = pos[pos["campaña"] == pos["campaña"].iloc[0]]
    assert primera["dekad"].iloc[0].startswith("sep"), primera["dekad"].iloc[0]
    assert primera["dekad"].iloc[-1].startswith("ene"), primera["dekad"].iloc[-1]


def test_la_superficie_por_clase_trae_las_cuatro_clases_en_columnas():
    """Ya vienen asi de `aggregate.severity_area`, que es la misma funcion que
    alimenta la figura. Afuera se apilan tal cual, y la campania al lado
    separa los paneles: entre el cierre de una y la apertura de la siguiente
    no hay dato, y una sola serie corrida afirmaria una caida que nadie
    midio."""
    if "asi_gs1" not in panel.stored_series():
        pytest.skip("no hay panel construido")
    dks = panel.dekads("asi_gs1")[-20:]
    d = panel.load("asi_gs1", dks[0], dks[-1])
    t = wide.severity_table(d, "ASI", "GS1")
    assert list(t.columns) == ["campaña", "dekad", *cfg.CLASSES["ASI"][1]]
    # Son km2, asi que ninguna es negativa y la suma es el area con dato.
    assert (t[cfg.CLASSES["ASI"][1]] >= 0).all().all()
    # La campania se rotula como en las series: la postrera cruza el anio y
    # por eso lleva los dos. Y la que arranca a medias no entra, igual que en
    # el mapa de calor.
    carpeta = cfg.DATA / "flourish"
    if (carpeta / "superficie_clase_asi_postrera.csv").exists():
        pos = pd.read_csv(carpeta / "superficie_clase_asi_postrera.csv")
        assert "–" in pos["campaña"].iloc[0], pos["campaña"].iloc[0]
        primera = pos[pos["campaña"] == pos["campaña"].iloc[0]]
        assert primera["dekad"].iloc[0].startswith("sep")


def test_las_figuras_por_unidad_llevan_fecha_para_poder_ordenarse():
    """La etiqueta del dekad se lee, la fecha ordena: sin ella "1er dek abr"
    se ordena antes que "1er dek ene"."""
    if "asi_gs1" not in panel.stored_series():
        pytest.skip("no hay panel construido")
    dks = panel.dekads("asi_gs1")[-6:]
    d = panel.load("asi_gs1", dks[0], dks[-1])
    t = wide.unit_series_table(d, "ASI %", with_class=True)
    assert list(t.columns) == ["municipio", "fecha", "dekad", "ASI %", "clase"]
    assert set(t["clase"]) <= set(cfg.CLASSES["ASI"][1])
    # Una fila por unidad y dekad, agrupadas por unidad.
    assert not t.duplicated(["municipio", "fecha"]).any()
    dep = wide.unit_series_table(to_department(d), "ASI %",
                                 name_col="adm1_name")
    assert list(dep.columns) == ["departamento", "fecha", "dekad", "ASI %"]


def test_la_rejilla_de_coberturas_mantiene_las_dos_separadas():
    """Misma regla que el contraste de un dekad: conviven en columnas, nunca
    se promedian ni se restan. Lo que cambia es que aqui hay una fila por
    dekad, que es lo que dibuja cada panel de la rejilla."""
    if "asi_gs1_pasto" not in panel.stored_series():
        pytest.skip("no hay panel de pastizal")
    dks = panel.dekads("asi_gs1_pasto")[-6:]
    t = wide.cover_grid_table(panel.load("asi_gs1", dks[0], dks[-1]),
                              panel.load("asi_gs1_pasto", dks[0], dks[-1]))
    assert list(t.columns) == ["municipio", "fecha", "dekad", "cultivo",
                               "pastizal"]
    assert not t.duplicated(["municipio", "fecha"]).any()


# --- Los archivos publicados ------------------------------------------------
ENCABEZADOS = {
    "serie_nacional_asi_primera.csv": "dekad",
    "serie_nacional_asi_postrera.csv": "dekad",
    "serie_nacional_vci.csv": "dekad",
    "mapa_calor_asi_primera.csv": "campaña",
    "mapa_calor_asi_postrera.csv": "campaña",
    "superficie_clase_asi_primera.csv": "campaña",
    "superficie_clase_asi_postrera.csv": "campaña",
    "mapa_calor_municipios.csv": "municipio",
    "rejilla_departamentos.csv": "departamento",
    "rejilla_coberturas.csv": "municipio",
    "lluvia_nacional.csv": "dekad",
    "lluvia_anomalia.csv": "fecha",
    "ranking_municipios.csv": "municipio",
    "ranking_departamentos.csv": "departamento",
    "mapa_municipios.csv": "código",
    "mapa_departamentos.csv": "código",
    "geometria_municipios.csv": "geometria",
    "geometria_departamentos.csv": "geometria",
    "coberturas.csv": "municipio",
}


def test_las_series_nacionales_se_publican_completas():
    """Sin ventana. Afuera el lector elige que campanias mirar con el control
    de series, y acotarlas en el archivo le quita esa posibilidad. Son
    veintitantas columnas de dieciocho filas: no hay nada que ahorrar."""
    carpeta = cfg.DATA / "flourish"
    if not (carpeta / "serie_nacional_asi_primera.csv").exists():
        pytest.skip("todavia no se generaron")
    if "asi_gs1" not in panel.stored_series():
        pytest.skip("no hay panel construido")
    t = pd.read_csv(carpeta / "serie_nacional_asi_primera.csv")
    campanias = list(t.columns)[1:]
    anios = {int(d[:4]) for d in panel.dekads("asi_gs1")}
    assert len(campanias) >= len(anios) - 1, (len(campanias), len(anios))
    assert campanias[0].startswith(str(cfg.START_YEAR))


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
        if archivo.startswith("geometria_"):
            # La geometria no es una vista: es el mapa base, 290 poligonos
            # simplificados a 400 m. Pesa lo que pesa y no se mira, asi que el
            # limite de arriba no le dice nada. Lo que si importa es que no se
            # dispare: por encima de medio mega habria que simplificar mas.
            assert (carpeta / archivo).stat().st_size <= 500_000
            continue
        ruta = carpeta / archivo
        filas = len(ruta.read_text(encoding="utf-8").splitlines()) - 1
        # El limite de una carga en linea son mil filas, pero estos van por
        # URL. La anomalia completa son casi ochocientas y crece un dekad cada
        # diez dias, asi que el tope aqui es mas alto a proposito; lo que
        # vigila es que ninguna tabla se vuelva una descarga de datos.
        assert filas <= 2000, f"{archivo}: {filas} filas"
        assert ruta.stat().st_size <= 100_000, f"{archivo}: {ruta.stat().st_size} bytes"


def test_el_script_y_la_app_arman_la_misma_tabla():
    """Es la promesa del modulo: lo que se copia de la app y lo que Flourish lee
    por URL son el mismo objeto. Si divergieran, la cifra publicada y la
    dibujada dejarian de ser la misma sin que nada lo detecte."""
    carpeta = cfg.DATA / "flourish"
    if not carpeta.exists() or "asi_gs1" not in panel.stored_series():
        pytest.skip("todavia no se generaron")
    propios = panel.dekads("asi_gs1")
    df = panel.load("asi_gs1", propios[0], propios[-1])
    frame = climatology_frame(to_country(df), "GS1")
    frame = frame[frame["dekad_of_year"].isin(season_columns("GS1"))]
    esperado = wide.season_table(frame, "GS1")
    publicado = pd.read_csv(carpeta / "serie_nacional_asi_primera.csv")
    assert list(publicado.columns) == list(esperado.columns)
    assert len(publicado) == len(esperado)


@pytest.mark.parametrize("nivel,unidad,geo", [
    ("mapa_municipios.csv", "municipio", "municipios"),
    ("mapa_departamentos.csv", "departamento", "departamentos"),
])
def test_el_mapa_publica_los_codigos_que_tiene_la_geometria(nivel, unidad, geo):
    """El mapa de Flourish empata dos hojas por el codigo: la de valores y la
    de geometria. Si los codigos dejan de coincidir el mapa no falla: sale
    gris, que es peor. Son una por poligono, ni mas ni menos."""
    carpeta = cfg.DATA / "flourish"
    if not (carpeta / nivel).exists():
        pytest.skip("todavia no se genero")
    clave = "adm2_code" if geo == "municipios" else "adm1_code"
    feats = json.loads((cfg.DATA / "geo" / f"{geo}.geojson")
                       .read_text(encoding="utf-8"))["features"]
    codigos = {f["properties"][clave] for f in feats}

    t = pd.read_csv(carpeta / nivel, dtype={"código": str})
    assert list(t.columns)[:2] == ["código", unidad]
    assert set(t["código"]) == codigos, "una fila por poligono, ni mas ni menos"

    # La clase la pone `aggregate.classify` desde config.CLASSES, no se
    # teclea en la herramienta de afuera: si alguien mueve un umbral, el mapa
    # publicado se mueve con el y la leyenda sigue diciendo la verdad.
    etiquetas = [*cfg.CLASSES["ASI"][1], wide.NO_DATA_LABEL]
    assert list(t.columns)[-1] == "clase"
    assert set(t["clase"]) <= set(etiquetas), set(t["clase"]) - set(etiquetas)

    # La unidad sin dato se publica, con la cifra vacia y la clase nombrada.
    # Es la regla de siempre vista desde el otro lado: sin dato no es cero, y
    # para poder decirlo la fila tiene que existir. Si se la quita, el mapa la
    # pinta del color de fondo, y un hueco blanco en un mapa de sequia se lee
    # como que ahi no pasa nada.
    sin = t[t["clase"] == wide.NO_DATA_LABEL]
    assert len(sin), "la geometria trae unidades que el panel no cubre"
    assert sin["ASI %"].isna().all()

    # Y la hoja de geometria publicada tiene que traer los mismos codigos, en
    # la forma que la lee el grafico: una columna con el poligono y otra con
    # el codigo.
    hoja = pd.read_csv(carpeta / f"geometria_{geo}.csv", dtype={"código": str})
    assert list(hoja.columns) == ["geometria", "código"]
    assert set(hoja["código"]) == codigos
    assert json.loads(hoja["geometria"].iloc[0])["type"] in (
        "Polygon", "MultiPolygon")


def test_el_ranking_departamental_no_repite_la_columna_de_grupo():
    """Un departamento no tiene departamento encima: la tabla es de dos
    columnas, no de tres con una repetida."""
    if "asi_gs1" not in panel.stored_series():
        pytest.skip("no hay panel construido")
    dk = panel.dekads("asi_gs1")[-1]
    dep = to_department(panel.load("asi_gs1", dk, dk))
    t = wide.ranking_table(dep, "ASI %", name_col="adm1_name", group_col=None)
    assert list(t.columns) == ["departamento", "ASI %"]
