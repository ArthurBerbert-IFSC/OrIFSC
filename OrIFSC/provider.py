"""Provider de algoritmos Processing do plugin OrIFSC."""

import os
from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsProcessingProvider


class OrIFSCProvider(QgsProcessingProvider):
    """Registra os algoritmos Processing do OrIFSC."""

    def loadAlgorithms(self) -> None:
        """Carrega os algoritmos exportados pelo plugin."""
        if os.environ.get('ORIFSC_DEV'):
            import sys
            import importlib
            for mod_name in list(sys.modules.keys()):
                if mod_name.startswith('PluginQgis.algorithms') or mod_name.startswith(
                        'OrIFSC.algorithms'):
                    try:
                        importlib.reload(sys.modules[mod_name])
                    except Exception:
                        pass

        from .algorithms.gerar_curvas import GerarCurvasNivel
        from .algorithms.exportar_ocad import ExportarOCAD
        self.addAlgorithm(GerarCurvasNivel())
        self.addAlgorithm(ExportarOCAD())

    def id(self) -> str:
        """Identificador estável do provider no registro do Processing.

        Returns:
            str: ID curto usado em nomes de algoritmo (``orifsc:*``).
        """
        return 'orifsc'

    def name(self) -> str:
        """Nome curto exibido para o provider.

        Returns:
            str: Nome amigável do provider.
        """
        return 'OrIFSC'

    def longName(self) -> str:
        """Nome completo exibido pelo QGIS em listagens de providers.

        Returns:
            str: Nome descritivo do plugin.
        """
        return 'OrIFSC — Orientação IFSC'

    def icon(self) -> QIcon:
        """Ícone do provider com fallback para o ícone padrão do QGIS.

        Returns:
            QIcon: Ícone do provider.
        """
        icon_path = os.path.join(
            os.path.dirname(__file__), 'icons', 'icon.svg')
        return QIcon(icon_path) if os.path.exists(
            icon_path) else super().icon()
