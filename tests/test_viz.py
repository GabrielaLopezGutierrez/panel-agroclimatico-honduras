"""Las figuras que la app arma a partir del panel.

No se comprueba como se ven, sino que seleccionen los datos correctos: una
figura puede dibujarse perfecta y estar mostrando los municipios equivocados.
"""
import numpy as np
import pandas as pd
import pytest

from asis import config as cfg, viz
from asis.calendar import dekad_date

DEKADS = ["2019-06-D1", "2019-06-D2", "2019-06-D3", "2019-07-D1"]


def panel(valores: dict) -> pd.DataFrame:
    """valores: {municipio: [valor por dekad]}."""
    filas = []
    for i, (nombre, serie) in enumerate(valores.items()):
        for dk, v in zip(DEKADS, serie):
            filas.append(dict(adm2_code=str(100 + i), adm2_name=nombre,
                              adm1_code="10", adm1_name="Dep", dekad_id=dk,
                              mean=v, km2=100.0, n_px=100,
                              date=dekad_date(dk)))
    return pd.DataFrame(filas)


def etiquetas(fig) -> list[str]:
    """Municipios que quedaron en la matriz, de arriba hacia abajo."""
    return [str(y).split(" · ")[0] for y in fig.data[0].y][::-1]


def test_ranking_de_ventana_incluye_el_pico_de_la_mitad():
    """El modo de fallo que esto fija: ordenar por el último dekad deja fuera a
    quien tuvo el pico a mitad del rango, que es justo el que hay que ver."""
    d = panel({"PicoAlMedio": [0, 90, 0, 0],
               "SiempreBajo": [5, 5, 5, 5],
               "AltoAlFinal": [0, 0, 0, 40]})
    fig = viz.heatmap_panel(d, "mean", "t", family="ASI", top=2,
                            ref_dekad=None)
    top2 = etiquetas(fig)
    assert "PicoAlMedio" in top2
    assert "SiempreBajo" not in top2


def test_ranking_de_un_dekad_usa_ese_dekad():
    d = panel({"PicoAlMedio": [0, 90, 0, 0], "AltoAlFinal": [0, 0, 0, 40]})
    fig = viz.heatmap_panel(d, "mean", "t", family="ASI", top=1,
                            ref_dekad="2019-07-D1")
    assert etiquetas(fig) == ["AltoAlFinal"]


def test_en_el_vci_el_ranking_va_por_los_valores_bajos():
    """En el ASI interesa el máximo; en el VCI, el mínimo: un VCI bajo es
    vegetación en mal estado."""
    d = panel({"Peor": [0.9, 0.10, 0.9, 0.9], "Mejor": [0.8, 0.8, 0.8, 0.8]})
    fig = viz.heatmap_panel(d, "mean", "t", family="VCI", top=1,
                            ref_dekad=None)
    assert etiquetas(fig) == ["Peor"]


def test_el_ranking_respeta_el_tope():
    d = panel({f"M{i}": [i, i, i, i] for i in range(20)})
    fig = viz.heatmap_panel(d, "mean", "t", family="ASI", top=5,
                            ref_dekad=None)
    assert len(fig.data[0].y) == 5


def test_mapa_departamental_usa_codigos_departamentales():
    """Si la coropleta apuntara a adm2_code con geometría departamental, el mapa
    saldría vacío sin dar error."""
    gj = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "id": "10",
         "properties": {"adm1_code": "10", "adm1_name": "Dep"},
         "geometry": {"type": "Polygon",
                      "coordinates": [[[-87, 14], [-86, 14], [-86, 15],
                                       [-87, 15], [-87, 14]]]}}]}
    d = pd.DataFrame([dict(adm1_code="10", adm1_name="Dep",
                           dekad_id="2019-06-D1", mean=42.0, km2=100.0)])
    fig = viz.class_map(d, gj, "ASI", "t", animation=None,
                        code_col="adm1_code", name_col="adm1_name")
    assert fig is not None
    assert fig.data[0].locations[0] == "10"


