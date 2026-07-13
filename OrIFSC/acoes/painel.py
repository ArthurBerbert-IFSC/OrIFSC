"""Painel lateral compartilhado — identidade visual (logos) + instruções.

Fonte única do conteúdo do painel à direita das janelas do OrIFSC, para todas
ficarem com a mesma "margem" do diálogo de Processing. O mesmo HTML é usado de
duas formas:

  - embutido como coluna direita nos diálogos próprios (`criar_painel` /
    `montar_com_painel`): Definir Local, Configurações, Importar KML/GPX;
  - retornado por `shortHelpString()` dos algoritmos de Processing
    (`painel_html`), que o QGIS renderiza no painel de ajuda à direita do
    diálogo: Gerar Curvas, Exportar para o OCAD.

O alvo de renderização é o Qt rich text (subconjunto de HTML4/CSS2). Por isso o
layout é todo em `<table>` + `bgcolor`/`width`/`cellpadding` e as imagens são
PNG (SVG não renderiza). Os componentes visuais (cabeçalho de marca, card,
seção, bullets, passos, dica) e a paleta vivem aqui, em `CORES` + helpers `_*`,
para que todas as telas falem a mesma linguagem visual.

Os logos ficam em `recursos/` (ifsc.png, FLORA.png) e o ícone do
card em `recursos/mdt.png`. Se um arquivo não existir, a `<img>` simplesmente
não aparece — título e instruções continuam visíveis (degradação suave).
"""
import os
from typing import Any, Iterable, Optional, Sequence

from qgis.PyQt.QtWidgets import QTextBrowser, QHBoxLayout

RECURSOS = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'recursos')

LOGOS = [
    ('ifsc.png', 'Instituto Federal de Santa Catarina'),
    ('FLORA.png', 'Clube de Orientação de Florianópolis'),
]

CORES = {
    'acento': '#f1592a',
    'texto': '#23262a',
    'texto2': '#7c828a',
    'texto_desc': '#3a3e43',
    'fundo': '#f6f4ef',
    'cabec_bg': '#ffffff',
    'cabec_borda': '#e6e2d8',
    'card_bg': '#ffffff',
    'card_borda': '#e3dfd6',
    'dica_bg': '#fdf2e9',
    'dica_borda': '#f6d3b8',
    'dica_txt': '#8a5a36',
}
C = CORES


def _uri(arquivo: str) -> str:
    """`file:///...` para um arquivo de `recursos/`, ou '' se não existir."""
    caminho = os.path.join(RECURSOS, arquivo)
    if not os.path.exists(caminho):
        return ''
    return 'file:///' + caminho.replace('\\', '/')


def logos_html(altura: int = 60) -> str:
    """Faixa <img> com os logos existentes em RECURSOS, centralizada. Vazio se
    nenhum arquivo estiver presente."""
    partes = []
    for arquivo, legenda in LOGOS:
        uri = _uri(arquivo)
        if uri:
            partes.append(
                f'<img src="{uri}" height="{altura}" alt="{legenda}">')
    if not partes:
        return ''
    return '<p align="center">' + '&nbsp;&nbsp;&nbsp;'.join(partes) + '</p>'


def _esp(altura: int = 10) -> str:
    """Espaçador vertical entre blocos (margens de tabela são pouco confiáveis
    no Qt rich text, então usamos uma linha vazia com altura fixa)."""
    return (f'<table cellspacing="0" cellpadding="0" width="100%"><tr>'
            f'<td height="{altura}"></td></tr></table>')


def _cabecalho_marca(
        titulo: str, logo: str = 'FLORA.png', rotulo: str = 'ORIFSC') -> str:
    """Cabeçalho branco com borda inferior: logo + rótulo da marca + título.
    Retorna uma `<tr>` da tabela externa montada por `painel_html`."""
    uri = _uri(logo)
    cel_logo = f'<td valign="middle"><img src="{uri}" height="40"></td>' if uri else ''
    pad_txt = ' style="padding-left:12px;"' if uri else ''
    return (
        f'<tr><td bgcolor="{C["cabec_bg"]}" '
        f'style="padding:14px 16px; border-bottom:2px solid {C["cabec_borda"]};">'
        '<table cellspacing="0" cellpadding="0"><tr>'
        f'{cel_logo}'
        f'<td{pad_txt}>'
        f'<span style="color:{C["acento"]}; font-size:10px;"><b>{rotulo}</b></span><br>'
        f'<span style="color:{C["texto"]}; font-size:15px;"><b>{titulo}</b></span>'
        '</td></tr></table>'
        '</td></tr>'
    )


