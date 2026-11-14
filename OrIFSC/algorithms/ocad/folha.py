"""Tamanhos de papel e dimensões da folha no terreno (módulo puro, sem QGIS).

Centraliza a tabela de papéis usada pelo Definir Local e pelo Ajustar Folha,
e a dedução do papel a partir das dimensões salvas no projeto.
"""
from typing import Optional, Tuple

# (nome, lado maior em mm, lado menor em mm), do maior para o menor.
PAPEIS = (('A3', 420, 297), ('A4', 297, 210), ('A5', 210, 148))


def dimensoes_papel(nome: str, retrato: bool) -> Tuple[float, float]:
    """(largura, altura) em mm do papel ``nome`` na orientação pedida."""
    for n, maior, menor in PAPEIS:
        if n == nome:
            return (menor, maior) if retrato else (maior, menor)
    raise ValueError('Papel desconhecido: %r' % (nome,))


def identificar_papel(larg_mm: float,
                      alt_mm: float) -> Optional[Tuple[str, bool]]:
    """(nome, retrato) do papel com essas dimensões, ou None se não for um
    papel da tabela (ex.: folha de projeto antigo com tamanho arredondado)."""
    for nome, maior, menor in PAPEIS:
        if abs(max(larg_mm, alt_mm) - maior) < 0.5 and \
                abs(min(larg_mm, alt_mm) - menor) < 0.5:
            return nome, alt_mm > larg_mm
    return None


def area_terreno_m(larg_mm: float, alt_mm: float,
                   escala: int) -> Tuple[float, float]:
    """(largura, altura) da folha no terreno, em metros."""
    return larg_mm * escala / 1000.0, alt_mm * escala / 1000.0
