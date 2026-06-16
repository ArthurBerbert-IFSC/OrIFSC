from qgis.core import (
    QgsProcessingAlgorithm, QgsProcessingParameterString,
    QgsProcessingParameterNumber, QgsProcessingParameterEnum,
    QgsProcessingException, QgsCoordinateReferenceSystem,
    QgsCoordinateTransform, QgsPointXY, QgsVectorLayer,
    QgsRasterLayer, QgsFeature, QgsGeometry, QgsRectangle,
    QgsProject, QgsSymbol, QgsSingleSymbolRenderer,
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor


class PrepararAmbienteOrientacao(QgsProcessingAlgorithm):
    COORD_TEXT = 'COORD_TEXT'
    ESCALA = 'ESCALA'
    TAMANHO_FOLHA = 'TAMANHO_FOLHA'
    ORIENTACAO = 'ORIENTACAO'

    def tr(self, s): return s
    def createInstance(self): return PrepararAmbienteOrientacao()
    def name(self): return 'preparar_ambiente_orientacao'
    def displayName(self): return '1. Preparar Ambiente de Mapeamento'
    def group(self): return 'Orientação'
    def groupId(self): return 'orientacao'
    def shortHelpString(self): return 'Configura o projeto UTM, gera a folha de referência, a camada limite e carrega o satélite.'

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterString(
            self.COORD_TEXT, 'Coordenada Google Maps (ex: -27.5926, -48.5431)', defaultValue=''))
        self.addParameter(QgsProcessingParameterNumber(
            self.ESCALA, 'Denominador da Escala (ex: 4000)',
            type=QgsProcessingParameterNumber.Integer, defaultValue=4000))
        self.addParameter(QgsProcessingParameterEnum(
            self.TAMANHO_FOLHA, 'Tamanho da Folha', options=['A3', 'A4', 'A5'], defaultValue=1))
        self.addParameter(QgsProcessingParameterEnum(
            self.ORIENTACAO, 'Orientação da Folha', options=['Paisagem', 'Retrato'], defaultValue=0))

    def processAlgorithm(self, parameters, context, feedback):
        coord_str = self.parameterAsString(parameters, self.COORD_TEXT, context)
        escala = self.parameterAsInt(parameters, self.ESCALA, context)
        idx_folha = self.parameterAsInt(parameters, self.TAMANHO_FOLHA, context)
        idx_orientacao = self.parameterAsInt(parameters, self.ORIENTACAO, context)

        try:
            partes = coord_str.replace(' ', '').split(',')
            lat = float(partes[0])
            lon = float(partes[1])
        except Exception:
            raise QgsProcessingException(
                'Formato inválido. Use Lat, Lon como no Google Maps (ex: -27.5926, -48.5431).')

        fuso = int((lon + 180) / 6) + 1
        epsg_code = 32600 + fuso if lat >= 0 else 32700 + fuso

        crs_wgs84 = QgsCoordinateReferenceSystem.fromEpsgId(4326)
        crs_utm = QgsCoordinateReferenceSystem.fromEpsgId(epsg_code)
        transform = QgsCoordinateTransform(crs_wgs84, crs_utm, QgsProject.instance())
        ponto_utm = transform.transform(QgsPointXY(lon, lat))

        dimensoes = {'A3': (420, 297), 'A4': (297, 210), 'A5': (210, 148)}
        larg_mm, alt_mm = dimensoes[['A3', 'A4', 'A5'][idx_folha]]
        if idx_orientacao == 1:
            larg_mm, alt_mm = alt_mm, larg_mm

        larg_m = (larg_mm / 1000.0) * escala
        alt_m = (alt_mm / 1000.0) * escala

        x_min = ponto_utm.x() - larg_m / 2
        x_max = ponto_utm.x() + larg_m / 2
        y_min = ponto_utm.y() - alt_m / 2
        y_max = ponto_utm.y() + alt_m / 2

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

        camada_limite = QgsVectorLayer(f'Polygon?crs=EPSG:{epsg_code}', 'limite', 'memory')

        QgsProject.instance().setCrs(crs_utm)

        url_google = ('type=xyz&url=https://mt1.google.com/vt/'
                      'lyrs%3Ds%26x%3D%7Bx%7D%26y%3D%7By%7D%26z%3D%7Bz%7D&zmax=20&zmin=0')
        camada_google = QgsRasterLayer(url_google, 'Google Satellite', 'wms')
        if camada_google.isValid():
            QgsProject.instance().addMapLayer(camada_google)

        QgsProject.instance().addMapLayer(camada_limite)
        QgsProject.instance().addMapLayer(camada_folha)

        feedback.pushInfo(f'Projeto configurado em EPSG:{epsg_code} (UTM fuso {fuso})')
        return {}
