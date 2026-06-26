"""Dados Públicos — Santa Catarina — SIG@SC.

Carrega camadas WMS do geoportal SIG@SC (https://sigsc.sc.gov.br/) direto no
projeto. Os identificadores internos das camadas (<Name>) não são publicados no
site, então são resolvidos em tempo de execução pelo GetCapabilities, casando
pelo Título (mais robusto do que cravar um id que pode mudar). Se a resolução
falhar, o item cai para abrir o portal no navegador.
"""
from ..rede import baixar_bytes

from qgis.core import QgsRasterLayer, QgsProject, QgsMessageLog, Qgis
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.PyQt.QtCore import QUrl, QXmlStreamReader
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


def _parsear_capabilities(dados):
    """Extrai os pares (Name, Title) das camadas do GetCapabilities WMS.

    Usa QXmlStreamReader (Qt) em vez de xml.etree para não expandir entidades/DTD
    externos. Só considera <Name>/<Title> que são filhos diretos de um <Layer>
    (ignorando, p.ex., os <Name>/<Title> de <Style>).
    """
    reader = QXmlStreamReader(dados)
    caps = []
    tags = []      # nomes locais dos elementos abertos
    layers = []    # records [name, title] dos <Layer> abertos (mais interno por último)
    while not reader.atEnd():
        tok = reader.readNext()
        if tok == QXmlStreamReader.TokenType.StartElement:
            tag = str(reader.name())
            if tag in ('Name', 'Title') and tags and tags[-1] == 'Layer' and layers:
                texto = reader.readElementText().strip()  # consome até o </tag>
                if tag == 'Name':
                    layers[-1][0] = texto
                else:
                    layers[-1][1] = texto
                continue  # readElementText já consumiu o elemento
            tags.append(tag)
            if tag == 'Layer':
                rec = [None, None]
                caps.append(rec)
                layers.append(rec)
        elif tok == QXmlStreamReader.TokenType.EndElement:
            tag = str(reader.name())
            if tags:
                tags.pop()
            if tag == 'Layer' and layers:
                layers.pop()
    return [(n, t or '') for n, t in caps if n]


def _carregar_capabilities():
    """Baixa e parseia o GetCapabilities (WMS 1.3.0) -> lista de (Name, Title)."""
    global _cache_caps
    if _cache_caps is not None:
        return _cache_caps
    url = URL_WMS + '?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities'
    _cache_caps = _parsear_capabilities(baixar_bytes(url))
    return _cache_caps


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
