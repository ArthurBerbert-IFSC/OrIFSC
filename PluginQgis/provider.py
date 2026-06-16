import os
from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsProcessingProvider


class OrIFSCProvider(QgsProcessingProvider):
    def loadAlgorithms(self):
        from .algorithms.preparar_ambiente import PrepararAmbienteOrientacao
        from .algorithms.gerar_curvas import GerarCurvasNivel
        self.addAlgorithm(PrepararAmbienteOrientacao())
        self.addAlgorithm(GerarCurvasNivel())

    def id(self):
        return 'oriifsc'

    def name(self):
        return 'OrIFSC'

    def longName(self):
        return 'OrIFSC — Orientação IFSC'

    def icon(self):
        icon_path = os.path.join(os.path.dirname(__file__), 'icons', 'icon.png')
        return QIcon(icon_path) if os.path.exists(icon_path) else super().icon()
