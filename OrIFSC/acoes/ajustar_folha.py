"""Ajustar Folha: mover a folha no mapa, trocar escala, papel e orientação,
ou encaixar a folha num limite.

Diálogo não modal com prévia ao vivo: um contorno laranja mostra no mapa a
folha que vai ficar (sempre girada para o norte magnético). "Mover no mapa…"
ativa uma ferramenta em que o contorno segue o mouse; um clique fixa o novo
centro. "Ajustar ao limite" calcula papel, orientação e centro que contêm uma
camada de polígono (``folha.ajustar_ao_limite``). Ao aplicar, a camada 'folha'
existente é atualizada (sem duplicar) e o estado do projeto é regravado por
``criar_folha.aplicar_folha``.
"""
from typing import Any, Callable, Dict, List, Optional, Tuple

from qgis.core import (
    QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsGeometry,
    QgsPointXY, QgsProject, Qgis,
)
from qgis.gui import QgsMapTool, QgsRubberBand
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (
    QDialog, QFormLayout, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QSpinBox, QPushButton, QDialogButtonBox, QMessageBox,
)

from ..algorithms.ocad.folha import (
    PAPEIS, ajustar_ao_limite, area_terreno_m, dimensoes_papel,
    escala_sugerida, identificar_papel,
)
from ..algorithms.ocad.geo import cantos_folha
from .comum import (camadas_poligono, ler_escala, ler_folha,
                    ler_folha_girada, tem_camada_curvas)
from .criar_folha import aplicar_folha, calcular_orientacao, camada_folha
from .definir_local import ESCALAS, _graus, mensagem_orientacao
from .painel import montar_com_painel, INSTRUCOES

COR_PREVIA = QColor(241, 89, 42)   # laranja-picota do painel


def _banda(canvas: Any) -> QgsRubberBand:
    """Contorno tracejado laranja, sem preenchimento."""
    banda = QgsRubberBand(canvas, Qgis.GeometryType.Polygon)
    banda.setStrokeColor(COR_PREVIA)
    banda.setFillColor(QColor(0, 0, 0, 0))
    banda.setWidth(2)
    banda.setLineStyle(Qt.PenStyle.DashLine)
    return banda


def _milhar(valor: int) -> str:
    """4000 → '4.000' (separador de milhar pt-BR)."""
    return f'{int(valor):,}'.replace(',', '.')


def _geometria(cantos) -> QgsGeometry:
    anel = [QgsPointXY(e, n) for e, n in cantos]
    return QgsGeometry.fromPolygonXY([anel + [anel[0]]])


class FerramentaPosicionarFolha(QgsMapTool):
    """O contorno da folha segue o mouse; clique esquerdo fixa o centro.

    Botão direito ou Esc cancela. As coordenadas do mouse são levadas para o
    CRS da folha (a vista pode estar em outro sistema).
    """

    def __init__(self, canvas: Any, crs_folha: QgsCoordinateReferenceSystem,
                 desenhar: Callable[[QgsPointXY], Any],
                 ao_posicionar: Callable[[QgsPointXY], None],
                 ao_cancelar: Callable[[], None]) -> None:
        super().__init__(canvas)
        self.crs_folha = crs_folha
        self.desenhar = desenhar
        self.ao_posicionar = ao_posicionar
        self.ao_cancelar = ao_cancelar
        self.setCursor(Qt.CursorShape.CrossCursor)

    def _ponto_folha(self, evento: Any) -> QgsPointXY:
        crs_vista = self.canvas().mapSettings().destinationCrs()
        ponto = evento.mapPoint()
        if crs_vista == self.crs_folha:
            return QgsPointXY(ponto)
        tr = QgsCoordinateTransform(crs_vista, self.crs_folha,
                                    QgsProject.instance())
        return tr.transform(QgsPointXY(ponto))

    def canvasMoveEvent(self, evento: Any) -> None:
        self.desenhar(self._ponto_folha(evento))

    def canvasReleaseEvent(self, evento: Any) -> None:
        if evento.button() == Qt.MouseButton.LeftButton:
            self.ao_posicionar(self._ponto_folha(evento))
        elif evento.button() == Qt.MouseButton.RightButton:
            self.ao_cancelar()

    def keyPressEvent(self, evento: Any) -> None:
        if evento.key() == Qt.Key.Key_Escape:
            self.ao_cancelar()


