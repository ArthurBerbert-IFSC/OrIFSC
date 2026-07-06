"""Criação da camada 'folha' (Definir Local e Criar Folha).

Cria a camada 'folha' (retângulo do tamanho real da folha na escala definida no
Passo 2), com borda magenta e sem preenchimento. Chamada pelo diálogo de
Definir Local logo após salvar o retângulo no projeto.
"""
from typing import Any, Optional

from qgis.core import (
    QgsVectorLayer, QgsFeature, QgsGeometry, QgsRectangle, QgsProject,
    QgsSymbol, QgsSingleSymbolRenderer,
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor

from .comum import ler_folha, avisar_projeto_nao_configurado


def criar_folha(iface: Any, parent: Any = None) -> Optional[QgsVectorLayer]:
    """Cria e ativa a camada ``folha`` a partir do estado persistido no projeto.

    Args:
        iface: Interface principal do QGIS.
        parent: Widget pai opcional para mensagens de aviso.

    Returns:
        Optional[QgsVectorLayer]: Camada criada, ou ``None`` quando o projeto não
        está configurado.

    Usa o estado salvo em ``acoes.comum`` para manter regra de negócio central de
    pré-requisito de projeto configurado antes dos fluxos dependentes.
    """
    estado = ler_folha()
    if estado is None:
        avisar_projeto_nao_configurado(parent)
        return None
    epsg, x0, y0, x1, y1 = estado

    folha = QgsVectorLayer(f'Polygon?crs=EPSG:{epsg}', 'folha', 'memory')
    feat = QgsFeature()
    feat.setGeometry(QgsGeometry.fromRect(QgsRectangle(x0, y0, x1, y1)))
    folha.dataProvider().addFeatures([feat])
    folha.updateExtents()

    simbolo = QgsSymbol.defaultSymbol(folha.geometryType())
    simbolo.symbolLayer(0).setStrokeColor(QColor(255, 0, 255))
    simbolo.symbolLayer(0).setStrokeWidth(1.2)
    simbolo.symbolLayer(0).setBrushStyle(Qt.BrushStyle.NoBrush)
    folha.setRenderer(QgsSingleSymbolRenderer(simbolo))

    QgsProject.instance().addMapLayer(folha)

    canvas = iface.mapCanvas()
    canvas.setExtent(QgsRectangle(x0, y0, x1, y1))
    canvas.refresh()
    iface.setActiveLayer(folha)
    return folha
