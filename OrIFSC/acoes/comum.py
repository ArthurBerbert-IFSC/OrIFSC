"""Estado compartilhado entre os passos do menu OrIFSC.

Os passos são ações independentes do menu, então os parâmetros definidos no
Passo 2 (EPSG e o retângulo da folha) ficam guardados como propriedades do
projeto — sobrevivem a salvar/reabrir o .qgz.
"""
from typing import Any, List, Optional, Tuple

from qgis.core import QgsProject, QgsVectorLayer, Qgis
from qgis.PyQt.QtWidgets import QMessageBox

ESCOPO = 'OrIFSC'


def salvar_folha(epsg: int, x0: float, y0: float, x1: float, y1: float) -> None:
    """Grava no projeto o EPSG UTM e o retângulo da folha (definidos no Passo 2)."""
    proj = QgsProject.instance()
    proj.writeEntry(ESCOPO, 'epsg', int(epsg))
    proj.writeEntryDouble(ESCOPO, 'folha_x0', float(x0))
    proj.writeEntryDouble(ESCOPO, 'folha_y0', float(y0))
    proj.writeEntryDouble(ESCOPO, 'folha_x1', float(x1))
    proj.writeEntryDouble(ESCOPO, 'folha_y1', float(y1))


def salvar_escala(escala: int) -> None:
    """Grava o denominador da escala (Passo 2) — usado pela exportação para
    dimensionar a imagem na resolução real (mm da folha × DPI)."""
    QgsProject.instance().writeEntry(ESCOPO, 'escala', int(escala))


def ler_escala() -> Optional[int]:
    """Retorna o denominador da escala salvo no Passo 2, ou None se ausente."""
    val, ok = QgsProject.instance().readNumEntry(ESCOPO, 'escala', 0)
    return val if ok and val > 0 else None


def ler_folha() -> Optional[Tuple[int, float, float, float, float]]:
    """Retorna (epsg, x0, y0, x1, y1) ou None se o Passo 2 ainda não rodou."""
    proj = QgsProject.instance()
    epsg, ok = proj.readNumEntry(ESCOPO, 'epsg', 0)
    if not ok or epsg == 0:
        return None
    x0, _ = proj.readDoubleEntry(ESCOPO, 'folha_x0', 0.0)
    y0, _ = proj.readDoubleEntry(ESCOPO, 'folha_y0', 0.0)
    x1, _ = proj.readDoubleEntry(ESCOPO, 'folha_x1', 0.0)
    y1, _ = proj.readDoubleEntry(ESCOPO, 'folha_y1', 0.0)
    return epsg, x0, y0, x1, y1


def projeto_configurado() -> bool:
    """True se o Passo 2 (Definir Local e Criar Folha) já foi executado."""
    return ler_folha() is not None


def avisar_projeto_nao_configurado(parent: Any = None) -> None:
    """Avisa que o projeto precisa ser configurado antes do fluxo atual."""
    mensagem = (
        'Antes de continuar, use o menu "Definir Local e Criar Folha" para '
        'configurar coordenada, escala e folha.')
    if parent is not None and hasattr(parent, 'messageBar'):
        parent.messageBar().pushMessage('OrIFSC', mensagem,
                                        level=Qgis.MessageLevel.Warning,
                                        duration=6)
        return
    QMessageBox.warning(parent, 'OrIFSC', mensagem)


def camadas_poligono() -> List[QgsVectorLayer]:
    """Camadas vetoriais de polígono carregadas no projeto."""
    return [c for c in QgsProject.instance().mapLayers().values()
            if isinstance(c, QgsVectorLayer)
            and c.geometryType() == Qgis.GeometryType.Polygon]


def camada_curvas() -> Optional[QgsVectorLayer]:
    """Camada de linha cujo nome sugere curvas de nível, ou None.

    Heurística simples (nome contém "urva"), usada pelo guia de status do menu e
    pelo pré-preenchimento da exportação. O usuário sempre pode escolher outra.
    """
    for c in QgsProject.instance().mapLayers().values():
        if (isinstance(c, QgsVectorLayer)
                and c.geometryType() == Qgis.GeometryType.Line
                and 'urva' in c.name().lower()):
            return c
    return None


def tem_camada_curvas() -> bool:
    """True se há uma camada que parece ser de curvas de nível."""
    return camada_curvas() is not None
