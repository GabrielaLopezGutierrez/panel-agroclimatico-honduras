"""Detección de alertas ASI naranja y roja, y la estructura mínima para
enviarlas por correo más adelante.

No envía correos: solo detecta, evita duplicados y arma el contenido del
mensaje. Los umbrales son los mismos que gobiernan el mapa y la leyenda de la
app (`config.ASI_ALERT_THRESHOLDS`), no unos nuevos.

Entrega real: fuera de alcance a propósito. La opción más simple, sin agregar
un proveedor nuevo, es SMTP contra el relevo de correo de la organización
(host/usuario/contraseña por variable de entorno, nunca en el código); la
alternativa es una API transaccional (SendGrid, Mailgun, SES), que agrega una
dependencia y una cuenta que hoy no existen. `format_email()` ya deja listo el
asunto y el cuerpo para cualquiera de las dos.

Uso manual: `python -m asis.alerts [serie]` (por omisión `asi_gs1`).
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from asis import config as cfg, panel

# 25 y 40, los mismos umbrales de config.ASI_ALERT_THRESHOLDS. No se redefinen
# aquí para que un cambio en la clasificación de alerta no deje a este módulo
# usando un número viejo.
_, ORANGE_MIN, RED_MIN = cfg.ASI_ALERT_THRESHOLDS
_LEVEL_TO_CLASS = {"naranja": "25-40", "rojo": ">=40"}

# Destinatarios: solo por variable de entorno o por los secretos de Streamlit.
# Nunca un correo escrito en el código, y nunca en un archivo que se commitee
# (.streamlit/secrets.toml está en .gitignore).
RECIPIENTS_ENV = "ASIS_ALERT_RECIPIENTS"

# Registro de qué ya se avisó, para no duplicar. Vive en la caché de rásteres,
# que ya está fuera del repositorio (asis_cache/ no se versiona): es estado de
# ejecución, no dato del panel.
LOG_PATH_ENV = "ASIS_ALERT_LOG"
DEFAULT_LOG_PATH = cfg.CACHE / "alertas_estado.json"


def recipients() -> list[str]:
    """Lista de destinatarios configurada por quien despliega la app, nunca
    escrita en el código."""
    raw = os.environ.get(RECIPIENTS_ENV, "")
    if not raw:
        try:
            import streamlit as st
            raw = ",".join(st.secrets.get("alerts", {}).get("recipients", []))
        except Exception:
            raw = ""
    return [r.strip() for r in raw.split(",") if r.strip()]


@dataclass(frozen=True)
class Alert:
    location: str
    level: str          # "municipio" (única granularidad del panel)
    asi_season: str     # id de la serie: asi_gs1, asi_gs2 o el combinado
    asi_value: float
    period: str          # dekad_id
    alert_level: str     # "naranja" o "rojo"
    reason: str

    def key(self) -> tuple:
        """Identidad para evitar duplicados: mismo lugar, misma temporada,
        mismo periodo, mismo nivel de alerta."""
        return (self.location, self.asi_season, self.period, self.alert_level)


def _alert_level(value: float) -> str | None:
    if value >= RED_MIN:
        return "rojo"
    if value >= ORANGE_MIN:
        return "naranja"
    return None


def detect_alerts(series_id: str, dekad_id: str | None = None) -> list[Alert]:
    """Alertas naranja y roja de un dekad, a nivel municipal.

    Sin `dekad_id` usa el último dekad disponible de la serie.
    """
    dekad_id = dekad_id or panel.last_dekad(series_id)
    if not dekad_id:
        return []
    df = panel.load(series_id, dekad_id, dekad_id).dropna(subset=["mean"])
    out = []
    for _, row in df.iterrows():
        nivel = _alert_level(float(row["mean"]))
        if nivel is None:
            continue
        descripcion = cfg.ASI_ALERT_DESCRIPTIONS[_LEVEL_TO_CLASS[nivel]]
        umbral = RED_MIN if nivel == "rojo" else ORANGE_MIN
        out.append(Alert(
            location=f"{row['adm2_name']} ({row['adm1_name']})",
            level="municipio", asi_season=series_id,
            asi_value=round(float(row["mean"]), 1), period=dekad_id,
            alert_level=nivel,
            reason=f"ASI {row['mean']:.1f}% ≥ {umbral}% — {descripcion}"))
    return out


# --- Deduplicación: no repetir la misma alerta -------------------------------
def _log_path() -> Path:
    return Path(os.environ.get(LOG_PATH_ENV, DEFAULT_LOG_PATH))


def _load_sent() -> set[tuple]:
    p = _log_path()
    if not p.exists():
        return set()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return set()
    return {tuple(k) for k in data.get("enviadas", [])}


def _save_sent(sent: set[tuple]):
    p = _log_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"enviadas": [list(k) for k in sorted(sent)]},
                            ensure_ascii=False, indent=2), encoding="utf-8")


def pending_alerts(series_id: str, dekad_id: str | None = None) -> list[Alert]:
    """Alertas de este dekad que todavía no se marcaron como enviadas."""
    sent = _load_sent()
    return [a for a in detect_alerts(series_id, dekad_id)
            if a.key() not in sent]


def mark_sent(alerts: list[Alert]) -> None:
    """Registra alertas como enviadas, para no repetirlas.

    Se llama solo después de una entrega real; este módulo no entrega nada por
    su cuenta, así que nada se marca automáticamente.
    """
    sent = _load_sent()
    sent |= {a.key() for a in alerts}
    _save_sent(sent)


# --- Contenido del correo, sin enviarlo --------------------------------------
def format_email(alert: Alert) -> tuple[str, str]:
    """(asunto, cuerpo), listos para pasarle a un proveedor de envío."""
    asunto = f"Alerta {alert.alert_level.upper()} de ASI · {alert.location}"
    cuerpo = (
        f"Nivel de alerta: {alert.alert_level}\n"
        f"Temporada/serie ASI: {alert.asi_season}\n"
        f"Ubicación: {alert.location} ({alert.level})\n"
        f"Valor de ASI: {alert.asi_value}%\n"
        f"Periodo: {alert.period}\n"
        f"Motivo: {alert.reason}\n\n"
        "Las alertas reflejan condiciones de estrés/sequía agrícola "
        "identificadas por FAO GIEWS/ASIS y no necesariamente una "
        "declaratoria oficial de sequía.")
    return asunto, cuerpo


if __name__ == "__main__":
    sid = sys.argv[1] if len(sys.argv) > 1 else "asi_gs1"
    pend = pending_alerts(sid)
    print(f"{len(pend)} alertas nuevas para {sid}")
    for a in pend:
        subject, body = format_email(a)
        print("---", subject)
        print(body)
    dest = recipients()
    print(f"\ndestinatarios configurados: {len(dest)}"
          + (f" ({', '.join(dest)})" if dest
             else f" (ninguno: defina {RECIPIENTS_ENV})"))
