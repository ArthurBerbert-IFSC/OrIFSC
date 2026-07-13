"""Ponto de entrada do plugin OrIFSC para o QGIS."""
from typing import Any


def _recarregar_modulos_dev() -> None:
    """Recarrega módulos do plugin em ambiente de desenvolvimento."""
    import importlib
    import os
    import sys

    if not os.environ.get('ORIFSC_DEV'):
        return

    for mod in list(sys.modules.keys()):
        if mod.startswith('OrIFSC.') or mod.startswith('PluginQgis.'):
            try:
                importlib.reload(sys.modules[mod])
            except Exception:
                continue


def classFactory(iface: Any) -> Any:
    """Retorna a instância principal do plugin para a interface do QGIS."""
    _recarregar_modulos_dev()
    from .orifsc import OrIFSCPlugin
    return OrIFSCPlugin(iface)
