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
from asis.build import diff_dekad, is_preliminary, preliminary_dekads

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


# --- Dato preliminar: los ultimos dekads se aceptan sin --aceptar-republicacion
CATALOGO = ["2026-07-D1", "2026-07-D2", "2026-07-D3",
            "2026-08-D1", "2026-08-D2", "2026-08-D3"]


def test_la_ventana_preliminar_son_los_tres_mas_nuevos():
    assert preliminary_dekads(CATALOGO) == ["2026-08-D1", "2026-08-D2",
                                            "2026-08-D3"]


def test_el_dekad_mas_nuevo_es_preliminar():
    assert is_preliminary("2026-08-D3", preliminary_dekads(CATALOGO))


def test_dos_dekads_atras_del_mas_nuevo_sigue_siendo_preliminar():
    """El caso que motivo ensanchar la ventana: se midio una revision real de
    FAO en 2026-08-D1 cuando el mas nuevo ya era 2026-08-D3. Con la ventana de
    un solo dekad esa revision habria detenido la corrida."""
    assert is_preliminary("2026-08-D1", preliminary_dekads(CATALOGO))


def test_mas_atras_de_la_ventana_no_es_preliminar():
    """Aqui sigue viva la red de seguridad: un dekad ya asentado que cambia
    necesita --aceptar-republicacion, porque seria una revision anomala."""
    assert not is_preliminary("2026-07-D3", preliminary_dekads(CATALOGO))


def test_catalogo_mas_corto_que_la_ventana_no_revienta():
    assert preliminary_dekads(["2026-08-D3"]) == ["2026-08-D3"]


def test_sin_catalogo_nada_es_preliminar():
    """Si no se pudo consultar el catalogo, no se marca nada por default:
    preferible quedarse corto en la marca de transparencia que arriesgar
    marcar un dekad viejo como si todavia pudiera cambiar."""
    assert preliminary_dekads([]) == []
    assert not is_preliminary("2026-08-D3", None)
