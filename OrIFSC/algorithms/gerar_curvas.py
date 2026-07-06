"""Algoritmo Processing para geração de curvas de nível no OrIFSC."""

import os
import math
import xml.etree.ElementTree as ET
from urllib.parse import quote
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import numpy as np
from qgis.core import (
    Qgis,
    QgsProcessingAlgorithm, QgsProcessingParameterFeatureSource,
    QgsProcessingParameterNumber, QgsProcessingParameterFeatureSink,
    QgsProcessingParameterEnum,
    QgsProcessingException, QgsProcessingUtils,
    QgsCoordinateReferenceSystem, QgsCoordinateTransform,
    QgsVectorLayer, QgsFields, QgsField, QgsFeature, QgsFeatureSink,
    QgsGeometry, QgsLineString, QgsPointXY,
    QgsProject, QgsRectangle,
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
    """Gera curvas de nível a partir de Copernicus ou WCS do SIG@SC."""

    LIMITE = 'LIMITE'
    FONTE_MDT = 'FONTE_MDT'
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
        self.addParameter(QgsProcessingParameterEnum(
            self.FONTE_MDT, 'Fonte do MDT',
            options=['Copernicus 30 m (global, gratuito)',
                     'SIG@SC — MDT de SC (WCS, alta resolução; só SC)'],
            defaultValue=0))
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

        fonte = self.parameterAsEnum(parameters, self.FONTE_MDT, context)
        if fonte == 1:
            feedback.pushInfo('Fonte selecionada: SIG@SC (sem fallback automatico).')
            try:
                mdt_temp = self._baixar_mdt_sc(
                    camada_limite.sourceExtent(), camada_limite.sourceCrs(),
                    feedback)
            except QgsProcessingException:
                raise
            except Exception as e:
                raise QgsProcessingException(
                    'Falha ao obter MDT da fonte selecionada (SIG@SC). '
                    'Nenhuma outra fonte foi usada automaticamente.\n'
                    f'Erro: {e}')
        else:
            feedback.pushInfo('Fonte selecionada: Copernicus 30 m (sem fallback automatico).')
            try:
                mdt_temp = self._baixar_copernicus(camada_limite, context, feedback)
            except QgsProcessingException:
                raise
            except Exception as e:
                raise QgsProcessingException(
                    'Falha ao obter MDT da fonte selecionada (Copernicus). '
                    'Nenhuma outra fonte foi usada automaticamente.\n'
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
        if geom_recorte is not None and not geom_recorte.isEmpty():
            motor_recorte = QgsGeometry.createGeometryEngine(
                geom_recorte.constGet())
            motor_recorte.prepareGeometry()

        total = max(1, camada_brutas.featureCount())
        passo_log = max(1, total // 20)
        gravadas = 0
        tem_elev = 'ELEV' in [c.name() for c in camada_brutas.fields()]
        for i, feat in enumerate(camada_brutas.getFeatures()):
            if feedback.isCanceled():
                break
            if i % 25 == 0:
                feedback.setProgress(55 + int(43 * i / total))
            if i and i % passo_log == 0:
                feedback.pushInfo(
                    f'  suavizando: {i}/{total} curvas '
                    f'({gravadas} linhas gravadas)')
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
            # efeito visível na escala do mapa. Essencial no MDT de alta
            # resolução do SIG@SC.
            g = g.simplify(tol)
            if g is None or g.isEmpty():
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

        if len(tile_files) > 1:
            # VRT (mosaico virtual): instantâneo — o gdal:contour lê janelado
            # por cima dos tiles, sem reescrever o MDT inteiro em disco.
            feedback.pushInfo('Combinando tiles (mosaico virtual)...')
            from osgeo import gdal
            mdt_vrt = QgsProcessingUtils.generateTempFilename(
                'orifsc_mdt.vrt')
            vrt = gdal.BuildVRT(mdt_vrt, tile_files)
            if vrt is None:
                raise QgsProcessingException(
                    'Falha ao combinar os tiles do MDT (BuildVRT).')
            vrt.FlushCache()
            vrt = None
            return mdt_vrt
        return tile_files[0]

    def _baixar_mdt_sc(self, extent: Any, crs: Any, feedback: Any) -> str:
        """Baixa o MDT de SC pelo WCS do SIG@SC, recortado na folha, como GeoTIFF
        de elevacao (valores reais, nao imagem) para curvas de alta resolucao.

        Roda na thread do algoritmo (nao trava o QGIS). Descobre a coverage do
        MDT por GetCapabilities (XML) e baixa via GetCoverage WCS 1.0.0,
        evitando erros do driver WCS do GDAL em alguns ambientes.
        """
        from osgeo import gdal
        gdal.UseExceptions()
        gdal.SetConfigOption('GDAL_HTTP_TIMEOUT', '120')
        gdal.SetConfigOption('GDAL_HTTP_CONNECTTIMEOUT', '30')
        url = 'http://sigsc.sc.gov.br/sigserver/ows'

        feedback.pushInfo('Consultando o WCS do SIG@SC (pode demorar)...')
        coverage = None
        versao_ok = None
        coberturas_lidas = []
        for ver in ('1.0.0', '2.0.1', '1.1.1'):
            if feedback.isCanceled():
                return None
            try:
                caps_url = (f'{url}?service=WCS&request=GetCapabilities'
                            f'&version={ver}')
                xml_caps = baixar_bytes(caps_url)
                coberturas = self._extrair_coberturas_wcs(xml_caps)
                if coberturas:
                    coberturas_lidas = coberturas
                alvo = self._selecionar_cobertura_mdt(coberturas)
                if alvo is not None:
                    coverage = alvo['id']
                    versao_ok = ver
                    rotulo = alvo.get('title') or alvo['id']
                    feedback.pushInfo(
                        f'Coverage do MDT encontrada (WCS {ver}): {rotulo}')
                if coverage:
                    break
            except Exception as e:
                feedback.pushInfo(f'WCS {ver} nao respondeu ({e}).')
        if not coverage:
            if coberturas_lidas:
                amostra = ', '.join([c['id'] for c in coberturas_lidas[:6]])
                feedback.pushInfo(f'Coberturas encontradas no servico: {amostra}')
            raise QgsProcessingException(
                'Nao localizei o MDT no WCS do SIG@SC (servico fora do ar/lento, '
                'ou a camada mudou de nome). Nenhuma outra fonte foi usada '
                'automaticamente.')

        marg = 50.0
        bbox = [extent.xMinimum() - marg, extent.yMinimum() - marg,
                extent.xMaximum() + marg, extent.yMaximum() + marg]
        destino = QgsProcessingUtils.generateTempFilename('orifsc_mdt_sc.tif')

        feedback.pushInfo('Baixando o recorte do MDT de SC (alta resolucao)...')
        if versao_ok != '1.0.0':
            raise QgsProcessingException(
                'O SIG@SC respondeu com WCS em versao nao suportada por este '
                'fluxo de download direto. Tente novamente mais tarde.')

        try:
            self._baixar_getcoverage_wcs_100(
                url=url,
                coverage=coverage,
                extent=bbox,
                crs_origem=crs,
                destino=destino,
                feedback=feedback,
            )
        except Exception as e:
            raise QgsProcessingException(
                'Falha ao baixar o MDT de SC pelo WCS do SIG@SC.\n'
                f'Erro: {e}')

        ds_out = gdal.Open(destino)
        if ds_out is None:
            if feedback.isCanceled():
                raise QgsProcessingException('Operacao cancelada.')
            raise QgsProcessingException(
                'Falha ao baixar o MDT de SC pelo WCS do SIG@SC.')
        ds_out.FlushCache()
        ds_out = None
        return destino

    def _baixar_getcoverage_wcs_100(
            self,
            url: str,
            coverage: str,
            extent: Sequence[float],
            crs_origem: Any,
            destino: str,
            feedback: Any) -> None:
        """Baixa cobertura via WCS 1.0.0 (GetCoverage) em GeoTIFF."""
        from osgeo import gdal

        crs_req = crs_origem.authid() if crs_origem is not None else 'EPSG:4326'
        if not crs_req:
            crs_req = 'EPSG:4326'

        try:
            desc_url = (f'{url}?service=WCS&request=DescribeCoverage&version=1.0.0'
                        f'&coverage={quote(coverage, safe=":_")}')
            desc = baixar_bytes(desc_url)
            crs_desc = self._extrair_crs_wcs_100(desc)
            if crs_req not in crs_desc and crs_desc:
                crs_req = crs_desc[0]
        except Exception:
            pass

        bbox_req = self._transformar_bbox(extent, crs_origem.authid(), crs_req)
        largura, altura = self._dimensoes_bbox(bbox_req)

        gc_url = (
            f'{url}?service=WCS&request=GetCoverage&version=1.0.0'
            f'&coverage={quote(coverage, safe=":_")}'
            f'&crs={quote(crs_req, safe=":")}'
            f'&bbox={bbox_req[0]},{bbox_req[1]},{bbox_req[2]},{bbox_req[3]}'
            f'&width={largura}&height={altura}'
            '&format=GeoTIFF'
        )
        dados = baixar_bytes(gc_url)
        if not dados or len(dados) < 1024:
            raise RuntimeError('Resposta do GetCoverage vazia ou invalida.')

        with open(destino, 'wb') as f:
            f.write(dados)

        ds = gdal.Open(destino)
        if ds is None or ds.RasterCount < 1:
            raise RuntimeError('GetCoverage nao retornou um GeoTIFF de elevacao valido.')
        ds = None
        feedback.setProgress(40)

    @staticmethod
    def _extrair_crs_wcs_100(xml_desc: bytes) -> List[str]:
        """Extrai CRSs disponiveis do DescribeCoverage (WCS 1.0.0)."""
        root = ET.fromstring(xml_desc)
        crss = []
        for el in root.iter():
            nome = el.tag.split('}', 1)[-1].lower() if el.tag else ''
            if nome in ('requestresponsecrss', 'requestcrss',
                        'responsecrss', 'nativecrss'):
                txt = (el.text or '').strip()
                if txt:
                    crss.append(txt)
        unicos = []
        vistos = set()
        for c in crss:
            if c in vistos:
                continue
            vistos.add(c)
            unicos.append(c)
        return unicos

    @staticmethod
    def _transformar_bbox(
            bbox: Sequence[float],
            src_authid: str,
            dst_authid: str) -> Sequence[float]:
        """Transforma bbox [minx,miny,maxx,maxy] entre dois CRS."""
        if not src_authid or not dst_authid or src_authid == dst_authid:
            return bbox

        src = QgsCoordinateReferenceSystem(src_authid)
        dst = QgsCoordinateReferenceSystem(dst_authid)
        if not src.isValid() or not dst.isValid():
            return bbox

        ct = QgsCoordinateTransform(src, dst, QgsProject.instance())
        qext = QgsRectangle(bbox[0], bbox[1], bbox[2], bbox[3])
        t = ct.transformBoundingBox(qext)
        return [t.xMinimum(), t.yMinimum(), t.xMaximum(), t.yMaximum()]

    @staticmethod
    def _dimensoes_bbox(
            bbox: Sequence[float],
            alvo: int = 2048,
            maximo: int = 4096,
            minimo: int = 256) -> Tuple[int, int]:
        """Calcula width/height com base no aspecto do bbox."""
        dx = max(1e-9, abs(bbox[2] - bbox[0]))
        dy = max(1e-9, abs(bbox[3] - bbox[1]))
        asp = dx / dy
        if asp >= 1.0:
            w = max(minimo, min(maximo, int(alvo)))
            h = max(minimo, min(maximo, int(round(w / asp))))
        else:
            h = max(minimo, min(maximo, int(alvo)))
            w = max(minimo, min(maximo, int(round(h * asp))))
        return w, h

    @staticmethod
    def _extrair_coberturas_wcs(xml_caps: bytes) -> List[Dict[str, str]]:
        """Extrai lista de coberturas do GetCapabilities WCS (1.x/2.x)."""
        root = ET.fromstring(xml_caps)
        itens = []

        def _local(tag: str) -> str:
            """Normaliza tag XML removendo namespace.

            Args:
                tag: Nome bruto da tag.

            Returns:
                str: Nome local em minúsculas.
            """
            return tag.split('}', 1)[-1].lower() if tag else ''

        def _texto(el: Any) -> str:
            """Extrai texto limpo de elemento XML.

            Args:
                el: Elemento XML opcional.

            Returns:
                str: Texto sem espaços extras.
            """
            if el is None or el.text is None:
                return ''
            return el.text.strip()

        for cov in root.findall('.//{*}CoverageSummary'):
            cid = ''
            titulo = ''
            for ch in list(cov):
                nome = _local(ch.tag)
                if nome in ('coverageid', 'coverageidentifier', 'identifier'):
                    cid = _texto(ch)
                elif nome in ('title', 'label', 'abstract') and not titulo:
                    titulo = _texto(ch)
            if cid:
                itens.append({'id': cid, 'title': titulo})

        for cov in root.findall('.//{*}CoverageOfferingBrief'):
            cid = ''
            titulo = ''
            for ch in list(cov):
                nome = _local(ch.tag)
                if nome in ('name', 'identifier'):
                    cid = _texto(ch)
                elif nome in ('label', 'title', 'description', 'abstract') and not titulo:
                    titulo = _texto(ch)
            if cid:
                itens.append({'id': cid, 'title': titulo})

        if not itens:
            for el in root.iter():
                nome = _local(el.tag)
                if nome in ('coverageid', 'name'):
                    txt = _texto(el)
                    if txt:
                        itens.append({'id': txt, 'title': ''})

        unicos = []
        vistos = set()
        for it in itens:
            cid = it['id']
            if cid in vistos:
                continue
            vistos.add(cid)
            unicos.append(it)
        return unicos

    @staticmethod
    def _selecionar_cobertura_mdt(
            coberturas: Sequence[Dict[str, str]]) -> Optional[Dict[str, str]]:
        """Seleciona cobertura candidata de MDT por score de palavras-chave."""
        if not coberturas:
            return None

        palavras = (
            ('modelo digital de terreno', 10),
            ('mdt', 8),
            ('dem', 7),
            ('terreno', 5),
            ('elev', 4),
            ('relevo', 3),
        )

        melhor = None
        melhor_score = -1
        for c in coberturas:
            txt = ((c.get('id') or '') + ' ' + (c.get('title') or '')).lower()
            score = 0
            for p, w in palavras:
                if p in txt:
                    score += w

            if any(p in txt for p in (
                'imagepyramid', 'generated from imagepyramid',
                'hillshade', 'sombra', 'render', 'rgb', 'orto', 'ortofoto',
            )):
                score -= 20

            if score > melhor_score:
                melhor_score = score
                melhor = c
        return melhor if melhor_score > 0 else None

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
