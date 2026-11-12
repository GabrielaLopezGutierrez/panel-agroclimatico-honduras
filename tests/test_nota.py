"""La nota metodologica declara las mismas constantes que el codigo.

El motivo es un caso real: la nota afirmaba un area de pixel de 0,988 km2
despues de que el codigo la corrigiera a 0,9494, y nadie lo noto hasta que se
reviso a mano. Una nota que describe el calculo con una constante distinta no
es documentacion, es una segunda version del calculo.

La nota define cada constante una sola vez, en los `\\newcommand` de su
preambulo. Esto lee ese bloque y lo contrasta contra `asis/config.py` y
`data/manifest.json`.

El documento vive en `docs/`, que no se versiona: si no esta, las pruebas se
saltan en vez de fallar.
"""
import json
import re

import pytest

from asis import config as cfg

NOTA = cfg.ROOT / "docs" / "nota-conceptual-metodologia.tex"
MANIFIESTO = cfg.DATA / "manifest.json"


def _constantes() -> dict[str, str]:
    """Los \\newcommand del preambulo, ya sin el formato de LaTeX.

    La coma decimal se escribe `0{,}9494` para que babel no le meta espacio, y
    el separador de miles `12\\,297`. Los dos se deshacen aqui para comparar
    contra numeros de Python.
    """
    if not NOTA.exists():
        pytest.skip("docs/ no esta en esta copia del repositorio")
    texto = NOTA.read_text(encoding="utf-8")
    out = {}
    for nombre, valor in re.findall(r"\\newcommand\{\\(c\w+)\}\{([^}]*(?:\}[^}]*)*?)\}\s",
                                    texto):
        v = valor.replace("{,}", ".").replace("\\,", "").strip()
        out[nombre] = v
    return out


@pytest.fixture(scope="module")
def notas():
    return _constantes()


@pytest.fixture(scope="module")
def manifiesto():
    if not MANIFIESTO.exists():
        pytest.skip("no hay panel construido")
    return json.loads(MANIFIESTO.read_text(encoding="utf-8"))


def test_el_preambulo_declara_todas_las_constantes(notas):
    """Si alguien agrega una cifra al cuerpo sin pasarla por el preambulo, esta
    prueba no la ve. Al menos fija que el bloque siga completo."""
    esperadas = {
        "cPixKmDos", "cAnioInicio", "cKappa", "cPreliminares",
        "cMunicipios", "cPares", "cErre", "cErreDos", "cMae", "cSesgo",
        "cDekadsCultivo", "cDekadsPastura", "cPrimerDekadPastura",
    }
    faltan = esperadas - set(notas)
    assert not faltan, f"faltan en el preambulo de la nota: {sorted(faltan)}"


def test_las_constantes_de_calculo_coinciden_con_config(notas):
    assert float(notas["cPixKmDos"]) == cfg.PIX_KM2
    assert int(notas["cAnioInicio"]) == cfg.START_YEAR
    assert float(notas["cKappa"]) == cfg.TOLERANCE_FRAC


def test_los_dekads_preliminares_coinciden_con_el_constructor(notas):
    from asis import build

    assert int(notas["cPreliminares"]) == build.PRELIMINARY_DEKADS


def test_las_cifras_de_validacion_coinciden_con_el_manifiesto(notas, manifiesto):
    """Son las que la nota publica en el resumen: si el panel se reconstruye y
    la validacion cambia, la nota tiene que cambiar con ella."""
    v = manifiesto["validacion"]
    assert int(notas["cPares"]) == v["pares"]
    assert float(notas["cErre"]) == v["r"]
    assert float(notas["cErreDos"]) == v["r2"]
    assert float(notas["cMae"]) == v["mae_pp"]
    assert float(notas["cSesgo"]) == v["sesgo_pp"]


def test_la_cobertura_declarada_coincide_con_el_panel(notas, manifiesto):
    series = manifiesto["series"]
    assert int(notas["cMunicipios"]) == manifiesto["municipios"]
    assert int(notas["cDekadsCultivo"]) == series["asi_gs1"]["n_dekads"]
    if "asi_gs1_pasto" in series:
        assert int(notas["cDekadsPastura"]) == series["asi_gs1_pasto"]["n_dekads"]
        assert notas["cPrimerDekadPastura"] == series["asi_gs1_pasto"]["primero"]


def test_la_nota_nombra_las_dos_coberturas_y_su_regla():
    """Lo que no puede faltar del pastizal: que existen dos mascaras, cuales
    son sus sufijos en la fuente, y que nunca se promedian entre si."""
    if not NOTA.exists():
        pytest.skip("docs/ no esta en esta copia del repositorio")
    texto = NOTA.read_text(encoding="utf-8")
    for marca in ("LC-C", "LC-G", "pastizal", "nunca se promedian"):
        assert marca in texto, f"la nota no menciona {marca!r}"
    # Y que la regla se aplique: las cantidades por pixel llevan la cobertura.
    assert "n^c_{m,t}" in texto and "\\bar{x}^c_{m,t}" in texto


def test_cada_simbolo_de_la_tabla_apunta_a_algo_que_existe():
    """La tabla de correspondencia es la promesa de transparencia de la nota.
    Si nombra un identificador que ya no existe, la promesa es falsa."""
    if not NOTA.exists():
        pytest.skip("docs/ no esta en esta copia del repositorio")
    texto = NOTA.read_text(encoding="utf-8")
    tabla = texto.split("\\label{tab:codigo}")[1].split("\\end{tabular}")[0]
    citados = {m.replace("\\_", "_")
               for m in re.findall(r"\\texttt\{([A-Za-z_.\\]+)\}", tabla)}
    modulos = {"config": cfg}
    from asis import aggregate, calendar, panel, viz, zonal
    modulos.update(aggregate=aggregate, calendar=calendar, panel=panel,
                   viz=viz, zonal=zonal)
    columnas = {"n_px", "km2", "mean", "p10", "p90", "value", "lta",
                "anom_pct", "km2_gt", "pct_gt", "ok", "Series.cover"}
    for cita in citados:
        if cita in columnas or "." not in cita:
            continue
        modulo, _, nombre = cita.partition(".")
        assert modulo in modulos, f"{cita}: modulo desconocido"
        assert hasattr(modulos[modulo], nombre), f"{cita} no existe en el codigo"


def test_las_columnas_que_nombra_la_tabla_estan_en_el_panel():
    """Las cantidades por unidad y dekad son columnas descargables. Si la nota
    las nombra, tienen que estar en el parquet."""
    from asis import panel

    if not panel.stored_series():
        pytest.skip("no hay panel construido")
    df = panel.load("asi_gs1", *(panel.dekads("asi_gs1")[-1],) * 2)
    for col in ("n_px", "km2", "mean", "p10", "p90"):
        assert col in df.columns, f"la nota nombra {col} y el panel no lo tiene"
    assert any(c.startswith("km2_gt") for c in df.columns)
    assert any(c.startswith("pct_gt") for c in df.columns)
