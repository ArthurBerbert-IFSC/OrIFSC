# Diretrizes de Desenvolvimento do Plugin

## 1. Arquitetura adotada

- **Entrada do plugin**: `OrIFSC\__init__.py` expõe `classFactory` e instancia `OrIFSCPlugin`.
- **Casca de UI**: `OrIFSC\orifsc.py` concentra:
  - montagem do menu OrIFSC;
  - vínculo entre ações de menu e módulos de `acoes/`;
  - registro do provider de Processing.
- **Ações de interface** (`OrIFSC\acoes\*.py`):
  - diálogos e fluxos guiados para usuário final (definir local, importar dados, ajuda, bases).
  - persistência de estado do projeto em `comum.py`.
  - persistência de preferências globais em `configuracoes.py`.
- **Algoritmos Processing** (`OrIFSC\algorithms\*.py`):
  - `gerar_curvas.py`: aquisição de MDT + geração/suavização de curvas.
  - `exportar_ocad.py`: exportação georreferenciada para OCAD/OOM.
  - `suavizacao.py`: Chaikin vetorizado (NumPy) — módulo puro, sem QGIS, testável isoladamente.
  - `utils.py`: utilitários comuns — ocultar algoritmos da toolbox e cache persistente (`dir_cache`/`podar_cache`).
- **Núcleo de exportação OCAD/OOM** (`OrIFSC\algorithms\ocad\*.py`):
  - modelo comum (`projeto.py`);
  - cálculos geográficos (`geo.py`);
  - escritores de arquivo (`ocd.py`, `omap.py`).
- **Rede** (`OrIFSC\rede.py`):
  - `baixar_bytes`: requisições unitárias via rede do QGIS.
  - `baixar_varios`: download paralelo HTTP para mosaicos de tiles.

## 2. Regras de negócio identificadas

1. **Pré-requisito de projeto configurado**
   - Fluxos dependentes de folha/escala/CRS (ex.: exportação) exigem execução prévia de **Definir Local e Criar Folha**.
2. **CRS obrigatório para exportação**
   - Exportação aceita apenas EPSG UTM WGS84 (`326xx`/`327xx`).
3. **Curvas exigem área de referência**
   - Geração de curvas requer pelo menos uma camada poligonal (folha, limite ou outra).
4. **Sem fallback automático entre fontes de MDT**
   - Ao escolher Copernicus ou SIG@SC, falha deve ser explícita; não trocar fonte silenciosamente.
5. **Persistência separada por escopo**
   - Estado de projeto: `QgsProject` (`OrIFSC/...`).
   - Padrões globais: `QgsSettings` (`OrIFSC/...`).
6. **Exportação com pasta permanente**
   - Pasta de saída não pode ser diretório temporário.
7. **Compatibilidade de satélite com OCAD**
   - O TIFF **final** (`satelite_orifsc.tif`) deve preservar parâmetros compatíveis com OCAD 10: 3 bandas RGB (sem alpha), `COMPRESS=LZW`, `TILED=NO` (strips), `BIGTIFF=NO`, < 2 GB.
   - A restrição vale apenas para o arquivo que o OCAD abre. Arquivos **intermediários** do pipeline (lidos só pelo GDAL e apagados ao final) não têm essa restrição — otimizações de montagem em blocos/streaming são permitidas desde que o arquivo final saia com as opções acima.
8. **Operações métricas sempre em CRS projetado**
   - Tolerâncias de simplificação/suavização/buffer são definidas em **metros** e aplicadas com as geometrias já reprojetadas para o CRS UTM da folha.
   - Nunca aplicar tolerância numérica sobre geometria em CRS geográfico (graus). Causa histórica: `simplify(0.2)` aplicado sobre curvas em EPSG:4326 equivalia a ~22 km de tolerância e colapsava as curvas em "triângulos/retângulos" (bug corrigido em `gerar_curvas.py`).
9. **Fontes de MDT suportadas**
   - Copernicus 30 m (global) e SIG@SC via WCS (Santa Catarina). **FABDEM foi removido do escopo** (decisão de julho/2026); não reintroduzir placeholders "em breve" no menu ou nas configurações.

## 3. Comunicação entre módulos

- `orifsc.py` chama funções/classes em `acoes/*` sob demanda (imports locais).
- Ações e algoritmos compartilham estado via:
  - `acoes/comum.py` (folha, escala, verificação de contexto);
  - camadas já carregadas no `QgsProject`.
- `exportar_ocad.py` e `gerar_curvas.py` usam `rede.py` para acesso HTTP.
- `provider.py` publica algoritmos de `algorithms/*` para execução pelo menu.
- `painel.py` centraliza HTML/identidade visual para diálogos próprios e `shortHelpString()` do Processing.

## 4. Diretrizes para próximos desenvolvedores

### Faça

- Mantenha **imports tardios** em slots de menu quando o objetivo for reduzir custo de carregamento.
- Mantenha mensagens de erro claras para o usuário (sem falhas silenciosas).
- Preserve compatibilidade com **QGIS 3.40+ (LTR) e QGIS 4 (Qt6/PyQt6)** com um único código, sem branches de versão:
  - imports sempre via `qgis.PyQt` (nunca `PyQt5`/`PyQt6` direto);
  - enums sempre na **forma escopada** (`Qgis.MessageLevel.Warning`, `QMessageBox.Icon.Question`, `Qgis.ProcessingSourceType.VectorPolygon`, `QgsFeatureSink.Flag.FastInsert`, ...) — a forma não-escopada quebra no PyQt6;
  - `qgisMinimumVersion=3.40` no `metadata.txt`; APIs anteriores a 3.40 não precisam de fallback.
