"""
Gera o ZIP do plugin OrIFSC pronto para instalar no QGIS.
Uso: python empacotar.py
"""
import os
import zipfile

PLUGIN_DIR = os.path.join(os.path.dirname(__file__), 'PluginQgis')
OUTPUT_ZIP = os.path.join(os.path.dirname(__file__), 'OrIFSC.zip')

IGNORAR = {'.pyc', '.pyo', '__pycache__', '.git', '.DS_Store'}


def deve_incluir(path):
    for parte in path.split(os.sep):
        if parte in IGNORAR or parte.startswith('__pycache__'):
            return False
    return True


with zipfile.ZipFile(OUTPUT_ZIP, 'w', zipfile.ZIP_DEFLATED) as zf:
    for raiz, dirs, arquivos in os.walk(PLUGIN_DIR):
        dirs[:] = [d for d in dirs if deve_incluir(d)]
        for arquivo in arquivos:
            if not deve_incluir(arquivo):
                continue
            caminho_abs = os.path.join(raiz, arquivo)
            caminho_rel = os.path.relpath(caminho_abs, os.path.dirname(PLUGIN_DIR))
            zf.write(caminho_abs, caminho_rel)

print(f'Plugin empacotado em: {OUTPUT_ZIP}')
print('Para instalar: QGIS → Plugins → Gerenciar → Instalar a partir de ZIP')
