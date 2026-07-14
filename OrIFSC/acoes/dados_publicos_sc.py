"""Dados Públicos — Santa Catarina — SIG@SC.

Fluxo principal: abre uma janela simples com escolhas prontas (Ortofoto/MDT
visual) e tenta adicionar automaticamente a camada WMS correspondente. Se der
erro, mostra a mensagem e volta para a janela de escolha, para o usuario tentar
outra opcao.

Ortofoto via WMTS (tiles, mais rápido); MDT via WMS (imagem de fundo — atenção:
é uma imagem renderizada, não valores de elevação, então NÃO serve para gerar
curvas; para curvas o plugin usa o MDT Copernicus).
"""
import xml.etree.ElementTree as ET  # nosec B405 - parse endurecido (guard anti-DOCTYPE/ENTITY)
from urllib.parse import quote
from typing import Any, List, Optional, Sequence, Set, Tuple

from qgis.core import (
    Qgis, QgsApplication, QgsMessageLog, QgsSettings, QgsTask,
)
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtGui import QDesktopServices

from .bases import abrir_gerenciador_wms
from ..rede import baixar_bytes

# Tarefas em andamento: a referência Python precisa sobreviver até a tarefa
# terminar — se o GC recolher um QgsTask em execução, o QGIS trava.
_TAREFAS: Set[QgsTask] = set()

URL_WMS = 'http://sigsc.sc.gov.br/sigserver/SIGSC/wms'
URL_WMTS = 'http://sigsc.sc.gov.br/sigserver/gwc/service/wmts'
PORTAL = 'https://sigsc.sc.gov.br/'

_CONEXOES = [
    ('SIG@SC Ortofoto (WMTS)', URL_WMTS),
    ('SIG@SC MDT (WMS)', URL_WMS),
]


def _registrar_conexoes() -> None:
    """Grava as conexões WMS/WMTS do SIG@SC nas configurações do QGIS, para
    aparecerem no gerenciador de fontes de dados (aba WMS/WMTS)."""
    s = QgsSettings()
    for nome, url in _CONEXOES:
        base = f'qgis/connections-wms/{nome}'
        s.setValue(f'{base}/url', url)
        s.setValue(f'{base}/dpiMode', 7)
        s.setValue(f'{base}/ignoreGetMapURI', False)
        s.setValue(f'{base}/ignoreGetFeatureInfoURI', False)
        s.setValue(f'{base}/smoothPixmapTransform', False)


def _listar_camadas_wms(url_wms: str) -> List[Tuple[str, str]]:
    """Retorna [(name, title), ...] a partir do GetCapabilities do WMS."""
    cap_url = (f'{url_wms}?service=WMS&request=GetCapabilities')
    conteudo = baixar_bytes(cap_url, user_agent='OrIFSC')
    # Defesa contra XML malicioso: o GetCapabilities vem da rede, então
    # recusamos DOCTYPE/ENTITY (um GetCapabilities legítimo não os declara).
    # Isso elimina XXE e "billion laughs" antes do parse; o expat do
    # ElementTree, além disso, não resolve entidades externas.
    if conteudo and (b'<!DOCTYPE' in conteudo or b'<!ENTITY' in conteudo):
        raise RuntimeError(
            'GetCapabilities do SIG@SC contém DOCTYPE/ENTITY — recusado '
            'por segurança.')
    root = ET.fromstring(conteudo)  # nosec B314 - guard acima recusa DOCTYPE/ENTITY
    camadas = []
    for el in root.iter():
        if not el.tag.lower().endswith('layer'):
            continue
        name = None
        title = None
        for ch in list(el):
            tag = ch.tag.lower()
            if tag.endswith('name') and ch.text:
                name = ch.text.strip()
            elif tag.endswith('title') and ch.text:
                title = ch.text.strip()
        if name:
            camadas.append((name, title or name))
    return camadas


def _escolher_camada(
        camadas: Sequence[Tuple[str, str]],
        termos: Sequence[str]) -> Optional[Tuple[str, str]]:
    """Escolhe a camada com melhor correspondencia por palavras-chave."""
    melhor = None
    melhor_score = -1
    for nome, titulo in camadas:
        texto = f'{nome} {titulo}'.lower()
        score = 0
        for t in termos:
            if t in texto:
                score += 1
        if score > melhor_score:
            melhor = (nome, titulo)
            melhor_score = score
    return melhor if melhor_score > 0 else None


def _uri_wms(url_wms: str, nome_camada: str, crs: str = 'EPSG:3857') -> str:
    """Monta URI de camada WMS para QgsRasterLayer(provider='wms')."""
    return (
        'contextualWMSLegend=0&'
        f'crs={quote(crs, safe=":")}&'
        'dpiMode=7&'
        'featureCount=10&'
        'format=image/png&'
        f'layers={quote(nome_camada, safe=",:_")}&'
        'styles=&'
        f'url={quote(url_wms, safe=":/?=&")}'
    )


def _adicionar_wms(
        iface: Any,
        nome_exibicao: str,
        url_wms: str,
        nome_camada: str):
    """Adiciona uma camada WMS diretamente no projeto."""
    from qgis.core import QgsRasterLayer, QgsProject

    uri = _uri_wms(url_wms, nome_camada)
    layer = QgsRasterLayer(uri, nome_exibicao, 'wms')
    if not layer.isValid():
        erro = layer.error().message() if layer.error() else 'sem detalhes'
        raise RuntimeError(f'QGIS nao conseguiu validar a camada WMS: {erro}')

    proj = QgsProject.instance()
    proj.addMapLayer(layer, False)
    root = proj.layerTreeRoot()
    root.insertLayer(len(root.children()), layer)

    canvas = iface.mapCanvas()
    canvas.setDestinationCrs(proj.crs())
    canvas.refreshAllLayers()
    canvas.refresh()
    return layer


