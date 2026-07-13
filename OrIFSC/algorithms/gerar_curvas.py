"""Algoritmo Processing para geração de curvas de nível no OrIFSC."""

import os
import math
from typing import Any, Optional, Set, Tuple

import numpy as np
from qgis.core import (
    Qgis,
    QgsProcessingAlgorithm, QgsProcessingParameterFeatureSource,
    QgsProcessingParameterNumber, QgsProcessingParameterFeatureSink,
    QgsProcessingException, QgsProcessingUtils,
    QgsCoordinateReferenceSystem, QgsCoordinateTransform,
    QgsVectorLayer, QgsFields, QgsField, QgsFeature, QgsFeatureSink,
    QgsGeometry, QgsLineString, QgsPointXY,
)
from qgis.PyQt.QtCore import QMetaType
import processing
from qgis.PyQt.QtGui import QIcon

from ..rede import baixar_bytes
from .suavizacao import chaikin as _chaikin
from .utils import dir_cache, ocultar_da_toolbox, podar_cache

_TILE_MIN_BYTES = 1024


def _equidistancia_padrao() -> int:
    """Equidistância padrão definida em OrIFSC → Configurações (fallback 5 m)."""
    try:
        from qgis.core import QgsSettings
        return int(QgsSettings().value('OrIFSC/equidistancia_padrao', 5))
    except Exception:
        return 5


