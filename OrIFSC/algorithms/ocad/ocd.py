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
from typing import Any, Iterable, List, Optional, Tuple

VENDOR = 0x0CAD
VERSION = 10
FATOR_SIMBOLO = 1000
CODIGO_CURVA = 101
CODIGO_CURVA_MESTRA = 102

_STR_ENTRY = 16
_SYM_ENTRY = 4
_OBJ_ENTRY = 40
_OBJ_POS_OFFSET = 16

assert struct.calcsize('<HBBH BB' + 'I' * 10) == 48
assert struct.calcsize('<iBBhIHBBIHHIIII') == 40
assert struct.calcsize('<iiiiIIiBBBBHHHBB') == _OBJ_ENTRY


def _round_half_up(v: float) -> int:
    """Arredonda com regra half-up para coordenadas de exportação.

    Args:
        v: Valor decimal de entrada.

    Returns:
        int: Valor inteiro arredondado.
    """
    return int(math.floor(v + 0.5))


def _pad8(ba: bytearray) -> None:
    """Alinha buffer para múltiplos de 8 bytes exigidos pelo formato OCD.

    Args:
        ba: Buffer binário em montagem.
    """
    ba.extend(b'\x00' * ((-len(ba)) % 8))


def _bloco(entry_size):
    """Bloco de índice zerado: next_block (4) + 256 entradas."""
    return bytearray(4 + 256 * entry_size)


def _u32(ba: bytearray, off: int) -> int:
    """Lê inteiro unsigned 32-bit little-endian no offset informado.

    Args:
        ba: Buffer binário.
        off: Posição do campo.

    Returns:
        int: Valor lido.
    """
    return struct.unpack_from('<I', ba, off)[0]


def _enc(texto: str) -> bytes:
    """Codifica string de parâmetro no 8-bit do OCD (latin-1)."""
    return texto.encode('latin-1', 'replace')


