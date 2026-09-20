# Decisões de implementação — F1 (MVP Leilão)

Registro do que foi decidido ao implementar a EF-ZLE-001 v1.1, onde a implementação
difere do texto da EF e por quê. Data: 18/09/2026.

## Escopo entregue na F1

- Três fontes reais de leilão de veículos, verificadas contra o site em 18/09/2026:
  **Mega Leilões** (HTML server-side), **Freitas Leiloeiro** (AJAX `PesquisarLotes`) e
  **Leilo** (JSON embutido em `__INITIAL_STATE__`). Mais um parser **genérico por
  seletores CSS** para cadastrar leiloeiros simples pelo admin sem código.
- Pipeline completo: coleta → mascaramento (RN-009) → classificação → extração
  determinística → LLM com JSON validado por schema (RN-003) → validação por
  categoria (RN-002) → ciclo de vida (RN-005) → deduplicação conservadora (RN-004) →
  saúde da coleta (RN-008).
- Vitrine pública com busca, facetas, ficha do lote, página do pregão e redirect
  rastreado para a fonte oficial (RN-001 + métrica de CTR).
- Painel admin: fontes, categorias e campos, itens, fila de revisão, incidentes,
  duplicados, jobs, configurações e branding.

## Fontes avaliadas e descartadas (por enquanto)

| Fonte | Motivo | Quando reavaliar |
|---|---|---|
| Sodré Santoro | Nuxt; lotes carregados por API client-side (`prd-api.sodresantoro.com.br`) com token Sanctum embutido na página e endpoint `/api/v1/lots` marcado "Depreciado". Exige engenharia reversa da API ou Playwright. | F4, junto com o worker de Playwright |
| Superbid / Vip Leilões | Plataforma Next.js com API própria; Vip redireciona para Superbid. | F4 |
| Copart | Página inicial vazia sem JS; anti-bot. | F4 |
| Milan, Lance Certo | Cloudflare "Just a moment" (403). | F4 com proxy |
| Zukerman | Foco em imóveis. | Categoria Imóveis |
| Palácio dos Leilões, Parque dos Leilões, Rogério Menezes, Leilões Brasil | Server-side simples; candidatos ao parser genérico. Não calibrados. | Sob demanda via admin |

## Onde a implementação difere da EF e por quê

1. **`auction_sessions` em vez de "1ª/2ª praça" fixas.** Leilão de seguradora e
   financeira tem sessão única, repasse e lance condicional (visto no Leilo e no Freitas).
   Mega Leilões (judicial) usa 1ª/2ª praça. A tabela de sessões cobre os dois.
2. **`item_price_history`.** A RN-006 (F3) precisa detectar queda de lance; sem histórico
   não há como. Também alimenta o comparador da F3.
3. **`plate_hash` (HMAC) em vez de "placa parcial" para deduplicar.** Resolve o conflito
   RN-004 × RN-009: a placa completa nunca é armazenada, mas o hash permite casar o mesmo
   veículo em portais diferentes. A versão exibida é `ABC-****`.
4. **`items.condition` promovido a coluna** (normal / sinistro_* / sucata / nao_informado).
   É o que impedirá o comparador (F3) de chamar um sinistrado de "oportunidade". O
   prompt do LLM é explícito: só marca sinistro quando o anúncio afirma isso sobre o
   bem, ignorando texto jurídico padrão.
5. **`extraction_version` e `extraction_cache`.** Permite reextrair quando prompt ou
   schema mudarem e evita pagar LLM duas vezes pelo mesmo texto.
6. **`raw_items` grava payload só quando o hash muda**, com retenção configurável.
7. **Extração determinística sempre roda**; o LLM complementa. Sem API key, o sistema
   publica com menos campos em vez de travar. Chave e modelo ficam em `system_settings`.
8. **Nomes de partes (autor/réu) não são armazenados.** O parser do Mega Leilões lê a
   Vara (comitente) e o leiloeiro (profissional público), mas ignora os campos Autor/Réu.
9. **APScheduler de fato** (a EF pedia; o Promo usa loops asyncio). Intervalos vêm da
   tabela settings e são lidos no boot.
10. **Sem Playwright na F1.** O servidor compartilhado tem 1 vCPU e 3,8 GB; as três fontes
    escolhidas dispensam navegador. Fontes que exigem JS ficam para a F4, idealmente em
    worker separado.
11. **Portas 8005 / 5177** no servidor (próximas livres após o Promo). Subdomínio
    `leilao.zconnect.ia.br` mantido como placeholder a confirmar.
12. **A fonte tem a palavra final sobre o próprio lote.** O ciclo de vida não encerra
    um item por data de sessão enquanto a fonte o declarar aberto. Em leilão de
    seguradora e financeira o lote segue à venda depois do pregão (repasse, lance
    condicional, condicional negada). Sem esse guard, 35 dos 72 lotes do Leilo sumiam
    da vitrine justamente por serem a oportunidade ativa. O item também reabre quando
    a fonte volta a declará-lo aberto.
13. **Marcadores de "sem informação" não viram dado.** "SI", "Sem Informação", "N/I" e
    afins são descartados na coleta; sem isso a vitrine exibia "Sem Informação / SI"
    como se fosse a cidade do lote.
