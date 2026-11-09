"""Internacionalização: catálogos completos e coerentes com o código.

Garante que todo texto passado a ``tr()``/``N_()`` no plugin tem tradução em
inglês e turco, que as traduções preservam os placeholders ``{nome}`` e as
marcações HTML, e que a resolução do idioma e o ``tr()`` se comportam como
documentado em ``OrIFSC/i18n/__init__.py``.
"""
import re
import string

import pytest

IDIOMAS_TRADUZIDOS = ['en', 'tr']


def _placeholders(texto):
    return sorted(campo for _, campo, _, _ in string.Formatter().parse(texto)
                  if campo is not None)


def _tags(texto):
    return sorted(re.findall(r'</?[a-zA-Z]+', texto))


@pytest.fixture(scope='module')
def textos(extrator):
    return [t for t, _, _ in extrator.extrair_strings()]


def test_ha_textos_extraidos(textos):
    assert len(textos) > 150


def test_sem_fstring_ou_concatenacao_no_tr(extrator):
    assert extrator.chamadas_invalidas() == []


@pytest.mark.parametrize('codigo', IDIOMAS_TRADUZIDOS)
def test_catalogo_completo(extrator, textos, codigo):
    cat = extrator.ler_catalogo(codigo)
    faltando = [t for t in textos if not cat.get(t)]
    assert faltando == [], (
        f'{codigo}.json sem tradução para {len(faltando)} texto(s); rode '
        f'python tools/i18n_atualizar.py e traduza: {faltando[:5]}')


@pytest.mark.parametrize('codigo', IDIOMAS_TRADUZIDOS)
def test_catalogo_sem_orfas(extrator, textos, codigo):
    cat = extrator.ler_catalogo(codigo)
    orfas = [k for k in cat if k not in set(textos)]
    assert orfas == [], (
        f'{codigo}.json tem chaves que não existem mais no código; rode '
        f'python tools/i18n_atualizar.py --podar: {orfas[:5]}')


@pytest.mark.parametrize('codigo', IDIOMAS_TRADUZIDOS)
def test_placeholders_preservados(extrator, codigo):
    for orig, trad in extrator.ler_catalogo(codigo).items():
        assert _placeholders(orig) == _placeholders(trad), (codigo, orig)


@pytest.mark.parametrize('codigo', IDIOMAS_TRADUZIDOS)
def test_html_preservado(extrator, codigo):
    for orig, trad in extrator.ler_catalogo(codigo).items():
        assert _tags(orig) == _tags(trad), (codigo, orig)


def test_idiomas_declarados_tem_catalogo(i18n, extrator):
    existentes = set(extrator.catalogos_existentes())
    for codigo in i18n.codigos():
        if codigo != i18n.IDIOMA_FONTE:
            assert codigo in existentes


@pytest.mark.parametrize('pref, qgis, esperado', [
    ('auto', 'tr', 'tr'),
    ('auto', 'pt', 'pt'),
    ('auto', 'en', 'en'),
    ('auto', 'de', 'en'),      # QGIS sem catálogo → inglês
    ('auto', '', 'en'),
    ('tr', 'pt', 'tr'),        # escolha explícita vence o QGIS
    ('pt', 'en', 'pt'),
    ('xx', 'tr', 'tr'),        # preferência inválida = automático
])
def test_resolver_idioma(i18n, pref, qgis, esperado):
    assert i18n.resolver_idioma(pref, qgis) == esperado


def test_tr_traduz_e_formata(i18n):
    i18n.definir_idioma_ativo('tr')
    assert i18n.tr('Salvar') == 'Kaydet'
    assert i18n.tr('{n} curva(s) lida(s).', n=7) == '7 eğri okundu.'
    i18n.definir_idioma_ativo('en')
    assert i18n.tr('Salvar') == 'Save'
    assert i18n.tr('Idioma do plugin: {idioma}.',
                   idioma='English') == 'Plugin language: English.'


def test_tr_portugues_e_texto_desconhecido(i18n):
    i18n.definir_idioma_ativo('pt')
    assert i18n.tr('Salvar') == 'Salvar'
    assert i18n.tr('{n} curva(s) lida(s).', n=2) == '2 curva(s) lida(s).'
    i18n.definir_idioma_ativo('tr')
    assert i18n.tr('Texto que não existe no catálogo') == (
        'Texto que não existe no catálogo')


def test_tr_tolera_placeholder_quebrado(i18n, monkeypatch):
    i18n.definir_idioma_ativo('tr')
    cat = i18n.carregar_catalogo('tr')
    monkeypatch.setitem(cat, '{n} curva(s) lida(s).', '{x} eğri okundu.')
    assert i18n.tr('{n} curva(s) lida(s).', n=3) == '3 curva(s) lida(s).'


def test_n_nao_traduz(i18n):
    i18n.definir_idioma_ativo('tr')
    assert i18n.N_('Salvar') == 'Salvar'


def test_maiusculas_turco(i18n):
    i18n.definir_idioma_ativo('tr')
    assert i18n.maiusculas('Genel varsayılanlar') == 'GENEL VARSAYILANLAR'
    assert i18n.maiusculas('Ne işe yarar') == 'NE İŞE YARAR'
    i18n.definir_idioma_ativo('en')
    assert i18n.maiusculas('What it does') == 'WHAT IT DOES'


def test_formatar_inteiro(i18n):
    i18n.definir_idioma_ativo('en')
    assert i18n.formatar_inteiro(10000) == '10,000'
    for codigo in ('pt', 'tr'):
        i18n.definir_idioma_ativo(codigo)
        assert i18n.formatar_inteiro(10000) == '10.000'
    assert i18n.formatar_inteiro(500) == '500'


def test_sem_qgis_preferencia_e_automatica(i18n):
    # Fora do QGIS não há QgsSettings: a preferência cai em 'auto'.
    assert i18n.preferencia_idioma() == i18n.AUTO