class _OcdWriter:
    """Montador incremental de blocos binários do formato OCD v10."""

    def __init__(self) -> None:
        """Inicializa cabeçalho e blocos de índice vazios.

        O formato v10 mantém layout estrutural do v9, então os offsets de
        índices seguem o mesmo contrato binário compatível com OCAD 10.
        """
        self.ba = bytearray()
        self.ba += struct.pack('<HBBHBB', VENDOR, 0, 0,
                               VERSION, 0, 0)
        self.ba += struct.pack('<10I', *([0] * 10))
        _pad8(self.ba)
        self.first_string = len(self.ba)
        self.ba += _bloco(_STR_ENTRY)
        _pad8(self.ba)
        self.first_symbol = len(self.ba)
        self.ba += _bloco(_SYM_ENTRY)
        _pad8(self.ba)
        self.first_object = len(self.ba)
        self.ba += _bloco(_OBJ_ENTRY)
        struct.pack_into('<I', self.ba, 8, self.first_symbol)
        struct.pack_into('<I', self.ba, 12, self.first_object)
        struct.pack_into('<I', self.ba, 32, self.first_string)

    @classmethod
    def de_doador(cls, dados: bytes) -> '_OcdWriter':
        """Inicializa o montador a partir de um .ocd doador de simbologia.

        Args:
            dados: Bytes completos do arquivo doador (OCD v9 ou v10).

        Returns:
            _OcdWriter: Montador pronto para receber strings e objetos.

        O doador contém apenas a paleta (símbolos + cores) exportada do
        symbol set do OOM; v9 e v10 são estruturalmente idênticos, então a
        versão do cabeçalho é normalizada para 10 (abre direto no OCAD 10
        sem pedido de conversão). Versões != 9/10 têm layout diferente e
        são rejeitadas.
        """
        w = cls.__new__(cls)
        w.ba = bytearray(dados)
        if len(w.ba) < 48 or struct.unpack_from('<H', w.ba, 0)[0] != VENDOR:
            raise ValueError('Doador não é um arquivo OCD válido.')
        versao = struct.unpack_from('<H', w.ba, 4)[0]
        if versao not in (9, 10):
            raise ValueError('Doador OCD na versão %d; exporte o symbol set '
                             'como OCD versão 9 ou 10.' % versao)
        struct.pack_into('<H', w.ba, 4, VERSION)
        w.first_symbol = _u32(w.ba, 8)
        w.first_object = _u32(w.ba, 12)
        w.first_string = _u32(w.ba, 32)
        for off in (w.first_symbol, w.first_object, w.first_string):
            if not 0 < off < len(w.ba):
                raise ValueError('Doador OCD com índices corrompidos.')
        return w

    def _blocos(self, first_block: int) -> Iterable[int]:
        """Percorre a cadeia de blocos de um índice."""
        bloco = first_block
        while bloco:
            yield bloco
            bloco = _u32(self.ba, bloco)

    def zerar_objetos(self) -> None:
        """Zera todas as entradas do índice de objetos (remove os objetos
        de exemplo que o symbol set traz; os bytes das entidades ficam
        órfãos no arquivo, o que o formato permite)."""
        for bloco in self._blocos(self.first_object):
            base = bloco + 4
            self.ba[base:base + 256 * _OBJ_ENTRY] = (
                b'\x00' * (256 * _OBJ_ENTRY))

    def zerar_strings(self, tipos: Tuple[int, ...]) -> None:
        """Zera as entradas de string dos tipos dados (ex.: 1039 do doador,
        que será substituída pela georreferência do projeto)."""
        for bloco in self._blocos(self.first_string):
            for i in range(256):
                epos = bloco + 4 + i * _STR_ENTRY
                if _u32(self.ba, epos) == 0:
                    continue
                tipo = struct.unpack_from('<i', self.ba, epos + 8)[0]
                if tipo in tipos:
                    self.ba[epos:epos + _STR_ENTRY] = b'\x00' * _STR_ENTRY

    def numeros_de_simbolos(self) -> List[int]:
        """Números (código x 1000 + sufixo) dos símbolos presentes."""
        numeros = []
        for bloco in self._blocos(self.first_symbol):
            for i in range(256):
                pos = _u32(self.ba, bloco + 4 + i * _SYM_ENTRY)
                if pos:
                    numeros.append(
                        struct.unpack_from('<i', self.ba, pos + 4)[0])
        return numeros

    def _insert(
            self,
            first_block: int,
            entry_size: int,
            pos_offset: int,
            entry: bytes,
            entity: bytes) -> None:
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

    def add_string(self, tipo: int, texto: str) -> None:
        """Adiciona string parametrizada no índice de strings do OCD.

        Args:
            tipo: Código de tipo da string (ex.: 8, 9, 1039).
            texto: Conteúdo textual.
        """
        dados = _enc(texto) + b'\x00'
        entry = struct.pack('<IIiI', 0, len(dados), tipo, 0)
        self._insert(self.first_string, _STR_ENTRY, 0, entry, dados)

    def add_symbol(self, dados: bytes) -> None:
        """Adiciona definição de símbolo no índice de símbolos.

        Args:
            dados: Bloco binário de símbolo serializado.
        """
        entry = struct.pack('<I', 0)
        self._insert(self.first_symbol, _SYM_ENTRY, 0, entry, dados)

    def add_object(
            self,
            dados: bytes,
            bounds: Tuple[int, int, int, int],
            simbolo: int,
            tipo: int,
            cor: int) -> None:
        """Adiciona objeto geográfico indexado no arquivo OCD.

        Args:
            dados: Bloco binário do objeto.
            bounds: Envelope inteiro do objeto (blx, bly, trx, try).
            simbolo: Número do símbolo aplicado.
            tipo: Tipo do objeto no formato OCD.
            cor: Cor principal associada.
        """
        blx, bly, trx, try_ = bounds
        entry = struct.pack('<iiiiIIiBBBBHHHBB',
                            blx, bly, trx, try_,
                            0, len(dados), simbolo,
                            tipo, 0, 1, 0, cor, 0, 0, 0, 0)
        self._insert(
            self.first_object,
            _OBJ_ENTRY,
            _OBJ_POS_OFFSET,
            entry,
            dados)


