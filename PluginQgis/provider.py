import os
from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsProcessingProvider


class OrIFSCProvider(QgsProcessingProvider):
    def loadAlgorithms(self):
        import sys
        import importlib

        # Força reload dos módulos de algoritmos para desenvolvimento
        for mod_name in list(sys.modules.keys()):
            if mod_name.startswith('PluginQgis.algorithms') or mod_name.startswith('OrIFSC.algorithms'):
                try:
                    importlib.reload(sys.modules[mod_name])
                except Exception:
                    pass

        from .algorithms.gerar_curvas import GerarCurvasNivel
        from .algorithms.exportar_ocad import ExportarOCAD
        self.addAlgorithm(GerarCurvasNivel())
        self.addAlgorithm(ExportarOCAD())

    def id(self):
        return 'oriifsc'

    def name(self):
        return 'OrIFSC'

    def longName(self):
        return 'OrIFSC — Orientação IFSC'

    def icon(self):
        icon_path = os.path.join(os.path.dirname(__file__), 'icons', 'icon.svg')
        return QIcon(icon_path) if os.path.exists(icon_path) else super().icon()
