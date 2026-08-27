"""Deteccion de alertas ASI: umbrales, deduplicacion y contenido del correo.

No prueba el envio -no existe todavia a proposito- sino la parte que si esta
implementada: que clasifique bien, que no repita la misma alerta dos veces, y
que el mensaje traiga lo que pide el requisito (nivel, temporada, lugar, valor,
periodo, motivo).
"""
import json

import pytest

from asis import alerts, config as cfg


def test_umbrales_son_los_mismos_que_la_clasificacion_visual():
    """Los umbrales de alerta no se redefinen aqui: si cambiaran en config, las
    alertas tienen que moverse con ellos sin tocar este modulo."""
    assert alerts.ORANGE_MIN == cfg.ASI_ALERT_THRESHOLDS[1] == 25
    assert alerts.RED_MIN == cfg.ASI_ALERT_THRESHOLDS[2] == 40


@pytest.mark.parametrize("valor,esperado", [
    (9.9, None), (10.0, None), (24.9, None),
    (25.0, "naranja"), (39.9, "naranja"),
    (40.0, "rojo"), (100.0, "rojo"),
])
def test_nivel_de_alerta_por_valor(valor, esperado):
    assert alerts._alert_level(valor) == esperado


def test_alerta_no_dispara_bajo_el_umbral_naranja():
    assert alerts._alert_level(24.999) is None


def test_clave_de_alerta_identifica_lugar_temporada_periodo_y_nivel():
    a = alerts.Alert(location="Choluteca (Choluteca)", level="municipio",
                     asi_season="asi_gs1", asi_value=42.0,
                     period="2019-09-D2", alert_level="rojo",
                     reason="ASI 42.0% >= 40% - Estrés extremo")
    b = alerts.Alert(location="Choluteca (Choluteca)", level="municipio",
                     asi_season="asi_gs1", asi_value=41.5,   # valor distinto
                     period="2019-09-D2", alert_level="rojo",
                     reason="otro motivo")
    assert a.key() == b.key()          # mismo lugar/temporada/periodo/nivel
    c = a.__class__(**{**a.__dict__, "period": "2019-09-D3"})
    assert a.key() != c.key()          # otro periodo, otra alerta


def test_deduplicacion_no_repite_una_alerta_ya_marcada(tmp_path, monkeypatch):
    log = tmp_path / "alertas_estado.json"
    monkeypatch.setenv(alerts.LOG_PATH_ENV, str(log))
    a = alerts.Alert(location="X", level="municipio", asi_season="asi_gs1",
                     asi_value=50.0, period="2019-09-D2", alert_level="rojo",
                     reason="r")
    assert alerts._load_sent() == set()
    alerts.mark_sent([a])
    assert a.key() in alerts._load_sent()
    assert log.exists()
    data = json.loads(log.read_text(encoding="utf-8"))
    assert list(a.key()) in data["enviadas"]


def test_recipients_no_trae_nada_por_omision(monkeypatch):
    """Sin variable de entorno ni secretos, la lista de destinatarios esta
    vacia: nunca hay un correo escrito en el codigo."""
    monkeypatch.delenv(alerts.RECIPIENTS_ENV, raising=False)
    assert alerts.recipients() == []


def test_recipients_lee_la_variable_de_entorno(monkeypatch):
    monkeypatch.setenv(alerts.RECIPIENTS_ENV, "a@x.org, b@x.org")
    assert alerts.recipients() == ["a@x.org", "b@x.org"]


def test_format_email_trae_los_campos_requeridos():
    a = alerts.Alert(location="Choluteca (Choluteca)", level="municipio",
                     asi_season="asi_gs1", asi_value=42.3,
                     period="2019-09-D2", alert_level="rojo",
                     reason="ASI 42.3% ≥ 40% — Estrés extremo")
    subject, body = alerts.format_email(a)
    assert "ROJO" in subject and "Choluteca" in subject
    for campo in ("rojo", "asi_gs1", "Choluteca", "42.3", "2019-09-D2",
                 "Estrés extremo"):
        assert campo in body
    assert "no necesariamente una" in body   # el descargo de item 6


def test_ningun_correo_se_envia_desde_este_modulo():
    """No hay smtplib, requests, ni cliente de proveedor alguno importado:
    el modulo detecta y arma el contenido, no entrega nada."""
    import inspect
    fuente = inspect.getsource(alerts)
    for prohibido in ("smtplib", "sendgrid", "boto3", "requests.post"):
        assert prohibido not in fuente
