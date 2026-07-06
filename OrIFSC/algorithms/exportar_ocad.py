"""Algoritmo Processing para exportação de projetos OCAD/OOM no OrIFSC."""

import datetime
import math
import os
import tempfile
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
from qgis.core import (
    Qgis,
    QgsProcessingAlgorithm, QgsProcessingParameterFeatureSource,
    QgsProcessingParameterVectorLayer, QgsProcessingParameterEnum,
    QgsProcessingParameterBoolean, QgsProcessingParameterNumber,
    QgsProcessingParameterFolderDestination,
    QgsProcessingException, QgsProject,
    QgsProcessingUtils,
    QgsCoordinateReferenceSystem, QgsCoordinateTransform,
)
from qgis.PyQt.QtGui import QImage, QIcon

from ..rede import baixar_varios
from .utils import dir_cache, ocultar_da_toolbox, podar_cache

TILE = 256
ORIGIN_SHIFT = math.pi * 6378137.0
ZOOM_MAX = 20
MAX_PX = 16384
TILE_URL = 'https://mt{s}.google.com/vt/lyrs=s&x={x}&y={y}&z={z}'
UA = 'Mozilla/5.0 (QGIS OrIFSC plugin)'


def _resolucao(zoom: int) -> float:
    """Metros por pixel (em EPSG:3857) no nível de zoom dado."""
    return (2.0 * ORIGIN_SHIFT) / (TILE * (2 ** zoom))


