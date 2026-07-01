"""Ajuda / Sobre — janela "Sobre" e atalho para a documentação.

Lê os dados (versão, descrição, links) do `metadata.txt` para não duplicar
informação.
"""
import os
import configparser

from qgis.core import QgsSettings
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QTextBrowser, QDialogButtonBox,
)
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtGui import QDesktopServices

_METADATA = os.path.join(
    os.path.dirname(
        os.path.dirname(__file__)),
    'metadata.txt')


def _geral():
    cfg = configparser.RawConfigParser()
    cfg.read(_METADATA, encoding='utf-8')
    return cfg['general'] if cfg.has_section('general') else {}


def _idioma():
    """Código de idioma do QGIS (ex.: 'pt'), ou '' se indefinido."""
    loc = QgsSettings().value('locale/userLocale', '') or ''
    return loc.split('_')[0].lower()


def _localizado(g, chave):
    """Valor de `chave` no idioma do QGIS (chave[xx]) com fallback para o
    padrão (inglês). O metadata.txt traz description/about em inglês e a
    variante [pt] em português."""
    lang = _idioma()
    if lang:
        traduzido = g.get(f'{chave}[{lang}]')
        if traduzido:
            return traduzido
    return g.get(chave, '')


def sobre(parent=None):
    """Janela "Sobre" — mesmo visual do painel lateral (cabeçalho de marca +
    rodapé de logos), num QDialog com QTextBrowser em vez de QMessageBox para
    controlar largura e fundo da paleta."""
    g = _geral()
    versao = g.get('version', '?')
    about = _localizado(g, 'about')
    repo = g.get('repository', '')
    tracker = g.get('tracker', '')
    autor = g.get('author', '')

    from .painel import painel_html, CORES as C
    corpo = (
        f'<p style="color:{C["texto_desc"]}; font-size:12px;">{about}</p>'
        f'<p style="color:{C["texto2"]}; font-size:12px;">'
        f'<b style="color:{C["texto"]};">Autoria:</b> {autor}</p>'
        '<p style="font-size:12px;">'
        f'<a href="{repo}" style="color:{C["acento"]};">Repositório</a>'
        '&nbsp;&nbsp;·&nbsp;&nbsp;'
        f'<a href="{tracker}" style="color:{C["acento"]};">Reportar problema</a>'
        '</p>'
    )
    html = painel_html(f'OrIFSC {versao}', corpo, rotulo='SOBRE')

    dlg = QDialog(parent)
    dlg.setWindowTitle('Sobre o OrIFSC')
    layout = QVBoxLayout(dlg)

    tb = QTextBrowser()
    tb.setHtml(html)
    tb.setOpenExternalLinks(True)
    tb.setStyleSheet(
        f'QTextBrowser {{ background: {C["fundo"]}; border: none; }}')
    tb.setMinimumSize(380, 460)
    layout.addWidget(tb)

    botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    botoes.button(QDialogButtonBox.StandardButton.Close).setText('Fechar')
    botoes.rejected.connect(dlg.reject)
    botoes.accepted.connect(dlg.accept)
    layout.addWidget(botoes)

    dlg.exec()


def abrir_documentacao():
    g = _geral()
    url = g.get('homepage') or g.get('repository') or ''
    if url:
        QDesktopServices.openUrl(QUrl(url))
