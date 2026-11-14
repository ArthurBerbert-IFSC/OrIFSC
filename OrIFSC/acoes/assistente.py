"""Assistente OrIFSC: painel lateral que guia as etapas sem travar nada.

Um ``QgsDockWidget`` com o mesmo visual dos painéis do plugin (``painel.py``,
Qt rich text). Cada etapa mostra ✓ feito / ▶ próximo / ! atenção (ou o número
da etapa, cinza, quando pendente ou opcional) e links que disparam as mesmas
ações do menu. O estado é lido do projeto (``situacao_do_projeto``) e
recalculado quando camadas entram ou saem, o projeto é aberto/limpo ou alguma
propriedade do OrIFSC é gravada (folha ajustada, curvas geradas, exportação).

Decisões de nov/2026: guia sem bloquear; abre sozinho na primeira vez e depois
o QGIS lembra se a pessoa fechou (controlado em ``orifsc.py``).
"""
import html
from typing import Any, Callable, Dict, List

from qgis.core import QgsProject, QgsRasterLayer, QgsVectorLayer, Qgis
from qgis.gui import QgsDockWidget
from qgis.PyQt.QtCore import QTimer
from qgis.PyQt.QtWidgets import QTextBrowser

from .etapas import (AVISO, FEITO, OPCIONAL, PROXIMO, Etapa, Situacao,
                     calcular_etapas)
from .painel import C, _dica, _esp, painel_html

COR_FEITO = '#2e7d32'
COR_AVISO = '#c77700'
COR_PENDENTE = '#c9c3b6'


def _graus(valor: float) -> str:
    return f'{valor:.2f}°'.replace('.', ',')


def situacao_do_projeto() -> Situacao:
    """Lê do projeto aberto tudo o que o assistente precisa."""
    from ..algorithms.ocad.folha import identificar_papel
    from .comum import (camada_curvas, ler_folha, ler_folha_girada,
                        ler_folha_revisao, ler_marcas, ler_tipo_mapa)
    from .criar_folha import camada_folha

    girada = ler_folha_girada()
    resumo = ''
    if girada is not None:
        partes = []
        tipo = ler_tipo_mapa()
        if tipo is not None:
            partes.append(tipo.rotulo)
        partes.append('1:' + f'{girada["escala"]:,}'.replace(',', '.'))
        papel = identificar_papel(girada['larg_mm'], girada['alt_mm'])
        if papel:
            partes.append(f'{papel[0]} {"retrato" if papel[1] else "paisagem"}')
        partes.append(f'folha girada {_graus(girada["grivacao"])}')
        resumo = ' · '.join(partes)

    camadas = list(QgsProject.instance().mapLayers().values())
    folha = camada_folha()
    tem_limite = any(
        isinstance(c, QgsVectorLayer)
        and c.geometryType() == Qgis.GeometryType.Polygon
        and (folha is None or c.id() != folha.id())
        and 'limite' in c.name().lower()
        for c in camadas)
    marcas = ler_marcas()
    return Situacao(
        tem_folha=ler_folha() is not None,
        folha_girada=girada is not None,
        resumo_folha=resumo,
        tem_fundo=any(isinstance(c, QgsRasterLayer) for c in camadas),
        tem_limite=tem_limite,
        tem_curvas=camada_curvas() is not None,
        folha_revisao=ler_folha_revisao(),
        curvas_folha_revisao=marcas['curvas_folha_revisao'],
        curvas_geracao=marcas['curvas_geracao'],
        exportado=marcas['exportacao_folha_revisao'] is not None,
        exportacao_folha_revisao=marcas['exportacao_folha_revisao'],
        exportacao_curvas_geracao=marcas['exportacao_curvas_geracao'],
        exportacao_pasta=marcas['exportacao_pasta'],
    )


def _marcador(numero: int, etapa: Etapa) -> str:
    """Célula quadrada colorida com o símbolo do estado."""
    simbolo, cor = {
        FEITO: ('✓', COR_FEITO),
        PROXIMO: ('▶', C['acento']),
        AVISO: ('!', COR_AVISO),
    }.get(etapa.estado, (str(numero), COR_PENDENTE))
    return ('<table cellspacing="0" cellpadding="0"><tr>'
            f'<td bgcolor="{cor}" align="center" width="20" '
            f'style="color:#ffffff; font-size:11px;"><b>{simbolo}</b></td>'
            '</tr></table>')


