🗺️ OrIFSC - Plugin QGIS para Mapas de Orientação
OrIFSC é um plugin para o QGIS que automatiza a produção de bases cartográficas para mapas de orientação desportiva.
Este projeto é uma parceria entre o Instituto Federal de Santa Catarina (IFSC) e o Clube de Orientação de Florianópolis (FLORA).

🚀 Novidades (v0.1.4)
A primeira versão totalmente funcional! Agora o plugin conta com:
Exportação Direta: Projetos prontos para OCAD (.ocd) e OpenOrienteering Mapper (.omap).
Georreferenciamento Nativo: Os arquivos já saem na escala, rotação e coordenadas corretas (UTM).
Declinação Magnética: Cálculo automático integrado.

🌐 Idiomas / Languages / Diller
O plugin está disponível em Português, English e Türkçe. Por padrão segue o idioma do QGIS (outros idiomas caem no inglês); para escolher manualmente, use o menu OrIFSC → Idioma / Language ou OrIFSC → Configurações.
The plugin follows the QGIS language by default; pick another one under OrIFSC → Language.
Eklenti varsayılan olarak QGIS dilini kullanır; başka bir dil seçmek için OrIFSC → Dil / Language menüsünü kullanın.
Quer ajudar a traduzir ou revisar? Os textos ficam em OrIFSC/i18n/*.json (texto em português = chave); rode python tools/i18n_atualizar.py depois de mudar textos no código.

📥 Instalação
O OrIFSC já está disponível no repositório oficial do QGIS:
Abra o QGIS (versão 3.40 ou superior; compatível com o QGIS 4).
Acesse o menu Complementos > Gerenciar e Instalar Complementos...
Pesquise por OrIFSC e clique em Instalar.

🗺️ Fluxo Rápido de Uso
Definir Local: Insira a coordenada (Lat, Lon) e o tamanho da folha.
Camadas de Fundo: Carregue imagens de satélite ou OpenStreetMap.
Relevo: Gere curvas de nível suavizadas automaticamente (via Copernicus 30m).
Exportar: Exporte a base final diretamente para OCAD ou OOM e comece a desenhar.

🚧 Próximas Implementações (Roadmap)

[x] Geração de curvas de nível a partir do MDT do SIG@SC (WCS, alta resolução).
[x] Importação de arquivos GPX e KML.
[x] Inclusão automática de simbologia completa na exportação (ISOM 2017-2 / ISSprOM 2019-2, symbol sets oficiais do OpenOrienteering Mapper embutidos).

📝 Créditos e Licença
Autor: Arthur Berbert (@arthurberbert-ifsc)
Licença: GNU GPLv3 (Consulte o arquivo LICENSE). Os escritores de exportação .ocd/.omap são portes do OpenOrienteering Mapper (GPLv3) e os conjuntos de símbolos embutidos vêm do mesmo projeto (ver OrIFSC/recursos/simbologias/PROVENIENCIA.txt).
