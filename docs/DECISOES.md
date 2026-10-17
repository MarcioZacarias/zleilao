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


---

# Onda 5 — o que a EF chamava de CTR não era CTR

O critério de aceite da F5 é "relatório de CTR/leads por fonte". O painel já
mostrava uma coluna "CTR 7d", mas ela era `cliques ÷ lotes publicados` — um
número sem denominador de audiência, que sobe quando a fonte publica menos.
Levar isso para uma conversa comercial seria vender um número que não
significa o que o nome promete.

Passamos a contar **abertura de ficha** (`source_daily_stats`), e a taxa virou
`cliques ÷ aberturas`. Três decisões dentro dessa:

- **Agregado por dia, não evento por visita.** O relatório responde a uma taxa.
  Uma linha por fonte por dia dá a mesma resposta e cabe num servidor de 1 vCPU
  compartilhado; uma tabela de eventos cresceria sem limite pelo mesmo número.
- **Aberturas, não visitantes únicos.** Não identificamos o visitante e não
  vamos criar identificação só para engrossar um número de proposta. A tela
  escreve "aberturas de ficha" e explica o que isso é.
- **Robô não conta.** Sem o filtro de user-agent, o Googlebot entraria no
  relatório como interesse de comprador no lote do parceiro.

A contagem é subordinada à navegação: falha de gravação vira log, nunca erro
para quem está vendo o lote.

**Login de parceiro e destaque pago ficaram para depois** (decisão de
20/09/2026). Sem contrato assinado, login de parceiro é superfície de ataque
nova sem usuário, e destaque pago é viés de ranking que ninguém está pagando.
Quando o primeiro contrato existir, o destaque entra com selo visível de
publicidade — uma vitrine que empurra lote pago sem dizer que é pago perde a
única coisa que ela tem para vender, que é ser confiável.


---

# A fila de revisão, e por que ela estava presa

Sete lotes reais estavam fora da vitrine com o mesmo erro — "campo obrigatório
ausente: marca" — e quatro causas diferentes por trás dele.

**1. A dica da fonte sobrepunha a evidência do título.** O classificador
aceitava a categoria que o leiloeiro informa sempre que ela apontava uma folha
da árvore, sem sequer olhar o título. Como muitos leiloeiros só têm "leves" e
"pesados", "Trator John Deere 5090E" e "PLAINA AGRICOLA BALDAN" foram parar em
Caminhões. Agora a dica só vale quando o título não traz palavra-chave; tendo,
a primeira delas define o bem. "Caminhão com munck" continua caminhão porque
"caminhão" vem antes de "munck".

**2. A herança de campos fazia o contrário do que dizia.** O comentário de
`effective_fields` afirmava que a categoria filha sobrescreve o campo do pai; o
código varria a cadeia da raiz para a folha e ficava com a primeira definição,
ou seja, com a do pai. Nenhuma categoria exercia isso ainda, então o bug estava
dormindo — e era exatamente o que faltava para tornar `marca` opcional em
Outros veículos.

**3. A tabela de marcas não acompanhou a onda 4.** A categoria de máquinas e
equipamentos nasceu ali, mas a lista de marcas continuou sendo só de veículos:
John Deere, Baldan, Case e Caterpillar não existiam. Entraram junto as marcas
exclusivamente de moto que faltavam (Ducati, KTM, Xinling), a sigla `MMC` que o
CRLV usa para Mitsubishi, e um punhado de grafias erradas que as fontes
publicam — "Renalt Kwid" não é inferência nossa: o leiloeiro informou a marca e
digitou errado.

**4. "Veículo Carcaça" não tem marca, e nunca vai ter.** Carcaça, sucata e
monobloco são lotes reais publicados sem marca. Exigi-la é exigir o que a fonte
não tem, e o lote fica numa revisão de onde não sai. `marca` passou a ser
opcional em Outros veículos.

## O que o teste em massa pegou depois

Antes de reclassificar os 546 itens coletados, rodei a regra nova contra todos
eles sem gravar. Doze mudariam — e dois eram **HONDA/HR-V indo para
Utilitários**, porque a palavra-chave `hr ` perdia o espaço na normalização e
casava dentro de "HR-V". O erro já existia no banco antes desta mudança; só
apareceu porque o título passou a ter voz. `hr ` e `fazer` saíram da lista:
palavra-chave de duas letras ou que também é verbo em português não classifica
nada, só erra.

Das doze mudanças restantes, todas eram correções: trailer e carcaças saindo de
Carros, Kangoo e Transit furgão indo para Utilitários. Fila de revisão zerada,
e um único lote segue sem marca — a carcaça, que agora está publicada na
categoria certa.

## Parcelamento em leilão judicial é regra de lei, não do anúncio (17/10/2026)

Pergunta do Márcio: o sistema traz os judiciais, que admitem entrada e
parcelamento em até 30 vezes? Traz — 104 dos 1.915 lotes publicados, todos do
Mega Leilões, a única das três fontes com leilão judicial (Freitas e Leilo são
retomadas extrajudiciais; o "judicial" nos mapas deles é origem do veículo).

O parcelamento vem do art. 895 do CPC de 2015: em leilão judicial de bem
penhorado, proposta por escrito antes do pregão, mínimo de 25% à vista e o
restante em até 30 meses, com garantia; pelo valor da avaliação até o 1º
leilão, não vil no 2º; lance à vista tem preferência e o juiz decide. Como a
regra vale para todo lote judicial, a vitrine sinaliza a partir de
`auction_type` sem coletar nada: selo "pode parcelar" no card, aviso completo
na ficha, atalho "Pode parcelar" na página inicial e rótulo na faceta de tipo
(`components/portal/ParcelamentoJudicial.tsx`).

Sempre "pode admitir", nunca promessa: falência e recuperação judicial seguem
regras próprias, o edital pode restringir, e a proposta é feita no juízo ou
com o leiloeiro. Condições de pagamento continuam fora da coleta — o
normalizador ignora o texto jurídico padrão de propósito, porque ele não
descreve o veículo.

## Deduplicação plena funde só com evidência forte (F4, 17/10/2026)

A F4 pede "duplicados fundidos acima de um limiar". O limiar existe
(`dedup_merge_threshold`), mas o padrão é 1.0, e a pontuação por semelhança
nunca chega lá: só placa igual (hash) ou a mesma URL oficial valem 1.0. O
motivo é leilão de frota: uma locadora vende cinquenta Onix 2022 brancos, mesma
UF, km parecido, e título, ano, km, UF e cor batem entre carros diferentes. A
semelhança máxima sem evidência forte é 0,99, o que ainda gera o vínculo
suspeito para o admin olhar, mas não funde sozinho. Placas conhecidas e
diferentes agora valem zero, para a frota não virar um emaranhado de suspeitos.

O que a fusão faz: o espelho some da busca, das facetas, das contagens e dos
alertas enquanto o canônico (a publicação mais antiga) estiver visível; o card
e a ficha do canônico ganham "também em <fonte>", com o link oficial de cada
publicação. Se o canônico encerra, o espelho volta por conta própria — a
regra está na consulta, não em estado.

Os vínculos passaram a viajar para a borda (`POST /ingest/duplicates`), cada
lado como (fonte, id externo), porque o D1 tem ids próprios. Confirmação e
rejeição do admin também vão, pelo `reviewed_at`.

Leilões BR saiu da lista das sete fontes HTML: é portal de arte, antiguidades e
colecionáveis; os "preços e marcas" da sondagem eram miniaturas. Sobraram seis.
