# EF-ZLE-001 — ZConnect Leilão

**Especificação Funcional — Agregador de Leilões e Busca de Usados**

| | |
|---|---|
| **Produto** | ZConnect Leilão *(nome provisório — segue o padrão de categoria: Imob, Conta$, Promo, Loja)* |
| **Código** | EF-ZLE-001 |
| **Versão** | 1.1 |
| **Data** | 18/09/2026 |
| **Autor** | Márcio Zacarias — ZardTech Tecnologia e Inovação |
| **Status** | Rascunho para validação |

---

## Histórico de revisões

| Versão | Data | Autor | Descrição |
|---|---|---|---|
| 1.0 | 17/09/2026 | Márcio Zacarias | Emissão inicial |
| 1.1 | 18/09/2026 | Márcio Zacarias | Inclusão do módulo de busca de usados (marketplaces), comparador leilão × usado e revisão das fases |

---

## 1. Cenário Atual

Os leilões no Brasil (veículos, máquinas, equipamentos, imóveis e itens diversos) estão pulverizados em dezenas de portais de leiloeiros oficiais, bancos, seguradoras e órgãos públicos. Cada portal tem estrutura própria, sem API pública, sem padronização de dados e sem mecanismo unificado de busca ou alerta. Quem procura um bem específico precisa monitorar manualmente vários sites, com risco de perder pregões por falta de visibilidade.

A ZardTech já opera um pipeline análogo no **ZConnect Promo** (coleta → normalização → score → alerta em WhatsApp), cuja arquitetura e infraestrutura serão reaproveitadas.

## 2. Problema

- Informação de leilões fragmentada em múltiplas fontes heterogêneas, sem busca centralizada.
- Ausência de alertas personalizados por tipo de bem, faixa de preço e localização.
- Descrições de lotes não padronizadas, dificultando comparação entre fontes.
- O mesmo lote pode aparecer em mais de um portal, gerando duplicidade.

## 3. Objetivo

Centralizar, em uma única plataforma, duas frentes de oportunidades de compra:

1. **Módulo Leilão** — lotes de leilões publicados por leiloeiros oficiais e portais de leilão;
2. **Módulo Usados** — anúncios de produtos e veículos usados publicados em marketplaces e portais especializados (Mercado Livre, OLX, Webmotors, NaPista, Compre Car, iCarros).

Ambos normalizados por categoria, com busca unificada, vitrine pública, alertas personalizados e **comparador leilão × usado** (referência de preço de mercado do bem) — **sempre direcionando o usuário à fonte oficial** (a plataforma não realiza leilões, não intermedia lances nem transações e não é leiloeira).

## 4. Dicionário de Termos

| Termo | Definição |
|---|---|
| Fonte | Portal de leiloeiro/leilão ou marketplace/portal de usados monitorado pela plataforma |
| Lote | Item ou conjunto de itens ofertado em um pregão |
| Anúncio | Item de venda direta publicado em marketplace/portal de usados (sem pregão; preço pedido) |
| Item | Conceito unificado que abrange lote (leilão) e anúncio (usado) |
| Pregão | Sessão de leilão com data/hora definidas |
| Preço de referência | Mediana de preço do mesmo bem (marca/modelo/ano) nos anúncios de usados, usada pelo comparador |
| Normalização | Conversão da descrição bruta do item em campos estruturados |
| Deduplicação | Identificação do mesmo item publicado em fontes distintas |
| Alerta | Notificação enviada ao usuário quando um lote casa com seu filtro salvo |
| Filtro salvo | Critérios persistidos do usuário (categoria, marca/modelo, preço, raio geográfico, datas) |

## 5. Volumetria (estimada)

- **Leilão**: 10–20 fontes na fase inicial; meta de 50+ fontes em 12 meses; 5.000–30.000 lotes ativos simultâneos; coleta 2–6x/dia.
- **Usados**: 4–6 fontes na fase inicial (ML, Webmotors, NaPista, Compre Car, iCarros; OLX em avaliação); volume potencialmente 10x maior que leilões — coleta **dirigida por demanda** (termos derivados dos filtros salvos e das categorias ativas), não varredura completa dos portais.
- Pico de eventos próximo às datas de pregão (atualização de lances iniciais/status).

## 6. Premissas

