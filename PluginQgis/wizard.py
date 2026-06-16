import os
import math
import tempfile
import urllib.request

from qgis.core import (
    QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsPointXY,
    QgsVectorLayer, QgsRasterLayer, QgsFeature, QgsGeometry, QgsRectangle,
    QgsProject, QgsSymbol, QgsSingleSymbolRenderer, QgsMapSettings,
    QgsMapRendererParallelJob, QgsVectorFileWriter, QgsWkbTypes,
)
from qgis.gui import QgsMapToolEmitPoint, QgsRubberBand
from qgis.PyQt.QtCore import Qt, QThread, QObject, pyqtSignal, QSize, QRectF
from qgis.PyQt.QtGui import QColor, QImage, QPainter
from qgis.PyQt.QtWidgets import (
    QWizard, QWizardPage, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QComboBox, QSpinBox, QPushButton, QProgressBar,
    QCheckBox, QFileDialog, QGroupBox, QRadioButton, QButtonGroup,
    QMessageBox, QFrame, QSizePolicy,
)
import processing


ESCALAS = [
    ('1:4.000', 4000),
    ('1:5.000', 5000),
    ('1:7.500', 7500),
    ('1:10.000', 10000),
    ('1:15.000', 15000),
    ('Personalizada...', -1),
]

FOLHAS = [('A3', 420, 297), ('A4', 297, 210), ('A5', 210, 148)]


# ---------------------------------------------------------------------------
# Worker de download do DEM (roda em QThread separado)
# ---------------------------------------------------------------------------
class DEMDownloadWorker(QObject):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, tiles):
        super().__init__()
        self.tiles = tiles  # list of (url, local_path)

    def run(self):
        try:
            total = len(self.tiles)
            downloaded = []
            for i, (url, path) in enumerate(self.tiles):
                pct = int(i * 90 / total)
                self.progress.emit(pct, f'Baixando MDT ({i + 1}/{total})...')
                if not os.path.exists(path):
                    urllib.request.urlretrieve(url, path)
                downloaded.append(path)
            self.progress.emit(90, 'Download concluído.')
            self.finished.emit(downloaded)
        except Exception as e:
            self.error.emit(str(e))


# ---------------------------------------------------------------------------
# Wizard principal
# ---------------------------------------------------------------------------
class OrIFSCWizard(QWizard):
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle('OrIFSC — Criar Mapa de Orientação')
        self.setMinimumWidth(520)
        self.setMinimumHeight(420)
        self.setWizardStyle(QWizard.ModernStyle)

        # Estado compartilhado entre páginas
        self.epsg_code = None
        self.crs_utm = None
        self.camada_limite = None
        self.camada_folha = None
        self.camada_google = None
        self.camada_curvas = None
        self.extent_folha = None

        self.addPage(PaginaLocalizacao(self))
        self.addPage(PaginaLimite(self))
        self.addPage(PaginaDownload(self))
        self.addPage(PaginaExportar(self))

        self.setButtonText(QWizard.NextButton, 'Próximo  ›')
        self.setButtonText(QWizard.BackButton, '‹  Voltar')
        self.setButtonText(QWizard.FinishButton, 'Concluir')
        self.setButtonText(QWizard.CancelButton, 'Cancelar')