def _card(titulo: str, subtitulo: str, icone: Optional[str] = None) -> str:
    """Card branco com borda: ícone PNG (opcional) + título + subtítulo. Usado
    como "card de fonte de dados"."""
    uri = _uri(icone) if icone else ''
    cel_icone = ''
    pad_txt = ''
    if uri:
        cel_icone = f'<td valign="middle" width="40"><img src="{uri}" height="32"></td>'
        pad_txt = ' style="padding-left:10px;"'
    return (
        '<table width="100%" cellspacing="0" cellpadding="0">'
        f'<tr><td bgcolor="{C["card_bg"]}" '
        f'style="padding:10px 12px; border:1px solid {C["card_borda"]};">'
        '<table cellspacing="0" cellpadding="0"><tr>'
        f'{cel_icone}'
        f'<td valign="middle"{pad_txt}>'
        f'<span style="color:{C["texto"]}; font-size:13px;"><b>{titulo}</b></span><br>'
        f'<span style="color:{C["texto2"]}; font-size:11px;">{subtitulo}</span>'
        '</td></tr></table>'
        '</td></tr></table>'
    )


def _secao(rotulo: str) -> str:
    """Rótulo de seção em cinza, MAIÚSCULAS (ex.: "O QUE FAZ")."""
    return (f'<p style="color:{C["texto2"]}; font-size:10px;">'
            f'<b>{rotulo.upper()}</b></p>')


def _bullets(itens: Sequence[str]) -> str:
    """Lista sem ordem; cada item com marcador laranja. `itens` = lista de HTML.
    Use quando a ordem não importa (o conteúdo pode mudar)."""
    linhas = ''
    for item in itens:
        linhas += (
            '<tr>'
            f'<td valign="top" width="14" style="color:{C["acento"]};"><b>&bull;</b></td>'
            f'<td style="color:{C["texto_desc"]}; font-size:12px; '
            f'padding-bottom:6px;">{item}</td>'
            '</tr>'
        )
    return f'<table cellspacing="0" cellpadding="0">{linhas}</table>'


def _passos(itens: Iterable[Any]) -> str:
    """Lista ordenada; número em célula laranja + título/descrição. `itens` =
    lista de (titulo, descricao) ou strings. Use para fluxos com ordem."""
    linhas = ''
    for i, item in enumerate(itens, 1):
        titulo, desc = item if isinstance(item, (tuple, list)) else (item, '')
        corpo = f'<span style="color:{C["texto"]}; font-size:13px;"><b>{titulo}</b></span>'
        if desc:
            corpo += (f'<br><span style="color:{C["texto2"]}; font-size:12px;">'
                      f'{desc}</span>')
        linhas += (
            '<tr>'
            '<td valign="top" width="22"><table cellspacing="0" cellpadding="0"><tr>'
            f'<td bgcolor="{C["acento"]}" align="center" width="18" '
            f'style="color:#ffffff; font-size:11px;"><b>{i}</b></td>'
            '</tr></table></td>'
            f'<td style="padding-left:8px; padding-bottom:8px;">{corpo}</td>'
            '</tr>'
        )
    return f'<table cellspacing="0" cellpadding="0">{linhas}</table>'


def _dica(texto: str) -> str:
    """Caixa de dica creme com "!" laranja."""
    return (
        '<table width="100%" cellspacing="0" cellpadding="0"><tr>'
        f'<td bgcolor="{C["dica_bg"]}" '
        f'style="padding:10px 12px; border:1px solid {C["dica_borda"]}; '
        f'color:{C["dica_txt"]}; font-size:12px;">'
        f'<b style="color:{C["acento"]};">!</b>&nbsp; {texto}'
        '</td></tr></table>'
    )


def painel_html(titulo: str, instrucoes_html: str, rotulo: str = 'ORIFSC') -> str:
    """HTML completo do painel (chrome): cabeçalho de marca + instruções +
    rodapé de logos, tudo sobre o fundo da paleta. Se `titulo` for vazio, o
    cabeçalho é omitido (degradação suave). `rotulo` é o texto pequeno acima do
    título (padrão da marca; ex.: 'SOBRE' na janela Sobre)."""
    cabec = _cabecalho_marca(titulo, rotulo=rotulo) if titulo else ''
    logos = logos_html(altura=40)
    rodape = (f'<tr><td style="padding:10px 16px 14px 16px;">{logos}</td></tr>'
              if logos else '')
    return (
        f'<table width="100%" cellspacing="0" cellpadding="0" bgcolor="{C["fundo"]}">'
        f'{cabec}'
        f'<tr><td style="padding:12px 16px;">{instrucoes_html}</td></tr>'
        f'{rodape}'
        '</table>'
    )


