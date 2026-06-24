"""Camada de Limite.

Cria uma camada 'limite' vazia (polígono) no CRS do projeto e entra em modo de
edição com a ferramenta de adicionar feição ativa, para o usuário desenhar o
contorno da área do mapa.
"""
from qgis.core import (
    QgsVectorLayer, QgsProject, QgsSymbol, QgsSingleSymbolRenderer,
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor

from .comum import projeto_configurado, avisar_projeto_nao_configurado


def criar_limite(iface, parent=None):
    if not projeto_configurado():
        avisar_projeto_nao_configurado(parent)
        return None

    authid = QgsProject.instance().crs().authid()  # ex: EPSG:32722
    limite = QgsVectorLayer(f'Polygon?crs={authid}', 'limite', 'memory')

    # Simbologia: borda vermelha tracejada, sem preenchimento
    simbolo = QgsSymbol.defaultSymbol(limite.geometryType())
    camada = simbolo.symbolLayer(0)
    camada.setStrokeColor(QColor(255, 0, 0))
    camada.setStrokeWidth(0.6)
    camada.setStrokeStyle(Qt.DashLine)
    camada.setBrushStyle(Qt.NoBrush)
    limite.setRenderer(QgsSingleSymbolRenderer(simbolo))

    QgsProject.instance().addMapLayer(limite)

    # Deixa pronta para desenhar o contorno
    iface.setActiveLayer(limite)
    limite.startEditing()
    try:
        iface.actionAddFeature().trigger()
    except Exception:
        pass
    return limite
