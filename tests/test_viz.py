"""Las figuras que la app arma a partir del panel.

No se comprueba como se ven, sino que seleccionen los datos correctos: una
figura puede dibujarse perfecta y estar mostrando los municipios equivocados.
"""
import numpy as np
import pandas as pd
import pytest

from asis import viz
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
