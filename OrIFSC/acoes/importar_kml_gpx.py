"""Importar KML / GPX.

Diálogo que permite selecionar um arquivo .kml ou .gpx, escolher quais
sub-camadas importar (no caso do GPX) e adicioná-las ao projeto QGIS,
centralizando o mapa na extensão das camadas carregadas.
"""
import os
from typing import Any, List

from qgis.core import (
    QgsCoordinateTransform,
    QgsProject, QgsRectangle, QgsVectorLayer, Qgis,
)
from qgis.PyQt.QtWidgets import (
    QDialog, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
    QLineEdit, QPushButton, QVBoxLayout,
    QCheckBox, QDialogButtonBox,
)

from .painel import montar_com_painel, INSTRUCOES

_SUBCAMADAS_GPX = [
    ('tracks', 'Trilhas (tracks)'),
    ('routes', 'Rotas (routes)'),
    ('waypoints', 'Waypoints'),
]


class DialogImportarKmlGpx(QDialog):
    """Diálogo para importação de arquivos KML/GPX com zoom automático."""

    def __init__(self, iface: Any, parent: Any = None) -> None:
        """Inicializa UI de importação de arquivos KML e GPX.

        Args:
            iface: Interface principal do QGIS.
            parent: Widget pai opcional.

        O fluxo mantém importação guiada para usuário final, conforme papel dos
        módulos de ``acoes`` definido nas diretrizes.
        """
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle('OrIFSC — Importar KML / GPX')
        self.setMinimumWidth(420)

        layout = QVBoxLayout()
        form = QFormLayout()
        layout.addLayout(form)

        linha_arquivo = QHBoxLayout()
        self.campo_arquivo = QLineEdit()
        self.campo_arquivo.setPlaceholderText(
            'Selecione um arquivo .kml ou .gpx')
        self.campo_arquivo.textChanged.connect(self._on_arquivo_mudou)
        linha_arquivo.addWidget(self.campo_arquivo, 1)

        btn_browse = QPushButton('…')
        btn_browse.setFixedWidth(32)
        btn_browse.clicked.connect(self._selecionar_arquivo)
        linha_arquivo.addWidget(btn_browse)

        form.addRow('Arquivo:', linha_arquivo)

        self.grupo_gpx = QGroupBox('Sub-camadas a importar (GPX)')
        gpx_layout = QVBoxLayout(self.grupo_gpx)
        self.checks = {}
        for nome_ogr, rotulo in _SUBCAMADAS_GPX:
            cb = QCheckBox(rotulo)
            cb.setChecked(nome_ogr == 'tracks')
            gpx_layout.addWidget(cb)
            self.checks[nome_ogr] = cb
        self.grupo_gpx.setVisible(False)
        layout.addWidget(self.grupo_gpx)

        botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                  QDialogButtonBox.StandardButton.Cancel)
        botoes.button(QDialogButtonBox.StandardButton.Ok).setText('Importar')
        botoes.button(
            QDialogButtonBox.StandardButton.Cancel).setText('Cancelar')
        botoes.accepted.connect(self._importar)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)

        montar_com_painel(self, layout, 'Importar KML / GPX',
                          INSTRUCOES['importar_kml_gpx'])

    def _selecionar_arquivo(self) -> None:
        """Abre seletor de arquivo geográfico e preenche o campo de caminho."""
        path, _ = QFileDialog.getOpenFileName(
            self, 'Selecionar arquivo KML ou GPX', '',
            'Arquivos geográficos (*.kml *.gpx);;KML (*.kml);;GPX (*.gpx)')
        if path:
            self.campo_arquivo.setText(path)

    def _on_arquivo_mudou(self, path: str) -> None:
        """Alterna as opções de sub-camada quando o arquivo é GPX."""
        eh_gpx = path.lower().endswith('.gpx')
        self.grupo_gpx.setVisible(eh_gpx)
        self.adjustSize()

    def _importar(self) -> None:
        """Importa o arquivo selecionado e adiciona as camadas válidas no projeto."""
        path = self.campo_arquivo.text().strip()
        if not path or not os.path.isfile(path):
            self.iface.messageBar().pushMessage(
                'OrIFSC',
                'Selecione um arquivo KML ou GPX existente.',
                level=Qgis.MessageLevel.Warning,
                duration=6)
            return

        ext_lower = os.path.splitext(path)[1].lower()
        nome_base = os.path.splitext(os.path.basename(path))[0]

        camadas_carregadas = []

        if ext_lower == '.gpx':
            selecionadas = [
                n for n, cb in self.checks.items() if cb.isChecked()]
            if not selecionadas:
                self.iface.messageBar().pushMessage(
                    'OrIFSC',
                    'Marque ao menos uma sub-camada do GPX para importar.',
                    level=Qgis.MessageLevel.Warning,
                    duration=6)
                return
            for nome_ogr in selecionadas:
                rotulo = dict(_SUBCAMADAS_GPX)[nome_ogr]
                uri = f'{path}|layername={nome_ogr}'
                camada = QgsVectorLayer(uri, f'{nome_base} — {rotulo}', 'ogr')
                if camada.isValid() and camada.featureCount() > 0:
                    QgsProject.instance().addMapLayer(camada)
                    camadas_carregadas.append(camada)
        else:
            camada = QgsVectorLayer(path, nome_base, 'ogr')
            if camada.isValid():
                QgsProject.instance().addMapLayer(camada)
                camadas_carregadas.append(camada)

        if not camadas_carregadas:
            self.iface.messageBar().pushMessage(
                'OrIFSC',
                'Não foi possível carregar camadas válidas desse arquivo. '
                'Verifique se ele contém dados compatíveis.',
                level=Qgis.MessageLevel.Warning,
                duration=8)
            return

        self._zoom_para_camadas(camadas_carregadas)
        self.iface.messageBar().pushMessage(
            'OrIFSC',
            'Importação concluída com sucesso.',
            level=Qgis.MessageLevel.Success,
            duration=5)
        self.accept()

    def _zoom_para_camadas(self, camadas: List[QgsVectorLayer]) -> None:
        """Ajusta o canvas para a extensão combinada das camadas importadas."""
        canvas = self.iface.mapCanvas()
        crs_projeto = QgsProject.instance().crs()
        extent = QgsRectangle()

        for camada in camadas:
            crs_camada = camada.crs()
            ext_camada = camada.extent()
            if not crs_camada.isValid() or not crs_projeto.isValid():
                extent.combineExtentWith(ext_camada)
                continue
            if crs_camada.authid() != crs_projeto.authid():
                try:
                    tr = QgsCoordinateTransform(crs_camada, crs_projeto,
                                                QgsProject.instance())
                    ext_camada = tr.transformBoundingBox(ext_camada)
                except Exception:  # nosec B110 - falha na transformação: usa o extent original
                    pass
            extent.combineExtentWith(ext_camada)

        if not extent.isNull() and not extent.isEmpty():
            extent.grow(extent.width() * 0.05 or 100)
            canvas.setExtent(extent)
            canvas.refresh()
