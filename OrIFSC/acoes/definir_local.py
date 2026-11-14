"""Definir Local e Criar Folha.

Diálogo que pede a coordenada (Google Maps), escala e folha; configura o
projeto em UTM, calcula a declinação magnética (WMM offline, ou valor manual),
guarda a folha para os passos seguintes e já cria a camada 'folha' girada para
o norte magnético — assim ela fica em pé no papel do OCAD/OOM. O campo de
coordenada vem pré-preenchido com o centro da vista atual (o satélite do
Passo 1 já está carregado) e continua editável.
"""
import datetime
from typing import Any, Optional, Tuple

from qgis.core import (
    QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsPointXY,
    QgsProject, Qgis,
)
from qgis.PyQt.QtWidgets import (
    QDialog, QFormLayout, QVBoxLayout,
    QLabel, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox,
    QDialogButtonBox,
)

from ..algorithms.ocad.folha import PAPEIS
from ..algorithms.ocad.geo import declinacao_wmm
from ..algorithms.ocad.tipos_mapa import (
    PERSONALIZADO, TIPOS_MAPA, resumo, tem_predefinicao, tipo_por_id,
)
from .painel import montar_com_painel, INSTRUCOES

ESCALAS = [
    ('1:2.000', 2000),
    ('1:3.000', 3000),
    ('1:4.000', 4000),
    ('1:5.000', 5000),
    ('1:7.500', 7500),
    ('1:10.000', 10000),
    ('1:15.000', 15000),
    ('Personalizada...', -1),
]

FOLHAS = list(PAPEIS)


def _graus(valor: float) -> str:
    """Ângulo para exibição em pt-BR: '-20,08°'."""
    return f'{valor:.2f}°'.replace('.', ',')


def mensagem_orientacao(info: dict) -> str:
    """Texto da barra de mensagens depois de criar/ajustar a folha."""
    return (f'Folha girada {_graus(info["grivacao"])} para o norte magnético '
            f'(declinação {_graus(info["declinacao"])}, {info["origem"]}; '
            f'convergência {_graus(info["convergencia"])}). No OCAD ela fica '
            'em pé.')


def ler_coordenada(texto: str) -> Optional[Tuple[float, float]]:
    """(lat, lon) a partir de 'Lat, Lon' (formato do Google Maps), ou None
    se o texto não for uma coordenada válida."""
    try:
        partes = texto.strip().replace(' ', '').split(',')
        lat, lon = float(partes[0]), float(partes[1])
    except (ValueError, IndexError):
        return None
    if not (-90.0 < lat < 90.0 and -180.0 <= lon <= 180.0):
        return None
    return lat, lon


