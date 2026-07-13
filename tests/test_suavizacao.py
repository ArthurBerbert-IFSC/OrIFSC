"""Chaikin vetorizado: equivalência com a implementação original e
propriedades geométricas que o algoritmo deve preservar."""
import random

import numpy as np


def _chaikin_referencia(pts, iteracoes=2):
    """Implementação original em Python puro (pré-0.1.11), usada como oráculo:
    o resultado do NumPy deve ser idêntico bit a bit a ela."""
    if len(pts) < 3:
        return pts
    fechada = pts[0] == pts[-1]
    if fechada:
        base = pts[:-1]
        for _ in range(iteracoes):
            novo = []
            m = len(base)
            for i in range(m):
                p0 = base[i]
                p1 = base[(i + 1) % m]
                novo.append((0.75 * p0[0] + 0.25 * p1[0],
                             0.75 * p0[1] + 0.25 * p1[1]))
                novo.append((0.25 * p0[0] + 0.75 * p1[0],
                             0.25 * p0[1] + 0.75 * p1[1]))
            base = novo
        return base + [base[0]]
    for _ in range(iteracoes):
        novo = [pts[0]]
        for i in range(len(pts) - 1):
            p0 = pts[i]
            p1 = pts[i + 1]
            novo.append((0.75 * p0[0] + 0.25 * p1[0],
                         0.75 * p0[1] + 0.25 * p1[1]))
            novo.append((0.25 * p0[0] + 0.75 * p1[0],
                         0.25 * p0[1] + 0.75 * p1[1]))
        novo.append(pts[-1])
        pts = novo
    return pts


def test_equivalencia_bit_a_bit_com_original(suavizacao):
    rng = random.Random(42)
    for caso in range(200):
        n = rng.randint(2, 300)
        pts = [(rng.uniform(-1e6, 1e6), rng.uniform(-1e7, 1e7))
               for _ in range(n)]
        if caso % 3 == 0 and n >= 4:
            pts[-1] = pts[0]
        for iteracoes in (1, 2, 3):
            esperado = np.array(_chaikin_referencia(list(pts), iteracoes))
            obtido = suavizacao.chaikin(
                np.array(pts, dtype=np.float64), iteracoes)
            assert esperado.shape == obtido.shape
            assert np.array_equal(esperado, obtido)


def test_extremos_de_linha_aberta_preservados(suavizacao):
    pts = np.array([(0.0, 0.0), (10.0, 8.0), (20.0, 0.0), (30.0, 8.0)])
    saida = suavizacao.chaikin(pts, 2)
    assert np.array_equal(saida[0], pts[0])
    assert np.array_equal(saida[-1], pts[-1])


def test_anel_fechado_continua_fechado(suavizacao):
    pts = np.array([(0.0, 0.0), (10.0, 0.0), (10.0, 10.0),
                    (0.0, 10.0), (0.0, 0.0)])
    saida = suavizacao.chaikin(pts, 2)
    assert np.array_equal(saida[0], saida[-1])


def test_linha_curta_passa_intacta(suavizacao):
    pts = np.array([(1.0, 2.0), (3.0, 4.0)])
    assert np.array_equal(suavizacao.chaikin(pts, 2), pts)


def test_numero_de_vertices_quadruplica_em_duas_iteracoes(suavizacao):
    # Linha aberta: cada iteração leva n -> 2n; duas iterações, n -> 4n.
    # (É por isso que a pré-simplificação antes do Chaikin importa tanto.)
    pts = np.array([(float(i), float(i % 3)) for i in range(50)])
    saida = suavizacao.chaikin(pts, 2)
    assert len(saida) == 4 * len(pts)
