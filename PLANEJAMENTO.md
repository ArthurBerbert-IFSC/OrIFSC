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
- [ ] **Parte 3 — Ajustar ao limite**: calcula orientação/papel/posição que cabem no limite (regra da decisão 6).
- [ ] **Parte 4 — Tipos de mapa**: presets Sprint / Floresta / Personalizado.
- [ ] **Parte 5 — Painel assistente**: etapas com ✓ / ▶ / ⚠, avisa sem bloquear, marca etapas desatualizadas.
- [ ] **Parte 6 — Linhas de norte magnético** como objetos no `.ocd`/`.omap`, no espaçamento da norma.

Presets iniciais (parte 4 — validar com a FLORA):

| Tipo | Norma | Escala | Equidistância | Papel |
|---|---|---|---|---|
| Sprint / urbano | ISSprOM 2019-2 | 1:4.000 | 2,5 m | A4 |
| Floresta / rural | ISOM 2017-2 | 1:10.000 | 5 m | A4 |
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