def _dialogo_escolha(parent: Any = None) -> Optional[str]:
    """Mostra escolhas guiadas para usuário iniciante."""
    msg = QMessageBox(parent)
    msg.setIcon(QMessageBox.Icon.Question)
    msg.setWindowTitle('SIG@SC')
    msg.setText('O que você quer adicionar no mapa?')
    msg.setInformativeText(
        'Escolha uma opção pronta. O plugin tenta carregar automaticamente.')

    b1 = msg.addButton('Ortofoto (recomendado)',
                       QMessageBox.ButtonRole.ActionRole)
    b2 = msg.addButton('MDT visual (sombra de relevo)',
                       QMessageBox.ButtonRole.ActionRole)
    b3 = msg.addButton('Modo avançado (abrir WMS/WMTS manual)',
                       QMessageBox.ButtonRole.HelpRole)
    msg.addButton(QMessageBox.StandardButton.Cancel)
    msg.exec()

    clicado = msg.clickedButton()
    if clicado == b1:
        return 'orto'
    if clicado == b2:
        return 'mdt_visual'
    if clicado == b3:
        return 'manual'
    return None


def adicionar_sigsc(iface: Any, parent: Any = None) -> None:
    """Fluxo guiado do SIG@SC. A consulta ao serviço (GetCapabilities, que é
    lento) roda em segundo plano num ``QgsTask`` — o QGIS não congela. A
    camada é criada e adicionada no callback de conclusão, já na thread
    principal (camadas só entram no projeto pela thread da UI)."""
    _registrar_conexoes()
    escolha = _dialogo_escolha(parent)
    if escolha is None:
        return

    if escolha == 'manual':
        abriu = abrir_gerenciador_wms(iface, parent)
        if not abriu:
            iface.messageBar().pushMessage(
                'OrIFSC',
                'Não foi possível abrir o gerenciador WMS/WMTS. Use o '
                'menu de camadas do QGIS para adicionar o serviço manualmente.',
                level=Qgis.MessageLevel.Warning,
                duration=8)
        return

    if escolha == 'orto':
        termos = ('ortofoto', 'orto', 'aerea', 'aérea', 'imagem')
        nome_exibicao = 'SIG@SC Ortofoto (auto)'
        aviso_extra = ''
    else:
        termos = ('modelo digital de terreno', 'mdt', 'terreno', 'relevo')
        nome_exibicao = 'SIG@SC MDT (visual, auto)'
        aviso_extra = (' Esse dado é apenas visual e não serve para gerar '
                       'curvas.')

    iface.messageBar().pushMessage(
        'OrIFSC',
        'Consultando o SIG@SC em segundo plano — o QGIS continua livre; a '
        'camada aparece quando o serviço responder.',
        level=Qgis.MessageLevel.Info,
        duration=6)

    def _descobrir(_tarefa: Any) -> str:
        """Roda na thread da tarefa: encontra a camada no GetCapabilities."""
        camadas = _listar_camadas_wms(URL_WMS)
        alvo = _escolher_camada(camadas, termos)
        if alvo is None:
            raise RuntimeError(
                'Nenhuma camada correspondente no GetCapabilities do SIG@SC.')
        return alvo[0]

    def _concluir(excecao: Optional[Exception],
                  nome_camada: Optional[str] = None) -> None:
        """Roda na thread principal: adiciona a camada ou avisa a falha."""
        _TAREFAS.discard(tarefa)
        if excecao is not None or not nome_camada:
            QgsMessageLog.logMessage(f'Falha SIG@SC: {excecao}', 'OrIFSC',
                                     Qgis.MessageLevel.Warning)
            iface.messageBar().pushMessage(
                'OrIFSC',
                'Não foi possível carregar a camada do SIG@SC (serviço fora '
                'do ar ou lento). Tente novamente pelo menu, ou use o modo '
                'avançado.',
                level=Qgis.MessageLevel.Critical,
                duration=8)
            return
        try:
            _adicionar_wms(iface, nome_exibicao, URL_WMS, nome_camada)
        except Exception as e:
            QgsMessageLog.logMessage(f'Falha SIG@SC: {e}', 'OrIFSC',
                                     Qgis.MessageLevel.Warning)
            iface.messageBar().pushMessage(
                'OrIFSC',
                'O SIG@SC respondeu, mas o QGIS não conseguiu criar a '
                'camada. Tente novamente pelo menu.',
                level=Qgis.MessageLevel.Critical,
                duration=8)
            return
        iface.messageBar().pushMessage(
            'OrIFSC',
            f'{nome_exibicao} adicionada com sucesso.{aviso_extra}',
            level=Qgis.MessageLevel.Success,
            duration=6)

    tarefa = QgsTask.fromFunction(
        'OrIFSC — consultando o SIG@SC', _descobrir, on_finished=_concluir)
    _TAREFAS.add(tarefa)
    QgsApplication.taskManager().addTask(tarefa)


def abrir_portal() -> None:
    """Abre o portal do SIG@SC no navegador padrão."""
    QDesktopServices.openUrl(QUrl(PORTAL))
