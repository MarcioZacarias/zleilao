# ZConnect Leilão — bíblia do sistema

Documento de transferência de contexto. O que o sistema é, como funciona por dentro e
quais armadilhas já se conhecem. Estado: **18/09/2026, F1 (MVP Leilão) implementada,
ainda não publicada no servidor**. Especificação em `docs/EF-ZLE-001-ZConnect-Leilao.md`;
desvios em `docs/DECISOES.md`.

---

## 1. A ideia

Radar de leilões de veículos. O sistema **coleta** lotes dos sites de leiloeiros
oficiais, **normaliza** a descrição em campos estruturados por categoria, **publica**
numa vitrine com busca e **manda o usuário para a fonte oficial**. Não realiza leilão,
não recebe lance, não intermedeia nada (EF, seção 7).

| Público | Onde | O que vê |
|---|---|---|
| Visitante | `/` | busca, ficha do lote, página do pregão, botão "Ver no leilão oficial" |
| Operador | `/admin` | fontes, categorias/campos, itens, revisão, incidentes, duplicados, jobs, config |

Herdado do ZConnect Promo: infraestrutura de compose isolado, tabela `system_settings`,
`BaseScraper` (httpx + atraso aleatório + retry), branding no banco, auth JWT.
**Não** herdado: pipeline LLM (o Promo não tem), APScheduler de verdade, envio WhatsApp
(fica para a F3 e não usa o dispatcher de grupos).

---

## 2. Arquitetura

```
nginx do host (TLS) -> zleilao-dashboard (nginx + SPA React; /api -> proxy)
                          -> zleilao-backend (FastAPI :8000)
                              -> zleilao-db (PostgreSQL 16)
```

`baseURL: "/api"` no axios já vira `/v1` no backend (reescrita no nginx do dashboard e
no proxy do Vite). O nginx do host só repassa para 127.0.0.1:5177.

```
backend/app/
  main.py               FastAPI, lifespan (init_db + seeds + scheduler)
  config.py             pydantic BaseSettings (.env: banco, SECRET_KEY, admin inicial)
  database.py           engine async, create_all + DDL extra (pg_trgm, GIN em JSONB/tsvector)
  models.py             Source, Category, CategoryField, Auction, AuctionSession, Item,
                        ItemPriceHistory, RawItem, ExtractionCache, ItemDuplicate,
                        ScrapeIncident, JobExecution, ClickEvent, User, SystemSetting, BrandingAsset
  seed.py               admin, árvore de categorias com campos, 3 fontes da F1
  settings_service.py   settings no banco com cache 60s (DEFAULTS = fonte da verdade)
  scrapers/             base.py, megaleiloes.py, freitas.py, leilo.py, generic_html.py, robots.py
  engine/               masking (RN-009), classifier, deterministic, normalizer (LLM),
                        category_fields (RN-002), dedup (RN-004), lifecycle (RN-005), health (RN-008)
  scheduler/jobs.py     scrape_tick, normalize, lifecycle, dedup, cleanup + persistência
  v1/                   portal.py (público), sources, categories, items, operations
                        (incidentes/jobs/duplicados/dashboard), settings_routes, branding, auth_routes
                        serializers.py monta os DTOs de item/pregão para portal e admin
```

---

## 3. Modelo de dados — o que confunde

> **Novo patamar de volume.** A RN-008 existe para detectar parser quebrado, não para
> brigar com mudança legítima de volume. Se o volume muda e se mantém estável por três
> coletas, isso vira o novo normal: a média se recalibra e o incidente se auto-resolve.
> Resolver um incidente de volume no admin também recalibra a média — senão a coleta
> seguinte reabriria o mesmo incidente. Sem isso a fonte fica suspensa para sempre:
> medido, o Freitas passou 40 horas trazendo 24 itens contra uma média congelada em 12.

**Source** tem três interruptores distintos:
- `is_active` — a fonte é **coletada**
- `dispatch_enabled` — os itens dela são **publicados** na vitrine
- `scraping_allowed` — RN-009; `false` bloqueia a coleta e abre incidente

