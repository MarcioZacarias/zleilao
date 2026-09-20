# API — ZConnect Leilão (F1)

Base do frontend: `baseURL: "/api"` (o nginx do dashboard reescreve `/api/*` → `zleilao-backend:8000/v1/*`).
Em dev, o Vite faz o mesmo proxy (`/api` → `http://localhost:8005/v1`).

Autenticação admin: `Authorization: Bearer <jwt>`. Rotas `/portal/*`, `/auth/login` e `/branding/{key}` são públicas.
Datas: ISO 8601 **sem timezone**, já em horário de Brasília. Valores monetários: string decimal (`"21900.00"`), BRL.

## Enums

| Campo | Valores |
|---|---|
| `Item.status` | `collected`, `review`, `published`, `auction_soon`, `closed`, `withdrawn`, `possibly_withdrawn` |
| `Item.extraction_status` | `pending`, `done`, `failed`, `review`, `skipped` |
| `Item.price_kind` | `lance_inicial`, `lance_atual`, `avaliacao`, `preco_pedido` |
| `Item.condition` | `normal`, `sinistro_recuperavel`, `sinistro_media_monta`, `sinistro_grande_monta`, `sucata`, `nao_informado` |
| `AuctionSession.kind` | `1a_praca`, `2a_praca`, `unica`, `repasse`, `condicional` |
| `Auction.auction_type` | `judicial`, `extrajudicial` |
| `Auction.modality` | `online`, `presencial`, `hibrido` |
| `Source.health_status` | `ok`, `suspended`, `unknown` |
| `Incident.kind` | `zero_items`, `abnormal_variation`, `parser_error`, `http_error`, `robots_disallowed`, `scraping_not_allowed` |
| `Incident.status` | `open`, `acknowledged`, `resolved` |
| `Duplicate.status` | `suspected`, `confirmed`, `rejected` |
| `CategoryField.field_type` | `string`, `int`, `decimal`, `bool`, `enum`, `date` |

Visíveis na vitrine: `published` e `auction_soon` (detalhe também aceita `closed`).

## Shapes principais

