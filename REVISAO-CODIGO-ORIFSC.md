# Revisão crítica — Plugin OrIFSC (PyQGIS → OCAD 10 / OOM)

Revisão por engenheiro sênior PyQGIS / cartografia de orientação. Base analisada: pacote ativo em `OrIFSC/OrIFSC/` (≈2.400 linhas). Pasta `Antigos/` e arquivos soltos (`OrIFSC.zip`, `Mapa sem título.kml`, `testes/`, `verificar/`) ignorados por serem legado/lixo de repo.

---

## Veredito geral

Este **não** é o código de um iniciante. A arquitetura está bem separada, há tratamento defensivo real, e os pontos mais difíceis (TIFF que o OCAD 10 aceita, gravação binária do `.ocd`, declinação vs. convergência, download sem travar o QGIS) já estão resolvidos — em vários casos melhor do que eu esperaria. O changelog mostra que você já apanhou e corrigiu os bugs clássicos (satélite travando ao fechar, NAM órfão por thread, TIFF com alpha/tiles, OCD v9 pedindo conversão).

O trabalho a fazer agora é de **acabamento**, não de reconstrução. As três frentes de maior retorno: (1) transformar o "menu" num assistente que **impede** o leigo de pular etapas; (2) reduzir densidade de vértices das curvas antes de exportar; (3) tirar a declinação da dependência de internet em tempo de exportação.

### Prioridades

| # | Severidade | Item | Onde |
|---|-----------|------|------|
| 1 | Alta (UX) | Menu não força ordem; leigo pode "Exportar" antes de "Definir Local" e cair em erro técnico | `orifsc.py`, `comum.py` |
| 2 | Alta (OCAD) | Curvas suavizadas sem simplificação → objetos densos no `.ocd` | `gerar_curvas.py`, `ocd.py` |
| 3 | Média (robustez) | Declinação depende da NOAA na hora de exportar (chave demo, sem cache) | `geo.py`, `exportar_ocad.py` |
| 4 | Média (travar) | GetCapabilities do SIG@SC roda na thread da GUI | `dados_publicos_sc.py` |
| 5 | Média (memória) | Pico de RAM no mosaico de satélite (~2–4× a imagem final) | `exportar_ocad.py` |
| 6 | Baixa | `.ocd` sem teste de ida-e-volta; constantes `g/d` do georref hardcoded | `ocd.py` |
| 7 | Baixa | Temp do MDT mesclado com nome fixo; transforms via `QgsProject.instance()` em thread | `gerar_curvas.py`, `exportar_ocad.py` |
| 8 | Baixa | Higiene de repositório (`Antigos/`, `.zip`, layout aninhado) | raiz |

---

## 1. Compatibilidade com OCAD 10

**Premissa a corrigir:** você pergunta sobre "DXF, Shapefile ou GeoTIFF". O plugin **não passa por DXF nem Shapefile** — escreve `.ocd` (binário, v10) e `.omap` (XML) **diretamente**, mais o GeoTIFF de fundo. Isso é o melhor caminho possível e deve continuar assim: importar DXF/SHP no OCAD é justamente a fonte clássica de dor (DXF vira arcos/splines e mapeamento de layers; SHP perde simbologia e vira tabela de atributos). Você já fugiu disso.

**O que está certo (manter):**

- **GeoTIFF de fundo** com `COMPRESS=LZW`, `TILED=NO`, `BIGTIFF=NO`, `PHOTOMETRIC=RGB`, 3 bandas RGB sem alpha. É exatamente o que o leitor TIFF do OCAD 10 (32-bit, `fRead` do arquivo inteiro) aceita. Os comentários em `_georref_e_reprojeta` estão corretos e valem ouro.
- **`.ocd` gravado nativamente como v10**, então o OCAD 10+ abre sem o diálogo de conversão.
- **Escritor binário portado campo-a-campo do OpenOrienteering Mapper**, com `assert struct.calcsize(...)` validando o tamanho das structs *packed*. Número do símbolo (101000) bate com a referência no objeto. Strings 9 (cor), 1039 (georref) e 8 (fundo) presentes. `latin-1` é a codificação certa para o OCD pré-Unicode.

**A melhorar / verificar:**

- **[Alta] Densidade de vértices.** `native:smoothgeometry` com `ITERATIONS=3` multiplica os vértices, e não há simplificação antes de escrever `.ocd`/`.omap`. Curvas muito densas geram `.ocd` grande, OCAD lento e risco com polilinhas extremamente longas. Adicione uma simplificação Douglas–Peucker **depois** de suavizar, com tolerância ligada à escala (ex.: ~0,2–0,4 m a 1:10.000):

  ```python
  # após native:smoothgeometry, antes do recorte/saída
  simplificadas = processing.run('native:simplifygeometry', {
      'INPUT': suavizadas, 'METHOD': 0,        # 0 = distância (Douglas–Peucker)
      'TOLERANCE': max(0.2, equidistancia * 0.05),
      'OUTPUT': 'TEMPORARY_OUTPUT',
  }, context=context, feedback=feedback)['OUTPUT']
  ```

  Por segurança, considere quebrar polilinhas com mais de ~16k vértices em segmentos antes de gravar no OCD.
