"""Folha girada para o norte magnético (geo.cantos_folha / papel_para_mundo).

A propriedade que importa: mapeada de volta para o papel do OCAD/OOM pelo
mesmo QTransform da exportação (ProjetoOcad), a folha vira um retângulo em
pé, do tamanho exato do papel — sem a "imagem torcida" da 0.1.x.
"""
import math

import pytest

GRIVACOES = [-21.3, -5.0, 0.0, 3.7, 14.2]


def _transform_projeto(ref_e, ref_n, escala, grivacao):
    """O mesmo QTransform que ProjetoOcad monta (papel mm → UTM)."""
    qtgui = pytest.importorskip('PyQt5.QtGui')
    t = qtgui.QTransform()
    t.translate(ref_e, ref_n)
    t.rotate(-grivacao)
    s = escala / 1000.0
    t.scale(s, -s)
    return t


def test_grivacao_e_declinacao_menos_convergencia(geo):
    assert geo.grivacao(-20.1, -1.1) == pytest.approx(-19.0)
    assert geo.grivacao(5.0, 0.0) == 5.0


@pytest.mark.parametrize('grivacao', GRIVACOES)
def test_papel_para_mundo_igual_ao_qtransform_da_exportacao(geo, grivacao):
    qtcore = pytest.importorskip('PyQt5.QtCore')
    ref_e, ref_n, escala = 744210.5, 6943120.25, 4000
    t = _transform_projeto(ref_e, ref_n, escala, grivacao)
    for x, y in [(0, 0), (148.5, -105), (-148.5, 105), (12.3, 45.6)]:
        esperado = t.map(qtcore.QPointF(x, y))
        e, n = geo.papel_para_mundo(x, y, ref_e, ref_n, escala, grivacao)
        assert e == pytest.approx(esperado.x(), abs=1e-6)
        assert n == pytest.approx(esperado.y(), abs=1e-6)


@pytest.mark.parametrize('grivacao', GRIVACOES)
def test_folha_fica_em_pe_no_papel_do_ocad(geo, grivacao):
    qtcore = pytest.importorskip('PyQt5.QtCore')
    ref_e, ref_n, escala = 744210.5, 6943120.25, 10000
    cantos = geo.cantos_folha(ref_e, ref_n, 297, 210, escala, grivacao)
    para_papel, ok = _transform_projeto(ref_e, ref_n, escala,
                                        grivacao).inverted()
    assert ok
    papel = [para_papel.map(qtcore.QPointF(e, n)) for e, n in cantos]
    esperado = [(-148.5, -105), (148.5, -105), (148.5, 105), (-148.5, 105)]
    for p, (x, y) in zip(papel, esperado):
        assert p.x() == pytest.approx(x, abs=1e-6)
        assert p.y() == pytest.approx(y, abs=1e-6)


@pytest.mark.parametrize('grivacao', GRIVACOES)
def test_tamanho_e_rumo_da_folha_no_terreno(geo, grivacao):
    escala = 4000
    se, sd, idir, ie = geo.cantos_folha(0.0, 0.0, 297, 210, escala, grivacao)
    assert math.dist(se, sd) == pytest.approx(0.297 * escala)
    assert math.dist(sd, idir) == pytest.approx(0.210 * escala)
    # O topo da folha aponta para o norte magnético: azimute (horário, a
    # partir do norte da quadrícula) do centro ao meio da borda superior.
    meio_topo = ((se[0] + sd[0]) / 2, (se[1] + sd[1]) / 2)
    azimute = math.degrees(math.atan2(meio_topo[0], meio_topo[1]))
    assert azimute == pytest.approx(grivacao)


def test_sem_grivacao_e_o_retangulo_da_versao_antiga(geo):
    cantos = geo.cantos_folha(1000.0, 2000.0, 297, 210, 4000, 0.0)
    assert cantos == [
        pytest.approx((1000 - 594, 2000 + 420)),
        pytest.approx((1000 + 594, 2000 + 420)),
        pytest.approx((1000 + 594, 2000 - 420)),
        pytest.approx((1000 - 594, 2000 - 420)),
    ]