14. **Placeholder de imagem da fonte é descartado.** O Mega Leilões serve
    `card-no-image` com a própria marca quando o lote não tem foto; exibi-lo mostraria
    o logo do leiloeiro no lugar do veículo.
15. **A extração concluída substitui as colunas promovidas, inclusive com nulo.**
    Preservar o valor anterior faria uma correção de regra nunca limpar um dado errado
    já gravado.
16. **Sem API key de LLM o sistema publica assim mesmo**, só com as regras
    determinísticas. Uma instalação nova não pode ficar com a vitrine vazia esperando
    alguém configurar o modelo.

17. **Varredura parcial não gera retirada.** O parser informa se viu o catálogo
    inteiro; só então a ausência de um item conta para `misses` (RN-005).
18. **Volume estável vira o novo normal.** A RN-008 recalibra a média depois de três
    coletas consistentes, e resolver o incidente no admin também recalibra.
19. **Jobs perdidos são reexecutados** (`misfire_grace_time` de 1 h). A limpeza diária
    foi pulada por 7h20 numa hibernação da máquina, sem nenhum aviso.

## Limitações conhecidas (F1)

- **Mascaramento de placa tem falso positivo** em códigos de modelo com o formato
  `AAA-0000`: "PLAINA AGRICOLA BALDAN PDM-3000" vira "PDM-****". O trade-off é
  deliberado (RN-009 é conservadora: mascarar a mais é preferível a vazar placa),
  mas polui o título de máquinas e equipamentos. Reavaliar na F4, quando a categoria
  de máquinas entrar de fato.
- **Cobertura do Leilo é parcial**: a paginação é client-side sem endpoint público,
  então cada consulta traz 36 lotes. A cobertura vem de consultar a página geral mais
  os leilões ativos individualmente (`per_auction`), não do catálogo inteiro.
- **A RN-008 dispara quando os limites de coleta mudam.** Alterar `max_pages` no
  cadastro dobra o volume e a fonte é suspensa por variação anormal — comportamento
  correto, mas exige resolver o incidente no admin depois de mudar a configuração.
- **`extraction_cache` e `_raw`**: reextrair um item usa o payload já gravado em
  `attributes._raw`; correções no parser só alcançam o item na próxima coleta que o
  reencontrar.

## Recomendações mantidas para as próximas fases (da revisão da EF)

- Inverter F2 e F3: alertas + filtros salvos (só leilão) antes do módulo Usados, porque
  a RN-011 depende de filtros salvos e porque a monetização chega antes do risco
  jurídico/anti-bot dos marketplaces.
- Comparador: exigir `condition` conhecido, somar comissão (já capturada em
  `_raw.comissao_pct` no Freitas/Leilo) ao lance e considerar FIPE como referência
  complementar ao preço pedido de anúncios.
- Alertas 1:1 por WhatsApp em escala exigem API oficial da Meta; o dispatcher de grupos
  do Promo não serve para assinantes individuais.
- Definir gateway de pagamento e provedor de e-mail antes da F3.

## Placeholders que continuam a confirmar

- Nome definitivo do produto e subdomínio.
- Chave da API do LLM (configurar em Configurações → Normalização) e teto de custo.
- Lista final de fontes além das três da F1.

---

# Onda 3 — comparador (RN-010) e avaliação do módulo de usados

## A mudança de rota, e por quê

A EF previa calcular o preço de referência pela **mediana de anúncios de
marketplaces**. Ao avaliar as fontes uma a uma, essa base se mostrou frágil
e juridicamente arriscada:

| Fonte | O que o robots.txt diz | Situação |
|---|---|---|
| Webmotors | `Disallow: /comprar/` (as páginas de anúncio), exceto 9 marcas premium; `Disallow: /api/detail/` | A listagem e `/api/search/car` não são proibidas e entregam dados ricos (inclusive km e percentual sobre a FIPE), mas o anúncio em si é restrito |
| Mercado Livre | `Disallow: /` para agentes de IA (ClaudeBot, GPTBot, PerplexityBot e outros) | Intenção declarada contra coleta automatizada |
| iCarros | `Disallow: /ache/listaanuncios.jsp` — justamente a listagem | Restrito |
| OLX | já era Tier 2 na EF (anti-bot forte) | Mantido fora |

**Decisão: a tabela FIPE passa a ser a referência primária do comparador.**
Ela é pública, feita para consulta, atualizada mensalmente, e é a referência
que o mercado brasileiro de fato usa — inclusive os leiloeiros, que publicam
"X% da FIPE" nos próprios anúncios. Isso entrega o valor central da EF (saber
se o lote é oportunidade) sem depender de scraping de terceiros.

O módulo de usados **não é descartado**: `sources.kind = marketplace` e
`items.item_type = listing` continuam no modelo, e `price_references` aceita
`source_kind = "listings"`. Quando houver autorização de uma fonte — acordo
comercial, API oficial ou programa de afiliados — os anúncios entram como
complemento. O que muda é que o comparador não fica refém disso.

## Como o score é calculado, e as três correções em relação à EF