def _simbolo_linha_bytes(proj: Any) -> bytes:
    """Símbolo de linha (BaseSymbolV9 + LineSymbolCommonV8), linha sólida."""
    numero = proj.codigo_simbolo * FATOR_SIMBOLO
    base = bytearray(572)
    struct.pack_into('<II', base, 0, 648, numero)
    base[8] = 2
    struct.pack_into('<i', base, 16, 7)
    struct.pack_into('<h', base, 26, 1)
    struct.pack_into('<H', base, 28, 0)
    desc = _enc('Curva de nível')[:31]
    base[56] = len(desc)
    base[57:57 + len(desc)] = desc
    common = bytearray(76)
    largura = _round_half_up(
        proj.largura_um /
        10.0)
    struct.pack_into('<HHH', common, 0, 0, largura, 1)
    return bytes(base) + bytes(common)


def _objeto_bytes(
        linha: Iterable[Tuple[float, float]],
        numero: int) -> Tuple[bytes, Tuple[int, int, int, int]]:
    """Objeto de linha (ObjectV9) com as coordenadas da curva."""
    coords = bytearray()
    xs, ys = [], []
    for (mx, my) in linha:
        x = _round_half_up(mx * 100.0) << 8
        y = _round_half_up(-my * 100.0) << 8
        coords += struct.pack('<ii', x, y)
        xs.append(x)
        ys.append(y)
    cabec = struct.pack('<iBBhIHBBIHHIIII',
                        numero, 2, 0, 0, len(linha), 0, 0, 0,
                        0, 0, 0, 0, 0, 0, 0)
    dados = cabec + bytes(coords)
    bounds = (min(xs), min(ys), max(xs), max(ys))
    return dados, bounds


def _numeros_por_codigo(w: '_OcdWriter') -> Tuple[int, int]:
    """Números dos símbolos de curva (101) e curva mestra (102) do doador.

    Sem o 101 o doador não serve (é a base das curvas exportadas); sem o
    102 as mestras degradam para o 101.
    """
    numeros = set(w.numeros_de_simbolos())
    numero_curva = CODIGO_CURVA * FATOR_SIMBOLO
    if numero_curva not in numeros:
        raise ValueError('Doador de simbologia sem o símbolo 101 '
                         '(curva de nível).')
    numero_mestra = CODIGO_CURVA_MESTRA * FATOR_SIMBOLO
    if numero_mestra not in numeros:
        numero_mestra = numero_curva
    return numero_curva, numero_mestra


def escrever_ocd_v10(proj: Any, caminho: str,
                     doador: Optional[str] = None) -> str:
    """Gera o .ocd (OCAD 10) em `caminho` a partir de um ProjetoOcad.

    Args:
        proj: Projeto com georreferência, curvas e satélite.
        caminho: Arquivo .ocd de saída.
        doador: Caminho opcional de um .ocd só-simbologia (ver
            ``recursos/simbologias/``). Quando presente, o arquivo sai com
            a paleta completa da norma e as curvas apontam para os
            símbolos reais 101/102; sem doador, mantém o comportamento
            original (símbolo único de curva criado do zero).
    """
    if doador is None:
        w = _OcdWriter()
        c, m, y, k = proj.cor
        w.add_string(9, '%s\tn0\tc%d\tm%d\ty%d\tk%d\to1\tt100' % (
            proj.cor_nome, round(c * 100), round(m * 100),
            round(y * 100), round(k * 100)))
        w.add_symbol(_simbolo_linha_bytes(proj))
        numero_curva = numero_mestra = proj.codigo_simbolo * FATOR_SIMBOLO
    else:
        with open(doador, 'rb') as f:
            w = _OcdWriter.de_doador(f.read())
        w.zerar_objetos()
        w.zerar_strings((8, 1039))
        numero_curva, numero_mestra = _numeros_por_codigo(w)

    w.add_string(1039, '\tm%d\tg%.4f\tr1\tx%d\ty%d\ta%.8f\td%.6f\ti%d' % (
        proj.escala, 50.0, round(proj.ref_e), round(proj.ref_n),
        proj.grivacao, 500.0, proj.i_grade))

    codigos = getattr(proj, 'codigos_linhas', None)
    if not codigos:
        codigos = ['%d' % CODIGO_CURVA] * len(proj.linhas_mm)
    for linha, codigo in zip(proj.linhas_mm, codigos):
        numero = (numero_mestra if codigo == '%d' % CODIGO_CURVA_MESTRA
                  else numero_curva)
        dados, bounds = _objeto_bytes(linha, numero)
        w.add_object(dados, bounds, numero, 2, 0)

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
