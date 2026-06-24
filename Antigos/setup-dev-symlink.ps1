# Script para configurar symlink e preparar plugin para desenvolvimento com reload
# Precisa rodar como Admin

# Verifica se esta rodando como Admin
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "Este script precisa rodar como Administrador!" -ForegroundColor Red
    Write-Host "Clique com botao direito em PowerShell > Executar como Administrador"
    exit 1
}

$pluginSourceDir = "d:\Visual Studio\OrIFSC\OrIFSC\PluginQgis"
$pluginsTargetDir = "C:\Users\$env:USERNAME\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins"
$pluginLinkPath = Join-Path $pluginsTargetDir "OrIFSC"

Write-Host "Setup de Desenvolvimento - OrIFSC Plugin com Reload" -ForegroundColor Cyan
Write-Host "====================================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path $pluginsTargetDir)) {
    Write-Host "Criando diretorio de plugins..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Path $pluginsTargetDir -Force | Out-Null
}

if (Test-Path $pluginLinkPath) {
    Write-Host "Removendo symlink anterior..." -ForegroundColor Yellow
    $item = Get-Item $pluginLinkPath -Force
    if ($item.LinkType -eq "SymbolicLink") {
        Remove-Item $pluginLinkPath -Force
        Write-Host "[OK] Symlink removido" -ForegroundColor Green
    }
    else {
        Write-Host "[ERRO] Pasta existe mas nao eh symlink" -ForegroundColor Red
        Write-Host "      Remova manualmente: $pluginLinkPath" -ForegroundColor Yellow
        exit 1
    }
}

Write-Host "Criando symlink..." -ForegroundColor Yellow
New-Item -ItemType SymbolicLink -Path $pluginLinkPath -Target $pluginSourceDir -Force | Out-Null
Write-Host "[OK] Symlink criado" -ForegroundColor Green
Write-Host ""

if (Test-Path $pluginLinkPath) {
    Write-Host "[OK] Plugin pronto em: $pluginLinkPath" -ForegroundColor Green
}
else {
    Write-Host "[ERRO] Falha ao criar symlink" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Proximos passos:" -ForegroundColor Cyan
Write-Host "1. Abre o QGIS"
Write-Host "2. Plugins > Gerenciar e Instalar > OrIFSC > Instalar"
Write-Host "3. Plugins > Plugin Reloader > Recarregar Plugins"
Write-Host "4. Abre a Caixa de Ferramentas (Processing Toolbox)"
Write-Host "5. Edita o codigo e clica Recarregar Plugins para testar"
Write-Host ""
Write-Host "Desenvolvimento pronto para hot-reload!" -ForegroundColor Green
