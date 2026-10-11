# =====================================================================
# ZConnect Leilão — ciclo de coleta no computador do operador.
# ---------------------------------------------------------------------
# Sobe o Postgres local se preciso, roda o pipeline (coleta, normaliza,
# classifica, ciclo de vida, deduplica, calcula o score) e envia para a
# Cloudflare só o que mudou.
#
# Por que o pipeline fica aqui e não na borda: parsear a página real do
# Mega Leilões custa 96 ms de CPU contra um teto de 10 ms por invocação
# do plano gratuito, e o Freitas exige ignorar um certificado com cadeia
# quebrada — coisa que o httpx do Python aceita e o fetch do Worker não.
#
# Agendar (uma vez, como Administrador):
#   .\agente\instalar-tarefa.ps1
# =====================================================================
[CmdletBinding()]
param(
    # Sem --full o envio leva só o que mudou desde a última execução.
    [switch]$Full,
    [string]$ConfigPath
)

$ErrorActionPreference = "Stop"

# $PSScriptRoot nao e' resolvido dentro do bloco param() no PowerShell 5.1,
# entao os caminhos sao montados aqui, ja' no corpo do script.
$aqui = $PSScriptRoot
if (-not $aqui) { $aqui = Split-Path -Parent $MyInvocation.MyCommand.Path }
if (-not $ConfigPath) { $ConfigPath = Join-Path $aqui "config.json" }
$raiz = Split-Path -Parent $aqui
$log = Join-Path $aqui "coleta.log"

function Escrever($msg, $nivel = "INFO") {
    $linha = "{0} [{1}] {2}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $nivel, $msg
    Write-Host $linha
    Add-Content -Path $log -Value $linha -Encoding utf8
}

# Log sem rotação vira arquivo de gigabytes depois de alguns meses.
if ((Test-Path $log) -and ((Get-Item $log).Length -gt 5MB)) {
    Move-Item $log "$log.old" -Force
}

if (-not (Test-Path $ConfigPath)) {
    Escrever "config.json não encontrado em $ConfigPath. Copie config.exemplo.json e preencha." "ERRO"
    exit 1
}
$cfg = Get-Content $ConfigPath -Raw -Encoding utf8 | ConvertFrom-Json
if (-not $cfg.edge_url -or -not $cfg.edge_token) {
    Escrever "config.json precisa de edge_url e edge_token." "ERRO"
    exit 1
}

$python = Join-Path $raiz "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Escrever "ambiente Python não encontrado em $python" "ERRO"
    exit 1
}

Escrever "=== ciclo iniciado ==="

# ── 1. Banco local ────────────────────────────────────────────────────
# O Postgres é o banco de trabalho do pipeline e o amortecedor: se a
# Cloudflare estiver fora, a coleta continua e o envio se resolve depois.
$docker = Get-Command docker -ErrorAction SilentlyContinue
if (-not $docker) { Escrever "Docker não encontrado no PATH" "ERRO"; exit 1 }

$dbNoAr = (docker ps --filter "name=zleilao-db" --format "{{.Names}}" 2>$null) -contains "zleilao-db"
if (-not $dbNoAr) {
    Escrever "subindo o Postgres local..."
    Push-Location $raiz
    docker compose --env-file .env -p zconnect_leilao `
        -f docker/docker-compose.yml -f docker/docker-compose.override.yml up -d postgres 2>&1 | Out-Null
    Pop-Location

    $pronto = $false
    foreach ($i in 1..30) {
        Start-Sleep -Seconds 2
        docker exec zleilao-db pg_isready -U zleilao *> $null
        if ($LASTEXITCODE -eq 0) { $pronto = $true; break }
    }
    if (-not $pronto) { Escrever "Postgres não respondeu a tempo" "ERRO"; exit 1 }
    Escrever "Postgres pronto"
}

# ── 2. Pipeline ───────────────────────────────────────────────────────
$senha = (Select-String -Path (Join-Path $raiz ".env") -Pattern '^POSTGRES_PASSWORD=(.*)$').Matches.Groups[1].Value
$porta = (Select-String -Path (Join-Path $raiz ".env") -Pattern '^DB_PORT=(.*)$').Matches.Groups[1].Value
if (-not $porta) { $porta = "5439" }

$env:DATABASE_URL = "postgresql+asyncpg://zleilao:$senha@localhost:$porta/zleilao"
$env:SCHEDULER_ENABLED = "false"

# O Python registra log em stderr. No PowerShell 5.1, com
# ErrorActionPreference = Stop, cada linha de stderr de um executável nativo
# vira exceção e aborta o ciclo — mesmo quando o processo termina com 0. Daí
# rodar as chamadas com "Continue" e julgar pelo código de saída, que é o
# único sinal confiável aqui.
function Invocar($rotulo, $argumentos) {
    $anterior = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $saidaArq = Join-Path $env:TEMP "zleilao-$rotulo.log"
        & $python @argumentos *> $saidaArq
        $codigo = $LASTEXITCODE
        if (Test-Path $saidaArq) {
            # O PowerShell embrulha stderr de executável nativo em ErrorRecord
            # e despeja o rastro dele no arquivo. Essas linhas não dizem nada
            # sobre a coleta e só atrapalham a leitura do log.
            $ruido = '^\s*(\+ CategoryInfo|\+ FullyQualifiedErrorId|No linha:|At line:|\+\s*~+|\s*~+\s*$)'
            Get-Content $saidaArq -Encoding utf8 |
                Where-Object { $_.Trim() -and $_ -notmatch $ruido } |
                ForEach-Object { Escrever "  $_" }
            Remove-Item $saidaArq -Force -ErrorAction SilentlyContinue
        }
        return $codigo
    } finally {
        $ErrorActionPreference = $anterior
    }
}

Push-Location (Join-Path $raiz "backend")
try {
    Escrever "coletando das fontes..."
    $maxPaginas = if ($cfg.max_pages) { $cfg.max_pages } else { 2 }
    $codigo = Invocar "pipeline" @("scripts/run_pipeline_once.py", "--max-pages", "$maxPaginas")
    if ($codigo -ne 0) { Escrever "pipeline terminou com código $codigo" "AVISO" }

    # ── 3. Envio ──────────────────────────────────────────────────────
    Escrever "enviando para a Cloudflare..."
    $argumentos = @("scripts/sync_edge.py", "--url", $cfg.edge_url, "--token", $cfg.edge_token)
    if ($Full) { $argumentos += "--full" }
    $codigo = Invocar "sync" $argumentos
    if ($codigo -ne 0) {
        Escrever "envio falhou (código $codigo). A próxima execução tenta de novo." "ERRO"
        exit 1
    }
} finally {
    Pop-Location
}

Escrever "=== ciclo concluído ==="
