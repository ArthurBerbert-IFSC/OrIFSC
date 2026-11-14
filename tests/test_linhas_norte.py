"""Linhas de norte magnético (parte 6): espaçamento da norma, geometria no
papel, símbolo certo em cada symbol set embutido e escrita no .omap/.ocd.

Decisão de nov/2026: linhas separadas, pretas, no símbolo de linha de norte
da norma (o mapeador corta cada uma onde esconder detalhes).
"""
import math
import os
import struct
import xml.etree.ElementTree as ET
from types import SimpleNamespace

import pytest

NS = '{http://openorienteering.org/apps/mapper/xml/v2}'
_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__))), 'OrIFSC', 'recursos', 'simbologias')
A4_RETRATO = [(-105, -148.5), (105, -148.5), (105, 148.5), (-105, 148.5)]


@pytest.mark.parametrize('norma, escala, esperado', [
    ('ISOM', 15000, 20.0),     # texto da norma: 20 mm = 300 m
    ('ISOM', 10000, 30.0),     # ampliação 1:10.000: 30 mm
    ('ISOM', 7500, 40.0),
    ('ISSPROM', 4000, 30.0),   # texto da norma: 30 mm = 120 m
    ('ISSPROM', 3000, 30.0),
    ('ISSPROM', 2000, 30.0),   # Escolar
])
def test_espacamento_da_norma(geo, norma, escala, esperado):
    assert geo.espacamento_norte_mm(norma, escala) == pytest.approx(esperado)


def test_espacamento_norma_desconhecida(geo):
    with pytest.raises(ValueError):
        geo.espacamento_norte_mm('IOF-MTBO', 10000)


def test_linhas_verticais_de_baixo_para_cima_cobrindo_a_folha(geo):
    linhas = geo.linhas_norte(A4_RETRATO, 30.0)
    assert [l[0][0] for l in linhas] == [-90, -60, -30, 0, 30, 60, 90]
    for (x0, y0), (x1, y1) in linhas:
        assert x0 == x1
        assert (y0, y1) == pytest.approx((148.5, -148.5))  # sul → norte


def test_paisagem_e_espacamento_isom_15000(geo):
    paisagem = [(-148.5, -105), (148.5, -105), (148.5, 105), (-148.5, 105)]
    assert len(geo.linhas_norte(paisagem, 30.0)) == 9    # -120 .. 120
    assert len(geo.linhas_norte(paisagem, 20.0)) == 15   # -140 .. 140


def test_linha_sobre_a_borda_e_omitida(geo):
    quadrado = [(-60, -50), (60, -50), (60, 50), (-60, 50)]
    assert [l[0][0] for l in geo.linhas_norte(quadrado, 30.0)] == \
        [-30, 0, 30]


def test_anel_fechado_e_folha_girada_da_versao_antiga(geo):
    # Folha 0.1.x: retângulo girado no papel; linhas recortadas por ele.
    g = math.radians(19.0)
    cantos = [(x * math.cos(g) - y * math.sin(g),
               x * math.sin(g) + y * math.cos(g))
              for x, y in A4_RETRATO]
    anel = cantos + cantos[:1]
    linhas = geo.linhas_norte(anel, 30.0)
    assert linhas
    for (x, y_baixo), (_, y_cima) in linhas:
        assert y_baixo > y_cima
        for y in (y_baixo, y_cima):   # extremos sobre o contorno
            dist = min(_dist_segmento((x, y), a, b)
                       for a, b in zip(cantos, cantos[1:] + cantos[:1]))
            assert dist < 1e-6


def _dist_segmento(p, a, b):
    (px, py), (ax, ay), (bx, by) = p, a, b
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy)
                     / (dx * dx + dy * dy)))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def test_poligono_degenerado(geo):
    assert geo.linhas_norte([(0, 0), (10, 0)], 30.0) == []
    with pytest.raises(ValueError):
        geo.linhas_norte(A4_RETRATO, 0.0)


def test_numero_ocd(ocd):
    assert ocd.numero_ocd('601') == 601000
    assert ocd.numero_ocd('601.1') == 601001
    assert ocd.numero_ocd('101') == 101000


@pytest.mark.parametrize('norma, arquivo_omap, arquivo_ocd', [
    ('ISOM', 'ISOM_2017-2_15000.omap', 'ISOM_2017-2_15000.ocd'),
    ('ISOM', 'ISOM_2017-2_10000.omap', 'ISOM_2017-2_10000.ocd'),
    ('ISSPROM', 'ISSprOM_2019_4000.omap', 'ISSprOM_2019_4000.ocd'),
])
def test_codigo_aponta_para_a_linha_de_norte_preta(
        simbologia, ocd, norma, arquivo_omap, arquivo_ocd):
    codigo = simbologia.CODIGO_LINHA_NORTE[norma]
    raiz = ET.parse(os.path.join(_DIR, arquivo_omap)).getroot()
    simbolos = [s for s in raiz.iter(f'{NS}symbol') if s.get('code') == codigo]
    assert len(simbolos) == 1
    assert simbolos[0].get('name') == 'Magnetic north line'
    assert simbolos[0].get('type') == '2'   # símbolo de linha, não de área
    caminho_ocd = os.path.join(_DIR, arquivo_ocd)
    w = ocd._OcdWriter.de_doador(open(caminho_ocd, 'rb').read())
    assert ocd.numero_ocd(codigo) in w.numeros_de_simbolos()


