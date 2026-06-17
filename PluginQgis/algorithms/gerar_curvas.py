import os
import math
import tempfile
import urllib.request
from qgis.core import (
    QgsProcessingAlgorithm, QgsProcessingParameterFeatureSource,
    QgsProcessingParameterNumber, QgsProcessingParameterVectorDestination,
    QgsProcessingException, QgsProcessing,
    QgsCoordinateReferenceSystem, QgsCoordinateTransform,
)
import processing


def _ocultar_da_toolbox(alg):
    """Marca o algoritmo como oculto da Caixa de Ferramentas (só acessível pelo menu).
    Compatível com QGIS antigo (FlagHideFromToolbox) e novo (Qgis.ProcessingAlgorithmFlag)."""
    flags = super(type(alg), alg).flags()
    try:
        return flags | QgsProcessingAlgorithm.FlagHideFromToolbox
    except AttributeError:
        from qgis.core import Qgis
        return flags | Qgis.ProcessingAlgorithmFlag.HideFromToolbox


class GerarCurvasNivel(QgsProcessingAlgorithm):
    LIMITE = 'LIMITE'
    EQUIDISTANCIA = 'EQUIDISTANCIA'
    OUTPUT_CURVAS = 'OUTPUT_CURVAS'

    def tr(self, s): return s
    def createInstance(self): return GerarCurvasNivel()
    def flags(self): return _ocultar_da_toolbox(self)
    def name(self): return 'gerar_curvas_nivel'
    def displayName(self): return '4. Gerar Curvas de Nível Automáticas'
    def group(self): return 'Orientação'
    def groupId(self): return 'orientacao'
    def shortHelpString(self): return ('Baixa o MDT Copernicus 30m (gratuito, sem API key) '
                                       'e gera curvas de nível suavizadas para a área da folha.')

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.LIMITE, 'Camada da Folha (área a mapear)', [QgsProcessing.TypeVectorPolygon]))
        self.addParameter(QgsProcessingParameterNumber(
            self.EQUIDISTANCIA, 'Equidistância (metros)',
            type=QgsProcessingParameterNumber.Integer, defaultValue=5))
        self.addParameter(QgsProcessingParameterVectorDestination(
            self.OUTPUT_CURVAS, 'Salvar Curvas como'))

    def processAlgorithm(self, parameters, context, feedback):
        camada_limite = self.parameterAsSource(parameters, self.LIMITE, context)
        equidistancia = self.parameterAsInt(parameters, self.EQUIDISTANCIA, context)
        saida_curvas = self.parameterAsOutputLayer(parameters, self.OUTPUT_CURVAS, context)

        crs_wgs84 = QgsCoordinateReferenceSystem('EPSG:4326')
        transform = QgsCoordinateTransform(camada_limite.sourceCrs(), crs_wgs84, context.project())
        ext = transform.transformBoundingBox(camada_limite.sourceExtent())

        margem = 0.003
        tiles = self._tiles_necessarios(
            ext.yMinimum() - margem, ext.yMaximum() + margem,
            ext.xMinimum() - margem, ext.xMaximum() + margem
        )

        tile_files = []
        for i, (lat_fl, lon_fl) in enumerate(tiles):
            feedback.setProgress(int(i * 40 / len(tiles)))
            url = self._copernicus_url(lat_fl, lon_fl)
            tmp = os.path.join(tempfile.gettempdir(), f'oriifsc_cop30_{lat_fl}_{lon_fl}.tif')
            if not os.path.exists(tmp):
                feedback.pushInfo(f'Baixando tile Copernicus ({lat_fl}, {lon_fl})...')
                try:
                    urllib.request.urlretrieve(url, tmp)
                except Exception as e:
                    raise QgsProcessingException(
                        f'Falha ao baixar o MDT Copernicus. Verifique sua conexão com a internet.\nErro: {e}')
            tile_files.append(tmp)

        if len(tile_files) > 1:
            feedback.pushInfo('Mesclando tiles...')
            mdt_temp = os.path.join(tempfile.gettempdir(), 'oriifsc_mdt_merged.tif')
            processing.run('gdal:merge', {
                'INPUT': tile_files,
                'PCT': False, 'SEPARATE': False,
                'NODATA_INPUT': None, 'NODATA_OUTPUT': None,
                'DATA_TYPE': 5, 'OUTPUT': mdt_temp,
            }, context=context, feedback=feedback)
        else:
            mdt_temp = tile_files[0]

        feedback.setProgress(50)
        feedback.pushInfo('Gerando curvas brutas...')
        curvas_brutas = processing.run('gdal:contour', {
            'INPUT': mdt_temp,
            'BAND': 1,
            'INTERVAL': equidistancia,
            'FIELD_NAME': 'ELEV',
            'CREATE_3D': False,
            'OUTPUT': 'TEMPORARY_OUTPUT',
        }, context=context, feedback=feedback)['OUTPUT']

        feedback.setProgress(80)
        feedback.pushInfo('Suavizando geometria...')
        processing.run('native:smoothgeometry', {
            'INPUT': curvas_brutas,
            'ITERATIONS': 3,
            'OFFSET': 0.25,
            'MAX_ANGLE': 180,
            'OUTPUT': saida_curvas,
        }, context=context, feedback=feedback)

        feedback.setProgress(100)
        return {self.OUTPUT_CURVAS: saida_curvas}

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
        name = f'Copernicus_DSM_COG_10_{ns}{lat_abs:02d}_00_{ew}{lon_abs:03d}_00_DEM'
        return f'https://copernicus-dem-30m.s3.amazonaws.com/{name}/{name}.tif'
