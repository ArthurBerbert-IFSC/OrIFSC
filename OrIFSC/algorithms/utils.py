"""Utilitários compartilhados entre os algoritmos OrIFSC."""
import os

from qgis.core import Qgis, QgsApplication, QgsProcessingAlgorithm

_CACHE_MAX_MB = 1024


def ocultar_da_toolbox(alg: QgsProcessingAlgorithm):
    """Marca o algoritmo como oculto da Caixa de Ferramentas (só acessível
    pelo menu OrIFSC)."""
    return (QgsProcessingAlgorithm.flags(alg)
            | Qgis.ProcessingAlgorithmFlag.HideFromToolbox)


def dir_cache(subpasta: str = '') -> str:
    """Diretório de cache persistente do plugin, sob o perfil do QGIS —
    sobrevive a reinícios e a limpezas de %TEMP%, então re-execuções na mesma
    área reaproveitam MDT e tiles de satélite já baixados."""
    base = os.path.join(
        QgsApplication.qgisSettingsDirPath(), 'cache', 'orifsc')
    if subpasta:
        base = os.path.join(base, subpasta)
    os.makedirs(base, exist_ok=True)
    return base


def podar_cache(max_mb: int = _CACHE_MAX_MB) -> None:
    """Mantém o cache dentro de `max_mb`, removendo os arquivos mais antigos
    (por mtime) quando o total excede o limite."""
    base = dir_cache()
    arquivos = []
    total = 0
    for raiz, _dirs, nomes in os.walk(base):
        for nome in nomes:
            caminho = os.path.join(raiz, nome)
            try:
                st = os.stat(caminho)
            except OSError:
                continue
            arquivos.append((st.st_mtime, st.st_size, caminho))
            total += st.st_size
    limite = max_mb * 1024 * 1024
    if total <= limite:
        return
    arquivos.sort()
    for _mtime, tamanho, caminho in arquivos:
        try:
            os.remove(caminho)
        except OSError:
            continue
        total -= tamanho
        if total <= limite:
            break
