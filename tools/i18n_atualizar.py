"""Extrai os textos traduzíveis do plugin e atualiza os catálogos de idioma.

Varre ``OrIFSC/**/*.py`` atrás de chamadas ``tr('...')``, ``self.tr('...')``
e ``N_('...')`` com texto literal (o texto em português é a chave) e
sincroniza ``OrIFSC/i18n/<idioma>.json``:

  - chaves novas entram com valor vazio ("") — sem tradução, o plugin mostra o
    original em português até alguém traduzir;
  - traduções existentes são preservadas;
  - chaves que sumiram do código são listadas (``--podar`` remove);
  - o arquivo é regravado na ordem em que os textos aparecem no código, para o
    tradutor ter o contexto de cada tela.

Uso (na raiz do repositório)::

    python tools/i18n_atualizar.py            # atualiza todos os catálogos
    python tools/i18n_atualizar.py --podar    # idem, removendo órfãs
    python tools/i18n_atualizar.py es         # cria/atualiza es.json

Para um idioma novo, além do catálogo, inclua o código em ``IDIOMAS``
(``OrIFSC/i18n/__init__.py``). O teste ``tests/test_i18n.py`` usa as mesmas
funções para garantir que en/tr estão completos.
"""
import ast
import json
import os
import sys
from typing import Dict, List, Tuple

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACOTE = os.path.join(RAIZ, 'OrIFSC')
PASTA_I18N = os.path.join(PACOTE, 'i18n')
FUNCOES = ('tr', 'N_')


def _nome_funcao(no: ast.Call) -> str:
    """Nome da função chamada (``tr``, ``self.tr`` → 'tr'), ou ''."""
    if isinstance(no.func, ast.Name):
        return no.func.id
    if isinstance(no.func, ast.Attribute):
        return no.func.attr
    return ''


def _arquivos(pasta: str) -> List[str]:
    """Arquivos .py do pacote, em ordem estável."""
    saida = []
    for raiz, dirs, nomes in os.walk(pasta):
        dirs.sort()
        for nome in sorted(nomes):
            if nome.endswith('.py'):
                saida.append(os.path.join(raiz, nome))
    return saida


def _chamadas(pasta: str):
    """Gera (arquivo, nó Call) de cada chamada a tr/N_ no pacote, em ordem
    de arquivo e de linha."""
    for arquivo in _arquivos(pasta):
        with open(arquivo, encoding='utf-8') as f:
            arvore = ast.parse(f.read(), arquivo)
        nos = [n for n in ast.walk(arvore)
               if isinstance(n, ast.Call) and _nome_funcao(n) in FUNCOES
               and n.args]
        nos.sort(key=lambda n: (n.lineno, n.col_offset))
        for no in nos:
            yield arquivo, no


def extrair_strings(pasta: str = PACOTE) -> List[Tuple[str, str, int]]:
    """[(texto, arquivo relativo, linha)] de cada texto literal passado a
    tr/N_, sem repetição (fica a primeira ocorrência)."""
    vistos = set()
    saida = []
    for arquivo, no in _chamadas(pasta):
        arg = no.args[0]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            if arg.value not in vistos:
                vistos.add(arg.value)
                saida.append((arg.value, os.path.relpath(arquivo, RAIZ),
                              no.lineno))
    return saida


def chamadas_invalidas(pasta: str = PACOTE) -> List[str]:
    """Chamadas a tr/N_ cujo texto não pode ser traduzido: f-string ou
    concatenação com ``+`` (a chave muda a cada execução). Use placeholders
    nomeados: ``tr('{n} curvas', n=total)``. Variáveis simples são aceitas
    (texto marcado com N_ em outro lugar)."""
    ruins = []
    for arquivo, no in _chamadas(pasta):
        arg = no.args[0]
        if isinstance(arg, (ast.JoinedStr, ast.BinOp)):
            ruins.append(f'{os.path.relpath(arquivo, RAIZ)}:{no.lineno}')
    return ruins


def catalogos_existentes() -> List[str]:
    """Códigos dos catálogos .json presentes em OrIFSC/i18n."""
    return sorted(n[:-5] for n in os.listdir(PASTA_I18N)
                  if n.endswith('.json'))


def ler_catalogo(codigo: str) -> Dict[str, str]:
    """Conteúdo de ``<codigo>.json`` (vazio se não existir)."""
    caminho = os.path.join(PASTA_I18N, f'{codigo}.json')
    if not os.path.exists(caminho):
        return {}
    with open(caminho, encoding='utf-8') as f:
        return json.load(f)


def gravar_catalogo(codigo: str, dados: Dict[str, str]) -> None:
    """Grava o catálogo em JSON legível (UTF-8, sem escapes, indentado)."""
    caminho = os.path.join(PASTA_I18N, f'{codigo}.json')
    with open(caminho, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
        f.write('\n')


def atualizar(codigo: str, textos: List[str], podar: bool) -> Tuple[int, int, int]:
    """Sincroniza um catálogo com os textos do código.
    Retorna (novas, sem_tradução, órfãs)."""
    atual = ler_catalogo(codigo)
    novo = {}
    novas = 0
    for t in textos:
        if t not in atual:
            novas += 1
        novo[t] = atual.get(t, '')
    orfas = [k for k in atual if k not in novo]
    if not podar:
        for k in orfas:
            novo[k] = atual[k]
    gravar_catalogo(codigo, novo)
    vazias = sum(1 for t in textos if not novo.get(t))
    return novas, vazias, len(orfas)


def main(argv: List[str]) -> int:
    podar = '--podar' in argv
    codigos = [a for a in argv if not a.startswith('-')]
    if not codigos:
        codigos = catalogos_existentes()
    ruins = chamadas_invalidas()
    for r in ruins:
        print(f'AVISO: tr() com f-string/concatenação (não traduzível): {r}')
    textos = [t for t, _, _ in extrair_strings()]
    print(f'{len(textos)} textos traduzíveis no código.')
    for codigo in codigos:
        novas, vazias, orfas = atualizar(codigo, textos, podar)
        acao = 'removidas' if podar else 'mantidas (use --podar)'
        print(f'{codigo}.json: {novas} novas, {vazias} sem tradução, '
              f'{orfas} órfãs {acao if orfas else ""}'.rstrip())
    return 1 if ruins else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
