"""Injeção do projeto nos symbol sets oficiais (.omap com simbologia).

Usa os symbol sets reais embutidos em ``recursos/simbologias/`` — além da
lógica de injeção, valida que os arquivos versionados têm a estrutura
esperada (símbolos 101/102, partes, georreferência).
"""
import xml.etree.ElementTree as ET
from types import SimpleNamespace

NS = '{http://openorienteering.org/apps/mapper/xml/v2}'


def _projeto_falso(linhas_mm, satelite=None, codigos_linhas=None):
    return SimpleNamespace(
        escala=10000,
        declinacao=-21.3,
        grivacao=-19.5,
        proj4='+proj=utm +zone=22 +south +datum=WGS84 +units=m +no_defs',
        crs_param='22 S',
        ref_e=700000.0,
        ref_n=6900000.0,
        lat=-27.59,
        lon=-48.54,
        linhas_mm=linhas_mm,
        codigos_linhas=codigos_linhas,
        satelite=satelite,
    )


def _gerar(simbologia, tmp_path, linhas, satelite=None, codigos=None,
           norma=None, escala=10000):
    base = simbologia.arquivo_simbologia(
        norma or simbologia.NORMA_ISOM, escala)
    caminho = str(tmp_path / 'projeto.omap')
    simbologia.escrever_omap_com_simbologia(
        _projeto_falso(linhas, satelite, codigos), caminho, base)
    return ET.parse(caminho).getroot()


def _container(raiz):
    barrier = raiz.find(f'{NS}barrier')
    return raiz if barrier is None else barrier


def test_arquivo_simbologia_por_norma_e_escala(simbologia):
    assert simbologia.arquivo_simbologia(
        simbologia.NORMA_ISOM, 15000).endswith('ISOM_2017-2_15000.omap')
    assert simbologia.arquivo_simbologia(
        simbologia.NORMA_ISOM, 10000).endswith('ISOM_2017-2_10000.omap')
    assert simbologia.arquivo_simbologia(
        simbologia.NORMA_ISOM, 7500).endswith('ISOM_2017-2_10000.omap')
    assert simbologia.arquivo_simbologia(
        simbologia.NORMA_ISSPROM, 4000).endswith('ISSprOM_2019_4000.omap')
    assert simbologia.arquivo_simbologia(
        simbologia.NORMA_ISSPROM, 3000).endswith('ISSprOM_2019_4000.omap')
    assert simbologia.arquivo_simbologia(
        simbologia.NORMA_ISOM, 15000, '.ocd').endswith(
        'ISOM_2017-2_15000.ocd')


def test_arquivo_simbologia_norma_invalida(simbologia):
    import pytest
    with pytest.raises(ValueError):
        simbologia.arquivo_simbologia('ISOM-1990', 15000)


def test_classificar_curvas_mestra_a_cada_5_equidistancias(simbologia):
    elevs = [10.0, 15.0, 20.0, 25.0, 30.0, 50.0]
    assert simbologia.classificar_curvas(elevs) == [
        '101', '101', '101', '102', '101', '102']


def test_classificar_curvas_sem_elevacao_ou_insuficiente(simbologia):
    assert simbologia.classificar_curvas([None, None]) == ['101', '101']
    assert simbologia.classificar_curvas([25.0]) == ['101']
    assert simbologia.classificar_curvas([]) == []
    # Elevação ausente numa curva não impede classificar as demais.
    assert simbologia.classificar_curvas([20.0, None, 25.0]) == [
        '101', '101', '102']


def test_classificar_curvas_tolerancia_float(simbologia):
    elevs = [10.0, 15.0, 20.0, 25.0000001, 30.0]
    assert simbologia.classificar_curvas(elevs)[3] == '102'


def test_classificar_curvas_elevacao_negativa(simbologia):
    elevs = [-25.0, -20.0, -15.0, -10.0, -5.0, 0.0]
    assert simbologia.classificar_curvas(elevs) == [
        '102', '101', '101', '101', '101', '102']


def test_issprom_embutido_atualizado_para_2019_2(simbologia):
    """A paleta sprint embutida é a 2019-2 Rev. 6 (atualizada pelo
    tools/atualizar_issprom_2019_2.py sobre o symbol set do OOM)."""
    raiz = ET.parse(simbologia.arquivo_simbologia(
        simbologia.NORMA_ISSPROM, 4000)).getroot()
    container = _container(raiz)
    simbolos = container.find(f'{NS}symbols')
    nomes = {s.get('code'): (s.get('name') or '') for s in simbolos}
    assert 'fight' in nomes['410'].lower()
    assert 'uncrossable' in nomes['411'].lower()
    assert '411.1' in nomes
    assert '533' in nomes
    assert simbolos.get('count') == str(len(simbolos))
    cores = raiz.find(f'{NS}colors')
    assert cores.get('count') == str(len(cores))
    nomes_cores = [c.get('name') for c in cores]
    assert 'Dark green for area features' in nomes_cores
    assert 'Dark green for line symbols' in nomes_cores