# ---------------------------------------------------------------------------
# Página 1 — Localização e escala
# ---------------------------------------------------------------------------
class PaginaLocalizacao(QWizardPage):
    def __init__(self, parent):
        super().__init__(parent)
        self.setTitle('Passo 1 de 4 — Localização')
        self.setSubTitle('Cole a coordenada do Google Maps e defina o tamanho do mapa.')

        layout = QFormLayout(self)
        layout.setRowWrapPolicy(QFormLayout.WrapLongRows)

        self.coord_input = QLineEdit()
        self.coord_input.setPlaceholderText('Ex: -27.5926, -48.5431')
        self.coord_input.textChanged.connect(self.completeChanged)
        layout.addRow('Coordenada (Google Maps):', self.coord_input)

        self.escala_combo = QComboBox()
        for label, _ in ESCALAS:
            self.escala_combo.addItem(label)
        self.escala_combo.currentIndexChanged.connect(self._on_escala_changed)
        layout.addRow('Escala:', self.escala_combo)

        self.escala_custom = QSpinBox()
        self.escala_custom.setRange(500, 500000)
        self.escala_custom.setValue(4000)
        self.escala_custom.setSuffix('  (denominador)')
        self.escala_custom.setVisible(False)
        layout.addRow('Valor personalizado 1:', self.escala_custom)

        self.folha_combo = QComboBox()
        for nome, _, _ in FOLHAS:
            self.folha_combo.addItem(nome)
        self.folha_combo.setCurrentIndex(1)
        self.folha_combo.currentIndexChanged.connect(self._atualizar_preview)
        layout.addRow('Tamanho da Folha:', self.folha_combo)

        self.orientacao_combo = QComboBox()
        self.orientacao_combo.addItems(['Paisagem', 'Retrato'])
        self.orientacao_combo.currentIndexChanged.connect(self._atualizar_preview)
        layout.addRow('Orientação da Folha:', self.orientacao_combo)

        self.preview_label = QLabel()
        self.preview_label.setStyleSheet('color: #555; font-style: italic;')
        layout.addRow('Área na escala:', self.preview_label)

        self._atualizar_preview()

    def _on_escala_changed(self, idx):
        eh_custom = (ESCALAS[idx][1] == -1)
        self.escala_custom.setVisible(eh_custom)
        self._atualizar_preview()

    def _atualizar_preview(self):
        escala = self._escala_valor()
        idx_folha = self.folha_combo.currentIndex()
        _, larg_mm, alt_mm = FOLHAS[idx_folha]
        if self.orientacao_combo.currentIndex() == 1:
            larg_mm, alt_mm = alt_mm, larg_mm
        larg_m = (larg_mm / 1000.0) * escala
        alt_m = (alt_mm / 1000.0) * escala
        self.preview_label.setText(f'{larg_m:.0f} m × {alt_m:.0f} m no terreno')

    def _escala_valor(self):
        idx = self.escala_combo.currentIndex()
        val = ESCALAS[idx][1]
        return self.escala_custom.value() if val == -1 else val

    def isComplete(self):
        txt = self.coord_input.text().strip()
        if not txt:
            return False
        try:
            partes = txt.replace(' ', '').split(',')
            float(partes[0])
            float(partes[1])
            return True
        except Exception:
            return False

    def validatePage(self):
        try:
            txt = self.coord_input.text().replace(' ', '')
            partes = txt.split(',')
            lat = float(partes[0])
            lon = float(partes[1])
        except Exception:
            QMessageBox.warning(self, 'Coordenada inválida',
                                'Use o formato do Google Maps: Lat, Lon\nEx: -27.5926, -48.5431')
            return False

        escala = self._escala_valor()
        idx_folha = self.folha_combo.currentIndex()
        _, larg_mm, alt_mm = FOLHAS[idx_folha]
        if self.orientacao_combo.currentIndex() == 1:
            larg_mm, alt_mm = alt_mm, larg_mm

        fuso = int((lon + 180) / 6) + 1
        epsg_code = 32600 + fuso if lat >= 0 else 32700 + fuso

        crs_wgs84 = QgsCoordinateReferenceSystem.fromEpsgId(4326)
        crs_utm = QgsCoordinateReferenceSystem.fromEpsgId(epsg_code)
        transform = QgsCoordinateTransform(crs_wgs84, crs_utm, QgsProject.instance())
        ponto_utm = transform.transform(QgsPointXY(lon, lat))

        larg_m = (larg_mm / 1000.0) * escala
        alt_m = (alt_mm / 1000.0) * escala

        x_min = ponto_utm.x() - larg_m / 2
        x_max = ponto_utm.x() + larg_m / 2
        y_min = ponto_utm.y() - alt_m / 2
        y_max = ponto_utm.y() + alt_m / 2

        w = self.wizard()
        w.epsg_code = epsg_code
        w.crs_utm = crs_utm
        w.extent_folha = QgsRectangle(x_min, y_min, x_max, y_max)

        # Camada folha (gabarito visual vermelho)
        camada_folha = QgsVectorLayer(f'Polygon?crs=EPSG:{epsg_code}', 'folha', 'memory')
        prov = camada_folha.dataProvider()
        feat = QgsFeature()
        feat.setGeometry(QgsGeometry.fromRect(QgsRectangle(x_min, y_min, x_max, y_max)))
        prov.addFeatures([feat])
        simbolo = QgsSymbol.defaultSymbol(camada_folha.geometryType())
        simbolo.setColor(QColor(255, 0, 0, 255))
        simbolo.symbolLayer(0).setStrokeColor(QColor(255, 0, 0, 255))
        simbolo.symbolLayer(0).setBrushStyle(Qt.NoBrush)
        camada_folha.setRenderer(QgsSingleSymbolRenderer(simbolo))
        w.camada_folha = camada_folha

        # Camada limite (vazia, para o usuário desenhar)
        camada_limite = QgsVectorLayer(f'Polygon?crs=EPSG:{epsg_code}', 'limite', 'memory')
        camada_limite.startEditing()
        w.camada_limite = camada_limite

        # Configura o projeto
        QgsProject.instance().setCrs(crs_utm)

        url_google = ('type=xyz&url=https://mt1.google.com/vt/'
                      'lyrs%3Ds%26x%3D%7Bx%7D%26y%3D%7By%7D%26z%3D%7Bz%7D&zmax=20&zmin=0')
        camada_google = QgsRasterLayer(url_google, 'Google Satellite', 'wms')
        if camada_google.isValid():
            QgsProject.instance().addMapLayer(camada_google)
            w.camada_google = camada_google

        QgsProject.instance().addMapLayer(camada_limite)
        QgsProject.instance().addMapLayer(camada_folha)

        self.wizard().iface.mapCanvas().setExtent(QgsRectangle(x_min, y_min, x_max, y_max))
        self.wizard().iface.mapCanvas().refresh()

        return True


