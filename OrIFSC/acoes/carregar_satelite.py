"""Carregar camadas de base XYZ (Satélite Google, OpenStreetMap, ...).

Adiciona uma camada raster XYZ como camada de base, embaixo das demais, e força
a reprojeção on-the-fly + refresh do canvas (correção do problema de "camada
aparece no painel mas o canvas fica em branco").

`adicionar_xyz` é o helper genérico reutilizado por outras bases (ver
`acoes/bases.py`).
"""
from typing import Any, Optional

from qgis.core import QgsRasterLayer, QgsProject, QgsMessageLog, Qgis
from qgis.PyQt.QtWidgets import QMessageBox

from ..i18n import tr

URL_GOOGLE = ('type=xyz&url=https://mt1.google.com/vt/'
              'lyrs%3Ds%26x%3D%7Bx%7D%26y%3D%7By%7D%26z%3D%7Bz%7D&zmax=20&zmin=0')


def adicionar_xyz(
        iface: Any,
        nome: str,
        url: str,
        parent: Any = None) -> Optional[QgsRasterLayer]:
    """Adiciona uma camada raster XYZ (provedor 'wms') como camada de base.

    Retorna a camada criada ou None em caso de erro (já avisa o usuário e
    registra no log da aba OrIFSC).
    """
    layer = QgsRasterLayer(url, nome, 'wms')
    if not layer.isValid():
        erro = (layer.error().message() if layer.error()
                else tr('sem detalhes'))
        QgsMessageLog.logMessage(
            tr('Erro ao carregar "{nome}": {erro}', nome=nome, erro=erro),
            'OrIFSC', Qgis.MessageLevel.Critical)
        if hasattr(iface, 'messageBar'):
            iface.messageBar().pushMessage(
                'OrIFSC',
                tr('Não foi possível carregar {nome}. Verifique sua conexão '
                   'e tente novamente.', nome=nome),
                level=Qgis.MessageLevel.Critical,
                duration=8)
        else:
            QMessageBox.warning(
                parent, nome,
                tr('Não foi possível carregar "{nome}".\n\nErro: {erro}\n\n'
                   'Veja mais em: Exibir → Painéis → Mensagens de Log → aba '
                   'OrIFSC', nome=nome, erro=erro))
        return None

    proj = QgsProject.instance()
    proj.addMapLayer(layer, False)
    root = proj.layerTreeRoot()
    root.insertLayer(len(root.children()), layer)

    canvas = iface.mapCanvas()
    canvas.setDestinationCrs(proj.crs())
    canvas.refreshAllLayers()
    canvas.refresh()
    return layer


def carregar_satelite(iface: Any, parent: Any = None) -> Optional[QgsRasterLayer]:
    """Carrega a imagem de satélite do Google (XYZ) como camada de base."""
    return adicionar_xyz(iface, 'Google Satellite', URL_GOOGLE, parent)
