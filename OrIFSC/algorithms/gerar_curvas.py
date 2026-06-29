import os
import math
import tempfile
from qgis.core import (
    QgsProcessingAlgorithm, QgsProcessingParameterFeatureSource,
    QgsProcessingParameterNumber, QgsProcessingParameterVectorDestination,
    QgsProcessingException, QgsProcessing,
    QgsCoordinateReferenceSystem, QgsCoordinateTransform,
)
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


class GerarCurvasNivel(QgsProcessingAlgorithm):
    LIMITE = 'LIMITE'
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
        return QIcon(os.path.join(os.path.dirname(__file__), '..', 'icons', 'curvas.svg'))

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
        self.addParameter(QgsProcessingParameterNumber(
            self.EQUIDISTANCIA, 'Equidistância (metros)',
            type=QgsProcessingParameterNumber.Integer,
            defaultValue=_equidistancia_padrao()))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.RECORTE, 'Recortar curvas por (camada — opcional: folha ou limite)',
            [QgsProcessing.TypeVectorPolygon], optional=True))
        self.addParameter(QgsProcessingParameterVectorDestination(
            self.OUTPUT_CURVAS, 'Curvas de Nível (copernicus)', type=QgsProcessing.TypeVectorLine))

    def processAlgorithm(self, parameters, context, feedback):
        camada_limite = self.parameterAsSource(parameters, self.LIMITE, context)
        equidistancia = self.parameterAsInt(parameters, self.EQUIDISTANCIA, context)
        camada_recorte = self.parameterAsVectorLayer(parameters, self.RECORTE, context)
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
        for i, (lat_fl, lon_fl) in enumerate(sorted(tiles)):
            feedback.setProgress(int(i * 40 / len(tiles)))
            url = self._copernicus_url(lat_fl, lon_fl)
            tmp = os.path.join(tempfile.gettempdir(), f'orifsc_cop30_{lat_fl}_{lon_fl}.tif')
            if self._cache_valido(tmp):
                feedback.pushInfo(f'Usando tile em cache ({lat_fl}, {lon_fl}).')
            else:
                if os.path.exists(tmp):
                    feedback.pushWarning(
                        f'Tile em cache inválido ou corrompido ({lat_fl}, {lon_fl}); baixando novamente.')
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass
                feedback.pushInfo(f'Baixando tile Copernicus ({lat_fl}, {lon_fl})...')
                try:
                    dados = baixar_bytes(url)
                    with open(tmp, 'wb') as f:
                        f.write(dados)
                except Exception as e:
                    # Remove arquivo parcial para não ser reusado como cache válido.
                    if os.path.exists(tmp):
                        try:
                            os.remove(tmp)
                        except OSError:
                            pass
                    raise QgsProcessingException(
                        f'Falha ao baixar o MDT Copernicus. Verifique sua conexão com a internet.\nErro: {e}')
            tile_files.append(tmp)

        if len(tile_files) > 1:
            feedback.pushInfo('Mesclando tiles...')
            mdt_temp = os.path.join(tempfile.gettempdir(), 'orifsc_mdt_merged.tif')
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
        # Quando há recorte, a suavização vai para um temporário e o recorte
        # escreve a saída final; sem recorte, a suavização já é a saída.
        destino_suave = 'TEMPORARY_OUTPUT' if camada_recorte is not None else saida_curvas
        suavizadas = processing.run('native:smoothgeometry', {
            'INPUT': curvas_brutas,
            'ITERATIONS': 3,
            'OFFSET': 0.25,
            'MAX_ANGLE': 180,
            'OUTPUT': destino_suave,
        }, context=context, feedback=feedback)['OUTPUT']

        if camada_recorte is not None:
            feedback.setProgress(90)
            crs_recorte = camada_recorte.crs()
            # As curvas saem em EPSG:4326 (CRS do MDT). Reprojeta para o CRS da
            # camada de recorte para cortar corretamente e alinhar à folha (UTM).
            entrada_clip = suavizadas
            if crs_recorte != crs_wgs84:
                feedback.pushInfo(f'Reprojetando curvas para {crs_recorte.authid()}...')
                entrada_clip = processing.run('native:reprojectlayer', {
                    'INPUT': suavizadas,
                    'TARGET_CRS': crs_recorte,
                    'OUTPUT': 'TEMPORARY_OUTPUT',
                }, context=context, feedback=feedback)['OUTPUT']

            feedback.pushInfo(f'Recortando curvas pela camada "{camada_recorte.name()}"...')
            processing.run('native:clip', {
                'INPUT': entrada_clip,
                'OVERLAY': camada_recorte,
                'OUTPUT': saida_curvas,
            }, context=context, feedback=feedback)

        feedback.setProgress(100)
        return {self.OUTPUT_CURVAS: saida_curvas}

    @staticmethod
    def _cache_valido(caminho):
        """Retorna True se o arquivo existe e tem tamanho mínimo aceitável."""
        try:
            return os.path.exists(caminho) and os.path.getsize(caminho) >= _TILE_MIN_BYTES
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
        name = f'Copernicus_DSM_COG_10_{ns}{lat_abs:02d}_00_{ew}{lon_abs:03d}_00_DEM'
        return f'https://copernicus-dem-30m.s3.amazonaws.com/{name}/{name}.tif'
