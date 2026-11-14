"""Cálculos geográficos para a exportação: declinação magnética, convergência
meridiana (UTM), geometria da folha girada e o código OCD de grade/zona.

A declinação vem do World Magnetic Model calculado offline (``wmm.py``, com os
coeficientes embutidos em ``recursos/wmm``) — sem internet e sem chave de API.
"""
import datetime
import math
from typing import List, Tuple


def declinacao_wmm(lat: float, lon: float,
                   data: datetime.date) -> Tuple[float, bool]:
    """(declinação em graus, leste +; dentro_da_validade) pelo WMM offline."""
    # Import tardio: mantém este módulo carregável isolado nos testes (que o
    # leem direto do arquivo, fora do pacote).
    from .wmm import declinacao_na_data
    return declinacao_na_data(lat, lon, data)


def convergencia_utm(lat_deg: float, lon_deg: float, lon0_deg: float) -> float:
    """Convergência meridiana (graus) num ponto UTM.

    Ângulo entre o norte verdadeiro e o norte da grade. Fórmula de 1ª ordem
    (γ = atan(tan(Δλ)·sen φ)), suficiente para a área de um mapa de orientação.
    """
    dlon = math.radians(lon_deg - lon0_deg)
    lat = math.radians(lat_deg)
    return math.degrees(math.atan(math.tan(dlon) * math.sin(lat)))


def grivacao(declinacao: float, convergencia: float) -> float:
    """Ângulo entre o norte da quadrícula UTM e o norte magnético (graus).

    É o ângulo com que o papel do OCAD/OOM fica girado em relação à grade;
    positivo = norte magnético a leste da grade (sentido horário).
    """
    return declinacao - convergencia


def papel_para_mundo(x_mm: float, y_mm: float, ref_e: float, ref_n: float,
                     escala: int, grivacao_graus: float) -> Tuple[float, float]:
    """Ponto do papel (mm, y para baixo, origem no centro) → UTM (metros).

    Reproduz exatamente o ``QTransform`` de ``ProjetoOcad`` (convenção do
    OpenOrienteering Mapper): translate(ref) · rotate(−grivação) ·
    scale(s, −s), com s = escala/1000 m por mm. O topo do papel aponta para
    o norte magnético.
    """
    s = escala / 1000.0
    g = math.radians(grivacao_graus)
    xs, ys = s * x_mm, -s * y_mm
    return (ref_e + xs * math.cos(g) + ys * math.sin(g),
            ref_n - xs * math.sin(g) + ys * math.cos(g))


def mundo_para_papel(e: float, n: float, ref_e: float, ref_n: float,
                     escala: int, grivacao_graus: float) -> Tuple[float, float]:
    """Inverso de ``papel_para_mundo``: UTM (metros) → papel (mm, y para
    baixo, origem em ``ref``)."""
    s = escala / 1000.0
    g = math.radians(grivacao_graus)
    de, dn = e - ref_e, n - ref_n
    xs = de * math.cos(g) - dn * math.sin(g)
    ys = de * math.sin(g) + dn * math.cos(g)
    return xs / s, -ys / s


def cantos_folha(ref_e: float, ref_n: float, larg_mm: float, alt_mm: float,
                 escala: int, grivacao_graus: float) -> List[Tuple[float, float]]:
    """Os 4 cantos (UTM) de uma folha centrada em ``ref`` e girada para o
    norte magnético: superior-esquerdo, superior-direito, inferior-direito,
    inferior-esquerdo.

    No OCAD/OOM essa folha aparece em pé, alinhada ao papel. Com grivação
    zero é o retângulo alinhado à quadrícula UTM (comportamento da 0.1.x).
    """
    meia_l, meia_a = larg_mm / 2.0, alt_mm / 2.0
    return [papel_para_mundo(x, y, ref_e, ref_n, escala, grivacao_graus)
            for x, y in ((-meia_l, -meia_a), (meia_l, -meia_a),
                         (meia_l, meia_a), (-meia_l, meia_a))]


def espacamento_norte_mm(norma: str, escala: int) -> float:
    """Espaçamento das linhas de norte magnético no papel (mm), pela norma.

    Textos das normas, como estão nos symbol sets embutidos (símbolo 601):
    ISOM 2017-2 — 20 mm em 1:15.000, isto é, 300 m no terreno (30 mm na
    ampliação 1:10.000); ISSprOM 2019-2 — 30 mm no papel em qualquer escala.
    """
    if norma == 'ISOM':
        return 300.0 * 1000.0 / escala
    if norma == 'ISSPROM':
        return 30.0
    raise ValueError('Norma desconhecida para linhas de norte: %r' % (norma,))


def linhas_norte(poligono_mm: List[Tuple[float, float]],
                 espacamento_mm: float,
                 folga_borda_mm: float = 0.5) -> List[List[Tuple[float, float]]]:
    """Linhas de norte magnético cobrindo a folha, no papel (mm, y para baixo).

    No papel do OCAD/OOM o norte magnético é o "para cima", então as linhas
    são verticais, a cada ``espacamento_mm`` a partir do centro (x = 0) e
    recortadas pelo contorno da folha (polígono convexo — a folha é um
    retângulo, girado ou não). Cada linha vai de baixo para cima (sul →
    norte), para que um símbolo com seta aponte para o norte. Linhas a menos
    de ``folga_borda_mm`` das laterais da folha são omitidas (cairiam sobre
    a borda).
    """
    if espacamento_mm <= 0:
        raise ValueError('Espaçamento das linhas de norte deve ser > 0.')
    pts = list(poligono_mm)
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    if len(pts) < 3:
        return []
    x_min = min(x for x, _ in pts) + folga_borda_mm
    x_max = max(x for x, _ in pts) - folga_borda_mm
    linhas = []
    k = math.ceil(x_min / espacamento_mm)
    while k * espacamento_mm <= x_max:
        x = k * espacamento_mm
        ys = []
        for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
            if x1 != x2 and (x1 - x) * (x2 - x) <= 0:
                ys.append(y1 + (x - x1) / (x2 - x1) * (y2 - y1))
        if len(ys) >= 2 and max(ys) - min(ys) > 1e-9:
            linhas.append([(x, max(ys)), (x, min(ys))])
        k += 1
    return linhas


def meridiano_central(zona: int) -> int:
    """Longitude (graus) do meridiano central de uma zona UTM."""
    return zona * 6 - 183


def zona_utm_de_epsg(epsg: int) -> Tuple[int, bool]:
    """(zona, sul) a partir de um EPSG WGS84/UTM (326xx ou 327xx)."""
    if 32601 <= epsg <= 32660:
        return epsg - 32600, False
    if 32701 <= epsg <= 32760:
        return epsg - 32700, True
    raise ValueError(f'EPSG {epsg} não é WGS84/UTM (esperado 326xx ou 327xx).')


def codigo_grade_zona(epsg: int) -> int:
    """Campo `i` do OCD (string 1039): grade·1000 + zona, negativo no Sul.

    Para UTM (OcdGrid::Utm = 2): Norte → 2000+zona; Sul → -(2000+zona).
    Espelha `toOcd()`/`combineGridZone()` do OpenOrienteering Mapper.
    """
    zona, sul = zona_utm_de_epsg(epsg)
    i = 2000 + zona
    return -i if sul else i