- **[Baixa] Constantes do georref 1039 hardcoded** (`g=50.0`, `d=500.0`). Confirme contra `ocd_georef_fields.cpp` do OOM se correspondem aos espaçamentos de grade pretendidos. Importante: elas afetam **só a grade que o OCAD desenha**, não a posição dos objetos (essa vem de `x/y/a/i` + o `QTransform`). Risco baixo, mas vale confirmar no round-trip.
- **[Baixa] Sinal de rotação do fundo.** O `.tif` é norte-de-grade-acima (UTM) e entra com `a=grivacao`. É o lugar clássico onde mora um erro de sinal/espelhamento. Confirme abrindo no OCAD que o satélite alinha com as curvas (sem rotação dupla).
- **[Baixa] Sem QA de ida-e-volta.** Não há nada que reabra o `.ocd` gerado. Veja o checklist no fim — teste em **OCAD 10 real**, não só 2018/2020 (o leitor v10 é mais rígido).

---

## 2. Fluxo do assistente (UX/UI) e validações

**O ponto central:** hoje é um **menu**, não um assistente. O "passo a passo" está só no agrupamento do menu (Início → Bases → Importar → Relevo → Dados Públicos → Exportar) e nos painéis de instrução (que, aliás, estão lindos — `painel.py` é um mini design-system excelente). Mas um menu **não impede** o leigo de clicar em "Gerar Projeto OCAD" antes de "Definir Local". Para o público-alvo (mapeadores com muita dificuldade no QGIS), isso é a maior lacuna frente ao objetivo "à prova de erros".

**Validações que já existem e estão boas:** coordenada (parse + faixa lat/lon, recente), pasta de saída obrigatória e não-temporária, CRS precisa ser WGS84/UTM, escala precisa estar definida, KML/GPX exige arquivo existente e ≥1 sub-camada, falha de `QImage.save` levanta exceção. Bom nível defensivo.

**O que falta / recomendações:**

- **[Alta] Guarda amigável antes das etapas pesadas.** `projeto_configurado()` só protege `criar_limite`/`criar_folha`. Em `_gerar_curvas` e `_exportar_ocad`, o erro hoje só aparece **dentro** do diálogo de Processing como `QgsProcessingException` (texto vermelho assustador). Antes de abrir o diálogo, cheque e avise com `QMessageBox`:

  ```python
  def _exportar_ocad(self):
      from .acoes.comum import projeto_configurado, avisar_projeto_nao_configurado
      if not projeto_configurado():
          avisar_projeto_nao_configurado(self.iface.mainWindow())
          return
      import processing
      processing.execAlgorithmDialog('orifsc:exportar_ocad', {})
  ```

- **[Alta] Transformar em assistente de verdade.** Duas opções, em ordem de esforço:
  - *Menor esforço:* um painel dockável "Assistente OrIFSC" listando as etapas com estado (✓ feito / 🔒 bloqueado), cinza enquanto o pré-requisito não existe (dirigido por `projeto_configurado()` + presença das camadas `folha`/`limite`/`curvas`). Você já tem a linguagem visual pronta em `painel.py`.
  - *Mais robusto:* um `QWizard` com páginas (Local → Bases → Limite → Curvas → Exportar) e o botão **Avançar desabilitado** até cada página validar. Isso é, literalmente, "à prova de erros".
- **[Média] Pré-preencher o diálogo de exportação.** Default do combo FOLHA para a camada `folha`; default da pasta para `Configurações → pasta_saida`; e **mostrar a escala** lida do projeto (hoje ela é invisível no diálogo de export — o leigo não sabe que está embutida).
- **[Baixa] Entrada de coordenada mais tolerante:** aceitar também URL colada do Google Maps e `lat lon` sem vírgula.
- **[Baixa] Borda de fuso UTM:** em `lon == 180`, `fuso` vira 61 (EPSG inválido). Faça `fuso = min(60, ...)`. Não afeta SC, mas é trivial.

---

## 3. Cálculo de declinação magnética

**Está correto e bem pensado — é o ponto mais forte tecnicamente.** Você acertou justamente onde quase todo mundo erra: distinguir os três nortes.