```ts
interface ItemCard {
  id: number; item_type: "lot" | "listing"; title: string; lot_number: string | null;
  price: string | null; price_kind: string | null; price_second: string | null;   // 2ª praça
  image_url: string | null; city: string | null; state: string | null;
  brand: string | null; model: string | null; year_model: number | null; km: number | null;
  condition: string | null; status: string; next_session_at: string | null; last_seen_at: string;
  source_id: number; source_name: string | null; source_slug: string | null;
  category_id: number | null; category_slug: string | null; category_name: string | null;
  auction_id: number | null; auction_type: string | null;
  card_fields: Record<string, unknown>;   // campos show_in_card da categoria (ex.: combustivel, origem)
  possible_duplicate: boolean;
}

interface CategoryField {
  id: number; category_id: number; key: string; label: string; field_type: string; unit: string | null;
  required: boolean; options: string[] | null; show_in_card: boolean; filterable: boolean;
  sort_order: number; description: string | null; inherited_from: string | null; // slug da categoria-mãe
}

interface AuctionSession { id: number; kind: string; sequence: number; starts_at: string | null; ends_at: string | null; min_bid: string | null }
interface Auction {
  id: number; source_id: number; source_name: string | null; external_id: string; title: string | null;
  auctioneer_name: string | null; auctioneer_registration: string | null; committer_name: string | null;
  modality: string | null; auction_type: string | null; official_url: string | null; status: string;
  starts_at: string | null; ends_at: string | null; sessions: AuctionSession[]; items_count: number;
}

interface ItemDetail extends ItemCard {
  description: string | null; images: string[]; attributes: Record<string, unknown>;  // já mascarados (RN-009)
  field_defs: CategoryField[];        // renderizar a ficha nesta ordem; ausente => "não informado" (RN-002)
  official_url: string; location_text: string | null; auction: Auction | null;
  price_history: { price: string; price_kind: string | null; observed_at: string }[];
  duplicates: { item_id: number; title: string; source_name: string | null; official_url: string; similarity: number; status: string }[];
  first_seen_at: string; disclaimer: string | null; extraction_status: string | null; extraction_version: string | null;
}

interface FacetValue { value: string; label: string | null; count: number }
interface PageMeta { page: number; page_size: number; total: number; pages: number }
interface ItemPage { items: ItemCard[]; meta: PageMeta; facets: { states; sources; categories; brands; conditions; auction_types }: Record<string, FacetValue[]> }

interface Category {
  id: number; name: string; slug: string; parent_id: number | null; is_active: boolean; sort_order: number;
  keywords: string[]; llm_hint: string | null; path: string; created_at: string; items_count: number;
  fields: CategoryField[]; children: Category[];
}

interface Source {
  id: number; name: string; slug: string; kind: "auction" | "marketplace"; parser_type: string; base_url: string | null;
  config: Record<string, unknown> | null; is_active: boolean; dispatch_enabled: boolean; scraping_allowed: boolean;
  scrape_frequency: number; priority_weight: number; robots_status: string | null; robots_checked_at: string | null;
  last_run_at: string | null; last_run_status: string | null; last_items_count: number; avg_items_count: number | null;
  health_status: string; suspended_reason: string | null; created_at: string; updated_at: string;
  items_total: number; items_published: number; open_incidents: number;
}

interface ItemAdmin extends ItemCard {
  external_id: string; official_url: string; extraction_status: string; extraction_attempts: number;
  extraction_version: string | null; extraction_error: string | null; extraction_model: string | null;
  status_hint: string | null; misses: number; first_seen_at: string; created_at: string; updated_at: string;
  description: string | null; attributes: Record<string, unknown>; images: string[];
}

interface Incident { id; source_id; source_name; kind; message; expected: number|null; observed: number|null; status; created_at; resolved_at; resolved_by }
interface JobExecution { id; job_type; source_id; source_name; status: "running"|"success"|"failed"|"skipped"; items_processed; details: object|null; error; started_at; finished_at }
interface Duplicate { id; canonical: ItemCard; duplicate: ItemCard; similarity: number; reasons: object|null; status; created_at }
```

## Público

| Método | Rota | Resposta |
|---|---|---|
| POST | `/auth/login` `{email,password}` | `{access_token, token_type, user_name, user_email, role}` |
| GET | `/auth/me` (auth) | `{id,email,name,role,is_active}` |
| POST | `/auth/change-password` (auth) `{current_password,new_password}` | `{status}` |
| GET | `/portal/branding` | `{logo_dark, logo_light, favicon, site_title, tagline, disclaimer}` (urls podem ser null → usar `/branding/*.png` do `public/`) |
| GET | `/portal/stats` | `{items_published, sources_active, auctions_upcoming_7d, next_session_at, last_collected_at, by_category:[{slug,name,count}]}` |
| GET | `/portal/categories` | `Category[]` (árvore, só ativas, com `fields` efetivos e `items_count` agregado) |
| GET | `/portal/items` | `ItemPage`. Query: `q, category(slug), brand, model, year_min, year_max, price_min, price_max, state(UF), city, source(slug), condition, auction_type, session_from, session_to, status, sort(relevance\|price_asc\|price_desc\|session_asc\|newest), page, page_size(≤100), facets(bool)` |
| GET | `/portal/items/{id}` | `ItemDetail` (404 se fora da vitrine) |
| GET | `/portal/items/{id}/go` | **302** para a fonte oficial (registra clique). Use como `href` do botão "Ver no leilão oficial" com `target="_blank" rel="noopener"`. |
| GET | `/portal/brands?category=` | `FacetValue[]` |
| GET | `/portal/models?brand=` | `FacetValue[]` |
| GET | `/portal/auctions/upcoming?days=7&limit=10` | `Auction[]` |
| GET | `/portal/auctions/{id}` | `{auction: Auction, items: ItemCard[]}` |
| GET | `/branding/{logo_dark\|logo_light\|favicon}` | binário |

## Admin (Bearer)

