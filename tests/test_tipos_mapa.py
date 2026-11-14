"""Tipos de mapa (algorithms/ocad/tipos_mapa.py) — valores decididos em
nov/2026 com a FLORA."""
import pytest


@pytest.mark.parametrize('tipo_id, norma, escala, equi, papel', [
    ('sprint', 'ISSPROM', 4000, 2.5, 'A4'),
    ('floresta', 'ISOM', 10000, 5.0, 'A4'),
    ('escolar', 'ISSPROM', 2000, 2.0, 'A4'),
])
def test_predefinicoes_decididas(tipos_mapa, tipo_id, norma, escala, equi,
                                 papel):
    t = tipos_mapa.tipo_por_id(tipo_id)
    assert (t.norma, t.escala, t.equidistancia, t.papel) == \
        (norma, escala, equi, papel)
    assert tipos_mapa.tem_predefinicao(t)


def test_personalizado_nao_fixa_nada(tipos_mapa):
    t = tipos_mapa.tipo_por_id('personalizado')
    assert (t.norma, t.escala, t.equidistancia, t.papel) == \
        (None, None, None, None)
    assert not tipos_mapa.tem_predefinicao(t)
    assert not tipos_mapa.tem_predefinicao(None)


def test_ids_unicos_e_desconhecido(tipos_mapa):
    ids = [t.id for t in tipos_mapa.TIPOS_MAPA]
    assert len(ids) == len(set(ids))
    assert tipos_mapa.tipo_por_id('orientacao-noturna') is None
    assert tipos_mapa.tipo_por_id(None) is None


def test_normas_iguais_as_da_simbologia(tipos_mapa, simbologia):
    assert tipos_mapa.NORMA_ISOM == simbologia.NORMA_ISOM
    assert tipos_mapa.NORMA_ISSPROM == simbologia.NORMA_ISSPROM


def test_equidistancias_cabem_no_parametro_das_curvas(tipos_mapa):
    # Faixa do parâmetro Equidistância de gerar_curvas (0,5 a 100 m).
    for t in tipos_mapa.TIPOS_MAPA:
        if tipos_mapa.tem_predefinicao(t):
            assert 0.5 <= t.equidistancia <= 100.0


def test_resumo(tipos_mapa):
    assert tipos_mapa.resumo(tipos_mapa.tipo_por_id('sprint')) == \
        'ISSprOM 2019-2 · 1:4.000 · equidistância 2,5 m · A4'
    assert tipos_mapa.resumo(tipos_mapa.tipo_por_id('floresta')) == \
        'ISOM 2017-2 · 1:10.000 · equidistância 5 m · A4'
    assert 'Configurações' in tipos_mapa.resumo(
        tipos_mapa.tipo_por_id('personalizado'))
