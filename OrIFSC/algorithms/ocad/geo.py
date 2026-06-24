"""Cálculos geográficos para a exportação: declinação magnética, convergência
meridiana (UTM) e o código OCD de grade/zona.

A declinação vem do modelo magnético mundial (WMM) via API pública da NOAA. Se a
chamada falhar (sem internet, serviço fora), o chamador usa o valor manual.
"""
import json
import math

from ...rede import baixar_bytes

# Chave "demo" usada pela própria calculadora web da NOAA (geomag-web).
_NOAA_URL = (
    'https://www.ngdc.noaa.gov/geomag-web/calculators/calculateDeclination'
    '?lat1={lat}&lon1={lon}&key=zNEw7&resultFormat=json'
    '&startYear={ano}&startMonth={mes}&startDay={dia}'
)


def declinacao_noaa(lat, lon, ano, mes, dia):
    """Declinação magnética (graus, leste +) pela NOAA/WMM, ou None se falhar."""
    url = _NOAA_URL.format(lat=lat, lon=lon, ano=ano, mes=mes, dia=dia)
    try:
        dados = json.loads(baixar_bytes(url).decode('utf-8'))
        return float(dados['result'][0]['declination'])
    except Exception:
        return None


def convergencia_utm(lat_deg, lon_deg, lon0_deg):
    """Convergência meridiana (graus) num ponto UTM.

    Ângulo entre o norte verdadeiro e o norte da grade. Fórmula de 1ª ordem
    (γ = atan(tan(Δλ)·sen φ)), suficiente para a área de um mapa de orientação.
    """
    dlon = math.radians(lon_deg - lon0_deg)
    lat = math.radians(lat_deg)
    return math.degrees(math.atan(math.tan(dlon) * math.sin(lat)))


def meridiano_central(zona):
    """Longitude (graus) do meridiano central de uma zona UTM."""
    return zona * 6 - 183


def zona_utm_de_epsg(epsg):
    """(zona, sul) a partir de um EPSG WGS84/UTM (326xx ou 327xx)."""
    if 32601 <= epsg <= 32660:
        return epsg - 32600, False
    if 32701 <= epsg <= 32760:
        return epsg - 32700, True
    raise ValueError(f'EPSG {epsg} não é WGS84/UTM (esperado 326xx ou 327xx).')


def codigo_grade_zona(epsg):
    """Campo `i` do OCD (string 1039): grade·1000 + zona, negativo no Sul.

    Para UTM (OcdGrid::Utm = 2): Norte → 2000+zona; Sul → -(2000+zona).
    Espelha `toOcd()`/`combineGridZone()` do OpenOrienteering Mapper.
    """
    zona, sul = zona_utm_de_epsg(epsg)
    i = 2000 + zona
    return -i if sul else i