- Declinação automática via **WMM/NOAA** (`declinacao_noaa`), com fallback manual claro ("leste +; usada se o automático falhar").
- **Convergência meridiana** por forma fechada sólida `γ = atan(tan Δλ · sin φ)`, avaliada no **centro da folha** (correto).
- **Grivação = declinação − convergência** (magnético em relação à **grade**). Esse é o ângulo certo a gravar, porque o papel do OCAD/OOM é norte-magnético-acima e o mundo (UTM) é norte-de-grade-acima — a rotação mundo→papel é a grivação, **não** a declinação crua. Usar a declinação direto (erro comum) erraria pela convergência. Você não caiu nessa.
- O `QTransform` (`translate → rotate(−grivação) → scale(s,−s)` e inverter) espelha o `Georeferencing` do OOM, que é a forma mais segura de não errar o sinal. `.omap` grava `declination` e `grivation`; `.ocd` grava a grivação no ângulo `a` e no fundo. Consistente.

**A melhorar:**

- **[Média] Tirar a dependência de internet do momento da exportação.** Hoje a exportação chama a NOAA com a **chave demo** `zNEw7` (pode ter rate-limit / mudar) e precisa de rede. Mitigado pelo fallback, mas:
  - **Cacheie** a declinação calculada no projeto (`writeEntryDouble`), para reexportar offline e de forma reprodutível.
  - **Melhor solução de longo prazo:** embarcar os coeficientes do **WMM/IGRF** e calcular localmente (uma implementação WMM em Python pura é pequena). Elimina a rede de vez.
  - **Mostre** declinação e grivação resolvidas num passo de confirmação (hoje só vão para o log do Processing). Para SC a declinação ronda ~ −20°; um valor visível ajuda o mapeador a pegar um sinal trocado na hora.
- **[Baixa] Datas fora da validade do modelo** (futuro distante) retornam erro na API → cai no manual. Ok como está; com WMM local, trate a faixa de validade explicitamente.

---

## 4. Robustez PyQGIS — travamentos, memória, limpeza

**Esta é uma base notavelmente cuidadosa.** O essencial para "não travar" está certo:

- **Operações pesadas rodam fora da thread da GUI.** `gerar_curvas` e `exportar_ocad` são algoritmos de Processing abertos via `execAlgorithmDialog`; `flags()` adiciona só `HideFromToolbox` (**não** `NoThreading`), então o QGIS roda num `QgsProcessingAlgRunnerTask` em background, com progresso e **Cancelar**. É a coisa mais importante do pedido, e está correta.
- **Tiles do satélite baixadas de forma assíncrona numa única thread** (`rede.baixar_varios`: vários `get()` + `QEventLoop` aninhado sobre o `QgsNetworkAccessManager` da própria thread), justamente para evitar o NAM órfão por thread que travava o fechamento. `nam.finished` desconectado no `finally`, `reply.deleteLater()`. Ciclo de vida limpo.
- **Handles GDAL fechados explicitamente** (`ds = None`, `FlushCache()`), temporários removidos em `finally`, **satélite não é auto-carregado** no QGIS (evita o freeze com imagem grande). Rede via `QgsBlockingNetworkRequest` (respeita proxy/timeout, bloqueia esquemas não-http). XML por `QXmlStreamReader` (sem expandir DTD/entidades externas) — bom instinto de segurança. Cache de tile valida tamanho mínimo. `unload()` remove provider e deleta o menu.

**Bugs / riscos (priorizados):**

- **[Média] Download na thread da GUI no SIG@SC.** `adicionar_wms → _carregar_capabilities → baixar_bytes` roda no slot do menu (thread principal). `QgsBlockingNetworkRequest` na main thread usa um event loop interno (não congela de fato), mas a UI fica parada até o GetCapabilities (XML potencialmente grande) voltar, com risco de reentrância. Rode em `QgsTask` (ou ao menos cursor de espera + timeout).
- **[Média] Pico de memória do mosaico.** `MAX_PX=16384` limita o mosaico a ~0,8 GB, mas o `.copy()` do recorte + PNG + buffers do GDAL Translate/Warp levam o **pico** a ~2–4× a imagem final. Está limitado (bom) e fora da GUI, mas num notebook de 8 GB uma folha A3 em zoom alto chega perto do limite. Libere o mosaico cheio assim que possível e/ou deixe o GDAL fazer o recorte/warp em disco:

  ```python
  recorte = mosaico.copy(esq, topo, larg, alt)
  pintor.end()
  mosaico = None        # libera o mosaico cheio antes de salvar/reprojetar
  ```

  Alternativa mais escalável: escrever o mosaico num GeoTIFF temporário e deixar `gdal.Warp` recortar/reprojetar em streaming, em vez de manter `QImage`s inteiros na RAM. Considere baixar o default de `MAX_PX`.
