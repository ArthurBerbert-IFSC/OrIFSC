"""Etapas do Assistente OrIFSC: o que já foi feito, o que vem a seguir e o
que ficou desatualizado.

Módulo puro (sem QGIS): recebe uma ``Situacao`` (montada a partir do projeto
por ``assistente.situacao_do_projeto``) e devolve a lista de ``Etapa`` que o
painel desenha. Decisões de nov/2026: o assistente guia sem travar (todas as
etapas continuam clicáveis), mostra ✓ feito / ▶ próximo / ⚠ atenção, e marca
curvas e exportação como desatualizadas quando a folha muda.
"""
from typing import List, NamedTuple, Optional, Tuple

FEITO = 'feito'
PROXIMO = 'proximo'
AVISO = 'aviso'
PENDENTE = 'pendente'
OPCIONAL = 'opcional'

# Etapas que formam o caminho principal (o ▶ percorre só estas, na ordem).
CAMINHO = ('local', 'fundo', 'curvas', 'exportar')


class Situacao(NamedTuple):
    """Retrato do projeto que o assistente precisa saber."""
    tem_folha: bool = False
    folha_girada: bool = False
    resumo_folha: str = ''
    tem_fundo: bool = False
    tem_limite: bool = False
    tem_curvas: bool = False
    folha_revisao: int = 0
    curvas_folha_revisao: Optional[int] = None
    curvas_geracao: int = 0
    exportado: bool = False
    exportacao_folha_revisao: Optional[int] = None
    exportacao_curvas_geracao: Optional[int] = None
    exportacao_pasta: str = ''


class Etapa(NamedTuple):
    """Uma linha do painel: estado, texto e ações (rótulo, id da ação)."""
    id: str
    titulo: str
    estado: str
    detalhe: str
    acoes: Tuple[Tuple[str, str], ...]


def curvas_desatualizadas(s: Situacao) -> bool:
    """Curvas geradas para uma folha que já mudou (sem registro = em dia)."""
    return (s.tem_curvas and s.curvas_folha_revisao is not None
            and s.curvas_folha_revisao != s.folha_revisao)


def exportacao_desatualizada(s: Situacao) -> bool:
    """A folha ou as curvas mudaram depois da última exportação."""
    return s.exportado and (
        s.exportacao_folha_revisao != s.folha_revisao
        or s.exportacao_curvas_geracao != s.curvas_geracao)


def calcular_etapas(s: Situacao) -> List[Etapa]:
    """As seis etapas do assistente com o estado de cada uma."""
    if not s.tem_folha:
        local = Etapa('local', 'Tipo de mapa e local', PENDENTE,
                      'Escolha o tipo de mapa, a coordenada e a folha.',
                      (('Definir local', 'definir_local'),))
    elif not s.folha_girada:
        local = Etapa('local', 'Tipo de mapa e local', AVISO,
                      'Folha da versão antiga, alinhada à quadrícula: no '
                      'OCAD ela sai inclinada. Refaça o local ou use '
                      '"Ajustar folha" para girá-la.',
                      (('Refazer local', 'definir_local'),
                       ('Ajustar folha', 'ajustar_folha')))
    else:
        local = Etapa('local', 'Tipo de mapa e local', FEITO,
                      s.resumo_folha or 'Folha definida.',
                      (('Refazer', 'definir_local'),))

    if s.tem_folha:
        ajustar = Etapa('ajustar', 'Ajustar folha', OPCIONAL,
                        'Mova a folha no mapa ou troque escala, papel e '
                        'orientação.',
                        (('Ajustar folha', 'ajustar_folha'),))
    else:
        ajustar = Etapa('ajustar', 'Ajustar folha', OPCIONAL,
                        'Disponível depois de definir o local.',
                        (('Ajustar folha', 'ajustar_folha'),))

    acoes_fundo = (('Satélite', 'satelite'), ('OpenStreetMap', 'osm'),
                   ('Ortofoto SC', 'sigsc'))
    if s.tem_fundo:
        fundo = Etapa('fundo', 'Imagem de fundo', FEITO,
                      'Há uma imagem de fundo no projeto.', acoes_fundo)
    else:
        fundo = Etapa('fundo', 'Imagem de fundo', PENDENTE,
                      'Carregue uma imagem para se localizar (o satélite do '
                      'projeto OCAD é baixado na exportação).', acoes_fundo)

    acoes_limite = (('Desenhar limite', 'limite'),
                    ('Encaixar folha no limite', 'ajustar_folha'))
    if s.tem_limite:
        limite = Etapa('limite', 'Limite da área', FEITO,
                       'Limite desenhado. Você pode encaixar a folha nele.',
                       acoes_limite)
    else:
        limite = Etapa('limite', 'Limite da área', OPCIONAL,
                       'Desenhe o contorno da área a mapear se quiser '
                       'encaixar a folha nele.', acoes_limite)

    if curvas_desatualizadas(s):
        curvas = Etapa('curvas', 'Curvas de nível', AVISO,
                       'A folha mudou depois das curvas: gere de novo.',
                       (('Gerar de novo', 'curvas'),))
    elif s.tem_curvas:
        curvas = Etapa('curvas', 'Curvas de nível', FEITO,
                       'Curvas geradas para a folha atual.',
                       (('Gerar de novo', 'curvas'),))
    else:
        curvas = Etapa('curvas', 'Curvas de nível', PENDENTE,
                       'Gera curvas suavizadas (MDT Copernicus 30 m) para a '
                       'folha.', (('Gerar curvas', 'curvas'),))

    if exportacao_desatualizada(s):
        exportar = Etapa('exportar', 'Exportar para OCAD / OOM', AVISO,
                         'A folha ou as curvas mudaram depois da exportação: '
                         'exporte de novo.',
                         (('Exportar de novo', 'exportar'),))
    elif s.exportado:
        onde = f' em {s.exportacao_pasta}' if s.exportacao_pasta else ''
        exportar = Etapa('exportar', 'Exportar para OCAD / OOM', FEITO,
                         f'Projeto exportado{onde}.',
                         (('Exportar de novo', 'exportar'),))
    else:
        exportar = Etapa('exportar', 'Exportar para OCAD / OOM', PENDENTE,
                         'Gera o .ocd / .omap com georreferência, satélite e '
                         'curvas.', (('Exportar', 'exportar'),))

    etapas = [local, ajustar, fundo, limite, curvas, exportar]
    # ▶ na primeira etapa pendente do caminho principal. Se antes dela houver
    # uma etapa pedindo atenção (⚠), não há ▶: resolver o aviso vem antes
    # (ex.: não sugerir exportar com curvas desatualizadas).
    for i, etapa in enumerate(etapas):
        if etapa.id not in CAMINHO:
            continue
        if etapa.estado == AVISO:
            break
        if etapa.estado == PENDENTE:
            etapas[i] = etapa._replace(estado=PROXIMO)
            break
    return etapas