# ---------------------------------------------------------------------------
# Página 2 — Desenhar o polígono limite
# ---------------------------------------------------------------------------
class PaginaLimite(QWizardPage):
    def __init__(self, parent):
        super().__init__(parent)
        self.setTitle('Passo 2 de 4 — Área do Mapa')
        self.setSubTitle(
            'Desenhe o polígono da área que será mapeada.\n'
            'A borda vermelha é só referência do tamanho da folha.')

        layout = QVBoxLayout(self)

        instrucoes = QLabel(
            '1. Clique em  <b>Iniciar Desenho</b> abaixo.\n'
            '2. Clique no mapa para adicionar os vértices da área.\n'
            '3. Clique com o botão <b>direito</b> para finalizar o polígono.\n'
            '4. Quando aparecer "Polígono desenhado ✓", clique em Próximo.'
        )
        instrucoes.setWordWrap(True)
        instrucoes.setStyleSheet('padding: 8px; background: #f0f4ff; border-radius: 4px;')
        layout.addWidget(instrucoes)

        layout.addSpacing(12)

        self.btn_desenhar = QPushButton('✏  Iniciar Desenho')
        self.btn_desenhar.setMinimumHeight(36)
        self.btn_desenhar.clicked.connect(self._iniciar_desenho)
        layout.addWidget(self.btn_desenhar)

        self.status_label = QLabel('Aguardando polígono...')
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet('color: #888; padding: 8px;')
        layout.addWidget(self.status_label)

        layout.addStretch()

    def initializePage(self):
        self._checar_limite()

    def _iniciar_desenho(self):
        w = self.wizard()
        iface = w.iface
        camada = w.camada_limite

        if camada is None:
            return

        iface.setActiveLayer(camada)
        if not camada.isEditable():
            camada.startEditing()

        iface.actionAddFeature().trigger()
        camada.featureAdded.connect(self._on_feature_added)
        self.btn_desenhar.setText('Desenhando... (clique direito para finalizar)')
        self.btn_desenhar.setEnabled(False)

    def _on_feature_added(self, fid):
        w = self.wizard()
        w.camada_limite.commitChanges()
        w.camada_limite.featureAdded.disconnect(self._on_feature_added)
        self._checar_limite()

    def _checar_limite(self):
        w = self.wizard()
        if w.camada_limite and w.camada_limite.featureCount() > 0:
            self.status_label.setText('Polígono desenhado ✓')
            self.status_label.setStyleSheet('color: green; font-weight: bold; padding: 8px;')
            self.btn_desenhar.setEnabled(False)
            self.btn_desenhar.setText('Polígono pronto ✓')
            self.completeChanged.emit()
        else:
            self.status_label.setText('Aguardando polígono...')
            self.status_label.setStyleSheet('color: #888; padding: 8px;')
            self.btn_desenhar.setEnabled(True)
            self.btn_desenhar.setText('✏  Iniciar Desenho')

    def isComplete(self):
        w = self.wizard()
        return bool(w.camada_limite and w.camada_limite.featureCount() > 0)