| Método | Rota | Notas |
|---|---|---|
| GET | `/dashboard` | ver shape abaixo |
| GET/POST | `/sources` | lista `Source[]` / cria (`SourceCreate`: name, slug, kind, parser_type, base_url, config, is_active, dispatch_enabled, scraping_allowed, scrape_frequency, priority_weight) |
| GET | `/sources/parsers` | `[{key, name, default_config}]` — popular o select de parser e pré-preencher `config` |
| GET/PUT/DELETE | `/sources/{id}` | PUT aceita parcial. DELETE 409 se houver itens |
| POST | `/sources/{id}/run` | dispara coleta em background → `{status:"started"}` |
| POST | `/sources/{id}/test` | coleta a seco (1 página) → `{ok, items_found, sample:[...], error, duration_ms}` |
| POST | `/sources/{id}/reactivate` | limpa suspensão (RN-008) |
| GET/POST | `/categories` | árvore completa (inclusive inativas) / cria (`name, slug, parent_id, is_active, sort_order, keywords[], llm_hint`) |
| PUT/DELETE | `/categories/{id}` | |
| GET/POST | `/categories/{id}/fields` | campos efetivos (com `inherited_from`) / cria campo (`CategoryField` sem id) |
| PUT/DELETE | `/categories/fields/{field_id}` | |
| GET | `/items` | `{items: ItemAdmin[], meta}`. Query: `q, status(csv), extraction_status(csv), source_id, category_id, page, page_size(≤200), sort(updated_desc\|first_seen_desc\|session_asc\|price_desc)`. **Fila de revisão** = `extraction_status=review` |
| GET | `/items/summary` | `{by_status:{}, by_extraction:{}}` |
| GET/PATCH/DELETE | `/items/{id}` | PATCH `ItemUpdate`: `title, category_id, attributes{}, status, brand, model, year_model, year_fab, km, condition, description` (attributes é mesclado e revalidado; item em revisão vira `done`) |
| POST | `/items/{id}/renormalize` | reextrai agora (503 se LLM indisponível) |
| POST | `/items/{id}/publish` | força publicação |
| POST | `/items/{id}/hide` | marca `withdrawn` |
| GET | `/incidents?status=open\|acknowledged\|resolved\|all&source_id=` | `Incident[]` |
| PATCH | `/incidents/{id}` `{status: "acknowledged"\|"resolved", reactivate_source: bool}` | resolver reativa a fonte se não houver outro aberto |
| GET | `/jobs?job_type=&limit=` | `JobExecution[]` (scrape, normalize, lifecycle, dedup, cleanup) |
| GET | `/jobs/scheduler` | `{jobs:[{id,next_run_at,running}]}` |
| POST | `/jobs/{scrape_tick\|normalize\|lifecycle\|dedup\|cleanup}/run` | dispara agora |
| GET | `/duplicates?status=suspected\|confirmed\|rejected\|all` | `Duplicate[]` |
| PATCH | `/duplicates/{id}` `{status}` | |
| GET | `/settings` | `{ [group]: {label, items:[{key,value,label,is_secret}]} }` — segredos vêm como `********` |
| PUT | `/settings` `{settings:{key:value}}` | ignora valores `********` |
| POST | `/settings/test-llm` | `{ok, detail, model?, reply?, usage?}` |
| POST | `/branding/upload` (multipart `key`, `file`) / DELETE `/branding/{key}` | |

### `/dashboard`

```ts
{
  items_total: number; items_by_status: Record<string, number>; items_by_extraction: Record<string, number>;
  extraction_rate: number | null; items_new_24h: number; auctions_upcoming_7d: number;
  open_incidents: number; suspected_duplicates: number;
  sources: { id; name; slug; is_active; dispatch_enabled; health_status; last_run_at; last_run_status;
             last_items_count; avg_items_count; items_total; items_published; clicks_7d; ctr_7d: number|null }[];
  last_jobs: Record<"scrape"|"normalize"|"lifecycle"|"dedup"|"cleanup", JobExecution | null>;
  daily_collected: { day: string; count: number }[];   // 14 dias
}
```

## Regras de exibição (da EF)

