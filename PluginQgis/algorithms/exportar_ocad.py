import os

from qgis.core import (
    QgsProcessingAlgorithm, QgsProcessingParameterFeatureSource,
    QgsProcessingParameterVectorLayer, QgsProcessingParameterEnum,
    QgsProcessingParameterBoolean, QgsProcessingParameterFolderDestination,
    QgsProcessingException, QgsProcessing, QgsProject, QgsProcessingContext,
    QgsMapSettings, QgsMapRendererParallelJob, QgsVectorFileWriter,
)
from qgis.PyQt.QtCore import QSize, QEventLoop
from qgis.PyQt.QtGui import QImage

from ..acoes.comum import ler_escala

# Teto de segurança por lado (evita estourar memória em folhas grandes).
MAX_PX = 25000


def _ocultar_da_toolbox(alg):
    """Marca o algoritmo como oculto da Caixa de Ferramentas (só acessível pelo menu).
    Compatível com QGIS antigo (FlagHideFromToolbox) e novo (Qgis.ProcessingAlgorithmFlag)."""
    flags = super(type(alg), alg).flags()
    try:
        return flags | QgsProcessingAlgorithm.FlagHideFromToolbox
    except AttributeError:
        from qgis.core import Qgis
        return flags | Qgis.ProcessingAlgorithmFlag.HideFromToolbox


