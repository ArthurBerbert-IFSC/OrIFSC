"""Estado compartilhado entre os passos do menu OrIFSC.

Os passos são ações independentes do menu, então os parâmetros definidos no
Passo 2 (EPSG e o retângulo da folha) ficam guardados como propriedades do
projeto — sobrevivem a salvar/reabrir o .qgz.
"""
from qgis.core import QgsProject
from qgis.PyQt.QtWidgets import QMessageBox

ESCOPO = 'OrIFSC'


def salvar_folha(epsg, x0, y0, x1, y1):
    """Grava no projeto o EPSG UTM e o retângulo da folha (definidos no Passo 2)."""
    proj = QgsProject.instance()
    proj.writeEntry(ESCOPO, 'epsg', int(epsg))
    proj.writeEntryDouble(ESCOPO, 'folha_x0', float(x0))
    proj.writeEntryDouble(ESCOPO, 'folha_y0', float(y0))
    proj.writeEntryDouble(ESCOPO, 'folha_x1', float(x1))
    proj.writeEntryDouble(ESCOPO, 'folha_y1', float(y1))


def salvar_escala(escala):
    """Grava o denominador da escala (Passo 2) — usado pela exportação para
    dimensionar a imagem na resolução real (mm da folha × DPI)."""
    QgsProject.instance().writeEntry(ESCOPO, 'escala', int(escala))


def ler_escala():
    """Retorna o denominador da escala salvo no Passo 2, ou None se ausente."""
    val, ok = QgsProject.instance().readNumEntry(ESCOPO, 'escala', 0)
    return val if ok and val > 0 else None


def ler_folha():
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


def projeto_configurado():
    """True se o Passo 2 (Definir Local e Criar Folha) já foi executado."""
    return ler_folha() is not None


def avisar_projeto_nao_configurado(parent=None):
    """Aviso padrão quando um passo é chamado sem o projeto estar configurado."""
    QMessageBox.warning(
        parent, 'OrIFSC',
        'Rode antes o passo "2 — Definir Local e Criar Folha" para configurar o '
        'projeto (coordenada, escala e folha).')
