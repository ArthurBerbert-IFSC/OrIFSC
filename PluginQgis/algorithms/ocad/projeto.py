"""Modelo comum aos dois escritores (.omap e .ocd).

`ProjetoOcad` resolve a georreferência (UTM + escala + declinação) e converte as
curvas do mundo (UTM, metros) para coordenadas de papel do mapa, usando o MESMO
`QTransform` que o OpenOrienteering Mapper monta em `Georeferencing` — assim os
dois formatos saem com geometria idêntica e sem erro de sinal de rotação.

Coordenadas de papel ficam em **mm com y para baixo** (convenção do OOM); cada
escritor depois aplica suas unidades (OOM: 1/1000 mm; OCD: 1/100 mm, y para cima).
"""
from qgis.core import (
    QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsPointXY,
    QgsProject,
)
from qgis.PyQt.QtCore import QPointF
from qgis.PyQt.QtGui import QTransform

from .geo import (
    convergencia_utm, codigo_grade_zona, meridiano_central, zona_utm_de_epsg,
)

# Símbolo de curva embutido (curva mestra/intermediária genérica).
COR_CURVA = (0.0, 0.56, 1.0, 0.18)   # CMYK (fração) — marrom de curva de nível
COR_NOME = 'Marrom (curvas)'
LARGURA_CURVA_UM = 140               # 0,14 mm em 1/1000 mm
CODIGO_SIMBOLO = 101                 # "101" — curva de nível (ISOM)


def centro_latlon(epsg, e, n):
    """Latitude/longitude (graus) de um ponto UTM."""
    crs_utm = QgsCoordinateReferenceSystem.fromEpsgId(epsg)
    crs_wgs = QgsCoordinateReferenceSystem.fromEpsgId(4326)
    tr = QgsCoordinateTransform(crs_utm, crs_wgs, QgsProject.instance())
    pt = tr.transform(QgsPointXY(e, n))
    return pt.y(), pt.x()


class ProjetoOcad:
    """Reúne tudo que os escritores precisam para gerar o projeto."""

    def __init__(self, escala, epsg, folha_rect, declinacao, linhas_mundo,
                 satelite=None):
        self.escala = int(escala)
        self.epsg = int(epsg)
        self.zona, self.sul = zona_utm_de_epsg(self.epsg)
        self.proj4 = ('+proj=utm +zone={z}{s} +datum=WGS84 +units=m +no_defs'
                      .format(z=self.zona, s=' +south' if self.sul else ''))
        self.crs_param = '{z} {h}'.format(z=self.zona, h='S' if self.sul else 'N')
        self.i_grade = codigo_grade_zona(self.epsg)

        x0, y0, x1, y1 = folha_rect
        self.ref_e = (x0 + x1) / 2.0
        self.ref_n = (y0 + y1) / 2.0
        self.lat, self.lon = centro_latlon(self.epsg, self.ref_e, self.ref_n)

        self.declinacao = float(declinacao)
        self.convergencia = convergencia_utm(
            self.lat, self.lon, meridiano_central(self.zona))
        # Grivação = declinação − convergência (magnético em relação à grade),
        # igual ao OOM. É o ângulo `a` do OCD e o `grivation` do .omap.
        self.grivacao = self.declinacao - self.convergencia

        # Transform mapa(mm)→mundo, idêntico a Georeferencing::updateTransformation.
        t = QTransform()
        t.translate(self.ref_e, self.ref_n)
        t.rotate(-self.grivacao)
        s = self.escala / 1000.0
        t.scale(s, -s)
        # map_ref_point = (0,0): translate(-0,-0) omitido.
        self._para_mapa, ok = t.inverted()
        if not ok:
            raise ValueError('Transform de georreferência não inversível.')

        self.cor = COR_CURVA
        self.cor_nome = COR_NOME
        self.largura_um = LARGURA_CURVA_UM
        self.codigo_simbolo = CODIGO_SIMBOLO

        # Converte as curvas para mm de papel (y para baixo).
        self.linhas_mm = [
            [self.mapa_mm(e, n) for (e, n) in linha]
            for linha in linhas_mundo if len(linha) >= 2
        ]

        self.satelite = self._preparar_satelite(satelite)

    def mapa_mm(self, e, n):
        """Ponto do mundo (UTM) → papel do mapa em mm (y para baixo)."""
        p = self._para_mapa.map(QPointF(e, n))
        return p.x(), p.y()

    def _preparar_satelite(self, sat):
        """Acrescenta ao dict do satélite o posicionamento de papel do OCD
        (centro em mm e tamanho do pixel em mm)."""
        if not sat:
            return None
        cx = sat['ulx'] + (sat['w'] / 2.0) * sat['px']
        cy = sat['uly'] + (sat['h'] / 2.0) * sat['py']     # py é negativo
        mcx, mcy = self.mapa_mm(cx, cy)
        sat = dict(sat)
        sat['centro_mm'] = (mcx, mcy)
        sat['u_mm'] = sat['px'] * 1000.0 / self.escala     # mm por pixel (x)
        sat['v_mm'] = abs(sat['py']) * 1000.0 / self.escala  # mm por pixel (y)
        return sat
