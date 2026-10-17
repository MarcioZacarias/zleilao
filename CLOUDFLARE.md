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

São **duas tarefas**, e a diferença importa:

| Tarefa | Quando | O que faz |
|---|---|---|
| `ZConnect Leilao - coleta` | a cada hora | 2 páginas por fonte — pega o que muda na frente da lista |
| `ZConnect Leilao - coleta (profunda)` | todo dia às 03:30 | 12 páginas por fonte — encontra o que está no fundo do catálogo |

A rasa sozinha não basta, e isso foi medido: depois de 27 ciclos de hora em
hora sem **nenhum** lote novo, a primeira varredura profunda trouxe **200
lotes** que nunca tinham sido vistos. As primeiras páginas de cada fonte mudam
pouco; lote novo costuma entrar ordenado por data de pregão, lá atrás.

A profunda roda de madrugada porque faz muito mais requisições aos sites dos
leiloeiros. Para rodar uma na mão:

```powershell
.gente\coletar.ps1 -Profunda
```

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

**O que funciona aqui:** Dashboard, Usuários, Alertas e Configurações por
inteiro; Fontes e Categorias só em leitura. Itens, Revisão, Incidentes,
Duplicados, Parcerias e Jobs nem aparecem no menu da versão publicada:
dependem do banco de trabalho da coleta (fila de extração, incidentes,
execuções de job), que fica no backend em Python, junto da coleta, onde não há
teto de CPU. Se alguma dessas ações chegar ao Worker, ele responde 501 com o
aviso, em vez de um "Not Found" seco.

Fontes e categorias são espelho do que o agente local envia; uma edição feita
na borda seria desfeita na sincronização seguinte, por isso as rotas de
escrita não existem lá. Já usuários, planos e alertas moram no D1, e é na
Cloudflare que se administram.

| Onde | Para quê |
|---|---|
| `/admin` na Cloudflare | assinantes e planos, alertas, publicidade, textos, limites |
| `http://localhost:5177/admin` (Docker local) | operação da coleta: fontes, categorias, itens, revisão, incidentes, jobs |

**Logo e favicon** se trocam em Configurações > Marca: o upload grava no D1
(`branding_assets`, até 2 MB cada) e vale na hora para vitrine, telas de conta
e painel, sem republicar nada. Os SVGs em `dashboard/public/branding/` são só
o padrão de quando nada foi enviado. O cabeçalho mostra o logo com 36 px de
altura, então o ideal é uma arte horizontal.

A senha não é a mesma do backend local: os formatos de hash são diferentes. O
Worker usa PBKDF2 pelo Web Crypto, porque bcrypt em JS leva dezenas de
milissegundos e não cabe no teto de 10 ms de CPU. O número de iterações é mais
baixo do que se usaria numa base de senhas de usuários, e a defesa contra
tentativa em massa é o bloqueio por origem após 20 erros no dia
(`login_failures`).

### Trocar a senha

Não há tela para isso ainda. O caminho é um script, que pede a senha nova,
gera o hash dela na sua máquina (PBKDF2, o mesmo formato que o Worker
confere), grava o admin direto no D1 e testa o login:

```powershell
powershell -ExecutionPolicy Bypass -File .\edge\redefinir-admin.ps1
powershell -ExecutionPolicy Bypass -File .\edge\redefinir-admin.ps1 -Email outro@email.com
```

O e-mail padrão é `marcio.zacariass@gmail.com`. A senha não fica gravada em
lugar nenhum; quem perdê-la roda o script de novo.

O caminho antigo — `wrangler secret put ADMIN_PASSWORD` e `POST /v1/admin/seed`
— ficou só para o primeiro administrador de uma instalação nova. Para trocar
senha ele é traiçoeiro: o `seed` pode rodar antes de o segredo novo propagar
(e cria o admin com a senha anterior), e o PowerShell 5.1 corrompe acento ao
passar a senha por pipe. O `seed` só funciona enquanto não existe admin;
depois responde 409 e não serve de porta dos fundos.

Se errar a senha 20 vezes no mesmo dia, a origem é bloqueada até o dia
seguinte. Para destravar antes disso:

```powershell
npx wrangler d1 execute zleilao --remote --command "DELETE FROM login_failures"
```

## Contas de assinante

Cadastro, login, verificação de e-mail, recuperação de senha, perfil, filtros
salvos e histórico de alertas rodam no Worker (`edge/src/rotas/conta.ts`), com
o mesmo contrato do backend em Python. Até 13/10/2026 só existiam no Python, e
o cadastro pela vitrine publicada respondia "Not Found".