1. A plataforma atua exclusivamente como **agregador/vitrine com link para a fonte oficial** — modelo já praticado no mercado (agregadores de leilões, de imóveis e de veículos).
2. Não haverá cópia massiva de fotos: exibição por thumbnail/URL da fonte com atribuição, ou imagem única de referência, conforme termos de uso de cada fonte.
3. Fontes sem API serão coletadas via scraping estruturado, com parser dedicado por fonte e monitoramento de quebra de layout (mesma abordagem do BaseScraper do Promo). O scraper de Mercado Livre do Promo será reaproveitado como base do módulo Usados.
4. Fontes de usados priorizadas por viabilidade: **Tier 1** — Mercado Livre, Webmotors, NaPista, Compre Car, iCarros (dados estruturados, anti-bot moderado); **Tier 2** — OLX (anti-bot forte: Playwright, rate limit agressivo, possível necessidade de proxy).
5. Reuso da infraestrutura ZConnect: servidor compartilhado, PostgreSQL, Docker com projeto compose isolado, nginx do host, envio WhatsApp via API do ZConnect RH (Baileys).
6. A extração de campos a partir de descrições não padronizadas usará LLM de baixo custo com saída JSON validada por schema.

## 7. Não Escopo

- Realização, transmissão ou intermediação de leilões, lances ou transações de compra e venda (não há motor de lances nem checkout).
- **Facebook Marketplace** — fora do escopo (exige login, anti-automação agressivo da Meta, violação de termos ativamente perseguida; reavaliar apenas se surgir via oficial).
- Cadastro/habilitação de arrematantes ou repasse de pagamentos.
- Contato com vendedores ou gestão de negociação de usados (o usuário negocia na fonte).
- Emissão de laudos, vistorias ou consulta de débitos/restrições de veículos (Detran, gravame) — pode virar evolução futura como serviço agregado.
- Garantia de completude ou exatidão dos dados da fonte (exibir sempre data da última coleta e disclaimer).
- App mobile nativo na v1 (web responsivo).

## 8. Solução Proposta

### 8.1 Visão geral

Pipeline em quatro estágios, agendados via APScheduler:

```
[Coleta por fonte] → [Normalização LLM] → [Deduplicação] → [Indexação/Alertas]
```

1. **Coleta**: scrapers por fonte (httpx + BeautifulSoup/Playwright quando houver JS), gravando o item bruto (`raw_items`) com HTML/JSON de origem. Fontes têm `kind = auction | marketplace`; a coleta de marketplaces é dirigida por termos de busca derivados dos filtros salvos e categorias ativas.
2. **Normalização**: LLM extrai campos estruturados conforme a categoria (schema dinâmico), com validação Pydantic; falhas vão para fila de revisão. Portais especializados de veículos (Webmotors, NaPista, Compre Car, iCarros) já entregam campos estruturados — normalização determinística, LLM só para o texto livre.
3. **Deduplicação**: chave composta por fonte + similaridade (marca/modelo/ano/placa parcial/localização) para agrupar o mesmo item publicado em portais distintos — comum em veículos anunciados simultaneamente em vários portais.
4. **Indexação e alertas**: item publicado na vitrine e confrontado com os filtros salvos; casamentos geram alertas (WhatsApp/e-mail) respeitando janela de silêncio e não-repetição — regras herdadas do dispatcher do Promo.
5. **Comparador (agregado)**: job que consolida preços de referência por bem (marca/modelo/ano/faixa de KM) a partir dos anúncios de usados e calcula o **score de oportunidade** de cada lote de leilão (desconto do lance vs. mediana de mercado) — mesma lógica do score de preço histórico do Promo.

### 8.2 Modelo de dados (núcleo)

