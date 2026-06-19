"""Ajuda / Sobre — janela "Sobre" e atalho para a documentação.

Lê os dados (versão, descrição, links) do `metadata.txt` para não duplicar
informação.
"""
import os
import configparser

from qgis.PyQt.QtWidgets import QMessageBox
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtGui import QDesktopServices

_METADATA = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'metadata.txt')


def _geral():
    cfg = configparser.RawConfigParser()
    cfg.read(_METADATA, encoding='utf-8')
    return cfg['general'] if cfg.has_section('general') else {}


def sobre(parent=None):
    g = _geral()
    versao = g.get('version', '?')
    about = g.get('about', '')
    repo = g.get('repository', '')
    tracker = g.get('tracker', '')
    autor = g.get('author', '')
    from .painel import logos_html
    html = (
        logos_html(altura=44)
        + f'<h3>OrIFSC {versao}</h3>'
        f'<p>{about}</p>'
        f'<p><b>Autoria:</b> {autor}</p>'
        f"<p><a href='{repo}'>Repositório</a> &nbsp;·&nbsp; "
        f"<a href='{tracker}'>Reportar problema</a></p>"
    )
    QMessageBox.about(parent, 'Sobre o OrIFSC', html)


def abrir_documentacao():
    g = _geral()
    url = g.get('homepage') or g.get('repository') or ''
    if url:
        QDesktopServices.openUrl(QUrl(url))
