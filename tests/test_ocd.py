"""Escritor binário OCD v10: cabeçalho, índices e coordenadas dos objetos.

Usa um "projeto" falso (SimpleNamespace) com os mesmos atributos que o
``ProjetoOcad`` real expõe, e valida o arquivo gerado byte a byte contra o
contrato do formato (portado do OpenOrienteering Mapper).
"""
import struct
from types import SimpleNamespace

_STR_ENTRY = 16
_OBJ_ENTRY = 40
_OBJ_POS_OFFSET = 16


def _projeto_falso(linhas_mm, satelite=None):
    return SimpleNamespace(
        escala=10000,
        cor=(0.0, 0.56, 1.0, 0.18),
        cor_nome='Marrom (curvas)',
        largura_um=140,
        codigo_simbolo=101,
        ref_e=700000.0,
        ref_n=6900000.0,
        grivacao=-19.5,
        i_grade=-2022,
        linhas_mm=linhas_mm,
        satelite=satelite,
    )


def _u32(b, off):
    return struct.unpack_from('<I', b, off)[0]


def _tipos_de_string(b):
    """Percorre o índice de strings e devolve a lista de tipos gravados."""
    tipos = []
    bloco = _u32(b, 32)
    while bloco:
        for i in range(256):
            pos_entrada = bloco + 4 + i * _STR_ENTRY
            if _u32(b, pos_entrada) == 0:
                continue
            tipos.append(struct.unpack_from('<i', b, pos_entrada + 8)[0])
        bloco = _u32(b, bloco)
    return tipos


def _objetos(b):
    """Percorre o índice de objetos e devolve as posições das entidades."""
    posicoes = []
    bloco = _u32(b, 12)
    while bloco:
        for i in range(256):
            entrada = bloco + 4 + i * _OBJ_ENTRY
            pos = _u32(b, entrada + _OBJ_POS_OFFSET)
            if pos:
                posicoes.append(pos)
        bloco = _u32(b, bloco)
    return posicoes


def test_round_half_up(ocd):
    assert ocd._round_half_up(0.5) == 1
    assert ocd._round_half_up(1.5) == 2
    assert ocd._round_half_up(-0.5) == 0
    assert ocd._round_half_up(2.4) == 2
    assert ocd._round_half_up(-2.6) == -3


def test_cabecalho_vendor_e_versao(ocd, tmp_path):
    caminho = str(tmp_path / 'projeto.ocd')
    ocd.escrever_ocd_v10(_projeto_falso([[(0.0, 0.0), (10.0, 5.0)]]), caminho)
    b = open(caminho, 'rb').read()
    assert struct.unpack_from('<H', b, 0)[0] == 0x0CAD
    assert struct.unpack_from('<H', b, 4)[0] == 10  # OCD v10 (OCAD 10)
    # Offsets do cabeçalho apontam para dentro do arquivo.
    for off in (8, 12, 32):
        assert 0 < _u32(b, off) < len(b)


def test_strings_de_cor_e_georreferencia(ocd, tmp_path):
    caminho = str(tmp_path / 'projeto.ocd')
    ocd.escrever_ocd_v10(_projeto_falso([[(0.0, 0.0), (10.0, 5.0)]]), caminho)
    tipos = _tipos_de_string(open(caminho, 'rb').read())
    assert 9 in tipos      # cor CMYK
    assert 1039 in tipos   # georreferência (escala, grivação, grade)
    assert 8 not in tipos  # sem satélite -> sem template


def test_template_de_satelite_quando_presente(ocd, tmp_path):
    sat = {'path': 'satelite_orifsc.tif', 'centro_mm': (1.5, -2.5),
           'u_mm': 0.03, 'v_mm': 0.03}
    caminho = str(tmp_path / 'projeto.ocd')
    ocd.escrever_ocd_v10(
        _projeto_falso([[(0.0, 0.0), (10.0, 5.0)]], satelite=sat), caminho)
    assert 8 in _tipos_de_string(open(caminho, 'rb').read())


def test_objetos_um_por_linha_com_coordenadas_em_centesimos_de_mm(
        ocd, tmp_path):
    linhas = [[(0.0, 0.0), (10.0, 5.0), (20.0, 0.0)],
              [(1.0, 1.0), (2.0, 2.0)]]
    caminho = str(tmp_path / 'projeto.ocd')
    ocd.escrever_ocd_v10(_projeto_falso(linhas), caminho)
    b = open(caminho, 'rb').read()
    posicoes = _objetos(b)
    assert len(posicoes) == len(linhas)

    pos = posicoes[0]
    numero = struct.unpack_from('<i', b, pos)[0]
    assert numero == 101 * 1000  # código do símbolo x fator
    n_coords = _u32(b, pos + 8)
    assert n_coords == 3
    # 2º vértice: (10 mm, 5 mm) -> 1/100 mm, y para cima, deslocado 8 bits.
    x, y = struct.unpack_from('<ii', b, pos + 40 + 8)
    assert x == (1000 << 8)
    assert y == (-500 << 8)


def test_linha_vazia_gera_arquivo_valido(ocd, tmp_path):
    caminho = str(tmp_path / 'projeto.ocd')
    ocd.escrever_ocd_v10(_projeto_falso([]), caminho)
    b = open(caminho, 'rb').read()
    assert struct.unpack_from('<H', b, 0)[0] == 0x0CAD
    assert _objetos(b) == []
