"""Internacionalização (i18n) do OrIFSC — português (original), inglês e turco.

Abordagem no estilo gettext: o **texto-fonte em português é a chave**. No
código, todo texto visível ao usuário passa por ``tr('Texto em português')``;
a tradução vem de um catálogo JSON por idioma (``en.json``, ``tr.json``, nesta
pasta). Texto sem tradução cai no original em português — nunca quebra.

- ``tr(texto, **kwargs)``: traduz e, se houver kwargs, aplica ``str.format``
  com placeholders nomeados (``tr('{n} curva(s)', n=3)``) — o tradutor pode
  reordenar as palavras sem mexer no código.
- ``N_(texto)``: só marca o texto para extração (não traduz). Para listas
  definidas no nível do módulo, cujo valor também serve de chave estável
  (ex.: preferências salvas); a tela mostra ``tr(valor)``.
- Idioma ativo: a preferência ``OrIFSC/idioma`` (QgsSettings) — ``auto``
  (padrão) segue o idioma do QGIS; idioma do QGIS sem catálogo cai no inglês.

Módulo puro (sem import de ``qgis`` no nível do módulo) para continuar
testável sem o QGIS. Para atualizar os catálogos depois de mexer em textos do
código: ``python tools/i18n_atualizar.py`` (ver Diretrizes, seção 5).
"""
import json
import os
from typing import Any, Dict, List, Optional, Tuple

PASTA = os.path.dirname(os.path.abspath(__file__))

IDIOMA_FONTE = 'pt'
IDIOMA_RESERVA = 'en'
AUTO = 'auto'
CHAVE_CONFIG = 'OrIFSC/idioma'

# (código ISO 639-1, nome nativo). O nome nativo NÃO é traduzido, para que
# qualquer usuário reconheça o próprio idioma na lista. Para incluir um
# idioma: acrescente aqui e crie o catálogo com tools/i18n_atualizar.py.
IDIOMAS: List[Tuple[str, str]] = [
    ('pt', 'Português'),
    ('en', 'English'),
    ('tr', 'Türkçe'),
]

_catalogos: Dict[str, Dict[str, str]] = {}
_ativo: Optional[str] = None


def N_(texto: str) -> str:
    """Marca ``texto`` para tradução sem traduzir (é traduzido ao exibir)."""
    return texto


def codigos() -> List[str]:
    """Códigos dos idiomas suportados, na ordem de exibição."""
    return [c for c, _ in IDIOMAS]


def nome_idioma(codigo: str) -> str:
    """Nome nativo do idioma (ex.: 'Türkçe'), ou o próprio código."""
    return dict(IDIOMAS).get(codigo, codigo)


def carregar_catalogo(codigo: str) -> Dict[str, str]:
    """Catálogo ``{texto_pt: tradução}`` do idioma (vazio para o português).

    Entradas vazias são ignoradas (caem no original). Catálogo ausente ou
    corrompido vira catálogo vazio: o plugin segue em português, sem falhar.
    """
    if codigo == IDIOMA_FONTE:
        return {}
    if codigo not in _catalogos:
        try:
            with open(os.path.join(PASTA, f'{codigo}.json'),
                      encoding='utf-8') as f:
                dados = json.load(f)
        except (OSError, ValueError):
            dados = {}
        if not isinstance(dados, dict):
            dados = {}
        _catalogos[codigo] = {k: v for k, v in dados.items()
                              if isinstance(v, str) and v}
    return _catalogos[codigo]


def resolver_idioma(preferencia: str, idioma_qgis: str) -> str:
    """Idioma efetivo: a preferência explícita, se suportada; senão (``auto``)
    o idioma do QGIS, se suportado; senão o inglês (idioma internacional)."""
    if preferencia in codigos():
        return preferencia
    if idioma_qgis in codigos():
        return idioma_qgis
    return IDIOMA_RESERVA


def idioma_do_qgis() -> str:
    """Código de 2 letras do idioma da interface do QGIS (ex.: 'pt', 'tr').

    ``QgsApplication.locale()`` já considera a opção "Substituir o idioma do
    sistema" do QGIS; sem QGIS (testes), usa o idioma do sistema via Qt.
    """
    loc = ''
    try:
        from qgis.core import QgsApplication
        loc = QgsApplication.locale() or ''
    except Exception:  # nosec B110 - fora do QGIS (testes): tenta o Qt
        pass
    if not loc:
        try:
            from qgis.PyQt.QtCore import QLocale
            loc = QLocale.system().name()
        except Exception:  # nosec B110 - sem Qt: idioma indefinido
            loc = ''
    return loc.replace('-', '_').split('_')[0].lower()


def preferencia_idioma() -> str:
    """Preferência salva (``auto``, ``pt``, ``en``, ``tr``...)."""
    try:
        from qgis.core import QgsSettings
        valor = QgsSettings().value(CHAVE_CONFIG, AUTO)
    except Exception:
        return AUTO
    valor = str(valor or AUTO)
    return valor if valor == AUTO or valor in codigos() else AUTO


def salvar_preferencia_idioma(codigo: str) -> None:
    """Grava a preferência de idioma e passa a usá-la imediatamente."""
    from qgis.core import QgsSettings
    if codigo != AUTO and codigo not in codigos():
        codigo = AUTO
    QgsSettings().setValue(CHAVE_CONFIG, codigo)
    redefinir()


def idioma() -> str:
    """Idioma ativo do plugin (resolvido uma vez e guardado em cache)."""
    global _ativo
    if _ativo is None:
        _ativo = resolver_idioma(preferencia_idioma(), idioma_do_qgis())
    return _ativo


def definir_idioma_ativo(codigo: Optional[str]) -> None:
    """Força o idioma ativo (testes). ``None`` volta a resolver pela
    preferência salva na próxima chamada."""
    global _ativo
    _ativo = codigo


def redefinir() -> None:
    """Descarta o idioma em cache (após mudar a preferência)."""
    definir_idioma_ativo(None)


def tr(texto: str, **kwargs: Any) -> str:
    """Traduz ``texto`` (português) para o idioma ativo.

    Com ``kwargs``, aplica ``format`` nos placeholders nomeados. Se a tradução
    estiver com placeholder errado, usa o original — nunca levanta exceção na
    cara do usuário por causa de um catálogo.
    """
    cod = idioma()
    traduzido = texto if cod == IDIOMA_FONTE else carregar_catalogo(
        cod).get(texto, texto)
    if not kwargs:
        return traduzido
    try:
        return traduzido.format(**kwargs)
    except (KeyError, IndexError, ValueError):
        return texto.format(**kwargs)


def maiusculas(texto: str) -> str:
    """``upper()`` com a regra do turco (i → İ; ı → I), que o Python não
    aplica sozinho."""
    if idioma() == 'tr':
        texto = texto.replace('i', 'İ')
    return texto.upper()


def formatar_inteiro(valor: int) -> str:
    """Inteiro com separador de milhar do idioma: 10.000 (pt/tr) ou
    10,000 (en)."""
    s = f'{int(valor):,}'
    return s if idioma() == 'en' else s.replace(',', '.')