class DialogDefinirLocal(QDialog):
    """Diálogo responsável por configurar CRS, folha e escala do projeto."""

    def __init__(self, iface: Any, parent: Any = None) -> None:
        """Monta o fluxo de definição inicial de folha.

        Args:
            iface: Interface principal do QGIS.
            parent: Widget pai opcional.

        Este passo persiste parâmetros em ``QgsProject`` porque são estado do
        projeto atual e pré-requisito para exportação e demais fluxos.
        """
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle('OrIFSC — Definir Local e Criar Folha')
        self.setMinimumWidth(400)

        layout = QVBoxLayout()
        form = QFormLayout()
        layout.addLayout(form)

        self.tipo_combo = QComboBox()
        for tipo in TIPOS_MAPA:
            self.tipo_combo.addItem(tipo.rotulo, tipo.id)
        form.addRow('Tipo de mapa:', self.tipo_combo)
        self.tipo_resumo = QLabel()
        self.tipo_resumo.setWordWrap(True)
        self.tipo_resumo.setStyleSheet('color: #555; font-style: italic;')
        form.addRow('', self.tipo_resumo)

        self.coord_input = QLineEdit()
        self.coord_input.setPlaceholderText('Ex: -27.5926, -48.5431')
        form.addRow('Coordenada (Google Maps):', self.coord_input)

        self.escala_combo = QComboBox()
        for label, _ in ESCALAS:
            self.escala_combo.addItem(label)
        self.escala_combo.currentIndexChanged.connect(self._on_escala_changed)
        form.addRow('Escala:', self.escala_combo)

        self.escala_custom = QSpinBox()
        self.escala_custom.setRange(500, 500000)
        self.escala_custom.setValue(4000)
        self.escala_custom.setSuffix('  (denominador)')
        self.escala_custom.setVisible(False)
        form.addRow('Valor personalizado:', self.escala_custom)

        self.folha_combo = QComboBox()
        for nome, _, _ in FOLHAS:
            self.folha_combo.addItem(nome)
        self.folha_combo.setCurrentIndex(1)
        self.folha_combo.currentIndexChanged.connect(self._atualizar_preview)
        form.addRow('Tamanho da Folha:', self.folha_combo)

        self.orientacao_combo = QComboBox()
        self.orientacao_combo.addItems(['Paisagem', 'Retrato'])
        self.orientacao_combo.currentIndexChanged.connect(
            self._atualizar_preview)
        form.addRow('Orientação:', self.orientacao_combo)

        self.preview_label = QLabel()
        self.preview_label.setStyleSheet('color: #555; font-style: italic;')
        form.addRow('Área no terreno:', self.preview_label)

        self.decl_label = QLabel()
        self.decl_label.setWordWrap(True)
        self.decl_label.setStyleSheet('color: #555; font-style: italic;')
        form.addRow('Declinação magnética:', self.decl_label)

        self.decl_manual_check = QCheckBox('Informar manualmente')
        self.decl_manual_spin = QDoubleSpinBox()
        self.decl_manual_spin.setRange(-90.0, 90.0)
        self.decl_manual_spin.setDecimals(2)
        self.decl_manual_spin.setSingleStep(0.1)
        self.decl_manual_spin.setSuffix('°  (leste +, oeste −)')
        self.decl_manual_spin.setEnabled(False)
        self.decl_manual_check.toggled.connect(
            self.decl_manual_spin.setEnabled)
        self.decl_manual_check.toggled.connect(self._atualizar_declinacao)
        form.addRow(self.decl_manual_check, self.decl_manual_spin)
        self.coord_input.textChanged.connect(self._atualizar_declinacao)

        botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                  QDialogButtonBox.StandardButton.Cancel)
        botoes.button(
            QDialogButtonBox.StandardButton.Ok).setText('Criar Folha')
        botoes.button(
            QDialogButtonBox.StandardButton.Cancel).setText('Cancelar')
        botoes.accepted.connect(self._definir)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)

        montar_com_painel(self, layout, 'Definir Local e Criar Folha',
                          INSTRUCOES['definir_local'])

        self._aplicar_padroes()
        self._selecionar_tipo_inicial()
        self.tipo_combo.currentIndexChanged.connect(self._aplicar_tipo)
        self._atualizar_preview()
        self._prefill_coord_do_canvas()
        self._atualizar_declinacao()

    def _aplicar_padroes(self) -> None:
        """Pré-seleciona escala/folha/orientação a partir das Configurações."""
        try:
            from .configuracoes import (ler_escala_padrao, ler_folha_padrao,
                                        ler_orientacao_padrao)
        except Exception:
            return
        padrao = ler_escala_padrao()
        for i, (_, val) in enumerate(ESCALAS):
            if val == padrao:
                self.escala_combo.setCurrentIndex(i)
                break
        else:
            self.escala_combo.setCurrentIndex(len(ESCALAS) - 1)
            self.escala_custom.setValue(padrao)
        nomes = [nome for nome, _, _ in FOLHAS]
        folha = ler_folha_padrao()
        if folha in nomes:
            self.folha_combo.setCurrentIndex(nomes.index(folha))
        self.orientacao_combo.setCurrentIndex(
            1 if ler_orientacao_padrao() == 'Retrato' else 0)

    def tipo(self):
        """``TipoMapa`` selecionado."""
        return tipo_por_id(self.tipo_combo.currentData())

    def _selecionar_tipo_inicial(self) -> None:
        """Pré-seleciona o último tipo usado (Personalizado se nenhum) e,
        se ele tiver predefinição, já preenche escala e papel."""
        try:
            from .configuracoes import ler_tipo_mapa_ultimo
            ultimo = ler_tipo_mapa_ultimo()
        except Exception:
            ultimo = PERSONALIZADO
        indice = self.tipo_combo.findData(ultimo)
        self.tipo_combo.setCurrentIndex(
            indice if indice >= 0 else self.tipo_combo.findData(PERSONALIZADO))
        self._aplicar_tipo()

    def _aplicar_tipo(self) -> None:
        """Preenche escala e papel com a predefinição do tipo (a orientação
        fica como está). Os campos continuam editáveis; o tipo segue
        valendo para a norma e a equidistância dos passos seguintes."""
        tipo = self.tipo()
        self.tipo_resumo.setText(resumo(tipo))
        if not tem_predefinicao(tipo):
            return
        for i, (_, valor) in enumerate(ESCALAS):
            if valor == tipo.escala:
                self.escala_combo.setCurrentIndex(i)
                break
        else:
            self.escala_combo.setCurrentIndex(len(ESCALAS) - 1)
            self.escala_custom.setValue(tipo.escala)
        nomes = [nome for nome, _, _ in FOLHAS]
        self.folha_combo.setCurrentIndex(nomes.index(tipo.papel))

    def _prefill_coord_do_canvas(self) -> None:
        """Pré-preenche o campo com o centro da vista atual (em Lat,Lon)."""
        canvas = self.iface.mapCanvas()
        ext = canvas.extent()
        if ext.isNull() or ext.isEmpty():
            return
        src = canvas.mapSettings().destinationCrs()
        if not src.isValid():
            return
        crs_wgs = QgsCoordinateReferenceSystem.fromEpsgId(4326)
        try:
            pt = QgsCoordinateTransform(
                src, crs_wgs, QgsProject.instance()).transform(ext.center())
            self.coord_input.setText(f'{pt.y():.6f}, {pt.x():.6f}')
        except Exception:  # nosec B110 - preencher coordenada é best-effort
            pass

    def _on_escala_changed(self, idx: int) -> None:
        """Exibe ou oculta o campo de escala personalizada.

        Args:
            idx: Índice selecionado no combo de escalas.
        """
        self.escala_custom.setVisible(ESCALAS[idx][1] == -1)
        self._atualizar_preview()

    def _escala_valor(self) -> int:
        """Obtém denominador da escala atualmente selecionada.

        Returns:
            int: Denominador da escala padrão ou personalizada.
        """
        idx = self.escala_combo.currentIndex()
        val = ESCALAS[idx][1]
        return self.escala_custom.value() if val == -1 else val

    def _dimensoes_mm(self) -> Tuple[int, int]:
        """Largura/altura da folha em mm, já aplicada a orientação."""
        _, larg_mm, alt_mm = FOLHAS[self.folha_combo.currentIndex()]
        if self.orientacao_combo.currentIndex() == 1:
            larg_mm, alt_mm = alt_mm, larg_mm
        return larg_mm, alt_mm

    def _atualizar_preview(self) -> None:
        """Atualiza texto de área real da folha no terreno.
        """
        escala = self._escala_valor()
        larg_mm, alt_mm = self._dimensoes_mm()
        self.preview_label.setText(
            f'{(larg_mm / 1000.0) * escala:.0f} m × {(alt_mm / 1000.0) * escala:.0f} m')

    def _declinacao_wmm(self, lat: float, lon: float) -> Tuple[float, bool]:
        """Declinação de hoje pelo WMM offline: (graus, dentro_da_validade)."""
        return declinacao_wmm(lat, lon, datetime.date.today())

    def _atualizar_declinacao(self) -> None:
        """Mostra a declinação calculada para a coordenada digitada.

        Enquanto o modo manual está desligado, o campo manual acompanha o
        valor calculado — ao ligar, a pessoa parte do valor do modelo.
        """
        if self.decl_manual_check.isChecked():
            self.decl_label.setText(
                'Valor manual — a folha será girada com ele.')
            return
        coord = ler_coordenada(self.coord_input.text())
        if coord is None:
            self.decl_label.setText('Informe a coordenada para calcular.')
            return
        valor, valido = self._declinacao_wmm(*coord)
        self.decl_manual_spin.setValue(round(valor, 2))
        texto = (f'{_graus(valor)} ({"oeste" if valor < 0 else "leste"}) — '
                 'modelo WMM, calculada sem internet.')
        if not valido:
            texto += (' Atenção: o modelo embutido está vencido; confira o '
                      'valor e atualize o plugin.')
        self.decl_label.setText(texto)

    def _declinacao_escolhida(self, lat: float, lon: float) -> Tuple[float, str]:
        """(declinação em graus, origem) que vai girar a folha."""
        if self.decl_manual_check.isChecked():
            return self.decl_manual_spin.value(), 'manual'
        valor, _ = self._declinacao_wmm(lat, lon)
        hoje = datetime.date.today().strftime('%d/%m/%Y')
        return valor, f'WMM em {hoje}'

    def _definir(self) -> None:
        """Valida entrada, define CRS UTM e cria a camada de folha girada.

        A escolha de EPSG UTM WGS84 segue regra de negócio do plugin para manter
        compatibilidade da exportação OCAD/OOM, que depende desse sistema. A
        folha é girada pela grivação (declinação − convergência meridiana)
        para ficar em pé no papel do OCAD/OOM, que é orientado ao norte
        magnético.
        """
        coord = ler_coordenada(self.coord_input.text())
        if coord is None:
            self.iface.messageBar().pushMessage(
                'OrIFSC',
                'Informe a coordenada no formato Lat, Lon (latitude entre -90 '
                'e 90, longitude entre -180 e 180). Exemplo: -27.5926, '
                '-48.5431.',
                level=Qgis.MessageLevel.Warning,
                duration=6)
            return
        lat, lon = coord

        escala = self._escala_valor()
        larg_mm, alt_mm = self._dimensoes_mm()

        fuso = int((lon + 180) / 6) + 1
        epsg = 32600 + fuso if lat >= 0 else 32700 + fuso

        crs_wgs = QgsCoordinateReferenceSystem.fromEpsgId(4326)
        crs_utm = QgsCoordinateReferenceSystem.fromEpsgId(epsg)
        pt_utm = QgsCoordinateTransform(crs_wgs, crs_utm, QgsProject.instance()).transform(
            QgsPointXY(lon, lat))

        declinacao, origem = self._declinacao_escolhida(lat, lon)

        QgsProject.instance().setCrs(crs_utm)
        self.iface.mapCanvas().setDestinationCrs(crs_utm)
        from .criar_folha import aplicar_folha
        from .comum import salvar_tipo_mapa
        salvar_tipo_mapa(self.tipo().id)
        try:
            from .configuracoes import salvar_tipo_mapa_ultimo
            salvar_tipo_mapa_ultimo(self.tipo().id)
        except Exception:  # nosec B110 - lembrar o tipo é conveniência
            pass
        info = aplicar_folha(self.iface, epsg, pt_utm.x(), pt_utm.y(),
                             larg_mm, alt_mm, escala, declinacao, origem,
                             parent=self)
        self.iface.messageBar().pushMessage(
            'OrIFSC', mensagem_orientacao(info),
            level=Qgis.MessageLevel.Info, duration=8)

        self.accept()
