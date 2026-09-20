# Deploy — ZConnect Leilão

## Servidor compartilhado (produção)

Mesmo host dos demais sistemas ZConnect (1 vCPU, 3,8 GB RAM). Regras sem exceção:

- Todo comando de compose leva `-p zconnect_leilao` e os dois `-f`.
- Não existe container nginx: quem publica é o nginx do host.
- O Postgres não publica porta no host.
- `nginx -t` antes de todo `systemctl reload nginx`.
- Builds do dashboard fora do horário comercial (seguram a única CPU).

| Projeto | Portas (127.0.0.1) |
|---|---|
| Contas | 8001, 5173, 5433, 6380, 3000 |
| CRM | 8002, 5174 |
| Suporte | 8003, 5175 |
| Promo | 8004, 5176 |
| **Leilão** | **8005 (API), 5177 (dashboard)** |

### Primeira instalação

```bash
sudo mkdir -p /opt/zconnect_leilao && sudo chown $USER /opt/zconnect_leilao
git clone <repo> /opt/zconnect_leilao
cd /opt/zconnect_leilao
cp .env.example .env && nano .env      # POSTGRES_PASSWORD, SECRET_KEY, ADMIN_PASSWORD

docker compose --env-file .env -p zconnect_leilao \
  -f docker/docker-compose.yml -f docker/docker-compose.prod.yml up -d --build

curl -s http://127.0.0.1:8005/health     # {"status":"ok"}
```

O primeiro boot cria as tabelas, semeia settings, admin, categorias com campos e as três
fontes da F1 (Mega Leilões, Freitas, Leilo). O scheduler começa a coletar em ~20 s.

### Nginx do host + TLS

```bash
sudo cp docker/nginx/leilao.zconnect.ia.br.conf /etc/nginx/sites-available/leilao.zconnect.ia.br
sudo ln -sf /etc/nginx/sites-available/leilao.zconnect.ia.br /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d leilao.zconnect.ia.br --redirect --agree-tos --email marcio.zacarias@radconsult.com.br -n
```

Requisito: DNS A de `leilao.zconnect.ia.br` apontando para o servidor.

### Atualizações

Manual: `git pull` + o mesmo `docker compose ... up -d --build`. Ou pelo GitHub Actions
(`.github/workflows/deploy.yml`, disparo manual, secrets `DEPLOY_*`).

### Pós-deploy

1. Entrar em `/admin` com `ADMIN_EMAIL`/`ADMIN_PASSWORD` e trocar a senha.
2. Configurações → Normalização (LLM): colar a API Key, salvar, **Testar LLM**.
   Sem chave o sistema roda só com regras determinísticas.
3. Fontes → "Testar parser" em cada fonte, depois "Coletar agora".
4. Acompanhar em Jobs e Incidentes. A vitrine mostra itens quando `normalize` e
   `lifecycle` rodarem (5 e 30 min por padrão; ou "Rodar agora" em Jobs).

## Desenvolvimento local

```bash
cp .env.example .env
./deploy.sh                 # sobe db + backend + dashboard com o override de dev
# ou, sem Docker para o app:
docker compose --env-file .env -p zconnect_leilao -f docker/docker-compose.yml -f docker/docker-compose.override.yml up -d postgres
cd backend && python -m venv .venv && .venv/Scripts/pip install -r requirements.txt -r requirements-dev.txt
.venv/Scripts/uvicorn app.main:app --reload --port 8005
cd ../dashboard && npm install && npm run dev      # http://localhost:5177
```

Testes: `cd backend && .venv/Scripts/python -m pytest -q`.

Pipeline manual (primeira carga, diagnóstico), com limites para não martelar as fontes:

```bash
cd backend
DATABASE_URL=postgresql+asyncpg://zleilao:<senha>@localhost:5439/zleilao SCHEDULER_ENABLED=false \
  .venv/Scripts/python scripts/run_pipeline_once.py --max-pages 1 --details 3
.venv/Scripts/python scripts/smoke_api.py http://localhost:8005 admin@zconnect.ia.br <senha>
```

Na máquina de desenvolvimento a porta 5434 já é usada por outro projeto; o `.env` local usa `DB_PORT=5439`.

## Configuração pós-deploy das ondas 2 a 4

Ordem que importa: **sem SMTP, nenhum alerta sai** — eles ficam na fila e o job
de envio para o ciclo, em vez de marcá-los como entregues.

1. **E-mail (obrigatório para alertas).** Configurações → E-mail (SMTP): servidor,
   porta, usuário, senha, remetente. Use **Testar e-mail** antes de seguir: manda
   uma mensagem real, que é o único teste que vale.
2. **URL pública.** Configurações → Contas → `public_base_url`. É o endereço que
   entra nos links de confirmação de e-mail e nos alertas. Errado aqui significa
   links quebrados na caixa do assinante.
3. **WhatsApp (opcional, desligado por padrão).** Só ligue sabendo do risco: envio
   1:1 para não-contatos por API não oficial pode levar ao banimento do número.
   Exige `whatsapp_tenant` — sem o header `x-tenant` a API responde 404 e o envio
   falha em silêncio.
4. **LLM (opcional).** Sem chave o sistema publica com as regras determinísticas,
   e o comparador usa a premissa de condição (ver DECISOES.md). Com chave, a
   extração fica bem melhor e o score deixa de ser presumido.
5. **Comparador.** Já vem ligado. A API FIPE tem limite de requisições: o job
   busca até 40 bens por ciclo e retoma no próximo. As referências valem 30 dias.

### Planos

Não há gateway de pagamento. O plano pago é ativado à mão em
**Admin → Usuários → Mudar plano**, com prazo em meses (`0` = sem vencimento,
para cortesia ou parceiro). A estrutura já prevê um gateway quando houver
decisão sobre qual.

## Operação

| Sintoma | Onde olhar |
|---|---|
| Vitrine vazia | Admin → Jobs: `scrape` rodou? `normalize` concluiu? `lifecycle` publicou? Fonte com `dispatch_enabled` e `health_status=ok`? |
| Fonte suspensa | Admin → Incidentes: resolver com "reativar fonte". Antes, "Testar parser" na fonte. |
| Itens em revisão | Admin → Revisão: editar atributos ou reextrair. Ver `extraction_error`. |
| LLM não roda | Configurações → Testar LLM. Job `normalize` com `stopped` em details. |
| Layout da fonte mudou | Parser em `backend/app/scrapers/<fonte>.py`; fixtures em `backend/tests/fixtures/`. |
| Alertas não chegam | Configurações → Testar e-mail. Admin → Alertas mostra o erro de cada um. Assinante com e-mail não verificado não recebe. |
| Assinante reclama de spam | Admin → Usuários → filtros do usuário. Confira a janela de silêncio e o teto diário em Configurações → Alertas. |
| Lote sem score de oportunidade | Normal quando não há referência FIPE ou a condição é desconhecida. Admin → Jobs → comparador mostra o motivo agregado. |
| Fonte suspensa sem parar | Resolver o incidente recalibra a média de volume. Se o volume mudou de vez, três coletas estáveis já resolvem sozinhas. |

Logs: `docker logs -f zleilao-backend`.