class DialogAjustarFolha(QDialog):
    """Ajusta centro, escala, papel e orientação da folha com prévia."""

    def __init__(self, iface: Any, parent: Any = None) -> None:
        super().__init__(parent)
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.setWindowTitle('OrIFSC — Ajustar Folha')
        self.setMinimumWidth(420)

        estado = self._estado_atual()
        self.epsg = estado['epsg']
        self.crs_folha = QgsCoordinateReferenceSystem.fromEpsgId(self.epsg)
        self.original = (estado['ref_e'], estado['ref_n'], estado['larg_mm'],
                         estado['alt_mm'], estado['escala'])
        self.ref_e, self.ref_n = estado['ref_e'], estado['ref_n']
        self.orientacao = calcular_orientacao(self.epsg, self.ref_e,
                                              self.ref_n)
        self._ferramenta: Optional[FerramentaPosicionarFolha] = None
        self._ferramenta_anterior = None

        layout = QVBoxLayout()
        form = QFormLayout()
        layout.addLayout(form)

        self.escala_combo = QComboBox()
        for rotulo, _ in ESCALAS:
            self.escala_combo.addItem(rotulo)
        self.escala_custom = QSpinBox()
        self.escala_custom.setRange(500, 500000)
        self.escala_custom.setSuffix('  (denominador)')
        form.addRow('Escala:', self.escala_combo)
        form.addRow('Valor personalizado:', self.escala_custom)

        self.papel_combo = QComboBox()
        for nome, _, _ in PAPEIS:
            self.papel_combo.addItem(nome)
        form.addRow('Tamanho da Folha:', self.papel_combo)

        self.orientacao_combo = QComboBox()
        self.orientacao_combo.addItems(['Paisagem', 'Retrato'])
        form.addRow('Orientação:', self.orientacao_combo)

        self.area_label = QLabel()
        self.area_label.setStyleSheet('color: #555; font-style: italic;')
        form.addRow('Área no terreno:', self.area_label)

        linha_centro = QHBoxLayout()
        self.centro_label = QLabel()
        self.centro_label.setStyleSheet('color: #555;')
        botao_mover = QPushButton('Mover no mapa…')
        botao_mover.clicked.connect(self._iniciar_mover)
        linha_centro.addWidget(self.centro_label, 1)
        linha_centro.addWidget(botao_mover)
        form.addRow('Centro da folha:', linha_centro)

        self.orientacao_label = QLabel()
        self.orientacao_label.setWordWrap(True)
        self.orientacao_label.setStyleSheet('color: #555; font-style: italic;')
        form.addRow('Norte magnético:', self.orientacao_label)

        linha_limite = QHBoxLayout()
        self.limite_combo = QComboBox()
        self.botao_limite = QPushButton('Ajustar')
        self.botao_limite.clicked.connect(self.ajustar_ao_limite)
        linha_limite.addWidget(self.limite_combo, 1)
        linha_limite.addWidget(self.botao_limite)
        form.addRow('Ajustar ao limite:', linha_limite)
        self._preencher_limites()

        botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                  QDialogButtonBox.StandardButton.Cancel)
        botoes.button(QDialogButtonBox.StandardButton.Ok).setText('Aplicar')
        botoes.button(
            QDialogButtonBox.StandardButton.Cancel).setText('Cancelar')
        botoes.accepted.connect(self._aplicar)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)

        montar_com_painel(self, layout, 'Ajustar Folha',
                          INSTRUCOES['ajustar_folha'])

        self._preencher(estado)
        self.escala_combo.currentIndexChanged.connect(self._mudou_escala)
        self.escala_custom.valueChanged.connect(self._atualizar_previa)
        self.papel_combo.currentIndexChanged.connect(self._atualizar_previa)
        self.orientacao_combo.currentIndexChanged.connect(
            self._atualizar_previa)

        self.banda = _banda(self.canvas)
        self._atualizar_previa()

    # ------------------------------------------------------------- estado
    @staticmethod
    def _estado_atual() -> Dict[str, Any]:
        """Folha salva no projeto; projetos da 0.1.x são convertidos a partir
        do retângulo envolvente (o ajuste passa a girar a folha)."""
        girada = ler_folha_girada()
        if girada is not None:
            return girada
        epsg, x0, y0, x1, y1 = ler_folha()
        escala = ler_escala() or 4000
        return {
            'epsg': epsg,
            'ref_e': (x0 + x1) / 2.0,
            'ref_n': (y0 + y1) / 2.0,
            'larg_mm': (x1 - x0) * 1000.0 / escala,
            'alt_mm': (y1 - y0) * 1000.0 / escala,
            'escala': escala,
        }

    def _preencher(self, estado: Dict[str, Any]) -> None:
        escala = int(round(estado['escala']))
        for i, (_, valor) in enumerate(ESCALAS):
            if valor == escala:
                self.escala_combo.setCurrentIndex(i)
                break
        else:
            self.escala_combo.setCurrentIndex(len(ESCALAS) - 1)
        self.escala_custom.setValue(escala)
        self.escala_custom.setVisible(
            ESCALAS[self.escala_combo.currentIndex()][1] == -1)

        papel = identificar_papel(estado['larg_mm'], estado['alt_mm'])
        nome, retrato = papel if papel else (
            'A4', estado['alt_mm'] > estado['larg_mm'])
        self.papel_combo.setCurrentIndex([p[0] for p in PAPEIS].index(nome))
        self.orientacao_combo.setCurrentIndex(1 if retrato else 0)

    def _preencher_limites(self) -> None:
        """Camadas de polígono que podem servir de limite (menos a folha);
        pré-seleciona a que se chama 'limite'."""
        folha = camada_folha()
        camadas = [c for c in camadas_poligono()
                   if folha is None or c.id() != folha.id()]
        self.limite_combo.clear()
        for c in camadas:
            self.limite_combo.addItem(c.name(), c.id())
        nomes = [c.name().lower() for c in camadas]
        for i, nome in enumerate(nomes):
            if 'limite' in nome:
                self.limite_combo.setCurrentIndex(i)
                break
        tem = bool(camadas)
        self.limite_combo.setEnabled(tem)
        self.botao_limite.setEnabled(tem)
        if not tem:
            self.limite_combo.addItem('(nenhuma camada de polígono)')
            self.botao_limite.setToolTip(
                'Desenhe o limite em Início → Camada de Limite ou importe '
                'um KML com o contorno da área.')

    def _pontos_limite(self, camada: Any) -> List[Tuple[float, float]]:
        """Vértices do limite no CRS da folha (só as feições selecionadas,
        se houver seleção)."""
        tr = None
        if camada.crs() != self.crs_folha:
            tr = QgsCoordinateTransform(camada.crs(), self.crs_folha,
                                        QgsProject.instance())
        feicoes = (camada.getSelectedFeatures() if camada.selectedFeatureCount()
                   else camada.getFeatures())
        pontos = []
        for f in feicoes:
            geom = QgsGeometry(f.geometry())
            if geom.isEmpty():
                continue
            if tr is not None:
                geom.transform(tr)
            pontos.extend((v.x(), v.y()) for v in geom.vertices())
        return pontos

    def _definir_escala(self, escala: int) -> None:
        for i, (_, valor) in enumerate(ESCALAS):
            if valor == escala:
                self.escala_combo.setCurrentIndex(i)
                return
        self.escala_combo.setCurrentIndex(len(ESCALAS) - 1)
        self.escala_custom.setValue(escala)

    def ajustar_ao_limite(self) -> None:
        """Encaixa a folha na camada de limite escolhida (com 5 mm de folga).

        Aumenta o papel se preciso, nunca muda a escala sozinho: se nem o
        maior papel couber, pergunta se pode usar a escala que caberia.
        """
        camada = QgsProject.instance().mapLayer(
            self.limite_combo.currentData() or '')
        pontos = self._pontos_limite(camada) if camada is not None else []
        if not pontos:
            self.iface.messageBar().pushMessage(
                'OrIFSC', 'A camada de limite escolhida não tem polígonos.',
                level=Qgis.MessageLevel.Warning, duration=6)
            return
        escala = self._escala()
        centro_e = (min(e for e, _ in pontos) + max(e for e, _ in pontos)) / 2
        centro_n = (min(n for _, n in pontos) + max(n for _, n in pontos)) / 2
        griv = calcular_orientacao(self.epsg, centro_e, centro_n)['grivacao']
        papel = self.papel_combo.currentText()
        ajuste = ajustar_ao_limite(pontos, escala, griv, papel)
        if not ajuste.cabe:
            sugerida = escala_sugerida(
                ajuste.escala_minima, [v for _, v in ESCALAS if v > 0])
            resposta = QMessageBox.question(
                self, 'OrIFSC — Ajustar ao limite',
                f'O limite não cabe numa folha {ajuste.papel} na escala '
                f'1:{_milhar(escala)}, nem com o papel maior.\n\nEle caberia '
                f'em {ajuste.papel} na escala 1:{_milhar(sugerida)}. Lembre que '
                'a escala de competição é definida pela norma.\n\nUsar '
                f'1:{_milhar(sugerida)}?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if resposta != QMessageBox.StandardButton.Yes:
                return
            self._definir_escala(sugerida)
            ajuste = ajustar_ao_limite(pontos, sugerida, griv, papel)
            if not ajuste.cabe:
                return
        self.papel_combo.setCurrentIndex(
            [p[0] for p in PAPEIS].index(ajuste.papel))
        self.orientacao_combo.setCurrentIndex(1 if ajuste.retrato else 0)
        self.ref_e, self.ref_n = ajuste.ref_e, ajuste.ref_n
        self.orientacao = calcular_orientacao(self.epsg, self.ref_e,
                                              self.ref_n)
        self._atualizar_previa()
        escala_fmt = _milhar(self._escala())
        self.iface.messageBar().pushMessage(
            'OrIFSC',
            f'Folha encaixada no limite: {ajuste.papel} '
            f'{"retrato" if ajuste.retrato else "paisagem"}, escala '
            f'1:{escala_fmt}. Confira o contorno laranja e clique em '
            'Aplicar.',
            level=Qgis.MessageLevel.Info, duration=8)

    def _escala(self) -> int:
        valor = ESCALAS[self.escala_combo.currentIndex()][1]
        return self.escala_custom.value() if valor == -1 else valor

    def _dimensoes(self) -> Tuple[float, float]:
        return dimensoes_papel(self.papel_combo.currentText(),
                               self.orientacao_combo.currentIndex() == 1)

    def candidata(self) -> Tuple[float, float, float, float, int]:
        """(ref_e, ref_n, larg_mm, alt_mm, escala) da folha que vai ficar."""
        larg_mm, alt_mm = self._dimensoes()
        return self.ref_e, self.ref_n, larg_mm, alt_mm, self._escala()

    # -------------------------------------------------------------- prévia
    def _mudou_escala(self, idx: int) -> None:
        self.escala_custom.setVisible(ESCALAS[idx][1] == -1)
        self._atualizar_previa()

    def _desenhar(self, ref_e: float, ref_n: float) -> None:
        _, _, larg_mm, alt_mm, escala = self.candidata()
        cantos = cantos_folha(ref_e, ref_n, larg_mm, alt_mm, escala,
                              self.orientacao['grivacao'])
        self.banda.setToGeometry(_geometria(cantos), self.crs_folha)

    def _atualizar_previa(self) -> None:
        ref_e, ref_n, larg_mm, alt_mm, escala = self.candidata()
        larg_m, alt_m = area_terreno_m(larg_mm, alt_mm, escala)
        self.area_label.setText(f'{larg_m:.0f} m × {alt_m:.0f} m')
        self.centro_label.setText(
            f'{ref_e:,.0f} E · {ref_n:,.0f} N'.replace(',', '.'))
        o = self.orientacao
        self.orientacao_label.setText(
            f'declinação {_graus(o["declinacao"])} ({o["origem"]}) · folha '
            f'girada {_graus(o["grivacao"])}')
        self._desenhar(ref_e, ref_n)

    # ---------------------------------------------------------------- mover
    def _iniciar_mover(self) -> None:
        self._ferramenta_anterior = self.canvas.mapTool()
        self._ferramenta = FerramentaPosicionarFolha(
            self.canvas, self.crs_folha,
            lambda p: self._desenhar(p.x(), p.y()),
            self._posicionado, self._cancelou_mover)
        self.canvas.setMapTool(self._ferramenta)
        self.hide()
        self.iface.messageBar().pushMessage(
            'OrIFSC', 'Clique no mapa para fixar o centro da folha '
            '(botão direito ou Esc cancela).',
            level=Qgis.MessageLevel.Info, duration=5)

    def _encerrar_mover(self) -> None:
        if self._ferramenta is None:
            return
        if self._ferramenta_anterior is not None:
            self.canvas.setMapTool(self._ferramenta_anterior)
        else:
            self.canvas.unsetMapTool(self._ferramenta)
        self._ferramenta = None
        self._ferramenta_anterior = None

    def _posicionado(self, ponto: QgsPointXY) -> None:
        self._encerrar_mover()
        self.ref_e, self.ref_n = ponto.x(), ponto.y()
        # Declinação e convergência do novo lugar (valor manual é mantido).
        self.orientacao = calcular_orientacao(self.epsg, self.ref_e,
                                              self.ref_n)
        self._atualizar_previa()
        self._reabrir()

    def _cancelou_mover(self) -> None:
        self._encerrar_mover()
        self._atualizar_previa()
        self._reabrir()

    def _reabrir(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    # -------------------------------------------------------------- aplicar
    def mudou(self) -> bool:
        """True se a folha candidata difere da salva no projeto."""
        atual = self.candidata()
        return any(abs(a - b) > 1e-6 for a, b in zip(atual, self.original))

    def _aplicar(self) -> None:
        if not self.mudou():
            self.accept()
            return
        ref_e, ref_n, larg_mm, alt_mm, escala = self.candidata()
        info = aplicar_folha(
            self.iface, self.epsg, ref_e, ref_n, larg_mm, alt_mm, escala,
            self.orientacao['declinacao'], self.orientacao['origem'],
            parent=self, enquadrar=False)
        mensagem = 'Folha ajustada. ' + mensagem_orientacao(info)
        if tem_camada_curvas():
            mensagem += (' Se você já gerou curvas ou exportou o projeto, '
                         'refaça essas etapas para a nova folha.')
        self.iface.messageBar().pushMessage(
            'OrIFSC', mensagem, level=Qgis.MessageLevel.Info, duration=10)
        self.accept()

    def done(self, resultado: int) -> None:
        """Fecha limpando a prévia e devolvendo a ferramenta anterior."""
        self._encerrar_mover()
        if self.banda is not None:
            self.banda.reset(Qgis.GeometryType.Polygon)
            self.canvas.scene().removeItem(self.banda)
            self.banda = None
        super().done(resultado)
