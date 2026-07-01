import os
import math
import tempfile

from qgis.core import (
    QgsProcessingAlgorithm, QgsProcessingParameterFeatureSource,
    QgsProcessingParameterNumber, QgsProcessingParameterFeatureSink,
    QgsProcessingParameterEnum,
    QgsProcessingException, QgsProcessing,
    QgsCoordinateReferenceSystem, QgsCoordinateTransform,
    QgsVectorLayer, QgsFields, QgsField, QgsFeature, QgsFeatureSink,
    QgsGeometry, QgsPointXY, QgsWkbTypes,
)
from qgis.PyQt.QtCore import QVariant
import processing
from qgis.PyQt.QtGui import QIcon

from ..rede import baixar_bytes
from .utils import ocultar_da_toolbox

# Tamanho mínimo aceitável para um tile Copernicus válido (1 KB).
# Arquivos menores indicam download corrompido ou incompleto.
_TILE_MIN_BYTES = 1024


def _equidistancia_padrao():
    """Equidistância padrão definida em OrIFSC → Configurações (fallback 5 m)."""
    try:
        from qgis.core import QgsSettings
        return int(QgsSettings().value('OrIFSC/equidistancia_padrao', 5))
    except Exception:
        return 5


def _chaikin(pts, iteracoes=2):
    """Suaviza uma polilinha por corner-cutting de Chaikin (pura aritmética).

    Não usa o motor de geometria do QGIS (que estava travando), então é seguro
    para qualquer dado. Mantém os extremos de linhas abertas e trata linhas
    fechadas (anéis) de forma cíclica. `pts` é uma lista de (x, y).
    """
    if len(pts) < 3:
        return pts
    fechada = pts[0] == pts[-1]
    if fechada:
        base = pts[:-1]                        # remove o ponto repetido do fecho
        for _ in range(iteracoes):
            novo = []
            m = len(base)
            for i in range(m):
                p0 = base[i]
                p1 = base[(i + 1) % m]
                novo.append((0.75 * p0[0] + 0.25 * p1[0],
                             0.75 * p0[1] + 0.25 * p1[1]))
                novo.append((0.25 * p0[0] + 0.75 * p1[0],
                             0.25 * p0[1] + 0.75 * p1[1]))
            base = novo
        return base + [base[0]]                # re-fecha o anel
    for _ in range(iteracoes):
        novo = [pts[0]]
        for i in range(len(pts) - 1):
            p0 = pts[i]
            p1 = pts[i + 1]
            novo.append((0.75 * p0[0] + 0.25 * p1[0],
                         0.75 * p0[1] + 0.25 * p1[1]))
            novo.append((0.25 * p0[0] + 0.75 * p1[0],
                         0.25 * p0[1] + 0.75 * p1[1]))
        novo.append(pts[-1])
        pts = novo
    return pts


