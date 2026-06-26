"""Escritor de arquivo .ocd binário (OCAD 10 / formato versão 10).

Portado das estruturas e da lógica de exportação do OpenOrienteering Mapper
(GPLv3): `ocd_types.h`, `ocd_types_v8.h`, `ocd_types_v9.h`, `ocd_types.cpp`
(montagem de blocos) e `ocd_file_export.cpp` (strings 9/1039/8, símbolo de linha
e objetos). O formato v10 é estruturalmente idêntico ao v9 (no OOM,
`ocd_types_v10.h` é apenas `using FormatV10 = FormatV9;`); muda só o número de
versão no cabeçalho. Tudo little-endian e com structs "packed" (sem alinhamento).

Modelo de coordenadas do OCD: 1/100 mm de papel, y para cima, valor deslocado 8
bits à esquerda (os 8 bits baixos guardam flags de vértice, aqui sempre 0).
"""
import math
import os
import struct

VENDOR = 0x0CAD
VERSION = 10
FATOR_SIMBOLO = 1000                 # BaseSymbolV9::symbol_number_factor

_STR_ENTRY = 16                      # ParameterStringIndexEntry
_SYM_ENTRY = 4                       # SymbolIndexEntry
_OBJ_ENTRY = 40                      # ObjectIndexEntryV9
_OBJ_POS_OFFSET = 16                 # ObjectIndexEntryV9: campo `pos` (após 2 OcdPoint32)

# Conferência das structs portadas (packed).
assert struct.calcsize('<HBBH BB' + 'I' * 10) == 48          # FileHeaderV9
assert struct.calcsize('<iBBhIHBBIHHIIII') == 40             # ObjectV9 (header)
assert struct.calcsize('<iiiiIIiBBBBHHHBB') == _OBJ_ENTRY    # ObjectIndexEntryV9


def _round_half_up(v):
    return int(math.floor(v + 0.5))


def _pad8(ba):
    ba.extend(b'\x00' * ((-len(ba)) % 8))


def _bloco(entry_size):
    """Bloco de índice zerado: next_block (4) + 256 entradas."""
    return bytearray(4 + 256 * entry_size)


def _u32(ba, off):
    return struct.unpack_from('<I', ba, off)[0]


def _enc(texto):
    """Codifica string de parâmetro no 8-bit do OCD (latin-1)."""
    return texto.encode('latin-1', 'replace')


class _OcdWriter:
    def __init__(self):
        self.ba = bytearray()
        self.ba += struct.pack('<HBBHBB', VENDOR, 0, 0, VERSION, 0, 0)  # 8 bytes
        self.ba += struct.pack('<10I', *([0] * 10))                    # -> 48
        # V9 não tem bloco de setup binário (só o V8 tem).
        _pad8(self.ba)
        self.first_string = len(self.ba); self.ba += _bloco(_STR_ENTRY)
        _pad8(self.ba)
        self.first_symbol = len(self.ba); self.ba += _bloco(_SYM_ENTRY)
        _pad8(self.ba)
        self.first_object = len(self.ba); self.ba += _bloco(_OBJ_ENTRY)
        struct.pack_into('<I', self.ba, 8, self.first_symbol)
        struct.pack_into('<I', self.ba, 12, self.first_object)
        struct.pack_into('<I', self.ba, 32, self.first_string)

    def _insert(self, first_block, entry_size, pos_offset, entry, entity):
        """Insere uma entidade e sua entrada de índice (espelha OcdEntityIndex::insert)."""
        _pad8(self.ba)
        block = first_block
        while _u32(self.ba, block) != 0:
            block = _u32(self.ba, block)
        index = 0
        while index < 256:
            epos = block + 4 + index * entry_size
            if _u32(self.ba, epos + pos_offset) == 0:
                break
            index += 1
        if index == 256:
            novo = len(self.ba)
            struct.pack_into('<I', self.ba, block, novo)
            self.ba += _bloco(entry_size)
            block, index = novo, 0
            epos = block + 4
        entity_pos = len(self.ba)
        self.ba += entity
        entrada = bytearray(entry)
        struct.pack_into('<I', entrada, pos_offset, entity_pos)
        self.ba[epos:epos + entry_size] = entrada

    def add_string(self, tipo, texto):
        dados = _enc(texto) + b'\x00'
        entry = struct.pack('<IIiI', 0, len(dados), tipo, 0)
        self._insert(self.first_string, _STR_ENTRY, 0, entry, dados)

    def add_symbol(self, dados):
        entry = struct.pack('<I', 0)
        self._insert(self.first_symbol, _SYM_ENTRY, 0, entry, dados)

    def add_object(self, dados, bounds, simbolo, tipo, cor):
        blx, bly, trx, try_ = bounds
        entry = struct.pack('<iiiiIIiBBBBHHHBB',
                            blx, bly, trx, try_,
                            0, len(dados), simbolo,
                            tipo, 0, 1, 0, cor, 0, 0, 0, 0)
        self._insert(self.first_object, _OBJ_ENTRY, _OBJ_POS_OFFSET, entry, dados)


