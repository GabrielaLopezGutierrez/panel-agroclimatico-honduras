"""La compuerta de la actualizacion diaria.

El defecto que arregla: con tres corridas fijas al mes, una que caia antes de
que FAO publicara dejaba el panel parado hasta la siguiente, diez dias despues.
Ahora se mira todos los dias, y `behind_series` decide si vale la pena consultar
a FAO. Lo que esta prueba protege es esa decision, porque si se equivoca en un
sentido el panel se queda viejo sin avisar, y si se equivoca en el otro se
consulta a FAO todos los dias para nada.

No toca el panel versionado: redirige el directorio de series a uno temporal.
"""
import pandas as pd
import pytest

from asis import build, config as cfg


def _panel(tmp_path, monkeypatch, ultimos):
    """Un panel de mentira: una carpeta por serie con un parquet por anio."""
    monkeypatch.setattr(cfg, "PANEL_DIR", tmp_path)
    for sid, ultimo in ultimos.items():
        if ultimo is None:
            continue
        carpeta = tmp_path / sid
        carpeta.mkdir(parents=True, exist_ok=True)
        anio = int(ultimo[:4])
        pd.DataFrame({"dekad_id": [ultimo], "adm2_code": ["HND.1.1_1"]}).to_parquet(
            carpeta / f"{anio}.parquet", index=False)


TODAS = {sid: "2026-08-D3" for sid in cfg.SERIES}


def test_al_dia_no_hay_nada_que_consultar(tmp_path, monkeypatch):
    """El 5 de septiembre el ultimo dekad cerrado es 2026-08-D3, que es donde
    esta el panel. No hay nada que FAO pueda haber publicado."""
    _panel(tmp_path, monkeypatch, TODAS)
    assert build.behind_series(today="2026-09-05") == {}


def test_apenas_cierra_un_dekad_hay_que_volver_a_consultar(tmp_path, monkeypatch):
    """El 11 de septiembre cerro 2026-09-D1. Aunque FAO no lo haya publicado
    todavia, la compuerta abre: es justo el caso que antes esperaba diez dias."""
    _panel(tmp_path, monkeypatch, TODAS)
    atrasadas = build.behind_series(today="2026-09-11")
    assert set(atrasadas) == set(cfg.SERIES)
    assert set(atrasadas.values()) == {"2026-08-D3"}


def test_basta_una_serie_atrasada_para_consultar(tmp_path, monkeypatch):
    """Las series no siempre llegan juntas. Si alguna quedo atras se consulta,
    porque lo contrario la dejaria vieja mientras las demas avanzan."""
    ultimos = dict(TODAS)
    ultimos["vci"] = "2026-09-D1"
    _panel(tmp_path, monkeypatch, ultimos)
    atrasadas = build.behind_series(today="2026-09-11")
    assert "vci" not in atrasadas
    assert set(atrasadas) == set(cfg.SERIES) - {"vci"}


def test_una_serie_sin_nada_en_disco_cuenta_como_atrasada(tmp_path, monkeypatch):
    _panel(tmp_path, monkeypatch, {sid: None for sid in cfg.SERIES})
    atrasadas = build.behind_series(today="2026-09-11")
    assert atrasadas == {sid: None for sid in cfg.SERIES}


def test_la_compuerta_sale_sin_consultar_cuando_el_panel_esta_al_dia(
        tmp_path, monkeypatch, capsys):
    """De punta a punta por la linea de comandos: con --solo-si-falta y el panel
    al dia, main() devuelve 0 sin llamar a FAO. Si llamara, client.last_dekad
    levantaria la excepcion."""
    _panel(tmp_path, monkeypatch,
           {sid: build.last_closed_dekad() for sid in cfg.SERIES})
    monkeypatch.setattr(
        build.client, "last_dekad",
        lambda *a, **k: pytest.fail("no deberia consultar a FAO"))
    assert build.main(["--solo-si-falta"]) == 0
    assert "no hay" in capsys.readouterr().out
