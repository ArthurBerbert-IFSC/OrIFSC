"""Camada 'folha' e aplicação de uma folha nova ao projeto.

A camada 'folha' é o retângulo do tamanho real do papel na escala do projeto,
com borda magenta e sem preenchimento. Ela nasce girada para o norte
magnético, para ficar em pé no papel do OCAD/OOM; projetos da 0.1.x (sem
grivação salva) continuam com o retângulo alinhado à quadrícula UTM.

``aplicar_folha`` é o ponto único usado pelo Definir Local e pelo Ajustar
Folha: calcula a orientação (declinação, convergência, grivação) no centro da
folha, grava o estado no projeto e cria ou atualiza a camada — sem duplicar a
camada a cada ajuste.
"""
import datetime
from typing import Any, Dict, Optional

from qgis.core import (
    QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY, QgsRectangle,
    QgsProject, QgsSymbol, QgsSingleSymbolRenderer, Qgis,
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor

from .comum import (ler_folha, ler_folha_girada, ler_declinacao,
                    salvar_folha, salvar_escala, salvar_declinacao,
                    avisar_projeto_nao_configurado)

NOME_CAMADA = 'folha'
PROPRIEDADE_CAMADA = 'OrIFSC/camada'


def calcular_orientacao(epsg: int, ref_e: float, ref_n: float,
                        declinacao: Optional[float] = None,
                        origem: Optional[str] = None) -> Dict[str, Any]:
    """Declinação, convergência e grivação no centro (UTM) de uma folha.

    Sem ``declinacao`` explícita: mantém o valor manual já salvo no projeto
    (decisão do usuário) ou recalcula pelo WMM offline para a data de hoje.

    Returns:
        dict com declinacao, origem, convergencia, grivacao, lat, lon.
    """
    from ..algorithms.ocad.geo import (
        convergencia_utm, declinacao_wmm, grivacao, meridiano_central,
        zona_utm_de_epsg,
    )
    from ..algorithms.ocad.projeto import centro_latlon

    lat, lon = centro_latlon(epsg, ref_e, ref_n)
    if declinacao is None:
        salva = ler_declinacao()
        if salva is not None and salva[1] == 'manual':
            declinacao, origem = salva
        else:
            declinacao, _ = declinacao_wmm(lat, lon, datetime.date.today())
            origem = 'WMM em ' + datetime.date.today().strftime('%d/%m/%Y')
    zona, _ = zona_utm_de_epsg(epsg)
    convergencia = convergencia_utm(lat, lon, meridiano_central(zona))
    return {
        'declinacao': declinacao,
        'origem': origem or 'manual',
        'convergencia': convergencia,
        'grivacao': grivacao(declinacao, convergencia),
        'lat': lat,
        'lon': lon,
    }


def aplicar_folha(iface: Any, epsg: int, ref_e: float, ref_n: float,
                  larg_mm: float, alt_mm: float, escala: int,
                  declinacao: Optional[float] = None,
                  origem: Optional[str] = None, parent: Any = None,
                  enquadrar: bool = True) -> Dict[str, Any]:
    """Grava a folha no projeto (girada para o norte magnético) e cria ou
    atualiza a camada 'folha'.

    Returns:
        O dict de ``calcular_orientacao`` acrescido de ``camada``.
    """
    orientacao = calcular_orientacao(epsg, ref_e, ref_n, declinacao, origem)
    salvar_escala(escala)
    salvar_folha(epsg, ref_e, ref_n, larg_mm, alt_mm, escala,
                 orientacao['grivacao'])
    salvar_declinacao(orientacao['declinacao'], orientacao['origem'])
    orientacao['camada'] = criar_folha(iface, parent, enquadrar)
    return orientacao


def camada_folha() -> Optional[QgsVectorLayer]:
    """A camada 'folha' do OrIFSC no projeto, ou None.

    Procura primeiro a camada marcada pelo plugin; em projetos da 0.1.x (sem
    marca), a primeira camada de polígono chamada 'folha'.
    """
    candidatas = [c for c in QgsProject.instance().mapLayers().values()
                  if isinstance(c, QgsVectorLayer)
                  and c.geometryType() == Qgis.GeometryType.Polygon]
    for c in candidatas:
        if c.customProperty(PROPRIEDADE_CAMADA) == NOME_CAMADA:
            return c
    for c in candidatas:
        if c.name() == NOME_CAMADA:
            return c
    return None


def _geometria_salva() -> Optional[QgsGeometry]:
    """Geometria da folha a partir do estado do projeto, ou None."""
    estado = ler_folha()
    if estado is None:
        return None
    girada = ler_folha_girada()
    if girada is not None:
        anel = [QgsPointXY(e, n) for e, n in girada['cantos']]
        return QgsGeometry.fromPolygonXY([anel + [anel[0]]])
    _, x0, y0, x1, y1 = estado
    return QgsGeometry.fromRect(QgsRectangle(x0, y0, x1, y1))


def _atualizar_existente(camada: QgsVectorLayer, epsg: int,
                         geometria: QgsGeometry) -> bool:
    """Troca a geometria da camada 'folha' existente; False se não der
    (outro CRS, mais de uma feição ou provedor que não aceita edição)."""
    if camada.crs().authid() != f'EPSG:{epsg}' or camada.featureCount() != 1:
        return False
    feicao = next(camada.getFeatures(), None)
    if feicao is None:
        return False
    if not camada.dataProvider().changeGeometryValues(
            {feicao.id(): geometria}):
        return False
    camada.setCustomProperty(PROPRIEDADE_CAMADA, NOME_CAMADA)
    camada.updateExtents()
    camada.triggerRepaint()
    return True


def _nova_camada(epsg: int, geometria: QgsGeometry) -> QgsVectorLayer:
    """Camada de memória 'folha' com borda magenta, marcada pelo plugin."""
    folha = QgsVectorLayer(f'Polygon?crs=EPSG:{epsg}', NOME_CAMADA, 'memory')
    feat = QgsFeature()
    feat.setGeometry(geometria)
    folha.dataProvider().addFeatures([feat])
    folha.updateExtents()
    folha.setCustomProperty(PROPRIEDADE_CAMADA, NOME_CAMADA)

    simbolo = QgsSymbol.defaultSymbol(folha.geometryType())
    simbolo.symbolLayer(0).setStrokeColor(QColor(255, 0, 255))
    simbolo.symbolLayer(0).setStrokeWidth(1.2)
    simbolo.symbolLayer(0).setBrushStyle(Qt.BrushStyle.NoBrush)
    folha.setRenderer(QgsSingleSymbolRenderer(simbolo))
    return folha


def criar_folha(iface: Any, parent: Any = None,
                enquadrar: bool = True) -> Optional[QgsVectorLayer]:
    """Cria ou atualiza a camada ``folha`` a partir do estado do projeto.

    Args:
        iface: Interface principal do QGIS.
        parent: Widget pai opcional para mensagens de aviso.
        enquadrar: Aproxima a vista na folha (desligado no Ajustar Folha,
            em que a pessoa já está olhando para o lugar).

    Returns:
        Optional[QgsVectorLayer]: Camada criada/atualizada, ou ``None`` quando
        o projeto não está configurado.

    Se já existe uma camada 'folha' no mesmo CRS, a geometria dela é trocada
    (rodar o Definir Local de novo ou ajustar a folha não duplica a camada).
    Uma camada antiga de memória em outro CRS (outra zona UTM) é substituída.
    """
    estado = ler_folha()
    geometria = _geometria_salva()
    if estado is None or geometria is None:
        avisar_projeto_nao_configurado(parent)
        return None
    epsg, x0, y0, x1, y1 = estado

    projeto = QgsProject.instance()
    folha = camada_folha()
    if folha is None or not _atualizar_existente(folha, epsg, geometria):
        if (folha is not None and folha.providerType() == 'memory'
                and folha.crs().authid() != f'EPSG:{epsg}'):
            projeto.removeMapLayer(folha.id())
        folha = _nova_camada(epsg, geometria)
        projeto.addMapLayer(folha)

    canvas = iface.mapCanvas()
    if enquadrar:
        canvas.setExtent(QgsRectangle(x0, y0, x1, y1))
    canvas.refresh()
    iface.setActiveLayer(folha)
    return folha
