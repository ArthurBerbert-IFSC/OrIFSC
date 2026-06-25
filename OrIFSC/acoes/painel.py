"""Painel lateral compartilhado — identidade visual (logos) + instruções.

Fonte única do conteúdo do painel à direita das janelas do OrIFSC, para todas
ficarem com a mesma "margem" do diálogo de Processing. O mesmo HTML é usado de
duas formas:

  - embutido como coluna direita nos diálogos próprios (`criar_painel` /
    `montar_com_painel`): Definir Local, Configurações;
  - retornado por `shortHelpString()` dos algoritmos de Processing
    (`painel_html`), que o QGIS renderiza no painel de ajuda à direita do
    diálogo: Gerar Curvas, Exportar para o OCAD.

Os logos ficam em `recursos/` (ORIESC.jpg, ifsc.png, FLORA.png). Se um arquivo
não existir, a tag <img> simplesmente não aparece — título e instruções
continuam visíveis (degradação suave).
"""
import os

from qgis.PyQt.QtWidgets import QTextBrowser, QHBoxLayout

RECURSOS = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'recursos')

# (arquivo, legenda) na ordem de exibição.
LOGOS = [
    ('ORIESC.jpg', 'Federação Catarinense de Orientação'),
    ('ifsc.png', 'Instituto Federal de Santa Catarina'),
    ('FLORA.png', 'Clube de Orientação de Florianópolis'),
]


def logos_html(altura=60):
    """Faixa <img> com os logos existentes em RECURSOS, centralizada. Vazio se
    nenhum arquivo estiver presente."""
    partes = []
    for arquivo, legenda in LOGOS:
        caminho = os.path.join(RECURSOS, arquivo)
        if os.path.exists(caminho):
            uri = 'file:///' + caminho.replace('\\', '/')
            partes.append(f'<img src="{uri}" height="{altura}" alt="{legenda}">')
    if not partes:
        return ''
    return '<p align="center">' + '&nbsp;&nbsp;&nbsp;'.join(partes) + '</p>'


def painel_html(titulo, instrucoes_html):
    """HTML completo do painel: logos + título do passo + instruções."""
    logos = logos_html()
    sep = '<hr>' if logos else ''
    cabec = f'<h3>{titulo}</h3>' if titulo else ''
    return logos + sep + cabec + instrucoes_html


def criar_painel(titulo, instrucoes_html, parent=None, largura=320, altura_min=340):
    """QTextBrowser estilizado com o conteúdo do painel, para embutir como
    coluna direita de um QDialog próprio. `altura_min` garante que o diálogo
    cresça o suficiente para o texto de ajuda caber sem rolar."""
    tb = QTextBrowser(parent)
    tb.setHtml(painel_html(titulo, instrucoes_html))
    tb.setOpenExternalLinks(True)
    tb.setFixedWidth(largura)
    tb.setMinimumHeight(altura_min)
    tb.setStyleSheet('QTextBrowser { background: #f5f5f5; border: none; }')
    return tb


def montar_com_painel(dialog, conteudo_layout, titulo, instrucoes_html,
                      largura=320, altura_min=340):
    """Define o layout do `dialog` como [conteúdo | painel lateral].

    `conteudo_layout` deve ser um QLayout ainda SEM parent (criado com
    QVBoxLayout() em vez de QVBoxLayout(dialog)). `largura`/`altura_min`
    dimensionam o painel (e, por consequência, a altura mínima do diálogo)."""
    raiz = QHBoxLayout(dialog)
    raiz.addLayout(conteudo_layout, 1)
    raiz.addWidget(criar_painel(titulo, instrucoes_html, dialog, largura, altura_min))


INSTRUCOES = {
    'definir_local': (
        '<ol>'
        '<li>Cole a <b>coordenada</b> do Google Maps (Lat, Lon) — o campo já vem '
        'preenchido com o centro da vista atual.</li>'
        '<li>Escolha a <b>escala</b> e o <b>tamanho da folha</b>.</li>'
        '<li>Confira a <b>área no terreno</b> e clique em <b>Criar Folha</b>.</li>'
        '</ol>'
        '<p>O projeto é configurado em UTM e a camada <i>folha</i> é criada.</p>'
    ),
    'configuracoes': (
        '<p>Defina os <b>padrões globais</b> (valem para todos os projetos):</p>'
        '<ul>'
        '<li>Escala, folha e orientação pré-selecionadas em <i>Definir Local</i>;</li>'
        '<li>Equidistância padrão das curvas de nível;</li>'
        '<li>Pasta de saída padrão da exportação.</li>'
        '</ul>'
    ),
    'gerar_curvas': (
        '<p>Baixa o <b>MDT Copernicus 30m</b> (gratuito, sem API key) e gera '
        'curvas de nível suavizadas para a área da folha.</p>'
        '<p>Opcionalmente recorta as curvas exatamente na borda de uma camada '
        '(a folha ou o limite). Deixe o recorte em branco para não recortar.</p>'
    ),
    'exportar_ocad': (
        '<p>Gera um <b>projeto pronto para abrir</b>, já configurado, em dois '
        'formatos a partir da folha:</p>'
        '<ul>'
        '<li><b>projeto_oriifsc.ocd</b> — abre direto no <b>OCAD 9+</b>;</li>'
        '<li><b>projeto_oriifsc.omap</b> — abre no <b>OpenOrienteering Mapper</b> '
        '(e, de lá, exporta para OCAD se preciso).</li>'
        '</ul>'
        '<p>Os dois já trazem:</p>'
        '<ul>'
        '<li><b>georreferência</b> (UTM, escala e grade) e <b>declinação '
        'magnética</b> (automática pela coordenada, via WMM/NOAA, ou manual);</li>'
        '<li>o <b>satélite</b> como mapa de fundo georreferenciado;</li>'
        '<li>as <b>curvas de nível</b> já como objetos de linha vinculados ao '
        'símbolo de curva;</li>'
        '<li>a <b>simbologia completa</b> da norma escolhida (ISOM 2017-2, '
        'ISSprOM 2019 ou ISMTBOM), quando há um modelo para a norma e a escala '
        'do projeto. Sem modelo, sai só com as curvas (um aviso é exibido).</li>'
        '</ul>'
        '<p>Escolha a <b>norma de simbologia</b> no diálogo; a escala vem da '
        'folha (definida em "Definir Local e Criar Folha"). Posicione a folha e '
        'salve as edições antes de gerar. O satélite <b>.tif</b> fica na mesma '
        'pasta — mantenha-o junto dos projetos.</p>'
    ),
}
