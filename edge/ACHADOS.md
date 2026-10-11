# Cloudflare Workers no plano gratuito — o que foi medido

Investigação de 10/10/2026 sobre levar o ZConnect Leilão inteiro para o plano
gratuito do Cloudflare Workers. Tudo aqui é medição, não estimativa.

## Resultado em uma linha

**Tudo cabe no plano gratuito, desde que a coleta seja fatiada.** Parsear a
página inteira numa invocação custa 96 ms contra um teto de 10 ms; parsear
três lotes por invocação custa 6,4 ms. O teto é por invocação, e nada obriga
a fazer a página de uma vez.

## O teto

O plano gratuito dá **10 ms de CPU por invocação**, tanto em requisição HTTP
quanto em Cron Trigger. Espera de rede não conta; parsing conta.

## A prova de conceito funciona

`src/parsers/htmlrewriter.ts` reproduz o parser do Mega Leilões usando
HTMLRewriter, a API de parsing em streaming da Cloudflare (LOL HTML, escrita em
Rust). Rodando contra a página real de `megaleiloes.com.br/veiculos`, extraiu os
**48 lotes** com título, preço, cidade, lote, imagem, link do pregão e as duas
praças aninhadas — o mesmo que o parser em Python entrega.

A tradução de árvore para fluxo funcionou: onde o Python fazia `select_one`
dentro do card, aqui há uma máquina de estado que abre um registro no `data-key`
e fecha no `onEndTag`.

## Onde esbarra

| Medição | Valor | Teto gratuito |
|---|---|---|
| Parsing da página real do Mega (225 KB, 48 lotes) | **96,2 ms** | 10 ms |
| Parsing da fixture recortada (19 KB, 5 lotes) | 8,6 ms | 10 ms |
| Mesma fixture, Python + lxml | 31,2 ms | — |
| Normalização determinística | 2,3 ms/item | cabe fatiada |
| Escritas no D1 por dia | ~7,4 mil | 100 mil |
| Armazenamento | 23 MB | 5 GB |

O HTMLRewriter é **3,6× mais rápido que o Python**, e ainda assim fica **10×
acima do teto** na página real. Não há o que otimizar depois disso: ele já é a
ferramenta mais rápida disponível na plataforma, implementada em Rust dentro do
runtime. A listagem do Leilo tem 734 KB, o triplo do Mega.

Fatiar não resolve: HTMLRewriter é streaming do começo ao fim, então pegar os
últimos lotes exige atravessar todos os anteriores. O custo total vira O(n²).

## O Freitas não é alcançável de um Worker, em nenhum plano

```
fetch("https://www.freitasleiloeiro.com.br/")
  → Error: internal error; reference = m7onri1j4ftcgaqj3hmon2u4
```

A causa está fora da Cloudflare:

```
verify error:num=20: unable to get local issuer certificate
verify error:num=21: unable to verify the first certificate
```

A fonte serve uma cadeia de certificado incompleta. Por isso ela tem
`verify_ssl: false` na configuração do scraper em Python. O `fetch` do Workers
não expõe como ignorar validação de certificado — e isso não muda no plano pago.

Testado também sem TLS e sem `www`, por via das dúvidas: todas falham igual,
porque o site redireciona para HTTPS antes de servir.

```
http://www.freitasleiloeiro.com.br/   → internal error
https://freitasleiloeiro.com.br/      → internal error
http://freitasleiloeiro.com.br/       → internal error
```

### Causa raiz, provada

Não é bloqueio de rede: falando TCP na mão pela porta 80, o servidor **conecta
e responde** (301 para HTTPS, em 182 ms). O que quebra é só o TLS.

```
Certificado do site:      CN=*.freitasleiloeiro.com.br
  emitido por:            GlobalSign GCC R6 AlphaSSL CA 2025
Intermediário entregue:   AlphaSSL CA - SHA256 - G2   (expirado em 20/02/2024)
```

O servidor entrega um intermediário que não é o emissor do certificado dele, e
que por cima está vencido. A cadeia não fecha. O intermediário correto está
publicado no próprio AIA do certificado:

```
http://secure.globalsign.com/cacert/gsgccr6alphasslca2025.crt
```

