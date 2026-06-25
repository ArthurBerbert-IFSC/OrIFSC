"""Escritor de arquivo .omap (OpenOrienteering Mapper, XML aberto, versão 9).

Estrutura e nomes de elementos portados do XML que o próprio OOM escreve
(`core/georeferencing.cpp`, `core/objects/object.cpp`, `templates/template.cpp`).
Coordenadas de objeto em 1/1000 mm (nativo do OOM), y para baixo.

Dois caminhos:

- **com modelo** (`template`): abre um .omap-mestre (que já traz toda a paleta de
  cores e símbolos da norma) e injeta nele só o que é do projeto — georreferência,
  as curvas como objetos e o satélite de fundo. É o caminho que leva a simbologia
  completa para o arquivo exportado.
- **sem modelo**: escreve do zero com um único símbolo de curva (comportamento
  histórico, usado como fallback quando não há mestre para a norma/escala).
"""
import os
from xml.sax.saxutils import escape, quoteattr
import xml.etree.ElementTree as ET

NS = 'http://openorienteering.org/apps/mapper/xml/v2'


def _q(tag):
    """Tag com o namespace padrão do OOM (como o ElementTree representa)."""
    return '{%s}%s' % (NS, tag)


def _num(v):
    """Formata fração CMYK sem zeros à toa: 0, 0.56, 1, 0.18."""
    return '%g' % v


def _coords_xml(linha):
    """'x y;x y;...' em 1/1000 mm a partir de uma lista de (mm, mm)."""
    return ''.join('%d %d;' % (round(mx * 1000), round(my * 1000))
                   for (mx, my) in linha)


def escrever_omap(proj, caminho, template=None):
    """Gera o .omap em `caminho` a partir de um ProjetoOcad.

    Se `template` apontar para um .omap-mestre, a simbologia completa dele é
    preservada e o projeto é injetado por cima; caso contrário, escreve do zero.
    """
    if template and os.path.exists(template):
        return _escrever_com_modelo(proj, caminho, template)
    return _escrever_do_zero(proj, caminho)


# --------------------------------------------------------------- com modelo
def _georef_element(proj):
    """Monta o <georeferencing> do projeto como elemento ET (com namespace)."""
    frag = (
        '<georeferencing xmlns="%s" scale="%d" declination="%.4f" grivation="%.4f">'
        '<projected_crs id="UTM">'
        '<spec language="PROJ.4">%s</spec>'
        '<parameter>%s</parameter>'
        '<ref_point x="%.6f" y="%.6f"/>'
        '</projected_crs>'
        '<geographic_crs id="Geographic coordinates">'
        '<spec language="PROJ.4">+proj=latlong +datum=WGS84</spec>'
        '<ref_point_deg lat="%.8f" lon="%.8f"/>'
        '</geographic_crs>'
        '</georeferencing>'
        % (NS, proj.escala, proj.declinacao, proj.grivacao,
           escape(proj.proj4), escape(proj.crs_param),
           proj.ref_e, proj.ref_n, proj.lat, proj.lon))
    return ET.fromstring(frag)


def _id_simbolo_curva(symbols_el, codigo):
    """id (str) do <symbol> cujo `code` casa com `codigo`.

    Casa primeiro pelo código exato ('101'); se não houver, aceita a primeira
    forma numérica equivalente (ex.: '101.0', '101.000')."""
    alvo = str(codigo)
    aproximado = None
    for sym in symbols_el.findall(_q('symbol')):
        code = sym.get('code')
        if code is None:
            continue
        if code == alvo:
            return sym.get('id')
        try:
            if int(float(code)) == codigo and aproximado is None:
                aproximado = sym.get('id')
        except ValueError:
            pass
    return aproximado


