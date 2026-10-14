# =====================================================================
# ZConnect Leilão — redefine o administrador do painel na Cloudflare.
#
# Faz numa tacada os passos de "Trocar a senha" do CLOUDFLARE.md: grava
# os segredos do Worker, apaga o admin atual e o bloqueio por tentativa,
# recria o admin pelo /admin/seed e testa o login no fim.
#
# Precisa do Wrangler logado na conta da Cloudflare (npx wrangler whoami).
#
# Uso (PowerShell, de qualquer pasta):
#   .\edge\redefinir-admin.ps1
#   .\edge\redefinir-admin.ps1 -Email outro@email.com
# =====================================================================
[CmdletBinding()]
param(
    [string]$Email = "marcio.zacariass@gmail.com",
    [string]$Api = "https://zleilao-api.marcio-zacariass.workers.dev",
    [string]$Site = "https://zleilao.marcio-zacariass.workers.dev"
)

$ErrorActionPreference = "Stop"

# $PSScriptRoot nao e' resolvido dentro do bloco param() no PowerShell 5.1.
$aqui = $PSScriptRoot
if (-not $aqui) { $aqui = Split-Path -Parent $MyInvocation.MyCommand.Path }
Set-Location $aqui

$senha = Read-Host "Nova senha do painel (minimo 8 caracteres)"
if ($senha.Length -lt 8) {
    Write-Host "Senha curta demais." -ForegroundColor Red
    exit 1
}

Write-Host "1/4 Gravando segredos no Worker..."
# O Wrangler le o valor da entrada padrao quando nao ha terminal interativo
# e descarta a quebra de linha do fim.
$Email | npx wrangler secret put ADMIN_EMAIL
if ($LASTEXITCODE -ne 0) { exit 1 }
$senha | npx wrangler secret put ADMIN_PASSWORD
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host "2/4 Apagando o admin atual e o bloqueio por tentativa..."
npx wrangler d1 execute zleilao --remote --command "DELETE FROM users WHERE role='admin'; DELETE FROM login_failures;"
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host "3/4 Recriando o admin..."
# `curl` no Windows PowerShell e' apelido de Invoke-WebRequest e nao aceita
# -X; o comando em forma de curl falha aqui. Invoke-RestMethod resolve.
$seed = Invoke-RestMethod -Method Post -Uri "$Api/v1/admin/seed"
Write-Host "    criado: $($seed.criado)"

Write-Host "4/4 Testando o login..."
$corpo = @{ email = $Email; password = $senha } | ConvertTo-Json
$login = Invoke-RestMethod -Method Post -Uri "$Api/v1/auth/login" -ContentType "application/json" -Body $corpo

Write-Host ""
Write-Host "Pronto. Entre em $Site/admin" -ForegroundColor Green
Write-Host "  e-mail: $Email"
Write-Host "  papel : $($login.role)"