def test_figuras_devuelven_none_si_no_hay_dato():
    """La app distingue "sin dato" de "error": las figuras devuelven None y la
    app muestra el aviso de que sin dato no es cero."""
    vacio = panel({"M": [np.nan] * 4})
    assert viz.heatmap_panel(vacio, "mean", "t", family="ASI") is None
    assert viz.severity_area_fig(vacio, "ASI", "t") is None
    assert viz.ranking_fig(vacio, "mean", "t", family="ASI") is None


def test_area_de_severidad_reparte_la_superficie_por_clase():
    d = panel({"Verde": [5, 5, 5, 5], "Rojo": [90, 90, 90, 90]})
    fig = viz.severity_area_fig(d, "ASI", "t")
    nombres = {t.name for t in fig.data}
    assert "<10" in nombres and ">=40" in nombres


# --- Ejes categoricos de dekads ----------------------------------------------
def test_las_etiquetas_del_eje_se_espacian():
    """Una etiqueta por dekad deja de leerse mucho antes de dejar de caber: con
    la ventana completa serian 779."""
    assert viz.thin_ticks(["a", "b", "c"]) == ["a", "b", "c"]
    muchas = [str(i) for i in range(779)]
    assert len(viz.thin_ticks(muchas)) <= 12
    assert len(viz.thin_ticks(muchas, 16)) <= 16
    # Siempre arranca en la primera, para que el eje quede anclado.
    assert viz.thin_ticks(muchas)[0] == "0"


def test_la_nota_de_fuente_se_ancla_en_pixeles_bajo_el_eje():
    """Con la nota en fraccion del area de dibujo, las etiquetas rotadas la
    invadian entre 8 y 17 pixeles, medidos en el navegador. En pixeles la
    separacion no depende del alto de la figura."""
    import plotly.graph_objects as go

    fig = viz.style_fig(go.Figure(), "t", source_shift=78)
    nota = [a for a in fig.layout.annotations if "Fuente" in (a.text or "")][0]
    assert nota.y == 0 and nota.yshift == -78
    assert fig.layout.margin.b >= 78


# --- Escala continua y color de las cifras de encabezado ---------------------
def _rgb(h):
    return [int(h[i:i + 2], 16) for i in (1, 3, 5)]


def _salto_maximo(family, lo, hi, n=400):
    """El mayor salto de color entre dos valores contiguos de la escala."""
    cols = [_rgb(viz.color_at(lo + (hi - lo) * i / n, family))
            for i in range(n + 1)]
    return max(max(abs(a - b) for a, b in zip(c1, c2))
               for c1, c2 in zip(cols, cols[1:]))


def test_la_escala_no_tiene_costuras_en_los_umbrales():
    """El defecto que esto fija: la escala anterior ponia dos paradas a cada
    lado de cada umbral y reiniciaba la luminosidad, asi que el borde de banda
    se veia como una costura. Medido, el salto maximo entre valores contiguos
    era de 32 sobre 255, justo en 24 (el umbral de 25); ahora es de 5."""
    assert _salto_maximo("ASI", 0, 100) <= 8
    assert _salto_maximo("VCI", 0, 1) <= 8


def test_la_escala_sale_de_los_colores_de_clase_de_fao():
    """Un solo lugar donde vive el color de un indicador: si cambian las clases
    de config, la escala continua las sigue."""
    for familia in ("ASI", "VCI"):
        colores_escala = {c for _pos, c in viz.scale_from_classes(familia)}
        assert set(cfg.CLASSES[familia][2]) <= colores_escala


def test_el_mapa_de_calor_y_el_kpi_pintan_igual_un_valor():
    """Es lo que hace que la celda de un dekad y su cifra de encabezado se vean
    del mismo color. Depende de que el mapa fije el rango al del indicador y no
    al de los datos en pantalla."""
    d = pd.DataFrame({"Year": [2025, 2025], "dekad_of_year": [13, 14],
                      "mean": [12.0, 80.0]})
    fig = viz.climatology_matrix(d, "t", value_col="mean", columns=[13, 14],
                                 family="ASI")
    assert (fig.data[0].zmin, fig.data[0].zmax) == viz.range_for("ASI")
    assert list(fig.data[0].colorscale) == [tuple(p) for p in viz.scale_for("ASI")]


