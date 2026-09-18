# ZConnect Leilão

Agregador de leilões de veículos (e, nas próximas fases, anúncios de usados) com
vitrine pública, normalização por LLM e painel administrativo. Não realiza leilões nem
intermedeia lances: toda ficha aponta para a fonte oficial.

- Especificação: [docs/EF-ZLE-001-ZConnect-Leilao.md](docs/EF-ZLE-001-ZConnect-Leilao.md)
- Decisões e desvios da EF: [docs/DECISOES.md](docs/DECISOES.md)
- Contrato da API: [docs/API.md](docs/API.md)
- Como o sistema funciona por dentro: [SISTEMA.md](SISTEMA.md)
- Deploy e operação: [DEPLOY.md](DEPLOY.md)

## Estrutura

```
backend/    FastAPI + SQLAlchemy async + APScheduler (Python 3.11)
  app/scrapers/   parsers por fonte (megaleiloes, freitas, leilo, generic_html)
  app/engine/     masking, classifier, deterministic, normalizer (LLM), dedup, lifecycle, health
  app/scheduler/  jobs de fundo
  app/v1/         rotas (portal público + admin)
  tests/          testes unitários com fixtures HTML reais
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
