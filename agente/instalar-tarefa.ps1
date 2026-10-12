# =====================================================================
# Agenda o ciclo de coleta no Agendador de Tarefas do Windows.
# Rodar UMA VEZ, como Administrador:
#   powershell -ExecutionPolicy Bypass -File .\agente\instalar-tarefa.ps1
# =====================================================================
[CmdletBinding()]
param(
    [string]$Nome = "ZConnect Leilao - coleta",
    # As fontes são coletadas a cada 4 h; de hora em hora o ciclo apenas
    # confere quem venceu e envia o que mudou. Rodar mais que isso só
    # gera requisição à toa nos sites dos leiloeiros.
    [int]$IntervaloHoras = 1
)

$ErrorActionPreference = "Stop"
$aqui = $PSScriptRoot
if (-not $aqui) { $aqui = Split-Path -Parent $MyInvocation.MyCommand.Path }
$script = Join-Path $aqui "coletar.ps1"
if (-not (Test-Path $script)) { throw "coletar.ps1 não encontrado" }
if (-not (Test-Path (Join-Path $aqui "config.json"))) {
    throw "Crie o agente\config.json a partir de config.exemplo.json antes de agendar."
}

$acao = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`""

# Começa 5 min após instalar e repete indefinidamente.
$gatilho = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(5) `
    -RepetitionInterval (New-TimeSpan -Hours $IntervaloHoras)

# StartWhenAvailable: se o computador estiver desligado na hora marcada,
# o ciclo roda assim que ligar, em vez de pular a janela em silêncio.
$cfg = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -DontStopOnIdleEnd -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -MultipleInstances IgnoreNew -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 10)

Register-ScheduledTask -TaskName $Nome -Action $acao -Trigger $gatilho `
    -Settings $cfg -Description "Coleta os leilões e envia para a Cloudflare" -Force | Out-Null

# ── Varredura profunda, uma vez por dia ───────────────────────────────
# O ciclo de hora em hora só vê as primeiras páginas de cada fonte, onde a
# lista muda pouco. Sem uma passada funda, lote que entra no fim do catálogo
# nunca é descoberto. Vai de madrugada porque faz muito mais requisições.
$nomeFundo = "$Nome (profunda)"
$acaoFunda = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`" -Profunda"
$gatilhoFundo = New-ScheduledTaskTrigger -Daily -At "03:30"
$cfgFundo = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -DontStopOnIdleEnd -ExecutionTimeLimit (New-TimeSpan -Hours 4) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $nomeFundo -Action $acaoFunda -Trigger $gatilhoFundo `
    -Settings $cfgFundo -Description "Varredura profunda diária das fontes" -Force | Out-Null

Write-Host "Tarefa '$Nome' agendada: a cada $IntervaloHoras h, começando em 5 min."
Write-Host "Tarefa '$nomeFundo' agendada: todo dia às 03:30."
Write-Host "Conferir:  Get-ScheduledTask -TaskName '$Nome'"
Write-Host "Rodar já:  Start-ScheduledTask -TaskName '$Nome'"
Write-Host "Remover:   Unregister-ScheduledTask -TaskName '$Nome' -Confirm:`$false"
