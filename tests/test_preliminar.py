"""El manifiesto lista los dekads preliminares de cada serie, y la app los lee
de ahi. No toca el manifiesto real: redirige la ruta a un archivo temporal,
porque data/manifest.json esta versionado.
"""
from asis import build, config as cfg, panel


def _series_info(dekads, preliminares_fao):
    return {"nuevos": 0, "republicados": [], "preliminares": [],
            "dekads": dekads, "preliminares_fao": preliminares_fao}


def _rutas(tmp_path, monkeypatch):
    ruta = tmp_path / "manifest.json"
    monkeypatch.setattr(build, "MANIFEST", ruta)
    monkeypatch.setattr(panel, "MANIFEST", ruta)
    return ruta


def test_se_marcan_los_tres_dekads_mas_nuevos(tmp_path, monkeypatch):
    _rutas(tmp_path, monkeypatch)
    dekads = ["2026-07-D2", "2026-07-D3", "2026-08-D1", "2026-08-D2",
              "2026-08-D3"]
    info = {"vci": _series_info(dekads, ["2026-08-D1", "2026-08-D2",
                                         "2026-08-D3"])}
    build.write_manifest(info, {}, {}, n_muni=290)

    assert panel.is_preliminary("vci", "2026-08-D3")
    assert panel.is_preliminary("vci", "2026-08-D1")
    assert not panel.is_preliminary("vci", "2026-07-D3")


def test_no_se_marca_un_dekad_que_el_panel_no_tiene(tmp_path, monkeypatch):
    """FAO ya publico 2026-08-D3 pero el panel se construyo hasta D2: prometer
    preliminar un dekad que no esta en el panel no le sirve a nadie."""
    ruta = _rutas(tmp_path, monkeypatch)
    info = {"vci": _series_info(["2026-08-D1", "2026-08-D2"],
                                ["2026-08-D1", "2026-08-D2", "2026-08-D3"])}
    build.write_manifest(info, {}, {}, n_muni=290)

    import json
    guardado = json.loads(ruta.read_text(encoding="utf-8"))
    assert guardado["series"]["vci"]["preliminares"] == ["2026-08-D1",
                                                        "2026-08-D2"]


def test_sin_consultar_el_catalogo_se_conserva_la_lista_anterior(
        tmp_path, monkeypatch):
    """Rama 'al dia' o --solo-oficiales: no se llamo al catalogo esta corrida,
    asi que no se debe pisar lo que ya habia con un valor adivinado."""
    _rutas(tmp_path, monkeypatch)
    primero = {"vci": _series_info(["2026-08-D2", "2026-08-D3"],
                                   ["2026-08-D2", "2026-08-D3"])}
    build.write_manifest(primero, {}, {}, n_muni=290)
    assert panel.is_preliminary("vci", "2026-08-D3")

    segundo = {"vci": _series_info(["2026-08-D2", "2026-08-D3"], None)}
    build.write_manifest(segundo, {}, {}, n_muni=290)
    assert panel.is_preliminary("vci", "2026-08-D3")


def test_indicador_combinado_es_preliminar_si_alguna_temporada_lo_es(
        tmp_path, monkeypatch):
    _rutas(tmp_path, monkeypatch)
    info = {
        "asi_gs1": _series_info(["2026-08-D2"], ["2026-08-D2"]),
        "asi_gs2": _series_info(["2026-07-D3"], ["2026-08-D2"]),
    }
    build.write_manifest(info, {}, {}, n_muni=290)

    assert panel.is_preliminary(cfg.ASI_COMBINED, "2026-08-D2")
    assert not panel.is_preliminary(cfg.ASI_COMBINED, "2026-07-D3")