E um estado de saúde: `health_status` (`ok`/`suspended`/`unknown`). **Suspensa, a fonte
continua sendo coletada, mas nada novo dela é publicado** até alguém resolver o
incidente no admin. É a RN-008 na prática.

**Item** unifica lote (`item_type=lot`) e, no futuro, anúncio (`listing`). Chave natural
`(source_id, external_id)`. Dois status independentes:
- `status` — ciclo de vida (RN-005): `collected → published → auction_soon → closed`,
  com `review`, `withdrawn`, `possibly_withdrawn`
- `extraction_status` — normalização (RN-003): `pending → done`, ou `failed → review`

Só `published` e `auction_soon` aparecem na vitrine (`engine/lifecycle.VISIBLE_STATUSES`).

`attributes` (JSONB) guarda os campos dinâmicos da categoria **já validados**. Chaves com
`_` são internas: `_raw` (o que a fonte entregou estruturado), `_category_hint`. O portal
nunca as mostra. Colunas `brand`, `model`, `year_model`, `km`, `condition` são cópias
promovidas para índice/filtro.

`plate_hash` é HMAC-SHA256 da placa com `SECRET_KEY`. A placa em claro **nunca** é
gravada. Trocar `SECRET_KEY` invalida a deduplicação por placa entre itens antigos e novos.

**Horário**: todo `datetime` do banco é **naive em America/Sao_Paulo** (`app/timeutil.now_brt`).
As fontes publicam em Brasília, o portal exibe em Brasília, e o Brasil não tem horário de
verão desde 2019. Nunca compare com `datetime.utcnow()`: dá 3h de erro em "pregão
próximo" e "encerrado". Única exceção é o JWT (`auth.py`), que segue em UTC. O Leilo entrega
ISO em UTC e o parser converte (`iso_to_brt_naive`).

**Auction / AuctionSession**: um pregão tem N sessões (`1a_praca`, `2a_praca`, `unica`,
`repasse`, `condicional`). `Item.next_session_at` é denormalizado pelo lifecycle e é o
que ordena a vitrine e alimenta a contagem regressiva.

**CategoryField** é herdado pela árvore: Carros herda os campos de Veículos
(`engine/category_fields.effective_fields`). O admin mostra os herdados como "herdado de".

---

## 4. O pipeline

Cinco jobs (APScheduler, `max_instances=1`, intervalos em settings lidos **no boot**):

| Job | Default | O que faz |
|---|---|---|
| `scrape_tick` | 10 min | coleta as fontes ativas cujo `scrape_frequency` venceu |
| `normalize` | 5 min | extrai campos de até `llm_max_items_per_cycle` itens pendentes |
| `lifecycle` | 30 min | publica, marca pregão próximo, encerra, oculta não reencontrados |
| `dedup` | 60 min | vínculos suspeitos entre fontes |
| `cleanup` | 03:00 | apaga `raw_items` velhos e encerrados antigos |

> **Varredura parcial.** Quando o parser para por limite de páginas, por limite de
> leilões ou porque a fonte pagina no cliente, ele marca `ScrapeStats.complete=False`.
> Numa varredura parcial **a ausência de um item não conta como retirada** (RN-005): ele
> pode estar apenas fora da janela vista. Sem isso, 76 lotes que existiam sumiram da
> vitrine nas primeiras 34 horas de operação. O motivo fica nos detalhes do job, visível
> no admin.

### 4.1 Scrape (`scheduler/jobs.run_scrape_job`)

1. Checa `scraping_allowed` e robots.txt (cache 24h). Bloqueio = incidente + skip.
2. Instancia o parser (`scrapers/__init__.SCRAPERS[parser_type]`) com `config` da fonte e
   `runtime` (UA, atrasos, detalhes) das settings. O parser devolve `ScrapedItem`s —
   **não grava nada**; isso permite o botão "Testar parser" rodar a seco.
3. `persist_scraped`: upsert de pregão + sessões, upsert do item por chave natural,
   `content_hash` decide se houve mudança. Mudou → reextrai (`extraction_status=pending`),
   grava `raw_items` e, se o preço mudou, `item_price_history`. Não mudou → só
   `last_seen_at` e `misses=0`.
