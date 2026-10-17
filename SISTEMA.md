# ZConnect Leilão — bíblia do sistema

Documento de transferência de contexto. O que o sistema é, como funciona por dentro e
quais armadilhas já se conhecem. Estado: **20/09/2026, ondas 1 a 4 implementadas,
ainda não publicado no servidor**. Especificação em `docs/EF-ZLE-001-ZConnect-Leilao.md`;
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
| Assinante | `/conta` | filtros salvos, alertas recebidos, perfil, plano |
| Operador | `/admin` | fontes, categorias/campos, itens, revisão, incidentes, duplicados, usuários, alertas, jobs, config |

Rotas de operação exigem **papel admin**: um token válido de assinante recebe 403.

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
| `match` | 10 min | casa itens novos com os filtros salvos (RN-006) |
| `dispatch` | 5 min | envia os alertas pendentes (RN-006/RN-007) |
| `comparator` | 180 min | referência FIPE por bem + score de oportunidade (RN-010) |
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

### Fontes da F4 (a partir de 17/10/2026)

| Fonte | Como | Cobertura | Armadilhas |
|---|---|---|---|
| Rogério Menezes (RJ) | HTML SSR por categoria (`/categorias/carros` etc., sem paginação) + agenda em `var AGENDA` + detalhe com `var lote`/`var leilao` | seguradoras, financeiras, locadoras; ~240 veículos | cidade só no detalhe (pátio em Campo Grande/RJ); "Consulte" vira preço nulo; comitente do lote em `raw_attributes.comitente` |
| Nakakogue (PR) | listagem `/lotes/consulta/{2,3}/` (tudo numa página) + detalhe em duas requisições (casca + `POST /proximo_lote.php` na sessão PHP) | judicial do Paraná, veículos e máquinas | charset misto (latin-1 com UTF-8 gravado por campo, `fix_mojibake`); "Valor Mínimo" é o piso da 2ª praça; `lotes/NNN` na capa são pregões |
| Parque dos Leilões (DF) | listas `/leiloes` e `/leiloes-judiciais` (`type_id=1`) → página do pregão paginada → detalhe com `div[data-json="auctionLot"]` | bancos (pregões quinzenais de ~100 lotes) e varas do DF | preço só no detalhe, por isso só emite lote detalhado; praças judiciais lidas das Observações; `default_city/state` é conhecimento do operador |
| Pestana Leilões (SP) — **inativa** | API JSON pública (`/api/v2/leilao`, `/api/v2/lote/por-leilao`) | ~800 veículos de financeiras em 7 pregões | termos de uso vedam "robôs para navegação da plataforma": fica cadastrada desligada até o operador decidir (RN-009) |
| Casa de Leilões (MS) | `generic_html` só por configuração: capa lista pregões, cada pregão traz todos os lotes; `page_fields` lê abertura/encerramento do cabeçalho | DETRAN, prefeitura e varas de Campo Grande; ~150 veículos | capa dá "Encerra dd/mm" sem ano; bens móveis vêm sem cidade; 2ª praça dos judiciais fica de fora (o genérico modela sessão única) |

Leilões BR foi descartado (arte e colecionáveis), Kleiber também (10 veículos,
termos restritivos) e D1 Lance proíbe robôs no `robots.txt`.

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

## 8.5 Alertas, comparador e busca por raio (ondas 2 a 4)

**Filtro salvo = query da busca.** `saved_filters.criteria` guarda exatamente as
chaves de `GET /portal/items`, e o matcher roda o mesmo código
(`engine/search.py`, compartilhado com o portal). Duas implementações divergiriam
na primeira mudança, e o usuário receberia alerta de lote que a busca não mostra.

**Um filtro novo não recebe histórico.** Nem lotes publicados antes dele, nem
quedas de preço anteriores ao seu último check. Um filtro recém-criado que
dispara dezenas de alertas parece spam e queima o canal.

**Falha de infraestrutura interrompe o envio** em vez de marcar os alertas como
enviados. Um alerta perdido é pior que um atrasado: o pregão acontece uma vez só.

**WhatsApp nasce desligado.** Envio 1:1 para não-contatos por API não oficial tem
risco real de banimento do número. O e-mail é o canal principal; para escala em
WhatsApp, o caminho é a API oficial da Meta.

**Comparador usa a tabela FIPE**, não mediana de anúncios — ver `docs/DECISOES.md`
para a avaliação de cada marketplace. O score só existe quando dá para comparar
com honestidade, e carrega as ressalvas que o tornam legível: o custo é lance +
comissão + despesas, a condição do bem ajusta a referência, e o lance inicial é
declarado como piso do pregão, não preço de arremate.