def html_etapas(etapas: List[Etapa]) -> str:
    """HTML do painel (Qt rich text: só tabelas, sem CSS moderno)."""
    linhas = ''
    for numero, etapa in enumerate(etapas, 1):
        titulo = (f'<span style="color:{C["texto"]}; font-size:13px;">'
                  f'<b>{html.escape(etapa.titulo)}</b></span>')
        if etapa.estado == OPCIONAL:
            titulo += (f'&nbsp; <span style="color:{C["texto2"]}; '
                       'font-size:10px;">OPCIONAL</span>')
        cor_detalhe = COR_AVISO if etapa.estado == AVISO else C['texto2']
        detalhe = (f'<span style="color:{cor_detalhe}; font-size:12px;">'
                   f'{html.escape(etapa.detalhe)}</span>')
        links = ' &nbsp;·&nbsp; '.join(
            f'<a href="orifsc:{acao}" style="color:{C["acento"]};">'
            f'{html.escape(rotulo)}</a>'
            for rotulo, acao in etapa.acoes)
        linhas += (
            '<tr>'
            f'<td valign="top" width="26">{_marcador(numero, etapa)}</td>'
            '<td style="padding-left:8px; padding-bottom:14px;">'
            f'{titulo}<br>{detalhe}<br>'
            f'<span style="font-size:12px;">{links}</span>'
            '</td></tr>')
    conteudo = (
        f'<table cellspacing="0" cellpadding="0" width="100%">{linhas}</table>'
        + _esp()
        + _dica('O assistente só sugere a ordem: nada fica bloqueado, e '
                'tudo continua no menu <b>OrIFSC</b>.'))
    return painel_html('Assistente', conteudo)


class PainelAssistente(QgsDockWidget):
    """Painel lateral com as etapas do mapa e atalhos para cada uma."""

    def __init__(self, acoes: Dict[str, Callable[[], Any]],
                 parent: Any = None) -> None:
        super().__init__('Assistente OrIFSC', parent)
        self.setObjectName('OrIFSCAssistente')
        self.acoes = acoes

        self.texto = QTextBrowser(self)
        self.texto.setOpenLinks(False)
        self.texto.setOpenExternalLinks(False)
        self.texto.setStyleSheet(
            f'QTextBrowser {{ background: {C["fundo"]}; border: none; }}')
        self.texto.anchorClicked.connect(self._clicou)
        self.setWidget(self.texto)

        # Junta rajadas de sinais (ex.: várias camadas entrando) num redesenho.
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(150)
        self._timer.timeout.connect(self.atualizar)

        projeto = QgsProject.instance()
        self._sinais = [projeto.layersAdded, projeto.layersRemoved,
                        projeto.cleared, projeto.readProject,
                        projeto.dirtySet]
        for sinal in self._sinais:
            sinal.connect(self.agendar)
        self.atualizar()

    def agendar(self, *_args: Any) -> None:
        """Pede um redesenho (adiado alguns ms para juntar sinais)."""
        self._timer.start()

    def etapas(self) -> List[Etapa]:
        """Etapas calculadas para o projeto atual."""
        return calcular_etapas(situacao_do_projeto())

    def atualizar(self) -> None:
        """Redesenha mantendo a posição da rolagem."""
        barra = self.texto.verticalScrollBar()
        posicao = barra.value()
        self.texto.setHtml(html_etapas(self.etapas()))
        barra.setValue(posicao)

    def _clicou(self, url: Any) -> None:
        acao = url.toString().split(':', 1)[-1]
        funcao = self.acoes.get(acao)
        if funcao is not None:
            funcao()
        self.agendar()

    def desconectar(self) -> None:
        """Solta os sinais do projeto (ao descarregar o plugin)."""
        self._timer.stop()
        for sinal in self._sinais:
            try:
                sinal.disconnect(self.agendar)
            except (TypeError, RuntimeError):
                pass
        self._sinais = []
