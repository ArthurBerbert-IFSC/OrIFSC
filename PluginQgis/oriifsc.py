from qgis.PyQt.QtWidgets import QAction, QMenu
from qgis.core import QgsApplication
from .provider import OrIFSCProvider

# Sentinela de separador na definição declarativa do menu.
SEP = object()


class OrIFSCPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.menu_oriifsc = None
        self.actions = []
        self.provider = None

    # ------------------------------------------------------------------ GUI
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

        self._construir_menu(self.menu_oriifsc, self._definicao_menu())

    def _definicao_menu(self):
        """Estrutura declarativa do menu. Para adicionar uma função, basta
        incluir um dict aqui e escrever o slot correspondente.

        Nós:
          - ação:     {'titulo': str, 'slot': callable}
          - submenu:  {'titulo': str, 'itens': [...]}
          - separador: SEP
          - placeholder: ação com 'slot' ausente/None ('habilitado' opcional)
        """
        return [
            {'titulo': 'Início', 'itens': [
                {'titulo': 'Definir Local e Criar Folha', 'slot': self._definir_local},
                {'titulo': 'Camada de Limite', 'slot': self._criar_limite},
            ]},
            {'titulo': 'Bases / Camadas de Fundo', 'itens': [
                {'titulo': 'Satélite Google', 'slot': self._carregar_satelite},
                {'titulo': 'OpenStreetMap', 'slot': self._base_osm},
                {'titulo': 'Adicionar WMS/WMTS…', 'slot': self._base_wms},
            ]},
            {'titulo': 'Relevo', 'itens': [
                {'titulo': 'Gerar Curvas de Nível', 'slot': self._gerar_curvas},
                {'titulo': 'Fonte de DEM: FABDEM (em breve)', 'slot': None,
                 'habilitado': False},
            ]},
            {'titulo': 'Dados Públicos', 'itens': [
                {'titulo': 'Santa Catarina', 'itens': [
                    {'titulo': 'SIG@SC — Ortofotomosaico RGB', 'slot': self._sigsc_ortofoto},
                    {'titulo': 'SIG@SC — Modelo Digital de Terreno (MDT)', 'slot': self._sigsc_mdt},
                    {'titulo': 'Abrir portal SIG@SC…', 'slot': self._abrir_sigsc},
                ]},
            ]},
            {'titulo': 'Exportar', 'itens': [
                {'titulo': 'Exportar para o OCAD', 'slot': self._exportar_ocad},
            ]},
            SEP,
            {'titulo': 'Configurações…', 'slot': self._configuracoes},
            {'titulo': 'Ajuda / Sobre', 'itens': [
                {'titulo': 'Documentação', 'slot': self._documentacao},
                {'titulo': 'Sobre o OrIFSC', 'slot': self._sobre},
            ]},
        ]

    def _construir_menu(self, menu, itens):
        """Monta recursivamente um QMenu a partir da definição declarativa."""
        for it in itens:
            if it is SEP:
                menu.addSeparator()
            elif 'itens' in it:
                sub = menu.addMenu(it['titulo'])
                self._construir_menu(sub, it['itens'])
            else:
                act = QAction(it['titulo'], self.iface.mainWindow())
                slot = it.get('slot')
                if slot is not None:
                    act.triggered.connect(slot)
                act.setEnabled(it.get('habilitado', True) and slot is not None)
                menu.addAction(act)
                self.actions.append(act)

    def unload(self):
        if self.menu_oriifsc:
            # Deletar o QMenu raiz remove submenus e ações filhas.
            self.menu_oriifsc.deleteLater()
            self.menu_oriifsc = None
        self.actions.clear()
        if self.provider:
            try:
                QgsApplication.processingRegistry().removeProvider(self.provider)
            except RuntimeError:
                pass
        self.provider = None

    # --------------------------------------------------------------- slots
    def _definir_local(self):
        from .acoes.definir_local import DialogDefinirLocal
        dlg = DialogDefinirLocal(self.iface, self.iface.mainWindow())
        dlg.exec_()

    def _criar_limite(self):
        from .acoes.criar_limite import criar_limite
        criar_limite(self.iface, self.iface.mainWindow())

    def _carregar_satelite(self):
        from .acoes.carregar_satelite import carregar_satelite
        carregar_satelite(self.iface, self.iface.mainWindow())

    def _base_osm(self):
        from .acoes.bases import adicionar_osm
        adicionar_osm(self.iface, self.iface.mainWindow())

    def _base_wms(self):
        from .acoes.bases import abrir_gerenciador_wms
        abrir_gerenciador_wms(self.iface, self.iface.mainWindow())

    def _gerar_curvas(self):
        import processing
        processing.execAlgorithmDialog('oriifsc:gerar_curvas_nivel', {})

    def _sigsc_ortofoto(self):
        from .acoes.dados_publicos_sc import adicionar_wms
        adicionar_wms(self.iface, 'ortofoto', self.iface.mainWindow())

    def _sigsc_mdt(self):
        from .acoes.dados_publicos_sc import adicionar_wms
        adicionar_wms(self.iface, 'mdt', self.iface.mainWindow())

    def _abrir_sigsc(self):
        from .acoes.dados_publicos_sc import abrir_portal
        abrir_portal()

    def _exportar_ocad(self):
        import processing
        processing.execAlgorithmDialog('oriifsc:exportar_ocad', {})

    def _configuracoes(self):
        from .acoes.configuracoes import DialogConfiguracoes
        dlg = DialogConfiguracoes(self.iface.mainWindow())
        dlg.exec_()

    def _documentacao(self):
        from .acoes.ajuda import abrir_documentacao
        abrir_documentacao()

    def _sobre(self):
        from .acoes.ajuda import sobre
        sobre(self.iface.mainWindow())
