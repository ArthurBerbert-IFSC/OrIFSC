"""Bases / Camadas de Fundo.

Bases adicionais além do Satélite Google (que vive em `carregar_satelite.py`):
OpenStreetMap (XYZ) e o atalho para o gerenciador de fontes WMS/WMTS nativo do
QGIS, onde o usuário pode colar a URL de qualquer serviço.
"""
from qgis.core import QgsMessageLog, Qgis
from qgis.PyQt.QtWidgets import QMessageBox

from .carregar_satelite import adicionar_xyz

URL_OSM = ('type=xyz&url=https://tile.openstreetmap.org/'
           '%7Bz%7D/%7Bx%7D/%7By%7D.png&zmax=19&zmin=0')


def adicionar_osm(iface, parent=None):
    """Adiciona o OpenStreetMap (XYZ) como camada de base."""
    return adicionar_xyz(iface, 'OpenStreetMap', URL_OSM, parent)


def abrir_gerenciador_wms(iface, parent=None):
    """Abre o Gerenciador de Fontes de Dados do QGIS na aba WMS/WMTS, para o
    usuário adicionar qualquer serviço colando a URL."""
    try:
        iface.openDataSourceManager('wms')
    except Exception as e:
        QgsMessageLog.logMessage(f'Falha ao abrir o gerenciador WMS: {e}',
                                 'OrIFSC', Qgis.Warning)
        QMessageBox.information(
            parent, 'Adicionar WMS/WMTS',
            'Abra manualmente em: Camada → Adicionar Camada → '
            'Adicionar Camada WMS/WMTS…')
