"""Simbologia oficial embutida: injeção do projeto nos symbol sets do OOM.

Em vez de gerar um .omap do zero com um único símbolo (caminho de
``omap.py``, mantido para a opção "Nenhuma"), este módulo abre um symbol
set oficial do OpenOrienteering Mapper (GPLv3, embutido em
``recursos/simbologias/`` — ver PROVENIENCIA.txt) e injeta nele a
georreferência do projeto, as curvas de nível como objetos dos símbolos
reais (101 Curva / 102 Curva mestra, localizados pelo atributo ``code``)
e o template do satélite. A paleta completa de símbolos e cores da norma
chega intacta ao usuário.

Módulo puro (sem QGIS): testável com pytest isoladamente. O XML do OOM
usa um elemento <barrier> para conteúdo que exige versão mínima do
aplicativo; símbolos/partes/templates dos symbol sets vivem dentro dele.
"""
import math
import os
import xml.etree.ElementTree as ET
from typing import Any, Iterable, List, Optional, Sequence

NS_URI = 'http://openorienteering.org/apps/mapper/xml/v2'
NS = '{%s}' % NS_URI

NORMA_ISOM = 'ISOM'
NORMA_ISSPROM = 'ISSPROM'

CODIGO_CURVA = '101'
CODIGO_CURVA_MESTRA = '102'
FATOR_MESTRA = 5

_DIR_SIMBOLOGIAS = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    '..', '..', 'recursos', 'simbologias'))


def arquivo_simbologia(norma: str, escala: int,
                       extensao: str = '.omap') -> str:
    """Caminho do arquivo de simbologia embutido para a norma e a escala.

    Args:
        norma: ``NORMA_ISOM`` ou ``NORMA_ISSPROM``.
        escala: Denominador da escala do projeto.
        extensao: ``.omap`` (symbol set) ou ``.ocd`` (doador OCAD 10).

    Returns:
        str: Caminho absoluto do arquivo.

    A ISOM 2017-2 tem escala-base 1:15.000; para mapas maiores que isso
    (1:10.000 e derivadas) a norma manda ampliar os símbolos em 150%, o
    que o symbol set de 1:10.000 do OOM já traz. A ISSprOM é publicada
    pelo OOM apenas em 1:4.000; escalas derivadas (ex.: 1:3.000) mantêm
    as dimensões de papel e só mudam a escala na georreferência.
    """
    if norma == NORMA_ISOM:
        nome = ('ISOM_2017-2_15000' if escala >= 15000
                else 'ISOM_2017-2_10000')
    elif norma == NORMA_ISSPROM:
        nome = 'ISSprOM_2019_4000'
    else:
        raise ValueError('Norma de simbologia desconhecida: %r' % (norma,))
    return os.path.join(_DIR_SIMBOLOGIAS, nome + extensao)


def classificar_curvas(
        elevacoes: Sequence[Optional[float]],
        fator_mestra: int = FATOR_MESTRA) -> List[str]:
    """Código de símbolo ('101'/'102') para cada curva pela elevação.

    Args:
        elevacoes: Elevação (m) de cada curva; ``None`` quando ausente.
        fator_mestra: Curva mestra a cada N equidistâncias (norma: 5).

    Returns:
        List[str]: Código por curva, alinhado com a entrada.

    A equidistância é deduzida dos próprios dados (menor diferença entre
    elevações distintas), então funciona para qualquer fonte de MDT sem
    depender de configuração. Sem elevações suficientes para deduzir
    (menos de duas distintas), tudo sai como curva normal ('101').
    """
    codigos = [CODIGO_CURVA] * len(elevacoes)
    distintas = sorted({round(float(e), 6) for e in elevacoes
                        if e is not None})
    if len(distintas) < 2:
        return codigos
    equidistancia = min(b - a for a, b in zip(distintas, distintas[1:]))
    if equidistancia <= 0:
        return codigos
    passo = fator_mestra * equidistancia
    tol = equidistancia * 0.01
    for i, elev in enumerate(elevacoes):
        if elev is None:
            continue
        resto = math.fmod(abs(float(elev)), passo)
        if min(resto, passo - resto) <= tol:
            codigos[i] = CODIGO_CURVA_MESTRA
    return codigos


def _codigos_das_linhas(proj: Any) -> List[str]:
    """Códigos por linha do projeto ('101' quando não classificadas)."""
    codigos = getattr(proj, 'codigos_linhas', None)
    if not codigos:
        return [CODIGO_CURVA] * len(proj.linhas_mm)
    if len(codigos) != len(proj.linhas_mm):
        raise ValueError('codigos_linhas não alinhado com linhas_mm '
                         '(%d != %d).' % (len(codigos), len(proj.linhas_mm)))
    return list(codigos)


def _mapa_codigo_id(container: ET.Element) -> dict:
    """Dicionário code -> id dos símbolos do symbol set."""
    simbolos = container.find(f'{NS}symbols')
    if simbolos is None:
        raise ValueError('Symbol set sem elemento <symbols>.')
    return {s.get('code'): s.get('id') for s in simbolos
            if s.get('code') and s.get('id') is not None}


