"""Configurações — padrões globais do OrIFSC.

Guarda preferências do usuário em `QgsSettings` (prefixo `OrIFSC/`), válidas para
todos os projetos — diferente de `comum.py`, que guarda o estado *do projeto*
atual (folha, escala, EPSG). Outros passos leem esses padrões: `definir_local`
pré-seleciona escala/folha/orientação e `gerar_curvas` usa a equidistância.
"""
from qgis.core import QgsSettings
from qgis.PyQt.QtWidgets import (
    QDialog, QFormLayout, QVBoxLayout, QHBoxLayout, QComboBox, QSpinBox,
    QLineEdit, QPushButton, QDialogButtonBox, QFileDialog,
)

from .painel import montar_com_painel, INSTRUCOES

PREFIXO = 'OrIFSC/'

FOLHAS = ['A3', 'A4', 'A5']
ORIENTACOES = ['Paisagem', 'Retrato']
FONTES_DEM = ['Copernicus 30m', 'FABDEM (em breve)']

PADROES = {
    'escala_padrao': 10000,
    'folha_padrao': 'A4',
    'orientacao_padrao': 'Paisagem',
    'equidistancia_padrao': 5,
    'fonte_dem': 'copernicus',
    'pasta_saida': '',
}


def _get(chave):
    return QgsSettings().value(PREFIXO + chave, PADROES[chave])


def ler_escala_padrao():
    try:
        return int(_get('escala_padrao'))
    except (TypeError, ValueError):
        return PADROES['escala_padrao']


def ler_equidistancia_padrao():
    try:
        return int(_get('equidistancia_padrao'))
    except (TypeError, ValueError):
        return PADROES['equidistancia_padrao']


def ler_folha_padrao():
    return str(_get('folha_padrao'))


def ler_orientacao_padrao():
    return str(_get('orientacao_padrao'))


def ler_pasta_saida():
    return str(_get('pasta_saida'))


class DialogConfiguracoes(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('OrIFSC — Configurações')
        self.setMinimumWidth(420)

        layout = QVBoxLayout()
        form = QFormLayout()
        layout.addLayout(form)

        self.escala_spin = QSpinBox()
        self.escala_spin.setRange(500, 500000)
        self.escala_spin.setPrefix('1:')
        form.addRow('Escala padrão:', self.escala_spin)

        self.folha_combo = QComboBox()
        self.folha_combo.addItems(FOLHAS)
        form.addRow('Tamanho de folha padrão:', self.folha_combo)

        self.orientacao_combo = QComboBox()
        self.orientacao_combo.addItems(ORIENTACOES)
        form.addRow('Orientação padrão:', self.orientacao_combo)

        self.equi_spin = QSpinBox()
        self.equi_spin.setRange(1, 100)
        self.equi_spin.setSuffix(' m')
        form.addRow('Equidistância padrão:', self.equi_spin)

        self.dem_combo = QComboBox()
        self.dem_combo.addItems(FONTES_DEM)
        # FABDEM ainda não implementado — item desabilitado.
        item_fabdem = self.dem_combo.model().item(1)
        if item_fabdem is not None:
            item_fabdem.setEnabled(False)
        form.addRow('Fonte de DEM:', self.dem_combo)

        pasta_box = QHBoxLayout()
        self.pasta_edit = QLineEdit()
        btn_pasta = QPushButton('…')
        btn_pasta.setMaximumWidth(32)
        btn_pasta.clicked.connect(self._escolher_pasta)
        pasta_box.addWidget(self.pasta_edit)
        pasta_box.addWidget(btn_pasta)
        form.addRow('Pasta de saída padrão:', pasta_box)

        botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                  QDialogButtonBox.StandardButton.Cancel)
        botoes.button(QDialogButtonBox.StandardButton.Ok).setText('Salvar')
        botoes.button(
            QDialogButtonBox.StandardButton.Cancel).setText('Cancelar')
        botoes.accepted.connect(self._salvar)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)

        montar_com_painel(self, layout, 'Configurações',
                          INSTRUCOES['configuracoes'], largura=360, altura_min=400)

        self._carregar()

    def _escolher_pasta(self):
        pasta = QFileDialog.getExistingDirectory(
            self, 'Pasta de saída padrão', self.pasta_edit.text())
        if pasta:
            self.pasta_edit.setText(pasta)

    def _carregar(self):
        self.escala_spin.setValue(ler_escala_padrao())
        self.equi_spin.setValue(ler_equidistancia_padrao())
        folha = ler_folha_padrao()
        if folha in FOLHAS:
            self.folha_combo.setCurrentIndex(FOLHAS.index(folha))
        ori = ler_orientacao_padrao()
        if ori in ORIENTACOES:
            self.orientacao_combo.setCurrentIndex(ORIENTACOES.index(ori))
        self.dem_combo.setCurrentIndex(0)  # Copernicus (FABDEM desabilitado)
        self.pasta_edit.setText(ler_pasta_saida())

    def _salvar(self):
        s = QgsSettings()
        s.setValue(PREFIXO + 'escala_padrao', int(self.escala_spin.value()))
        s.setValue(PREFIXO + 'folha_padrao', self.folha_combo.currentText())
        s.setValue(
            PREFIXO + 'orientacao_padrao',
            self.orientacao_combo.currentText())
        s.setValue(PREFIXO + 'equidistancia_padrao',
                   int(self.equi_spin.value()))
        s.setValue(PREFIXO + 'fonte_dem', 'copernicus')
        s.setValue(PREFIXO + 'pasta_saida', self.pasta_edit.text())
        self.accept()