- **RN-001** — toda ficha e card mostram a fonte (`source_name`), o botão para a fonte oficial (`/portal/items/{id}/go`) e a "última coleta" (`last_seen_at`).
- **RN-002** — a ficha percorre `field_defs` e mostra `attributes[key]`; ausente/null → "não informado". Nunca inventar. Enum `nao_informado` idem. `unit` vai junto do valor (`km`, `BRL`, `cc`).
- **RN-004** — `possible_duplicate=true` → selo "possível duplicado"; detalhe lista `duplicates` com link.
- **RN-005** — `status=auction_soon` → destaque "pregão em breve" + contagem regressiva usando `next_session_at`. `closed` → ficha ainda abre, com selo "encerrado", sem CTA de lance.
- Preço: `price_kind=lance_inicial` → rótulo "Lance inicial"; se `price_second` → mostrar "2ª praça: R$ …".
- `condition` ≠ `normal`/`nao_informado` → selo de alerta (sinistro/sucata). O portal **não** calcula score de oportunidade na F1.
- Disclaimer (`/portal/branding.disclaimer`) no rodapé de toda ficha.

---

# Onda 2 — contas, filtros salvos e alertas (RN-006/RN-007)

Autenticação: o mesmo `POST /auth/login` serve para assinante e administrador; o campo
`role` na resposta diz qual é (`user` ou `admin`). Rotas `/v1/me/*` exigem token de
qualquer papel. Rotas de operação (`/v1/sources`, `/v1/items`, `/v1/users`, `/v1/alerts`,
`/v1/settings`, `/v1/jobs`, `/v1/incidents`, `/v1/duplicates`, `/v1/categories`,
`/v1/dashboard`) exigem **papel admin** e respondem **403** para assinante.

## Enums

| Campo | Valores |
|---|---|
| `Alert.reason` | `new` (lote novo), `price_drop` (queda de lance), `new_session` (nova sessão) |
| `Alert.status` | `pending`, `sent`, `failed`, `skipped` |
| `Alert.channel` | `email`, `whatsapp` |
| `plan` | `free`, `pro` |
| `plan_status` | `active`, `canceled`, `expired` |

## Critério do filtro salvo

`criteria` usa **exatamente** as chaves da busca pública, então a query string de
`/busca` vira filtro salvo sem tradução:

```
q, category (slug), brand, model, year_min, year_max, price_min, price_max,
state (UF), city, source (slug), condition, auction_type
```

Chaves desconhecidas são descartadas no servidor. Critério vazio significa "qualquer
lote novo".

## Público (sem token)

| Método | Rota | Corpo / notas |
|---|---|---|
| POST | `/auth/register` | `{name, email, password (≥8), phone?}` → `{status, verification_required, verification_sent, detail}`. **409** se o e-mail já existe (mensagem neutra, não confirma cadastro). |
| POST | `/auth/verify-email?token=` | → `{status, email}`. Token é de uso único: a segunda chamada dá **400**. |
| POST | `/auth/resend-verification` | `{email}` → resposta igual exista ou não a conta. |
| POST | `/auth/forgot-password` | `{email}` → resposta igual exista ou não a conta. |
| POST | `/auth/reset-password` | `{token, new_password}` → devolve `access_token` já logado. |

## Conta do assinante (token)

| Método | Rota | Notas |
|---|---|---|
| GET | `/me` | `{id, email, name, role, phone, email_opt_in, whatsapp_opt_in, email_verified, quiet_start, quiet_end, plan, plan_status, plan_expires_at, filters_used, filters_limit, whatsapp_channel_available, realtime_alerts}` |
| PATCH | `/me` | `{name?, phone?, email_opt_in?, whatsapp_opt_in?, quiet_start?, quiet_end?}`. Ativar WhatsApp sem telefone dá **400**. |
| POST | `/me/change-password` | `{current_password, new_password}` |
| GET | `/me/filters` | `{filters: SavedFilter[], limit, plan}` |
| POST | `/me/filters` | `{name?, criteria, channels, is_active}` → **403** ao estourar o limite do plano, com a mensagem pronta para exibir. Sem `name`, o servidor gera a descrição. |
| PUT/DELETE | `/me/filters/{id}` | |
| GET | `/me/filters/{id}/preview?limit=6` | `{total, items: ItemCard[]}` — o que o filtro pegaria hoje |
| GET | `/me/alerts?limit=50` | `[{id, reason, status, channel, detail, created_at, sent_at, saved_filter_id, item: ItemCard\|null}]` |