class ExportarOCAD(QgsProcessingAlgorithm):
    FOLHA = 'FOLHA'
    EXPORTAR_SATELITE = 'EXPORTAR_SATELITE'
    SAT_FORMATO = 'SAT_FORMATO'
    DPI = 'DPI'
    CURVAS = 'CURVAS'
    LIMITE = 'LIMITE'
    FORMATO = 'FORMATO'
    PASTA = 'PASTA'

    def tr(self, s): return s
    def createInstance(self): return ExportarOCAD()
    def flags(self): return _ocultar_da_toolbox(self)
    def name(self): return 'exportar_ocad'
    def displayName(self): return '5. Exportar para o OCAD'
    def group(self): return 'Orientação'
    def groupId(self): return 'orientacao'
    def shortHelpString(self):
        return ('Gera os arquivos prontos para importar no OCAD a partir da área da '
                'folha:\n'
                '• satelite_oriifsc.(tif|png|jpg) — imagem georreferenciada do satélite,\n'
                '  na resolução real da folha (mm × DPI);\n'
                '• curvas_oriifsc.(shp|geojson) — curvas de nível (opcional);\n'
                '• limite_oriifsc.(shp|geojson) — contorno da área (opcional).\n\n'
                'Posicione a folha e salve as edições antes de exportar. A imagem '
                'exportada é recarregada no projeto para conferência.')

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.FOLHA, 'Camada da Folha (define a área de recorte)',
            [QgsProcessing.TypeVectorPolygon]))
        self.addParameter(QgsProcessingParameterBoolean(
            self.EXPORTAR_SATELITE, 'Exportar imagem de satélite',
            defaultValue=True))
        self.addParameter(QgsProcessingParameterEnum(
            self.SAT_FORMATO, 'Formato da imagem',
            options=['GeoTIFF (sem perdas)', 'PNG (sem perdas)',
                     'JPEG (qualidade alta)'], defaultValue=0))
        self.addParameter(QgsProcessingParameterEnum(
            self.DPI, 'Resolução da imagem',
            options=['150 DPI (rascunho)', '300 DPI (impressão)',
                     '600 DPI (máxima)'], defaultValue=1))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.CURVAS, 'Camada de Curvas de Nível (opcional)',
            [QgsProcessing.TypeVectorLine], optional=True))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.LIMITE, 'Camada de Limite (opcional)',
            [QgsProcessing.TypeVectorPolygon], optional=True))
        self.addParameter(QgsProcessingParameterEnum(
            self.FORMATO, 'Formato dos vetores (curvas/limite)',
            options=['Shapefile (.shp)', 'GeoJSON (.geojson)'], defaultValue=0))
        self.addParameter(QgsProcessingParameterFolderDestination(
            self.PASTA, 'Pasta de saída'))

    def processAlgorithm(self, parameters, context, feedback):
        folha = self.parameterAsSource(parameters, self.FOLHA, context)
        exportar_sat = self.parameterAsBool(parameters, self.EXPORTAR_SATELITE, context)
        idx_sat_fmt = self.parameterAsInt(parameters, self.SAT_FORMATO, context)
        idx_dpi = self.parameterAsInt(parameters, self.DPI, context)
        curvas = self.parameterAsVectorLayer(parameters, self.CURVAS, context)
        limite = self.parameterAsVectorLayer(parameters, self.LIMITE, context)
        idx_formato = self.parameterAsInt(parameters, self.FORMATO, context)
        pasta = self.parameterAsString(parameters, self.PASTA, context)

        if not pasta:
            raise QgsProcessingException('Selecione uma pasta de saída.')
        os.makedirs(pasta, exist_ok=True)

        extent = folha.sourceExtent()
        crs = folha.sourceCrs()
        saidas = {}

        if exportar_sat:
            feedback.pushInfo('Renderizando imagem de satélite (baixando tiles)...')
            img_path = self._exportar_satelite(extent, crs, idx_sat_fmt, idx_dpi,
                                               pasta, feedback)
            saidas['SATELITE'] = img_path
            self._carregar_no_projeto(img_path, 'Satélite (exportado)', context)
        feedback.setProgress(60)

        if curvas is not None:
            feedback.pushInfo('Exportando curvas de nível...')
            saidas['CURVAS'] = self._exportar_vetor(curvas, idx_formato, pasta, 'curvas')
        feedback.setProgress(80)

        if limite is not None:
            feedback.pushInfo('Exportando camada de limite...')
            saidas['LIMITE'] = self._exportar_vetor(limite, idx_formato, pasta, 'limite')
        feedback.setProgress(100)

        feedback.pushInfo(f'Exportação concluída. Arquivos em: {pasta}')
        return saidas

    # ------------------------------------------------------------------ satélite
    def _exportar_satelite(self, extent, crs, idx_sat_fmt, idx_dpi, pasta, feedback):
        dpi = (150, 300, 600)[idx_dpi]
        larg_px, alt_px = self._tamanho_px(extent, dpi, feedback)

        camadas = [l for l in QgsProject.instance().mapLayers().values()
                   if 'Google Satellite' in l.name()]
        if not camadas:
            raise QgsProcessingException(
                'Camada "Google Satellite" não encontrada no projeto. '
                'Rode o passo 1 (Carregar Satélite Google) primeiro.')

        settings = QgsMapSettings()
        settings.setExtent(extent)
        settings.setOutputSize(QSize(larg_px, alt_px))
        settings.setOutputDpi(dpi)
        settings.setDestinationCrs(crs)
        settings.setLayers(camadas)

        # Render com loop de eventos: sem isso a thread fica bloqueada e as
        # respostas de rede das tiles XYZ nunca são processadas -> imagem branca.
        job = QgsMapRendererParallelJob(settings)
        loop = QEventLoop()
        job.finished.connect(loop.quit)
        job.start()
        if job.isActive():
            loop.exec_()
        img = job.renderedImage()
        if img.isNull():
            raise QgsProcessingException(
                'Falha ao renderizar a imagem de satélite (imagem vazia).')
        # Descarta canal alfa -> RGB limpo de 3 bandas para o OCAD.
        img = img.convertToFormat(QImage.Format_RGB888)

        px_x = extent.width() / larg_px
        px_y = extent.height() / alt_px
        feedback.pushInfo(f'Imagem: {larg_px}×{alt_px}px @ {dpi} DPI '
                          f'({px_x:.3f} m/px).')

        if idx_sat_fmt == 0:      # GeoTIFF
            caminho = os.path.join(pasta, 'satelite_oriifsc.tif')
            self._salvar_geotiff(img, caminho, extent, crs)
        elif idx_sat_fmt == 1:    # PNG
            caminho = os.path.join(pasta, 'satelite_oriifsc.png')
            if not img.save(caminho, 'PNG'):
                raise QgsProcessingException('Não foi possível salvar o PNG.')
            self._world_file(pasta, 'satelite_oriifsc.pgw', extent, px_x, px_y)
        else:                     # JPEG
            caminho = os.path.join(pasta, 'satelite_oriifsc.jpg')
            if not img.save(caminho, 'JPEG', 95):
                raise QgsProcessingException('Não foi possível salvar o JPEG.')
            self._world_file(pasta, 'satelite_oriifsc.jgw', extent, px_x, px_y)

        return caminho

    def _tamanho_px(self, extent, dpi, feedback):
        """Pixels de saída na resolução real da folha (mm × DPI).
        Usa a escala salva no Passo 2; cai num proporcional ao DPI se ausente."""
        escala = ler_escala()
        if escala:
            larg_mm = extent.width() / escala * 1000.0
            alt_mm = extent.height() / escala * 1000.0
            larg_px = max(int(round(larg_mm / 25.4 * dpi)), 1)
            alt_px = max(int(round(alt_mm / 25.4 * dpi)), 1)
        else:
            feedback.pushInfo('Escala não encontrada (Passo 2); usando resolução '
                              'proporcional ao DPI.')
            base = int(round((dpi / 300.0) * 5000))
            if extent.width() >= extent.height():
                larg_px = base
                alt_px = max(int(round(base * extent.height() / extent.width())), 1)
            else:
                alt_px = base
                larg_px = max(int(round(base * extent.width() / extent.height())), 1)

        maior = max(larg_px, alt_px)
        if maior > MAX_PX:
            fator = MAX_PX / maior
            larg_px = max(int(larg_px * fator), 1)
            alt_px = max(int(alt_px * fator), 1)
            feedback.pushWarning(f'Resolução limitada a {MAX_PX}px por lado '
                                 'para não estourar a memória.')
        return larg_px, alt_px

    def _salvar_geotiff(self, img, caminho, extent, crs):
        """Salva GeoTIFF sem perdas com georreferência embutida (via GDAL).
        Passa por um PNG temporário (lossless) para não depender do plugin TIFF do Qt."""
        from osgeo import gdal
        tmp_png = caminho + '.tmp.png'
        if not img.save(tmp_png, 'PNG'):
            raise QgsProcessingException('Não foi possível gerar a imagem temporária.')
        try:
            gdal.Translate(
                caminho, tmp_png,
                outputSRS=crs.authid(),
                outputBounds=[extent.xMinimum(), extent.yMaximum(),
                              extent.xMaximum(), extent.yMinimum()],
                creationOptions=['COMPRESS=DEFLATE', 'TILED=YES'])
        finally:
            try:
                os.remove(tmp_png)
            except OSError:
                pass

    def _world_file(self, pasta, nome, extent, px_x, px_y):
        with open(os.path.join(pasta, nome), 'w') as f:
            f.write(f'{px_x}\n0.0\n0.0\n-{px_y}\n'
                    f'{extent.xMinimum() + px_x / 2}\n'
                    f'{extent.yMaximum() - px_y / 2}\n')

    def _carregar_no_projeto(self, caminho, nome, context):
        """Recarrega o arquivo exportado no projeto ao final (na thread principal)."""
        proj = context.project() or QgsProject.instance()
        detalhes = QgsProcessingContext.LayerDetails(nome, proj, nome)
        context.addLayerToLoadOnCompletion(caminho, detalhes)

    # ------------------------------------------------------------------- vetores
    def _exportar_vetor(self, layer, idx_formato, pasta, nome_base):
        usar_shp = (idx_formato == 0)
        ext = 'shp' if usar_shp else 'geojson'
        driver = 'ESRI Shapefile' if usar_shp else 'GeoJSON'
        caminho = os.path.join(pasta, f'{nome_base}_oriifsc.{ext}')

        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = driver
        options.fileEncoding = 'UTF-8'

        QgsVectorFileWriter.writeAsVectorFormatV3(
            layer,
            caminho,
            QgsProject.instance().transformContext(),
            options,
        )
        return caminho
