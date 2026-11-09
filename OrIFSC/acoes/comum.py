"""Estado compartilhado entre os passos do menu OrIFSC.

Os passos são ações independentes do menu, então os parâmetros definidos no
Passo 2 (EPSG e o retângulo da folha) ficam guardados como propriedades do
projeto — sobrevivem a salvar/reabrir o .qgz.
"""
from typing import Any, List, Optional, Tuple

from qgis.core import QgsProject, QgsVectorLayer, Qgis
from qgis.PyQt.QtWidgets import QMessageBox

from ..i18n import tr

ESCOPO = 'OrIFSC'

# Papel das camadas-chave, gravado como propriedade customizada da camada
# (persiste no .qgz). Os NOMES das camadas são traduzidos para o idioma do
# plugin, então a detecção não pode depender do nome — só projetos antigos,
# sem a propriedade, caem no nome em português.
PROP_PAPEL = 'orifsc/papel'
PAPEL_FOLHA = 'folha'
PAPEL_LIMITE = 'limite'

# Trechos de nome que denunciam uma camada de curvas de nível (pt/en/tr),
# para camadas que não têm o campo ELEV.
_NOMES_CURVAS = ('urva', 'contour', 'eğri', 'egri')


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
    mensagem = tr(
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


def marcar_papel(camada: Any, papel: str) -> None:
    """Grava o papel da camada (``PAPEL_FOLHA``/``PAPEL_LIMITE``) como
    propriedade customizada, para achá-la qualquer que seja o nome."""
    camada.setCustomProperty(PROP_PAPEL, papel)


def camada_folha() -> Optional[QgsVectorLayer]:
    """Camada da folha criada em "Definir Local", ou None.

    Procura pela propriedade de papel (independe do idioma); em projetos de
    versões anteriores, sem a propriedade, pelo nome original 'folha'.
    """
    poligonos = camadas_poligono()
    for c in poligonos:
        if c.customProperty(PROP_PAPEL) == PAPEL_FOLHA:
            return c
    for c in poligonos:
        if c.name() == PAPEL_FOLHA:
            return c
    return None


def camada_curvas() -> Optional[QgsVectorLayer]:
    """Camada de linha que parece ser de curvas de nível, ou None.

    Heurística usada pelo guia de status do menu e pelo pré-preenchimento da
    exportação: camada de linha com o campo ELEV (gerado por "Gerar Curvas")
    ou cujo nome sugere curvas em qualquer idioma do plugin. O usuário sempre
    pode escolher outra.
    """
    linhas = [c for c in QgsProject.instance().mapLayers().values()
              if isinstance(c, QgsVectorLayer)
              and c.geometryType() == Qgis.GeometryType.Line]
    for c in linhas:
        if c.fields().indexOf('ELEV') >= 0:
            return c
    for c in linhas:
        nome = c.name().lower()
        if any(t in nome for t in _NOMES_CURVAS):
            return c
    return None


def tem_camada_curvas() -> bool:
    """True se há uma camada que parece ser de curvas de nível."""
    return camada_curvas() is not None
