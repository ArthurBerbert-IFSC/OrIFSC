"""Dados Públicos — Santa Catarina — SIG@SC.

Carrega camadas WMS do geoportal SIG@SC (https://sigsc.sc.gov.br/) direto no
projeto. Os identificadores internos das camadas (<Name>) não são publicados no
site, então são resolvidos em tempo de execução pelo GetCapabilities, casando
pelo Título (mais robusto do que cravar um id que pode mudar). Se a resolução
falhar, o item cai para abrir o portal no navegador.
"""
import urllib.request
import xml.etree.ElementTree as ET

from qgis.core import QgsRasterLayer, QgsProject, QgsMessageLog, Qgis
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtGui import QDesktopServices

URL_WMS = 'http://sigsc.sc.gov.br/sigserver/SIGSC/wms'
URL_WMTS = 'http://sigsc.sc.gov.br/sigserver/gwc/service/wmts'
CRS_SC = 'EPSG:31982'  # SIRGAS 2000 / UTM 22S
PORTAL = 'https://sigsc.sc.gov.br/'

# chave -> (nome amigável da camada no projeto, substrings procuradas no Title)
ALVOS = {
    'ortofoto': ('SIG@SC — Ortofotomosaico RGB', ('ortofotomosaico', 'ortofoto')),
    'mdt': ('SIG@SC — Modelo Digital de Terreno (MDT)', ('modelo digital de terreno', 'mdt')),
    # 'mds': ('SIG@SC — Modelo Digital de Superfície (MDS)', ('modelo digital de superf', 'mds')),  # reservado
    # 'hidro': ('SIG@SC — Hidrografia (ANA)', ('hidrografia', 'curso')),                            # reservado
}

_cache_caps = None  # lista de (name, title) — cacheada por sessão


def _carregar_capabilities(timeout=25):
    """Baixa e parseia o GetCapabilities (WMS 1.3.0) -> lista de (Name, Title)."""
    global _cache_caps
    if _cache_caps is not None:
        return _cache_caps
    url = URL_WMS + '?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities'
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        dados = resp.read()
    root = ET.fromstring(dados)
    caps = []
    for elem in root.iter():
        if not elem.tag.endswith('Layer'):
            continue
        name = title = None
        for filho in elem:
            tag = filho.tag.rsplit('}', 1)[-1]
            if tag == 'Name':
                name = (filho.text or '').strip()
            elif tag == 'Title':
                title = (filho.text or '').strip()
        if name:
            caps.append((name, title or ''))
    _cache_caps = caps
    return caps


def _resolver_layer(chave):
    """Retorna o <Name> da camada WMS cujo Título casa com os alvos, ou None."""
    _, titulos = ALVOS[chave]
    for name, title in _carregar_capabilities():
        t = title.lower()
        if any(s in t for s in titulos):
            return name
    return None


def adicionar_wms(iface, chave, parent=None):
    """Adiciona uma camada WMS do SIG@SC ao projeto (como camada de base)."""
    nome, _ = ALVOS[chave]
    try:
        layer_name = _resolver_layer(chave)
    except Exception as e:
        QgsMessageLog.logMessage(f'GetCapabilities SIG@SC falhou: {e}',
                                 'OrIFSC', Qgis.Warning)
        layer_name = None

    if not layer_name:
        QMessageBox.warning(
            parent, 'SIG@SC',
            f'Não foi possível identificar a camada "{nome}" automaticamente.\n'
            'Abrindo o portal do SIG@SC no navegador...')
        abrir_portal()
        return None

    uri = (f'crs={CRS_SC}&format=image/png&layers={layer_name}'
           f'&styles=&url={URL_WMS}')
    layer = QgsRasterLayer(uri, nome, 'wms')
    if not layer.isValid():
        erro = layer.error().message() if layer.error() else 'sem detalhes'
        QgsMessageLog.logMessage(f'Erro ao carregar "{nome}": {erro}',
                                 'OrIFSC', Qgis.Critical)
        QMessageBox.warning(parent, nome,
                            f'Não foi possível carregar "{nome}".\n\n'
                            f'Erro: {erro}\n\n'
                            'Veja mais em: Exibir → Painéis → Mensagens de Log → aba OrIFSC')
        return None

    proj = QgsProject.instance()
    proj.addMapLayer(layer, False)
    root = proj.layerTreeRoot()
    root.insertLayer(len(root.children()), layer)  # como camada de base
    iface.mapCanvas().refresh()
    return layer


def abrir_portal():
    """Abre o portal do SIG@SC no navegador padrão."""
    QDesktopServices.openUrl(QUrl(PORTAL))
