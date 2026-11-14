# Planejamento — OrIFSC 0.2.0

Decisões tomadas na sessão de planejamento de novembro/2026 (Arthur + Claude).
Este arquivo é o guia das próximas sessões: marque os itens conforme forem
concluídos e registre aqui qualquer mudança de decisão.

## Decisões

| # | Pergunta | Decisão |
|---|----------|---------|
| 1 | Público principal | **Iniciante e experiente por igual.** Assistente em **painel lateral** que guia sem travar; o menu atual continua como "ferramentas avançadas". |
| 2 | O que vem primeiro: folha ou área? | **Os dois caminhos.** "Posicionar folha" (folha primeiro) e "Ajustar ao limite" (área primeiro). |
| 3 | Assistente começa pelo tipo de mapa? | **Sim.** Sprint / Floresta / Personalizado preenchem norma, escala, equidistância e papel (tudo editável depois). |
| 4 | O que entra no projeto exportado | **Linhas de norte magnético** entram (último item). Base OSM e moldura de impressão ficam para depois. |
| 5 | Publicação | **Tudo numa versão só (0.2.0)**, implementada por partes com um commit por parte. |
| 6 | Limite não cabe na folha | **Aumenta o papel primeiro** (A4 → A3) mantendo a escala da norma; se nem A3 couber, avisa e mostra a escala que caberia. |
| 7 | Programas de destino | Usam todos, mas o alvo de compatibilidade é **OCAD 10** e **OpenOrienteering Mapper** (o resto abre sem erro). |
| 8 | Folga entre o limite e a borda do papel | **5 mm** no papel. |
| 9 | Tipo "Escolar / Parque" | **Sim**: ISSprOM, 1:2.000, equidistância 2 m, A4. |
| 10 | Quando o assistente aparece | **Abre sozinho na primeira vez**; depois o QGIS lembra se a pessoa fechou; botão na barra reabre. |
| 11 | Como saem as linhas de norte | **Linhas separadas, pretas** (símbolo de linha de norte da norma), uma por objeto. |

Decisões técnicas (tomadas pelo Claude, sem objeção):

- **Declinação offline** com o modelo WMM2025 embutido (`OrIFSC/recursos/wmm/`),
  válido até o fim de 2029. Acaba a dependência da chave de demonstração da NOAA.
- **Satélite continua com o norte da quadrícula para cima** no GeoTIFF; o OCAD
  gira a imagem ao abrir (como já acontece). Girar antes perderia nitidez.
- **Folha muda → etapas dependentes ficam "desatualizadas"** no painel; nada é
  refeito automaticamente (downloads pesados).

## Escopo da 0.2.0 (ordem de implementação)

- [x] Equidistância decimal (2,5 m para sprint).
- [x] **Parte 1 — Folha certa no OCAD** (falta o teste no OCAD 10 e no OOM — ver checklist)
  - [x] Declinação calculada offline (WMM2025) no "Definir Local" e salva no projeto (com opção manual).
  - [x] Folha nasce girada para o norte magnético (grivação = declinação − convergência).
  - [x] Satélite e curvas cobrem a folha girada inteira (o satélite cobre o retângulo envolvente; as curvas são recortadas pelo polígono girado).
  - [x] Exportação usa a declinação salva na folha; projetos antigos continuam exportando como antes (com aviso).
- [x] **Parte 2 — Ajustar a folha** (menu Início → "Ajustar Folha (mover, escala, papel)…")
  - [x] Contorno laranja de prévia ao trocar escala, papel ou orientação.
  - [x] "Mover no mapa…": o contorno segue o mouse, clique fixa (botão direito/Esc cancela).
  - [x] Declinação e convergência recalculadas no novo lugar (valor manual é mantido).
  - [x] A camada `folha` é atualizada no lugar, nunca duplicada (inclusive ao rodar o Definir Local de novo); projetos 0.1.x são convertidos para a folha girada ao ajustar.
  - [x] Contador de revisão da folha no projeto (base para as etapas "desatualizadas" da parte 5).
- [x] **Parte 3 — Ajustar ao limite** (no Ajustar Folha: "Ajustar ao limite: [camada] [Ajustar]")
  - [x] Orientação pela proporção do limite medido no papel (já girado para o norte magnético); centro no meio do limite.
  - [x] Folga de **5 mm** no papel (decisão 8). Parte do papel escolhido e aumenta (A4 → A3); nunca diminui.
  - [x] Se nem o A3 couber: pergunta se pode usar a menor escala padrão que caberia (a escala nunca muda sozinha).
  - [x] Aceita qualquer camada de polígono (inclusive KML em graus); com feições selecionadas, usa só elas.
