import os
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMenu, QMessageBox
from qgis.core import QgsApplication
from .provider import OrIFSCProvider

# Sentinela de separador na definição declarativa do menu.
SEP = object()

ICONS_DIR = os.path.join(os.path.dirname(__file__), 'icons')


def _icone(nome):
    """QIcon do arquivo em icons/, ou QIcon() vazio se não houver nome."""
    return QIcon(os.path.join(ICONS_DIR, nome)) if nome else QIcon()


class OrIFSCPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.menu_orifsc = None
        self.actions = []
        self.acoes_por_id = {}     # id lógico -> QAction (etapas do fluxo)
        self._titulos_base = {}    # id lógico -> título sem prefixo de status
        self.provider = None

    # ------------------------------------------------------------------ GUI
    def initGui(self):
        # Registra o provider (algoritmos ficam ocultos da Caixa de Ferramentas,
        # acessíveis apenas pelo menu OrIFSC)
        self.provider = OrIFSCProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

        menu_bar = self.iface.mainWindow().menuBar()
        self.menu_orifsc = QMenu('OrIFSC', self.iface.mainWindow())

        # Insere antes do menu Ajuda
        ajuda = None
        for action in menu_bar.actions():
            m = action.menu()
            if m and m.title().lower() in ('ajuda', 'help', '&ajuda', '&help'):
                ajuda = action
                break
        if ajuda:
            menu_bar.insertMenu(ajuda, self.menu_orifsc)
        else:
            menu_bar.addMenu(self.menu_orifsc)

        self._construir_menu(self.menu_orifsc, self._definicao_menu())

        # Guia suave: ao abrir o menu, marca etapas concluídas (✓) e a próxima
        # sugerida (▶), sem desabilitar nada — o fluxo é intuitivo, não
        # obrigatório.
        self.menu_orifsc.aboutToShow.connect(self._atualizar_status_menu)

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
                {'titulo': 'Definir Local e Criar Folha',
                 'slot': self._definir_local,
                 'icone': 'definir_local.svg',
                 'id': 'definir_local'},
                {'titulo': 'Camada de Limite',
                 'slot': self._criar_limite,
                 'icone': 'criar_limite.svg'},
            ]},
            {'titulo': 'Bases / Camadas de Fundo', 'itens': [
                {'titulo': 'Satélite Google',
                 'slot': self._carregar_satelite,
                 'icone': 'satelite.svg'},
                {'titulo': 'OpenStreetMap',
                 'slot': self._base_osm,
                 'icone': 'osm.svg'},
                {'titulo': 'Adicionar WMS/WMTS…',
                    'slot': self._base_wms, 'icone': 'wms.svg'},
            ]},
            {'titulo': 'Importar', 'itens': [
                {'titulo': 'Importar KML / GPX…',
                    'slot': self._importar_kml_gpx, 'icone': ''},
            ]},
            {'titulo': 'Relevo', 'itens': [
                {'titulo': 'Gerar Curvas de Nível', 'slot': self._gerar_curvas,
                    'icone': 'curvas.svg', 'id': 'gerar_curvas'},
                {'titulo': 'Fonte de DEM: FABDEM (em breve)', 'slot': None,
                 'habilitado': False, 'icone': 'dem.svg'},
            ]},
            {'titulo': 'Dados Públicos', 'itens': [
                {'titulo': 'Santa Catarina', 'itens': [
                    {'titulo': 'Adicionar camadas do SIG@SC '
                               '(Ortofoto WMTS / MDT WMS)…',
                        'slot': self._sigsc_adicionar,
                        'icone': 'ortofoto.svg'},
                    {'titulo': 'Abrir portal SIG@SC…',
                        'slot': self._abrir_sigsc, 'icone': 'portal.svg'},
                ]},
            ]},
            {'titulo': 'Exportar', 'itens': [
                {'titulo': 'Gerar Projeto OCAD / OOM…',
                 'slot': self._exportar_ocad,
                 'icone': 'exportar.svg',
                 'id': 'exportar'},
            ]},
            SEP,
            {'titulo': 'Configurações…',
             'slot': self._configuracoes,
             'icone': 'config.svg'},
            {'titulo': 'Ajuda / Sobre', 'itens': [
                {'titulo': 'Documentação',
                 'slot': self._documentacao,
                 'icone': 'doc.svg'},
                {'titulo': 'Sobre o OrIFSC',
                 'slot': self._sobre,
                 'icone': 'sobre.svg'},
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
                act = QAction(
                    _icone(
                        it.get('icone')),
                    it['titulo'],
                    self.iface.mainWindow())
                slot = it.get('slot')
                if slot is not None:
                    act.triggered.connect(slot)
                act.setEnabled(it.get('habilitado', True) and slot is not None)
                menu.addAction(act)
                self.actions.append(act)
                aid = it.get('id')
                if aid:
                    self.acoes_por_id[aid] = act
                    self._titulos_base[aid] = it['titulo']

    def _atualizar_status_menu(self):
        """Marca as etapas-chave do fluxo: ✓ concluída, ▶ próxima sugerida.

        Não altera o que está habilitado — todos os itens seguem clicáveis. É só
        um guia visual, recalculado a cada abertura do menu a partir do estado
        atual do projeto (folha definida? já há curvas?)."""
        from .acoes.comum import projeto_configurado, tem_camada_curvas
        definido = projeto_configurado()
        tem_curvas = tem_camada_curvas()
        if not definido:
            proximo = 'definir_local'
        elif not tem_curvas:
            proximo = 'gerar_curvas'
        else:
            proximo = 'exportar'
        feito = {'definir_local': definido, 'gerar_curvas': tem_curvas}
        for aid, act in self.acoes_por_id.items():
            base = self._titulos_base.get(aid, act.text())
            if feito.get(aid):
                act.setText('✓  ' + base)      # ✓ etapa concluída
            elif aid == proximo:
                act.setText('▶  ' + base)      # ▶ próxima sugerida
            else:
                act.setText(base)

    def unload(self):
        if self.menu_orifsc:
            # Deletar o QMenu raiz remove submenus e ações filhas.
            self.menu_orifsc.deleteLater()
            self.menu_orifsc = None
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
        dlg.exec()

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

    def _importar_kml_gpx(self):
        from .acoes.importar_kml_gpx import DialogImportarKmlGpx
        dlg = DialogImportarKmlGpx(self.iface, self.iface.mainWindow())
        dlg.exec()

    def _gerar_curvas(self):
        # Curvas precisam de uma camada de área (polígono) que defina a extensão.
        # Não é trava de ordem: qualquer polígono serve; mas sem nenhum o diálogo
        # não teria como rodar — então avisamos de forma clara.
        from .acoes.comum import camadas_poligono
        if not camadas_poligono():
            QMessageBox.information(
                self.iface.mainWindow(), 'OrIFSC',
                'Para gerar curvas é preciso uma camada de área (polígono) que '
                'defina a extensão do terreno.\n\nO caminho mais fácil é rodar '
                'antes "Definir Local e Criar Folha" (ou "Camada de Limite"). '
                'Você também pode usar qualquer camada de polígono já carregada.')
            return
        import processing
        processing.execAlgorithmDialog('orifsc:gerar_curvas_nivel', {})

    def _sigsc_adicionar(self):
        from .acoes.dados_publicos_sc import adicionar_sigsc
        adicionar_sigsc(self.iface, self.iface.mainWindow())

    def _abrir_sigsc(self):
        from .acoes.dados_publicos_sc import abrir_portal
        abrir_portal()

    def _exportar_ocad(self):
        from qgis.core import QgsProject
        from .acoes.comum import (projeto_configurado,
                                  avisar_projeto_nao_configurado, camada_curvas)
        from .acoes.configuracoes import ler_pasta_saida
        # Exportar depende mesmo de folha/escala/CRS; sem isso o projeto OCAD não
        # pode ser montado. Avisa de forma amigável em vez do erro do
        # Processing.
        if not projeto_configurado():
            avisar_projeto_nao_configurado(self.iface.mainWindow())
            return

        # Pré-preenche o diálogo: camada da folha, curvas e pasta de saída
        # padrão.
        params = {}
        folhas = QgsProject.instance().mapLayersByName('folha')
        if folhas:
            params['FOLHA'] = folhas[0].id()
        curvas = camada_curvas()
        if curvas is not None:
            params['CURVAS'] = curvas.id()
        pasta = ler_pasta_saida()
        if pasta:
            params['PASTA'] = pasta

        import processing
        processing.execAlgorithmDialog('orifsc:exportar_ocad', params)

    def _configuracoes(self):
        from .acoes.configuracoes import DialogConfiguracoes
        dlg = DialogConfiguracoes(self.iface.mainWindow())
        dlg.exec()

    def _documentacao(self):
        from .acoes.ajuda import abrir_documentacao
        abrir_documentacao()

    def _sobre(self):
        from .acoes.ajuda import sobre
        sobre(self.iface.mainWindow())
