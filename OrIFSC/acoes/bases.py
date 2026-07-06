"""Bases / Camadas de Fundo.

Bases adicionais além do Satélite Google (que vive em `carregar_satelite.py`):
OpenStreetMap (XYZ) e o atalho para o gerenciador de fontes WMS/WMTS nativo do
QGIS, onde o usuário pode colar a URL de qualquer serviço.
"""
from typing import Any

from qgis.core import QgsMessageLog, Qgis
from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtWidgets import QMessageBox

from .carregar_satelite import adicionar_xyz

URL_OSM = ('type=xyz&url=https://tile.openstreetmap.org/'
           '%7Bz%7D/%7Bx%7D/%7By%7D.png&zmax=19&zmin=0')


def adicionar_osm(iface: Any, parent: Any = None):
    """Adiciona o OpenStreetMap (XYZ) como camada de base."""
    return adicionar_xyz(iface, 'OpenStreetMap', URL_OSM, parent)


def abrir_gerenciador_wms(iface: Any, parent: Any = None) -> bool:
    """Abre o Gerenciador de Fontes de Dados do QGIS na aba WMS/WMTS, para o
    usuário adicionar qualquer serviço colando a URL."""
    try:
        if hasattr(iface, 'openDataSourceManagerPage'):
            iface.openDataSourceManagerPage('wms')
            return True
    except Exception:
        pass

    try:
        iface.openDataSourceManager('wms')
        return True
    except Exception:
        pass

    try:
        iface.openDataSourceManager()
        return True
    except Exception:
        pass

    try:
        main = iface.mainWindow()
        acao = main.findChild(QAction, 'mActionAddWmsLayer')
        if acao is not None:
            acao.trigger()
            return True
    except Exception:
        pass

    try:
        iface.actionAddWmsLayer().trigger()
        return True
    except Exception as e:
        QgsMessageLog.logMessage(f'Falha ao abrir o gerenciador WMS: {e}',
                                 'OrIFSC', Qgis.MessageLevel.Warning)
        if hasattr(iface, 'messageBar'):
            iface.messageBar().pushMessage(
                'OrIFSC',
                'Não foi possível abrir o gerenciador WMS/WMTS. Use o menu '
                'de camadas do QGIS para abrir a opção manualmente.',
                level=Qgis.MessageLevel.Warning,
                duration=8)
        else:
            QMessageBox.information(
                parent, 'Adicionar WMS/WMTS',
                'Abra manualmente em: Camada → Adicionar Camada → '
                'Adicionar Camada WMS/WMTS…')
        return False