- `sources` — fontes monitoradas (nome, URL, `kind: auction | marketplace`, tipo de parser, status, agenda, dispatch_enabled, scraping_allowed).
- `auctions` — pregões (fonte, leiloeiro, datas de 1ª/2ª praça, modalidade online/presencial, link oficial). Aplicável apenas a fontes `auction`.
- `categories` — árvore de categorias (Veículos > Caminhões; Máquinas > Agrícolas; Imóveis; Diversos).
- `category_fields` — definição dos campos dinâmicos por categoria (nome, tipo, obrigatório, unidade).
- `items` — item normalizado, unificando lote e anúncio: `item_type: lot | listing`, campos comuns (título, categoria, preço [lance inicial ou preço pedido], localização geocodificada, status, link oficial, imagens, `auction_id` nulo para anúncios) + `attributes JSONB` com os campos da categoria (ex.: veículo: placa mascarada, KM, ano, combustível, câmbio, situação do documento; máquina: horímetro, ano, estado).
- `item_duplicates` — vínculos entre publicações do mesmo item em fontes distintas (canônico + espelhos).
- `price_references` — preço de referência consolidado por bem (categoria + marca/modelo/ano/faixa de KM): mediana, mínimo, máximo, amostra, data de cálculo. Alimenta o comparador.
- `saved_filters` — filtros salvos do usuário (categoria, atributos, faixa de preço, raio em km a partir de CEP/cidade, datas de pregão, origem: leilão/usado/ambos).
- `alerts` — histórico de alertas enviados (usuário, item, canal, timestamp) para não-repetição.
- `users` / `subscriptions` — contas, plano e limites.

### 8.3 Regras de Negócio

**RN-001 — Atribuição obrigatória à fonte.** Todo lote exibido deve conter nome do leiloeiro/portal de origem, link direto para o lote na fonte oficial e data/hora da última coleta.

**RN-002 — Campos dinâmicos por categoria.** A ficha do lote renderiza os campos definidos em `category_fields`; campos ausentes na fonte ficam como "não informado", nunca inferidos.

**RN-003 — Normalização com validação.** Saída do LLM deve validar contra o schema da categoria; lote que falhar 2x na extração entra em fila de revisão manual e não é publicado automaticamente.

**RN-004 — Deduplicação conservadora.** Lotes só são fundidos com similaridade ≥ limiar configurável; em dúvida, permanecem separados com aviso "possível duplicado".

**RN-005 — Ciclo de vida do item.** Lote: `coletado → publicado → pregão_próximo (D-2) → encerrado/retirado`. Anúncio: `coletado → publicado → vendido/removido`. Item não reencontrado em N coletas consecutivas é marcado `possivelmente_retirado` e ocultado da vitrine.

**RN-006 — Alertas.** Disparo somente para lotes novos ou com alteração relevante (queda de lance inicial, nova praça) que casem com filtro salvo; máximo configurável de alertas/dia por usuário; janela de silêncio respeitada; nunca reenviar o mesmo lote ao mesmo usuário.

**RN-007 — Limites por plano.** Plano gratuito: busca + X filtros salvos com alerta diário consolidado. Plano pago: alertas em tempo quase real, mais filtros, raio geográfico e atributos avançados.

**RN-008 — Robustez de coleta.** Parser que retornar 0 lotes ou variação anormal (> Y% vs. média) gera incidente no painel admin e suspende publicação da fonte até verificação.

**RN-009 — Conformidade.** Não armazenar dados pessoais de arrematantes/proprietários/vendedores eventualmente presentes nas descrições (mascarar placa/chassi/nomes/telefones na normalização); respeitar robots.txt e termos de uso por fonte, com flag `scraping_allowed` avaliada no cadastro da fonte.

**RN-010 — Comparador leilão × usado.** O score de oportunidade de um lote só é exibido quando o preço de referência tiver amostra mínima configurável (ex.: ≥ 5 anúncios comparáveis de mesma marca/modelo/ano ± 1 e faixa de KM); abaixo disso, exibir "sem referência de mercado suficiente", nunca um score de amostra fraca.

**RN-011 — Coleta dirigida no módulo Usados.** Marketplaces não são varridos integralmente: a coleta usa termos de busca derivados dos filtros salvos ativos e das categorias habilitadas, com teto de páginas/requisições por fonte por ciclo, priorizando fontes Tier 1.

### 8.4 Funcionalidades

**Portal público (vitrine)**
- Busca unificada com filtros por origem (leilão / usado / ambos), categoria, atributos dinâmicos, preço, localização (raio) e data de pregão.
- Página do lote: ficha normalizada, galeria (conforme RN-001/premissa 2), contagem regressiva do pregão, **score de oportunidade com preço de referência de mercado** (RN-010) e botão "Ver no leilão oficial".
- Página do anúncio (usado): ficha normalizada, comparação com o preço de referência do modelo e botão "Ver anúncio na fonte".
- Página do pregão: todos os lotes de uma sessão.
- Comparador: dado um bem (ex.: Hilux 2019), visão lado a lado dos lotes em leilão e dos anúncios de usados disponíveis.
- Cadastro/login e gestão de filtros salvos.

