"""El manifiesto marca el dekad mas nuevo de cada serie como preliminar, y la
app lo lee de ahi. No toca el manifiesto real: redirige la ruta a un archivo
temporal, porque data/manifest.json esta versionado.
"""
from asis import build, config as cfg, panel


def _series_info(dekads, ultimo_publicado_fao):
    return {"nuevos": 0, "republicados": [], "preliminares": [],
           "dekads": dekads, "ultimo_publicado_fao": ultimo_publicado_fao}


def test_se_marca_preliminar_cuando_el_ultimo_dekad_es_el_del_catalogo(
        tmp_path, monkeypatch):
    ruta = tmp_path / "manifest.json"
    monkeypatch.setattr(build, "MANIFEST", ruta)
    monkeypatch.setattr(panel, "MANIFEST", ruta)

    info = {"vci": _series_info(["2026-08-D1", "2026-08-D2"], "2026-08-D2")}
    build.write_manifest(info, {}, {}, n_muni=290)

    assert panel.manifest()["series"]["vci"]["preliminar"] is True
    assert panel.is_preliminary("vci", "2026-08-D2")
    assert not panel.is_preliminary("vci", "2026-08-D1")


def test_no_se_marca_preliminar_si_el_ultimo_dekad_ya_no_es_el_mas_nuevo(
        tmp_path, monkeypatch):
    """Caso del dia a dia: se construye hasta 2026-08-D2 pero FAO ya publico
    2026-08-D3. Ese dekad no deberia decir "preliminar" cuando en realidad ya
    quedo atras."""
    ruta = tmp_path / "manifest.json"
    monkeypatch.setattr(build, "MANIFEST", ruta)
    monkeypatch.setattr(panel, "MANIFEST", ruta)

    info = {"vci": _series_info(["2026-08-D1", "2026-08-D2"], "2026-08-D3")}
    build.write_manifest(info, {}, {}, n_muni=290)

    assert panel.manifest()["series"]["vci"]["preliminar"] is False


def test_sin_consultar_el_catalogo_se_conserva_la_marca_anterior(
        tmp_path, monkeypatch):
    """Rama 'al dia' o --solo-oficiales: no se llamo al catalogo esta corrida,
    asi que no se debe pisar la marca que ya habia con un valor adivinado."""
    ruta = tmp_path / "manifest.json"
    monkeypatch.setattr(build, "MANIFEST", ruta)
    monkeypatch.setattr(panel, "MANIFEST", ruta)

    primero = {"vci": _series_info(["2026-08-D2"], "2026-08-D2")}
    build.write_manifest(primero, {}, {}, n_muni=290)
    assert panel.manifest()["series"]["vci"]["preliminar"] is True

    segundo = {"vci": _series_info(["2026-08-D2"], None)}   # no se consulto
    build.write_manifest(segundo, {}, {}, n_muni=290)
    assert panel.manifest()["series"]["vci"]["preliminar"] is True


def test_indicador_combinado_es_preliminar_si_alguna_temporada_lo_es(
        tmp_path, monkeypatch):
    ruta = tmp_path / "manifest.json"
    monkeypatch.setattr(build, "MANIFEST", ruta)
    monkeypatch.setattr(panel, "MANIFEST", ruta)

    info = {
        "asi_gs1": _series_info(["2026-08-D2"], "2026-08-D2"),   # preliminar
        "asi_gs2": _series_info(["2026-07-D3"], "2026-08-D2"),   # asentado
    }
    build.write_manifest(info, {}, {}, n_muni=290)

    assert panel.is_preliminary(cfg.ASI_COMBINED, "2026-08-D2")
    assert not panel.is_preliminary(cfg.ASI_COMBINED, "2026-07-D3")
