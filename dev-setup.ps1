# Aponta a pasta de plugins do QGIS para a fonte deste repositorio (pasta OrIFSC/),
# usando uma JUNCTION de diretorio -- NAO precisa rodar como Administrador.
#
# Assim, editar a pasta OrIFSC/ no VSCode reflete direto no QGIS (use o Plugin Reloader),
# e e a mesma fonte que o workflow publica no plugins.qgis.org.
#
# >>> Rode com o QGIS FECHADO. <<<
#   Botao direito no arquivo > "Executar com PowerShell"  (ou)  powershell -File dev-setup.ps1

$ErrorActionPreference = "Stop"

$pluginSource = Join-Path $PSScriptRoot "OrIFSC"
$pluginsDir   = Join-Path $env:APPDATA "QGIS\QGIS3\profiles\default\python\plugins"
$linkPath     = Join-Path $pluginsDir "OrIFSC"

Write-Host "Setup de desenvolvimento - OrIFSC (junction)" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan

if (-not (Test-Path $pluginSource)) {
    Write-Host "[ERRO] Fonte do plugin nao encontrada: $pluginSource" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $pluginsDir)) {
    New-Item -ItemType Directory -Path $pluginsDir -Force | Out-Null
}

if (Test-Path $linkPath) {
    $item = Get-Item $linkPath -Force
    if ($item.LinkType) {
        Write-Host "Removendo link/junction anterior..." -ForegroundColor Yellow
        Remove-Item $linkPath -Force
    }
    else {
        $backup = "${linkPath}._backup_$(Get-Date -Format yyyyMMdd_HHmmss)"
        Write-Host "Pasta real encontrada; movendo para backup:" -ForegroundColor Yellow
        Write-Host "  $backup" -ForegroundColor Yellow
        Rename-Item $linkPath $backup
    }
}

New-Item -ItemType Junction -Path $linkPath -Target $pluginSource | Out-Null

if ((Get-Item $linkPath -Force).LinkType) {
    Write-Host "[OK] Junction criada:" -ForegroundColor Green
    Write-Host "  $linkPath  ->  $pluginSource" -ForegroundColor Green
    Write-Host ""
    Write-Host "Proximos passos:" -ForegroundColor Cyan
    Write-Host "  1. Abra o QGIS e ative o plugin OrIFSC"
    Write-Host "  2. Edite OrIFSC/ no VSCode e use o Plugin Reloader para testar"
}
else {
    Write-Host "[ERRO] Falha ao criar a junction." -ForegroundColor Red
    exit 1
}
