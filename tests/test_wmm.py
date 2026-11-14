"""Declinação magnética offline (WMM2025) — algorithms/ocad/wmm.py.

Sem acesso a uma referência externa no CI, a validação combina: leitura do
arquivo oficial, formas fechadas das funções de Legendre, derivadas
numéricas, o campo comparado com o gradiente numérico do potencial
(confere sinais e montagem das somas), dipolos com resposta analítica e
faixas de declinação conhecidas (que confirmam a convenção leste = +).
"""
import datetime
import math

import pytest


@pytest.fixture(scope='session')
def modelo(wmm):
    return wmm.modelo_padrao()


def _modelo_so(wmm, termos):
    """Modelo sintético só com os termos dados {(n, m): (g, h)}."""
    n_max = 12
    zeros = [[0.0] * (n_max + 1) for _ in range(n_max + 1)]
    g = [linha[:] for linha in zeros]
    h = [linha[:] for linha in zeros]
    for (n, m), (gnm, hnm) in termos.items():
        g[n][m], h[n][m] = gnm, hnm
    return wmm.ModeloWMM(2025.0, 'teste', n_max, g, h,
                         [linha[:] for linha in zeros],
                         [linha[:] for linha in zeros])


def test_le_arquivo_oficial(modelo):
    assert modelo.epoca == 2025.0
    assert modelo.nome == 'WMM-2025'
    assert modelo.n_max == 12
    assert modelo.valido_ate == 2030.0
    assert modelo.g[1][0] == -29351.8
    assert modelo.g[1][1] == -1410.8
    assert modelo.h[1][1] == 4545.4
    assert modelo.g_var[1][0] == 12.0
    assert modelo.g[12][12] == -0.7
    assert modelo.h[1][0] == 0.0  # h não existe para m = 0


@pytest.mark.parametrize('teta_graus', [5.0, 37.0, 90.0, 118.0, 171.0])
def test_legendre_formas_fechadas(wmm, teta_graus):
    t = math.radians(teta_graus)
    c, s = math.cos(t), math.sin(t)
    p, dp = wmm._legendre_schmidt(12, c, s)
    r3 = math.sqrt(3.0)
    esperado = {
        (1, 0): (c, -s),
        (1, 1): (s, c),
        (2, 0): (1.5 * c * c - 0.5, -3.0 * c * s),
        (2, 1): (r3 * c * s, r3 * (c * c - s * s)),
        (2, 2): (0.5 * r3 * s * s, r3 * s * c),
    }
    for (n, m), (val, der) in esperado.items():
        assert p[n][m] == pytest.approx(val, abs=1e-12)
        assert dp[n][m] == pytest.approx(der, abs=1e-12)


def test_derivada_legendre_bate_com_diferenca_numerica(wmm):
    t, eps = math.radians(63.0), 1e-6
    p_mais, _ = wmm._legendre_schmidt(12, math.cos(t + eps), math.sin(t + eps))
    p_menos, _ = wmm._legendre_schmidt(12, math.cos(t - eps),
                                       math.sin(t - eps))
    _, dp = wmm._legendre_schmidt(12, math.cos(t), math.sin(t))
    for n in range(13):
        for m in range(n + 1):
            numerica = (p_mais[n][m] - p_menos[n][m]) / (2 * eps)
            assert dp[n][m] == pytest.approx(numerica, rel=1e-6, abs=1e-8)


def _potencial(wmm, modelo, r, teta, lam):
    p, _ = wmm._legendre_schmidt(modelo.n_max, math.cos(teta), math.sin(teta))
    a = wmm._RAIO_REFERENCIA_KM
    v = 0.0
    for n in range(1, modelo.n_max + 1):
        for m in range(n + 1):
            v += (a * (a / r) ** (n + 1)
                  * (modelo.g[n][m] * math.cos(m * lam)
                     + modelo.h[n][m] * math.sin(m * lam)) * p[n][m])
    return v