- [x] **Parte 4 — Tipos de mapa** (primeiro campo do Definir Local)
  - [x] Sprint / Floresta / Escolar / Personalizado; o tipo preenche escala e papel (campos continuam editáveis).
  - [x] Tipo salvo no projeto: Gerar Curvas sugere a equidistância do tipo e a exportação sugere a norma do tipo.
  - [x] Último tipo usado é lembrado no próximo projeto; Personalizado e projetos sem tipo seguem as Configurações.
  - [x] Escalas 1:2.000 e 1:3.000 entram na lista.
- [x] **Parte 5 — Painel assistente** (painel lateral "Assistente OrIFSC")
  - [x] Seis etapas: Tipo e local → Ajustar folha (opcional) → Imagem de fundo → Limite (opcional) → Curvas → Exportar.
  - [x] ✓ feito, ▶ próximo, ! atenção (número cinza = pendente/opcional); links disparam as mesmas ações do menu, nada é bloqueado.
  - [x] Curvas e exportação ficam ⚠ quando a folha muda (ou as curvas são refeitas depois da exportação); com um ⚠ no caminho, não há ▶ adiante.
  - [x] Atualiza sozinho (camadas entram/saem, projeto aberto/limpo, folha ajustada, curvas geradas, exportação).
  - [x] Abre sozinho na primeira vez; fechar é lembrado; botão na barra e item no topo do menu reabrem.
  - [x] O ✓ / ▶ / ⚠ do menu OrIFSC usa a mesma lógica do painel.
- [x] **Parte 6 — Linhas de norte magnético** (exportação: "Incluir linhas de norte magnético", ligado por padrão)
  - [x] Espaçamento lido das normas embutidas: ISOM 300 m no terreno (20 mm em 1:15.000, 30 mm em 1:10.000); ISSprOM 30 mm no papel.
  - [x] Linhas verticais no papel (norte magnético), recortadas pela folha, de baixo para cima; uma por objeto.
  - [x] Símbolo por norma: ISOM `601.1` (OCD 601001), ISSprOM `601` (OCD 601000) — na ISSprOM o `601.1` é o padrão de área.
  - [x] Sem simbologia (ou sem doador `.ocd`) não há símbolo 601: as linhas não entram, com aviso no log.

**Escopo da 0.2.0 completo.** `metadata.txt` já está em `version=0.2.0` com o changelog.
Para publicar: rodar o checklist abaixo no OCAD 10 e no OOM → juntar o branch no `main`
→ `git tag 0.2.0 && git push origin 0.2.0` (ver `PUBLICAR.md`).

Tipos de mapa (parte 4 — em `OrIFSC/algorithms/ocad/tipos_mapa.py`):

| Tipo | Norma | Escala | Equidistância | Papel |
|---|---|---|---|---|
| Sprint / urbano | ISSprOM 2019-2 | 1:4.000 | 2,5 m | A4 |
| Floresta / rural | ISOM 2017-2 | 1:10.000 | 5 m | A4 |
| Escolar / parque | ISSprOM 2019-2 | 1:2.000 | 2 m | A4 |
| Personalizado | livre | livre | livre | livre |

## Depois da 0.2.0

- Base vetorial do OpenStreetMap já com símbolos ISOM/ISSprOM.
- Moldura de impressão (margem, legenda, título, limite da área mapeada).
- Opção de girar a vista do QGIS para o norte magnético ("ver como no papel").

## Checklist de teste antes de publicar (OCAD 10 e OOM)

Para cada um dos dois programas, com um projeto em Florianópolis (declinação ≈ −20°, grivação ≈ −19°):

1. A folha (A4) aparece **em pé**, sem cantos vazios: satélite e curvas preenchem o papel.
2. As curvas coincidem com o satélite (sem deslocamento nem rotação extra).
3. A georreferência mostra a declinação usada no "Definir Local" e a grivação do log.
4. Curvas mestras no símbolo 102 (testar com equidistância 2,5 m e 5 m).
5. Projeto antigo (folha criada na 0.1.x) ainda exporta e abre.
6. Ajustar Folha (no QGIS): mover, trocar escala/papel/orientação e conferir que a
   exportação seguinte sai com a folha nova, em pé.
7. Ajustar ao limite (no QGIS): desenhar um limite, ajustar e conferir que a folha o
   contém com folga; testar um limite grande demais (pergunta da escala).
8. Tipos de mapa: um projeto Escolar (1:2.000) exporta com a paleta ISSprOM e curvas
   de 2 m com mestras a cada 10 m.
9. Assistente: num QGIS novo ele abre sozinho; seguir o fluxo inteiro só pelos links do
   painel; ajustar a folha e ver curvas/exportação ficarem ⚠; fechar, reiniciar o QGIS e
   conferir que continua fechado (o botão na barra reabre).
10. Linhas de norte: no OCAD 10 e no OOM, linhas pretas verticais (paralelas às laterais
    do papel), a cada 30 mm no sprint/escolar e 300 m no terreno na floresta; dá para
    selecionar e cortar uma linha isolada.
11. Rodar no QGIS 3.40 LTR e no QGIS 4 (os testes daqui usaram o QGIS 3.34 sem tela).