```ts
interface SavedFilter {
  id: number; name: string; criteria: Record<string, unknown>; channels: ("email"|"whatsapp")[];
  is_active: boolean; last_matched_at: string | null; matches_count: number;
  created_at: string; description: string;   // resumo legível do critério
}
```

## Admin

| Método | Rota | Notas |
|---|---|---|
| GET | `/users?q=&plan=&page=&page_size=` | `{users: UserAdmin[], meta: PageMeta}` |
| GET | `/users/summary` | `{users_total, users_verified, by_plan, active_filters, alerts_sent_today, alerts_pending, alerts_failed}` |
| PATCH | `/users/{id}` | `{is_active?, role?, email_verified?}`. Bloqueia auto-rebaixamento e autodesativação. |
| PUT | `/users/{id}/plan` | `{plan: "free"\|"pro", months: 0-36, note?}`. `months=0` no pago = sem vencimento (cortesia). Ativação **manual**: não há gateway. |
| GET | `/users/{id}/filters` | filtros daquele usuário |
| GET | `/alerts?status=&user_id=&limit=` | `[{id, reason, status, channel, detail, error, created_at, sent_at, user, item}]` |
| POST | `/alerts/{id}/retry` | volta para `pending`. **400** se já foi enviado. |
| POST | `/settings/test-email` | `{to}` → `{ok, detail}`. Envia mensagem real. |
| POST | `/settings/test-whatsapp` | `{to: telefone}` → `{ok, detail}` |
| POST | `/jobs/{match\|dispatch}/run` | dispara os jobs de alerta |

```ts
interface UserAdmin {
  id: number; email: string; name: string | null; role: "user"|"admin"; is_active: boolean;
  phone: string | null; email_opt_in: boolean; whatsapp_opt_in: boolean; email_verified: boolean;
  created_at: string; last_login_at: string | null;
  plan: "free"|"pro"; plan_status: string; plan_expires_at: string | null; plan_note: string | null;
  filters: number; alerts_sent: number;
}
```

## Regras que a interface precisa respeitar

- **E-mail não verificado não recebe alerta.** `GET /me` traz `email_verified`; enquanto
  for `false`, mostrar aviso com ação de reenviar. O login funciona mesmo sem verificar.
- **Limite de filtros por plano** (`filters_used` / `filters_limit`): ao atingir, oferecer
  remover um ou mudar de plano. O erro **403** já vem com o texto pronto.
- **WhatsApp só aparece** quando `whatsapp_channel_available` é `true`; caso contrário o
  canal não é oferecido, porque está desligado no servidor.
- **Plano gratuito recebe resumo diário**, plano pago recebe quase em tempo real
  (`realtime_alerts`). Deixar isso explícito na tela de planos.
- **Janela de silêncio** é opcional e pessoal; vazia significa usar a global do sistema.

---

# Ondas 3 e 4 — comparador e busca por raio

## Score de oportunidade (RN-010)

Aparece em `ItemCard` (resumido) e em `ItemDetail` (completo). **Ausente quando
não dá para comparar com honestidade** — sem referência FIPE, ou com condição
desconhecida e sem premissa aceitável. Nesse caso a interface mostra
"sem referência de mercado suficiente", nunca um score fraco.

```ts
// no card, para destacar e ordenar
opportunity_score: number | null;      // 0-100
opportunity_discount: number | null;   // % sobre a referência ajustada

// no detalhe
interface Opportunity {
  score: number; discount_pct: number;
  reference_value: string;   // FIPE do bem
  total_cost: string;        // lance + comissão + despesas
  reference_label: string | null;   // "FIPE setembro de 2026 — MOBI LIKE 1.0 Fire Flex 5p."
  computed_at: string;
  reasons: {
    lance: number; comissao_pct: number; comissao: number; despesas: number; custo_total: number;
    referencia: number; referencia_ajustada: number; desconto_pct: number;
    condicao: string; condicao_presumida: boolean; fator_condicao: number;
    base_calculo: "lance_inicial" | "lance_atual" | string;
    nota_preco?: string;      // ressalva do lance inicial ser o piso
    nota_condicao?: string;   // quando a condição foi presumida
    nota?: string;            // quando a referência foi ajustada por sinistro/sucata
    alerta?: string;          // quando o custo está acima da referência
  };
}
```