# ---------------------------------------------------------------------------
# Página 3 — Download do DEM e geração de curvas
# ---------------------------------------------------------------------------
class PaginaDownload(QWizardPage):
    def __init__(self, parent):
        super().__init__(parent)
        self.setTitle('Passo 3 de 4 — Baixar Dados')
        self.setSubTitle(
            'O satélite já está carregado. Agora gere as curvas de nível '
            '(usa o MDT Copernicus 30m — gratuito, sem cadastro).')

        self._concluido = False
        self._thread = None
        self._worker = None

        layout = QVBoxLayout(self)

        grp = QGroupBox('Curvas de Nível')
        grp_layout = QFormLayout(grp)
        self.equidist_spin = QSpinBox()
        self.equidist_spin.setRange(1, 100)
        self.equidist_spin.setValue(5)
        self.equidist_spin.setSuffix(' metros')
        grp_layout.addRow('Equidistância:', self.equidist_spin)
        layout.addWidget(grp)

        self.btn_baixar = QPushButton('▶  Gerar Curvas de Nível')
        self.btn_baixar.setMinimumHeight(38)
        self.btn_baixar.clicked.connect(self._iniciar_download)
        layout.addWidget(self.btn_baixar)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel('')
        self.status_label.setWordWrap(True)
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)

        layout.addStretch()

    def initializePage(self):
        self._concluido = False
        self.btn_baixar.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText('')

    def _tiles_para_baixar(self):
        w = self.wizard()
        camada = w.camada_limite
        crs_wgs84 = QgsCoordinateReferenceSystem('EPSG:4326')
        transform = QgsCoordinateTransform(camada.crs(), crs_wgs84, QgsProject.instance())
        ext = transform.transformBoundingBox(camada.extent())
        margem = 0.003

        tiles = []
        lat = math.floor(ext.yMinimum() - margem)
        while lat <= math.floor(ext.yMaximum() + margem):
            lon = math.floor(ext.xMinimum() - margem)
            while lon <= math.floor(ext.xMaximum() + margem):
                ns = 'N' if lat >= 0 else 'S'
                ew = 'E' if lon >= 0 else 'W'
                name = (f'Copernicus_DSM_COG_10_{ns}{abs(lat):02d}_00'
                        f'_{ew}{abs(lon):03d}_00_DEM')
                url = f'https://copernicus-dem-30m.s3.amazonaws.com/{name}/{name}.tif'
                path = os.path.join(tempfile.gettempdir(), f'oriifsc_cop30_{lat}_{lon}.tif')
                tiles.append((url, path))
                lon += 1
            lat += 1
        return tiles

    def _iniciar_download(self):
        self.btn_baixar.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText('Iniciando download...')

        tiles = self._tiles_para_baixar()

        self._thread = QThread()
        self._worker = DEMDownloadWorker(tiles)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_download_done)
        self._worker.error.connect(self._on_error)

        self._thread.start()

    def _on_progress(self, pct, msg):
        self.progress_bar.setValue(pct)
        self.status_label.setText(msg)

    def _on_download_done(self, tile_files):
        self._thread.quit()
        self._thread.wait()

        self.status_label.setText('Gerando curvas de nível...')
        self.progress_bar.setValue(92)

        w = self.wizard()
        camada_limite = w.camada_limite
        equidistancia = self.equidist_spin.value()

        try:
            # Mescla tiles se necessário
            if len(tile_files) > 1:
                mdt_temp = os.path.join(tempfile.gettempdir(), 'oriifsc_mdt_merged.tif')
                processing.run('gdal:merge', {
                    'INPUT': tile_files,
                    'PCT': False, 'SEPARATE': False,
                    'NODATA_INPUT': None, 'NODATA_OUTPUT': None,
                    'DATA_TYPE': 5, 'OUTPUT': mdt_temp,
                })
            else:
                mdt_temp = tile_files[0]

            self.progress_bar.setValue(95)
            self.status_label.setText('Calculando curvas...')

            curvas_brutas = processing.run('gdal:contour', {
                'INPUT': mdt_temp,
                'BAND': 1,
                'INTERVAL': equidistancia,
                'FIELD_NAME': 'ELEV',
                'CREATE_3D': False,
                'OUTPUT': 'TEMPORARY_OUTPUT',
            })['OUTPUT']

            self.status_label.setText('Suavizando...')
            saida = processing.run('native:smoothgeometry', {
                'INPUT': curvas_brutas,
                'ITERATIONS': 3,
                'OFFSET': 0.25,
                'MAX_ANGLE': 180,
                'OUTPUT': 'TEMPORARY_OUTPUT',
            })['OUTPUT']

            w.camada_curvas = saida
            QgsProject.instance().addMapLayer(saida)

            self.progress_bar.setValue(100)
            self.status_label.setText('Curvas de nível geradas ✓')
            self.status_label.setStyleSheet('color: green; font-weight: bold;')
            self._concluido = True
            self.completeChanged.emit()

        except Exception as e:
            self._on_error(str(e))

    def _on_error(self, msg):
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait()
        self.btn_baixar.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText(f'Erro: {msg}')
        self.status_label.setStyleSheet('color: red;')
        QMessageBox.critical(self, 'Erro no download',
                             f'Não foi possível baixar o MDT.\n\n{msg}\n\n'
                             'Verifique sua conexão com a internet e tente novamente.')

    def isComplete(self):
        return self._concluido


