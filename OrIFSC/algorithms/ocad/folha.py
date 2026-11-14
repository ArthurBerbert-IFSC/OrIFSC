"""Tamanhos de papel, dimensões da folha e encaixe da folha num limite.

Módulo puro (sem QGIS). Centraliza a tabela de papéis usada pelo Definir
Local e pelo Ajustar Folha, a dedução do papel a partir das dimensões salvas
no projeto e o "Ajustar ao limite" (decisões de nov/2026: o papel aumenta
primeiro, a escala da norma não muda sozinha, nunca diminui o papel escolhido,
5 mm de folga no papel).
"""
import math
from typing import Iterable, NamedTuple, Optional, Sequence, Tuple

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


MARGEM_PADRAO_MM = 5.0


class AjusteFolha(NamedTuple):
    """Resultado do encaixe da folha num limite."""
    cabe: bool
    papel: str
    retrato: bool
    larg_mm: float
    alt_mm: float
    ref_e: float
    ref_n: float
    escala: int
    escala_minima: float


def ajustar_ao_limite(
        pontos: Iterable[Tuple[float, float]],
        escala: int,
        grivacao_graus: float,
        papel_inicial: str = 'A4',
        margem_mm: float = MARGEM_PADRAO_MM) -> AjusteFolha:
    """Folha (papel, orientação, centro) que contém o limite na escala dada.

    A folha é sempre girada para o norte magnético, então o limite é medido
    no referencial do papel. A orientação vem da proporção do limite (mais
    largo que alto → paisagem; ela nunca encaixa pior que a outra). Parte do
    ``papel_inicial`` e aumenta até o maior papel; se nem ele couber,
    ``cabe`` é False e ``escala_minima`` diz o menor denominador em que o
    limite caberia no maior papel (a decisão de mudar a escala é do usuário).

    Args:
        pontos: Vértices do limite em UTM (metros).
        escala: Denominador da escala do projeto.
        grivacao_graus: Rotação da folha (declinação − convergência).
        papel_inicial: Papel escolhido; nunca é reduzido.
        margem_mm: Folga mínima entre o limite e a borda, em mm de papel.
    """
    from .geo import mundo_para_papel, papel_para_mundo

    pts = list(pontos)
    if not pts:
        raise ValueError('O limite não tem vértices.')
    nomes = [nome for nome, _, _ in PAPEIS]
    if papel_inicial not in nomes:
        raise ValueError('Papel desconhecido: %r' % (papel_inicial,))

    # Referência provisória no centro do retângulo envolvente (UTM).
    ref_e = (min(e for e, _ in pts) + max(e for e, _ in pts)) / 2.0
    ref_n = (min(n for _, n in pts) + max(n for _, n in pts)) / 2.0
    papel = [mundo_para_papel(e, n, ref_e, ref_n, escala, grivacao_graus)
             for e, n in pts]
    x0, x1 = min(x for x, _ in papel), max(x for x, _ in papel)
    y0, y1 = min(y for _, y in papel), max(y for _, y in papel)
    larg_lim, alt_lim = x1 - x0, y1 - y0
    centro_e, centro_n = papel_para_mundo((x0 + x1) / 2.0, (y0 + y1) / 2.0,
                                          ref_e, ref_n, escala,
                                          grivacao_graus)
    retrato = alt_lim > larg_lim

    # PAPEIS vai do maior para o menor: percorre do inicial até o maior.
    for nome in reversed(nomes[:nomes.index(papel_inicial) + 1]):
        larg, alt = dimensoes_papel(nome, retrato)
        if (larg_lim + 2 * margem_mm <= larg + 1e-9
                and alt_lim + 2 * margem_mm <= alt + 1e-9):
            return AjusteFolha(True, nome, retrato, larg, alt, centro_e,
                               centro_n, escala, 0.0)

    maior = nomes[0]
    larg, alt = dimensoes_papel(maior, retrato)
    # Medidas do limite no papel são proporcionais a 1/escala.
    minima = escala * max(larg_lim / (larg - 2 * margem_mm),
                          alt_lim / (alt - 2 * margem_mm))
    return AjusteFolha(False, maior, retrato, larg, alt, centro_e, centro_n,
                       escala, minima)


def escala_sugerida(escala_minima: float,
                    padroes: Sequence[int] = (4000, 5000, 7500, 10000,
                                              15000)) -> int:
    """Menor escala padrão com denominador ≥ ``escala_minima``; acima da
    tabela, arredonda para cima em múltiplos de 500."""
    for valor in sorted(padroes):
        if valor >= escala_minima - 1e-6:
            return int(valor)
    return int(math.ceil(escala_minima / 500.0) * 500)
