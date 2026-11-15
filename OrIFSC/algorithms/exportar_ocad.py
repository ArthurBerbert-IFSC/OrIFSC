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
    QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsPointXY,
    QgsRectangle,
)
from qgis.PyQt.QtGui import QImage, QIcon

from ..i18n import N_, formatar_inteiro, tr
from ..rede import baixar_varios
from .utils import dir_cache, ocultar_da_toolbox, podar_cache

TILE = 256
ORIGIN_SHIFT = math.pi * 6378137.0
ZOOM_MAX = 20
MAX_PX = 16384
TILE_URL = 'https://mt{s}.google.com/vt/lyrs=s&x={x}&y={y}&z={z}'
UA = 'Mozilla/5.0 (QGIS OrIFSC plugin)'

# Índices casados com a ordem de _norma_da_opcao e com initAlgorithm.
# Rótulos em português marcados com N_ e traduzidos ao exibir (tr).
OPCOES_SIMBOLOGIA = [
    N_('ISOM 2017-2 — floresta (1:15.000 / 1:10.000)'),
    N_('ISSprOM 2019-2 — sprint (1:4.000 / 1:3.000)'),
    N_('Nenhuma (só o símbolo de curva)'),
]


def _resolucao(zoom: int) -> float:
    """Metros por pixel (em EPSG:3857) no nível de zoom dado."""
    return (2.0 * ORIGIN_SHIFT) / (TILE * (2 ** zoom))