O que ainda falta para a conta ficar completa:

- **Envio de e-mail.** O Worker não fala SMTP. `edge/src/lib/email.ts` está
  pronto para receber um provedor com API HTTP (Resend, Brevo…); enquanto
  nenhum é ligado, a conta é criada, a resposta diz que o e-mail não pôde ser
  enviado e o assinante fica sem verificar. Esqueci a senha não chega.
- **`public_base_url`** no D1 ainda aponta para `http://localhost:5177`. É
  dele que saem os links dos e-mails: trocar em Configurações > Contas de
  usuário assim que houver provedor.
- **Disparo dos alertas.** Os filtros moram no D1, mas o matcher e o
  dispatcher rodam no agente local contra o Postgres. Falta o agente ler os
  filtros e os assinantes do D1 e devolver os alertas gerados.

Senhas de assinante usam o mesmo PBKDF2 do painel, com o mesmo teto de
iterações imposto pelos 10 ms de CPU. A defesa contra tentativa em massa é a
mesma tabela `login_failures`: 20 erros de login por IP ao dia, e também 10
cadastros por IP ao dia (origem `cadastro:<ip>`).

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

**Desde 11/10/2026 o GitHub Actions não roda nada**: a conta do GitHub está
bloqueada por problema de cobrança ("account is locked due to a billing
issue"), e todo push termina em falha sem executar nenhum passo. Até resolver
isso em github.com/settings/billing, o push só guarda o código; publicar é
com os comandos abaixo.

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
| `006_admin.sql` | `login_failures`, o bloqueio por tentativa do login |
| `007_dedup.sql` | índices de `item_duplicates` e o limiar de fusão (F4) |
| `008_fontes_f4.sql` | fontes novas da F4 (a ingestão só aceita fonte cadastrada) |

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

## Domínio próprio e AdSense

O endereço atual é `*.workers.dev`, subdomínio de plataforma. Para o AdSense
isso é o obstáculo principal: o Google costuma recusar a inscrição, porque o
domínio não é seu e qualquer um pode criar um ali.

`zconnect.ia.br` **não serve para isso hoje**: a zona está numa conta
Cloudflare diferente da que hospeda este projeto, e domínio customizado exige
que zona e Worker estejam na mesma conta.

Verificado em 12/10/2026: **`zleilao.com.br` está disponível** no registro.br
(~R$ 40/ano), e é o mesmo nome do repositório e do Worker.

### Depois de registrar

1. No registro.br, apontar os nameservers para os que a Cloudflare indicar ao
   adicionar o site (Add a site → plano Free).
2. Ligar o domínio aos dois serviços:

```powershell
cd edge      ; npx wrangler deploy          # depois: Workers > zleilao-api > Settings > Domains
cd dashboard ; npx wrangler deploy          # idem para zleilao
```

   Pelo painel é mais direto: **Workers & Pages → o Worker → Settings →
   Domains & Routes → Add → Custom domain**. Sugestão de divisão:

   | Serviço | Endereço |
   |---|---|
   | vitrine | `zleilao.com.br` e `www.zleilao.com.br` |
   | API | `api.zleilao.com.br` |

3. Reconstruir a vitrine apontando para a API nova:

```powershell
cd dashboard
$env:VITE_API_URL="https://api.zleilao.com.br/v1"
npx vite build ; npx wrangler deploy
```

4. Atualizar três arquivos que ainda citam o endereço antigo:
   `dashboard/public/robots.txt` (linha do Sitemap),
   `.github/workflows/cloudflare.yml` (VITE_API_URL) e
   `agente/config.json` (edge_url).

### Checklist do AdSense

- [ ] Domínio próprio apontando para a vitrine
- [x] Política de privacidade em `/privacidade`, com seção de cookies de terceiros
- [x] Termos de uso em `/termos`
- [x] `robots.txt` liberando busca e fichas
- [x] `sitemap.xml` com as fichas publicadas (997 URLs hoje)
- [ ] `ads.txt` com o `pub-...` real (hoje tem um ID de exemplo)
- [ ] Revisão jurídica das duas páginas legais
- [ ] Conta no AdSense e os dois blocos criados

O que ainda pode derrubar a inscrição, mesmo com tudo acima: o Google avalia se
o conteúdo é **próprio**. Agregador que só repete anúncio de terceiro às vezes
é recusado como conteúdo de pouco valor. O que joga a favor aqui é o comparador
FIPE e o score de oportunidade — análise nossa, não cópia da fonte.