**A interface precisa mostrar as ressalvas.** O score só é honesto acompanhado
delas: `nota_preco` explica que o lance inicial é o piso do pregão;
`nota_condicao` avisa que o estado do bem foi presumido; `alerta` marca lote
mais caro que a referência. Exibir o número sozinho transforma uma estimativa
em promessa.

## Busca por raio

Três parâmetros em `GET /portal/items`, sempre juntos:

| Parâmetro | Exemplo |
|---|---|
| `near_city` | `São Paulo` |
| `near_state` | `SP` |
| `radius_km` | `100` (entre 1 e 3000) |

| Método | Rota | Resposta |
|---|---|---|
| GET | `/portal/cities?q=camp&limit=8` | `[{city, state, lat, lng}]` — autocomplete offline, base de 5.571 municípios |

O autocomplete ordena por **população** (IBGE 2021) e devolve o nome com
acento: quem digita `camp` recebe Campinas, Campo Grande e Campos dos
Goytacazes, não Campanha. O `city` devolvido é o que deve voltar em
`near_city`.

Item sem coordenada reconhecida **não entra** na busca por raio, em vez de
entrar no lugar errado. A precisão é a do centroide do município.

Quando a cidade de referência **não é reconhecida**, `/portal/items` responde
`400 Cidade de referência não reconhecida para a busca por raio`. Ignorar o
filtro devolveria o país inteiro a quem pediu 60 km — silenciosamente, e na
direção errada. No motor de alertas, onde não cabe um erro HTTP, o mesmo caso
não casa nenhum lote.

Com o raio ativo, cada item do resultado traz também a distância:

```ts
distance_km: number | null;   // km entre o município do lote e o de referência
```

Vem `null` fora da busca por raio. É o que explica a ordem `distance` na tela:
sem mostrar a distância, a lista reordenada não tem justificativa visível.

## Ordenações novas em `sort`

| Valor | Efeito |
|---|---|
| `distance` | do mais perto para o mais longe (exige os parâmetros de raio) |
| `opportunity` | maior desconto primeiro; lote sem score vai para o fim |

---

# Onda 5 — audiência e leads por fonte

O painel chamava de "CTR" a divisão `cliques / lotes publicados`. Não é taxa de
nada: falta o denominador. A medição passou a contar **abertura de ficha**,
agregada por fonte e por dia em `source_daily_stats`.

| Contador | O que é |
|---|---|
| `views` | abertura da página de um lote (`GET /portal/items/{id}`) — **não** visitante único |
| `clicks` | saída por `GET /portal/items/{id}/go`, o lead entregue ao leiloeiro |
| taxa | `clicks / views`; `null` quando não houve abertura |

Acessos de robô não contam (`app/engine/metrics.is_bot`), senão o relatório de
parceria somaria o Googlebot como interesse de comprador. A contagem é
subordinada à navegação: se o UPSERT falhar, o visitante ainda vê a ficha e
ainda é redirecionado.

| Método | Rota | Resposta |
|---|---|---|
| GET | `/partners/report?days=30` | totais, série diária e uma linha por fonte (admin) |

```jsonc
{
  "days": 30, "from": "2026-08-21",
  "sources": [{ "source_id": 3, "name": "Leilo", "slug": "leilo",
                "items_published": 151, "views": 2278, "clicks": 357,
                "ctr": 0.157, "views_per_item": 15.09 }],
  "totals": { "views": 6577, "clicks": 1078, "ctr": 0.164 },
  "daily": [{ "day": "2026-09-20", "views": 210, "clicks": 34 }]
}
```

O `/dashboard` ganhou `views_7d` por fonte, e `ctr_7d` passou a ser a taxa real.
