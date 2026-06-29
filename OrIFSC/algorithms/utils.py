"""Utilitários compartilhados entre os algoritmos OrIFSC."""
from qgis.core import QgsProcessingAlgorithm


def ocultar_da_toolbox(alg):
    """Marca o algoritmo como oculto da Caixa de Ferramentas (só acessível pelo menu).
    Compatível com QGIS antigo (FlagHideFromToolbox) e novo (Qgis.ProcessingAlgorithmFlag)."""
    flags = super(type(alg), alg).flags()
    try:
        return flags | QgsProcessingAlgorithm.FlagHideFromToolbox
    except AttributeError:
        from qgis.core import Qgis
        return flags | Qgis.ProcessingAlgorithmFlag.HideFromToolbox