class GerarCurvasNivel(QgsProcessingAlgorithm):
    LIMITE = 'LIMITE'
    FONTE_MDT = 'FONTE_MDT'
    EQUIDISTANCIA = 'EQUIDISTANCIA'
    RECORTE = 'RECORTE'
    OUTPUT_CURVAS = 'OUTPUT_CURVAS'

    def tr(self, s):
        return s

    def createInstance(self):
        return GerarCurvasNivel()

    def flags(self):
        return ocultar_da_toolbox(self)

    def icon(self):
        return QIcon(os.path.join(os.path.dirname(__file__),
                                  '..', 'icons', 'curvas.svg'))

    def name(self):
        return 'gerar_curvas_nivel'

    def displayName(self):
        return 'Gerar Curvas de Nível Automáticas'

    def group(self):
        return 'OrIFSC'

    def groupId(self):
        return 'orientacao'

    def shortHelpString(self):
        from ..acoes.painel import painel_html, INSTRUCOES
        return painel_html('Gerar Curvas de Nível', INSTRUCOES['gerar_curvas'])

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.LIMITE, 'Camada da área a mapear (define a extensão do MDT)',
            [QgsProcessing.TypeVectorPolygon]))
        self.addParameter(QgsProcessingParameterEnum(
            self.FONTE_MDT, 'Fonte do MDT',
            options=['Copernicus 30 m (global, gratuito)',
                     'SIG@SC — MDT de SC (WCS, alta resolução; só SC)'],
            defaultValue=0))
        self.addParameter(QgsProcessingParameterNumber(
            self.EQUIDISTANCIA, 'Equidistância (metros)',
            type=QgsProcessingParameterNumber.Integer,
            defaultValue=_equidistancia_padrao()))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.RECORTE, 'Recortar curvas por (camada — opcional: folha/limite)',
            [QgsProcessing.TypeVectorPolygon], optional=True))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT_CURVAS, 'Curvas de Nível',
            type=QgsProcessing.TypeVectorLine))

    def processAlgorithm(self, parameters, context, feedback):
        camada_limite = self.parameterAsSource(parameters, self.LIMITE, context)
        equidistancia = self.parameterAsInt(
            parameters, self.EQUIDISTANCIA, context)
        camada_recorte = self.parameterAsVectorLayer(
            parameters, self.RECORTE, context)

        # --- 1. Adquire o MDT: Copernicus 30 m (global) ou SIG@SC (alta res.) -
        fonte = self.parameterAsEnum(parameters, self.FONTE_MDT, context)
        if fonte == 1:
            mdt_temp = self._baixar_mdt_sc(
                camada_limite.sourceExtent(), camada_limite.sourceCrs(),
                feedback)
        else:
            mdt_temp = self._baixar_copernicus(camada_limite, context, feedback)

        # --- 2. Curvas brutas (gdal:contour) ---------------------------------
        feedback.setProgress(45)
        feedback.pushInfo('Gerando curvas brutas...')
        curvas_brutas = processing.run('gdal:contour', {
            'INPUT': mdt_temp,
            'BAND': 1,
            'INTERVAL': equidistancia,
            'FIELD_NAME': 'ELEV',
            'CREATE_3D': False,
            'OUTPUT': 'TEMPORARY_OUTPUT',
        }, context=context, feedback=feedback)['OUTPUT']

        camada_brutas = QgsVectorLayer(curvas_brutas, 'curvas_brutas', 'ogr')
        if not camada_brutas.isValid():
            raise QgsProcessingException(
                'Não foi possível ler as curvas brutas geradas.')
        crs_curvas = camada_brutas.crs()

        # --- 3. Geometria de recorte (opcional), no CRS das curvas -----------
        geom_recorte = None
        if camada_recorte is not None:
            feedback.pushInfo(
                f'Preparando recorte por "{camada_recorte.name()}"...')
            ct_rec = QgsCoordinateTransform(camada_recorte.crs(), crs_curvas,
                                            context.transformContext())
            partes_rec = []
            for f in camada_recorte.getFeatures():
                gg = f.geometry()
                if gg is None or gg.isEmpty():
                    continue
                gg = QgsGeometry(gg)
                try:
                    gg.transform(ct_rec)
                except Exception:
                    continue
                partes_rec.append(gg)
            if partes_rec:
                geom_recorte = QgsGeometry.unaryUnion(partes_rec)
                if geom_recorte is not None and not geom_recorte.isGeosValid():
                    geom_recorte = geom_recorte.makeValid()

        # --- 4. Saída (FeatureSink) com nome limpo ---------------------------
        campos = QgsFields()
        campos.append(QgsField('ELEV', QVariant.Double))
        sink, dest_id = self.parameterAsSink(
            parameters, self.OUTPUT_CURVAS, context,
            campos, QgsWkbTypes.LineString, crs_curvas)
        if sink is None:
            raise QgsProcessingException(
                'Não foi possível criar a camada de saída de curvas.')

        def _gravar(geom, elev):
            """Grava a geometria (separando multipartes em linhas) no sink."""
            if geom is None or geom.isEmpty():
                return
            for sub in geom.parts():
                pts = [QgsPointXY(v.x(), v.y()) for v in sub.vertices()]
                if len(pts) < 2:
                    continue
                nf = QgsFeature(campos)
                nf.setGeometry(QgsGeometry.fromPolylineXY(pts))
                nf.setAttribute(0, elev)
                sink.addFeature(nf, QgsFeatureSink.FastInsert)

        # --- 5. Suaviza (Chaikin, em Python) e recorta, feição a feição ------
        feedback.setProgress(55)
        feedback.pushInfo('Suavizando e gravando curvas...')
        total = max(1, camada_brutas.featureCount())
        nomes_campos = [c.name() for c in camada_brutas.fields()]
        tem_elev = 'ELEV' in nomes_campos
        for i, feat in enumerate(camada_brutas.getFeatures()):
            if feedback.isCanceled():
                break
            if i % 200 == 0:
                feedback.setProgress(55 + int(43 * i / total))
            g = feat.geometry()
            if g is None or g.isEmpty():
                continue
            elev = feat['ELEV'] if tem_elev else None
            for parte in g.parts():
                pts = [(v.x(), v.y()) for v in parte.vertices()]
                if len(pts) < 2:
                    continue
                pts_s = _chaikin(pts, 2)
                geom_s = QgsGeometry.fromPolylineXY(
                    [QgsPointXY(x, y) for x, y in pts_s])
                if geom_recorte is not None:
                    try:
                        geom_s = geom_s.intersection(geom_recorte)
                    except Exception:
                        continue
                _gravar(geom_s, elev)

        feedback.setProgress(100)
        return {self.OUTPUT_CURVAS: dest_id}

    # ------------------------------------------------------------ fontes de MDT
    def _baixar_copernicus(self, camada_limite, context, feedback):
        """Baixa (ou usa do cache) os tiles do MDT Copernicus 30 m que cobrem a
        folha e devolve o caminho do raster (mesclado se houver mais de um)."""
        crs_wgs84 = QgsCoordinateReferenceSystem('EPSG:4326')
        transform = QgsCoordinateTransform(
            camada_limite.sourceCrs(), crs_wgs84, context.transformContext())
        ext = transform.transformBoundingBox(camada_limite.sourceExtent())
        margem = 0.003
        tiles = self._tiles_necessarios(
            ext.yMinimum() - margem, ext.yMaximum() + margem,
            ext.xMinimum() - margem, ext.xMaximum() + margem)

        tile_files = []
        for i, (lat_fl, lon_fl) in enumerate(sorted(tiles)):
            feedback.setProgress(int(i * 35 / len(tiles)))
            url = self._copernicus_url(lat_fl, lon_fl)
            tmp = os.path.join(tempfile.gettempdir(),
                               f'orifsc_cop30_{lat_fl}_{lon_fl}.tif')
            if self._cache_valido(tmp):
                feedback.pushInfo(f'Usando tile em cache ({lat_fl}, {lon_fl}).')
            else:
                if os.path.exists(tmp):
                    feedback.pushWarning(
                        f'Tile em cache inválido ({lat_fl}, {lon_fl}); '
                        'baixando novamente.')
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass
                feedback.pushInfo(
                    f'Baixando tile Copernicus ({lat_fl}, {lon_fl})...')
                try:
                    dados = baixar_bytes(url)
                    with open(tmp, 'wb') as f:
                        f.write(dados)
                except Exception as e:
                    if os.path.exists(tmp):
                        try:
                            os.remove(tmp)
                        except OSError:
                            pass
                    raise QgsProcessingException(
                        'Falha ao baixar o MDT Copernicus. '
                        f'Verifique sua conexão com a internet.\nErro: {e}')
            tile_files.append(tmp)

        if len(tile_files) > 1:
            feedback.pushInfo('Mesclando tiles...')
            mdt_temp = os.path.join(
                tempfile.gettempdir(), 'orifsc_mdt_merged.tif')
            processing.run('gdal:merge', {
                'INPUT': tile_files,
                'PCT': False, 'SEPARATE': False,
                'NODATA_INPUT': None, 'NODATA_OUTPUT': None,
                'DATA_TYPE': 5, 'OUTPUT': mdt_temp,
            }, context=context, feedback=feedback)
            return mdt_temp
        return tile_files[0]

    def _baixar_mdt_sc(self, extent, crs, feedback):
        """Baixa o MDT de SC pelo WCS do SIG@SC, recortado na folha, como GeoTIFF
        de elevacao (valores reais, nao imagem) para curvas de alta resolucao.

        Roda na thread do algoritmo (nao trava o QGIS). Descobre a coverage do
        MDT pelo GetCapabilities (driver WCS do GDAL) casando pelo nome, e
        recorta/reprojeta para o CRS da folha. O SIG@SC costuma ser lento.
        """
        from osgeo import gdal
        gdal.UseExceptions()
        gdal.SetConfigOption('GDAL_HTTP_TIMEOUT', '120')
        gdal.SetConfigOption('GDAL_HTTP_CONNECTTIMEOUT', '30')
        url = 'http://sigsc.sc.gov.br/sigserver/ows'

        feedback.pushInfo('Consultando o WCS do SIG@SC (pode demorar)...')
        coverage = None
        for ver in ('1.0.0', '2.0.1', '1.1.1'):
            if feedback.isCanceled():
                return None
            try:
                svc = ('<WCS_GDAL><ServiceURL>%s</ServiceURL>'
                       '<Version>%s</Version></WCS_GDAL>' % (url, ver))
                ds = gdal.Open(svc)
                if ds is None:
                    continue
                for nome, desc in (ds.GetSubDatasets() or []):
                    low = (nome + ' ' + desc).lower()
                    if any(k in low for k in
                           ('modelo digital de terreno', 'mdt', 'terreno')):
                        coverage = nome
                        feedback.pushInfo(f'Coverage do MDT encontrada: {desc}')
                        break
                ds = None
                if coverage:
                    break
            except Exception as e:
                feedback.pushInfo(f'WCS {ver} nao respondeu ({e}).')
        if not coverage:
            raise QgsProcessingException(
                'Nao localizei o MDT no WCS do SIG@SC (servico fora do ar/lento, '
                'ou a camada mudou de nome). Tente de novo ou use o Copernicus.')

        marg = 50.0
        bbox = [extent.xMinimum() - marg, extent.yMinimum() - marg,
                extent.xMaximum() + marg, extent.yMaximum() + marg]
        destino = os.path.join(tempfile.gettempdir(), 'orifsc_mdt_sc.tif')
        feedback.pushInfo('Baixando o recorte do MDT de SC (alta resolucao)...')
        opcoes = gdal.WarpOptions(
            dstSRS=crs.authid(), outputBounds=bbox,
            outputBoundsSRS=crs.authid(), resampleAlg='bilinear',
            format='GTiff', callback=self._cb_gdal_curvas(feedback))
        ds_out = gdal.Warp(destino, coverage, options=opcoes)
        if ds_out is None:
            if feedback.isCanceled():
                raise QgsProcessingException('Operacao cancelada.')
            raise QgsProcessingException(
                'Falha ao baixar o MDT de SC pelo WCS do SIG@SC.')
        ds_out.FlushCache()
        ds_out = None
        return destino

    @staticmethod
    def _cb_gdal_curvas(feedback):
        """Callback de progresso do GDAL (0..1) do download do MDT (barra 0-40%)."""
        def _cb(complete, message, _d):
            if feedback.isCanceled():
                return 0
            feedback.setProgress(int(40 * complete))
            return 1
        return _cb

    # ------------------------------------------------------------------ apoio
    @staticmethod
    def _cache_valido(caminho):
        """Retorna True se o arquivo existe e tem tamanho mínimo aceitável."""
        try:
            return (os.path.exists(caminho)
                    and os.path.getsize(caminho) >= _TILE_MIN_BYTES)
        except OSError:
            return False

    def _tiles_necessarios(self, min_lat, max_lat, min_lon, max_lon):
        tiles = set()
        lat = math.floor(min_lat)
        while lat <= math.floor(max_lat):
            lon = math.floor(min_lon)
            while lon <= math.floor(max_lon):
                tiles.add((lat, lon))
                lon += 1
            lat += 1
        return tiles

    def _copernicus_url(self, lat_floor, lon_floor):
        ns = 'N' if lat_floor >= 0 else 'S'
        ew = 'E' if lon_floor >= 0 else 'W'
        lat_abs = abs(lat_floor)
        lon_abs = abs(lon_floor)
        name = (f'Copernicus_DSM_COG_10_{ns}{lat_abs:02d}_00_'
                f'{ew}{lon_abs:03d}_00_DEM')
        return f'https://copernicus-dem-30m.s3.amazonaws.com/{name}/{name}.tif'