class GerarCurvasNivel(QgsProcessingAlgorithm):
    """Gera curvas de nível a partir do MDT Copernicus 30 m."""

    LIMITE = 'LIMITE'
    EQUIDISTANCIA = 'EQUIDISTANCIA'
    RECORTE = 'RECORTE'
    OUTPUT_CURVAS = 'OUTPUT_CURVAS'

    def tr(self, s: str) -> str:
        """Retorna texto sem tradução explícita.

        Args:
            s: Texto de entrada.

        Returns:
            str: Texto original.
        """
        return s

    def createInstance(self):
        """Cria nova instância do algoritmo para o Processing.

        Returns:
            GerarCurvasNivel: Nova instância.
        """
        return GerarCurvasNivel()

    def flags(self):
        """Oculta algoritmo da toolbox para uso via menu OrIFSC.

        Returns:
            QgsProcessingAlgorithm.Flags: Conjunto de flags do algoritmo.
        """
        return ocultar_da_toolbox(self)

    def icon(self) -> QIcon:
        """Retorna ícone visual do algoritmo.

        Returns:
            QIcon: Ícone de curvas.
        """
        return QIcon(os.path.join(os.path.dirname(__file__),
                                  '..', 'icons', 'curvas.svg'))

    def name(self) -> str:
        """Nome técnico do algoritmo.

        Returns:
            str: Identificador interno.
        """
        return 'gerar_curvas_nivel'

    def displayName(self) -> str:
        """Nome amigável exibido ao usuário.

        Returns:
            str: Rótulo do algoritmo.
        """
        return 'Gerar Curvas de Nível Automáticas'

    def group(self) -> str:
        """Nome do grupo visual do algoritmo.

        Returns:
            str: Grupo do provider.
        """
        return 'OrIFSC'

    def groupId(self) -> str:
        """Identificador técnico do grupo.

        Returns:
            str: ID do grupo.
        """
        return 'orientacao'

    def shortHelpString(self) -> str:
        """Retorna painel HTML de ajuda contextual do algoritmo.

        Returns:
            str: HTML de ajuda para o Processing.
        """
        from ..acoes.painel import painel_html, INSTRUCOES
        return painel_html('Gerar Curvas de Nível', INSTRUCOES['gerar_curvas'])

    def initAlgorithm(self, config=None) -> None:
        """Declara parâmetros de entrada e saída do algoritmo.

        Args:
            config: Configuração opcional do Processing.
        """
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.LIMITE, 'Camada da área a mapear (define a extensão do MDT)',
            [Qgis.ProcessingSourceType.VectorPolygon]))
        self.addParameter(QgsProcessingParameterNumber(
            self.EQUIDISTANCIA, 'Equidistância (metros)',
            type=Qgis.ProcessingNumberParameterType.Integer,
            defaultValue=_equidistancia_padrao()))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.RECORTE, 'Recortar curvas por (camada — opcional: folha/limite)',
            [Qgis.ProcessingSourceType.VectorPolygon], optional=True))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT_CURVAS, 'Curvas de Nível',
            type=Qgis.ProcessingSourceType.VectorLine))

    def processAlgorithm(self, parameters, context, feedback):
        """Executa pipeline completo: MDT, contorno, suavização e recorte.

        Args:
            parameters: Parâmetros recebidos pelo Processing.
            context: Contexto de execução do QGIS.
            feedback: Canal de progresso/mensagens do algoritmo.

        Returns:
            dict: ID da camada de saída.

        A validação antecipada evita falhas tardias e mantém o fluxo amigável
        para o usuário, em vez de deixar a execução avançar até quebrar por falta
        de camada base ou configuração mínima.
        """
        camada_limite = self.parameterAsSource(parameters, self.LIMITE, context)
        if camada_limite is None:
            feedback.pushWarning(
                'Selecione uma camada poligonal de área antes de gerar curvas.')
            raise QgsProcessingException(
                'Camada da área a mapear não informada.')

        equidistancia = self.parameterAsInt(
            parameters, self.EQUIDISTANCIA, context)
        if equidistancia <= 0:
            feedback.pushWarning(
                'A equidistância precisa ser maior que zero.')
            raise QgsProcessingException('Equidistância inválida.')

        camada_recorte = self.parameterAsVectorLayer(
            parameters, self.RECORTE, context)
        if camada_recorte is not None and not camada_recorte.isValid():
            feedback.pushWarning(
                'A camada de recorte selecionada está inválida.')
            raise QgsProcessingException('Camada de recorte inválida.')

        feedback.pushInfo('Fonte do MDT: Copernicus 30 m.')
        try:
            mdt_temp = self._baixar_copernicus(camada_limite, context, feedback)
        except QgsProcessingException:
            raise
        except Exception as e:
            raise QgsProcessingException(
                'Falha ao obter o MDT Copernicus.\n'
                f'Erro: {e}')

        if not mdt_temp or not os.path.exists(mdt_temp):
            raise QgsProcessingException(
                'Nao foi possivel obter um MDT valido da fonte selecionada. '
                'Nenhuma outra fonte foi usada automaticamente.')

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

        # As curvas brutas saem no CRS do MDT (Copernicus = EPSG:4326, graus).
        # Suavização e simplificação usam tolerâncias em metros, então tudo é
        # reprojetado ANTES para o CRS métrico da folha (regra 8 das Diretrizes).
        crs_saida = self._crs_metrico(camada_limite, context)
        ct_curvas = QgsCoordinateTransform(
            camada_brutas.crs(), crs_saida, context.transformContext())
        feedback.pushInfo(
            f'Curvas de saída em {crs_saida.authid()} (CRS métrico).')

        geom_recorte = None
        fonte_recorte = camada_recorte if camada_recorte is not None else camada_limite
        crs_fonte_recorte = (camada_recorte.crs()
                             if camada_recorte is not None
                             else camada_limite.sourceCrs())
        nome_recorte = (camada_recorte.name()
                        if camada_recorte is not None
                        else 'camada de limite')

        if fonte_recorte is not None:
            feedback.pushInfo(f'Preparando recorte por "{nome_recorte}"...')
            ct_rec = QgsCoordinateTransform(crs_fonte_recorte, crs_saida,
                                            context.transformContext())
            partes_rec = []
            for f in fonte_recorte.getFeatures():
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

        campos = QgsFields()
        campos.append(QgsField('ELEV', QMetaType.Type.Double))
        sink, dest_id = self.parameterAsSink(
            parameters, self.OUTPUT_CURVAS, context,
            campos, Qgis.WkbType.LineString, crs_saida)
        if sink is None:
            raise QgsProcessingException(
                'Não foi possível criar a camada de saída de curvas.')

        feedback.setProgress(55)
        tol = self._tolerancia_simplificacao_m()
        feedback.pushInfo(
            'Suavizando e gravando curvas — etapa mais demorada. Acompanhe o '
            'contador abaixo: enquanto ele avança, não travou.')
        feedback.pushInfo(
            f'Tolerância de simplificação: {tol:.2f} m por passada '
            '(0,075 mm de papel; desvio total abaixo de 0,15 mm — o menor '
            'objeto visível no mapa).')

        # Recorte com geometria "preparada" (índice GEOS): a interseção por
        # curva fica ordens de grandeza mais rápida que geom.intersection().
        motor_recorte = None
        motor_prefiltro = None
        geom_prefiltro = None  # referência viva enquanto o motor existir
        if geom_recorte is not None and not geom_recorte.isEmpty():
            motor_recorte = QgsGeometry.createGeometryEngine(
                geom_recorte.constGet())
            motor_recorte.prepareGeometry()
            # Pré-filtro: pula curvas totalmente fora da área ANTES do
            # Chaikin (a etapa cara). A área é expandida em 2x a tolerância
            # porque o desvio da suavização é limitado por ~tol — garante
            # resultado final idêntico ao de suavizar tudo e recortar depois.
            geom_prefiltro = geom_recorte.buffer(2 * tol, 8)
            if geom_prefiltro is not None and not geom_prefiltro.isEmpty():
                motor_prefiltro = QgsGeometry.createGeometryEngine(
                    geom_prefiltro.constGet())
                motor_prefiltro.prepareGeometry()

        total = max(1, camada_brutas.featureCount())
        passo_log = max(1, total // 20)
        gravadas = 0
        puladas = 0
        tem_elev = 'ELEV' in [c.name() for c in camada_brutas.fields()]
        for i, feat in enumerate(camada_brutas.getFeatures()):
            if feedback.isCanceled():
                break
            if i % 25 == 0:
                feedback.setProgress(55 + int(43 * i / total))
            if i and i % passo_log == 0:
                feedback.pushInfo(
                    f'  suavizando: {i}/{total} curvas '
                    f'({gravadas} gravadas, {puladas} fora da área)')
            g = feat.geometry()
            if g is None or g.isEmpty():
                continue
            g = QgsGeometry(g)
            try:
                g.transform(ct_curvas)
            except Exception:
                continue
            # Remove vértices abaixo da resolução de desenho ANTES do Chaikin:
            # corta memória/tempo (o Chaikin ×2 quadruplica os vértices) sem
            # efeito visível na escala do mapa.
            g = g.simplify(tol)
            if g is None or g.isEmpty():
                continue
            if (motor_prefiltro is not None
                    and not motor_prefiltro.intersects(g.constGet())):
                puladas += 1
                continue
            elev = feat['ELEV'] if tem_elev else None
            for parte in g.parts():
                pts = np.array([(v.x(), v.y()) for v in parte.vertices()],
                               dtype=np.float64)
                if len(pts) < 2:
                    continue
                pts_s = _chaikin(pts, 2)
                geom_s = QgsGeometry(QgsLineString(
                    pts_s[:, 0].tolist(), pts_s[:, 1].tolist()))
                geom_s = geom_s.simplify(tol)
                if geom_s is None or geom_s.isEmpty():
                    continue
                if motor_recorte is not None:
                    try:
                        recortada = motor_recorte.intersection(
                            geom_s.constGet())
                    except Exception:
                        continue
                    if recortada is None:
                        continue
                    geom_s = QgsGeometry(recortada)
                gravadas += self._gravar(sink, campos, geom_s, elev)

        feedback.pushInfo(f'{gravadas} linha(s) gravadas na camada de saída.')
        if puladas:
            feedback.pushInfo(
                f'{puladas} curva(s) fora da área de recorte foram puladas '
                'antes da suavização (sem efeito no resultado).')
        feedback.setProgress(99)
        # Libera o sink AQUI, antes de o QGIS carregar a camada de saída no
        # projeto: buffer/handle ainda abertos nesse momento podem derrubar o
        # QGIS no Windows (access violation no on_complete do diálogo).
        try:
            sink.flushBuffer()
        except (AttributeError, RuntimeError):
            pass
        del sink
        feedback.setProgress(100)
        return {self.OUTPUT_CURVAS: dest_id}

    def _gravar(self, sink: Any, campos: QgsFields,
                geom: QgsGeometry, elev: Optional[float]) -> int:
        """Grava a geometria no sink (separando multipartes em linhas).
        Retorna quantas linhas foram gravadas."""
        if geom is None or geom.isEmpty():
            return 0
        n = 0
        for sub in geom.parts():
            pts = [QgsPointXY(v.x(), v.y()) for v in sub.vertices()]
            if len(pts) < 2:
                continue
            nf = QgsFeature(campos)
            nf.setGeometry(QgsGeometry.fromPolylineXY(pts))
            nf.setAttribute(0, elev)
            sink.addFeature(nf, QgsFeatureSink.Flag.FastInsert)
            n += 1
        return n

    def _tolerancia_simplificacao_m(self) -> float:
        """Tolerância (metros) de cada passada de simplificação, derivada do
        critério cartográfico do projeto: o menor objeto visível no papel é
        0,15 mm na escala do mapa. Como a simplificação roda em DUAS passadas
        (antes do Chaikin, removendo ruído do MDT; e depois, removendo
        vértices redundantes da suavização) e os desvios podem se somar, cada
        passada usa a metade — 0,075 mm de papel —, garantindo desvio total
        abaixo de 0,15 mm (invisível). Escala 1:2.000 → 0,15 m; 1:10.000 →
        0,75 m; 1:15.000 → 1,13 m. Limitada a [0,1 m; 1,5 m]; sem escala
        definida no projeto, usa 0,5 m. Exige geometria em CRS métrico
        (regra 8 das Diretrizes: em graus, esses valores virariam dezenas de
        km)."""
        try:
            from ..acoes.comum import ler_escala
            escala = ler_escala()
        except Exception:
            escala = None
        if not escala:
            return 0.5
        return min(1.5, max(0.1, float(escala) * 0.000075))

    def _crs_metrico(
            self,
            camada_limite: Any,
            context: Any) -> QgsCoordinateReferenceSystem:
        """CRS métrico para suavizar/simplificar as curvas: o CRS da camada da
        área (a folha, normalmente UTM). Se essa camada estiver em CRS
        geográfico (graus), deriva o UTM WGS84 do centro da área — as
        tolerâncias são em metros e não podem ser aplicadas em graus."""
        crs = camada_limite.sourceCrs()
        if crs.isValid() and not crs.isGeographic():
            return crs
        crs_wgs84 = QgsCoordinateReferenceSystem('EPSG:4326')
        ext = camada_limite.sourceExtent()
        if crs.isValid() and crs != crs_wgs84:
            ct = QgsCoordinateTransform(
                crs, crs_wgs84, context.transformContext())
            ext = ct.transformBoundingBox(ext)
        centro = ext.center()
        fuso = min(60, max(1, int((centro.x() + 180) / 6) + 1))
        epsg = 32600 + fuso if centro.y() >= 0 else 32700 + fuso
        return QgsCoordinateReferenceSystem.fromEpsgId(epsg)

    def _baixar_copernicus(self, camada_limite: Any, context: Any, feedback: Any) -> str:
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

        pasta_cache = dir_cache('copernicus')
        tile_files = []
        for i, (lat_fl, lon_fl) in enumerate(sorted(tiles)):
            feedback.setProgress(int(i * 35 / len(tiles)))
            url = self._copernicus_url(lat_fl, lon_fl)
            destino = os.path.join(pasta_cache,
                                   f'cop30_{lat_fl}_{lon_fl}.tif')
            if self._cache_valido(destino):
                feedback.pushInfo(f'Usando tile em cache ({lat_fl}, {lon_fl}).')
            else:
                if os.path.exists(destino):
                    feedback.pushWarning(
                        f'Tile em cache inválido ({lat_fl}, {lon_fl}); '
                        'baixando novamente.')
                    try:
                        os.remove(destino)
                    except OSError:
                        pass
                feedback.pushInfo(
                    f'Baixando tile Copernicus ({lat_fl}, {lon_fl})...')
                parcial = destino + '.part'
                try:
                    dados = baixar_bytes(url)
                    with open(parcial, 'wb') as f:
                        f.write(dados)
                    os.replace(parcial, destino)
                except Exception as e:
                    try:
                        if os.path.exists(parcial):
                            os.remove(parcial)
                    except OSError:
                        pass
                    raise QgsProcessingException(
                        'Falha ao baixar o MDT Copernicus. '
                        f'Verifique sua conexão com a internet.\nErro: {e}')
            tile_files.append(destino)
        podar_cache()

        # VRT (mosaico virtual) SEMPRE, recortado na janela da folha via
        # outputBounds: o gdal:contour vetoriza só a área de interesse. Sem
        # o recorte, o contour rodava sobre o(s) tile(s) de 1°x1° inteiro(s)
        # (~111 km de lado) e >99% das curvas nasciam fora da folha, eram
        # suavizadas à toa e descartadas no recorte final ("0 gravadas").
        feedback.pushInfo('Recortando o MDT na janela da folha (VRT)...')
        from osgeo import gdal
        mdt_vrt = QgsProcessingUtils.generateTempFilename(
            'orifsc_mdt.vrt')
        vrt = gdal.BuildVRT(mdt_vrt, tile_files, outputBounds=(
            ext.xMinimum() - margem, ext.yMinimum() - margem,
            ext.xMaximum() + margem, ext.yMaximum() + margem))
        if vrt is None:
            raise QgsProcessingException(
                'Falha ao montar o mosaico recortado do MDT (BuildVRT).')
        vrt.FlushCache()
        vrt = None
        return mdt_vrt

    @staticmethod
    def _cache_valido(caminho: str) -> bool:
        """Retorna True se o arquivo existe e tem tamanho mínimo aceitável."""
        try:
            return (os.path.exists(caminho)
                    and os.path.getsize(caminho) >= _TILE_MIN_BYTES)
        except OSError:
            return False

    def _tiles_necessarios(
            self,
            min_lat: float,
            max_lat: float,
            min_lon: float,
            max_lon: float) -> Set[Tuple[int, int]]:
        """Calcula lista de tiles de 1 grau necessários para o Copernicus.

        Args:
            min_lat: Latitude mínima.
            max_lat: Latitude máxima.
            min_lon: Longitude mínima.
            max_lon: Longitude máxima.

        Returns:
            Set[Tuple[int, int]]: Pares (lat_floor, lon_floor) a baixar.
        """
        tiles = set()
        lat = math.floor(min_lat)
        while lat <= math.floor(max_lat):
            lon = math.floor(min_lon)
            while lon <= math.floor(max_lon):
                tiles.add((lat, lon))
                lon += 1
            lat += 1
        return tiles

    def _copernicus_url(self, lat_floor: int, lon_floor: int) -> str:
        """Monta URL oficial de um tile COG do Copernicus DEM 30 m.

        Args:
            lat_floor: Latitude inteira do tile.
            lon_floor: Longitude inteira do tile.

        Returns:
            str: URL HTTPS do GeoTIFF.

        Segue nomenclatura oficial do bucket para manter ausência de fallback
        implícito entre fontes de MDT.
        """
        ns = 'N' if lat_floor >= 0 else 'S'
        ew = 'E' if lon_floor >= 0 else 'W'
        lat_abs = abs(lat_floor)
        lon_abs = abs(lon_floor)
        name = (f'Copernicus_DSM_COG_10_{ns}{lat_abs:02d}_00_'
                f'{ew}{lon_abs:03d}_00_DEM')
        return f'https://copernicus-dem-30m.s3.amazonaws.com/{name}/{name}.tif'
