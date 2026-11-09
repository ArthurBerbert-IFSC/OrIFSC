"""Plugin principal do OrIFSC: menu, ações e integração com Processing."""

import os
from typing import Any, Dict, List, Optional
from qgis.PyQt.QtCore import QTimer
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMenu
from qgis.core import QgsApplication, Qgis
from .i18n import tr
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
        self._criar_menu()

    def _criar_menu(self, antes: Optional[QAction] = None) -> None:
        """Cria o menu OrIFSC na barra do QGIS, no idioma ativo do plugin.

        Fica antes de ``antes`` (posição anterior, ao reconstruir) ou, na
        primeira vez, antes do menu Ajuda do QGIS.
        """
        menu_bar = self.iface.mainWindow().menuBar()
        self.menu_orifsc = QMenu('OrIFSC', self.iface.mainWindow())

        if antes is None:
            for action in menu_bar.actions():
                m = action.menu()
                if m and m.title().replace('&', '').lower() in (
                        'ajuda', 'help', 'yardım'):
                    antes = action
                    break
        if antes is not None:
            menu_bar.insertMenu(antes, self.menu_orifsc)
        else:
            menu_bar.addMenu(self.menu_orifsc)

        self._construir_menu(self.menu_orifsc, self._definicao_menu())
        self._construir_menu_idioma(self.menu_orifsc)

        self.menu_orifsc.aboutToShow.connect(self._atualizar_status_menu)

    def _reconstruir_menu(self) -> None:
        """Recria o menu no mesmo lugar da barra — usado ao trocar o idioma,
        já que os títulos são traduzidos na construção."""
        antes = None
        if self.menu_orifsc is not None:
            menu_bar = self.iface.mainWindow().menuBar()
            acoes = menu_bar.actions()
            mact = self.menu_orifsc.menuAction()
            if mact in acoes:
                i = acoes.index(mact)
                if i + 1 < len(acoes):
                    antes = acoes[i + 1]
            menu_bar.removeAction(mact)
            self.menu_orifsc.deleteLater()
            self.menu_orifsc = None
        self.actions.clear()
        self.acoes_por_id.clear()
        self._titulos_base.clear()
        self._criar_menu(antes)

    def _construir_menu_idioma(self, menu: QMenu) -> None:
        """Submenu de idioma no fim do menu OrIFSC. O título sempre traz
        "Language", para quem não lê o idioma atual achar a opção."""
        from .i18n import (AUTO, IDIOMAS, idioma, preferencia_idioma)
        titulo = 'Language' if idioma() == 'en' else (
            tr('Idioma') + ' / Language')
        sub = menu.addMenu(_icone('idioma.svg'), titulo)
        pref = preferencia_idioma()
        opcoes = [(AUTO, tr('Automático (idioma do QGIS)'))] + list(IDIOMAS)
        for codigo, rotulo in opcoes:
            act = QAction(rotulo, sub)
            act.setCheckable(True)
            act.setChecked(codigo == pref)
            act.triggered.connect(
                lambda _marcado=False, c=codigo: self._definir_idioma(c))
            sub.addAction(act)
            self.actions.append(act)
            if codigo == AUTO:
                sub.addSeparator()

    def _definir_idioma(self, codigo: str) -> None:
        """Salva o idioma escolhido no menu e reconstrói o menu traduzido.

        A reconstrução é adiada para o próximo ciclo do event loop: o sinal
        vem de uma ação do próprio menu que será destruído.
        """
        from .i18n import nome_idioma, idioma, salvar_preferencia_idioma
        salvar_preferencia_idioma(codigo)
        QTimer.singleShot(0, self._reconstruir_menu)
        self.iface.messageBar().pushMessage(
            'OrIFSC',
            tr('Idioma do plugin: {idioma}.', idioma=nome_idioma(idioma())),
            level=Qgis.MessageLevel.Info,
            duration=4)

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
            {'titulo': tr('Início'), 'itens': [
                {'titulo': tr('Definir Local e Criar Folha'),
                 'slot': self._definir_local,
                 'icone': 'definir_local.svg',
                 'id': 'definir_local'},
                {'titulo': tr('Camada de Limite'),
                 'slot': self._criar_limite,
                 'icone': 'criar_limite.svg'},
            ]},
            {'titulo': tr('Bases / Camadas de Fundo'), 'itens': [
                {'titulo': tr('Satélite Google'),
                 'slot': self._carregar_satelite,
                 'icone': 'satelite.svg'},
                {'titulo': 'OpenStreetMap',
                 'slot': self._base_osm,
                 'icone': 'osm.svg'},
                {'titulo': tr('Adicionar WMS/WMTS…'),
                    'slot': self._base_wms, 'icone': 'wms.svg'},
            ]},
            {'titulo': tr('Importar'), 'itens': [
                {'titulo': tr('Importar KML / GPX…'),
                    'slot': self._importar_kml_gpx, 'icone': ''},
            ]},
            {'titulo': tr('Relevo'), 'itens': [
                {'titulo': tr('Gerar Curvas de Nível'), 'slot': self._gerar_curvas,
                    'icone': 'curvas.svg', 'id': 'gerar_curvas'},
            ]},
            {'titulo': tr('Dados Públicos'), 'itens': [
                {'titulo': tr('Santa Catarina'), 'itens': [
                    {'titulo': tr('Adicionar camadas do SIG@SC '
                                  '(Ortofoto WMTS / MDT WMS)…'),
                        'slot': self._sigsc_adicionar,
                        'icone': 'ortofoto.svg'},
                    {'titulo': tr('Abrir portal SIG@SC…'),
                        'slot': self._abrir_sigsc, 'icone': 'portal.svg'},
                ]},
            ]},
            {'titulo': tr('Exportar'), 'itens': [
                {'titulo': tr('Gerar Projeto OCAD / OOM…'),
                 'slot': self._exportar_ocad,
                 'icone': 'exportar.svg',
                 'id': 'exportar'},
            ]},
            SEP,
            {'titulo': tr('Configurações…'),
             'slot': self._configuracoes,
             'icone': 'config.svg'},
            {'titulo': tr('Ajuda / Sobre'), 'itens': [
                {'titulo': tr('Documentação'),
                 'slot': self._documentacao,
                 'icone': 'doc.svg'},
                {'titulo': tr('Sobre o OrIFSC'),
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
                tr('Satélite carregado com sucesso.'),
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
                tr('OpenStreetMap carregado com sucesso.'),
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
                tr('Gerenciador WMS/WMTS aberto.'),
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
                tr('Para gerar curvas, adicione primeiro uma camada poligonal '
                   'que delimite a área de trabalho. Você pode usar "Definir '
                   'Local e Criar Folha" ou "Camada de Limite".'),
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
        from .acoes.comum import (projeto_configurado,
                                  avisar_projeto_nao_configurado,
                                  camada_curvas, camada_folha)
        from .acoes.configuracoes import ler_pasta_saida
        if not projeto_configurado():
            avisar_projeto_nao_configurado(self.iface)
            return

        params = {}
        folha = camada_folha()
        if folha is not None:
            params['FOLHA'] = folha.id()
        curvas = camada_curvas()
        if curvas is not None:
            params['CURVAS'] = curvas.id()
        pasta = ler_pasta_saida()
        if pasta:
            params['PASTA'] = pasta

        import processing
        processing.execAlgorithmDialog('orifsc:exportar_ocad', params)

    def _configuracoes(self) -> None:
        """Abre o diálogo de configurações globais; se o idioma mudou,
        reconstrói o menu já traduzido."""
        from .acoes.configuracoes import DialogConfiguracoes
        dlg = DialogConfiguracoes(self.iface.mainWindow())
        dlg.exec()
        if dlg.idioma_mudou:
            self._reconstruir_menu()

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
