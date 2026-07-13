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


# --- Doador de simbologia (paleta completa injetada no .ocd) ---------------


def _doador_bytes(ocd, codigos=(101, 102), versao=9, com_objetos=True):
    """Doador sintético: paleta com os símbolos dados, objetos de exemplo
    e strings próprias (cor 9, georreferência 1039, template 8) — o mesmo
    que um export OCD do symbol set do OOM traz."""
    from types import SimpleNamespace
    w = ocd._OcdWriter()
    w.add_string(9, 'Marrom\tn0\tc0\tm56\ty100\tk18\to1\tt100')
    w.add_string(1039, '\tm15000\tg50.0\tr1\tx0\ty0\ta0\td500\ti2001')
    w.add_string(8, 'exemplo.tif\ts1\tx0\ty0')
    for codigo in codigos:
        proj = SimpleNamespace(codigo_simbolo=codigo, largura_um=140)
        w.add_symbol(ocd._simbolo_linha_bytes(proj))
    if com_objetos:
        for linha in ([(0.0, 0.0), (5.0, 5.0)], [(1.0, 1.0), (2.0, 0.0)]):
            dados, bounds = ocd._objeto_bytes(linha, codigos[0] * 1000)
            w.add_object(dados, bounds, codigos[0] * 1000, 2, 0)
    struct.pack_into('<H', w.ba, 4, versao)
    return bytes(w.ba)


def _salvar_doador(ocd, tmp_path, **kwargs):
    caminho = str(tmp_path / 'doador.ocd')
    with open(caminho, 'wb') as f:
        f.write(_doador_bytes(ocd, **kwargs))
    return caminho


def _strings(b):
    """Lista (tipo, texto) das strings referenciadas pelo índice."""
    resultado = []
    bloco = _u32(b, 32)
    while bloco:
        for i in range(256):
            epos = bloco + 4 + i * _STR_ENTRY
            pos = _u32(b, epos)
            if pos == 0:
                continue
            tam = _u32(b, epos + 4)
            tipo = struct.unpack_from('<i', b, epos + 8)[0]
            resultado.append((tipo, b[pos:pos + tam].rstrip(b'\x00')
                              .decode('latin-1')))
        bloco = _u32(b, bloco)
    return resultado


def test_doador_rejeita_lixo_e_versao_incompativel(ocd):
    import pytest
    with pytest.raises(ValueError):
        ocd._OcdWriter.de_doador(b'\x00' * 64)
    with pytest.raises(ValueError):
        ocd._OcdWriter.de_doador(_doador_bytes(ocd, versao=8))


def test_doador_v9_sai_como_v10(ocd, tmp_path):
    doador = _salvar_doador(ocd, tmp_path, versao=9)
    caminho = str(tmp_path / 'projeto.ocd')
    ocd.escrever_ocd_v10(_projeto_falso([[(0.0, 0.0), (1.0, 1.0)]]),
                         caminho, doador=doador)
    b = open(caminho, 'rb').read()
    assert struct.unpack_from('<H', b, 4)[0] == 10
    # O arquivo doador em disco permanece intacto (v9).
    assert struct.unpack_from('<H', open(doador, 'rb').read(), 4)[0] == 9


def test_doador_remove_exemplos_e_grava_curvas_101_e_102(ocd, tmp_path):
    doador = _salvar_doador(ocd, tmp_path)
    linhas = [[(0.0, 0.0), (10.0, 5.0)], [(1.0, 1.0), (2.0, 2.0)]]
    proj = _projeto_falso(linhas)
    proj.codigos_linhas = ['101', '102']
    caminho = str(tmp_path / 'projeto.ocd')
    ocd.escrever_ocd_v10(proj, caminho, doador=doador)
    b = open(caminho, 'rb').read()
    posicoes = _objetos(b)
    assert len(posicoes) == 2  # só as curvas; exemplos do doador removidos
    numeros = [struct.unpack_from('<i', b, pos)[0] for pos in posicoes]
    assert numeros == [101 * 1000, 102 * 1000]


def test_doador_preserva_simbolos_e_cor_substitui_georreferencia(
        ocd, tmp_path):
    doador = _salvar_doador(ocd, tmp_path)
    caminho = str(tmp_path / 'projeto.ocd')
    ocd.escrever_ocd_v10(_projeto_falso([[(0.0, 0.0), (1.0, 1.0)]]),
                         caminho, doador=doador)
    b = open(caminho, 'rb').read()
    w = ocd._OcdWriter.de_doador(b)
    assert sorted(w.numeros_de_simbolos()) == [101000, 102000]
    strings = _strings(b)
    tipos = [t for (t, _) in strings]
    assert tipos.count(9) == 1     # cor do doador preservada
    assert tipos.count(1039) == 1  # georreferência única: a do projeto
    assert 8 not in tipos          # template do doador descartado
    georref = [txt for (t, txt) in strings if t == 1039][0]
    assert '\tm10000\t' in georref  # escala do projeto, não a do doador


def test_doador_template_do_satelite(ocd, tmp_path):
    doador = _salvar_doador(ocd, tmp_path)
    sat = {'path': 'satelite_orifsc.tif', 'centro_mm': (1.5, -2.5),
           'u_mm': 0.03, 'v_mm': 0.03}
    caminho = str(tmp_path / 'projeto.ocd')
    ocd.escrever_ocd_v10(
        _projeto_falso([[(0.0, 0.0), (1.0, 1.0)]], satelite=sat),
        caminho, doador=doador)
    strings = _strings(open(caminho, 'rb').read())
    templates = [txt for (t, txt) in strings if t == 8]
    assert len(templates) == 1
    assert templates[0].startswith('satelite_orifsc.tif')


def test_doador_sem_101_falha_sem_102_degrada(ocd, tmp_path):
    import pytest
    caminho = str(tmp_path / 'projeto.ocd')

    doador = _salvar_doador(ocd, tmp_path, codigos=(103,))
    with pytest.raises(ValueError):
        ocd.escrever_ocd_v10(_projeto_falso([[(0.0, 0.0), (1.0, 1.0)]]),
                             caminho, doador=doador)

    doador = _salvar_doador(ocd, tmp_path, codigos=(101,))
    proj = _projeto_falso([[(0.0, 0.0), (1.0, 1.0)]])
    proj.codigos_linhas = ['102']
    ocd.escrever_ocd_v10(proj, caminho, doador=doador)
    b = open(caminho, 'rb').read()
    numeros = [struct.unpack_from('<i', b, pos)[0] for pos in _objetos(b)]
    assert numeros == [101 * 1000]  # mestra degrada para a curva normal