Navegador busca esse arquivo sozinho e por isso não acusa nada; `fetch` de
Worker, curl e integrações em geral não buscam, e falham.

Testado e descartado:
- `http://` e sem `www` — o servidor responde 301 para HTTPS antes de servir.
- Outros hosts da mesma zona (`app.`, `api.`, `portal.`) — todos com o mesmo
  certificado e o mesmo erro 21.
- O endpoint AJAX que o scraper usa (`/Leiloes/PesquisarLotes`) — mesmo host.

**Não há rota alternativa.** A correção é de minutos e é do lado deles: trocar
o intermediário no arquivo de cadeia do servidor. O texto pronto para enviar
está em `AVISO-FREITAS.md`.

Enquanto isso não acontece, restam duas saídas, e uma delas pode já estar
resolvida sem fazer nada: **o `fetch` em produção pode buscar o intermediário
pelo AIA**, o que o runtime local não faz. Isso só se confirma no primeiro
deploy — e é barato descobrir.

## Duas armadilhas de medição encontradas no caminho

**`wrangler dev --local` não aplica `[limits] cpu_ms`.** Configurar o teto e ver
a invocação sobreviver não prova nada: um laço de 60 milhões de iterações em JS
puro, que leva segundos de CPU, também sobrevive. Qualquer conclusão tirada
desse enforcement é falsa.

**Drenar o corpo num `WritableStream` é ~2,5× mais lento que `arrayBuffer()`**
(28,9 ms contra 8,6 ms na mesma fixture), porque o ralo em JS força uma ida ao
JS por chunk. A intuição de "descartar é mais barato que materializar" está
errada aqui.

## A saída: recortar antes de parsear

Buscar string é ordens de grandeza mais barato que construir árvore. O
coletor acha cada `data-key="` com `indexOf`, recua até a abertura da `<div>`
e corta o bloco daquele lote. A página de 225 KB vira 48 blocos de ~3,8 KB.

| Operação | CPU (relógio) |
|---|---|
| Recortar a página inteira em 48 blocos | **0,5 ms** |
| Parsear 1 bloco | 2,25 ms |
| Parsear 2 blocos numa passada | 3,6 ms |
| **Parsear 3 blocos numa passada** | **6,4 ms** ✅ |
| Parsear 4 blocos | 13,2 ms ❌ |

Parsear em lote divide o custo fixo do HTMLRewriter (compilar os seletores)
entre os blocos, por isso 3 blocos custam menos que 3× um bloco. Acima de 3 o
tamanho domina e estoura.

**Três lotes por invocação** é o ponto de operação, com 36% de folga — e
folga importa, porque o número acima é relógio medido no `wrangler dev` local.

Isso vira uma fila em estágios, cada um com seu próprio orçamento de 10 ms:

1. `coletar` — busca a listagem, recorta, enfileira os blocos. Fetch não conta
   CPU; o recorte custa 0,5 ms.
2. `parsear` — tira 3 blocos da fila, extrai os campos, grava o registro cru.
3. `normalizar` — aplica marca/modelo/condição e promove as colunas.

Uma página do Mega vira ~16 invocações de parsing. Com 3 fontes coletadas a
cada 4 h, são algumas centenas de invocações por dia contra um teto de 100 mil.

## O que isso implica

- **Vitrine** (Pages + Worker de leitura + D1): cabe folgado. Ler do D1 e
  serializar JSON não tem parsing de HTML, que é o que estoura o orçamento.
- **Coleta**: cabe, fatiada em estágios de 3 lotes por invocação. O que não
  cabe é a página inteira de uma vez.
- **D1** aguenta este produto com folga em volume e armazenamento. O banco nunca
  foi o problema.

## Como reproduzir

```bash
cd edge && npm install
npx wrangler dev --port 8787 --local

curl "http://127.0.0.1:8787/?fontes=1"   # alcance das 3 fontes
curl "http://127.0.0.1:8787/?real=5"     # parsing da página real do Mega
curl "http://127.0.0.1:8787/?n=50"       # parsing da fixture recortada
curl "http://127.0.0.1:8787/?queima=60"  # controle: mostra que o teto não é aplicado
```
