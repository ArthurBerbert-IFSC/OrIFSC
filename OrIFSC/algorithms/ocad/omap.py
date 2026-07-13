"""Escritor de arquivo .omap (OpenOrienteering Mapper, XML aberto, versão 9).

Estrutura e nomes de elementos portados do XML que o próprio OOM escreve
(`core/georeferencing.cpp`, `core/objects/object.cpp`, `templates/template.cpp`).
Coordenadas de objeto em 1/1000 mm (nativo do OOM), y para baixo.
"""
import os
from xml.sax.saxutils import escape, quoteattr
from typing import Any, Iterable, Tuple


def _num(v: float) -> str:
    """Formata fração CMYK sem zeros à toa: 0, 0.56, 1, 0.18."""
    return '%g' % v


def _coords_xml(linha: Iterable[Tuple[float, float]]) -> str:
    """'x y;x y;...' em 1/1000 mm a partir de uma lista de (mm, mm)."""
    return ''.join('%d %d;' % (round(mx * 1000), round(my * 1000))
                   for (mx, my) in linha)


def escrever_omap(proj: Any, caminho: str) -> str:
    """Gera o .omap em `caminho` a partir de um ProjetoOcad."""
    c, m, y, k = proj.cor
    partes = []
    add = partes.append

    add('<?xml version="1.0" encoding="UTF-8"?>')
    add('<map xmlns="http://openorienteering.org/apps/mapper/xml/v2" '
        'version="9">')
    add('<notes></notes>')

    add('<georeferencing scale="%d" declination="%.4f" grivation="%.4f">'
        % (proj.escala, proj.declinacao, proj.grivacao))
    add('<projected_crs id="UTM">')
    add('<spec language="PROJ.4">%s</spec>' % escape(proj.proj4))
    add('<parameter>%s</parameter>' % escape(proj.crs_param))
    add('<ref_point x="%.6f" y="%.6f"/>' % (proj.ref_e, proj.ref_n))
    add('</projected_crs>')
    add('<geographic_crs id="Geographic coordinates">')
    add('<spec language="PROJ.4">+proj=latlong +datum=WGS84</spec>')
    add('<ref_point_deg lat="%.8f" lon="%.8f"/>' % (proj.lat, proj.lon))
    add('</geographic_crs>')
    add('</georeferencing>')

    add('<colors count="1">')
    add('<color priority="0" name=%s c="%s" m="%s" y="%s" k="%s" opacity="1">'
        '<cmyk method="custom"/></color>'
        % (quoteattr(proj.cor_nome), _num(c), _num(m), _num(y), _num(k)))
    add('</colors>')

    add('<symbols count="1" id="OrIFSC">')
    add('<symbol type="2" id="0" code="%d" name="Curva de nível">'
        '<line_symbol color="0" line_width="%d" minimum_length="0" '
        'join_style="1" cap_style="1" start_offset="0" end_offset="0" '
        'segment_length="0" end_length="0" show_at_least_one_symbol="false" '
        'minimum_mid_symbol_count="0" minimum_mid_symbol_count_when_closed="0" '
        'dash_length="0" break_length="0" dashes_in_group="1" '
        'in_group_break_length="0" mid_symbols_per_spot="0" '
        'mid_symbol_distance="0"/></symbol>'
        % (proj.codigo_simbolo, proj.largura_um))
    add('</symbols>')

    add('<parts count="1" current="0">')
    add('<part name="Curvas de nível"><objects count="%d">'
        % len(proj.linhas_mm))
    for linha in proj.linhas_mm:
        add('<object type="1" symbol="0"><coords count="%d">%s</coords>'
            '</object>' % (len(linha), _coords_xml(linha)))
    add('</objects></part>')
    add('</parts>')

    if proj.satelite:
        nome = escape(os.path.basename(proj.satelite['path']))
        add('<templates count="1" first_front_template="1">')
        add('<template type="TemplateImage" open="true" name="%s" path="%s" '
            'relpath="%s" georef="true"/>' % (nome, nome, nome))
        add('</templates>')

    add('</map>')

    with open(caminho, 'w', encoding='utf-8') as f:
        f.write('\n'.join(partes))
    return caminho
