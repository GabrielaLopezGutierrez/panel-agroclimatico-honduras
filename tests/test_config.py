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


# --- Area del pixel ----------------------------------------------------------
def _cell_km2(lat_deg: float) -> float:
    """Area exacta sobre WGS84 de una celda de la malla centrada en esa latitud.

    Integral de area del elipsoide entre dos paralelos, por el ancho en
    longitud. Es la definicion de PIX_KM2, escrita aparte a proposito: si
    llamara al mismo numero que quiere comprobar, no comprobaria nada.
    """
    import numpy as np

    a_e, f = 6378.137, 1 / 298.257223563
    e2 = f * (2 - f)
    e = np.sqrt(e2)

    def q(phi):
        s = np.sin(phi)
        return s / (1 - e2 * s ** 2) + np.log((1 + e * s) / (1 - e * s)) / (2 * e)

    half = np.radians(cfg.PIX_DEG / 2)
    phi = np.radians(lat_deg)
    return float(np.radians(cfg.PIX_DEG) * a_e ** 2 * (1 - e2) / 2
                 * (q(phi + half) - q(phi - half)))


def test_el_area_del_pixel_es_la_de_la_latitud_de_honduras():
    """La celda de la malla es un cuadro del graticulado, no un cuadrado: el
    grado de longitud se acorta con el coseno de la latitud. Tomar el lado en el
    ecuador daba 0,988 km2 e inflaba toda superficie declarada en un 4,1%."""
    assert _cell_km2(0) == pytest.approx(0.9813, abs=0.001)     # el valor viejo
    sur, norte = _cell_km2(12.90), _cell_km2(16.60)             # HND_BBOX
    assert norte < cfg.PIX_KM2 < sur
    assert cfg.PIX_KM2 == pytest.approx((sur + norte) / 2, rel=0.005)


def test_el_area_del_pixel_cuadra_con_la_geometria_del_panel():
    """Contraste independiente: la superficie de los 290 municipios en
    proyeccion equiarea, repartida entre los pixeles de zona que los cubren. No
    pasa por la formula de arriba ni por la constante."""
    from asis import panel

    muni = panel.municipios()
    medida = muni["area_km2"].sum() / muni["zone_px"].sum()
    assert cfg.PIX_KM2 == pytest.approx(medida, rel=0.01)
