"""Plugin principal do OrIFSC: menu, ações e integração com Processing."""

import os
from typing import Any, Dict, List, Optional
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMenu
from qgis.core import QgsApplication, Qgis
from .provider import OrIFSCProvider

SEP = object()

ICONS_DIR = os.path.join(os.path.dirname(__file__), 'icons')


def _icone(nome: str) -> QIcon:
    """QIcon do arquivo em icons/, ou QIcon() vazio se não houver nome."""
    return QIcon(os.path.join(ICONS_DIR, nome)) if nome else QIcon()


class OrIFSCPlugin:
    """Controla o ciclo de vida do plugin e o menu OrIFSC no QGIS."""

    def __init__(self, iface: Any) -> None:
        """Inicializa estado da casca de UI do plugin.

        Args:
            iface: Interface do QGIS injetada pelo carregador de plugins.

        Mantém referências das ações e títulos-base para atualizar o menu sem
        duplicar lógica entre módulos, conforme a arquitetura centralizada em
        ``orifsc.py`` definida nas diretrizes.
        """
        self.iface = iface
        self.menu_orifsc: Optional[QMenu] = None
        self.actions: List[QAction] = []
        self.acoes_por_id: Dict[str, QAction] = {}
        self._titulos_base: Dict[str, str] = {}
        self.provider: Optional[OrIFSCProvider] = None

    def initGui(self) -> None:
        """Inicializa provider, constrói o menu e conecta atualização de status."""
        self.provider = OrIFSCProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

        menu_bar = self.iface.mainWindow().menuBar()
        self.menu_orifsc = QMenu('OrIFSC', self.iface.mainWindow())

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

        self.menu_orifsc.aboutToShow.connect(self._atualizar_status_menu)

    def _definicao_menu(self) -> List[Any]:
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

    def _construir_menu(self, menu: QMenu, itens: List[Any]) -> None:
        """Monta recursivamente um QMenu a partir da definição declarativa."""
        for it in itens:
            if it is SEP:
                menu.addSeparator()
            elif 'itens' in it:
                sub = menu.addMenu(it['titulo'])
                self._construir_menu(sub, it['itens'])
            else:
                # Parent no próprio menu (não no mainWindow): o deleteLater()
                # do menu em unload() remove as ações em cascata, sem QAction
                # órfã acumulando entre recargas do plugin.
                act = QAction(_icone(it.get('icone')), it['titulo'], menu)
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

    def _atualizar_status_menu(self) -> None:
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
                act.setText('✓  ' + base)
            elif aid == proximo:
                act.setText('▶  ' + base)
            else:
                act.setText(base)

    def unload(self) -> None:
        """Remove menu, ações e provider de Processing ao descarregar.

        As ações são parenteadas no menu, então o deleteLater() do menu
        remove tudo em cascata — sem referências órfãs entre recargas.
        """
        if self.menu_orifsc:
            self.menu_orifsc.deleteLater()
            self.menu_orifsc = None
        self.actions.clear()
        self.acoes_por_id.clear()
        self._titulos_base.clear()
        if self.provider:
            try:
                QgsApplication.processingRegistry().removeProvider(self.provider)
            except RuntimeError:
                pass
        self.provider = None

    def _definir_local(self) -> None:
        """Abre o diálogo de definição de local e criação da folha.

        O import é tardio para preservar tempo de carregamento inicial da casca
        de UI, padrão recomendado nas diretrizes.
        """
        from .acoes.definir_local import DialogDefinirLocal
        dlg = DialogDefinirLocal(self.iface, self.iface.mainWindow())
        dlg.exec()

    def _criar_limite(self) -> None:
        """Cria a camada de limite do projeto atual.
        """
        from .acoes.criar_limite import criar_limite
        criar_limite(self.iface, self.iface)

    def _carregar_satelite(self) -> None:
        """Carrega a base de satélite no projeto.
        """
        from .acoes.carregar_satelite import carregar_satelite
        layer = carregar_satelite(self.iface, self.iface)
        if layer is not None:
            self.iface.messageBar().pushMessage(
                'OrIFSC',
                'Satélite carregado com sucesso.',
                level=Qgis.MessageLevel.Success,
                duration=4)

    def _base_osm(self) -> None:
        """Carrega a base OpenStreetMap no projeto.
        """
        from .acoes.bases import adicionar_osm
        layer = adicionar_osm(self.iface, self.iface)
        if layer is not None:
            self.iface.messageBar().pushMessage(
                'OrIFSC',
                'OpenStreetMap carregado com sucesso.',
                level=Qgis.MessageLevel.Success,
                duration=4)

    def _base_wms(self) -> None:
        """Abre o gerenciador nativo WMS/WMTS do QGIS.
        """
        from .acoes.bases import abrir_gerenciador_wms
        abriu = abrir_gerenciador_wms(self.iface, self.iface)
        if abriu:
            self.iface.messageBar().pushMessage(
                'OrIFSC',
                'Gerenciador WMS/WMTS aberto.',
                level=Qgis.MessageLevel.Success,
                duration=4)

    def _importar_kml_gpx(self) -> None:
        """Abre o diálogo de importação KML/GPX.
        """
        from .acoes.importar_kml_gpx import DialogImportarKmlGpx
        dlg = DialogImportarKmlGpx(self.iface, self.iface.mainWindow())
        dlg.exec()

    def _gerar_curvas(self) -> None:
        """Abre o diálogo de curvas quando há pelo menos uma camada poligonal."""
        from .acoes.comum import camadas_poligono
        if not camadas_poligono():
            self.iface.messageBar().pushMessage(
                'OrIFSC',
                'Para gerar curvas, adicione primeiro uma camada poligonal que '
                'delimite a área de trabalho. Você pode usar "Definir Local e '
                'Criar Folha" ou "Camada de Limite".',
                level=Qgis.MessageLevel.Warning,
                duration=8)
            return
        import processing
        processing.execAlgorithmDialog('orifsc:gerar_curvas_nivel', {})

    def _sigsc_adicionar(self) -> None:
        """Executa o fluxo guiado de dados públicos do SIG@SC.
        """
        from .acoes.dados_publicos_sc import adicionar_sigsc
        adicionar_sigsc(self.iface, self.iface.mainWindow())

    def _abrir_sigsc(self) -> None:
        """Abre o portal SIG@SC no navegador padrão.
        """
        from .acoes.dados_publicos_sc import abrir_portal
        abrir_portal()

    def _exportar_ocad(self) -> None:
        """Abre o diálogo de exportação OCAD/OOM com pré-preenchimento.

        As diretrizes exigem projeto configurado e CRS UTM/WGS84 antes de
        exportar; por isso o fluxo valida estado em ``acoes.comum`` antes de
        abrir o algoritmo.
        """
        from qgis.core import QgsProject
        from .acoes.comum import (projeto_configurado,
                                  avisar_projeto_nao_configurado, camada_curvas)
        from .acoes.configuracoes import ler_pasta_saida
        if not projeto_configurado():
            avisar_projeto_nao_configurado(self.iface)
            return

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

    def _configuracoes(self) -> None:
        """Abre o diálogo de configurações globais.
        """
        from .acoes.configuracoes import DialogConfiguracoes
        dlg = DialogConfiguracoes(self.iface.mainWindow())
        dlg.exec()

    def _documentacao(self) -> None:
        """Abre a documentação principal do plugin.
        """
        from .acoes.ajuda import abrir_documentacao
        abrir_documentacao()

    def _sobre(self) -> None:
        """Abre a janela "Sobre" do plugin.
        """
        from .acoes.ajuda import sobre
        sobre(self.iface.mainWindow())
