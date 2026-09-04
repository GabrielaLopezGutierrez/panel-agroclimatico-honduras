"""El contrato entre el constructor y la app: qué hay en disco y cómo se lee."""
import json

import pytest

from asis import config as cfg, panel
from asis.calendar import dekad_index


def test_manifiesto_existe_y_declara_las_series():
    mf = panel.manifest()
    assert mf["start_year"] == cfg.START_YEAR
    assert mf["pais"] == cfg.GAUL_COUNTRY
    assert mf["series"], "el manifiesto no declara ninguna serie"


def test_geometria_versionada_y_utilizable_sin_geopandas():
    """La app dibuja mapas sin geopandas: la geometría ya viene simplificada y
    con adm2_code en las propiedades, que es la llave de la coropleta."""
    gj = panel.geojson()
    assert gj["type"] == "FeatureCollection"
    assert len(gj["features"]) > 250
    props = gj["features"][0]["properties"]
    for key in ("adm2_code", "adm2_name", "adm1_name"):
        assert key in props


def test_codigos_de_la_geometria_coinciden_con_el_panel():
    if not panel.stored_series():
        pytest.skip("no hay panel construido")
    gj = panel.geojson()
    geo_codes = {f["properties"]["adm2_code"] for f in gj["features"]}
    sid = panel.stored_series()[0]
    panel_codes = set(panel.load(sid, *_last_window(sid))["adm2_code"])
    faltan = panel_codes - geo_codes
    assert not faltan, f"municipios del panel sin geometría: {sorted(faltan)[:5]}"


def _last_window(sid):
    d = panel.dekads(sid)
    return d[-1], d[-1]


def test_municipios_de_referencia():
    ref = panel.municipios()
    assert len(ref) > 250
    assert ref["adm2_code"].is_unique
    assert ref["area_km2"].sum() > 100_000        # Honduras ~112 mil km2


def test_corte_por_ventana_respeta_los_limites():
    if "vci" not in panel.stored_series():
        pytest.skip("no hay panel de vci")
    d = panel.dekads("vci")
    if len(d) < 5:
        pytest.skip("panel demasiado corto")
    start, end = d[2], d[4]
    out = panel.load("vci", start, end)
    assert set(out["dekad_id"]) <= set(d[2:5])
    assert out["dekad_id"].min() >= start
    assert out["dekad_id"].max() <= end


def test_no_se_ofrece_ninguna_serie_derivada():
    """El panel solo ofrece series reales. Hubo un indicador que combinaba las
    dos temporadas del ASI tomando la mayor por municipio; se retiró porque
    cada temporada se mide sobre su propia máscara de cultivo, y al agregar a
    país ponderando por píxeles válidos el combinado quedaba por debajo de la
    primera sola."""
    assert not (cfg.PANEL_DIR / cfg.ASI_COMBINED).exists()
    assert set(panel.available_series()) == set(panel.stored_series())


def test_particion_por_anio_coincide_con_el_contenido():
    for sid in panel.stored_series():
        for year in panel.years_on_disk(sid):
            df = panel.load(sid, f"{year}-01-D1", f"{year}-12-D3")
            years = {int(c[:4]) for c in df["dekad_id"]}
            assert years <= {year}, f"{sid}/{year}.parquet contiene {years}"


def test_dekads_del_manifiesto_coinciden_con_el_disco():
    mf = panel.manifest()
    for sid, info in mf["series"].items():
        if sid not in panel.stored_series():
            continue
        on_disk = set(panel.load(sid)["dekad_id"])
        declared = set(info["dekads"])
        assert declared == on_disk, (
            f"{sid}: el manifiesto declara {len(declared)} dekads y en disco "
            f"hay {len(on_disk)}")


def test_geometria_departamental_versionada():
    """El nivel departamental se dibuja con sus propios limites, no disolviendo
    municipios en la app."""
    gj = panel.geojson("departamento")
    assert gj["type"] == "FeatureCollection"
    assert len(gj["features"]) == 18            # Honduras tiene 18
    props = gj["features"][0]["properties"]
    assert "adm1_code" in props and "adm1_name" in props
    # La geometria departamental NO debe traer codigos municipales: si los
    # trajera, el mapa dibujaria la division interna que el nivel no tiene.
    assert "adm2_code" not in props


def test_codigos_departamentales_empatan_con_el_panel():
    if not panel.stored_series():
        pytest.skip("no hay panel construido")
    from asis.aggregate import to_department
    gj = panel.geojson("departamento")
    geo = {f["properties"]["adm1_code"] for f in gj["features"]}
    sid = panel.stored_series()[0]
    last = panel.dekads(sid)[-1]
    dept = to_department(panel.load(sid, last, last))
    faltan = set(dept["adm1_code"]) - geo
    assert not faltan, f"departamentos del panel sin geometria: {faltan}"


def test_cada_nivel_declara_como_se_dibuja():
    for level, spec in panel.LEVEL_GEO.items():
        assert spec["geojson"].exists(), f"falta la geometria de {level}"
        for key in ("code", "name", "label"):
            assert spec[key]


def test_tabla_de_referencia_departamental():
    ref = panel.departamentos()
    assert len(ref) == 18
    assert ref["adm1_code"].is_unique
    assert int(ref["n_muni"].sum()) == len(panel.municipios())
