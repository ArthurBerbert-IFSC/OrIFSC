"""Tipos de mapa: predefinições de norma, escala, equidistância e papel.

Módulo puro (sem QGIS). O tipo escolhido no Definir Local preenche escala e
papel e fica salvo no projeto; a geração de curvas usa a equidistância do tipo
e a exportação usa a norma do tipo — sempre como padrão editável (decisões de
nov/2026, valores validados com a FLORA).
"""
from typing import NamedTuple, Optional

# Mesmos valores de simbologia.NORMA_ISOM / NORMA_ISSPROM (repetidos aqui para
# manter este módulo sem dependências).
NORMA_ISOM = 'ISOM'
NORMA_ISSPROM = 'ISSPROM'

PERSONALIZADO = 'personalizado'


class TipoMapa(NamedTuple):
    """Predefinição de um tipo de mapa (``norma`` None = sem predefinição)."""
    id: str
    rotulo: str
    norma: Optional[str]
    escala: Optional[int]
    equidistancia: Optional[float]
    papel: Optional[str]


TIPOS_MAPA = (
    TipoMapa('sprint', 'Sprint / urbano', NORMA_ISSPROM, 4000, 2.5, 'A4'),
    TipoMapa('floresta', 'Floresta / rural', NORMA_ISOM, 10000, 5.0, 'A4'),
    TipoMapa('escolar', 'Escolar / parque', NORMA_ISSPROM, 2000, 2.0, 'A4'),
    TipoMapa(PERSONALIZADO, 'Personalizado', None, None, None, None),
)

ROTULO_NORMA = {
    NORMA_ISOM: 'ISOM 2017-2',
    NORMA_ISSPROM: 'ISSprOM 2019-2',
}


def tipo_por_id(tipo_id: Optional[str]) -> Optional[TipoMapa]:
    """O tipo com esse id, ou None (id vazio ou desconhecido)."""
    for tipo in TIPOS_MAPA:
        if tipo.id == tipo_id:
            return tipo
    return None


def tem_predefinicao(tipo: Optional[TipoMapa]) -> bool:
    """True para os tipos que fixam norma/escala/equidistância/papel."""
    return tipo is not None and tipo.id != PERSONALIZADO


def resumo(tipo: TipoMapa) -> str:
    """Linha curta para o diálogo: o que o tipo vai usar."""
    if not tem_predefinicao(tipo):
        return ('Norma sugerida pela escala (até 1:5.000 → ISSprOM) e '
                'equidistância das Configurações.')
    equi = f'{tipo.equidistancia:g}'.replace('.', ',')
    escala = f'{tipo.escala:,}'.replace(',', '.')
    return (f'{ROTULO_NORMA[tipo.norma]} · 1:{escala} · equidistância '
            f'{equi} m · {tipo.papel}')
