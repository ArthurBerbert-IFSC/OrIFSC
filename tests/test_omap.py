"""Escritor .omap (XML do OpenOrienteering Mapper): estrutura e coordenadas."""
import xml.etree.ElementTree as ET
from types import SimpleNamespace

NS = '{http://openorienteering.org/apps/mapper/xml/v2}'


def _projeto_falso(linhas_mm, satelite=None):
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
        cor=(0.0, 0.56, 1.0, 0.18),
        cor_nome='Marrom (curvas)',
        largura_um=140,
        codigo_simbolo=101,
        linhas_mm=linhas_mm,
        satelite=satelite,
    )


def _gerar(omap, tmp_path, linhas, satelite=None):
    caminho = str(tmp_path / 'projeto.omap')
    omap.escrever_omap(_projeto_falso(linhas, satelite), caminho)
    return ET.parse(caminho).getroot()


def test_georreferencia(omap, tmp_path):
    raiz = _gerar(omap, tmp_path, [[(0.0, 0.0), (10.0, 5.0)]])
    geo = raiz.find(f'{NS}georeferencing')
    assert geo.get('scale') == '10000'
    assert float(geo.get('declination')) == -21.3
    assert float(geo.get('grivation')) == -19.5
    ref = geo.find(f'{NS}projected_crs/{NS}ref_point')
    assert float(ref.get('x')) == 700000.0
    assert float(ref.get('y')) == 6900000.0


def test_objetos_e_coordenadas_em_milesimos_de_mm(omap, tmp_path):
    raiz = _gerar(omap, tmp_path, [[(0.0, 0.0), (10.0, 5.0), (20.0, 0.0)]])
    objetos = raiz.findall(f'.//{NS}object')
    assert len(objetos) == 1
    coords = objetos[0].find(f'{NS}coords')
    assert coords.get('count') == '3'
    assert coords.text == '0 0;10000 5000;20000 0;'


def test_sem_satelite_sem_template(omap, tmp_path):
    raiz = _gerar(omap, tmp_path, [[(0.0, 0.0), (1.0, 1.0)]])
    assert raiz.find(f'{NS}templates') is None


def test_satelite_vira_template_georreferenciado(omap, tmp_path):
    sat = {'path': 'C:/saida/satelite_orifsc.tif'}
    raiz = _gerar(omap, tmp_path, [[(0.0, 0.0), (1.0, 1.0)]], satelite=sat)
    template = raiz.find(f'{NS}templates/{NS}template')
    assert template is not None
    assert template.get('georef') == 'true'
    # Só o nome do arquivo (relativo): o .tif deve viajar junto do projeto.
    assert template.get('path') == 'satelite_orifsc.tif'


def test_cor_unica_cmyk(omap, tmp_path):
    raiz = _gerar(omap, tmp_path, [[(0.0, 0.0), (1.0, 1.0)]])
    cores = raiz.find(f'{NS}colors')
    assert cores.get('count') == '1'
    cor = cores.find(f'{NS}color')
    assert cor.get('m') == '0.56'
    assert cor.get('k') == '0.18'
