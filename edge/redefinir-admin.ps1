# =====================================================================
# ZConnect Leilão — redefine o administrador do painel na Cloudflare.
#
# Gera o hash da senha aqui mesmo (PBKDF2-SHA256, o formato que o Worker
# confere em edge/src/lib/auth.ts) e grava o admin direto no D1. Não passa
# pelos segredos ADMIN_EMAIL/ADMIN_PASSWORD nem pelo /admin/seed: a
# primeira versão fazia isso e a senha chegava errada ao Worker — ou o seed
# rodava antes de o segredo novo propagar, ou a senha com acento era
# corrompida no pipe do PowerShell 5.1, que fala ASCII com programas
# externos. Aqui a senha não sai da máquina: só o hash viaja.
#
# Precisa do Wrangler logado na conta da Cloudflare (npx wrangler whoami).
#
# Uso (PowerShell):
#   powershell -ExecutionPolicy Bypass -File .\edge\redefinir-admin.ps1
#   powershell -ExecutionPolicy Bypass -File .\edge\redefinir-admin.ps1 -Email outro@email.com
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

$Email = $Email.Trim().ToLower()
$senha = Read-Host "Nova senha do painel (minimo 8 caracteres)"
if ($senha.Length -lt 8) {
    Write-Host "Senha curta demais." -ForegroundColor Red
    exit 1
}

# Mesmo formato de edge/src/lib/auth.ts: pbkdf2$<iteracoes>$<salt>$<hash>,
# salt e hash em base64, 12.000 iteracoes (o teto que cabe nos 10 ms de CPU).
$iteracoes = 12000
$salt = New-Object byte[] 16
[System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($salt)
$derivador = [System.Security.Cryptography.Rfc2898DeriveBytes]::new(
    [System.Text.Encoding]::UTF8.GetBytes($senha), $salt, $iteracoes,
    [System.Security.Cryptography.HashAlgorithmName]::SHA256)
$hash = "pbkdf2`$$iteracoes`$" + [Convert]::ToBase64String($salt) + "`$" + [Convert]::ToBase64String($derivador.GetBytes(32))

Write-Host "1/2 Gravando o admin no D1..."
# O SQL vai por arquivo: o hash tem cifroes, e cifrao numa linha de comando
# do PowerShell vira tentativa de variavel.
$emailSql = $Email.Replace("'", "''")
$sql = @"
DELETE FROM login_failures;
DELETE FROM users WHERE role = 'admin';
INSERT INTO users (email, hashed_password, name, role, is_active, created_at)
VALUES ('$emailSql', '$hash', 'Administrador', 'admin', 1, datetime('now', '-3 hours'));
"@
$arquivo = Join-Path $env:TEMP "zleilao-admin.sql"
[System.IO.File]::WriteAllText($arquivo, $sql, (New-Object System.Text.UTF8Encoding $false))
try {
    npx wrangler d1 execute zleilao --remote --file $arquivo
    if ($LASTEXITCODE -ne 0) { exit 1 }
} finally {
    Remove-Item $arquivo -Force -ErrorAction SilentlyContinue
}

Write-Host "2/2 Testando o login..."
# Corpo em bytes UTF-8: o Invoke-RestMethod do 5.1 manda texto em Latin-1
# e uma senha com acento chegaria diferente da que foi gravada.
$json = @{ email = $Email; password = $senha } | ConvertTo-Json -Compress
$corpo = [System.Text.Encoding]::UTF8.GetBytes($json)
$login = Invoke-RestMethod -Method Post -Uri "$Api/v1/auth/login" -ContentType "application/json; charset=utf-8" -Body $corpo

Write-Host ""
Write-Host "Pronto. Entre em $Site/admin" -ForegroundColor Green
Write-Host "  e-mail: $Email"
Write-Host "  papel : $($login.role)"
