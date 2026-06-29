def classFactory(iface):
    import os
    if os.environ.get('ORIFSC_DEV'):
        import sys
        import importlib
        for mod in list(sys.modules.keys()):
            if mod.startswith('OrIFSC.') or mod.startswith('PluginQgis.'):
                try:
                    importlib.reload(sys.modules[mod])
                except Exception:
                    pass

    from .orifsc import OrIFSCPlugin
    return OrIFSCPlugin(iface)