def _georeferencing(proj: Any) -> ET.Element:
    """Elemento <georeferencing> do projeto (mesmo conteúdo de omap.py)."""
    geo = ET.Element(f'{NS}georeferencing', {
        'scale': '%d' % proj.escala,
        'declination': '%.4f' % proj.declinacao,
        'grivation': '%.4f' % proj.grivacao,
    })
    proj_crs = ET.SubElement(geo, f'{NS}projected_crs', {'id': 'UTM'})
    spec = ET.SubElement(proj_crs, f'{NS}spec', {'language': 'PROJ.4'})
    spec.text = proj.proj4
    param = ET.SubElement(proj_crs, f'{NS}parameter')
    param.text = proj.crs_param
    ET.SubElement(proj_crs, f'{NS}ref_point', {
        'x': '%.6f' % proj.ref_e, 'y': '%.6f' % proj.ref_n})
    geo_crs = ET.SubElement(geo, f'{NS}geographic_crs',
                            {'id': 'Geographic coordinates'})
    spec = ET.SubElement(geo_crs, f'{NS}spec', {'language': 'PROJ.4'})
    spec.text = '+proj=latlong +datum=WGS84'
    ET.SubElement(geo_crs, f'{NS}ref_point_deg', {
        'lat': '%.8f' % proj.lat, 'lon': '%.8f' % proj.lon})
    return geo


def _coords_texto(linha: Iterable) -> str:
    """'x y;x y;...' em 1/1000 mm (mesma conversão do escritor omap.py)."""
    return ''.join('%d %d;' % (round(mx * 1000), round(my * 1000))
                   for (mx, my) in linha)


def escrever_omap_com_simbologia(proj: Any, caminho: str,
                                 arquivo_base: str) -> str:
    """Gera o .omap com a simbologia completa do symbol set `arquivo_base`.

    Args:
        proj: ``ProjetoOcad`` (ou equivalente) com georreferência e curvas.
        caminho: Arquivo .omap de saída.
        arquivo_base: Symbol set .omap embutido a usar como base.

    Returns:
        str: O próprio ``caminho``.

    Os objetos de exemplo que o symbol set traz (amostra dos símbolos)
    são removidos; símbolos, cores e vista permanecem como no original.
    """
    ET.register_namespace('', NS_URI)
    # arquivo_base é um symbol set embutido no próprio plugin (confiável,
    # distribuído no pacote) — não é entrada de rede/usuário, sem superfície
    # de XXE.
    arvore = ET.parse(arquivo_base)  # nosec B314 - arquivo confiável do pacote
    raiz = arvore.getroot()

    antiga = raiz.find(f'{NS}georeferencing')
    if antiga is None:
        raise ValueError('Symbol set sem <georeferencing>: %s' % arquivo_base)
    indice = list(raiz).index(antiga)
    raiz.remove(antiga)
    raiz.insert(indice, _georeferencing(proj))

    container = raiz.find(f'{NS}barrier')
    if container is None:
        container = raiz

    ids = _mapa_codigo_id(container)
    id_curva = ids.get(CODIGO_CURVA)
    if id_curva is None:
        raise ValueError('Symbol set sem símbolo de curva (code="101"): %s'
                         % arquivo_base)
    id_mestra = ids.get(CODIGO_CURVA_MESTRA, id_curva)

    partes = container.find(f'{NS}parts')
    if partes is None or len(partes) == 0:
        raise ValueError('Symbol set sem <parts>: %s' % arquivo_base)
    parte = partes[0]
    parte.set('name', 'Curvas de nível')
    objetos = parte.find(f'{NS}objects')
    for filho in list(objetos):
        objetos.remove(filho)
    codigos = _codigos_das_linhas(proj)
    objetos.set('count', '%d' % len(proj.linhas_mm))
    for linha, codigo in zip(proj.linhas_mm, codigos):
        simbolo = id_mestra if codigo == CODIGO_CURVA_MESTRA else id_curva
        obj = ET.SubElement(objetos, f'{NS}object',
                            {'type': '1', 'symbol': simbolo})
        coords = ET.SubElement(obj, f'{NS}coords',
                               {'count': '%d' % len(linha)})
        coords.text = _coords_texto(linha)

    if proj.satelite:
        templates = container.find(f'{NS}templates')
        if templates is None:
            templates = ET.SubElement(container, f'{NS}templates')
        templates.set('count', '1')
        templates.set('first_front_template', '1')
        nome = os.path.basename(proj.satelite['path'])
        # Antes do <defaults> que o symbol set traz no fim de <templates>.
        templates.insert(0, ET.Element(f'{NS}template', {
            'type': 'TemplateImage', 'open': 'true', 'name': nome,
            'path': nome, 'relpath': nome, 'georef': 'true'}))

    arvore.write(caminho, encoding='UTF-8', xml_declaration=True)
    return caminho
