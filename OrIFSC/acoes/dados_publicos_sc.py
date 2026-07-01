"""Dados Públicos — Santa Catarina — SIG@SC.

Registra as conexões WMS/WMTS do geoportal SIG@SC (https://sigsc.sc.gov.br/) e
abre o gerenciador de fontes de dados nativo do QGIS na aba WMS/WMTS. Esse
diálogo faz o GetCapabilities de forma ASSÍNCRONA (não trava o QGIS), ao
contrário de baixar o GetCapabilities na thread da interface. O usuário escolhe
a conexão, conecta e adiciona a camada; o QGIS reprojeta on-the-fly para o CRS
do projeto (não fixamos CRS aqui).

Ortofoto via WMTS (tiles, mais rápido); MDT via WMS (imagem de fundo — atenção:
é uma imagem renderizada, não valores de elevação, então NÃO serve para gerar
curvas; para curvas o plugin usa o MDT Copernicus).
"""
from qgis.core import QgsSettings
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtGui import QDesktopServices

URL_WMS = 'http://sigsc.sc.gov.br/sigserver/SIGSC/wms'
URL_WMTS = 'http://sigsc.sc.gov.br/sigserver/gwc/service/wmts'
PORTAL = 'https://sigsc.sc.gov.br/'

# Conexões que o plugin registra no QGIS (nome exibido -> URL do serviço).
_CONEXOES = [
    ('SIG@SC Ortofoto (WMTS)', URL_WMTS),
    ('SIG@SC MDT (WMS)', URL_WMS),
]


def _registrar_conexoes():
    """Grava as conexões WMS/WMTS do SIG@SC nas configurações do QGIS, para
    aparecerem no gerenciador de fontes de dados (aba WMS/WMTS)."""
    s = QgsSettings()
    for nome, url in _CONEXOES:
        base = f'qgis/connections-wms/{nome}'
        s.setValue(f'{base}/url', url)
        s.setValue(f'{base}/dpiMode', 7)           # 7 = All (padrão do QGIS)
        s.setValue(f'{base}/ignoreGetMapURI', False)
        s.setValue(f'{base}/ignoreGetFeatureInfoURI', False)
        s.setValue(f'{base}/smoothPixmapTransform', False)


def adicionar_sigsc(iface, parent=None):
    """Registra as conexões do SIG@SC e abre o gerenciador WMS/WMTS do QGIS.

    O GetCapabilities roda de forma assíncrona no diálogo nativo, então o QGIS
    não trava. A camada adicionada é reprojetada on-the-fly para o CRS do projeto.
    """
    _registrar_conexoes()
    try:
        iface.openDataSourceManager('wms')
    except Exception:
        QMessageBox.information(
            parent, 'SIG@SC',
            'Abra: Camada → Adicionar Camada → Adicionar Camada WMS/WMTS…\n'
            'As conexões "SIG@SC Ortofoto (WMTS)" e "SIG@SC MDT (WMS)" já '
            'estão salvas — escolha, clique em Conectar e adicione a camada.\n\n'
            f'WMTS (ortofoto): {URL_WMTS}\n'
            f'WMS (MDT): {URL_WMS}')


def abrir_portal():
    """Abre o portal do SIG@SC no navegador padrão."""
    QDesktopServices.openUrl(QUrl(PORTAL))