def _projeto(linhas_norte, codigo_norte, escala=4000):
    return SimpleNamespace(
        escala=escala, declinacao=-20.1, grivacao=-18.9,
        proj4='+proj=utm +zone=22 +south +datum=WGS84 +units=m +no_defs',
        crs_param='22 S', ref_e=741000.0, ref_n=6944000.0,
        lat=-27.6, lon=-48.5, i_grade=-2022,
        linhas_mm=[[(0.0, 0.0), (10.0, 5.0)]], codigos_linhas=['101'],
        satelite=None, linhas_norte_mm=linhas_norte,
        codigo_norte=codigo_norte)


def test_omap_grava_linhas_de_norte_no_simbolo_certo(simbologia, geo,
                                                     tmp_path):
    linhas = geo.linhas_norte(A4_RETRATO, 30.0)
    base = simbologia.arquivo_simbologia(simbologia.NORMA_ISSPROM, 4000)
    caminho = str(tmp_path / 'p.omap')
    simbologia.escrever_omap_com_simbologia(
        _projeto(linhas, '601'), caminho, base)
    raiz = ET.parse(caminho).getroot()
    id_norte = [s.get('id') for s in raiz.iter(f'{NS}symbol')
                if s.get('code') == '601'][0]
    objetos = raiz.find(f'.//{NS}objects')
    assert objetos.get('count') == str(1 + len(linhas))
    norte = [o for o in objetos if o.get('symbol') == id_norte]
    assert len(norte) == len(linhas) == 7
    coords = norte[3].find(f'{NS}coords').text   # linha central (x = 0)
    assert coords == '0 148500;0 -148500;'


def test_omap_sem_o_simbolo_falha_claro(simbologia, tmp_path):
    base = simbologia.arquivo_simbologia(simbologia.NORMA_ISOM, 15000)
    with pytest.raises(ValueError, match='linha de norte'):
        simbologia.escrever_omap_com_simbologia(
            _projeto([[(0, 1), (0, -1)]], '999.9'), str(tmp_path / 'p.omap'),
            base)


def test_omap_sem_linhas_de_norte_continua_igual(simbologia, tmp_path):
    base = simbologia.arquivo_simbologia(simbologia.NORMA_ISOM, 15000)
    caminho = str(tmp_path / 'p.omap')
    simbologia.escrever_omap_com_simbologia(_projeto([], None), caminho, base)
    objetos = ET.parse(caminho).getroot().find(f'.//{NS}objects')
    assert objetos.get('count') == '1'


def _numeros_dos_objetos(b):
    numeros = []
    bloco = struct.unpack_from('<I', b, 12)[0]
    while bloco:
        for i in range(256):
            pos = struct.unpack_from('<I', b, bloco + 4 + i * 40 + 16)[0]
            if pos:
                numeros.append(struct.unpack_from('<i', b, pos)[0])
        bloco = struct.unpack_from('<I', b, bloco)[0]
    return numeros


@pytest.mark.parametrize('norma, doador, numero', [
    ('ISOM', 'ISOM_2017-2_10000.ocd', 601001),
    ('ISSPROM', 'ISSprOM_2019_4000.ocd', 601000),
])
def test_ocd_com_doador_grava_linhas_de_norte(simbologia, geo, ocd, tmp_path,
                                              norma, doador, numero):
    linhas = geo.linhas_norte(A4_RETRATO, 30.0)
    caminho = str(tmp_path / 'p.ocd')
    ocd.escrever_ocd_v10(
        _projeto(linhas, simbologia.CODIGO_LINHA_NORTE[norma]), caminho,
        doador=os.path.join(_DIR, doador))
    numeros = _numeros_dos_objetos(open(caminho, 'rb').read())
    assert numeros.count(101000) == 1
    assert numeros.count(numero) == len(linhas) == 7


def test_ocd_sem_doador_nao_tem_simbolo_e_omite_as_linhas(geo, ocd,
                                                          tmp_path):
    proj = _projeto(geo.linhas_norte(A4_RETRATO, 30.0), '601')
    proj.cor, proj.cor_nome = (0.0, 0.56, 1.0, 0.18), 'Marrom'
    proj.largura_um, proj.codigo_simbolo = 140, 101
    caminho = str(tmp_path / 'p.ocd')
    ocd.escrever_ocd_v10(proj, caminho)
    assert _numeros_dos_objetos(open(caminho, 'rb').read()) == [101000]
