"""Tamanhos de papel e dimensões da folha (algorithms/ocad/folha.py)."""
import pytest


def test_dimensoes_papel_por_orientacao(folha):
    assert folha.dimensoes_papel('A4', retrato=False) == (297, 210)
    assert folha.dimensoes_papel('A4', retrato=True) == (210, 297)
    assert folha.dimensoes_papel('A3', retrato=False) == (420, 297)
    assert folha.dimensoes_papel('A5', retrato=True) == (148, 210)


def test_papel_desconhecido(folha):
    with pytest.raises(ValueError):
        folha.dimensoes_papel('Carta', retrato=False)


@pytest.mark.parametrize('nome', ['A3', 'A4', 'A5'])
@pytest.mark.parametrize('retrato', [False, True])
def test_identificar_papel_e_inverso_de_dimensoes(folha, nome, retrato):
    larg, alt = folha.dimensoes_papel(nome, retrato)
    assert folha.identificar_papel(larg, alt) == (nome, retrato)


def test_identificar_papel_tolera_arredondamento_de_projeto_antigo(folha):
    # 0.1.x guardava o retângulo em metros; voltar para mm dá ruído de float.
    larg = 1188.0000000002 * 1000 / 4000
    alt = 839.9999999998 * 1000 / 4000
    assert folha.identificar_papel(larg, alt) == ('A4', False)


def test_identificar_papel_fora_da_tabela(folha):
    assert folha.identificar_papel(300, 300) is None


def test_area_terreno(folha):
    assert folha.area_terreno_m(297, 210, 4000) == pytest.approx((1188, 840))
    assert folha.area_terreno_m(210, 297, 10000) == pytest.approx((2100, 2970))
