# Cloudflare Workers no plano gratuito — o que foi medido

Investigação de 10/10/2026 sobre levar o ZConnect Leilão inteiro para o plano
gratuito do Cloudflare Workers. Tudo aqui é medição, não estimativa.

## Resultado em uma linha

**A vitrine cabe no plano gratuito. A coleta não cabe — e não é por falta de
otimização.**

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

## Duas armadilhas de medição encontradas no caminho

**`wrangler dev --local` não aplica `[limits] cpu_ms`.** Configurar o teto e ver
a invocação sobreviver não prova nada: um laço de 60 milhões de iterações em JS
puro, que leva segundos de CPU, também sobrevive. Qualquer conclusão tirada
desse enforcement é falsa.

**Drenar o corpo num `WritableStream` é ~2,5× mais lento que `arrayBuffer()`**
(28,9 ms contra 8,6 ms na mesma fixture), porque o ralo em JS força uma ida ao
JS por chunk. A intuição de "descartar é mais barato que materializar" está
errada aqui.

## O que isso implica

- **Vitrine** (Pages + Worker de leitura + D1): cabe folgado. Ler do D1 e
  serializar JSON não tem parsing de HTML, que é o que estoura o orçamento.
- **Coleta**: precisa de 30 s de CPU, o que só existe no Workers Paid (US$ 5/mês)
  — e mesmo lá o Freitas continua inalcançável.
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
