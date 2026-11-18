"""La frontera entre el calculo y la app, comprobada en vez de acordada.

El proyecto se sostiene sobre una separacion: `asis/` calcula y dibuja sin saber
que existe una pantalla, y la app compone vistas. Eso es lo que permite que el
panel alimente a la vez al tablero, a las tablas de Flourish y a los cuadernos,
y es lo que haria barata una migracion a otro frontend.

Un acuerdo que no se comprueba se rompe solo. Las dos fugas que estas pruebas
cierran ya habian ocurrido: `asis/alerts.py` importaba streamlit para leer
`st.secrets`, y `streamlit_app.py` armaba una figura con `px.line` en vez de
pedirsela a `viz`. Ninguna rompia nada ese dia; las dos habrian encarecido la
migracion el dia que importara.

Se lee el texto de los modulos y no se importan: importar `streamlit_app` arranca
Streamlit, y aqui lo que interesa es que dependencia esta escrita, no cual se
ejecuta.
"""
import ast
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
PAQUETE = RAIZ / "asis"
APP = RAIZ / "streamlit_app.py"


def _importados(ruta: Path) -> set[str]:
    """Los paquetes de primer nivel que importa un archivo."""
    arbol = ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))
    nombres = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            nombres.update(a.name.split(".")[0] for a in nodo.names)
        elif isinstance(nodo, ast.ImportFrom) and nodo.level == 0 and nodo.module:
            nombres.add(nodo.module.split(".")[0])
    return nombres


@pytest.mark.parametrize("modulo", sorted(PAQUETE.glob("*.py")),
                         ids=lambda p: p.name)
def test_el_calculo_no_conoce_el_framework_de_la_app(modulo):
    """Ningun modulo de `asis/` importa streamlit.

    Es la condicion que hace instalable y reutilizable al paquete: un cuaderno,
    una API o un segundo tablero pueden depender de `asis` sin arrastrar un
    servidor web. La excepcion que existia estaba en `alerts.recipients()`, que
    ahora recibe los destinatarios en vez de ir a buscarlos.
    """
    assert "streamlit" not in _importados(modulo)


def test_la_app_no_dibuja_por_su_cuenta():
    """`streamlit_app.py` no importa plotly.

    Toda figura sale de `asis/viz.py`. Cuando la app dibuja una por su cuenta,
    esa figura no viaja: ni a los cuadernos, ni a Flourish, ni al frontend que
    venga despues. La ultima que lo hacia era la cuadricula departamental.
    """
    assert "plotly" not in _importados(APP)


def test_el_paquete_no_importa_la_app():
    """`asis/` no depende de `app/`. La flecha va en un solo sentido."""
    for modulo in PAQUETE.glob("*.py"):
        assert "app" not in _importados(modulo), modulo.name
