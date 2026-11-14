"""Ajustar a folha ao limite (folha.ajustar_ao_limite) — decisões de nov/2026:
papel aumenta primeiro, escala não muda sozinha, papel nunca diminui, 5 mm de
folga no papel, orientação pela proporção do limite."""
import math

import pytest

GRIV_FLORIPA = -18.94


def _retangulo_no_papel(geo, cx, cy, larg_mm, alt_mm, escala, griv):
    """Vértices (UTM) de um retângulo alinhado ao papel (norte magnético)."""
    return geo.cantos_folha(cx, cy, larg_mm, alt_mm, escala, griv)


def _folga_minima_mm(geo, pontos, ajuste, griv):
    """Menor distância (mm de papel) entre o limite e a borda da folha."""
    folgas = []
    for e, n in pontos:
        x, y = geo.mundo_para_papel(e, n, ajuste.ref_e, ajuste.ref_n,
                                    ajuste.escala, griv)
        folgas += [ajuste.larg_mm / 2 - abs(x), ajuste.alt_mm / 2 - abs(y)]
    return min(folgas)


def test_mundo_para_papel_e_inverso_de_papel_para_mundo(geo):
    for griv in (-21.3, 0.0, 14.2):
        e, n = geo.papel_para_mundo(37.5, -81.25, 741000.0, 6944000.0, 4000,
                                    griv)
        x, y = geo.mundo_para_papel(e, n, 741000.0, 6944000.0, 4000, griv)
        assert (x, y) == pytest.approx((37.5, -81.25), abs=1e-9)


def test_limite_pequeno_mantem_o_papel_escolhido(folha, geo_nucleo):
    # 100 x 60 mm no papel: caberia num A5, mas o papel nunca diminui.
    pts = _retangulo_no_papel(geo_nucleo, 741000, 6944000, 100, 60, 4000,
                              GRIV_FLORIPA)
    a = folha.ajustar_ao_limite(pts, 4000, GRIV_FLORIPA, 'A4')
    assert (a.cabe, a.papel, a.retrato) == (True, 'A4', False)
    assert (a.ref_e, a.ref_n) == pytest.approx((741000, 6944000))
    assert a.escala == 4000


def test_limite_alto_vira_retrato(folha, geo_nucleo):
    pts = _retangulo_no_papel(geo_nucleo, 741000, 6944000, 150, 250, 4000,
                              GRIV_FLORIPA)
    a = folha.ajustar_ao_limite(pts, 4000, GRIV_FLORIPA, 'A4')
    assert (a.cabe, a.papel, a.retrato) == (True, 'A4', True)
    assert (a.larg_mm, a.alt_mm) == (210, 297)


def test_limite_que_nao_cabe_em_a4_aumenta_para_a3(folha, geo_nucleo):
    pts = _retangulo_no_papel(geo_nucleo, 741000, 6944000, 350, 250, 4000,
                              GRIV_FLORIPA)
    a = folha.ajustar_ao_limite(pts, 4000, GRIV_FLORIPA, 'A4')
    assert (a.cabe, a.papel, a.retrato, a.escala) == (True, 'A3', False, 4000)


def test_folga_de_5mm_e_respeitada_no_limite_exato(folha, geo_nucleo):
    # 287 x 200 mm + 2 x 5 mm = A4 paisagem exato: cabe.
    pts = _retangulo_no_papel(geo_nucleo, 741000, 6944000, 287, 200, 4000,
                              GRIV_FLORIPA)
    a = folha.ajustar_ao_limite(pts, 4000, GRIV_FLORIPA, 'A4')
    assert (a.cabe, a.papel) == (True, 'A4')
    assert _folga_minima_mm(geo_nucleo, pts, a, GRIV_FLORIPA) == \
        pytest.approx(5.0, abs=1e-6)
    # 1 mm a mais já não cabe em A4.
    pts = _retangulo_no_papel(geo_nucleo, 741000, 6944000, 288, 200, 4000,
                              GRIV_FLORIPA)
    assert folha.ajustar_ao_limite(pts, 4000, GRIV_FLORIPA, 'A4').papel == 'A3'


def test_poligono_irregular_fica_dentro_com_folga(folha, geo_nucleo):
    # Hexágono irregular "deitado" em UTM; a folha está girada ~19°.
    cx, cy = 742000.0, 6945000.0
    pts = [(cx + 520 * math.cos(math.radians(a)), cy + 310 * math.sin(
        math.radians(a)) + 40 * math.cos(math.radians(3 * a)))
        for a in range(0, 360, 15)]
    a = folha.ajustar_ao_limite(pts, 4000, GRIV_FLORIPA, 'A4')
    assert a.cabe
    assert _folga_minima_mm(geo_nucleo, pts, a, GRIV_FLORIPA) >= 5.0 - 1e-6


def test_nao_cabe_nem_em_a3_informa_escala_minima(folha, geo_nucleo):
    pts = _retangulo_no_papel(geo_nucleo, 741000, 6944000, 600, 380, 4000,
                              GRIV_FLORIPA)
    a = folha.ajustar_ao_limite(pts, 4000, GRIV_FLORIPA, 'A4')
    assert not a.cabe
    assert (a.papel, a.retrato, a.escala) == ('A3', False, 4000)
    # Na escala mínima o limite cabe exatamente no A3 com 5 mm de folga.
    assert a.escala_minima == pytest.approx(4000 * max(600 / 410, 380 / 287))
    b = folha.ajustar_ao_limite(pts, a.escala_minima + 1e-6, GRIV_FLORIPA,
                                'A4')
    assert (b.cabe, b.papel) == (True, 'A3')


def test_papel_inicial_a3_nunca_diminui(folha, geo_nucleo):
    pts = _retangulo_no_papel(geo_nucleo, 741000, 6944000, 50, 40, 10000,
                              GRIV_FLORIPA)
    assert folha.ajustar_ao_limite(pts, 10000, GRIV_FLORIPA, 'A3').papel == \
        'A3'


def test_limite_vazio_ou_papel_desconhecido(folha):
    with pytest.raises(ValueError):
        folha.ajustar_ao_limite([], 4000, 0.0, 'A4')
    with pytest.raises(ValueError):
        folha.ajustar_ao_limite([(0, 0), (1, 1)], 4000, 0.0, 'Carta')


@pytest.mark.parametrize('minima, esperada', [
    (3200.0, 4000), (4000.0, 4000), (4000.4, 5000), (7400, 7500),
    (14999.0, 15000), (15001.0, 15500), (21234.0, 21500),
])
def test_escala_sugerida(folha, minima, esperada):
    assert folha.escala_sugerida(minima) == esperada
