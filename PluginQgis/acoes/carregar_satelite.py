"""Passo 1 — Carregar Satélite Google.

Adiciona a imagem de satélite do Google (XYZ) como camada de base, embaixo das
demais, e força a reprojeção on-the-fly + refresh do canvas (correção do
problema de "camada aparece no painel mas o canvas fica em branco").
"""
from qgis.core import QgsRasterLayer, QgsProject, QgsMessageLog, Qgis
from qgis.PyQt.QtWidgets import QMessageBox

URL_GOOGLE = ('type=xyz&url=https://mt1.google.com/vt/'
              'lyrs%3Ds%26x%3D%7Bx%7D%26y%3D%7By%7D%26z%3D%7Bz%7D&zmax=20&zmin=0')


def carregar_satelite(iface, parent=None):
    google = QgsRasterLayer(URL_GOOGLE, 'Google Satellite', 'wms')
    if not google.isValid():
        erro = google.error().message() if google.error() else 'sem detalhes'
        QgsMessageLog.logMessage(f'Erro ao carregar Google Satellite: {erro}',
                                 'OrIFSC', Qgis.Critical)
        QMessageBox.warning(parent, 'Google Satellite',
                            'Não foi possível carregar o satélite.\n\n'
                            f'Erro: {erro}\n\n'
                            'Veja mais em: Exibir → Painéis → Mensagens de Log → aba OrIFSC')
        return None

    proj = QgsProject.instance()
    # Adiciona sem ir para o topo da árvore e insere embaixo (camada de base)
    proj.addMapLayer(google, False)
    root = proj.layerTreeRoot()
    root.insertLayer(len(root.children()), google)

    # Garante que o canvas reprojeta (UTM <-> 3857) e redesenha — sem isso a
    # camada aparece no painel mas o canvas pode ficar em branco.
    canvas = iface.mapCanvas()
    canvas.setDestinationCrs(proj.crs())
    canvas.refreshAllLayers()
    canvas.refresh()
    return google