**Busca por raio sem PostGIS**: base dos 5.571 municípios versionada em
`app/data/municipios.json` (coordenada, população IBGE 2021 e nome de exibição),
retângulo mais Haversine em SQL puro. Item sem coordenada reconhecida não entra
na busca, em vez de entrar no lugar errado — e **cidade de referência não
reconhecida devolve 400**, porque ignorar o raio entregaria o país inteiro a
quem pediu 60 km. A população não entra em nenhum cálculo: serve só para o
autocomplete oferecer Campinas antes de Campanha. Com o raio ativo, cada item
traz `distance_km`, que é o que justifica a ordem "mais perto" na tela.

## 8.6 Audiência e leads por fonte (onda 5)

`source_daily_stats` guarda, por fonte e por dia, **aberturas de ficha** e
**cliques de saída** para o site do leiloeiro. Agregado, e não um evento por
visita: o relatório de parceria responde a uma taxa, e uma linha por dia por
fonte responde isso sem crescer sem limite.

Aberturas não são visitantes únicos — não há identificação do visitante, e a
tela diz "aberturas" em vez de inventar uma métrica mais bonita para uma
proposta comercial. Acesso de robô não conta (`engine/metrics.is_bot`), e a
contagem nunca derruba a navegação: falha de gravação vira log, não erro para
o visitante.

Antes disso o painel exibia como "CTR" a divisão cliques ÷ lotes publicados,
que não tem denominador de audiência. Agora a taxa é cliques ÷ aberturas, e é
`—` quando não houve abertura no período: taxa sem denominador não existe.

**Login de parceiro e destaque pago ficaram para quando houver contrato**
(decisão de 20/09/2026). Destaque pago sem parceiro fechado seria viés de
ranking que ninguém está pagando; o mecanismo é pequeno e entra quando o
primeiro contrato existir — e, quando entrar, com selo visível de publicidade.

## 8.7 Classificacao de categoria: o titulo manda

A dica de categoria que a fonte manda e' grossa — muitos leiloeiros so' tem
"leves" e "pesados", e jogam trator, implemento agricola e carcaca no balde
mais proximo. Por isso a dica so' vale quando o titulo nao traz palavra-chave
nenhuma; havendo palavra-chave, **a primeira delas define o bem**:

- "Trator John Deere" com dica "pesados" -> maquinas agricolas.
- "Carcaca de Carro Fiat Doblo" com dica "carros" -> outros veiculos, porque
  "carcaca" vem antes de "carro".
- "Caminhao com munck" com dica "pesados" -> caminhoes, porque "caminhao" e' a
  primeira.

Palavra-chave curta ou ambigua nao entra na lista: `hr ` casava "HONDA/HR-V" e
mandava o SUV para Utilitarios, e `fazer` (da Yamaha Fazer) e' verbo em
portugues. O mesmo criterio vale para marcas: `cat`, `bull` e `still` ficam de
fora de proposito, porque marca errada publicada e' pior que lote em revisao.

`marca` e' obrigatoria em Veiculos e em Maquinas, mas **opcional em Outros
veiculos**: carcaca, sucata e monobloco sao lotes reais que a fonte publica sem
marca, e exigi-la manda o lote para uma revisao de onde ele nunca sai.

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

## 10. Estado atual (20/09/2026)

| Onda | Escopo | Situação |
|---|---|---|
| 1 | Coleta, normalização, vitrine, painel | pronta |
| 2 | Contas, filtros salvos, alertas (RN-006/RN-007) | pronta |
| 3 | Comparador com referência FIPE (RN-010) | pronta, na vitrine e na ficha |
| 4 | Busca por raio, máquinas e equipamentos | pronta, com filtro e ordem na busca |
| 5 | Parcerias — relatório de CTR/leads por fonte | pronto (critério de aceite da EF) |
| 5 | Parcerias — login de parceiro e destaque pago | adiado por decisão comercial (20/09/2026) |

- 72 testes unitários. Validação de ponta a ponta em Docker local contra as três
  fontes reais, contra a API FIPE e com as telas renderizadas no Playwright
  (sem erro de console, sem overflow em 1440 e em 390 px).
- 546 itens coletados, 370 na vitrine, 74 pregões, 3 fontes saudáveis, 8 jobs
  agendados, 27 lotes com score de oportunidade. **Nenhum lote em revisão.**
- **Não publicado** no servidor. Sem API key de LLM e sem SMTP configurados: o
  pipeline roda com regras determinísticas, o comparador usa a premissa de
  condição e os alertas ficam na fila até o SMTP existir.
- Próximos passos, todos dependentes de acesso ao servidor: publicar (DEPLOY.md),
  apontar o DNS, configurar SMTP e a chave de LLM, acompanhar a primeira semana.
  O relatório de parcerias nasce vazio e ganha sentido com o tráfego.
