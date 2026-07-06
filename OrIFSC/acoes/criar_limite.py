"""Camada de Limite.

Cria uma camada 'limite' vazia (polígono) no CRS do projeto e entra em modo de
edição com a ferramenta de adicionar feição ativa, para o usuário desenhar o
contorno da área do mapa.
"""
from typing import Any, Optional

from qgis.core import (
    QgsVectorLayer, QgsProject, QgsSymbol, QgsSingleSymbolRenderer,
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor

from .comum import projeto_configurado, avisar_projeto_nao_configurado


def criar_limite(iface: Any, parent: Any = None) -> Optional[QgsVectorLayer]:
    """Cria camada de limite pronta para digitalização manual.

    Args:
        iface: Interface principal do QGIS.
        parent: Widget pai opcional para mensagens.

    Returns:
        Optional[QgsVectorLayer]: Camada criada, ou ``None`` se o projeto ainda
        não estiver configurado.

    Preserva o pré-requisito de projeto configurado definido nas diretrizes e
    mantém a camada no CRS atual do projeto para evitar inconsistência espacial.
    """
    if not projeto_configurado():
        avisar_projeto_nao_configurado(parent)
        return None

    authid = QgsProject.instance().crs().authid()
    limite = QgsVectorLayer(f'Polygon?crs={authid}', 'limite', 'memory')

    simbolo = QgsSymbol.defaultSymbol(limite.geometryType())
    camada = simbolo.symbolLayer(0)
    camada.setStrokeColor(QColor(255, 0, 0))
    camada.setStrokeWidth(0.6)
    camada.setStrokeStyle(Qt.PenStyle.DashLine)
    camada.setBrushStyle(Qt.BrushStyle.NoBrush)
    limite.setRenderer(QgsSingleSymbolRenderer(simbolo))

    QgsProject.instance().addMapLayer(limite)

    iface.setActiveLayer(limite)
    limite.startEditing()
    try:
        iface.actionAddFeature().trigger()
    except Exception:
        pass
    return limite
