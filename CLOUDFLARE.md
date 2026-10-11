# ZConnect Leilão na Cloudflare

Escrito para: quem opera o sistema (você).

## O que está no ar

| | |
|---|---|
| Vitrine | https://zleilao.marcio-zacariass.workers.dev |
| API | https://zleilao-api.marcio-zacariass.workers.dev |
| Banco | D1 `zleilao` (`0470ba01-1887-47bc-9201-86f8118d09eb`) |
| Conta | a conta Cloudflare do projeto |

Tudo no plano gratuito.

## Por que a coleta ficou no seu computador

Não é meio-termo — é o que faz as três fontes funcionarem. Dois impedimentos
medidos, nenhum contornável de dentro de um Worker:

- **Parsear a página real do Mega Leilões custa 96 ms de CPU**, contra um teto
  de 10 ms por invocação. Mesmo com HTMLRewriter, que é a ferramenta mais
  rápida da plataforma e já é 3,6× mais rápida que o parser em Python.
- **O Freitas serve cadeia de certificado quebrada.** O `httpx` do Python
  aceita ignorar a validação (`verify_ssl: false`); o `fetch` do Worker não,
  em plano nenhum. Detalhes e a correção que eles precisam fazer em
  `edge/AVISO-FREITAS.md`.

Rodando local, nada do motor precisou ser reescrito: ciclo de vida (RN-005),
deduplicação (RN-004) e score de oportunidade (RN-010) seguem valendo. O
Postgres local também é amortecedor — se a Cloudflare cair, a coleta continua
e o envio se resolve no ciclo seguinte.

```
seu computador                          Cloudflare (grátis)
┌────────────────────────────┐          ┌──────────────────────┐
│ Agendador de Tarefas (1h)  │          │ Worker  zleilao-api  │
│   └─ agente/coletar.ps1    │          │   /ingest/batch      │
│        ├─ pipeline Python  │  HTTPS   │   /v1/portal/*       │
│        │   (Postgres local)│ ───────► │ D1      zleilao      │
│        └─ sync_edge.py     │  token   │ Assets  zleilao      │
└────────────────────────────┘          └──────────────────────┘
```

## Operação do dia a dia

```powershell
# Ver a tarefa agendada
Get-ScheduledTask -TaskName "ZConnect Leilao - coleta"
Get-ScheduledTaskInfo -TaskName "ZConnect Leilao - coleta"

# Rodar agora, sem esperar a hora
Start-ScheduledTask -TaskName "ZConnect Leilao - coleta"

# Acompanhar
Get-Content .\agente\coleta.log -Tail 40 -Wait

# Reenviar tudo (depois de limpar o D1, ou em dúvida)
.\agente\coletar.ps1 -Full
```

O ciclo roda de hora em hora, mas cada fonte só é coletada a cada 4 h
(`scrape_frequency`). Nas horas intermediárias o ciclo confere quem venceu e
envia o que mudou — custa segundos.

## Quando algo não aparece na vitrine

| Sintoma | Onde olhar |
|---|---|
| Vitrine parada no tempo | `agente\coleta.log`. A tarefa rodou? O envio terminou com erro? |
| Lote some depois de aparecer | Ciclo de vida: o lote foi encerrado ou retirado na fonte. Confira em `/lote/<id>`. |
| Lote novo não chega | O pipeline grava no Postgres primeiro. Veja se ele está lá: `docker exec zleilao-db psql -U zleilao -d zleilao -c "select count(*) from items"` |
| Envio falha com 401 | O token do `agente\config.json` saiu de sincronia com o segredo do Worker. Veja "Trocar o token". |
| Envio falha com 503 | A requisição estourou tempo. Diminua `max_pages` no `config.json`. |
| Site no ar mas sem dados | O build foi publicado sem `VITE_API_URL` e caiu em `/api`, que não existe no Pages. Reconstrua com a variável. |

## Trocar o token de ingestão

O segredo do Worker não é legível de volta; para trocar, define-se dos dois
lados:

```powershell
# 1. Gere um token e coloque em agente\config.json (campo edge_token)
python -c "import secrets; print(secrets.token_urlsafe(32))"

# 2. Mande o mesmo valor para o Worker
cd edge
Get-Content ..\agente\config.json | ConvertFrom-Json |
  Select-Object -ExpandProperty edge_token | npx wrangler secret put INGEST_TOKEN
```

## Painel administrativo

`https://zleilao.marcio-zacariass.workers.dev/admin`

O acesso sai dos segredos `ADMIN_EMAIL` e `ADMIN_PASSWORD` do Worker. **Troque
a senha inicial no primeiro acesso** — ela foi definida para destravar a
entrada, não para ficar.

**Só duas telas funcionam aqui: o painel inicial e Configurações.** As outras
(Fontes, Itens, Revisão, Incidentes, Duplicados, Jobs) continuam no backend em
Python, que roda junto da coleta — é lá que está o banco de trabalho, com a
fila de extração e o histórico de execuções, e lá não há teto de CPU.

| Onde | Para quê |
|---|---|
| `/admin` na Cloudflare | configuração que a vitrine lê: publicidade, textos, limites |
| `http://localhost:5177/admin` (Docker local) | operação da coleta: fontes, revisão, incidentes, jobs |

A senha não é a mesma do backend local: os formatos de hash são diferentes. O
Worker usa PBKDF2 pelo Web Crypto, porque bcrypt em JS leva dezenas de
milissegundos e não cabe no teto de 10 ms de CPU. O número de iterações é mais
baixo do que se usaria numa base de senhas de usuários, e a defesa contra
tentativa em massa é o bloqueio por origem após 20 erros no dia
(`login_failures`).

