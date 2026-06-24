🗺️ OrIFSC - Plugin QGIS para Mapas de Orientação
OrIFSC é um plugin para o QGIS que automatiza a produção de bases cartográficas para mapas de orientação desportiva.
Este projeto é uma parceria entre o Instituto Federal de Santa Catarina (IFSC), a Federação Catarinense de Orientação (FCO) e o Clube de Orientação de Florianópolis (FLORA).

🚀 Novidades (v0.1.4)
A primeira versão totalmente funcional! Agora o plugin conta com:
Exportação Direta: Projetos prontos para OCAD (.ocd) e OpenOrienteering Mapper (.omap).
Georreferenciamento Nativo: Os arquivos já saem na escala, rotação e coordenadas corretas (UTM).
Declinação Magnética: Cálculo automático integrado.

📥 Instalação
O OrIFSC já está disponível no repositório oficial do QGIS:
Abra o QGIS.
Acesse o menu Complementos > Gerenciar e Instalar Complementos...
Pesquise por OrIFSC e clique em Instalar.

🗺️ Fluxo Rápido de Uso
Definir Local: Insira a coordenada (Lat, Lon) e o tamanho da folha.
Camadas de Fundo: Carregue imagens de satélite ou OpenStreetMap.
Relevo: Gere curvas de nível suavizadas automaticamente (via Copernicus 30m).
Exportar: Exporte a base final diretamente para OCAD ou OOM e comece a desenhar.

🚧 Próximas Implementações (Roadmap)

[ ] Integração com modelo de elevação FABDEM.
[ ] Geração de curvas de nível a partir de qualquer Raster/WMS (ex: MDT do SIG@SC).
[ ] Inclusão automática de simbologia completa na exportação (ligação com arquivos de referência .crt).
[ ] Importação de arquivos GPX e KML.

📝 Créditos e Licença
Autor: Arthur Berbert (@arthurberbert-ifsc)
Licença: GNU GPLv2 (Consulte o arquivo LICENSE).