4. Itens da fonte **não** vistos nesta coleta → `misses += 1` (RN-005).
5. `engine/health.evaluate_run`: 0 itens ou variação > X% vs média móvel (EMA 0,3) →
   incidente e suspensão. Falha de parser → incidente `parser_error`.

### 4.2 Normalize (`engine/normalizer.normalize_item`)

1. Categoria: dica da fonte (`_category_hint`) → palavras-chave do título → fallback.
2. Mascaramento (`engine/masking`): placa → `ABC-****` + hash; chassi → últimos 4;
   RENAVAM, CPF, telefone, e-mail removidos. Idempotente.
3. Determinístico (`engine/deterministic`): marca (lista), modelo, anos (`19/20`,
   `2010/2011`, `ano 2005`), km, combustível, câmbio, cor, documento, IPVA, débitos,
   restrições, origem. **Nunca infere** condição sem palavra explícita.
4. LLM (se `llm_enabled` e `llm_api_key`): `client.messages.create` com
   `output_config.format = json_schema` gerado dos campos da categoria. Cache por hash do
   conteúdo em `extraction_cache`. O LLM **vence** nos campos de julgamento
   (`condicao`, `origem`, `observacoes`…); o determinístico vence em marca/modelo/ano/km.
   Sem chave/rate limit/rede → `LLMUnavailable` interrompe o ciclo (não conta tentativa).
   Erro 4xx/JSON inválido/recusa → conta tentativa.
5. `validate_attributes` coage tipos; enum inválido → `nao_informado`; obrigatório
   ausente → tentativa falha. 2 falhas → `extraction_status=review`, `status=review`.
6. Promove colunas, atualiza `search_tsv`.

**Consequência**: sem API key o sistema publica normalmente, só com menos campos. O
`extraction_version` diz o que gerou cada item (`p1+det-1+claude-haiku-4-5`, `+cache`,
`+manual`).

### 4.3 Lifecycle (`engine/lifecycle.run_lifecycle`)

Publica `collected` com extração `done` de fonte `dispatch_enabled` e não suspensa.
`status_hint` da fonte (`closed`/`sold`/`withdrawn`) manda. Sessões passadas +
`closed_grace_hours` → `closed`, **exceto quando a fonte ainda declara o lote aberto**.
`misses >= lifecycle_misses_threshold` → `possibly_withdrawn` (volta a `published` se
reaparecer). Sessão em ≤ `auction_soon_days` → `auction_soon`.

> **A fonte tem a palavra final sobre o próprio lote.** Em leilão de seguradora e
> financeira é normal o lote continuar à venda depois do pregão: repasse, lance
> condicional aguardando o comitente, condicional negada. Encerrar por data
> esconderia da vitrine justamente a oportunidade ativa — foram 35 de 72 lotes do
> Leilo na primeira integração. O item também **reabre** quando a coleta o reencontra
> com `status_hint=open` (`scheduler/jobs._persist_one`).

### 4.4 Dedup (`engine/dedup`)

Só entre fontes diferentes. Placa igual → 1,0. Senão: Jaccard do título (0,4) + ano
(0,2) + km ±10% (0,15) + UF (0,15) + cor (0,1). `>= dedup_threshold` (0,85) → vínculo
`suspected`. Nunca funde; o admin confirma/rejeita. O portal mostra selo e links.

---

## 5. Fontes da F1 (verificadas em 18/09/2026)

| Fonte | Como | Cobertura | Armadilhas |
|---|---|---|---|
| Mega Leilões | HTML SSR, `div[data-key] .card`, `?pagina=N`; detalhe com descrição/leiloeiro/vara | veículos (maioria judicial) | descrição traz placa/chassi/renavam em claro e nomes de partes → mascaramento obrigatório; parser ignora Autor/Réu |
| Freitas Leiloeiro | AJAX `GET /Leiloes/PesquisarLotes?Categoria=1&PageNumber=N&TopRows=60` (header `X-Requested-With`) → cards `.cardlote` | veículos de financeira/seguradora | placa já mascarada pela fonte (`D__-___6`); observações são texto jurídico longo (o LLM é instruído a ignorar); **cadeia TLS incompleta no servidor deles** → `config.verify_ssl=false` (o `curl` passa porque usa o store do Windows; o httpx/certifi não) |
| Leilo | JSON em `window.__INITIAL_STATE__` (`elastic.lotes`, 36 por consulta) + consulta por leilão ativo | leves/pesados/motos, dados estruturados (marca, km, laudo, comitente, valor de mercado) | paginação é client-side sem endpoint público: cobertura = página geral + 36 por leilão ativo; datas vêm em UTC (convertidas para BRT) |

