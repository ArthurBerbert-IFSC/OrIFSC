# 🛠️ Setup de Desenvolvimento — OrIFSC Plugin com Hot Reload

Este guia configura o plugin para desenvolvimento com recarga automática (hot reload).

## 1️⃣ Pré-requisitos

- **QGIS 3.16+** instalado
- **Plugin Reloader** instalado no QGIS (via Plugins → Gerenciar e Instalar)
- **PowerShell** (Windows) ou terminal com permissões de admin

## 2️⃣ Setup Automático (Symlink)

### Windows (PowerShell como Admin)

```powershell
# 1. Clique com botão direito em PowerShell → "Executar como Administrador"
# 2. Navegue para a pasta do projeto:
cd "d:\Visual Studio\OrIFSC\OrIFSC"

# 3. Execute o script:
.\setup-dev-symlink.ps1
```

O script irá:
- ✓ Criar um symlink de `PluginQgis/` para o diretório de plugins do QGIS
- ✓ Habilitar reload automático no código Python
- ✓ Mostrar próximos passos

## 3️⃣ Configurar no QGIS (primeira vez)

1. **Abre QGIS**
2. **Plugins** → **Gerenciar e Instalar Plugins**
3. Busca: `OrIFSC`
4. Clica em **Instalar**
5. Espera a barra de carregamento

## 4️⃣ Workflow de Desenvolvimento

### Fluxo rápido a cada mudança:

```
┌─────────────────────────────┐
│ 1. Edita código em VS Code  │  (arquivo já aberto)
│    ex: gerar_curvas.py      │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│ 2. Salva (Ctrl+S)           │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│ 3. QGIS: Plugins →          │  (ou clica o botão Reloader)
│    Plugin Reloader →         │
│    Recarregar Plugins       │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│ 4. Seleciona "OrIFSC"       │  (marca checkbox)
│    → Recarregar             │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│ 5. Testa na Caixa de        │  (mudança já está viva)
│    Ferramentas              │
└─────────────────────────────┘
```

### Exemplo: editar `gerar_curvas.py`

```python
# Edita PluginQgis/algorithms/gerar_curvas.py
def shortHelpString(self):
    return ('Meu novo texto de ajuda...')
```

Salva → Reload → Abre a Caixa de Ferramentas → vê o novo texto. ✨

## 5️⃣ Estrutura de Pastas

```
OrIFSC (symlink) → d:\Visual Studio\OrIFSC\OrIFSC\PluginQgis\
├── __init__.py              (com reload automático)
├── orifsc.py                (ponto de entrada / menu)
├── provider.py              (com reload automático)
├── metadata.txt             (informações do plugin)
├── icons/
│   └── icon.png
├── acoes/                    (ações do menu)
│   ├── __init__.py
│   ├── comum.py              (estado compartilhado no projeto)
│   ├── carregar_satelite.py  (Passo 1)
│   ├── definir_local.py      (Passo 2 — define local e já cria a folha)
│   ├── criar_folha.py        (parte do Passo 2)
│   └── criar_limite.py       (Passo 3)
└── algorithms/
    ├── __init__.py
    ├── gerar_curvas.py       (Passo 4)
    └── exportar_ocad.py      (Passo 5)
```

## 🔧 Troubleshooting

### "Symlink não foi criado"
- Verifique se rodou como **Administrador**
- Se a pasta `OrIFSC` já existe, remova manualmente primeiro:
  ```powershell
  Remove-Item "C:\Users\$env:USERNAME\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins\OrIFSC" -Force
  ```
- Rode o script novamente

### "Plugin não aparece na Caixa de Ferramentas"
- Vai em **Plugins** → **Gerenciar e Instalar**
- Busca `OrIFSC`
- Marca **Ativo**
- Reinicia QGIS

### "Mudança não aparece após reload"
- Salve o arquivo (**Ctrl+S**)
- Abra a Caixa de Ferramentas (se fechar, abre novamente)
- Rode **Plugin Reloader** novamente
- Espere alguns segundos

### "Erros de sintaxe depois de reload"
Se houver erro de sintaxe no código, o reload pode falhar silenciosamente:
- Verifique a **Compilação** do arquivo:
  ```powershell
  cd "d:\Visual Studio\OrIFSC\OrIFSC"
  python -m py_compile PluginQgis/algorithms/gerar_curvas.py
  ```
- Corrija o erro de sintaxe
- Rode reload novamente

## 📝 Notas

- O reload automático está configurado em `__init__.py` e `provider.py`
- Qualquer arquivo em `PluginQgis/` muda imediatamente (via symlink)
- Às vezes é bom fechar e reabrir a Caixa de Ferramentas entre reloads

---

**💡 Dica:** mantenha QGIS aberto enquanto edita — reload é muito mais rápido que reiniciar! 🚀
