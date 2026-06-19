"""
Gera o ZIP do plugin OrIFSC pronto para instalar no QGIS.
Uso: python empacotar.py
"""
import os
import zipfile

PLUGIN_DIR = os.path.join(os.path.dirname(__file__), 'PluginQgis')
OUTPUT_ZIP = os.path.join(os.path.dirname(__file__), 'OrIFSC.zip')

# Nome da pasta de topo dentro do ZIP. É o nome com que o QGIS instala o plugin
# (precisa bater com o usado em desenvolvimento — ver setup-dev-symlink.ps1).
PLUGIN_NAME = 'OrIFSC'

# Diretórios/extensões ignorados (arquivos compilados, controle de versão, SO).
IGNORAR_DIRS = {'__pycache__', '.git'}
IGNORAR_EXT = {'.pyc', '.pyo'}
IGNORAR_NOMES = {'.DS_Store', 'Thumbs.db'}
# Dados pesados que não fazem parte do plugin (não referenciados pelo código).
IGNORAR_NOMES |= {'sigsc_articulacao_50k_10k.geojson'}


def deve_incluir(arquivo):
    nome = os.path.basename(arquivo)
    if nome in IGNORAR_NOMES:
        return False
    if os.path.splitext(nome)[1] in IGNORAR_EXT:
        return False
    return True


with zipfile.ZipFile(OUTPUT_ZIP, 'w', zipfile.ZIP_DEFLATED) as zf:
    for raiz, dirs, arquivos in os.walk(PLUGIN_DIR):
        dirs[:] = [d for d in dirs if d not in IGNORAR_DIRS]
        for arquivo in arquivos:
            if not deve_incluir(arquivo):
                continue
            caminho_abs = os.path.join(raiz, arquivo)
            interno = os.path.relpath(caminho_abs, PLUGIN_DIR)
            caminho_rel = os.path.join(PLUGIN_NAME, interno)
            zf.write(caminho_abs, caminho_rel)

print(f'Plugin empacotado em: {OUTPUT_ZIP}')
print('Para instalar: QGIS > Plugins > Gerenciar > Instalar a partir de ZIP')