### Trocar a senha

Não há tela para isso ainda; são três comandos. O `seed` recria o
administrador a partir do segredo, e só funciona enquanto não existe nenhum —
depois responde 409 e não serve de porta dos fundos.

```powershell
cd edge
npx wrangler secret put ADMIN_PASSWORD   # digite a nova senha e Enter

# apaga o admin atual e zera o bloqueio por tentativa
npx wrangler d1 execute zleilao --remote --command "DELETE FROM users WHERE role='admin'; DELETE FROM login_failures;"

# recria com a senha nova
curl -X POST https://zleilao-api.marcio-zacariass.workers.dev/v1/admin/seed
```

Se errar a senha 20 vezes no mesmo dia, a origem é bloqueada até o dia
seguinte. Para destravar antes disso:

```powershell
npx wrangler d1 execute zleilao --remote --command "DELETE FROM login_failures"
```

## Publicidade

Configurável em **Admin → Configurações → Publicidade**, sem precisar de SQL.
Desligada por padrão. Dois modos, que não competem:

**Próprio** — espaço vendido direto, tipicamente ao leiloeiro que já está na
vitrine. Rende mais por impressão e não depende de aprovação de ninguém, mas
alguém precisa vender. É o mesmo caminho do destaque pago da onda 5.

```sql
-- edge> npx wrangler d1 execute zleilao --remote --command "..."
UPDATE system_settings SET value='1'        WHERE key='ads_enabled';
UPDATE system_settings SET value='proprio'  WHERE key='ads_provider';
UPDATE system_settings SET value='https://.../banner.png' WHERE key='ads_proprio_busca_imagem';
UPDATE system_settings SET value='https://site-do-anunciante' WHERE key='ads_proprio_busca_alvo';
UPDATE system_settings SET value='Leilões de veículos em SP' WHERE key='ads_proprio_busca_texto';
```

**AdSense** — paga por impressão e clique, sem negociar com ninguém, mas o
Google precisa aprovar o site. Três coisas pesam na aprovação e hoje faltam:

1. **Domínio próprio.** Subdomínio de plataforma (`.workers.dev`) costuma ser
   recusado. É o maior impedimento.
2. **Política de privacidade e termos de uso**, com menção a cookies de
   terceiros.
3. **Conteúdo próprio.** Um agregador que só repete anúncio de terceiro pode
   ser enquadrado como conteúdo de pouco valor. O comparador FIPE e o score de
   oportunidade jogam a favor, porque são análise nossa.

```sql
UPDATE system_settings SET value='1'        WHERE key='ads_enabled';
UPDATE system_settings SET value='adsense'  WHERE key='ads_provider';
UPDATE system_settings SET value='ca-pub-XXXXXXXXXXXXXXXX' WHERE key='ads_adsense_client';
UPDATE system_settings SET value='1234567890' WHERE key='ads_adsense_slot_busca';
UPDATE system_settings SET value='0987654321' WHERE key='ads_adsense_slot_ficha';
```

Em qualquer um dos dois o bloco é rotulado como publicidade, entra como célula
do grid (não desloca a lista) e o link leva `rel="sponsored"`. Impressões e
cliques ficam em `ad_events`, agregados por dia:

```sql
SELECT posicao, tipo, SUM(total) FROM ad_events
 WHERE dia >= date('now','-30 days') GROUP BY posicao, tipo;
```

## Publicar à mão

```powershell
cd edge      ; npx wrangler deploy                      # API
cd dashboard ; $env:VITE_API_URL="https://zleilao-api.marcio-zacariass.workers.dev/v1"
               npx vite build ; npx wrangler deploy      # vitrine
```

O build **precisa** da variável: sem ela cai em `/api`, que só existe atrás do
nginx do Docker, e a vitrine fica sem dados.

## Migrações do banco

Os arquivos em `edge/schema/` são aplicados em ordem e são idempotentes.

```powershell
cd edge
npx wrangler d1 execute zleilao --remote --file schema/001_schema.sql
```

| Arquivo | O quê |
|---|---|
| `001_schema.sql` | 26 tabelas, índices, FTS5 e gatilhos |
| `002_seed_dev.sql` | três lotes de teste, só para o banco local |
| `003_municipios.sql` | 5.618 municípios (gerado de `backend/app/data/municipios.json`) |
| `004_seed.sql` | categorias, campos, fontes e configuração (exportados do Postgres) |
| `005_ads.sql` | configuração de publicidade e `ad_events` |

Quatro decisões do esquema que mudam o significado das colunas estão
documentadas no cabeçalho do `001_schema.sql` — dinheiro em centavos, data como
texto ISO em horário de Brasília, busca em FTS5 sem stemming, JSON como texto.

## Limites do plano gratuito, e onde estamos

| | Teto | Hoje |
|---|---|---|
| Requisições ao Worker | 100 mil/dia | centenas |
| CPU por invocação | 10 ms | leitura e gravação, sem parsing |
| Escritas no D1 | 100 mil/dia | ~7,4 mil |
| Armazenamento no D1 | 5 GB | ~2 MB |

O aperto não é volume: é CPU por invocação, e é por isso que o parsing ficou
fora. Com tração, o caminho é o Workers Paid (US$ 5/mês, 30 s de CPU), que
traria a coleta para a borda — menos o Freitas, enquanto o certificado deles
estiver quebrado.
