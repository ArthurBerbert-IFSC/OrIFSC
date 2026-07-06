"""Suavização de polilinhas — módulo puro (NumPy, sem QGIS).

Separado de ``gerar_curvas.py`` para poder ser testado isoladamente
(``tests/``) sem uma instalação do QGIS.
"""
import numpy as np


def chaikin(pts: np.ndarray, iteracoes: int = 2) -> np.ndarray:
    """Suaviza uma polilinha por corner-cutting de Chaikin, vetorizado com
    NumPy — mesmos coeficientes 0,75/0,25 da implementação original em Python
    puro (resultado idêntico bit a bit), mas ordens de grandeza mais rápido em
    curvas densas.

    Não usa o motor de geometria do QGIS (que estava travando), então é seguro
    para qualquer dado. Mantém os extremos de linhas abertas e trata linhas
    fechadas (anéis) de forma cíclica. `pts` é um array float64 (n, 2).
    """
    if len(pts) < 3:
        return pts
    fechada = bool(np.all(pts[0] == pts[-1]))
    if fechada:
        base = pts[:-1]
        for _ in range(iteracoes):
            seguinte = np.roll(base, -1, axis=0)
            novo = np.empty((2 * len(base), 2), dtype=np.float64)
            novo[0::2] = 0.75 * base + 0.25 * seguinte
            novo[1::2] = 0.25 * base + 0.75 * seguinte
            base = novo
        return np.vstack([base, base[:1]])
    for _ in range(iteracoes):
        p0, p1 = pts[:-1], pts[1:]
        novo = np.empty((2 * len(p0) + 2, 2), dtype=np.float64)
        novo[0] = pts[0]
        novo[1:-1:2] = 0.75 * p0 + 0.25 * p1
        novo[2:-1:2] = 0.25 * p0 + 0.75 * p1
        novo[-1] = pts[-1]
        pts = novo
    return pts
