import os
from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsApplication
from .provider import OrIFSCProvider


class OrIFSCPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.provider = None
        self.action = None

    def initProcessing(self):
        self.provider = OrIFSCProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def initGui(self):
        self.initProcessing()
        icon_path = os.path.join(os.path.dirname(__file__), 'icons', 'icon.png')
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()
        self.action = QAction(icon, 'OrIFSC — Criar Mapa de Orientação', self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu('OrIFSC', self.action)

    def unload(self):
        self.iface.removePluginMenu('OrIFSC', self.action)
        self.iface.removeToolBarIcon(self.action)
        if self.provider:
            QgsApplication.processingRegistry().removeProvider(self.provider)

    def run(self):
        from .wizard import OrIFSCWizard
        wizard = OrIFSCWizard(self.iface, self.iface.mainWindow())
        wizard.show()