def test_symbol_sets_embutidos_tem_101_e_102(simbologia):
    for norma, escala in ((simbologia.NORMA_ISOM, 15000),
                          (simbologia.NORMA_ISOM, 10000),
                          (simbologia.NORMA_ISSPROM, 4000)):
        raiz = ET.parse(simbologia.arquivo_simbologia(norma, escala)).getroot()
        ids = simbologia._mapa_codigo_id(_container(raiz))
        assert '101' in ids and '102' in ids


def test_injecao_substitui_georreferencia(simbologia, tmp_path):
    raiz = _gerar(simbologia, tmp_path, [[(0.0, 0.0), (10.0, 5.0)]])
    geos = raiz.findall(f'{NS}georeferencing')
    assert len(geos) == 1
    geo = geos[0]
    assert geo.get('scale') == '10000'
    assert float(geo.get('declination')) == -21.3
    assert float(geo.get('grivation')) == -19.5
    ref = geo.find(f'{NS}projected_crs/{NS}ref_point')
    assert float(ref.get('x')) == 700000.0
    assert float(ref.get('y')) == 6900000.0


def test_injecao_preserva_simbolos_e_cores(simbologia, tmp_path):
    base = ET.parse(simbologia.arquivo_simbologia(
        simbologia.NORMA_ISOM, 10000)).getroot()
    raiz = _gerar(simbologia, tmp_path, [[(0.0, 0.0), (10.0, 5.0)]])
    for lado_a, lado_b in ((base, raiz),):
        simb_a = _container(lado_a).find(f'{NS}symbols')
        simb_b = _container(lado_b).find(f'{NS}symbols')
        assert simb_b.get('count') == simb_a.get('count')
        assert len(simb_b) == len(simb_a)
        cores_a = lado_a.find(f'{NS}colors')
        cores_b = lado_b.find(f'{NS}colors')
        assert cores_b.get('count') == cores_a.get('count')
        assert len(cores_b) == len(cores_a)


def test_injecao_remove_objetos_de_exemplo_e_grava_curvas(
        simbologia, tmp_path):
    linhas = [[(0.0, 0.0), (10.0, 5.0), (20.0, 0.0)], [(1.0, 1.0), (2.0, 2.0)]]
    raiz = _gerar(simbologia, tmp_path, linhas,
                  codigos=['101', '102'])
    container = _container(raiz)
    ids = simbologia._mapa_codigo_id(container)
    # Só os objetos do mapa (em <parts>): os <object> embutidos nas
    # definições de símbolos de ponto não contam.
    objetos = container.find(f'{NS}parts').findall(f'.//{NS}object')
    assert len(objetos) == 2
    assert objetos[0].get('symbol') == ids['101']
    assert objetos[1].get('symbol') == ids['102']
    coords = objetos[0].find(f'{NS}coords')
    assert coords.get('count') == '3'
    assert coords.text == '0 0;10000 5000;20000 0;'
    pai = container.find(f'{NS}parts')[0].find(f'{NS}objects')
    assert pai.get('count') == '2'


def test_injecao_sem_codigos_usa_curva_normal(simbologia, tmp_path):
    raiz = _gerar(simbologia, tmp_path, [[(0.0, 0.0), (1.0, 1.0)]])
    container = _container(raiz)
    ids = simbologia._mapa_codigo_id(container)
    objeto = container.find(f'{NS}parts/{NS}part/{NS}objects/{NS}object')
    assert objeto.get('symbol') == ids['101']


def test_injecao_template_do_satelite(simbologia, tmp_path):
    sat = {'path': 'C:/saida/satelite_orifsc.tif'}
    raiz = _gerar(simbologia, tmp_path, [[(0.0, 0.0), (1.0, 1.0)]],
                  satelite=sat)
    templates = _container(raiz).find(f'{NS}templates')
    assert templates.get('count') == '1'
    assert templates.get('first_front_template') == '1'
    template = templates.find(f'{NS}template')
    assert template.get('georef') == 'true'
    assert template.get('path') == 'satelite_orifsc.tif'
    # O <defaults> original do symbol set continua lá, depois do template.
    assert templates[-1].tag == f'{NS}defaults'


def test_injecao_sem_satelite_mantem_templates_vazio(simbologia, tmp_path):
    raiz = _gerar(simbologia, tmp_path, [[(0.0, 0.0), (1.0, 1.0)]])
    templates = _container(raiz).find(f'{NS}templates')
    assert templates.get('count') == '0'
    assert templates.find(f'{NS}template') is None


def test_codigos_desalinhados_falham(simbologia, tmp_path):
    import pytest
    base = simbologia.arquivo_simbologia(simbologia.NORMA_ISOM, 10000)
    with pytest.raises(ValueError):
        simbologia.escrever_omap_com_simbologia(
            _projeto_falso([[(0.0, 0.0), (1.0, 1.0)]],
                           codigos_linhas=['101', '102']),
            str(tmp_path / 'projeto.omap'), base)
