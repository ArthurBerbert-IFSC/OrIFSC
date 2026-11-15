"""Etapas do Assistente OrIFSC: o que já foi feito, o que vem a seguir e o
que ficou desatualizado.

Módulo puro (sem QGIS): recebe uma ``Situacao`` (montada a partir do projeto
por ``assistente.situacao_do_projeto``) e devolve a lista de ``Etapa`` que o
painel desenha. Decisões de nov/2026: o assistente guia sem travar (todas as
etapas continuam clicáveis), mostra ✓ feito / ▶ próximo / ⚠ atenção, e marca
curvas e exportação como desatualizadas quando a folha muda.
"""
from typing import Dict, List, NamedTuple, Optional, Tuple


def N_(texto: str) -> str:
    """Marca o texto para tradução (extraído por tools/i18n_atualizar.py).
    O painel mostra ``tr(texto, **valores)``. Local para o módulo seguir
    puro e testável sem o pacote."""
    return texto


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
    """Uma linha do painel: estado, texto e ações (rótulo, id da ação).

    ``titulo``, ``detalhe`` e os rótulos das ações são chaves em português;
    ``valores`` preenche os placeholders do detalhe na hora de traduzir.
    """
    id: str
    titulo: str
    estado: str
    detalhe: str
    acoes: Tuple[Tuple[str, str], ...]
    valores: Dict[str, str] = {}


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
        local = Etapa('local', N_('Tipo de mapa e local'), PENDENTE,
                      N_('Escolha o tipo de mapa, a coordenada e a folha.'),
                      ((N_('Definir local'), 'definir_local'),))
    elif not s.folha_girada:
        local = Etapa('local', N_('Tipo de mapa e local'), AVISO,
                      N_('Folha da versão antiga, alinhada à quadrícula: no '
                         'OCAD ela sai inclinada. Refaça o local ou use '
                         '"Ajustar folha" para girá-la.'),
                      ((N_('Refazer local'), 'definir_local'),
                       (N_('Ajustar folha'), 'ajustar_folha')))
    else:
        if s.resumo_folha:
            detalhe, valores = N_('{resumo}'), {'resumo': s.resumo_folha}
        else:
            detalhe, valores = N_('Folha definida.'), {}
        local = Etapa('local', N_('Tipo de mapa e local'), FEITO, detalhe,
                      ((N_('Refazer'), 'definir_local'),), valores)

    if s.tem_folha:
        ajustar = Etapa('ajustar', N_('Ajustar folha'), OPCIONAL,
                        N_('Mova a folha no mapa ou troque escala, papel e '
                           'orientação.'),
                        ((N_('Ajustar folha'), 'ajustar_folha'),))
    else:
        ajustar = Etapa('ajustar', N_('Ajustar folha'), OPCIONAL,
                        N_('Disponível depois de definir o local.'),
                        ((N_('Ajustar folha'), 'ajustar_folha'),))

    acoes_fundo = ((N_('Satélite'), 'satelite'), (N_('OpenStreetMap'), 'osm'),
                   (N_('Ortofoto SC'), 'sigsc'))
    if s.tem_fundo:
        fundo = Etapa('fundo', N_('Imagem de fundo'), FEITO,
                      N_('Há uma imagem de fundo no projeto.'), acoes_fundo)
    else:
        fundo = Etapa('fundo', N_('Imagem de fundo'), PENDENTE,
                      N_('Carregue uma imagem para se localizar (o satélite '
                         'do projeto OCAD é baixado na exportação).'),
                      acoes_fundo)

    acoes_limite = ((N_('Desenhar limite'), 'limite'),
                    (N_('Encaixar folha no limite'), 'ajustar_folha'))
    if s.tem_limite:
        limite = Etapa('limite', N_('Limite da área'), FEITO,
                       N_('Limite desenhado. Você pode encaixar a folha '
                          'nele.'),
                       acoes_limite)
    else:
        limite = Etapa('limite', N_('Limite da área'), OPCIONAL,
                       N_('Desenhe o contorno da área a mapear se quiser '
                          'encaixar a folha nele.'), acoes_limite)

    if curvas_desatualizadas(s):
        curvas = Etapa('curvas', N_('Curvas de nível'), AVISO,
                       N_('A folha mudou depois das curvas: gere de novo.'),
                       ((N_('Gerar de novo'), 'curvas'),))
    elif s.tem_curvas:
        curvas = Etapa('curvas', N_('Curvas de nível'), FEITO,
                       N_('Curvas geradas para a folha atual.'),
                       ((N_('Gerar de novo'), 'curvas'),))
    else:
        curvas = Etapa('curvas', N_('Curvas de nível'), PENDENTE,
                       N_('Gera curvas suavizadas (MDT Copernicus 30 m) para '
                          'a folha.'), ((N_('Gerar curvas'), 'curvas'),))

    if exportacao_desatualizada(s):
        exportar = Etapa('exportar', N_('Exportar para OCAD / OOM'), AVISO,
                         N_('A folha ou as curvas mudaram depois da '
                            'exportação: exporte de novo.'),
                         ((N_('Exportar de novo'), 'exportar'),))
    elif s.exportado:
        if s.exportacao_pasta:
            detalhe = N_('Projeto exportado em {pasta}.')
            valores = {'pasta': s.exportacao_pasta}
        else:
            detalhe, valores = N_('Projeto exportado.'), {}
        exportar = Etapa('exportar', N_('Exportar para OCAD / OOM'), FEITO,
                         detalhe, ((N_('Exportar de novo'), 'exportar'),),
                         valores)
    else:
        exportar = Etapa('exportar', N_('Exportar para OCAD / OOM'), PENDENTE,
                         N_('Gera o .ocd / .omap com georreferência, satélite '
                            'e curvas.'), ((N_('Exportar'), 'exportar'),))

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
