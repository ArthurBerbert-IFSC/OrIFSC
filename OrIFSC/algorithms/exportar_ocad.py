import datetime
import math
import os
import tempfile

from qgis.core import (
    QgsProcessingAlgorithm, QgsProcessingParameterFeatureSource,
    QgsProcessingParameterVectorLayer, QgsProcessingParameterEnum,
    QgsProcessingParameterBoolean, QgsProcessingParameterNumber,
    QgsProcessingParameterFolderDestination,
    QgsProcessingException, QgsProcessing, QgsProject,
    QgsProcessingUtils,
    QgsCoordinateReferenceSystem, QgsCoordinateTransform,
)
from qgis.PyQt.QtGui import QImage, QPainter, QIcon

from ..rede import baixar_varios
from .utils import ocultar_da_toolbox

# --- Web Mercator / tiles do Google -----------------------------------------
TILE = 256
ORIGIN_SHIFT = math.pi * 6378137.0          # meia-circunferência em EPSG:3857
ZOOM_MAX = 20                               # zoom máximo do Google Satellite (lyrs=s)
MAX_PX = 16384                              # teto por lado do mosaico
TILE_URL = 'https://mt{s}.google.com/vt/lyrs=s&x={x}&y={y}&z={z}'
UA = 'Mozilla/5.0 (QGIS OrIFSC plugin)'


def _resolucao(zoom):
    """Metros por pixel (em EPSG:3857) no nível de zoom dado."""
    return (2.0 * ORIGIN_SHIFT) / (TILE * (2 ** zoom))


