"""Atualiza o symbol set ISSprOM do OOM para a ISSprOM 2019-2 (Rev. 6, jan/2024).

O OpenOrienteering Mapper publica o conjunto sprint com a numeração da
ISSprOM 2019 original. Este script aplica sobre o .omap embutido as
mudanças da revisão 2019-2 usadas em competição desde 2023/2024:

1. Cor nova "Dark green" (CMYK 100-0-80-30), conforme o documento oficial
   "IOF Map Specifications — Printing and Colour Definitions" (jan/2022):
   uma entrada para linhas (antes do Blue 100%) e uma para áreas (antes do
   Green 100% de área). Todas as referências de cor são renumeradas.
2. Renumeração da vegetação intransponível: 410 -> 411 "Uncrossable
   vegetation" (área, dark green) e 410.1 -> 411.1 (linha/hedge).
3. Novo 410 "Vegetation: fight" (área, green 100%), da 2019-2.
4. Novo 533 "Area with obstacles" (Rev. 6, jan/2024): padrão de pontos
   Ø 0,55 mm, espaçamento 0,75 mm centro-a-centro, a 45°, preto 50%.
5. Renumeração dos `id` de símbolo pela posição final na lista (0..N-1) e
   atualização de toda referência cruzada (`<part symbol="X">` dentro de
   símbolos combinados e `<object symbol="X">` dos objetos de exemplo).
   No arquivo original o `id` de cada símbolo é sempre igual à sua posição
   na lista — inserir os dois símbolos novos no meio sem renumerar os
   demais quebra esse invariante e corrompe as referências cruzadas
   (o arquivo deixa de abrir no OOM).

Fonte das definições: ISSprOM 2019-2 Revision 6 (IOF, jan/2024) e IOF Map
Specifications — Printing and Colour Definitions. Rodar da raiz do repo:

    python tools/atualizar_issprom_2019_2.py
"""
import os
import xml.etree.ElementTree as ET

NS_URI = 'http://openorienteering.org/apps/mapper/xml/v2'
NS = '{%s}' % NS_URI

ARQUIVO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__))), 'OrIFSC', 'recursos', 'simbologias', 'ISSprOM_2019_4000.omap')

DARK_GREEN = {'c': '1', 'm': '0', 'y': '0.8', 'k': '0.3'}  # 100-0-80-30

DESC_410 = ('An area of dense vegetation (trees or undergrowth) which is '
            'barely passable. Running reduced to less than about 20% of '
            'normal speed.\n'
            'Minimum area: 0.3 mm² (footprint 5 m²).\n'
            'Minimum width: 0.25 mm.')
DESC_411 = ('Uncrossable vegetation is an area of vegetation (for example '
            'a hedge) that shall not be crossed or passed through since '
            'there may be a danger that private property or the vegetation '
            'itself is damaged.\n'
            'Minimum area: 0.3 mm² (footprint 5 m²).\n'
            'Minimum width: 0.4 mm.')
DESC_533 = ('An area with several man-made features that are too small or '
            'close to be mapped individually and that constitute obstacles '
            'to the runners. The area cannot be crossed at full speed.\n'
            'Minimum area: 65 m².')


def _cor(nome, prioridade):
    cor = ET.Element(f'{NS}color', {
        'priority': str(prioridade), 'name': nome,
        'c': DARK_GREEN['c'], 'm': DARK_GREEN['m'],
        'y': DARK_GREEN['y'], 'k': DARK_GREEN['k'], 'opacity': '1'})
    ET.SubElement(cor, f'{NS}cmyk', {'method': 'custom'})
    return cor


