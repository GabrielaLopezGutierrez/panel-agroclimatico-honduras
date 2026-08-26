"""Semantica de los indicadores y ventanas de temporada."""
import pytest

from asis import config as cfg


def test_rango_valido_declarado_para_cada_serie():
    for s in cfg.SERIES.values():
        lo, hi = s.valid_range
        assert lo < hi


def test_tolerancia_escala_con_el_rango_del_indicador():
    """Media unidad es ruido de redondeo en el ASI (0-100) y media escala en el
    VCI (0-1). Una tolerancia absoluta comun dejaria pasar en silencio una
    republicacion que cambiara el VCI por completo."""
    asi = cfg.tolerance_for(cfg.SERIES["asi_gs1"])
    vci = cfg.tolerance_for(cfg.SERIES["vci"])
    assert asi == pytest.approx(0.5)
    assert vci == pytest.approx(0.005)
    assert vci < asi


@pytest.mark.parametrize("dekad,gs1,gs2", [
    (7, False, False),      # marzo D1: ninguna temporada activa
    (10, False, False),     # abril D1
    (13, True, False),      # mayo D1: arranca la primera
    (23, True, False),      # agosto D2
    (25, True, True),       # septiembre D1: se solapan
    (30, True, True),       # octubre D3: cierra la primera
    (32, False, True),      # noviembre D2: solo la postrera
    (2, False, True),       # enero D2: la postrera cruza el fin de ano
])
def test_ventana_de_cultivo(dekad, gs1, gs2):
    assert cfg.in_season("GS1", dekad) is gs1
    assert cfg.in_season("GS2", dekad) is gs2


def test_sin_temporada_siempre_esta_en_ventana():
    """El VCI cubre todo el ano y todo el territorio."""
    for k in range(1, 37):
        assert cfg.in_season(None, k) is True


def test_las_banderas_no_estan_en_ningun_rango_valido():
    """251 a 255 son banderas, no valores del indice."""
    for s in cfg.SERIES.values():
        lo, hi = s.valid_range
        for flag in cfg.FLAGS:
            assert not (lo <= flag <= hi)


def test_clases_cubren_todo_el_rango():
    for family, (cuts, labels, colors) in cfg.CLASSES.items():
        assert len(labels) == len(colors) == len(cuts) - 1
        assert cuts == sorted(cuts)
