"""Cálculos geográficos puros da exportação (zona UTM, convergência, grade)."""
import math

import pytest


def test_zona_utm_de_epsg_hemisferio_norte(geo):
    assert geo.zona_utm_de_epsg(32601) == (1, False)
    assert geo.zona_utm_de_epsg(32622) == (22, False)
    assert geo.zona_utm_de_epsg(32660) == (60, False)


def test_zona_utm_de_epsg_hemisferio_sul(geo):
    assert geo.zona_utm_de_epsg(32701) == (1, True)
    assert geo.zona_utm_de_epsg(32722) == (22, True)
    assert geo.zona_utm_de_epsg(32760) == (60, True)


def test_zona_utm_de_epsg_rejeita_nao_utm(geo):
    for epsg in (4326, 31982, 32600, 32661, 32700, 32761, 3857):
        with pytest.raises(ValueError):
            geo.zona_utm_de_epsg(epsg)


def test_meridiano_central(geo):
    assert geo.meridiano_central(22) == -51   # zona de Santa Catarina
    assert geo.meridiano_central(23) == -45
    assert geo.meridiano_central(31) == 3


def test_codigo_grade_zona_ocd(geo):
    # UTM (grade 2): Norte -> 2000+zona; Sul -> -(2000+zona).
    assert geo.codigo_grade_zona(32622) == 2022
    assert geo.codigo_grade_zona(32722) == -2022


def test_convergencia_nula_no_meridiano_central(geo):
    assert geo.convergencia_utm(-27.0, -51.0, -51.0) == pytest.approx(0.0)


def test_convergencia_sinal_e_valor(geo):
    # gamma = atan(tan(dlon) * sin(lat)); Florianópolis (zona 22, lon0 -51):
    # dlon positivo e latitude sul -> convergência negativa.
    valor = geo.convergencia_utm(-27.0, -48.5, -51.0)
    esperado = math.degrees(math.atan(
        math.tan(math.radians(2.5)) * math.sin(math.radians(-27.0))))
    assert valor == pytest.approx(esperado)
    assert valor < 0
    # Espelhando para o hemisfério norte, o sinal inverte.
    assert geo.convergencia_utm(27.0, -48.5, -51.0) == pytest.approx(-valor)
