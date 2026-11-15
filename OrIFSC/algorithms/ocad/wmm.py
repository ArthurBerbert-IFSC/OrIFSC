"""Declinação magnética offline pelo World Magnetic Model (WMM).

Lê os coeficientes de Gauss do arquivo oficial ``.COF`` embutido em
``recursos/wmm`` e calcula a declinação para qualquer ponto e data, sem
internet. Segue as equações do relatório técnico do WMM (NOAA/BGS):
coordenadas geodésicas WGS84 → geocêntricas esféricas, harmônicos esféricos
até o grau 12 com funções de Legendre semi-normalizadas de Schmidt, e rotação
do campo de volta ao referencial geodésico.

Módulo puro (sem QGIS), testável isoladamente.
"""
import datetime
import math
import os
from functools import lru_cache
from typing import List, NamedTuple, Tuple

ARQUIVO_PADRAO = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(
        __file__)))), 'recursos', 'wmm', 'WMM2025.COF')

_A_WGS84_KM = 6378.137
_F_WGS84 = 1.0 / 298.257223563
_E2_WGS84 = _F_WGS84 * (2.0 - _F_WGS84)
_RAIO_REFERENCIA_KM = 6371.2
_ANOS_VALIDADE = 5.0


class ModeloWMM(NamedTuple):
    """Coeficientes de um modelo WMM (matrizes [n][m], n e m até ``n_max``)."""
    epoca: float
    nome: str
    n_max: int
    g: List[List[float]]
    h: List[List[float]]
    g_var: List[List[float]]
    h_var: List[List[float]]

    @property
    def valido_ate(self) -> float:
        """Ano decimal em que o modelo deixa de valer (época + 5 anos)."""
        return self.epoca + _ANOS_VALIDADE


def ler_cof(caminho: str) -> ModeloWMM:
    """Lê um arquivo ``.COF`` no formato oficial do WMM.

    Primeira linha: época, nome e data de publicação; depois uma linha por
    termo (n, m, g, h, ġ, ḣ), terminando numa linha de noves.
    """
    with open(caminho, encoding='ascii') as f:
        linhas = f.read().splitlines()
    if not linhas:
        raise ValueError('Arquivo de coeficientes WMM vazio: %s' % caminho)
    cabecalho = linhas[0].split()
    epoca, nome = float(cabecalho[0]), cabecalho[1]

    termos = []
    for linha in linhas[1:]:
        partes = linha.split()
        if not partes or partes[0].startswith('9999'):
            break
        n, m = int(partes[0]), int(partes[1])
        termos.append((n, m) + tuple(float(v) for v in partes[2:6]))
    if not termos:
        raise ValueError('Nenhum coeficiente no arquivo WMM: %s' % caminho)

    n_max = max(t[0] for t in termos)

    def matriz():
        return [[0.0] * (n_max + 1) for _ in range(n_max + 1)]

    g, h, g_var, h_var = matriz(), matriz(), matriz(), matriz()
    for n, m, gnm, hnm, dg, dh in termos:
        g[n][m], h[n][m], g_var[n][m], h_var[n][m] = gnm, hnm, dg, dh
    return ModeloWMM(epoca, nome, n_max, g, h, g_var, h_var)


@lru_cache(maxsize=4)
def modelo_padrao(caminho: str = ARQUIVO_PADRAO) -> ModeloWMM:
    """Modelo embutido no plugin (lido uma vez e mantido em cache)."""
    return ler_cof(caminho)


def ano_decimal(data: datetime.date) -> float:
    """Data → ano decimal (ex.: 1º/jul/2026 ≈ 2026,496)."""
    inicio = datetime.date(data.year, 1, 1)
    dias_no_ano = (datetime.date(data.year + 1, 1, 1) - inicio).days
    return data.year + (data - inicio).days / dias_no_ano


def _legendre_schmidt(
        n_max: int,
        cos_t: float,
        sen_t: float) -> Tuple[List[List[float]], List[List[float]]]:
    """Funções de Legendre semi-normalizadas de Schmidt e derivada em θ.

    θ é a colatitude geocêntrica. As recorrências trabalham com as funções
    não normalizadas (sem a fase de Condon-Shortley) e derivam termo a termo,
    sem dividir por sen θ; no fim aplica o fator de Schmidt
    √((2 − δ₀ₘ)(n − m)!/(n + m)!).
    """
    p = [[0.0] * (n_max + 1) for _ in range(n_max + 1)]
    dp = [[0.0] * (n_max + 1) for _ in range(n_max + 1)]
    p[0][0] = 1.0
    for m in range(n_max + 1):
        if m > 0:
            p[m][m] = (2 * m - 1) * sen_t * p[m - 1][m - 1]
            dp[m][m] = (2 * m - 1) * (cos_t * p[m - 1][m - 1]
                                      + sen_t * dp[m - 1][m - 1])
        if m + 1 <= n_max:
            p[m + 1][m] = (2 * m + 1) * cos_t * p[m][m]
            dp[m + 1][m] = (2 * m + 1) * (-sen_t * p[m][m]
                                          + cos_t * dp[m][m])
        for n in range(m + 2, n_max + 1):
            p[n][m] = ((2 * n - 1) * cos_t * p[n - 1][m]
                       - (n + m - 1) * p[n - 2][m]) / (n - m)
            dp[n][m] = ((2 * n - 1) * (-sen_t * p[n - 1][m]
                                       + cos_t * dp[n - 1][m])
                        - (n + m - 1) * dp[n - 2][m]) / (n - m)
    for n in range(n_max + 1):
        for m in range(n + 1):
            fator = math.sqrt((2.0 if m else 1.0) * math.factorial(n - m)
                              / math.factorial(n + m))
            p[n][m] *= fator
            dp[n][m] *= fator
    return p, dp