- Rede disparada por clique de menu/diálogo (fora de algoritmos de Processing) deve rodar em `QgsTask` — nunca bloquear a thread da UI. Algoritmos de Processing já rodam em thread própria e podem usar `baixar_bytes`/`baixar_varios` diretamente.
- Arquivos temporários com nome único por execução (`QgsProcessingUtils.generateTempFilename`), nunca nomes fixos em `%TEMP%`.
- Em algoritmos de Processing, **libere o sink de saída antes do `return`** (`sink.flushBuffer()` + `del sink`, sem closures segurando referência): um buffer/handle ainda aberto quando o QGIS carrega a camada de saída causa access violation no Windows.
- Laços por vértice em Python são proibidos para dados densos — vetorize com NumPy (ex.: `_chaikin` em `gerar_curvas.py`) e use `QgsGeometry.createGeometryEngine` + `prepareGeometry()` para interseções repetidas contra a mesma geometria.
- Toda simplificação de geometria deve ser justificada em resolução de papel (mm na escala do projeto), nunca um número solto. **Critério cartográfico do projeto: o menor objeto visível no papel é 0,15 mm** (definição do autor, jul/2026). Desvios acumulados de todo o pipeline devem ficar abaixo disso; como as curvas passam por duas simplificações (antes e depois do Chaikin), cada passada usa 0,075 mm de papel, limitada a [0,1 m; 1,5 m] (`_tolerancia_simplificacao_m` em `gerar_curvas.py`).
- Rasters grandes nunca inteiros na RAM: monte/escreva por faixas (streaming) direto num dataset GDAL (`_montar_mosaico_tif` em `exportar_ocad.py`). Combine tiles de MDT com `gdal.BuildVRT` (mosaico virtual), não com `gdal:merge`.
- Caches persistentes (tiles de MDT/satélite) em `QgsApplication.qgisSettingsDirPath()/cache/orifsc`, com validação de integridade (tamanho mínimo) e re-download automático de arquivos corrompidos.
- Reutilize `acoes/comum.py` e `acoes/configuracoes.py` para qualquer novo estado.
- Documente decisões técnicas importantes em docstrings (não em comentários longos soltos).

### Não faça

- Não adicionar fallback implícito entre serviços de dados sem sinalizar ao usuário.
- Não depender de diretório temporário para artefatos finais de exportação.
- Não mover regras de georreferência para múltiplos lugares (manter no núcleo `algorithms/ocad`).
- Não criar novas rotas de rede que aceitem esquemas além de `http/https`.
- Não duplicar lógica de validação de projeto já existente em `acoes/comum.py`.
- Não usar enums Qt/QGIS na forma não-escopada (ex.: `QMessageBox.Cancel`, `Qgis.Warning`) — quebra no QGIS 4/PyQt6.
- Não alterar as creation options do GeoTIFF **final** do satélite (RGB, LZW, `TILED=NO`, `BIGTIFF=NO`) — requisito do OCAD 10.
- Não reintroduzir FABDEM nem itens de menu/configuração desabilitados como placeholder.
- Não expandir o uso de tiles do Google para novas funcionalidades (ver seção 6).

## 5. Convenções técnicas do projeto

- Nome de camadas-chave: `folha`, `limite`, `Curvas de Nível` (ou variantes detectáveis).
- Algoritmos de Processing devem permanecer ocultos da toolbox e acessíveis pelo menu OrIFSC.
- Quando necessário preservar contexto histórico (ex.: limitações de OCAD/GDAL), priorizar docstring no método responsável.
- `__pycache__`/`.pyc` não entram no repositório nem no zip publicado.
- **Testes** (`tests/`): cobrem os módulos puros (escritores `.ocd`/`.omap`, cálculos UTM, suavização) e rodam sem QGIS — `python -m pytest tests/` local e no CI (`.github/workflows/testes.yml`) a cada push/PR. Módulos novos com lógica pura devem nascer sem imports de `qgis` no nível do módulo (ex.: `suavizacao.py`; import tardio quando inevitável, como em `geo.py`), para continuarem testáveis.
- Lógica nova em módulo puro ganha teste junto; ao mexer nos escritores OCD/OMAP, rodar a suíte antes de publicar.
- Docstrings sem seções vazias ("Args: None / Returns: None"): descreva o que importa ou apenas a linha de resumo.

## 6. Restrições e riscos externos documentados

- **OCAD 10 (32 bits)**: lê apenas TIFF RGB de 3 bandas, LZW ou sem compressão, organização em strips (`TILED=NO`) e arquivo < 2 GB; sem canal alpha. O limite `MAX_PX=16384` por lado em `exportar_ocad.py` deriva disso — é limite técnico, não ajuste de qualidade.
- **Tiles do Google (`mt*.google.com`)**: o download automatizado (scraping de endpoint não oficial), o salvamento offline em GeoTIFF e a vetorização de mapa por cima da imagem violam os Termos de Serviço do Google Maps. **Atribuição/referência não autoriza esses usos** — a restrição é contratual, não de crédito. Riscos, em ordem realista: sinalização/remoção do plugin no repositório oficial do QGIS; bloqueio técnico do endpoint pelo Google (quebra silenciosa da funcionalidade); ação legal contra usuários finais (teórico nessa escala). **Decisão registrada (julho/2026)**: manter a funcionalidade com o risco documentado; preferir e promover a ortofoto do SIG@SC como fundo quando a área for em Santa Catarina; não expandir o uso do Google em novas funcionalidades.
- **NOAA/WMM (declinação)**: usa a chave pública de demonstração; se falhar, degrada para o valor manual informado no diálogo (comportamento intencional).
- **SIG@SC**: serviço lento/instável; toda chamada precisa de timeout e mensagem clara ao usuário, sem fallback implícito para outra fonte.
