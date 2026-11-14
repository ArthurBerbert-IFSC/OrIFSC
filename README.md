🗺️ OrIFSC - Plugin QGIS para Mapas de Orientação
OrIFSC é um plugin para o QGIS que automatiza a produção de bases cartográficas para mapas de orientação desportiva.
Este projeto é uma parceria entre o Instituto Federal de Santa Catarina (IFSC) e o Clube de Orientação de Florianópolis (FLORA).

🚀 Novidades (v0.2.0)
Folha certa no OCAD: a folha nasce girada para o norte magnético e fica em pé no papel do OCAD/OOM.
Declinação sem internet: modelo magnético mundial (WMM2025) embutido, com opção de valor manual.
Ajustar Folha: mova a folha com o mouse, troque escala/papel/orientação ou encaixe a folha no limite da área.
Tipos de mapa: Sprint, Floresta, Escolar e Personalizado já preenchem norma, escala, equidistância e papel.
Assistente OrIFSC: painel lateral que guia as etapas, sem bloquear nada, e avisa o que ficou desatualizado.
Linhas de norte magnético: exportadas no símbolo e no espaçamento da norma.

📥 Instalação
O OrIFSC já está disponível no repositório oficial do QGIS:
Abra o QGIS (versão 3.40 ou superior; compatível com o QGIS 4).
Acesse o menu Complementos > Gerenciar e Instalar Complementos...
Pesquise por OrIFSC e clique em Instalar.

🗺️ Fluxo Rápido de Uso (o painel Assistente OrIFSC mostra estas etapas)
Tipo e Local: Escolha o tipo de mapa, a coordenada (Lat, Lon) e a folha — ela nasce girada para o norte magnético.
Ajustar Folha (opcional): Mova a folha, troque escala/papel ou encaixe-a no limite desenhado.
Camadas de Fundo: Carregue imagens de satélite, OpenStreetMap ou a ortofoto do SIG@SC.
Relevo: Gere curvas de nível suavizadas automaticamente (via Copernicus 30m).
Exportar: Exporte a base final diretamente para OCAD ou OOM, com curvas, satélite e linhas de norte, e comece a desenhar.

🚧 Próximas Implementações (Roadmap)

[x] Geração de curvas de nível a partir do MDT do SIG@SC (WCS, alta resolução).
[x] Importação de arquivos GPX e KML.
[x] Inclusão automática de simbologia completa na exportação (ISOM 2017-2 / ISSprOM 2019-2, symbol sets oficiais do OpenOrienteering Mapper embutidos).

📝 Créditos e Licença
Autor: Arthur Berbert (@arthurberbert-ifsc)
Licença: GNU GPLv3 (Consulte o arquivo LICENSE). Os escritores de exportação .ocd/.omap são portes do OpenOrienteering Mapper (GPLv3) e os conjuntos de símbolos embutidos vêm do mesmo projeto (ver OrIFSC/recursos/simbologias/PROVENIENCIA.txt).