def test_campo_e_o_gradiente_do_potencial(wmm, modelo):
    r, teta, lam = 6390.0, math.radians(117.6), math.radians(-48.5)
    x, y, z = wmm._campo_geocentrico(modelo, 0.0, r, math.cos(teta),
                                     math.sin(teta), lam)
    dr, da = 1e-3, 1e-7
    dv_dteta = (_potencial(wmm, modelo, r, teta + da, lam)
                - _potencial(wmm, modelo, r, teta - da, lam)) / (2 * da)
    dv_dlam = (_potencial(wmm, modelo, r, teta, lam + da)
               - _potencial(wmm, modelo, r, teta, lam - da)) / (2 * da)
    dv_dr = (_potencial(wmm, modelo, r + dr, teta, lam)
             - _potencial(wmm, modelo, r - dr, teta, lam)) / (2 * dr)
    assert x == pytest.approx(dv_dteta / r, rel=1e-5)
    assert y == pytest.approx(-dv_dlam / (r * math.sin(teta)), rel=1e-5)
    assert z == pytest.approx(dv_dr, rel=1e-5)


def test_dipolo_axial_tem_declinacao_zero(wmm):
    axial = _modelo_so(wmm, {(1, 0): (-29000.0, 0.0)})
    for lat, lon in [(-27.6, -48.5), (45.0, 10.0), (-70.0, 150.0)]:
        assert wmm.declinacao(lat, lon, 2025.0, modelo=axial) == \
            pytest.approx(0.0, abs=1e-9)


def test_dipolo_inclinado_bate_com_formula_analitica(wmm):
    g10, g11, h11 = -29000.0, -1400.0, 4500.0
    inclinado = _modelo_so(wmm, {(1, 0): (g10, 0.0), (1, 1): (g11, h11)})
    teta, lam = math.radians(110.0), math.radians(-40.0)
    x, y, _ = wmm._campo_geocentrico(inclinado, 0.0, 6371.2, math.cos(teta),
                                     math.sin(teta), lam)
    x_esp = (-g10 * math.sin(teta)
             + (g11 * math.cos(lam) + h11 * math.sin(lam)) * math.cos(teta))
    y_esp = g11 * math.sin(lam) - h11 * math.cos(lam)
    assert x == pytest.approx(x_esp, rel=1e-12)
    assert y == pytest.approx(y_esp, rel=1e-12)


@pytest.mark.parametrize('lat, lon, minimo, maximo', [
    (-27.5954, -48.548, -24.0, -19.0),   # Florianópolis: ~20° oeste
    (40.0, -105.0, 6.0, 9.5),            # Boulder (EUA): ~8° leste
    (51.5, -0.12, -0.5, 3.0),            # Londres: perto de zero, leste
    (-33.87, 151.2, 11.0, 14.5),         # Sydney: ~12-13° leste
])
def test_declinacao_em_faixas_conhecidas(wmm, lat, lon, minimo, maximo):
    d = wmm.declinacao(lat, lon, 2026.9)
    assert minimo < d < maximo


def test_variacao_anual_pequena(wmm):
    d0 = wmm.declinacao(-27.6, -48.5, 2025.0)
    d1 = wmm.declinacao(-27.6, -48.5, 2026.0)
    assert 0.0 < abs(d1 - d0) < 0.5


def test_ano_decimal(wmm):
    assert wmm.ano_decimal(datetime.date(2026, 1, 1)) == 2026.0
    assert wmm.ano_decimal(datetime.date(2024, 7, 2)) == \
        pytest.approx(2024 + 183 / 366)


def test_validade_do_modelo(wmm):
    _, valido = wmm.declinacao_na_data(-27.6, -48.5, datetime.date(2026, 11, 14))
    assert valido
    valor, valido = wmm.declinacao_na_data(-27.6, -48.5,
                                           datetime.date(2031, 3, 1))
    assert not valido
    assert -30.0 < valor < -15.0  # ainda calcula, só sinaliza


def test_latitude_no_polo_e_recusada(wmm):
    with pytest.raises(ValueError):
        wmm.declinacao(90.0, 0.0, 2026.0)
