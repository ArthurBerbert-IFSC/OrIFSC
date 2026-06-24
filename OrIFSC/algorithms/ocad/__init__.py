"""Geração de projetos para softwares de orientação a partir da folha do OrIFSC.

Dois formatos, escritos do zero (sem depender de OCAD/OOM instalados):

- **.omap** — OpenOrienteering Mapper (XML aberto). Caminho robusto e verificável.
- **.ocd** — OCAD 9 (binário). Abre direto no OCAD, sem passar pelo OOM.

Ambos saem com a mesma geometria: georreferência (UTM + escala + grade),
declinação magnética, a imagem de satélite como mapa de fundo georreferenciado e
as curvas de nível já como objetos de linha vinculados a um símbolo de curva.

A modelagem binária do .ocd e o XML do .omap foram portados das estruturas do
OpenOrienteering Mapper (GPLv3): `src/fileformats/ocd_types*.h`,
`ocd_file_export.cpp`, `ocd_georef_fields.cpp` e `core/georeferencing.cpp`.
"""
from .projeto import ProjetoOcad
from .omap import escrever_omap
from .ocd import escrever_ocd_v9

__all__ = ['ProjetoOcad', 'escrever_omap', 'escrever_ocd_v9']