# ---------------------------------------------------------------------------
# Página 4 — Exportar para o OCAD
# ---------------------------------------------------------------------------
class PaginaExportar(QWizardPage):
    def __init__(self, parent):
        super().__init__(parent)
        self.setTitle('Passo 4 de 4 — Exportar para o OCAD')
        self.setSubTitle('Escolha o formato e a pasta de saída. Os arquivos ficam prontos para importar no OCAD.')

        layout = QVBoxLayout(self)

        # Pasta de saída
        pasta_layout = QHBoxLayout()
        self.pasta_input = QLineEdit()
        self.pasta_input.setPlaceholderText('Selecione a pasta de saída...')
        self.pasta_input.textChanged.connect(self.completeChanged)
        btn_pasta = QPushButton('📁')
        btn_pasta.setFixedWidth(32)
        btn_pasta.clicked.connect(self._selecionar_pasta)
        pasta_layout.addWidget(self.pasta_input)
        pasta_layout.addWidget(btn_pasta)
        layout.addLayout(pasta_layout)

        # Imagem de satélite
        grp_sat = QGroupBox('Imagem de Satélite (fundo para o OCAD)')
        sat_layout = QFormLayout(grp_sat)
        self.chk_satelite = QCheckBox('Exportar imagem georreferenciada (.jpg + .jgw)')
        self.chk_satelite.setChecked(True)
        self.resolucao_combo = QComboBox()
        self.resolucao_combo.addItems(['150 DPI (rascunho)', '300 DPI (impressão)'])
        self.resolucao_combo.setCurrentIndex(1)
        sat_layout.addRow(self.chk_satelite)
        sat_layout.addRow('Resolução:', self.resolucao_combo)
        layout.addWidget(grp_sat)

        # Curvas de nível
        grp_curvas = QGroupBox('Curvas de Nível')
        curvas_layout = QVBoxLayout(grp_curvas)
        self.chk_curvas = QCheckBox('Exportar curvas de nível')
        self.chk_curvas.setChecked(True)

        formato_layout = QHBoxLayout()
        self.radio_shp = QRadioButton('Shapefile (.shp)  — compatível com OCAD 10+')
        self.radio_geojson = QRadioButton('GeoJSON (.geojson)  — formato moderno')
        self.radio_shp.setChecked(True)
        self.btn_group = QButtonGroup(self)
        self.btn_group.addButton(self.radio_shp)
        self.btn_group.addButton(self.radio_geojson)
        formato_layout.addWidget(self.radio_shp)
        formato_layout.addWidget(self.radio_geojson)

        curvas_layout.addWidget(self.chk_curvas)
        curvas_layout.addLayout(formato_layout)
        layout.addWidget(grp_curvas)

        self.btn_exportar = QPushButton('✔  Exportar')
        self.btn_exportar.setMinimumHeight(38)
        self.btn_exportar.clicked.connect(self._exportar)
        layout.addWidget(self.btn_exportar)

        self.status_label = QLabel('')
        self.status_label.setWordWrap(True)
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)

        layout.addStretch()
        self._exportado = False

    def _selecionar_pasta(self):
        pasta = QFileDialog.getExistingDirectory(self, 'Selecionar pasta de saída')
        if pasta:
            self.pasta_input.setText(pasta)

    def isComplete(self):
        return bool(self.pasta_input.text().strip()) and self._exportado

    def _exportar(self):
        pasta = self.pasta_input.text().strip()
        if not pasta or not os.path.isdir(pasta):
            QMessageBox.warning(self, 'Pasta inválida', 'Selecione uma pasta de saída válida.')
            return

        w = self.wizard()
        erros = []

        if self.chk_satelite.isChecked():
            try:
                self._exportar_satelite(pasta, w)
                self.status_label.setText('Exportando satelite... ✓')
            except Exception as e:
                erros.append(f'Satélite: {e}')

        if self.chk_curvas.isChecked() and w.camada_curvas:
            try:
                self._exportar_curvas(pasta, w)
                self.status_label.setText('Exportando curvas... ✓')
            except Exception as e:
                erros.append(f'Curvas: {e}')

        if erros:
            QMessageBox.critical(self, 'Erro na exportação', '\n'.join(erros))
            return

        msg_partes = []
        if self.chk_satelite.isChecked():
            msg_partes.append('• satelite_oriifsc.jpg  (+ .jgw)')
        if self.chk_curvas.isChecked():
            ext = 'shp' if self.radio_shp.isChecked() else 'geojson'
            msg_partes.append(f'• curvas_oriifsc.{ext}')

        self.status_label.setText(
            f'Exportação concluída ✓\n\nArquivos em:\n{pasta}\n\n' + '\n'.join(msg_partes))
        self.status_label.setStyleSheet('color: green;')
        self._exportado = True
        self.completeChanged.emit()

    def _exportar_satelite(self, pasta, w):
        dpi = 150 if self.resolucao_combo.currentIndex() == 0 else 300
        extent = w.camada_limite.extent() if w.camada_limite.featureCount() > 0 else w.extent_folha

        larg_px = int((extent.width() / (extent.width() + extent.height())) * 4000)
        alt_px = int((extent.height() / (extent.width() + extent.height())) * 4000)
        larg_px = max(larg_px, 800)
        alt_px = max(alt_px, 800)

        settings = QgsMapSettings()
        settings.setExtent(extent)
        settings.setOutputSize(QSize(larg_px, alt_px))
        settings.setOutputDpi(dpi)
        settings.setDestinationCrs(w.crs_utm)

        camadas = [l for l in QgsProject.instance().mapLayers().values()
                   if 'Google Satellite' in l.name()]
        if not camadas:
            raise Exception('Camada Google Satellite não encontrada no projeto.')
        settings.setLayers(camadas)

        job = QgsMapRendererParallelJob(settings)
        job.start()
        job.waitForFinished()

        img = job.renderedImage()
        caminho_jpg = os.path.join(pasta, 'satelite_oriifsc.jpg')
        img.save(caminho_jpg, 'JPEG', 90)

        # World file (.jgw)
        px_x = extent.width() / larg_px
        px_y = extent.height() / alt_px
        caminho_jgw = os.path.join(pasta, 'satelite_oriifsc.jgw')
        with open(caminho_jgw, 'w') as f:
            f.write(f'{px_x}\n0.0\n0.0\n-{px_y}\n'
                    f'{extent.xMinimum() + px_x / 2}\n'
                    f'{extent.yMaximum() - px_y / 2}\n')

    def _exportar_curvas(self, pasta, w):
        usar_shp = self.radio_shp.isChecked()
        ext = 'shp' if usar_shp else 'geojson'
        driver = 'ESRI Shapefile' if usar_shp else 'GeoJSON'
        caminho = os.path.join(pasta, f'curvas_oriifsc.{ext}')

        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = driver
        options.fileEncoding = 'UTF-8'

        QgsVectorFileWriter.writeAsVectorFormatV3(
            w.camada_curvas,
            caminho,
            QgsProject.instance().transformContext(),
            options,
        )