class ExportarOCAD(QgsProcessingAlgorithm):
    """Gera projeto georreferenciado para OCAD (.ocd) e/ou OOM (.omap)."""

    FOLHA = 'FOLHA'
    EXPORTAR_SATELITE = 'EXPORTAR_SATELITE'
    QUALIDADE = 'QUALIDADE'
    CURVAS = 'CURVAS'
    DECL_AUTO = 'DECL_AUTO'
    DECL_MANUAL = 'DECL_MANUAL'
    FORMATO = 'FORMATO'
    PASTA = 'PASTA'

    def tr(self, s: str) -> str:
        """Retorna texto sem tradução explícita.

        Args:
            s: Texto original.

        Returns:
            str: O mesmo texto.
        """
        return s

    def createInstance(self):
        """Cria nova instância do algoritmo para o Processing.

        Returns:
            ExportarOCAD: Nova instância do algoritmo.
        """
        return ExportarOCAD()

    def flags(self):
        """Marca algoritmo como oculto da toolbox.

        Returns:
            QgsProcessingAlgorithm.Flags: Flags com ocultação aplicada.
        """
        return ocultar_da_toolbox(self)

    def icon(self) -> QIcon:
        """Ícone do algoritmo no menu do plugin.

        Returns:
            QIcon: Ícone SVG do fluxo de exportação.
        """
        return QIcon(os.path.join(os.path.dirname(
            __file__), '..', 'icons', 'exportar.svg'))

    def name(self) -> str:
        """Nome interno do algoritmo Processing.

        Returns:
            str: Identificador estável usado em execução programática.
        """
        return 'exportar_ocad'

    def displayName(self) -> str:
        """Nome amigável exibido ao usuário.

        Returns:
            str: Rótulo do algoritmo.
        """
        return 'Gerar Projeto OCAD / OOM'

    def group(self) -> str:
        """Grupo visual do algoritmo no provider.

        Returns:
            str: Nome de agrupamento.
        """
        return 'OrIFSC'

    def groupId(self) -> str:
        """ID técnico do grupo do algoritmo.

        Returns:
            str: Identificador de grupo.
        """
        return 'orientacao'

    def shortHelpString(self) -> str:
        """Retorna HTML de ajuda consistente com o painel visual do plugin.

        Returns:
            str: HTML renderizável pelo painel de ajuda do Processing.
        """
        from ..acoes.painel import painel_html, INSTRUCOES
        from ..acoes.comum import ler_escala
        instrucoes = INSTRUCOES['exportar_ocad']
        escala = ler_escala()
        if escala:
            escala_fmt = f'{escala:,}'.replace(',', '.')
            instrucoes = (
                f'<p style="font-size:12px; color:#23262a;">'
                f'<b>Escala do projeto:</b> 1:{escala_fmt}</p>' + instrucoes)
        return painel_html('Gerar Projeto OCAD / OOM', instrucoes)

    def initAlgorithm(self, config=None) -> None:
        """Declara parâmetros do algoritmo de exportação.

        Args:
            config: Configuração opcional do Processing.

        Mantém entrada explícita de pasta permanente para respeitar diretriz de
        não depender de diretórios temporários para artefatos finais.
        """
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.FOLHA, 'Camada da Folha (define a área e a georreferência)',
            [Qgis.ProcessingSourceType.VectorPolygon]))
        self.addParameter(QgsProcessingParameterBoolean(
            self.EXPORTAR_SATELITE, 'Incluir satélite como mapa de fundo',
            defaultValue=True))
        self.addParameter(QgsProcessingParameterEnum(
            self.QUALIDADE, 'Qualidade da imagem (zoom do Google)',
            options=['Máxima (melhor zoom)', 'Alta (1 nível abaixo)',
                     'Média (2 níveis abaixo)'], defaultValue=0))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.CURVAS, 'Camada de Curvas de Nível (vira objeto no projeto)',
            [Qgis.ProcessingSourceType.VectorLine], optional=True))
        self.addParameter(QgsProcessingParameterBoolean(
            self.DECL_AUTO, 'Calcular declinação magnética automaticamente (WMM/NOAA)',
            defaultValue=True))
        self.addParameter(QgsProcessingParameterNumber(
            self.DECL_MANUAL,
            'Declinação magnética manual (graus, leste +; usada se o automático '
            'estiver desmarcado ou falhar)',
            type=Qgis.ProcessingNumberParameterType.Double, defaultValue=0.0,
            minValue=-90.0, maxValue=90.0))
        self.addParameter(QgsProcessingParameterEnum(
            self.FORMATO, 'Formato(s) a gerar',
            options=['OCAD (.ocd)',
                     'OpenOrienteering Mapper (.omap)',
                     'Ambos (.ocd e .omap)'],
            defaultValue=0))
        self.addParameter(QgsProcessingParameterFolderDestination(
            self.PASTA, 'Pasta de saída'))

    def processAlgorithm(self, parameters, context, feedback):
        """Executa exportação completa de satélite, curvas e arquivos finais.

        Args:
            parameters: Parâmetros recebidos pelo Processing.
            context: Contexto de execução do QGIS.
            feedback: Canal de progresso/mensagens do algoritmo.

        Returns:
            dict: Caminhos gerados para os formatos selecionados.

        As validações iniciais interrompem cedo entradas inválidas para manter o
        fluxo previsível e evitar trabalho pesado desnecessário quando a pasta,
        a folha ou o CRS não atendem aos pré-requisitos do plugin.
        """
        from .ocad import ProjetoOcad, escrever_omap, escrever_ocd_v10
        from .ocad.geo import declinacao_noaa
        from .ocad.projeto import centro_latlon

        folha = self.parameterAsSource(parameters, self.FOLHA, context)
        if folha is None:
            feedback.pushWarning(
                'Selecione uma camada de folha válida antes de exportar.')
            raise QgsProcessingException('Camada da folha não informada.')

        exportar_sat = self.parameterAsBool(
            parameters, self.EXPORTAR_SATELITE, context)
        offset_zoom = self.parameterAsInt(parameters, self.QUALIDADE, context)
        curvas = self.parameterAsVectorLayer(parameters, self.CURVAS, context)
        if curvas is not None and not curvas.isValid():
            feedback.pushWarning('A camada de curvas selecionada está inválida.')
            raise QgsProcessingException('Camada de curvas inválida.')

        decl_auto = self.parameterAsBool(parameters, self.DECL_AUTO, context)
        decl_manual = self.parameterAsDouble(
            parameters, self.DECL_MANUAL, context)
        formato = self.parameterAsEnum(parameters, self.FORMATO, context)
        fazer_ocad = formato in (0, 2)
        fazer_omap = formato in (1, 2)
        pasta = self.parameterAsString(parameters, self.PASTA, context)

        if not pasta:
            feedback.pushWarning('Selecione uma pasta de saída antes de exportar.')
            raise QgsProcessingException(
                'Selecione uma pasta de saída no seu computador.')
        pasta_abs = os.path.normcase(os.path.abspath(pasta))
        for td in (tempfile.gettempdir(), QgsProcessingUtils.tempFolder()):
            if td and pasta_abs.startswith(
                    os.path.normcase(os.path.abspath(td))):
                feedback.pushWarning(
                    'A pasta de saída não pode ser um diretório temporário.')
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

        satelite = None
        if exportar_sat:
            feedback.pushInfo('Montando imagem de satélite...')
            tif = self._exportar_satelite(
                extent, crs, offset_zoom, pasta, feedback)
            satelite = self._geotransform(tif)
            feedback.pushInfo(
                f'Satélite salvo em: {tif} (não é carregado no QGIS para não '
                'travar com imagens grandes; abra-o manualmente se quiser vê-lo).')
        feedback.setProgress(60)

        linhas = []
        if curvas is not None:
            feedback.pushInfo('Lendo curvas de nível...')
            linhas = self._curvas_para_linhas(curvas, crs)
            feedback.pushInfo(f'{len(linhas)} curva(s) lida(s).')
        feedback.setProgress(70)

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
            feedback.pushInfo(
                'Gerando projeto OpenOrienteering Mapper (.omap)...')
            escrever_omap(proj, omap)
            resultado['OMAP'] = omap
        feedback.setProgress(100)

        feedback.pushInfo(f'Projetos gerados em: {pasta}')
        return resultado

    def _epsg_utm(self, crs: QgsCoordinateReferenceSystem) -> int:
        """Valida se o CRS da folha é UTM/WGS84 e retorna o EPSG numérico.

        Args:
            crs: CRS da camada de folha.

        Returns:
            int: Código EPSG UTM.

        Raises:
            QgsProcessingException: Quando o CRS não é UTM WGS84.
        """
        authid = crs.authid()
        if not authid.startswith('EPSG:'):
            raise QgsProcessingException(
                'A folha precisa estar em um CRS UTM/WGS84 (rode "Definir Local").')
        epsg = int(authid.split(':')[1])
        if not (32601 <= epsg <= 32660 or 32701 <= epsg <= 32760):
            raise QgsProcessingException(
                f'CRS {authid} não é WGS84/UTM. Rode "Definir Local e Criar Folha".')
        return epsg

    def _ler_escala(self) -> int:
        """Lê escala persistida no estado do projeto.

        Returns:
            int: Denominador da escala.

        Raises:
            QgsProcessingException: Quando o projeto não foi configurado.
        """
        from ..acoes.comum import ler_escala
        escala = ler_escala()
        if not escala:
            raise QgsProcessingException(
                'Escala não definida. Rode antes "Definir Local e Criar Folha".')
        return escala

    def _curvas_para_linhas(
            self,
            layer: Any,
            crs_destino: QgsCoordinateReferenceSystem) -> list:
        """Lê as feições de linha reprojetadas para o CRS da folha como listas
        de (x, y). Itera vértices por parte (robusto a multipartes e curvas)."""
        ct = QgsCoordinateTransform(
            layer.crs(), crs_destino, QgsProject.instance())
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

    def _geotransform(self, tif: str) -> Dict[str, Any]:
        """Lê origem/pixel/tamanho do GeoTIFF para posicionar o fundo no OCD."""
        from osgeo import gdal
        ds = gdal.Open(tif)
        gt = ds.GetGeoTransform()
        sat = {'path': tif, 'ulx': gt[0], 'uly': gt[3],
               'px': gt[1], 'py': gt[5],
               'w': ds.RasterXSize, 'h': ds.RasterYSize}
        ds = None
        return sat

    def _exportar_satelite(
            self,
            extent: Any,
            crs: QgsCoordinateReferenceSystem,
            offset_zoom: int,
            pasta: str,
            feedback: Any) -> str:
        """Exporta satélite georreferenciado para o CRS da folha.

        Args:
            extent: Extensão da folha.
            crs: CRS da folha.
            offset_zoom: Redução manual de qualidade.
            pasta: Pasta de saída.
            feedback: Canal de progresso do Processing.

        Returns:
            str: Caminho do GeoTIFF final.
        """
        crs3857 = QgsCoordinateReferenceSystem.fromEpsgId(3857)
        rect = QgsCoordinateTransform(
            crs, crs3857, QgsProject.instance()).transformBoundingBox(extent)

        zoom = self._escolher_zoom(rect, offset_zoom, feedback)

        caminho = os.path.join(pasta, 'satelite_orifsc.tif')
        tmp_3857 = QgsProcessingUtils.generateTempFilename(
            'orifsc_sat_3857.tif')
        try:
            self._montar_mosaico_tif(rect, zoom, tmp_3857, feedback)
            self._reprojetar_satelite(tmp_3857, crs, caminho, feedback)
        finally:
            try:
                os.remove(tmp_3857)
            except OSError:
                pass
        return caminho

    def _escolher_zoom(self, rect: Any, offset_zoom: int, feedback: Any) -> int:
        """Maior zoom (<= ZOOM_MAX) cujo mosaico cabe em MAX_PX por lado — ou
        seja, a MELHOR resolução possível para a folha (o satélite é a base de
        desenho, então sempre buscamos o zoom máximo). MAX_PX é limite técnico
        (memória e abertura no OCAD 10 32-bit), não ajuste de qualidade — só atua
        em folhas gigantes."""
        for z in range(ZOOM_MAX, 0, -1):
            res = _resolucao(z)
            if rect.width() / res <= MAX_PX and rect.height() / res <= MAX_PX:
                zoom = max(1, z - offset_zoom)
                if zoom != z:
                    feedback.pushInfo(
                        f'Zoom {z} reduzido para {zoom} (qualidade escolhida).')
                feedback.pushInfo(f'Melhor zoom do Google para a folha: {zoom} '
                                  f'(~{self._contar_tiles(rect, zoom)} tiles).')
                return zoom
        return 1

    def _contar_tiles(self, rect: Any, zoom: int) -> int:
        """Número de tiles 256 px que cobrem a bbox (EPSG:3857) no zoom dado."""
        res = _resolucao(zoom)
        px_min = (rect.xMinimum() + ORIGIN_SHIFT) / res
        px_max = (rect.xMaximum() + ORIGIN_SHIFT) / res
        py_min = (ORIGIN_SHIFT - rect.yMaximum()) / res
        py_max = (ORIGIN_SHIFT - rect.yMinimum()) / res
        tx0, tx1 = int(px_min // TILE), int((px_max - 1e-6) // TILE)
        ty0, ty1 = int(py_min // TILE), int((py_max - 1e-6) // TILE)
        return (tx1 - tx0 + 1) * (ty1 - ty0 + 1)

    def _obter_tiles(
            self,
            tiles: List[Tuple[int, int]],
            zoom: int,
            feedback: Any) -> Dict[Tuple[int, int], Optional[bytes]]:
        """Bytes de cada tile ((tx, ty) -> bytes ou None): reaproveita o cache
        persistente e baixa em paralelo apenas o que falta. Tiles baixadas são
        gravadas no cache (escrita atômica) para re-exportações da mesma área."""
        pasta = dir_cache(os.path.join('gsat', str(zoom)))
        dados: Dict[Tuple[int, int], Optional[bytes]] = {}
        faltantes = []
        for (tx, ty) in tiles:
            caminho = os.path.join(pasta, f'{tx}_{ty}.jpg')
            try:
                if os.path.getsize(caminho) >= 128:
                    with open(caminho, 'rb') as f:
                        dados[(tx, ty)] = f.read()
                    continue
            except OSError:
                pass
            faltantes.append((tx, ty))
        if dados:
            feedback.pushInfo(f'{len(dados)} tile(s) do cache; '
                              f'baixando {len(faltantes)}.')
        if not faltantes:
            return dados

        url_de = {(tx, ty): TILE_URL.format(s=(tx + ty) % 4, x=tx, y=ty,
                                            z=zoom)
                  for (tx, ty) in faltantes}
        total = len(faltantes)
        passo_log = max(1, total // 20)

        def _prog(feito: int, tot: int) -> None:
            feedback.setProgress(int(45 * feito / tot))
            if feito == tot or feito % passo_log == 0:
                feedback.pushInfo(f'  tiles: {feito}/{tot}')

        baixados = baixar_varios(
            url_de.values(), user_agent=UA, max_conc=12, timeout_ms=20000,
            tentativas=3, cancelado=feedback.isCanceled, progresso=_prog)

        for (tx, ty), url in url_de.items():
            conteudo = baixados.get(url)
            dados[(tx, ty)] = conteudo
            if conteudo and len(conteudo) >= 128:
                caminho = os.path.join(pasta, f'{tx}_{ty}.jpg')
                parcial = caminho + '.part'
                try:
                    with open(parcial, 'wb') as f:
                        f.write(conteudo)
                    os.replace(parcial, caminho)
                except OSError:
                    pass
        podar_cache()
        return dados

    @staticmethod
    def _tile_para_array(dados: Optional[bytes]) -> Optional[np.ndarray]:
        """Decodifica os bytes de uma tile para array (altura, largura, 3)
        RGB uint8, ou None se os dados forem inválidos."""
        if not dados:
            return None
        img = QImage()
        if not img.loadFromData(dados) or img.isNull():
            return None
        img = img.convertToFormat(QImage.Format.Format_RGB888)
        h, w, bpl = img.height(), img.width(), img.bytesPerLine()
        buf = img.constBits()
        buf.setsize(h * bpl)
        plano = np.frombuffer(bytes(buf), dtype=np.uint8).reshape(h, bpl)
        return plano[:, :w * 3].reshape(h, w, 3)

    def _montar_mosaico_tif(
            self,
            rect: Any,
            zoom: int,
            destino: str,
            feedback: Any) -> None:
        """Baixa as tiles e escreve o mosaico DIRETO num GeoTIFF em EPSG:3857,
        faixa por faixa de tiles (streaming) — substitui o QImage gigante +
        QPainter + PNG intermediário, que chegava a ~1,5 GB de pico de RAM.
        O arquivo gerado aqui é intermediário (só o GDAL lê; apagado ao final):
        as exigências do OCAD valem apenas para o GeoTIFF final (regra 7)."""
        from osgeo import gdal, osr

        res = _resolucao(zoom)
        px_min = (rect.xMinimum() + ORIGIN_SHIFT) / res
        px_max = (rect.xMaximum() + ORIGIN_SHIFT) / res
        py_min = (ORIGIN_SHIFT - rect.yMaximum()) / res
        py_max = (ORIGIN_SHIFT - rect.yMinimum()) / res
        tx0, tx1 = int(px_min // TILE), int((px_max - 1e-6) // TILE)
        ty0, ty1 = int(py_min // TILE), int((py_max - 1e-6) // TILE)

        esq = int(round(px_min - tx0 * TILE))
        topo = int(round(py_min - ty0 * TILE))
        larg = max(1, int(round(px_max - px_min)))
        alt = max(1, int(round(py_max - py_min)))
        gx0 = tx0 * TILE + esq
        gy0 = ty0 * TILE + topo

        tiles = [(tx, ty) for ty in range(ty0, ty1 + 1)
                 for tx in range(tx0, tx1 + 1)]
        total_tiles = len(tiles)
        feedback.pushInfo(
            f'Baixando {total_tiles} tiles no melhor zoom ({zoom}). Em folhas '
            'grandes pode levar alguns minutos — acompanhe abaixo: enquanto o '
            'número avança, está baixando (não travou).')

        dados_por_tile = self._obter_tiles(tiles, zoom, feedback)

        ulx = gx0 * res - ORIGIN_SHIFT
        uly = ORIGIN_SHIFT - gy0 * res
        drv = gdal.GetDriverByName('GTiff')
        ds = drv.Create(destino, larg, alt, 3, gdal.GDT_Byte,
                        ['COMPRESS=LZW', 'BIGTIFF=IF_SAFER'])
        if ds is None:
            raise QgsProcessingException(
                'Não foi possível criar o mosaico intermediário do satélite.')
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(3857)
        ds.SetProjection(srs.ExportToWkt())
        ds.SetGeoTransform((ulx, res, 0.0, uly, 0.0, -res))

        feedback.pushInfo('Montando o mosaico (por faixas, direto no disco)...')
        falhas = 0
        n_faixas = ty1 - ty0 + 1
        for j, ty in enumerate(range(ty0, ty1 + 1)):
            if feedback.isCanceled():
                break
            dy0 = max(0, ty * TILE - gy0)
            dy1 = min(alt, ty * TILE + TILE - gy0)
            if dy1 <= dy0:
                continue
            faixa = np.zeros((dy1 - dy0, larg, 3), dtype=np.uint8)
            for tx in range(tx0, tx1 + 1):
                arr = self._tile_para_array(dados_por_tile.get((tx, ty)))
                if arr is None:
                    falhas += 1
                    continue
                dx0 = max(0, tx * TILE - gx0)
                dx1 = min(larg, tx * TILE + arr.shape[1] - gx0)
                if dx1 <= dx0:
                    continue
                sy0 = dy0 + gy0 - ty * TILE
                sy1 = min(arr.shape[0], sy0 + (dy1 - dy0))
                sx0 = dx0 + gx0 - tx * TILE
                sx1 = sx0 + (dx1 - dx0)
                if sy1 <= sy0 or sx1 > arr.shape[1]:
                    continue
                faixa[:sy1 - sy0, dx0:dx1] = arr[sy0:sy1, sx0:sx1]
            ds.WriteRaster(0, dy0, larg, dy1 - dy0, faixa.tobytes(),
                           band_list=[1, 2, 3], buf_pixel_space=3,
                           buf_line_space=larg * 3, buf_band_space=1)
            feedback.setProgress(45 + int(7 * (j + 1) / n_faixas))
            if (j + 1) % max(1, n_faixas // 10) == 0 or j + 1 == n_faixas:
                feedback.pushInfo(f'  montando: faixa {j + 1}/{n_faixas}')
        ds.FlushCache()
        ds = None

        if feedback.isCanceled():
            raise QgsProcessingException('Operação cancelada pelo usuário.')
        if falhas == total_tiles:
            raise QgsProcessingException(
                'Não foi possível baixar nenhuma tile do Google. '
                'Verifique a conexão com a internet.')
        if falhas:
            feedback.pushWarning(
                f'{falhas} tile(s) não baixaram (áreas pretas).')
        feedback.pushInfo(f'Mosaico: {larg}×{alt}px '
                          f'({res:.3f} m/px em 3857).')

    def _reprojetar_satelite(
            self,
            tmp_3857: str,
            crs: QgsCoordinateReferenceSystem,
            destino_tif: str,
            feedback: Any) -> None:
        """Reprojeta o mosaico 3857 para o CRS da folha.

        O GeoTIFF FINAL sai em RGB com LZW e sem tiling (`TILED=NO`, strips)
        para manter compatibilidade com o OCAD 10 — não alterar (regra 7 das
        Diretrizes). `multithread`/`NUM_THREADS` aceleram só o cálculo do
        warp; não mudam um byte do resultado.
        """
        from osgeo import gdal
        feedback.pushInfo('Reprojetando para o sistema da folha — etapa mais '
                          'demorada; acompanhe a % abaixo...')
        ds_out = gdal.Warp(destino_tif, tmp_3857, dstSRS=crs.authid(),
                           resampleAlg='lanczos',
                           multithread=True,
                           warpMemoryLimit=256,
                           warpOptions=['INIT_DEST=255',
                                        'NUM_THREADS=ALL_CPUS'],
                           creationOptions=['COMPRESS=LZW', 'TILED=NO',
                                            'BIGTIFF=NO', 'PHOTOMETRIC=RGB'],
                           callback=self._cb_gdal(feedback, 'reprojetando',
                                                  52, 60))
        if ds_out is None:
            if feedback.isCanceled():
                raise QgsProcessingException(
                    'Operação cancelada pelo usuário.')
            raise QgsProcessingException(
                'Falha ao reprojetar a imagem do satélite (GDAL Warp).')
        ds_out.FlushCache()
        ds_out = None

    @staticmethod
    def _cb_gdal(
            feedback: Any,
            rotulo: str,
            p0: int,
            p1: int) -> Callable[[float, str, Any], int]:
        """Callback de progresso do GDAL (complete 0..1): move a barra de p0→p1,
        loga a cada ~10% e permite cancelar (retornar 0 aborta a operação)."""
        estado = {'dec': -1}

        def _cb(complete: float, message: str, _dados: Any) -> int:
            """Propaga progresso do GDAL para o feedback do Processing.

            Args:
                complete: Fração de 0 a 1.
                message: Mensagem opcional do GDAL.
                _dados: Contexto não utilizado.

            Returns:
                int: 0 para cancelar, 1 para continuar.
            """
            if feedback.isCanceled():
                return 0
            feedback.setProgress(p0 + (p1 - p0) * complete)
            dec = int(complete * 10)
            if dec > estado['dec']:
                estado['dec'] = dec
                feedback.pushInfo(f'  {rotulo}: {dec * 10}%')
            return 1
        return _cb
