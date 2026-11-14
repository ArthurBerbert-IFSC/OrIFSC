"""Estado compartilhado entre os passos do menu OrIFSC.

Os passos são ações independentes do menu, então os parâmetros definidos no
Passo 2 (EPSG e o retângulo da folha) ficam guardados como propriedades do
projeto — sobrevivem a salvar/reabrir o .qgz.
"""
from typing import Any, Dict, List, Optional, Tuple

from qgis.core import QgsProject, QgsVectorLayer, Qgis
from qgis.PyQt.QtWidgets import QMessageBox

ESCOPO = 'OrIFSC'


def salvar_folha(epsg: int, ref_e: float, ref_n: float, larg_mm: float,
                 alt_mm: float, escala: int, grivacao: float) -> None:
    """Grava no projeto a folha girada para o norte magnético.

    Guarda o centro (UTM), o tamanho do papel (mm), a escala e a grivação
    com que a folha foi girada, mais o retângulo envolvente (``folha_x0..y1``)
    que os passos antigos e a verificação de projeto configurado já usam.
    """
    from ..algorithms.ocad.geo import cantos_folha
    cantos = cantos_folha(ref_e, ref_n, larg_mm, alt_mm, escala, grivacao)
    es = [e for e, _ in cantos]
    ns = [n for _, n in cantos]
    proj = QgsProject.instance()
    proj.writeEntry(ESCOPO, 'epsg', int(epsg))
    proj.writeEntryDouble(ESCOPO, 'folha_x0', float(min(es)))
    proj.writeEntryDouble(ESCOPO, 'folha_y0', float(min(ns)))
    proj.writeEntryDouble(ESCOPO, 'folha_x1', float(max(es)))
    proj.writeEntryDouble(ESCOPO, 'folha_y1', float(max(ns)))
    proj.writeEntryDouble(ESCOPO, 'folha_ref_e', float(ref_e))
    proj.writeEntryDouble(ESCOPO, 'folha_ref_n', float(ref_n))
    proj.writeEntryDouble(ESCOPO, 'folha_larg_mm', float(larg_mm))
    proj.writeEntryDouble(ESCOPO, 'folha_alt_mm', float(alt_mm))
    proj.writeEntryDouble(ESCOPO, 'folha_grivacao', float(grivacao))
    revisao, _ = proj.readNumEntry(ESCOPO, 'folha_revisao', 0)
    proj.writeEntry(ESCOPO, 'folha_revisao', int(revisao) + 1)


def ler_folha_revisao() -> int:
    """Contador que sobe a cada vez que a folha é criada ou ajustada.

    Permite saber se curvas/exportação foram feitas para a folha atual
    (etapas "desatualizadas" do painel assistente).
    """
    revisao, ok = QgsProject.instance().readNumEntry(
        ESCOPO, 'folha_revisao', 0)
    return int(revisao) if ok else 0


def ler_folha_girada() -> Optional[Dict[str, Any]]:
    """Parâmetros da folha girada, ou None (projeto da 0.1.x ou sem folha).

    Chaves: epsg, ref_e, ref_n, larg_mm, alt_mm, escala, grivacao, cantos
    (4 pontos UTM, a partir do superior-esquerdo, sentido horário).
    """
    estado = ler_folha()
    escala = ler_escala()
    if estado is None or escala is None:
        return None
    proj = QgsProject.instance()
    valores = {}
    for chave in ('ref_e', 'ref_n', 'larg_mm', 'alt_mm', 'grivacao'):
        valor, ok = proj.readDoubleEntry(ESCOPO, 'folha_' + chave, 0.0)
        if not ok:
            return None
        valores[chave] = valor
    from ..algorithms.ocad.geo import cantos_folha
    valores['epsg'] = estado[0]
    valores['escala'] = escala
    valores['cantos'] = cantos_folha(
        valores['ref_e'], valores['ref_n'], valores['larg_mm'],
        valores['alt_mm'], escala, valores['grivacao'])
    return valores


def salvar_declinacao(declinacao: float, origem: str) -> None:
    """Grava a declinação usada para girar a folha e de onde ela veio
    (ex.: 'WMM-2025 em 14/11/2026' ou 'manual')."""
    proj = QgsProject.instance()
    proj.writeEntryDouble(ESCOPO, 'declinacao', float(declinacao))
    proj.writeEntry(ESCOPO, 'declinacao_origem', str(origem))


def ler_declinacao() -> Optional[Tuple[float, str]]:
    """(declinação em graus, origem) salva no Definir Local, ou None."""
    proj = QgsProject.instance()
    valor, ok = proj.readDoubleEntry(ESCOPO, 'declinacao', 0.0)
    if not ok:
        return None
    origem, _ = proj.readEntry(ESCOPO, 'declinacao_origem', '')
    return valor, origem


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


def salvar_tipo_mapa(tipo_id: str) -> None:
    """Grava o tipo de mapa escolhido no Definir Local (sprint, floresta,
    escolar ou personalizado)."""
    QgsProject.instance().writeEntry(ESCOPO, 'tipo_mapa', str(tipo_id))


def ler_tipo_mapa() -> Any:
    """``TipoMapa`` do projeto, ou None (projeto sem tipo salvo)."""
    from ..algorithms.ocad.tipos_mapa import tipo_por_id
    tipo_id, ok = QgsProject.instance().readEntry(ESCOPO, 'tipo_mapa', '')
    return tipo_por_id(tipo_id) if ok else None


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
