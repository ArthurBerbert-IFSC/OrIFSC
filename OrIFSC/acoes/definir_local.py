"""Definir Local e Criar Folha.

Diálogo que pede a coordenada (Google Maps), escala e folha; configura o
projeto em UTM, guarda o retângulo da folha para os passos seguintes e já cria
a camada 'folha'. O campo de coordenada vem pré-preenchido com o centro da
vista atual (o satélite do Passo 1 já está carregado) e continua editável.
"""
from qgis.core import (
    QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsPointXY,
    QgsProject,
)
from qgis.PyQt.QtWidgets import (
    QDialog, QFormLayout, QVBoxLayout,
    QLabel, QLineEdit, QComboBox, QSpinBox,
    QDialogButtonBox, QMessageBox,
)

from .comum import salvar_folha, salvar_escala
from .painel import montar_com_painel, INSTRUCOES

ESCALAS = [
    ('1:4.000', 4000),
    ('1:5.000', 5000),
    ('1:7.500', 7500),
    ('1:10.000', 10000),
    ('1:15.000', 15000),
    ('Personalizada...', -1),
]

FOLHAS = [('A3', 420, 297), ('A4', 297, 210), ('A5', 210, 148)]


class DialogDefinirLocal(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle('OrIFSC — Definir Local e Criar Folha')
        self.setMinimumWidth(400)

        layout = QVBoxLayout()
        form = QFormLayout()
        layout.addLayout(form)

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
        self.folha_combo.setCurrentIndex(1)  # A4 padrão
        self.folha_combo.currentIndexChanged.connect(self._atualizar_preview)
        form.addRow('Tamanho da Folha:', self.folha_combo)

        self.orientacao_combo = QComboBox()
        self.orientacao_combo.addItems(['Paisagem', 'Retrato'])
        self.orientacao_combo.currentIndexChanged.connect(self._atualizar_preview)
        form.addRow('Orientação:', self.orientacao_combo)

        self.preview_label = QLabel()
        self.preview_label.setStyleSheet('color: #555; font-style: italic;')
        form.addRow('Área no terreno:', self.preview_label)

        botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                  QDialogButtonBox.StandardButton.Cancel)
        botoes.button(QDialogButtonBox.StandardButton.Ok).setText('Criar Folha')
        botoes.button(QDialogButtonBox.StandardButton.Cancel).setText('Cancelar')
        botoes.accepted.connect(self._definir)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)

        montar_com_painel(self, layout, 'Definir Local e Criar Folha',
                          INSTRUCOES['definir_local'])

        self._aplicar_padroes()
        self._atualizar_preview()
        self._prefill_coord_do_canvas()

    def _aplicar_padroes(self):
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
            self.escala_combo.setCurrentIndex(len(ESCALAS) - 1)  # Personalizada...
            self.escala_custom.setValue(padrao)
        nomes = [nome for nome, _, _ in FOLHAS]
        folha = ler_folha_padrao()
        if folha in nomes:
            self.folha_combo.setCurrentIndex(nomes.index(folha))
        self.orientacao_combo.setCurrentIndex(
            1 if ler_orientacao_padrao() == 'Retrato' else 0)

    def _prefill_coord_do_canvas(self):
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
        except Exception:
            pass

    def _on_escala_changed(self, idx):
        self.escala_custom.setVisible(ESCALAS[idx][1] == -1)
        self._atualizar_preview()

    def _escala_valor(self):
        idx = self.escala_combo.currentIndex()
        val = ESCALAS[idx][1]
        return self.escala_custom.value() if val == -1 else val

    def _dimensoes_mm(self):
        """Largura/altura da folha em mm, já aplicada a orientação."""
        _, larg_mm, alt_mm = FOLHAS[self.folha_combo.currentIndex()]
        if self.orientacao_combo.currentIndex() == 1:  # Retrato
            larg_mm, alt_mm = alt_mm, larg_mm
        return larg_mm, alt_mm

    def _atualizar_preview(self):
        escala = self._escala_valor()
        larg_mm, alt_mm = self._dimensoes_mm()
        self.preview_label.setText(
            f'{(larg_mm / 1000.0) * escala:.0f} m × {(alt_mm / 1000.0) * escala:.0f} m')

    def _definir(self):
        txt = self.coord_input.text().strip()
        try:
            partes = txt.replace(' ', '').split(',')
            lat = float(partes[0])
            lon = float(partes[1])
        except Exception:
            QMessageBox.warning(self, 'Coordenada inválida',
                                'Use o formato do Google Maps: Lat, Lon\n'
                                'Ex: -27.5926, -48.5431')
            return

        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            QMessageBox.warning(self, 'Coordenada fora do intervalo',
                                f'Latitude deve estar entre -90 e 90 (recebido: {lat}).\n'
                                f'Longitude deve estar entre -180 e 180 (recebido: {lon}).\n'
                                'Verifique o formato: Lat, Lon')
            return

        escala = self._escala_valor()
        larg_mm, alt_mm = self._dimensoes_mm()

        fuso = int((lon + 180) / 6) + 1
        epsg = 32600 + fuso if lat >= 0 else 32700 + fuso

        crs_wgs = QgsCoordinateReferenceSystem.fromEpsgId(4326)
        crs_utm = QgsCoordinateReferenceSystem.fromEpsgId(epsg)
        pt_utm = QgsCoordinateTransform(crs_wgs, crs_utm, QgsProject.instance()).transform(
            QgsPointXY(lon, lat))

        larg_m = (larg_mm / 1000.0) * escala
        alt_m = (alt_mm / 1000.0) * escala
        x0 = pt_utm.x() - larg_m / 2
        y0 = pt_utm.y() - alt_m / 2
        x1 = pt_utm.x() + larg_m / 2
        y1 = pt_utm.y() + alt_m / 2

        QgsProject.instance().setCrs(crs_utm)
        salvar_folha(epsg, x0, y0, x1, y1)
        salvar_escala(escala)

        # Garante reprojeção on-the-fly do satélite (3857 → UTM) antes de criar
        # a folha; criar_folha já centraliza o canvas e ativa a camada.
        self.iface.mapCanvas().setDestinationCrs(crs_utm)
        from .criar_folha import criar_folha
        criar_folha(self.iface, self)

        self.accept()