class ExportarOCAD(QgsProcessingAlgorithm):
    """Gera projeto georreferenciado para OCAD (.ocd) e/ou OOM (.omap)."""

    FOLHA = 'FOLHA'
    EXPORTAR_SATELITE = 'EXPORTAR_SATELITE'
    QUALIDADE = 'QUALIDADE'
    CURVAS = 'CURVAS'
    SIMBOLOGIA = 'SIMBOLOGIA'
    LINHAS_NORTE = 'LINHAS_NORTE'
    DECL_AUTO = 'DECL_AUTO'
    DECL_MANUAL = 'DECL_MANUAL'
    FORMATO = 'FORMATO'
    PASTA = 'PASTA'

    def tr(self, texto: str, **kwargs: Any) -> str:
        """Traduz para o idioma ativo do plugin (ver ``OrIFSC/i18n``)."""
        return tr(texto, **kwargs)

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
        return self.tr('Gerar Projeto OCAD / OOM')

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
        from ..acoes.painel import painel_html, instrucoes as _instrucoes
        from ..acoes.comum import ler_escala
        instrucoes = _instrucoes('exportar_ocad')
        escala = ler_escala()
        if escala:
            instrucoes = (
                f'<p style="font-size:12px; color:#23262a;">'
                f'<b>{self.tr("Escala do projeto:")}</b> '
                f'1:{formatar_inteiro(escala)}</p>' + instrucoes)
        return painel_html(self.tr('Gerar Projeto OCAD / OOM'), instrucoes)

    def initAlgorithm(self, config=None) -> None:
        """Declara parâmetros do algoritmo de exportação.

        Args:
            config: Configuração opcional do Processing.

        Mantém entrada explícita de pasta permanente para respeitar diretriz de
        não depender de diretórios temporários para artefatos finais.
        """
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.FOLHA,
            self.tr('Camada da Folha (define a área e a georreferência)'),
            [Qgis.ProcessingSourceType.VectorPolygon]))
        self.addParameter(QgsProcessingParameterBoolean(
            self.EXPORTAR_SATELITE,
            self.tr('Incluir satélite como mapa de fundo'),
            defaultValue=True))
        self.addParameter(QgsProcessingParameterEnum(
            self.QUALIDADE, self.tr('Qualidade da imagem (zoom do Google)'),
            options=[self.tr('Máxima (melhor zoom)'),
                     self.tr('Alta (1 nível abaixo)'),
                     self.tr('Média (2 níveis abaixo)')], defaultValue=0))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.CURVAS,
            self.tr('Camada de Curvas de Nível (vira objeto no projeto)'),
            [Qgis.ProcessingSourceType.VectorLine], optional=True))
        self.addParameter(QgsProcessingParameterEnum(
            self.SIMBOLOGIA,
            self.tr('Simbologia (paleta de símbolos da norma, pronta para '
                    'desenhar)'),
            options=[self.tr(o) for o in OPCOES_SIMBOLOGIA],
            defaultValue=self._simbologia_padrao()))
        self.addParameter(QgsProcessingParameterBoolean(
            self.LINHAS_NORTE,
            self.tr('Incluir linhas de norte magnético (símbolo 601, '
                    'espaçamento da norma; exige simbologia)'),
            defaultValue=True))
        self.addParameter(QgsProcessingParameterBoolean(
            self.DECL_AUTO,
            self.tr('Usar a declinação magnética da folha (calculada em '
                    '"Definir Local")'),
            defaultValue=True))
        self.addParameter(QgsProcessingParameterNumber(
            self.DECL_MANUAL,
            self.tr('Declinação magnética manual (graus, leste +; usada só '
                    'com a opção acima desmarcada)'),
            type=Qgis.ProcessingNumberParameterType.Double, defaultValue=0.0,
            minValue=-90.0, maxValue=90.0))
        self.addParameter(QgsProcessingParameterEnum(
            self.FORMATO, self.tr('Formato(s) a gerar'),
            options=['OCAD (.ocd)',
                     'OpenOrienteering Mapper (.omap)',
                     self.tr('Ambos (.ocd e .omap)')],
            defaultValue=0))
        self.addParameter(QgsProcessingParameterFolderDestination(
            self.PASTA, self.tr('Pasta de saída')))

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
        from .ocad import (
            NORMA_ISOM, NORMA_ISSPROM, ProjetoOcad, arquivo_simbologia,
            classificar_curvas, escrever_ocd_v10, escrever_omap,
            escrever_omap_com_simbologia,
        )
        from .ocad.projeto import centro_latlon

        folha = self.parameterAsSource(parameters, self.FOLHA, context)
        if folha is None:
            feedback.pushWarning(self.tr(
                'Selecione uma camada de folha válida antes de exportar.'))
            raise QgsProcessingException(
                self.tr('Camada da folha não informada.'))

        exportar_sat = self.parameterAsBool(
            parameters, self.EXPORTAR_SATELITE, context)
        offset_zoom = self.parameterAsInt(parameters, self.QUALIDADE, context)
        curvas = self.parameterAsVectorLayer(parameters, self.CURVAS, context)
        if curvas is not None and not curvas.isValid():
            feedback.pushWarning(
                self.tr('A camada de curvas selecionada está inválida.'))
            raise QgsProcessingException(
                self.tr('Camada de curvas inválida.'))

        incluir_norte = self.parameterAsBool(
            parameters, self.LINHAS_NORTE, context)
        indice_simb = self.parameterAsEnum(
            parameters, self.SIMBOLOGIA, context)
        norma = (NORMA_ISOM, NORMA_ISSPROM, None)[indice_simb]

        decl_auto = self.parameterAsBool(parameters, self.DECL_AUTO, context)
        decl_manual = self.parameterAsDouble(
            parameters, self.DECL_MANUAL, context)
        formato = self.parameterAsEnum(parameters, self.FORMATO, context)
        fazer_ocad = formato in (0, 2)
        fazer_omap = formato in (1, 2)
        pasta = self.parameterAsString(parameters, self.PASTA, context)

        if not pasta:
            feedback.pushWarning(
                self.tr('Selecione uma pasta de saída antes de exportar.'))
            raise QgsProcessingException(
                self.tr('Selecione uma pasta de saída no seu computador.'))
        pasta_abs = os.path.normcase(os.path.abspath(pasta))
        for td in (tempfile.gettempdir(), QgsProcessingUtils.tempFolder()):
            if td and pasta_abs.startswith(
                    os.path.normcase(os.path.abspath(td))):
                feedback.pushWarning(self.tr(
                    'A pasta de saída não pode ser um diretório temporário.'))
                raise QgsProcessingException(self.tr(
                    'A pasta de saída não pode ser um diretório temporário. '
                    'Escolha uma pasta permanente no seu computador — o '
                    'satélite (.tif) precisa ficar junto dos projetos.'))
        os.makedirs(pasta, exist_ok=True)

        crs = folha.sourceCrs()
        epsg = self._epsg_utm(crs)
        extent = folha.sourceExtent()
        rect = (extent.xMinimum(), extent.yMinimum(),
                extent.xMaximum(), extent.yMaximum())

        escala = self._ler_escala()

        satelite = None
        if exportar_sat:
            feedback.pushInfo(self.tr('Montando imagem de satélite...'))
            tif = self._exportar_satelite(
                self._folha_no_papel(extent, escala), epsg, crs,
                offset_zoom, pasta, feedback)
            satelite = self._geotransform(tif)
            feedback.pushInfo(self.tr(
                'Satélite salvo em: {arquivo} (não é carregado no QGIS para '
                'não travar com imagens grandes; abra-o manualmente se quiser '
                'vê-lo).', arquivo=tif))
        feedback.setProgress(60)

        linhas, elevacoes = [], []
        if curvas is not None:
            feedback.pushInfo(self.tr('Lendo curvas de nível...'))
            linhas, elevacoes = self._curvas_para_linhas(curvas, crs)
            feedback.pushInfo(
                self.tr('{n} curva(s) lida(s).', n=len(linhas)))

        codigos = None
        if norma is not None and linhas:
            codigos = classificar_curvas(elevacoes)
            mestras = codigos.count('102')
            if mestras:
                feedback.pushInfo(self.tr(
                    '{n} curva(s) mestra(s) (símbolo 102, a cada 5ª '
                    'equidistância pelo campo ELEV).', n=mestras))
            else:
                feedback.pushWarning(self.tr(
                    'Nenhuma curva mestra identificada (campo ELEV ausente '
                    'ou elevações insuficientes): todas sairão como curva '
                    'normal (101).'))
        feedback.setProgress(70)

        declinacao = self._declinacao(
            decl_auto, decl_manual, epsg, rect, centro_latlon, feedback)
        feedback.pushInfo(self.tr('Declinação usada: {valor}°.',
                                  valor=f'{declinacao:.2f}'))
        feedback.setProgress(80)

        proj = ProjetoOcad(escala, epsg, rect, declinacao, linhas, satelite,
                           codigos_linhas=codigos)
        feedback.pushInfo(self.tr(
            'Convergência meridiana: {conv}° | grivação (norte magnético): '
            '{griv}°.', conv=f'{proj.convergencia:.2f}',
            griv=f'{proj.grivacao:.2f}'))
        if norma is not None:
            feedback.pushInfo(self.tr(
                'Simbologia: {nome}.',
                nome=self.tr(OPCOES_SIMBOLOGIA[indice_simb])))
        if incluir_norte:
            self._linhas_norte(proj, folha, norma, escala, feedback)

        resultado = {}
        if fazer_ocad:
            ocd = os.path.join(pasta, 'projeto_orifsc.ocd')
            feedback.pushInfo(self.tr('Gerando projeto OCAD 10 (.ocd)...'))
            doador = (arquivo_simbologia(norma, escala, '.ocd')
                      if norma is not None else None)
            if doador is not None and not os.path.exists(doador):
                feedback.pushWarning(self.tr(
                    'Simbologia para .ocd ainda não disponível (falta o '
                    'arquivo {arquivo} no plugin); o .ocd sai só com o '
                    'símbolo de curva (sem linhas de norte). O .omap sai '
                    'completo.',
                    arquivo=os.path.basename(doador)))
                doador = None
            try:
                escrever_ocd_v10(proj, ocd, doador=doador)
            except ValueError as exc:
                if doador is None:
                    raise
                feedback.pushWarning(self.tr(
                    'Simbologia .ocd descartada ({erro}); gerando só com o '
                    'símbolo de curva (sem linhas de norte).', erro=exc))
                escrever_ocd_v10(proj, ocd)
            resultado['OCD'] = ocd
        if fazer_omap:
            omap = os.path.join(pasta, 'projeto_orifsc.omap')
            feedback.pushInfo(self.tr(
                'Gerando projeto OpenOrienteering Mapper (.omap)...'))
            if norma is None:
                escrever_omap(proj, omap)
            else:
                escrever_omap_com_simbologia(
                    proj, omap, arquivo_simbologia(norma, escala))
            resultado['OMAP'] = omap
        feedback.setProgress(100)

        feedback.pushInfo(self.tr('Projetos gerados em: {pasta}', pasta=pasta))
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
            raise QgsProcessingException(self.tr(
                'A folha precisa estar em um CRS UTM/WGS84 (rode "Definir '
                'Local").'))
        epsg = int(authid.split(':')[1])
        if not (32601 <= epsg <= 32660 or 32701 <= epsg <= 32760):
            raise QgsProcessingException(self.tr(
                'CRS {crs} não é WGS84/UTM. Rode "Definir Local e Criar '
                'Folha".', crs=authid))
        return epsg

    def _linhas_norte(self, proj: Any, folha: Any, norma: Optional[str],
                      escala: int, feedback: Any) -> None:
        """Acrescenta ao projeto as linhas de norte magnético da norma.

        Linhas separadas no símbolo de linha de norte preto (decisão de
        nov/2026), cobrindo o contorno da folha, para o mapeador poder cortar
        cada uma onde esconder detalhes, como a norma pede. Sem simbologia
        não há o símbolo 601 no projeto, então nada é gerado.
        """
        if norma is None:
            feedback.pushInfo(self.tr(
                'Linhas de norte não incluídas: elas usam o símbolo 601 da '
                'norma — escolha a simbologia ISOM ou ISSprOM.'))
            return
        from .ocad.geo import espacamento_norte_mm
        from .ocad.simbologia import CODIGO_LINHA_NORTE
        feicao = next(folha.getFeatures(), None)
        if feicao is None or feicao.geometry().isEmpty():
            feedback.pushWarning(self.tr(
                'Folha sem geometria: linhas de norte não incluídas.'))
            return
        contorno = [(v.x(), v.y()) for v in feicao.geometry().vertices()]
        espacamento = espacamento_norte_mm(norma, escala)
        codigo = CODIGO_LINHA_NORTE[norma]
        n = proj.definir_linhas_norte(contorno, espacamento, codigo)
        feedback.pushInfo(self.tr(
            '{n} linha(s) de norte magnético (símbolo {codigo}) a cada '
            '{papel} mm no papel ({terreno} m no terreno).',
            n=n, codigo=codigo, papel=f'{espacamento:g}',
            terreno=f'{espacamento * escala / 1000:g}'))

    def _declinacao(self, decl_auto: bool, decl_manual: float, epsg: int,
                    rect: Tuple[float, float, float, float],
                    centro_latlon: Callable, feedback: Any) -> float:
        """Declinação da exportação, coerente com a rotação da folha.

        A folha é girada no "Definir Local" pela declinação daquele momento;
        exportar com outro valor faria a folha aparecer inclinada no OCAD.
        Por isso o padrão é a declinação salva no projeto. Projetos da 0.1.x
        (sem declinação salva) calculam pelo WMM offline na hora, como antes.
        """
        from ..acoes.comum import ler_declinacao, ler_folha_girada
        salva = ler_declinacao()
        if ler_folha_girada() is None:
            feedback.pushWarning(self.tr(
                'Esta folha foi criada numa versão anterior do OrIFSC, '
                'alinhada à quadrícula UTM: no OCAD/OOM ela aparece '
                'inclinada. Rode "Definir Local e Criar Folha" de novo (ou '
                '"Ajustar Folha") para criar a folha girada para o norte '
                'magnético.'))

        if not decl_auto:
            if salva is not None and abs(decl_manual - salva[0]) > 0.01:
                feedback.pushWarning(self.tr(
                    'A folha foi girada para a declinação {folha}°; '
                    'exportando com {manual}° ela vai aparecer inclinada '
                    '{diferenca}° no OCAD. Para mudar a declinação, refaça '
                    '"Definir Local".',
                    folha=f'{salva[0]:.2f}', manual=f'{decl_manual:.2f}',
                    diferenca=f'{abs(decl_manual - salva[0]):.2f}'))
            return decl_manual

        if salva is not None:
            from ..acoes.comum import rotulo_origem
            feedback.pushInfo(self.tr(
                'Declinação da folha: {valor}° ({origem}).',
                valor=f'{salva[0]:.2f}', origem=rotulo_origem(salva[1])))
            return salva[0]

        from .ocad.geo import declinacao_wmm
        lat, lon = centro_latlon(epsg, (rect[0] + rect[2]) / 2,
                                 (rect[1] + rect[3]) / 2)
        valor, valido = declinacao_wmm(lat, lon, datetime.date.today())
        feedback.pushInfo(self.tr(
            'Declinação calculada agora pelo modelo WMM (sem internet): '
            '{valor}°.', valor=f'{valor:.2f}'))
        if not valido:
            feedback.pushWarning(self.tr(
                'O modelo magnético embutido está fora da validade; confira '
                'a declinação e atualize o plugin.'))
        return valor

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
            raise QgsProcessingException(self.tr(
                'Escala não definida. Rode antes "Definir Local e Criar '
                'Folha".'))
        return escala

    def _simbologia_padrao(self) -> int:
        """Índice padrão do parâmetro Simbologia (preferência global; se
        'Automática', sugerido pela escala do projeto). Nunca falha: o
        diálogo precisa abrir mesmo sem projeto configurado."""
        try:
            from ..acoes.configuracoes import indice_simbologia_padrao
            return indice_simbologia_padrao()
        except Exception:
            return 0

    def _curvas_para_linhas(
            self,
            layer: Any,
            crs_destino: QgsCoordinateReferenceSystem) -> Tuple[list, list]:
        """Lê as feições de linha reprojetadas para o CRS da folha como listas
        de (x, y), com a elevação (campo ELEV, ou None) alinhada por linha.
        Itera vértices por parte (robusto a multipartes e curvas)."""
        ct = QgsCoordinateTransform(
            layer.crs(), crs_destino, QgsProject.instance())
        idx_elev = layer.fields().indexOf('ELEV')
        linhas, elevacoes = [], []
        for feat in layer.getFeatures():
            geom = feat.geometry()
            if geom is None or geom.isEmpty():
                continue
            geom.transform(ct)
            elev = None
            if idx_elev >= 0:
                try:
                    elev = float(feat.attribute(idx_elev))
                except (TypeError, ValueError):
                    elev = None
            for parte in geom.parts():
                pts = [(v.x(), v.y()) for v in parte.vertices()]
                if len(pts) >= 2:
                    linhas.append(pts)
                    elevacoes.append(elev)
        return linhas, elevacoes

    def _geotransform(self, tif: str) -> Dict[str, Any]:
        """Lê origem/pixel/tamanho do GeoTIFF para posicionar o fundo no OCD."""
        from osgeo import gdal
        ds = gdal.Open(tif)
        gt = ds.GetGeoTransform()
        sat = {'path': tif, 'gt': tuple(gt), 'ulx': gt[0], 'uly': gt[3],
               'px': gt[1], 'py': gt[5],
               'w': ds.RasterXSize, 'h': ds.RasterYSize}
        ds = None
        return sat

    def _folha_no_papel(self, extent: Any,
                        escala: int) -> Tuple[float, float, float, float,
                                              float]:
        """(ref_e, ref_n, largura_mm, altura_mm, grivação) da folha exportada.

        A folha girada do projeto quando a camada escolhida é ela (mesmo
        centro); senão (projeto 0.1.x ou outro polígono), o retângulo
        envolvente da camada, sem rotação — a imagem sai norte-acima, como
        nas versões anteriores.
        """
        from ..acoes.comum import ler_folha_girada
        cx = (extent.xMinimum() + extent.xMaximum()) / 2.0
        cy = (extent.yMinimum() + extent.yMaximum()) / 2.0
        g = ler_folha_girada()
        if (g is not None and abs(g['ref_e'] - cx) < 0.5
                and abs(g['ref_n'] - cy) < 0.5):
            return (g['ref_e'], g['ref_n'], g['larg_mm'], g['alt_mm'],
                    g['grivacao'])
        return (cx, cy, extent.width() * 1000.0 / escala,
                extent.height() * 1000.0 / escala, 0.0)

    def _exportar_satelite(
            self,
            folha_papel: Tuple[float, float, float, float, float],
            epsg: int,
            crs: QgsCoordinateReferenceSystem,
            offset_zoom: int,
            pasta: str,
            feedback: Any) -> str:
        """Exporta o satélite já alinhado ao papel (norte magnético para cima).

        O raster final cobre só a folha (+2 mm de margem) e é girado pela
        grivação dentro da MESMA reprojeção Web Mercator → UTM que já existia
        — uma única reamostragem (Lanczos), sem perda de nitidez a mais. Com
        isso o TIFF fica do tamanho da folha (sem o retângulo envolvente da
        folha girada, ~1,65x a área) e sobra mais pixel para o zoom dentro do
        limite do OCAD 10.

        Args:
            folha_papel: (ref_e, ref_n, largura_mm, altura_mm, grivação).
            epsg: EPSG UTM da folha.
            crs: CRS da folha.
            offset_zoom: Redução manual de qualidade.
            pasta: Pasta de saída.
            feedback: Canal de progresso do Processing.

        Returns:
            str: Caminho do GeoTIFF final.
        """
        from .ocad.geo import grade_papel
        from .ocad.projeto import centro_latlon
        ref_e, ref_n, larg_mm, alt_mm, griv = folha_papel
        escala = self._ler_escala()
        lat, _ = centro_latlon(epsg, ref_e, ref_n)
        cos_lat = math.cos(math.radians(lat))
        larg_m = (larg_mm + 4.0) * escala / 1000.0
        alt_m = (alt_mm + 4.0) * escala / 1000.0

        crs3857 = QgsCoordinateReferenceSystem.fromEpsgId(3857)
        tr3857 = QgsCoordinateTransform(crs, crs3857, QgsProject.instance())
        # Pegada do raster no Web Mercator (com folga de 10 m) para montar o
        # mosaico de tiles que alimenta a reprojeção.
        gt0, w0, h0 = grade_papel(ref_e, ref_n, larg_mm, alt_mm, escala,
                                  griv, 1.0)
        cantos = [QgsPointXY(gt0[0] + gt0[1] * c + gt0[2] * r,
                             gt0[3] + gt0[4] * c + gt0[5] * r)
                  for c, r in ((0, 0), (w0, 0), (w0, h0), (0, h0))]
        pegada = QgsRectangle.fromCenterAndSize(QgsPointXY(ref_e, ref_n),
                                                1.0, 1.0)
        for p in cantos:
            pegada.combineExtentWith(p)
        pegada.grow(10.0)
        rect = tr3857.transformBoundingBox(pegada)

        zoom = self._escolher_zoom(rect, offset_zoom, feedback,
                                   (larg_m, alt_m, cos_lat))
        pixel_m = _resolucao(zoom) * cos_lat
        maior = max(larg_m, alt_m) / pixel_m
        if maior > MAX_PX:
            pixel_m *= maior / MAX_PX
        gt, w, h = grade_papel(ref_e, ref_n, larg_mm, alt_mm, escala, griv,
                               pixel_m)

        caminho = os.path.join(pasta, 'satelite_orifsc.tif')
        tmp_3857 = QgsProcessingUtils.generateTempFilename(
            'orifsc_sat_3857.tif')
        try:
            self._montar_mosaico_tif(rect, zoom, tmp_3857, feedback)
            self._reprojetar_satelite(tmp_3857, epsg, gt, w, h, caminho,
                                      feedback)
        finally:
            try:
                os.remove(tmp_3857)
            except OSError:
                pass
        return caminho

    def _escolher_zoom(self, rect: Any, offset_zoom: int, feedback: Any,
                       saida: Optional[Tuple[float, float, float]] = None
                       ) -> int:
        """Maior zoom (<= ZOOM_MAX) cuja imagem FINAL cabe em MAX_PX por lado
        — ou seja, a MELHOR resolução possível para a folha (o satélite é a
        base de desenho, então sempre buscamos o zoom máximo). MAX_PX é
        limite técnico (abertura no OCAD 10 32-bit), não ajuste de qualidade
        — só atua em folhas gigantes.

        ``saida`` = (largura_m, altura_m, cos_lat) da imagem final alinhada
        ao papel; o mosaico intermediário (só lido pelo GDAL) pode ser até
        2x maior por lado. Sem ``saida``, mede o próprio mosaico.
        """
        for z in range(ZOOM_MAX, 0, -1):
            res = _resolucao(z)
            if saida is not None:
                larg_m, alt_m, cos_lat = saida
                cabe = (max(larg_m, alt_m) / (res * cos_lat) <= MAX_PX
                        and max(rect.width(), rect.height()) / res
                        <= 2 * MAX_PX)
            else:
                cabe = (rect.width() / res <= MAX_PX
                        and rect.height() / res <= MAX_PX)
            if cabe:
                zoom = max(1, z - offset_zoom)
                if zoom != z:
                    feedback.pushInfo(self.tr(
                        'Zoom {z} reduzido para {zoom} (qualidade escolhida).',
                        z=z, zoom=zoom))
                feedback.pushInfo(self.tr(
                    'Melhor zoom do Google para a folha: {zoom} (~{n} tiles).',
                    zoom=zoom, n=self._contar_tiles(rect, zoom)))
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
            feedback.pushInfo(self.tr(
                '{n} tile(s) do cache; baixando {faltam}.',
                n=len(dados), faltam=len(faltantes)))
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
                feedback.pushInfo(self.tr('  tiles: {feito}/{total}',
                                          feito=feito, total=tot))

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
        feedback.pushInfo(self.tr(
            'Baixando {n} tiles no melhor zoom ({zoom}). Em folhas grandes '
            'pode levar alguns minutos — acompanhe abaixo: enquanto o número '
            'avança, está baixando (não travou).', n=total_tiles, zoom=zoom))

        dados_por_tile = self._obter_tiles(tiles, zoom, feedback)

        ulx = gx0 * res - ORIGIN_SHIFT
        uly = ORIGIN_SHIFT - gy0 * res
        drv = gdal.GetDriverByName('GTiff')
        ds = drv.Create(destino, larg, alt, 3, gdal.GDT_Byte,
                        ['COMPRESS=LZW', 'BIGTIFF=IF_SAFER'])
        if ds is None:
            raise QgsProcessingException(self.tr(
                'Não foi possível criar o mosaico intermediário do satélite.'))
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(3857)
        ds.SetProjection(srs.ExportToWkt())
        ds.SetGeoTransform((ulx, res, 0.0, uly, 0.0, -res))

        feedback.pushInfo(
            self.tr('Montando o mosaico (por faixas, direto no disco)...'))
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
                feedback.pushInfo(self.tr(
                    '  montando: faixa {i}/{total}', i=j + 1, total=n_faixas))
        ds.FlushCache()
        ds = None

        if feedback.isCanceled():
            raise QgsProcessingException(
                self.tr('Operação cancelada pelo usuário.'))
        if falhas == total_tiles:
            raise QgsProcessingException(self.tr(
                'Não foi possível baixar nenhuma tile do Google. Verifique a '
                'conexão com a internet.'))
        if falhas:
            feedback.pushWarning(self.tr(
                '{n} tile(s) não baixaram (áreas pretas).', n=falhas))
        feedback.pushInfo(self.tr(
            'Mosaico: {larg}×{alt}px ({res} m/px em 3857).',
            larg=larg, alt=alt, res=f'{res:.3f}'))

    def _reprojetar_satelite(
            self,
            tmp_3857: str,
            epsg: int,
            gt: Tuple[float, ...],
            w: int,
            h: int,
            destino_tif: str,
            feedback: Any) -> None:
        """Reprojeta o mosaico 3857 direto na grade alinhada ao papel.

        Uma única reamostragem (Lanczos) para um raster intermediário com o
        geotransform girado; depois ``gdal.Translate`` só copia os pixels
        para o GeoTIFF FINAL em RGB, LZW e sem tiling (`TILED=NO`, strips),
        compatível com o OCAD 10 — não alterar (regra 7 das Diretrizes). O
        ``TFW=YES`` grava o world file com a rotação, para o OOM posicionar o
        template. `multithread`/`NUM_THREADS` aceleram só o cálculo do warp.
        """
        from osgeo import gdal, osr
        feedback.pushInfo(self.tr(
            'Reprojetando para o sistema da folha — etapa mais demorada; '
            'acompanhe a % abaixo...'))
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(int(epsg))
        tmp_papel = QgsProcessingUtils.generateTempFilename(
            'orifsc_sat_papel.tif')
        try:
            ds = gdal.GetDriverByName('GTiff').Create(
                tmp_papel, int(w), int(h), 3, gdal.GDT_Byte,
                ['TILED=YES', 'BIGTIFF=IF_SAFER'])
            if ds is None:
                raise QgsProcessingException(self.tr(
                    'Falha ao reprojetar a imagem do satélite (GDAL Warp).'))
            ds.SetGeoTransform(tuple(gt))
            ds.SetProjection(srs.ExportToWkt())
            ok = gdal.Warp(ds, tmp_3857, resampleAlg='lanczos',
                           multithread=True, warpMemoryLimit=256,
                           warpOptions=['INIT_DEST=255',
                                        'NUM_THREADS=ALL_CPUS'],
                           callback=self._cb_gdal(
                               feedback, self.tr('reprojetando'), 52, 58))
            ds.FlushCache()
            ds = None
            if not ok:
                if feedback.isCanceled():
                    raise QgsProcessingException(
                        self.tr('Operação cancelada pelo usuário.'))
                raise QgsProcessingException(self.tr(
                    'Falha ao reprojetar a imagem do satélite (GDAL Warp).'))
            ds_out = gdal.Translate(
                destino_tif, tmp_papel,
                creationOptions=['COMPRESS=LZW', 'TILED=NO', 'BIGTIFF=NO',
                                 'PHOTOMETRIC=RGB', 'TFW=YES'])
            if ds_out is None:
                raise QgsProcessingException(self.tr(
                    'Falha ao reprojetar a imagem do satélite (GDAL Warp).'))
            ds_out.FlushCache()
            ds_out = None
        finally:
            try:
                os.remove(tmp_papel)
            except OSError:
                pass

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
