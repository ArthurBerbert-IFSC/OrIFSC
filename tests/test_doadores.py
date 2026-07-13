"""Valida os doadores .ocd reais (exportados do OOM) quando presentes.

Os doadores de simbologia são gerados manualmente uma única vez (OOM:
Arquivo > Exportar como > OCD, versão 9 ou 10) e versionados em
``OrIFSC/recursos/simbologias/``. Estes testes garantem que cada arquivo
presente é utilizável pelo carregador do plugin (vendor/versão, símbolos
101/102, paleta completa) e que a injeção do projeto funciona sobre ele.
Enquanto os doadores não existirem, os testes são pulados (CI verde).
"""
import os
import struct
from types import SimpleNamespace

import pytest

_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'OrIFSC', 'recursos', 'simbologias')
DOADORES = [
    'ISOM_2017-2_15000.ocd',
    'ISOM_2017-2_10000.ocd',
    'ISSprOM_2019_4000.ocd',
]


def _caminho(nome):
    caminho = os.path.join(_DIR, nome)
    if not os.path.exists(caminho):
        pytest.skip(f'doador ainda não gerado: {nome}')
    return caminho


@pytest.mark.parametrize('nome', DOADORES)
def test_doador_carrega_e_tem_simbolos_de_curva(ocd, nome):
    with open(_caminho(nome), 'rb') as f:
        dados = f.read()
    w = ocd._OcdWriter.de_doador(dados)
    numeros = w.numeros_de_simbolos()
    assert len(numeros) > 100  # paleta completa da norma, não só curvas
    assert 101 * 1000 in numeros  # curva de nível
    assert 102 * 1000 in numeros  # curva mestra


@pytest.mark.parametrize('nome', DOADORES)
def test_doador_injecao_completa(ocd, nome, tmp_path):
    proj = SimpleNamespace(
        escala=10000, ref_e=700000.0, ref_n=6900000.0,
        grivacao=-19.5, i_grade=-2022,
        linhas_mm=[[(0.0, 0.0), (10.0, 5.0)], [(1.0, 1.0), (2.0, 2.0)]],
        codigos_linhas=['101', '102'],
        satelite={'path': 'satelite_orifsc.tif', 'centro_mm': (1.5, -2.5),
                  'u_mm': 0.03, 'v_mm': 0.03},
    )
    caminho = str(tmp_path / 'projeto.ocd')
    ocd.escrever_ocd_v10(proj, caminho, doador=_caminho(nome))
    b = open(caminho, 'rb').read()
    assert struct.unpack_from('<H', b, 0)[0] == 0x0CAD
    assert struct.unpack_from('<H', b, 4)[0] == 10  # sempre sai OCD v10
