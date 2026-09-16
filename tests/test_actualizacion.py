"""La compuerta de la actualizacion diaria.

El defecto que arregla: con tres corridas fijas al mes, una que caia antes de
que FAO publicara dejaba el panel parado hasta la siguiente, diez dias despues.
Ahora se mira todos los dias, y `behind_series` decide si vale la pena consultar
a FAO. Lo que esta prueba protege es esa decision, porque si se equivoca en un
sentido el panel se queda viejo sin avisar, y si se equivoca en el otro se
consulta a FAO todos los dias para nada.

No toca el manifiesto real: redirige la ruta a un archivo temporal, porque
data/manifest.json esta versionado.
"""
import json

import pytest

from asis import build, config as cfg, panel


def _manifiesto(tmp_path, monkeypatch, ultimos):
    """Un manifiesto de mentira con el ultimo dekad de cada serie."""
    ruta = tmp_path / "manifest.json"
    ruta.write_text(json.dumps({
        "series": {sid: {"ultimo": ultimo}
                   for sid, ultimo in ultimos.items() if ultimo}
    }), encoding="utf-8")
    monkeypatch.setattr(panel, "MANIFEST", ruta)
    return ruta


TODAS = {sid: "2026-08-D3" for sid in cfg.SERIES}


def test_al_dia_no_hay_nada_que_consultar(tmp_path, monkeypatch):
    """El 5 de septiembre el ultimo dekad cerrado es 2026-08-D3, que es donde
    esta el panel. No hay nada que FAO pueda haber publicado."""
    _manifiesto(tmp_path, monkeypatch, TODAS)
    assert build.behind_series(today="2026-09-05") == {}


def test_apenas_cierra_un_dekad_hay_que_volver_a_consultar(tmp_path, monkeypatch):
    """El 11 de septiembre cerro 2026-09-D1. Aunque FAO no lo haya publicado
    todavia, la compuerta abre: es justo el caso que antes esperaba diez dias."""
    _manifiesto(tmp_path, monkeypatch, TODAS)
    atrasadas = build.behind_series(today="2026-09-11")
    assert set(atrasadas) == set(cfg.SERIES)
    assert set(atrasadas.values()) == {"2026-08-D3"}


def test_basta_una_serie_atrasada_para_consultar(tmp_path, monkeypatch):
    """Las series no siempre llegan juntas. Si alguna quedo atras se consulta,
    porque lo contrario la dejaria vieja mientras las demas avanzan."""
    ultimos = dict(TODAS)
    ultimos["vci"] = "2026-09-D1"
    _manifiesto(tmp_path, monkeypatch, ultimos)
    atrasadas = build.behind_series(today="2026-09-11")
    assert "vci" not in atrasadas
    assert set(atrasadas) == set(cfg.SERIES) - {"vci"}


@pytest.mark.parametrize("contenido", [
    {},                                  # manifiesto sin series
    {sid: None for sid in cfg.SERIES},   # series sin ultimo dekad
])
def test_lo_que_falta_cuenta_como_atrasado(tmp_path, monkeypatch, contenido):
    """El error se prefiere hacia consultar de mas. Consultar cuando no hacia
    falta cuesta dos minutos; no consultar cuando si hacia falta deja el panel
    viejo sin que nadie se entere."""
    _manifiesto(tmp_path, monkeypatch, contenido)
    assert build.behind_series(today="2026-09-11") == {
        sid: None for sid in cfg.SERIES}


def test_sin_manifiesto_tambien_se_consulta(tmp_path, monkeypatch):
    """Un repositorio recien clonado sin panel construido no debe quedarse
    callado: tiene todo por bajar."""
    monkeypatch.setattr(panel, "MANIFEST", tmp_path / "no-existe.json")
    assert set(build.behind_series(today="2026-09-11")) == set(cfg.SERIES)


def test_la_compuerta_sale_sin_consultar_cuando_el_panel_esta_al_dia(
        tmp_path, monkeypatch, capsys):
    """De punta a punta por la linea de comandos: con --solo-si-falta y el panel
    al dia, main() devuelve 0 sin llamar a FAO. Si llamara, client.last_dekad
    haria fallar la prueba."""
    _manifiesto(tmp_path, monkeypatch,
                {sid: build.last_closed_dekad() for sid in cfg.SERIES})
    monkeypatch.setattr(
        build.client, "last_dekad",
        lambda *a, **k: pytest.fail("no deberia consultar a FAO"))
    assert build.main(["--solo-si-falta"]) == 0
    assert "no hay" in capsys.readouterr().out


def test_la_compuerta_no_abre_los_parquets(tmp_path, monkeypatch):
    """Leia ciento diez parquets para contestar una pregunta de una linea, y eso
    arrancaba el motor de Arrow: al salir medio segundo despues, su pool de
    hilos abortaba el proceso con codigo 134 y la corrida diaria quedaba en rojo
    todos los dias aunque hubiera hecho lo correcto. El dato sale del
    manifiesto, que lo escribe esta misma construccion."""
    _manifiesto(tmp_path, monkeypatch, TODAS)
    monkeypatch.setattr(
        build, "stored_dekads",
        lambda sid: pytest.fail("la compuerta no deberia leer el panel"))
    assert build.behind_series(today="2026-09-05") == {}
