"""La deteccion de republicaciones de FAO.

De esta funcion depende que la actualizacion automatica avance o se detenga. Si
es demasiado laxa, sobrescribe en silencio una cifra que alguien ya pudo citar;
si es demasiado estricta, bloquea cada corrida con una falsa alarma. Las dos
fallas ya ocurrieron una vez, y de ahi vienen estas pruebas.
"""
import numpy as np
import pandas as pd
import pytest

from asis import config as cfg
from asis.build import diff_dekad

TOL_ASI = cfg.tolerance_for(cfg.SERIES["asi_gs1"])     # 0,5 pp
TOL_VCI = cfg.tolerance_for(cfg.SERIES["vci"])         # 0,005


def serie(valores):
    return pd.Series(valores, index=[str(i) for i in range(len(valores))],
                     dtype="float64")


def test_identicas_no_son_republicacion():
    s = serie([10.0, 20.0, 30.0])
    assert diff_dekad(s, s.copy(), TOL_ASI) is None


def test_mismos_nulos_en_ambas_no_son_republicacion():
    """El caso que producia la falsa alarma en cada corrida: el ASI tiene
    municipios fuera de temporada, y eso no es un cambio."""
    s = serie([10.0, np.nan, np.nan, 30.0])
    assert diff_dekad(s, s.copy(), TOL_ASI) is None


def test_diferencia_por_debajo_de_la_tolerancia_se_ignora():
    a = serie([10.0, 20.0])
    b = serie([10.2, 20.3])            # ruido de redondeo del servicio
    assert diff_dekad(a, b, TOL_ASI) is None


def test_diferencia_por_encima_de_la_tolerancia_se_reporta():
    a = serie([10.0, 20.0])
    b = serie([10.0, 25.0])
    found = diff_dekad(a, b, TOL_ASI)
    assert found is not None
    assert found["municipios_afectados"] == 1
    assert found["dif_max"] == pytest.approx(5.0)
    assert found["aparecen"] == 0 and found["desaparecen"] == 0


def test_la_escala_del_vci_se_respeta():
    """Dos decimas en el VCI son una quinta parte del indice: no es ruido."""
    a = serie([0.50, 0.60])
    b = serie([0.70, 0.60])
    assert diff_dekad(a, b, TOL_VCI) is not None
    # La misma diferencia, con la tolerancia del ASI, quedaria por debajo.
    assert diff_dekad(a, b, TOL_ASI) is None


def test_dato_que_aparece_se_reporta():
    a = serie([10.0, np.nan])
    b = serie([10.0, 40.0])
    found = diff_dekad(a, b, TOL_ASI)
    assert found is not None
    assert found["aparecen"] == 1 and found["desaparecen"] == 0


def test_dato_que_desaparece_se_reporta():
    """Un municipio que pierde el dato importa aunque no cambie ninguna media:
    la cobertura del panel cambio."""
    a = serie([10.0, 40.0])
    b = serie([10.0, np.nan])
    found = diff_dekad(a, b, TOL_ASI)
    assert found is not None
    assert found["desaparecen"] == 1 and found["aparecen"] == 0


def test_conteos_no_se_confunden_con_los_nulos_comunes():
    """Nulos compartidos, uno que aparece y uno que desaparece a la vez."""
    a = serie([np.nan, np.nan, 10.0, np.nan])
    b = serie([np.nan, 5.0, np.nan, np.nan])
    found = diff_dekad(a, b, TOL_ASI)
    assert found is not None
    assert found["aparecen"] == 1
    assert found["desaparecen"] == 1


def test_series_vacias_no_revientan():
    vacia = pd.Series(dtype="float64")
    assert diff_dekad(vacia, vacia, TOL_ASI) is None