class ExportarOCAD(QgsProcessingAlgorithm):
    FOLHA = 'FOLHA'
    EXPORTAR_SATELITE = 'EXPORTAR_SATELITE'
    QUALIDADE = 'QUALIDADE'
    CURVAS = 'CURVAS'
    DECL_AUTO = 'DECL_AUTO'
    DECL_MANUAL = 'DECL_MANUAL'
    FORMATO = 'FORMATO'
    PASTA = 'PASTA'

    def tr(self, s):
        return s

    def createInstance(self):
        return ExportarOCAD()

    def flags(self):
        return ocultar_da_toolbox(self)

    def icon(self):
        return QIcon(os.path.join(os.path.dirname(__file__), '..', 'icons', 'exportar.svg'))

    def name(self):
        return 'exportar_ocad'

    def displayName(self):
        return 'Gerar Projeto OCAD / OOM'

    def group(self):
        return 'OrIFSC'

    def groupId(self):
        return 'orientacao'

    def shortHelpString(self):
        from ..acoes.painel import painel_html, INSTRUCOES
        return painel_html('Gerar Projeto OCAD / OOM', INSTRUCOES['exportar_ocad'])

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.FOLHA, 'Camada da Folha (define a área e a georreferência)',
            [QgsProcessing.TypeVectorPolygon]))
        self.addParameter(QgsProcessingParameterBoolean(
            self.EXPORTAR_SATELITE, 'Incluir satélite como mapa de fundo',
            defaultValue=True))
        self.addParameter(QgsProcessingParameterEnum(
            self.QUALIDADE, 'Qualidade da imagem (zoom do Google)',
            options=['Máxima (melhor zoom)', 'Alta (1 nível abaixo)',
                     'Média (2 níveis abaixo)'], defaultValue=0))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.CURVAS, 'Camada de Curvas de Nível (vira objeto no projeto)',
            [QgsProcessing.TypeVectorLine], optional=True))
        self.addParameter(QgsProcessingParameterBoolean(
            self.DECL_AUTO, 'Calcular declinação magnética automaticamente (WMM/NOAA)',
            defaultValue=True))
        self.addParameter(QgsProcessingParameterNumber(
            self.DECL_MANUAL,
            'Declinação magnética manual (graus, leste +; usada se o automático '
            'estiver desmarcado ou falhar)',
            type=QgsProcessingParameterNumber.Double, defaultValue=0.0,
            minValue=-90.0, maxValue=90.0))
        self.addParameter(QgsProcessingParameterEnum(
            self.FORMATO, 'Formato(s) a gerar',
            options=['OCAD (.ocd)',
                     'OpenOrienteering Mapper (.omap)',
                     'Ambos (.ocd e .omap)'],
            defaultValue=0))   # 0 = Só OCAD por padrão
        self.addParameter(QgsProcessingParameterFolderDestination(
            self.PASTA, 'Pasta de saída'))

    def processAlgorithm(self, parameters, context, feedback):
        from .ocad import ProjetoOcad, escrever_omap, escrever_ocd_v10
        from .ocad.geo import declinacao_noaa
        from .ocad.projeto import centro_latlon

        folha = self.parameterAsSource(parameters, self.FOLHA, context)
        exportar_sat = self.parameterAsBool(parameters, self.EXPORTAR_SATELITE, context)
        offset_zoom = self.parameterAsInt(parameters, self.QUALIDADE, context)
        curvas = self.parameterAsVectorLayer(parameters, self.CURVAS, context)
        decl_auto = self.parameterAsBool(parameters, self.DECL_AUTO, context)
        decl_manual = self.parameterAsDouble(parameters, self.DECL_MANUAL, context)
        formato = self.parameterAsEnum(parameters, self.FORMATO, context)
        fazer_ocad = formato in (0, 2)
        fazer_omap = formato in (1, 2)
        pasta = self.parameterAsString(parameters, self.PASTA, context)

        if not pasta:
            raise QgsProcessingException(
                'Selecione uma pasta de saída no seu computador.')
        # A pasta precisa ser permanente: o satélite (.tif) fica junto dos
        # projetos, então um diretório temporário (apagado depois) não serve.
        pasta_abs = os.path.normcase(os.path.abspath(pasta))
        for td in (tempfile.gettempdir(), QgsProcessingUtils.tempFolder()):
            if td and pasta_abs.startswith(os.path.normcase(os.path.abspath(td))):
                raise QgsProcessingException(
                    'A pasta de saída não pode ser um diretório temporário. '
                    'Escolha uma pasta permanente no seu computador — o '
                    'satélite (.tif) precisa ficar junto dos projetos.')
        os.makedirs(pasta, exist_ok=True)

        crs = folha.sourceCrs()
        epsg = self._epsg_utm(crs)
        extent = folha.sourceExtent()
        rect = (extent.xMinimum(), extent.yMinimum(),
                extent.xMaximum(), extent.yMaximum())

        escala = self._ler_escala()

        # 1. Satélite (GeoTIFF georreferenciado, usado como mapa de fundo).
        satelite = None
        if exportar_sat:
            feedback.pushInfo('Montando imagem de satélite...')
            tif = self._exportar_satelite(extent, crs, offset_zoom, pasta, feedback)
            satelite = self._geotransform(tif)
            feedback.pushInfo(
                f'Satélite salvo em: {tif} (não é carregado no QGIS para não '
                'travar com imagens grandes; abra-o manualmente se quiser vê-lo).')
        feedback.setProgress(60)

        # 2. Curvas de nível -> polilinhas no CRS da folha.
        linhas = []
        if curvas is not None:
            feedback.pushInfo('Lendo curvas de nível...')
            linhas = self._curvas_para_linhas(curvas, crs)
            feedback.pushInfo(f'{len(linhas)} curva(s) lida(s).')
        feedback.setProgress(70)

        # 3. Declinação magnética.
        declinacao = decl_manual
        if decl_auto:
            lat, lon = centro_latlon(epsg, (rect[0] + rect[2]) / 2,
                                     (rect[1] + rect[3]) / 2)
            hoje = datetime.date.today()
            feedback.pushInfo('Consultando declinação magnética (NOAA/WMM)...')
            valor = declinacao_noaa(lat, lon, hoje.year, hoje.month, hoje.day)
            if valor is None:
                feedback.pushWarning(
                    'Não foi possível obter a declinação automática; usando o '
                    f'valor manual ({decl_manual:.2f}°).')
            else:
                declinacao = valor
        feedback.pushInfo(f'Declinação usada: {declinacao:.2f}°.')
        feedback.setProgress(80)

        # 4. Monta o projeto e escreve os dois formatos.
        proj = ProjetoOcad(escala, epsg, rect, declinacao, linhas, satelite)
        feedback.pushInfo(f'Convergência meridiana: {proj.convergencia:.2f}° | '
                          f'grivação (norte magnético): {proj.grivacao:.2f}°.')

        resultado = {}
        if fazer_ocad:
            ocd = os.path.join(pasta, 'projeto_orifsc.ocd')
            feedback.pushInfo('Gerando projeto OCAD 10 (.ocd)...')
            escrever_ocd_v10(proj, ocd)
            resultado['OCD'] = ocd
        if fazer_omap:
            omap = os.path.join(pasta, 'projeto_orifsc.omap')
            feedback.pushInfo('Gerando projeto OpenOrienteering Mapper (.omap)...')
            escrever_omap(proj, omap)
            resultado['OMAP'] = omap
        feedback.setProgress(100)

        feedback.pushInfo(f'Projetos gerados em: {pasta}')
        return resultado

    # ------------------------------------------------------------------ apoio
    def _epsg_utm(self, crs):
        authid = crs.authid()                       # ex.: 'EPSG:32722'
        if not authid.startswith('EPSG:'):
            raise QgsProcessingException(
                'A folha precisa estar em um CRS UTM/WGS84 (rode "Definir Local").')
        epsg = int(authid.split(':')[1])
        if not (32601 <= epsg <= 32660 or 32701 <= epsg <= 32760):
            raise QgsProcessingException(
                f'CRS {authid} não é WGS84/UTM. Rode "Definir Local e Criar Folha".')
        return epsg

    def _ler_escala(self):
        from ..acoes.comum import ler_escala
        escala = ler_escala()
        if not escala:
            raise QgsProcessingException(
                'Escala não definida. Rode antes "Definir Local e Criar Folha".')
        return escala

    def _curvas_para_linhas(self, layer, crs_destino):
        """Lê as feições de linha reprojetadas para o CRS da folha como listas
        de (x, y). Itera vértices por parte (robusto a multipartes e curvas)."""
        ct = QgsCoordinateTransform(layer.crs(), crs_destino, QgsProject.instance())
        linhas = []
        for feat in layer.getFeatures():
            geom = feat.geometry()
            if geom is None or geom.isEmpty():
                continue
            geom.transform(ct)
            for parte in geom.parts():
                pts = [(v.x(), v.y()) for v in parte.vertices()]
                if len(pts) >= 2:
                    linhas.append(pts)
        return linhas

    def _geotransform(self, tif):
        """Lê origem/pixel/tamanho do GeoTIFF para posicionar o fundo no OCD."""
        from osgeo import gdal
        ds = gdal.Open(tif)
        gt = ds.GetGeoTransform()
        sat = {'path': tif, 'ulx': gt[0], 'uly': gt[3],
               'px': gt[1], 'py': gt[5],
               'w': ds.RasterXSize, 'h': ds.RasterYSize}
        ds = None
        return sat

    # ------------------------------------------------------------------ satélite
    def _exportar_satelite(self, extent, crs, offset_zoom, pasta, feedback):
        # 1. Área da folha (UTM) -> bbox em EPSG:3857 (CRS das tiles).
        crs3857 = QgsCoordinateReferenceSystem.fromEpsgId(3857)
        rect = QgsCoordinateTransform(
            crs, crs3857, QgsProject.instance()).transformBoundingBox(extent)

        # 2. Melhor zoom que cabe no teto de pixels, menos o offset de qualidade.
        zoom = self._escolher_zoom(rect, offset_zoom, feedback)

        # 3. Baixa e monta o mosaico já recortado na bbox, no melhor zoom.
        img, bounds3857 = self._baixar_mosaico(rect, zoom, feedback)

        # 4. Georreferencia em 3857 e reprojeta para o CRS da folha (alinha às curvas).
        caminho = os.path.join(pasta, 'satelite_orifsc.tif')
        self._georref_e_reprojeta(img, bounds3857, crs, caminho)
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

        mosaico = QImage(nx * TILE, ny * TILE, QImage.Format.Format_RGB888)
        mosaico.fill(0)
        pintor = QPainter(mosaico)
        tiles = [(tx, ty) for ty in range(ty0, ty1 + 1) for tx in range(tx0, tx1 + 1)]
        feedback.pushInfo(f'Baixando {len(tiles)} tiles (zoom {zoom})...')

        # URL por tile, alternando os hosts mt0..mt3 do Google (mais conexões
        # concorrentes num só gerenciador de rede, que limita ~6 por host).
        url_de = {(tx, ty): TILE_URL.format(s=(tx + ty) % 4, x=tx, y=ty, z=zoom)
                  for (tx, ty) in tiles}

        # Download assíncrono numa thread só (ver rede.baixar_varios): evita criar
        # gerenciadores de rede em threads Python, que travavam o QGIS ao fechar.
        dados_por_url = baixar_varios(
            url_de.values(), user_agent=UA, max_conc=24,
            cancelado=feedback.isCanceled,
            progresso=lambda feito, tot: feedback.setProgress(int(50 * feito / tot)))

        falhas = 0
        for (tx, ty) in tiles:
            dados = dados_por_url.get(url_de[(tx, ty)])
            ok = False
            if dados:
                tile = QImage()
                if tile.loadFromData(dados):
                    pintor.drawImage((tx - tx0) * TILE, (ty - ty0) * TILE, tile)
                    ok = True
            if not ok:
                falhas += 1
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

    def _georref_e_reprojeta(self, img, bounds3857, crs, destino_tif):
        """Carimba a georreferência 3857 na imagem e reprojeta para o CRS da folha."""
        from osgeo import gdal
        tmp_png = destino_tif + '.src.png'
        tmp_3857 = destino_tif + '.3857.tif'
        if not img.save(tmp_png, 'PNG'):
            raise QgsProcessingException('Não foi possível gerar a imagem temporária.')
        try:
            ulx, uly, lrx, lry = bounds3857
            ds_3857 = gdal.Translate(tmp_3857, tmp_png, outputSRS='EPSG:3857',
                                     outputBounds=[ulx, uly, lrx, lry])
            ds_3857 = None      # fecha o handle antes do Warp ler o arquivo
            # GeoTIFF do fundo: 3 bandas RGB, SEM canal alpha (o OCAD lê o 4º
            # canal errado → falsa-cor no OCAD 2020 / nem abre no OCAD 10) e
            # COMPRESS=LZW. O OCAD lê o arquivo INTEIRO de uma vez (fRead): com
            # LZW ele fica pequeno no disco (o OCAD lê e descomprime); SEM
            # compressão o arquivo passa de ~290 MB e o OCAD 10 (32-bit) falha o
            # fRead ("Não pôde ler de fRead ..."). OCAD só lê TIFF *stripped* e
            # sem JPEG/DEFLATE → TILED=NO + COMPRESS=LZW. Cantos vazios da rotação
            # ficam brancos (INIT_DEST=255); PHOTOMETRIC=RGB explícito; lanczos
            # reamostra com mais nitidez. NÃO usar TILED=YES ("contains tiles")
            # nem COMPRESS=JPEG/DEFLATE ("compressão não suportada" no OCAD).
            ds_out = gdal.Warp(destino_tif, tmp_3857, dstSRS=crs.authid(),
                               resampleAlg='lanczos',
                               warpOptions=['INIT_DEST=255'],
                               creationOptions=['COMPRESS=LZW', 'TILED=NO',
                                                'BIGTIFF=NO', 'PHOTOMETRIC=RGB'])
            if ds_out is not None:
                ds_out.FlushCache()
            ds_out = None       # fecha/libera o GeoTIFF final (sem handle preso)
        finally:
            for f in (tmp_png, tmp_3857):
                try:
                    os.remove(f)
                except OSError:
                    pass