def _campo_geocentrico(
        modelo: ModeloWMM,
        dt: float,
        r_km: float,
        cos_t: float,
        sen_t: float,
        lam: float) -> Tuple[float, float, float]:
    """X', Y', Z' (nT) no referencial geocêntrico esférico.

    É o gradiente do potencial V = a Σ (a/r)^(n+1) Σ (g cos mλ + h sen mλ)
    P̆ₙᵐ(cos θ): X' = (1/r)∂V/∂θ, Y' = −(1/(r sen θ))∂V/∂λ, Z' = ∂V/∂r.
    """
    p, dp = _legendre_schmidt(modelo.n_max, cos_t, sen_t)
    x_c = y_c = z_c = 0.0
    razao = _RAIO_REFERENCIA_KM / r_km
    for n in range(1, modelo.n_max + 1):
        fator_r = razao ** (n + 2)
        for m in range(n + 1):
            gnm = modelo.g[n][m] + dt * modelo.g_var[n][m]
            hnm = modelo.h[n][m] + dt * modelo.h_var[n][m]
            cos_ml, sen_ml = math.cos(m * lam), math.sin(m * lam)
            termo = gnm * cos_ml + hnm * sen_ml
            x_c += fator_r * termo * dp[n][m]
            y_c += fator_r * m * (gnm * sen_ml - hnm * cos_ml) * p[n][m]
            z_c -= fator_r * (n + 1) * termo * p[n][m]
    return x_c, y_c / sen_t, z_c


def campo_magnetico(
        lat: float,
        lon: float,
        ano: float,
        altitude_km: float = 0.0,
        modelo: ModeloWMM = None) -> Tuple[float, float, float]:
    """Componentes X (norte), Y (leste), Z (para baixo) em nT, geodésicas."""
    if modelo is None:
        modelo = modelo_padrao()
    if not -90.0 < lat < 90.0:
        raise ValueError('Latitude fora do intervalo aberto (-90, 90): %r'
                         % (lat,))
    dt = ano - modelo.epoca

    phi = math.radians(lat)
    lam = math.radians(lon)
    sen_phi, cos_phi = math.sin(phi), math.cos(phi)
    rc = _A_WGS84_KM / math.sqrt(1.0 - _E2_WGS84 * sen_phi * sen_phi)
    p_eq = (rc + altitude_km) * cos_phi
    z_ax = (rc * (1.0 - _E2_WGS84) + altitude_km) * sen_phi
    r = math.hypot(p_eq, z_ax)
    phi_c = math.asin(z_ax / r)

    # Colatitude geocêntrica: cos θ = sen φ', sen θ = cos φ'.
    x_c, y_c, z_c = _campo_geocentrico(
        modelo, dt, r, math.sin(phi_c), math.cos(phi_c), lam)

    psi = phi_c - phi
    x = x_c * math.cos(psi) - z_c * math.sin(psi)
    z = x_c * math.sin(psi) + z_c * math.cos(psi)
    return x, y_c, z


def declinacao(
        lat: float,
        lon: float,
        ano: float,
        altitude_km: float = 0.0,
        modelo: ModeloWMM = None) -> float:
    """Declinação magnética em graus (leste positivo, oeste negativo)."""
    x, y, _ = campo_magnetico(lat, lon, ano, altitude_km, modelo)
    return math.degrees(math.atan2(y, x))


def declinacao_na_data(
        lat: float,
        lon: float,
        data: datetime.date,
        modelo: ModeloWMM = None) -> Tuple[float, bool]:
    """(declinação em graus, dentro_da_validade) para uma data civil.

    Fora da validade do modelo o valor ainda é calculado (erro cresce cerca
    de 0,1° por ano); cabe ao chamador avisar o usuário.
    """
    if modelo is None:
        modelo = modelo_padrao()
    ano = ano_decimal(data)
    valido = modelo.epoca <= ano < modelo.valido_ate
    return declinacao(lat, lon, ano, modelo=modelo), valido
