import math
import os
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from qgis.core import (
    QgsProcessingAlgorithm, QgsProcessingParameterFeatureSource,
    QgsProcessingParameterVectorLayer, QgsProcessingParameterEnum,
    QgsProcessingParameterBoolean, QgsProcessingParameterFolderDestination,
    QgsProcessingException, QgsProcessing, QgsProject, QgsProcessingContext,
    QgsVectorFileWriter, QgsCoordinateReferenceSystem, QgsCoordinateTransform,
)
from qgis.PyQt.QtGui import QImage, QPainter

# --- Web Mercator / tiles do Google -----------------------------------------
TILE = 256
ORIGIN_SHIFT = math.pi * 6378137.0          # meia-circunferência em EPSG:3857
ZOOM_MAX = 20                               # zoom máximo do Google Satellite (lyrs=s)
MAX_PX = 16384                              # teto por lado do mosaico
TILE_URL = 'https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}'
UA = 'Mozilla/5.0 (QGIS OrIFSC plugin)'


def _resolucao(zoom):
    """Metros por pixel (em EPSG:3857) no nível de zoom dado."""
    return (2.0 * ORIGIN_SHIFT) / (TILE * (2 ** zoom))


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
    QUALIDADE = 'QUALIDADE'
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
        from ..acoes.painel import painel_html, INSTRUCOES
        return painel_html('Exportar para o OCAD', INSTRUCOES['exportar_ocad'])

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
            self.QUALIDADE, 'Qualidade (zoom do Google)',
            options=['Máxima (melhor zoom)', 'Alta (1 nível abaixo)',
                     'Média (2 níveis abaixo)'], defaultValue=0))
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
        offset_zoom = self.parameterAsInt(parameters, self.QUALIDADE, context)
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
            img_path = self._exportar_satelite(extent, crs, idx_sat_fmt, offset_zoom,
                                               pasta, feedback)
            saidas['SATELITE'] = img_path
            self._carregar_no_projeto(img_path, 'Satélite (exportado)', context)
        feedback.setProgress(70)

        if curvas is not None:
            feedback.pushInfo('Exportando curvas de nível...')
            saidas['CURVAS'] = self._exportar_vetor(curvas, idx_formato, pasta, 'curvas')
        feedback.setProgress(85)

        if limite is not None:
            feedback.pushInfo('Exportando camada de limite...')
            saidas['LIMITE'] = self._exportar_vetor(limite, idx_formato, pasta, 'limite')
        feedback.setProgress(100)

        feedback.pushInfo(f'Exportação concluída. Arquivos em: {pasta}')
        return saidas

    # ------------------------------------------------------------------ satélite
    def _exportar_satelite(self, extent, crs, idx_sat_fmt, offset_zoom, pasta, feedback):
        # 1. Área da folha (UTM) -> bbox em EPSG:3857 (CRS das tiles).
        crs3857 = QgsCoordinateReferenceSystem.fromEpsgId(3857)
        rect = QgsCoordinateTransform(
            crs, crs3857, QgsProject.instance()).transformBoundingBox(extent)

        # 2. Melhor zoom que cabe no teto de pixels, menos o offset de qualidade.
        zoom = self._escolher_zoom(rect, offset_zoom, feedback)

        # 3. Baixa e monta o mosaico já recortado na bbox, no melhor zoom.
        img, bounds3857 = self._baixar_mosaico(rect, zoom, feedback)

        # 4. Georreferencia em 3857 e reprojeta para o CRS da folha (alinha às curvas).
        tif_utm = os.path.join(pasta, '_satelite_utm.tif')
        self._georref_e_reprojeta(img, bounds3857, crs, tif_utm)

        # 5. Salva no formato escolhido.
        if idx_sat_fmt == 0:
            caminho = os.path.join(pasta, 'satelite_oriifsc.tif')
            os.replace(tif_utm, caminho)
        else:
            ext, nome_wld = ('png', 'pgw') if idx_sat_fmt == 1 else ('jpg', 'jgw')
            caminho = os.path.join(pasta, f'satelite_oriifsc.{ext}')
            self._tif_para_imagem(tif_utm, caminho, ext, pasta, nome_wld)
            try:
                os.remove(tif_utm)
            except OSError:
                pass
        return caminho

    def _escolher_zoom(self, rect, offset_zoom, feedback):
        """Maior zoom (<= ZOOM_MAX) cujo mosaico cabe em MAX_PX por lado."""
        for z in range(ZOOM_MAX, 0, -1):
            res = _resolucao(z)
            if rect.width() / res <= MAX_PX and rect.height() / res <= MAX_PX:
                zoom = max(1, z - offset_zoom)
                if zoom != z:
                    feedback.pushInfo(f'Zoom {z} reduzido para {zoom} (qualidade).')
                feedback.pushInfo(f'Melhor zoom do Google para a folha: {zoom}.')
                return zoom
        return 1

    def _baixar_mosaico(self, rect, zoom, feedback):
        """Baixa as tiles que cobrem a bbox e devolve (QImage RGB recortada,
        (ulx, uly, lrx, lry) em EPSG:3857)."""
        res = _resolucao(zoom)
        px_min = (rect.xMinimum() + ORIGIN_SHIFT) / res
        px_max = (rect.xMaximum() + ORIGIN_SHIFT) / res
        py_min = (ORIGIN_SHIFT - rect.yMaximum()) / res     # topo (y invertido)
        py_max = (ORIGIN_SHIFT - rect.yMinimum()) / res     # base

        tx0, tx1 = int(px_min // TILE), int((px_max - 1e-6) // TILE)
        ty0, ty1 = int(py_min // TILE), int((py_max - 1e-6) // TILE)
        nx, ny = tx1 - tx0 + 1, ty1 - ty0 + 1

        mosaico = QImage(nx * TILE, ny * TILE, QImage.Format_RGB888)
        mosaico.fill(0)
        pintor = QPainter(mosaico)
        tiles = [(tx, ty) for ty in range(ty0, ty1 + 1) for tx in range(tx0, tx1 + 1)]
        feedback.pushInfo(f'Baixando {len(tiles)} tiles (zoom {zoom})...')

        falhas = 0
        with ThreadPoolExecutor(max_workers=16) as pool:
            for i, (coord, dados) in enumerate(
                    zip(tiles, pool.map(lambda c: self._baixar_tile(*c, zoom), tiles))):
                if feedback.isCanceled():
                    break
                tx, ty = coord
                ok = False
                if dados:
                    tile = QImage()
                    if tile.loadFromData(dados):
                        pintor.drawImage((tx - tx0) * TILE, (ty - ty0) * TILE, tile)
                        ok = True
                if not ok:
                    falhas += 1
                if i % 25 == 0:
                    feedback.setProgress(int(60 * i / len(tiles)))
        pintor.end()
        if falhas == len(tiles):
            raise QgsProcessingException(
                'Não foi possível baixar nenhuma tile do Google. '
                'Verifique a conexão com a internet.')
        if falhas:
            feedback.pushWarning(f'{falhas} tile(s) não baixaram (áreas pretas).')

        # Recorta o mosaico exatamente na bbox e recalcula os limites 3857.
        esq, topo = int(round(px_min - tx0 * TILE)), int(round(py_min - ty0 * TILE))
        larg = max(1, int(round(px_max - px_min)))
        alt = max(1, int(round(py_max - py_min)))
        recorte = mosaico.copy(esq, topo, larg, alt)

        ulx = (tx0 * TILE + esq) * res - ORIGIN_SHIFT
        uly = ORIGIN_SHIFT - (ty0 * TILE + topo) * res
        bounds = (ulx, uly, ulx + larg * res, uly - alt * res)
        feedback.pushInfo(f'Mosaico: {recorte.width()}×{recorte.height()}px '
                          f'({res:.3f} m/px em 3857).')
        return recorte, bounds

    def _baixar_tile(self, tx, ty, zoom):
        url = TILE_URL.format(x=tx, y=ty, z=zoom)
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=20) as resp:
                return resp.read()
        except Exception:
            return None

    def _georref_e_reprojeta(self, img, bounds3857, crs, destino_tif):
        """Carimba a georreferência 3857 na imagem e reprojeta para o CRS da folha."""
        from osgeo import gdal
        tmp_png = destino_tif + '.src.png'
        tmp_3857 = destino_tif + '.3857.tif'
        if not img.save(tmp_png, 'PNG'):
            raise QgsProcessingException('Não foi possível gerar a imagem temporária.')
        try:
            ulx, uly, lrx, lry = bounds3857
            gdal.Translate(tmp_3857, tmp_png, outputSRS='EPSG:3857',
                           outputBounds=[ulx, uly, lrx, lry])
            # dstAlpha: os cantos vazios da reprojeção (faixa preta) viram
            # transparentes (vale em GeoTIFF/PNG; JPEG não tem alfa).
            # Lanczos reamostra com mais nitidez que cúbica.
            gdal.Warp(destino_tif, tmp_3857, dstSRS=crs.authid(),
                      resampleAlg='lanczos', multithread=True, dstAlpha=True,
                      creationOptions=['COMPRESS=DEFLATE', 'TILED=YES'])
        finally:
            for f in (tmp_png, tmp_3857):
                try:
                    os.remove(f)
                except OSError:
                    pass

    def _tif_para_imagem(self, tif_utm, caminho, ext, pasta, nome_wld):
        """Converte o GeoTIFF UTM para PNG/JPEG + world file (.pgw/.jgw)."""
        from osgeo import gdal
        drv = 'PNG' if ext == 'png' else 'JPEG'
        # PNG mantém o alfa (transparência); JPEG não suporta, usa só RGB.
        if ext == 'jpg':
            opts = {'creationOptions': ['QUALITY=95'], 'bandList': [1, 2, 3]}
        else:
            opts = {}
        gdal.Translate(caminho, tif_utm, format=drv, **opts)

        ds = gdal.Open(tif_utm)
        gt = ds.GetGeoTransform()
        ds = None
        nome = os.path.splitext(os.path.basename(caminho))[0] + '.' + nome_wld
        with open(os.path.join(pasta, nome), 'w') as f:
            f.write(f'{gt[1]}\n0.0\n0.0\n{gt[5]}\n'
                    f'{gt[0] + gt[1] / 2}\n{gt[3] + gt[5] / 2}\n')

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
