"""Infraestrutura dos testes.

Os testes cobrem os módulos PUROS do plugin (sem dependência do QGIS) e por
isso rodam com Python + NumPy + pytest, sem uma instalação do QGIS. Como os
``__init__.py`` do pacote importam ``qgis``, cada módulo é carregado direto do
arquivo com ``importlib`` (sem executar os ``__init__``).
"""
import importlib.util
import os
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACOTE = os.path.join(RAIZ, 'OrIFSC')


def carregar_modulo(nome: str, *caminho: str):
    """Carrega um .py do plugin direto do arquivo, fora do pacote."""
    arquivo = os.path.join(PACOTE, *caminho)
    spec = importlib.util.spec_from_file_location(nome, arquivo)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[nome] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope='session')
def suavizacao():
    return carregar_modulo('orifsc_suavizacao',
                           'algorithms', 'suavizacao.py')


@pytest.fixture(scope='session')
def geo():
    return carregar_modulo('orifsc_geo', 'algorithms', 'ocad', 'geo.py')


@pytest.fixture(scope='session')
def ocd():
    return carregar_modulo('orifsc_ocd', 'algorithms', 'ocad', 'ocd.py')


@pytest.fixture(scope='session')
def omap():
    return carregar_modulo('orifsc_omap', 'algorithms', 'ocad', 'omap.py')


@pytest.fixture(scope='session')
def simbologia():
    return carregar_modulo('orifsc_simbologia',
                           'algorithms', 'ocad', 'simbologia.py')