`generic_html` cobre leiloeiros simples via seletores CSS no `config` (exemplo no docstring).
Sodré Santoro, Superbid, Copart, Milan e Lance Certo ficaram para a F4 (ver DECISOES.md).

Fixtures reais em `backend/tests/fixtures/`; quando um layout quebrar, refaça a fixture e
ajuste o parser com o teste guiando.

---

## 6. Configuração — a armadilha central (igual ao Promo)

`.env` = só boot (banco, `SECRET_KEY`, admin inicial). **Tudo operacional está em
`system_settings`**, editável em /admin/settings, cache de 60 s: chave e modelo do LLM,
intervalos dos jobs (**lidos no boot: mudar exige restart**), limites RN-003/005/008,
UA e atrasos da coleta, textos do portal.

Adicionar chave nova = uma linha em `settings_service.DEFAULTS` + restart.

---

## 7. Deploy

Ver `DEPLOY.md`. Resumo: `-p zconnect_leilao` sempre; portas 8005/5177 em 127.0.0.1;
nginx do host publica; Postgres sem porta no host; builds fora do horário comercial.

---

## 8. Identidade visual

Portal: navy profundo (`#0b1020`), superfícies `#121a33`/`#1a2447`, texto `#e8ecf8`,
acento âmbar `#f59e0b` (CTAs e preços), verde para "aberto", vermelho para
sinistro/sucata. Fonte Inter (carregada de fato). Admin: pele neutra do Promo
(bg-gray-50, cartões brancos, azul Tailwind). Logo/favicon: upload em Configurações;
placeholders SVG em `dashboard/public/branding/`.

---

## 9. Qualidade do dado — o que a coleta descarta

Regras aplicadas na coleta para não exibir lixo como se fosse informação do lote
(`scrapers/base`):

- `reject_unknown` — "SI", "Sem Informação", "N/I", "—" e afins viram nulo. Sem isso a
  vitrine mostrava "Sem Informação / SI" no lugar da cidade.
- `reject_placeholder` — imagem genérica da fonte (`card-no-image`,
  `imagem-indisponivel`) é descartada; exibi-la mostraria a marca do leiloeiro no lugar
  do veículo.
- `_fit` (`scheduler/jobs`) — string vazia vira nulo e todo texto é truncado ao tamanho
  da coluna. As fontes mandam textos imprevisíveis: o leiloeiro do Mega Leilões vem com
  quatro registros de junta comercial num campo de 200 caracteres.
- `LeiloScraper._clean_model` — remove o sufixo de portas da base Infocar
  ("Gol Trendline Mb (2P/4P)"), que atrapalha busca e deduplicação.

Uma extração concluída **substitui** as colunas promovidas, inclusive com nulo — senão
uma correção de regra nunca limparia um dado errado já gravado.

## 10. Estado atual (18/09/2026)

- Backend e frontend completos para a F1. 17 testes unitários de parsers e engine.
- Validado de ponta a ponta em Docker local contra as três fontes reais: coleta,
  normalização, ciclo de vida, deduplicação, vitrine e painel. Todas as rotas da API
  respondem (`scripts/smoke_api.py`, 0 falhas) e as 17 telas renderizam com dados reais.
- Fluxo de incidente validado na prática: mudar o limite de páginas dobrou o volume, a
  RN-008 suspendeu as duas fontes e o admin reativou pelo endpoint de incidentes.
- **Não publicado** no servidor; sem API key de LLM configurada (o pipeline roda só com
  as regras determinísticas, como projetado).
- Próximos passos: subir no servidor, configurar o LLM, acompanhar a primeira semana de
  coleta. Depois, F2/F3 conforme DECISOES.md.
