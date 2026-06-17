from qgis.PyQt.QtWidgets import QAction, QMenu
from qgis.core import QgsApplication
from .provider import OrIFSCProvider


class OrIFSCPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.menu_oriifsc = None
        self.actions = []
        self.provider = None

    def initGui(self):
        # Registra o provider (algoritmos ficam ocultos da Caixa de Ferramentas,
        # acessíveis apenas pelo menu OrIFSC)
        self.provider = OrIFSCProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

        menu_bar = self.iface.mainWindow().menuBar()
        self.menu_oriifsc = QMenu('OrIFSC', self.iface.mainWindow())

        # Insere antes do menu Ajuda
        ajuda = None
        for action in menu_bar.actions():
            m = action.menu()
            if m and m.title().lower() in ('ajuda', 'help', '&ajuda', '&help'):
                ajuda = action
                break
        if ajuda:
            menu_bar.insertMenu(ajuda, self.menu_oriifsc)
        else:
            menu_bar.addMenu(self.menu_oriifsc)

        self._add_action('1 — Carregar Satélite Google', self._carregar_satelite)
        self._add_action('2 — Definir Local e Criar Folha', self._definir_local)
        self._add_action('3 — Camada de Limite', self._criar_limite)
        self.menu_oriifsc.addSeparator()
        self._add_action('4 — Gerar Curvas de Nível', self._gerar_curvas)
        self._add_action('5 — Exportar para o OCAD', self._exportar_ocad)

    def _add_action(self, titulo, slot):
        action = QAction(titulo, self.iface.mainWindow())
        action.triggered.connect(slot)
        self.menu_oriifsc.addAction(action)
        self.actions.append(action)
        return action

    def unload(self):
        if self.menu_oriifsc:
            self.menu_oriifsc.deleteLater()
            self.menu_oriifsc = None
        self.actions.clear()
        if self.provider:
            try:
                QgsApplication.processingRegistry().removeProvider(self.provider)
            except RuntimeError:
                pass
        self.provider = None

    def _definir_local(self):
        from .acoes.definir_local import DialogDefinirLocal
        dlg = DialogDefinirLocal(self.iface, self.iface.mainWindow())
        dlg.exec_()

    def _carregar_satelite(self):
        from .acoes.carregar_satelite import carregar_satelite
        carregar_satelite(self.iface, self.iface.mainWindow())

    def _criar_limite(self):
        from .acoes.criar_limite import criar_limite
        criar_limite(self.iface, self.iface.mainWindow())

    def _gerar_curvas(self):
        import processing
        processing.execAlgorithmDialog('oriifsc:gerar_curvas_nivel', {})

    def _exportar_ocad(self):
        import processing
        processing.execAlgorithmDialog('oriifsc:exportar_ocad', {})