- **[Baixa] Temp do MDT mesclado com nome fixo** (`orifsc_mdt_merged.tif` em `gettempdir()`): execuções concorrentes/abortadas colidem ou reusam arquivo velho. Use `QgsProcessingUtils.tempFolder()` ou `'TEMPORARY_OUTPUT'` no merge.
- **[Baixa] Curvas geradas/suavizadas em EPSG:4326 e só depois reprojetadas.** Em SC (φ≈−27°, cos≈0,89) isso mete ~10% de anisotropia x/y na suavização antes de reprojetar. Visualmente quase nada para curvas, mas reprojetar o DEM (ou as curvas brutas) para UTM **antes** de suavizar é geometricamente mais limpo. Opcional.
- **[Baixa] `QgsProject.instance()` em transforms dentro dos algoritmos** (`_curvas_para_linhas`, `_exportar_satelite`, `projeto.centro_latlon`) roda em thread de worker. Funciona, mas o estritamente correto é `context.project()` / `context.transformContext()` (o `gerar_curvas` já faz certo). Padronize.
- **[Baixa] `_definir` (Definir Local):** o `QgsCoordinateTransform.transform` não está dentro de try/except; se falhar (raro), o diálogo quebra sem mensagem amigável. Envolva.

---

## 5. Estrutura do projeto

- **Separação limpa:** `orifsc.py` (menu declarativo — elegante e fácil de estender) / `acoes/*` (diálogos e ações simples) / `algorithms/*` (Processing) / `algorithms/ocad/*` (escritores de formato, **independentes do framework**). Estado do projeto em `comum.py` (via `writeEntry`, sobrevive ao salvar/reabrir) vs. globais em `configuracoes.py` (`QgsSettings`) — separação correta.
- **`painel.py` como fonte única de identidade visual** é um baita acerto; reaproveitar o mesmo HTML no `shortHelpString()` e nos diálogos próprios é inteligente.
- **Higiene de repositório [Baixa]:** `Antigos/`, `OrIFSC.zip`, `Mapa sem título.kml`, `OrIFSC Icones.dc.html`, `testes/`, `verificar/` poluem o repo (e atrapalham a submissão ao QGIS Plugin Repository, que empacota o pacote `OrIFSC/`). Mova `Antigos/` para um branch e adicione artefatos ao `.gitignore`. O aninhamento `OrIFSC/OrIFSC/OrIFSC` confunde — documente qual é o pacote (o mais interno) ou achate.
- **Reload de dev** em `__init__.classFactory` e `provider.loadAlgorithms` referencia `OrIFSC.` **e** `PluginQgis.` (resíduo do rename). Inofensivo (atrás de `ORIFSC_DEV`), mas dá para limpar.
- **Sem testes.** O escritor `.ocd` é exatamente o tipo de código que se beneficia de 1–2 testes de *golden file* (gerar um `ProjetoOcad` conhecido → conferir bytes / reabrir). `geo.py`, `projeto.py`, `ocd.py`, `omap.py` têm lógica testável quase sem QGIS. Um único teste de round-trip já pega regressão nas structs *packed*.
- **metadata.txt** correto: `hasProcessingProvider=yes`, `supportsQt6=True`, `qgisMaximumVersion=4.99`. i18n: as strings de UI são PT fixas (`tr()` devolve o texto) — ok para o público; só wire traduções reais se um dia quiser EN.

---

## Checklist de QA recomendado (round-trip OCAD 10)

Faça uma vez, com uma folha real de SC, **no OCAD 10** (não só 2018/2020):

1. Abrir `projeto_orifsc.ocd` — sem pedido de conversão, sem erro de leitura.
2. `Mapa → Definir escala e sistema de coordenadas`: escala, coordenadas de referência (E/N), ângulo e grade/zona corretos.
3. As linhas de **norte magnético** apontam na direção certa para a localidade (confere a grivação/sinal).
4. **Curvas** aparecem com o símbolo 101 (marrom), na posição certa, sobre o **satélite** alinhado (sem rotação dupla nem espelho).
5. Abrir o mesmo conjunto no **OpenOrienteering Mapper** (`.omap`) e comparar geometria — devem coincidir (é o seu "oráculo" de verificação).
6. Repetir com uma folha **A3 em zoom alto** para validar memória e tamanho do `.ocd` (gatilho da simplificação de vértices).

---

## Próximos passos sugeridos (ordem de retorno)

1. Guarda amigável antes de Curvas/Exportar + pré-preencher o diálogo de export (rápido, alto impacto UX).
2. Passo de simplificação Douglas–Peucker nas curvas (rápido, resolve OCAD pesado).
3. Cachear a declinação no projeto (rápido); WMM local depois (maior, elimina a rede).
4. SIG@SC GetCapabilities em `QgsTask` + liberar mosaico cedo (robustez/memória).
5. Assistente dockável "você está aqui" reaproveitando `painel.py` (médio, fecha o objetivo "passo a passo à prova de erros").
6. 1–2 testes de round-trip do `.ocd`/`.omap` + limpeza do repositório.