def _escrever_com_modelo(proj, caminho, template):
    ET.register_namespace('', NS)
    arvore = ET.parse(template)
    raiz = arvore.getroot()

    # --- Georreferência: substitui o bloco do modelo pelo do projeto -------
    novo_georef = _georef_element(proj)
    antigo = raiz.find(_q('georeferencing'))
    if antigo is not None:
        raiz[list(raiz).index(antigo)] = novo_georef
    else:
        raiz.insert(0, novo_georef)

    # --- Símbolo de curva (vinculado pelo id interno do modelo) ------------
    symbols_el = raiz.find(_q('symbols'))
    sym_id = (_id_simbolo_curva(symbols_el, proj.codigo_simbolo)
              if symbols_el is not None else None)
    if sym_id is None:
        raise ValueError(
            'O modelo .omap não tem símbolo com código %d (curva de nível).'
            % proj.codigo_simbolo)

    # --- Curvas injetadas na parte de mapa do modelo -----------------------
    parts_el = raiz.find(_q('parts'))
    if parts_el is None:
        parts_el = ET.SubElement(raiz, _q('parts'))
    parte = parts_el.find(_q('part'))
    if parte is None:
        parte = ET.SubElement(parts_el, _q('part'))
        parte.set('name', 'Curvas de nível')
    objs = parte.find(_q('objects'))
    if objs is None:
        objs = ET.SubElement(parte, _q('objects'))
        base_count = 0
    else:
        base_count = int(objs.get('count') or 0)
    for linha in proj.linhas_mm:
        obj = ET.SubElement(objs, _q('object'))
        obj.set('type', '1')
        obj.set('symbol', sym_id)
        coords = ET.SubElement(obj, _q('coords'))
        coords.set('count', str(len(linha)))
        coords.text = _coords_xml(linha)
    objs.set('count', str(base_count + len(proj.linhas_mm)))
    parts_el.set('count', str(len(parts_el.findall(_q('part')))))
    parts_el.set('current', '0')

    # --- Satélite como mapa de fundo georreferenciado ----------------------
    if proj.satelite:
        nome = os.path.basename(proj.satelite['path'])
        templates_el = raiz.find(_q('templates'))
        if templates_el is None:
            templates_el = ET.Element(_q('templates'))
            raiz.insert(list(raiz).index(parts_el) + 1, templates_el)
        tmpl = ET.SubElement(templates_el, _q('template'))
        tmpl.set('type', 'TemplateImage')
        tmpl.set('open', 'true')
        tmpl.set('name', nome)
        tmpl.set('path', nome)
        tmpl.set('relpath', nome)
        tmpl.set('georef', 'true')
        n_tmpl = len(templates_el.findall(_q('template')))
        templates_el.set('count', str(n_tmpl))
        templates_el.set('first_front_template', str(n_tmpl))

    arvore.write(caminho, encoding='utf-8', xml_declaration=True)
    return caminho


# ----------------------------------------------------------------- do zero
def _escrever_do_zero(proj, caminho):
    """Gera o .omap só com o símbolo de curva embutido (sem paleta completa)."""
    c, m, y, k = proj.cor
    partes = []
    add = partes.append

    add('<?xml version="1.0" encoding="UTF-8"?>')
    add('<map xmlns="http://openorienteering.org/apps/mapper/xml/v2" '
        'version="9">')
    add('<notes></notes>')

    # --- Georreferência ---------------------------------------------------
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

    # --- Cores ------------------------------------------------------------
    add('<colors count="1">')
    add('<color priority="0" name=%s c="%s" m="%s" y="%s" k="%s" opacity="1">'
        '<cmyk method="custom"/></color>'
        % (quoteattr(proj.cor_nome), _num(c), _num(m), _num(y), _num(k)))
    add('</colors>')

    # --- Símbolo de curva -------------------------------------------------
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

    # --- Objetos (curvas) -------------------------------------------------
    add('<parts count="1" current="0">')
    add('<part name="Curvas de nível"><objects count="%d">'
        % len(proj.linhas_mm))
    for linha in proj.linhas_mm:
        add('<object type="1" symbol="0"><coords count="%d">%s</coords>'
            '</object>' % (len(linha), _coords_xml(linha)))
    add('</objects></part>')
    add('</parts>')

    # --- Satélite como mapa de fundo georreferenciado ---------------------
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
