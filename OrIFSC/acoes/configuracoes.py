"""Configurações — padrões globais do OrIFSC.

Guarda preferências do usuário em `QgsSettings` (prefixo `OrIFSC/`), válidas para
todos os projetos — diferente de `comum.py`, que guarda o estado *do projeto*
atual (folha, escala, EPSG). Outros passos leem esses padrões: `definir_local`
pré-seleciona escala/folha/orientação e `gerar_curvas` usa a equidistância.
"""
from typing import Any

from qgis.core import QgsSettings
from qgis.PyQt.QtWidgets import (
    QDialog, QFormLayout, QVBoxLayout, QHBoxLayout, QComboBox, QSpinBox,
    QLineEdit, QPushButton, QDialogButtonBox, QFileDialog,
)

from .painel import montar_com_painel, INSTRUCOES

PREFIXO = 'OrIFSC/'

FOLHAS = ['A3', 'A4', 'A5']
ORIENTACOES = ['Paisagem', 'Retrato']
SIMBOLOGIAS = [
    'Automática (pela escala do projeto)',
    'ISOM 2017-2 (floresta)',
    'ISSprOM 2019-2 (sprint)',
    'Nenhuma (só curvas)',
]

PADROES = {
    'escala_padrao': 10000,
    'folha_padrao': 'A4',
    'orientacao_padrao': 'Paisagem',
    'equidistancia_padrao': 5,
    'simbologia_padrao': SIMBOLOGIAS[0],
    'pasta_saida': '',
}


def _get(chave: str) -> Any:
    """Lê uma preferência global em ``QgsSettings`` com fallback do plugin.

    Args:
        chave: Nome da chave dentro do prefixo ``OrIFSC/``.

    Returns:
        Any: Valor persistido ou valor padrão definido em ``PADROES``.

    Usa escopo global para manter preferências entre projetos, conforme a
    diretriz de separação entre estado de projeto (``QgsProject``) e padrões
    globais (``QgsSettings``).
    """
    return QgsSettings().value(PREFIXO + chave, PADROES[chave])


def ler_escala_padrao() -> int:
    """Retorna a escala padrão global para novos fluxos de definição local.

    Returns:
        int: Denominador da escala.
    """
    try:
        return int(_get('escala_padrao'))
    except (TypeError, ValueError):
        return PADROES['escala_padrao']


def ler_equidistancia_padrao() -> int:
    """Retorna a equidistância padrão de curvas em metros.

    Returns:
        int: Equidistância padrão.
    """
    try:
        return int(_get('equidistancia_padrao'))
    except (TypeError, ValueError):
        return PADROES['equidistancia_padrao']


def ler_folha_padrao() -> str:
    """Retorna o formato de folha padrão para novos diálogos.

    Returns:
        str: Nome da folha (A3, A4 ou A5).
    """
    return str(_get('folha_padrao'))


def ler_orientacao_padrao() -> str:
    """Retorna a orientação padrão de folha.

    Returns:
        str: ``Paisagem`` ou ``Retrato``.
    """
    return str(_get('orientacao_padrao'))


def ler_simbologia_padrao() -> str:
    """Retorna a simbologia padrão da exportação (rótulo de ``SIMBOLOGIAS``).

    Returns:
        str: Uma das opções de ``SIMBOLOGIAS``.
    """
    valor = str(_get('simbologia_padrao'))
    return valor if valor in SIMBOLOGIAS else SIMBOLOGIAS[0]


def indice_simbologia_padrao() -> int:
    """Índice padrão para o parâmetro Simbologia da exportação.

    Returns:
        int: 0 = ISOM, 1 = ISSprOM, 2 = Nenhuma (ordem do diálogo de
        exportação).

    Quando a preferência é 'Automática', sugere pela escala do projeto
    atual: sprints (denominador <= 5.000) usam ISSprOM; o resto, ISOM.
    """
    pref = ler_simbologia_padrao()
    if pref == SIMBOLOGIAS[1]:
        return 0
    if pref == SIMBOLOGIAS[2]:
        return 1
    if pref == SIMBOLOGIAS[3]:
        return 2
    from .comum import ler_escala
    escala = ler_escala()
    if escala and int(escala) <= 5000:
        return 1
    return 0


def ler_pasta_saida() -> str:
    """Retorna pasta padrão de saída para exportação.

    Returns:
        str: Caminho absoluto ou vazio.
    """
    return str(_get('pasta_saida'))


class DialogConfiguracoes(QDialog):
    """Diálogo de configuração global persistente do plugin."""

    def __init__(self, parent=None) -> None:
        """Monta UI e carrega preferências globais atuais.

        Args:
            parent: Widget pai opcional.

        Mantém opções em ``QgsSettings`` para que o comportamento padrão seja
        consistente entre projetos e sessões, como definido nas diretrizes.
        """
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

        self.simb_combo = QComboBox()
        self.simb_combo.addItems(SIMBOLOGIAS)
        form.addRow('Simbologia da exportação:', self.simb_combo)

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

    def _escolher_pasta(self) -> None:
        """Abre seletor de diretório para a pasta padrão de saída.
        """
        pasta = QFileDialog.getExistingDirectory(
            self, 'Pasta de saída padrão', self.pasta_edit.text())
        if pasta:
            self.pasta_edit.setText(pasta)

    def _carregar(self) -> None:
        """Carrega valores persistidos e preenche os controles da UI.
        """
        self.escala_spin.setValue(ler_escala_padrao())
        self.equi_spin.setValue(ler_equidistancia_padrao())
        folha = ler_folha_padrao()
        if folha in FOLHAS:
            self.folha_combo.setCurrentIndex(FOLHAS.index(folha))
        ori = ler_orientacao_padrao()
        if ori in ORIENTACOES:
            self.orientacao_combo.setCurrentIndex(ORIENTACOES.index(ori))
        self.simb_combo.setCurrentIndex(
            SIMBOLOGIAS.index(ler_simbologia_padrao()))
        self.pasta_edit.setText(ler_pasta_saida())

    def _salvar(self) -> None:
        """Persiste as preferências globais escolhidas e fecha com sucesso."""
        s = QgsSettings()
        s.setValue(PREFIXO + 'escala_padrao', int(self.escala_spin.value()))
        s.setValue(PREFIXO + 'folha_padrao', self.folha_combo.currentText())
        s.setValue(
            PREFIXO + 'orientacao_padrao',
            self.orientacao_combo.currentText())
        s.setValue(PREFIXO + 'equidistancia_padrao',
                   int(self.equi_spin.value()))
        s.setValue(PREFIXO + 'simbologia_padrao',
                   self.simb_combo.currentText())
        s.setValue(PREFIXO + 'pasta_saida', self.pasta_edit.text())
        self.accept()
