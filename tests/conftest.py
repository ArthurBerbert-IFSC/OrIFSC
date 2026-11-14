"""Infraestrutura dos testes.

Os testes cobrem os módulos PUROS do plugin (sem dependência do QGIS) e por
isso rodam com Python + NumPy + pytest, sem uma instalação do QGIS. Como os
``__init__.py`` do pacote importam ``qgis``, cada módulo é carregado direto do
arquivo com ``importlib`` (sem executar os ``__init__``).
"""
import importlib
import importlib.util
import os
import sys
import types

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


@pytest.fixture(scope='session')
def wmm():
    return carregar_modulo('orifsc_wmm', 'algorithms', 'ocad', 'wmm.py')


def carregar_do_nucleo(nome: str):
    """Carrega ``algorithms/ocad/<nome>.py`` como submódulo de um pacote
    sintético, para que imports relativos entre módulos puros do núcleo
    (ex.: folha → geo) funcionem sem executar o ``__init__`` (que usa qgis).
    """
    pacote = 'orifsc_nucleo'
    if pacote not in sys.modules:
        mod_pacote = types.ModuleType(pacote)
        mod_pacote.__path__ = [os.path.join(PACOTE, 'algorithms', 'ocad')]
        sys.modules[pacote] = mod_pacote
    return importlib.import_module(f'{pacote}.{nome}')


@pytest.fixture(scope='session')
def folha():
    return carregar_do_nucleo('folha')


@pytest.fixture(scope='session')
def geo_nucleo():
    """O mesmo geo.py que o folha.py usa (via pacote sintético)."""
    return carregar_do_nucleo('geo')
