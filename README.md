# ZConnect Leilão

Agregador de leilões de veículos, máquinas e equipamentos: vitrine pública com busca,
alertas por e-mail, comparação com a tabela FIPE e busca por raio. **Não realiza leilões
nem intermedeia lances** — toda ficha aponta para a fonte oficial, com a data da última
coleta à vista.

- Especificação: [docs/EF-ZLE-001-ZConnect-Leilao.md](docs/EF-ZLE-001-ZConnect-Leilao.md)
- Decisões e desvios da EF: [docs/DECISOES.md](docs/DECISOES.md)
- Contrato da API: [docs/API.md](docs/API.md)
- Como o sistema funciona por dentro: [SISTEMA.md](SISTEMA.md)
- Deploy e operação: [DEPLOY.md](DEPLOY.md)

## O que está pronto

| | |
|---|---|
| **Coleta** | 3 fontes com parser próprio + parser genérico configurável no admin (lista única ou duas etapas), com robots.txt, retry e detecção de quebra de layout |
| **Normalização** | regras determinísticas por categoria; LLM opcional, com cache por hash da descrição. Campo ausente vira "não informado" — nunca inferido |
| **Vitrine** | busca com facetas, ficha com fonte e data de coleta, pregões, deduplicação conservadora entre fontes |
| **Contas e alertas** | filtros salvos, alerta por e-mail (WhatsApp opcional), planos free/pago, janela de silêncio |
| **Comparador** | referência FIPE, custo total (lance + comissão + despesas) e desconto estimado, sempre com as ressalvas na tela |
| **Busca por raio** | 5.571 municípios versionados no repositório, sem PostGIS e sem API de geocodificação |
| **Parcerias** | aberturas de ficha e cliques de saída por fonte, com CTR real |

## Estrutura

```
backend/    FastAPI + SQLAlchemy async + APScheduler (Python 3.11)
  app/scrapers/   parsers por fonte (megaleiloes, freitas, leilo) + generic_html
  app/engine/     classifier, deterministic, normalizer (LLM), dedup, lifecycle,
                  health, masking, search, matcher, comparator, fipe, opportunity,
                  geo, metrics
  app/notify/     e-mail, WhatsApp, templates e dispatcher dos alertas
  app/scheduler/  8 jobs de fundo
  app/v1/         rotas (portal público, conta do assinante, admin)
  app/data/       base de municípios (coordenada, população IBGE, nome)
  tests/          72 testes com fixtures HTML reais
dashboard/  React 18 + TypeScript + Vite + Tailwind (portal em / e admin em /admin)
docker/     compose base + overrides dev/prod + server block do nginx do host
docs/       EF, decisões, contrato da API
```

## Subir localmente

```bash
cp .env.example .env
./deploy.sh
```

Portal: http://localhost:5177 · Admin: http://localhost:5177/admin · API: http://localhost:8005/docs

Testes: `cd backend && .venv/Scripts/python -m pytest -q`

## Configuração

Só as variáveis de boot ficam no `.env` (banco, `SECRET_KEY`, admin inicial). Tudo que é
operacional — chave de LLM, SMTP, intervalos dos jobs, limites por plano, textos da
vitrine — fica na tabela `system_settings`, editável em **Admin → Configurações**. Sem
chave de LLM o sistema publica com as regras determinísticas; sem SMTP os alertas ficam
na fila em vez de serem marcados como enviados.