def test_la_tinta_del_kpi_conserva_el_tono_y_alcanza_contraste():
    """La cifra va del color del valor, no de un gris: se oscurece solo lo
    necesario para leerse sobre blanco, y sigue siendo del mismo tono."""
    import streamlit_app as app

    tinta = app.readable_ink("#ffff00")            # amarillo puro
    r, g, b = _rgb(tinta)
    assert r > 100 and g > 100 and b < 80          # sigue siendo amarillo
    assert tinta != "#ffff00"                      # pero oscurecido
    assert app.readable_ink("#9a0000") == "#9a0000"  # ya contrastaba


def test_el_color_del_kpi_es_el_de_la_escala_continua():
    """Antes salia del color plano de la clase, asi que dos valores de la misma
    banda se veian identicos en la cifra y distintos en el mapa."""
    import streamlit_app as app

    for familia, valor in (("ASI", 32.0), ("VCI", 0.5)):
        _clase, color = app.class_color(valor, familia)
        assert color == viz.color_at(valor, familia)
    bajo = app.class_color(11.0, "ASI")[1]
    alto = app.class_color(24.0, "ASI")[1]
    assert bajo != alto                            # misma banda, distinto color


def _lluvia():
    from asis.calendar import dekad_date
    dekads = ["2026-01-D1", "2026-01-D2", "2026-01-D3"]
    return pd.DataFrame({"dekad_id": dekads,
                         "date": [dekad_date(d) for d in dekads],
                         "anom_pct": [40.0, -25.0, 0.0]})


def test_la_anomalia_colorea_por_signo():
    fig = viz.anomaly_bars_fig(_lluvia(), "t")
    colores = list(fig.data[0].marker.color)
    assert colores[0] == colores[2] != colores[1]


def test_la_anomalia_lleva_botones_de_acercamiento_y_no_una_miniatura():
    """El control de rango de Plotly dibuja una miniatura de las propias barras
    dentro de la banda: a esta densidad no es un asa, es una mancha. Un boton
    dice a las claras que periodo deja a la vista."""
    fig = viz.anomaly_bars_fig(_lluvia(), "t")
    assert not fig.layout.xaxis.rangeslider.visible
    assert fig.layout.xaxis.type == "date"      # el eje tiene que ser continuo
    etiquetas = [b.label for b in fig.layout.xaxis.rangeselector.buttons]
    assert etiquetas[-1] == "Todo"


def test_solo_se_ofrecen_los_tramos_que_caben_en_el_periodo():
    """Un boton de cinco anios sobre una ventana de dieciocho meses no haria
    nada."""
    from asis.calendar import dekad_date

    largos = ["%d-%02d-D1" % (a, m) for a in range(2005, 2027)
              for m in range(1, 13)]
    corta = _lluvia()
    larga = pd.DataFrame({"dekad_id": largos,
                          "date": [dekad_date(d) for d in largos],
                          "anom_pct": [0.0] * len(largos)})
    def etiquetas(d):
        fig = viz.anomaly_bars_fig(d, "t")
        return [b.label for b in fig.layout.xaxis.rangeselector.buttons]
    assert etiquetas(corta) == ["Todo"]         # un mes: ningun tramo cabe
    assert "5 años" in etiquetas(larga)


def test_la_temporada_que_cruza_el_anio_se_rotula_con_los_dos():
    """La postrera va de septiembre a enero y se guarda bajo el anio en que
    empieza, porque es una sola campania. Rotularla solo con ese anio la hacia
    leer como atrasada: la fila decia 2025 aunque llegara hasta enero de 2026."""
    from asis.aggregate import season_columns

    postrera = season_columns("GS2")
    primera = season_columns("GS1")
    assert viz.season_wraps(postrera)
    assert not viz.season_wraps(primera)
    assert viz.season_labels([2025], postrera) == ["2025-26"]
    assert viz.season_labels([2025, 2026], primera) == ["2025", "2026"]
    # El anio completo del VCI tampoco cruza.
    assert not viz.season_wraps(season_columns(None))