1. **Custo total, não o lance.** O arrematante paga lance + comissão do
   leiloeiro + despesas de pátio. Medido num lote real: lance de R$ 21.600
   vira R$ 26.560 de custo, e o desconto cai de 45% para 32%. Comparar o lance
   cru com a FIPE infla o desconto em mais de dez pontos.

2. **Condição do bem entra na conta.** Um sinistrado a 60% da FIPE não é
   oportunidade, é o preço dele. A RN-010 exigia só amostra mínima; sem olhar
   a condição, o comparador recomendaria justamente os piores lotes, que são
   os de maior "desconto". Sinistro e sucata não são excluídos — entram com a
   referência ajustada por um fator explícito, que aparece nas razões.

3. **O lance inicial é o piso, não o preço final.** O lote vai a pregão e o
   valor sobe. O score declara isso: é o desconto **máximo possível**, não o
   provável.

## Condição presumida — onde a RN-002 termina e o comparador começa

Sem LLM configurado, a maioria dos lotes fica com `condition = nao_informado`,
e a regra acima zerava o comparador inteiro (medido: 32 de 43 lotes sem score).

A saída **não** foi inferir o campo, o que violaria a RN-002. O campo continua
"não informado" na ficha. O que existe é uma **premissa do comparador**, com
três travas:

- só vale para retomada de **financeira, frota ou locadora** — leilões que
  destacam sinistro quando há, e onde o silêncio é informativo. Não vale para
  seguradora (onde sinistro é a regra) nem para judicial (onde a descrição
  raramente fala do estado do bem);
- qualquer menção a dano, avaria, sinistro ou sucata derruba a premissa;
- o score é **penalizado em 15%** pela incerteza e a razão declara, com todas
  as letras, que a condição foi presumida e deve ser conferida na fonte.

Desligável em Configurações (`comparator_presume_condition`).

## Validação

Rodado contra a API FIPE real: 30 referências obtidas, com casamento de modelo
entre 0,66 e 0,96 de confiança. O casamento é conservador — "Gol" nunca casa
com "Golf", porque o que separa modelos é a primeira palavra. Dos 11 scores
calculados, um (Honda XRE 2021) saiu com desconto negativo: o lance inicial já
estava acima da FIPE. É exatamente o tipo de armadilha que o comparador existe
para expor.


---

# Onda 4 — cadastrar fontes novas sem código

O parser genérico ganhou um **modo de duas etapas**: a home lista pregões e
cada pregão lista os lotes. É a estrutura mais comum entre leiloeiros de porte
médio, e sem ela o parser só serviria para o formato de lista única, que é
minoria. Com ela, adicionar uma fonte vira preencher um JSON no admin.

Validado contra o Parque dos Leilões (robots.txt: `Disallow:` vazio, tudo
liberado): 56 lotes reais coletados em dois pregões, sem uma linha de código
nova. A configuração usada está em `backend/tests/test_generic_parser.py`, que
serve de modelo para cadastrar outras fontes.

Candidatos já sondados e com robots.txt permissivo, prontos para cadastro:
Parque dos Leilões e Palácio dos Leilões. Rogério Menezes respondeu bem mas não
foi calibrado.


---

# Onda 4 — a busca por raio na tela, e três coisas que o teste visual pegou

A implantação das ondas 3 e 4 na interface expôs problemas que os testes
unitários não pegariam, porque nenhum deles é uma função errada: são decisões
de produto erradas.

**1. Cidade não reconhecida alargava a busca.** Pedir "60 km de São Paulo" com
a cidade grafada de um jeito que a base não reconhece fazia `radius_center`
devolver `None`, e o filtro era simplesmente pulado — o usuário pedia um raio e
recebia o país inteiro, sem aviso. Agora `apply_filters` não casa nada nesse
caso e a vitrine responde 400 com o motivo. **O erro seguro é para menos.**

**2. O autocomplete ordenava por tamanho do nome.** Digitar "camp" oferecia
Campanha, Campestre e Campinaçu; Campinas nem aparecia, porque a varredura
parava nos primeiros 32 achados e ordenava um recorte arbitrário da tabela. A
base ganhou a população do IBGE (tabela 6579, 2021 — 5.548 dos 5.571 municípios
casaram) e o nome de exibição com acento. A população não entra em nenhum
cálculo de distância: existe só para ordenar a lista. O arquivo foi de 200 KB
para 315 KB, o que continua barato para uma base offline e determinística.

**3. A ordem "mais perto" não se explicava.** A lista vinha reordenada e nada na
tela dizia por quê. O card agora traz `distance_km` ("· 39 km"), e o mesmo
município aparece como "sua cidade" em vez de "0 km". O número é a distância
entre centroides de município, não até o pátio — a ficha diz isso.

Além disso, o filtro salvo passou a carregar as três chaves do raio: sem elas,
"criar alerta desta busca" com raio ativo salvava um critério nacional, e o
usuário receberia por e-mail o oposto do que via na tela ao salvar.

O painel de comparação saiu da coluna fixa para baixo da galeria: a memória de
cálculo precisa de largura, e a coluna da direita já era a mais alta das duas.