def criar_painel(
        titulo: str,
        instrucoes_html: str,
        parent: Any = None,
        largura: int = 320,
        altura_min: int = 340) -> QTextBrowser:
    """QTextBrowser estilizado com o conteúdo do painel, para embutir como
    coluna direita de um QDialog próprio. `altura_min` garante que o diálogo
    cresça o suficiente para o texto de ajuda caber sem rolar."""
    tb = QTextBrowser(parent)
    tb.setHtml(painel_html(titulo, instrucoes_html))
    tb.setOpenExternalLinks(True)
    tb.setFixedWidth(largura)
    tb.setMinimumHeight(altura_min)
    tb.setStyleSheet(
        f'QTextBrowser {{ background: {C["fundo"]}; border: none; }}')
    return tb


def montar_com_painel(
        dialog: Any,
        conteudo_layout: Any,
        titulo: str,
        instrucoes_html: str,
        largura: int = 320,
        altura_min: int = 340) -> None:
    """Define o layout do `dialog` como [conteúdo | painel lateral].

    `conteudo_layout` deve ser um QLayout ainda SEM parent (criado com
    QVBoxLayout() em vez de QVBoxLayout(dialog)). `largura`/`altura_min`
    dimensionam o painel (e, por consequência, a altura mínima do diálogo)."""
    raiz = QHBoxLayout(dialog)
    raiz.addLayout(conteudo_layout, 1)
    raiz.addWidget(
        criar_painel(
            titulo,
            instrucoes_html,
            dialog,
            largura,
            altura_min))


INSTRUCOES = {
    'definir_local': (
        _passos([
            ('Cole a coordenada',
             'Lat, Lon do Google Maps — o campo já vem com o centro da vista atual.'),
            ('Escolha escala e folha',
             'Defina a escala e o tamanho da folha (A3 / A4 / A5).'),
            ('Crie a folha',
             'Confira a <b>área no terreno</b> e clique em <b>Criar Folha</b>.'),
        ])
        + _esp()
        + _dica('O projeto é configurado em <b>UTM</b> e a camada '
                '<b>folha</b> é criada.')
    ),
    'configuracoes': (
        _secao('Padrões globais')
        + _bullets([
            'Escala, folha e orientação pré-selecionadas em <i>Definir Local</i>.',
            'Equidistância padrão das curvas de nível.',
            'Pasta de saída padrão da exportação.',
        ])
        + _esp()
        + _dica('Valem para <b>todos os projetos</b>.')
    ),
    'gerar_curvas': (
        _card('MDT Copernicus 30 m', 'Gratuito · sem chave de API', 'mdt.png')
        + _esp()
        + _secao('O que faz')
        + _bullets([
            'Baixa o <b>MDT Copernicus 30 m</b> e gera <b>curvas suavizadas</b> '
            'para a área da folha.',
            '<b>Recorte opcional</b> — corta as curvas na borda de uma camada '
            '(a folha ou o limite).',
        ])
        + _esp()
        + _dica('Deixe <b>Recortar por</b> em branco para recortar pela '
                'própria área a mapear (não precisa selecioná-la de novo).')
    ),
    'importar_kml_gpx': (
        _secao('O que faz')
        + _bullets([
            '<b>GPX</b> — escolha as sub-camadas: trilhas, rotas e/ou waypoints.',
            '<b>KML</b> — importado diretamente; todas as feições são carregadas.',
        ])
        + _esp()
        + _dica('O mapa é centralizado na extensão do arquivo importado.')
    ),
    'exportar_ocad': (
        _secao('O que gera')
        + _bullets([
            '<b>projeto_orifsc.ocd</b> — abre direto no <b>OCAD 10+</b>.',
            '<b>projeto_orifsc.omap</b> — abre no <b>OpenOrienteering Mapper</b>.',
        ])
        + _esp()
        + _secao('Já vem configurado')
        + _bullets([
            '<b>Georreferência</b> (UTM, escala e grade) e <b>declinação '
            'magnética</b> (automática via WMM/NOAA, ou manual).',
            'O <b>satélite</b> como mapa de fundo georreferenciado.',
            'As <b>curvas de nível</b> já como objetos de linha '
            '(mestras no símbolo 102 a cada 5ª equidistância).',
            'A <b>paleta de símbolos oficial</b> (ISOM 2017-2 ou '
            'ISSprOM 2019-2) pronta para desenhar.',
        ])
        + _esp()
        + _dica('Posicione a folha e salve as edições antes de gerar. Mantenha '
                'o <b>.tif</b> do satélite junto dos projetos.')
    ),
}