def main():
    ET.register_namespace('', NS_URI)
    arvore = ET.parse(ARQUIVO)
    raiz = arvore.getroot()
    barrier = raiz.find(f'{NS}barrier')
    simbolos = barrier.find(f'{NS}symbols')
    cores = raiz.find(f'{NS}colors')

    nomes = [c.get('name') for c in cores]
    if 'Dark green for area features' in nomes:
        raise SystemExit('Arquivo já está na 2019-2; nada a fazer.')

    # 1. Insere as duas cores dark green nas posições da ordem oficial da
    #    IOF e calcula o mapeamento prioridade antiga -> nova.
    lista = list(cores)
    pos_linha = nomes.index('Blue 100%')
    pos_area = nomes.index('Green 100% for area features')
    lista.insert(pos_area, _cor('Dark green for area features', 0))
    lista.insert(pos_linha, _cor('Dark green for line symbols', 0))

    mapa = {}
    for nova, cor in enumerate(lista):
        antiga = cor.get('priority')
        cor.set('priority', str(nova))
        if cor.get('name') not in ('Dark green for area features',
                                   'Dark green for line symbols'):
            mapa[antiga] = str(nova)
    for filho in list(cores):
        cores.remove(filho)
    for cor in lista:
        cores.append(cor)
    cores.set('count', str(len(lista)))

    prioridade = {c.get('name'): c.get('priority') for c in lista}
    dg_area = prioridade['Dark green for area features']
    dg_linha = prioridade['Dark green for line symbols']

    # 2. Renumera as referências de cor em todos os símbolos.
    for el in simbolos.iter():
        for attr in ('color', 'inner_color', 'outer_color'):
            valor = el.get(attr)
            if valor is not None and valor in mapa:
                el.set(attr, mapa[valor])

    # 3. 410 -> 411 (área, dark green) e 410.1 -> 411.1 (linha, dark green).
    filhos = list(simbolos)
    velho_410 = velho_410_1 = None
    for s in filhos:
        if s.get('code') == '410':
            velho_410 = s
        elif s.get('code') == '410.1':
            velho_410_1 = s
    if velho_410 is None or velho_410_1 is None:
        raise SystemExit('Símbolos 410/410.1 não encontrados.')

    velho_410.set('code', '411')
    velho_410.set('name', 'Uncrossable vegetation')
    velho_410.find(f'{NS}description').text = DESC_411
    velho_410.find(f'{NS}area_symbol').set('inner_color', dg_area)

    velho_410_1.set('code', '411.1')
    velho_410_1.set('name', 'Uncrossable vegetation, minimum width (hedge)')
    velho_410_1.find(f'{NS}description').text = DESC_411
    velho_410_1.find(f'{NS}line_symbol').set('color', dg_linha)

    # 4. Novos símbolos 410 (Vegetation: fight) e 533 (Area with obstacles).
    prox_id = max(int(s.get('id')) for s in filhos) + 1

    fight = ET.Element(f'{NS}symbol', {
        'type': '4', 'id': str(prox_id), 'code': '410',
        'name': 'Vegetation: fight'})
    ET.SubElement(fight, f'{NS}description').text = DESC_410
    ET.SubElement(fight, f'{NS}area_symbol', {
        'inner_color': prioridade['Green 100% for area features'],
        'min_area': '300', 'patterns': '0'})
    simbolos.insert(list(simbolos).index(velho_410), fight)

    obst = ET.Element(f'{NS}symbol', {
        'type': '4', 'id': str(prox_id + 1), 'code': '533',
        'name': 'Area with obstacles'})
    ET.SubElement(obst, f'{NS}description').text = DESC_533
    area = ET.SubElement(obst, f'{NS}area_symbol', {
        'inner_color': '-1', 'min_area': '4000', 'patterns': '1'})
    padrao = ET.SubElement(area, f'{NS}pattern', {
        'type': '2', 'angle': '0.785398', 'line_spacing': '750',
        'line_offset': '0', 'offset_along_line': '0',
        'point_distance': '750'})
    ponto = ET.SubElement(padrao, f'{NS}symbol', {
        'type': '1', 'code': '', 'name': 'Fill pattern 1'})
    ET.SubElement(ponto, f'{NS}point_symbol', {
        'rotatable': 'true', 'inner_radius': '275',
        'inner_color': prioridade['Black 50%'], 'outer_width': '0',
        'outer_color': '-1', 'elements': '0'})
    ultimo_53x = max(i for i, s in enumerate(simbolos)
                     if (s.get('code') or '').startswith('532'))
    simbolos.insert(ultimo_53x + 1, obst)

    simbolos.set('count', str(len(list(simbolos))))

    # 5. Renumera os ids pela posição final e corrige toda referência
    # cruzada. Sem isso, os `<part symbol="X">` (símbolos combinados) e
    # `<object symbol="X">` (objetos de exemplo) que apontam para símbolos
    # deslocados pelas duas inserções acima passam a referenciar o símbolo
    # ERRADO (ou nenhum) — o OOM recusa abrir o arquivo.
    mapa_id = {s.get('id'): str(i) for i, s in enumerate(simbolos)}
    for i, s in enumerate(simbolos):
        s.set('id', str(i))
    for el in raiz.iter():
        valor = el.get('symbol')
        if valor is not None and valor in mapa_id:
            el.set('symbol', mapa_id[valor])

    arvore.write(ARQUIVO, encoding='UTF-8', xml_declaration=True)
    print('Atualizado: %s (%s cores, %s símbolos)' % (
        ARQUIVO, cores.get('count'), simbolos.get('count')))


if __name__ == '__main__':
    main()