def _simbolo_linha_bytes(proj):
    """Símbolo de linha (BaseSymbolV9 + LineSymbolCommonV8), linha sólida."""
    numero = proj.codigo_simbolo * FATOR_SIMBOLO
    base = bytearray(572)
    struct.pack_into('<II', base, 0, 648, numero)        # size, number
    base[8] = 2                                           # type = linha
    struct.pack_into('<i', base, 16, 7)                  # extent (~0,07 mm)
    struct.pack_into('<h', base, 26, 1)                  # num_colors
    struct.pack_into('<H', base, 28, 0)                  # colors[0] = cor 0
    desc = _enc('Curva de nível')[:31]
    base[56] = len(desc)
    base[57:57 + len(desc)] = desc                       # PascalString<31>
    # icon (484 bytes) fica zerado em [88..572]
    common = bytearray(76)
    largura = _round_half_up(proj.largura_um / 10.0)     # 1/1000 mm -> 1/100 mm
    struct.pack_into('<HHH', common, 0, 0, largura, 1)   # line_color, line_width, style
    return bytes(base) + bytes(common)


def _objeto_bytes(proj, linha):
    """Objeto de linha (ObjectV9) com as coordenadas da curva."""
    numero = proj.codigo_simbolo * FATOR_SIMBOLO
    coords = bytearray()
    xs, ys = [], []
    for (mx, my) in linha:
        x = _round_half_up(mx * 100.0) << 8              # 1/100 mm, flags=0
        y = _round_half_up(-my * 100.0) << 8             # y para cima
        coords += struct.pack('<ii', x, y)
        xs.append(x); ys.append(y)
    cabec = struct.pack('<iBBhIHBBIHHIIII',
                        numero, 2, 0, 0, len(linha), 0, 0, 0,
                        0, 0, 0, 0, 0, 0, 0)
    dados = cabec + bytes(coords)
    bounds = (min(xs), min(ys), max(xs), max(ys))
    return dados, bounds, numero


def escrever_ocd_v10(proj, caminho):
    """Gera o .ocd (OCAD 10) em `caminho` a partir de um ProjetoOcad."""
    w = _OcdWriter()

    # --- Cor da curva (string 9) ------------------------------------------
    c, m, y, k = proj.cor
    w.add_string(9, '%s\tn0\tc%d\tm%d\ty%d\tk%d\to1\tt100' % (
        proj.cor_nome, round(c * 100), round(m * 100),
        round(y * 100), round(k * 100)))

    # --- Georreferência (string 1039) -------------------------------------
    w.add_string(1039, '\tm%d\tg%.4f\tr1\tx%d\ty%d\ta%.8f\td%.6f\ti%d' % (
        proj.escala, 50.0, round(proj.ref_e), round(proj.ref_n),
        proj.grivacao, 500.0, proj.i_grade))

    # --- Símbolo de curva -------------------------------------------------
    w.add_symbol(_simbolo_linha_bytes(proj))

    # --- Curvas como objetos de linha -------------------------------------
    for linha in proj.linhas_mm:
        dados, bounds, numero = _objeto_bytes(proj, linha)
        w.add_object(dados, bounds, numero, 2, 0)

    # --- Satélite como mapa de fundo (string 8) ---------------------------
    if proj.satelite:
        nome = os.path.basename(proj.satelite['path'])
        mcx, mcy = proj.satelite['centro_mm']
        w.add_string(8, '%s\ts1\tx%.6f\ty%.6f\ta%.8f\tu%.10f\tv%.10f'
                        '\td0\tp\tt0\to0\tb%.6f' % (
                            nome, mcx, -mcy, proj.grivacao,
                            proj.satelite['u_mm'], proj.satelite['v_mm'],
                            proj.grivacao))

    with open(caminho, 'wb') as f:
        f.write(w.ba)
    return caminho