**Alertas**
- WhatsApp (via API ZConnect RH) e e-mail; digest diário no plano gratuito, near-real-time no pago.

**Painel admin (/admin)**
- CRUD de fontes (leilão e marketplace), categorias e campos dinâmicos; gestão de termos de busca da coleta dirigida (RN-011); fila de revisão de normalização; monitor de saúde dos scrapers (RN-008); métricas (itens/fonte, taxa de extração, cobertura do preço de referência, alertas enviados, CTR para a fonte).

### 8.5 Stack e deploy

- Backend: Python 3.11, FastAPI, SQLAlchemy async, APScheduler; scrapers httpx/BeautifulSoup + Playwright para fontes JS.
- Frontend: React 18 + TypeScript + Vite + Tailwind (portal e admin).
- Banco: PostgreSQL 16 (JSONB para atributos; PostGIS ou cálculo de raio via earthdistance para geobusca).
- Deploy: Docker Compose com projeto isolado (`-p zconnect_leilao`), portas próprias, publicado pelo nginx do host em subdomínio `leilao.zconnect.ia.br` *(a confirmar)*. Princípio aditivo: nenhum container existente é alterado.
- Config de runtime em tabela `settings` (padrão Promo), não em `.env`.

### 8.6 Monetização

1. **Assinatura** (principal): alertas personalizados, filtros avançados e comparador leilão × usado.
2. **Lead/afiliação** com leiloeiros parceiros (destaque de lotes, rastreio de cliques) e programas de afiliados dos marketplaces onde existirem (ex.: Mercado Livre, já usado no Promo).
3. **Futuro**: serviços agregados por veículo (consulta veicular, laudo) via parceiros.

## 9. Fases de Entrega

| Fase | Escopo | Critério de aceite |
|---|---|---|
| F1 — MVP Leilão | 3–5 fontes de leilão de veículos, normalização LLM, vitrine com busca básica | Lotes navegáveis com link à fonte e ficha normalizada |
| F2 — MVP Usados | Fontes Tier 1 (ML, Webmotors, NaPista, Compre Car, iCarros), coleta dirigida, busca unificada por origem | Anúncios navegáveis; busca leilão/usado/ambos funcional |
| F3 — Alertas + Comparador | Filtros salvos, dispatcher WhatsApp/e-mail, planos free/pago, `price_references` e score de oportunidade | Alerta < 30 min após publicação (pago); score exibido conforme RN-010 |
| F4 — Escala | +10 fontes de leilão, OLX (Tier 2), categorias máquinas/equipamentos, deduplicação plena, geobusca por raio | Duplicados fundidos ≥ limiar; busca por raio funcional |
| F5 — Parcerias | Painel de leiloeiro parceiro, rastreio de leads, destaque pago | Relatório de CTR/leads por fonte |

## 10. Riscos e Mitigações

| Risco | Impacto | Mitigação |
|---|---|---|
| Quebra de layout das fontes | Perda de coleta | RN-008 + parser por fonte + testes de contrato |
| Bloqueio anti-bot (OLX, marketplaces) | Fonte indisponível | Coleta dirigida (RN-011), rate limit educado, cache, rotação de agenda; OLX só na F4, com Playwright e avaliação de proxy |
| Volume do módulo Usados estourar o servidor compartilhado | Infra | Coleta dirigida + retenção curta de anúncios encerrados + teto de requisições por ciclo; monitorar antes de ampliar termos |
| Questionamento de termos de uso | Jurídico | Modelo vitrine+link, sem cópia de fotos em massa, opt-out por fonte |
| Custo de LLM na normalização | Financeiro | Modelo barato + normalização determinística nos portais estruturados + cache por hash da descrição + extração só no delta |
| Score de oportunidade enganoso (amostra fraca) | Confiança do usuário | RN-010: amostra mínima obrigatória |
| Duplicação incorreta | Confiança do usuário | RN-004 conservadora + revisão manual |

---

*Documento gerado como contexto para desenvolvimento assistido por IA. Placeholders a confirmar: nome definitivo do produto, subdomínio, lista inicial de fontes de leilão, termos de busca iniciais do módulo Usados e limites por plano.*
