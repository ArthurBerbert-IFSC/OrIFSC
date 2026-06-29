# Handoff — Painel lateral "Gerar Curvas de Nível" (OrIFSC)

Referência visual para reproduzir no `painel.py`. **Veja também a imagem anexada** (o mock).

> ⚠️ **Alvo de renderização: `QTextBrowser` (Qt rich text = subconjunto de HTML4/CSS2).**
> NÃO use: `flexbox`, `gap`, `border-radius`, `box-shadow`, `linear-gradient`, SVG inline.
> USE: `<table>` para layout, `bgcolor`/`width`/`cellpadding` nas células, `<img>` PNG.

---

## Paleta (cores exatas)

| Uso | Hex |
|---|---|
| Acento laranja-picota | `#f1592a` |
| Texto principal | `#23262a` |
| Texto secundário | `#7c828a` |
| Fundo do painel | `#f6f4ef` |
| Cabeçalho (sutil) | `#ffffff` + borda inferior `#e6e2d8` |
| Card / bordas | borda `#e3dfd6`, fundo `#ffffff` |
| Caixa de dica | fundo `#fdf2e9`, borda `#f6d3b8`, texto `#8a5a36` |
| Número do passo | círculo/célula `#f1592a`, texto branco |

## Tipografia
- Título do passo (cabeçalho): ~15px, **bold**, cor `#23262a`
- Rótulo "OrIFSC": ~10px, MAIÚSCULAS, espaçamento amplo, cor `#f1592a`, bold
- Texto dos passos: título ~13px bold `#23262a` + descrição ~12px `#7c828a`

---

## Estrutura do painel (de cima para baixo)

1. **Cabeçalho de marca** — fundo branco, borda inferior. Logo `FLORA.png` (40px) à esquerda + "OrIFSC" (laranja, pequeno) sobre "Gerar Curvas de Nível" (título).
2. **Card de fonte de dados** — célula branca com borda. Ícone do MDT + "MDT Copernicus 30 m" + linha menor "Gratuito · sem chave de API".
3. **Descrição objetiva** (título "O QUE FAZ" em cinza) — **sem numeração**, dois pontos com marcador de bolinha laranja (o texto vem direto do `INSTRUCOES['gerar_curvas']` em `painel.py`):
   - Baixa o **MDT Copernicus 30 m** (gratuito, sem API key) e gera **curvas suavizadas** para a área da folha.
   - **Recorte opcional** — corta as curvas na borda de uma camada (folha ou limite).
   - Marcador = bolinha laranja `#f1592a` (NÃO use número/ordem — o conteúdo pode mudar).
4. **Caixa de dica** — fundo creme: "Deixe *Recortar por* em branco para gerar sem recorte."
5. **Rodapé de logos** — ORIESC · IFSC · FLORA centralizados (já existe em `logos_html()`).

---

## Esqueleto sugerido (QTextBrowser-safe)

```html
<table width="100%" cellspacing="0" cellpadding="0">
  <!-- 1. Cabeçalho -->
  <tr><td bgcolor="#ffffff" style="padding:14px; border-bottom:1px solid #e6e2d8;">
    <table cellspacing="0" cellpadding="0"><tr>
      <td><img src="FLORA.png" height="40"></td>
      <td style="padding-left:12px;">
        <span style="color:#f1592a; font-size:10px;"><b>ORIFSC</b></span><br>
        <span style="color:#23262a; font-size:15px;"><b>Gerar Curvas de Nível</b></span>
      </td>
    </tr></table>
  </td></tr>

  <!-- 3. Descrição (sem número) — bolinha laranja como marcador -->
  <tr><td style="padding:6px 14px;">
    <table cellspacing="0" cellpadding="0"><tr>
      <td valign="top" width="14" style="color:#f1592a;"><b>&bull;</b></td>
      <td style="color:#3a3e43; font-size:12px;">Baixa o <b>MDT Copernicus 30 m</b> e gera curvas suavizadas para a folha.</td>
    </tr></table>
  </td></tr>

  <!-- 4. Dica -->
  <tr><td bgcolor="#fdf2e9" style="padding:10px 14px; color:#8a5a36; font-size:12px;">
    <b style="color:#f1592a;">!</b> Deixe <b>Recortar por</b> em branco para não recortar.
  </td></tr>
</table>
```

> O número arredondado/sombra do mock vira célula retangular laranja — é o limite do Qt. O resto (cor, hierarquia, marca) sai fiel.

## Como ligar no código
Reescreva a entrada `'gerar_curvas'` do dict `INSTRUCOES` (em `acoes/painel.py`) com esse HTML de tabela. O `painel_html()` já antepõe os logos + `<hr>` + título — se este HTML já traz o próprio cabeçalho de marca, passe `titulo=''` para não duplicar.