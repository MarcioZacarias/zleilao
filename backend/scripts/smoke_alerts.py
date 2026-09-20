"""Fluxo completo da F2 contra a API rodando, com um SMTP de mentira local.

    .venv/Scripts/python scripts/smoke_alerts.py http://localhost:8005

Faz: sobe um servidor SMTP em memória, aponta as settings para ele, cria uma
conta, verifica o e-mail pelo link recebido, salva um filtro, roda o matcher e
o dispatcher, e confere a mensagem entregue. Ao final restaura as settings.
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
from email import message_from_bytes

import httpx

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8005").rstrip("/")
ADMIN = ("admin@zconnect.ia.br", "admin123")
SMTP_PORT = 8026
# O backend roda em container: "127.0.0.1" la' dentro e' o proprio container.
# O compose expoe `host.docker.internal` justamente para este caso.
SMTP_HOST_FOR_BACKEND = os.environ.get("SMOKE_SMTP_HOST", "host.docker.internal")
inbox: list = []
failures = 0


def local_ip() -> str:
    """IP da maquina na rede local. Escutar em 0.0.0.0 nao serve: o aiosmtpd
    confirma a subida conectando no proprio hostname, e no Windows 0.0.0.0 nao
    e' um destino valido."""
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


async def reset_filter_clock(filter_id: int) -> None:
    """Volta `last_checked_at` do filtro no tempo para forçar o casamento.
    É manipulação de teste, feita por SQL de propósito: não existe (nem deve
    existir) endpoint para reavaliar o histórico de um filtro."""
    proc = await asyncio.create_subprocess_exec(
        "docker", "exec", "zleilao-db", "psql", "-U", "zleilao", "-d", "zleilao", "-At", "-c",
        f"update saved_filters set last_checked_at = now() - interval '30 days' where id = {int(filter_id)}",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()


def show(label: str, ok: bool, detail: str = "") -> bool:
    """O console do Windows usa cp1252: a saida passa por um filtro para o
    script nao morrer num acento no meio do relatorio."""
    global failures
    if not ok:
        failures += 1
    line = f"{'OK ' if ok else 'ERR'} {label:<46} {detail[:150]}"
    enc = sys.stdout.encoding or "utf-8"
    print(line.encode(enc, "replace").decode(enc, "replace"))
    return ok


class Handler:
    async def handle_DATA(self, server, session, envelope):
        msg = message_from_bytes(envelope.content)
        body = ""
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                body = part.get_payload(decode=True).decode("utf-8", "replace")
        inbox.append({"to": envelope.rcpt_tos, "subject": msg["Subject"], "html": body})
        return "250 OK"


async def main() -> int:
    from aiosmtpd.controller import Controller

    bind = local_ip()
    controller = Controller(Handler(), hostname=bind, port=SMTP_PORT)
    controller.start()
    smtp_for_backend = bind if SMTP_HOST_FOR_BACKEND == "auto" else SMTP_HOST_FOR_BACKEND
    print(f"SMTP de teste em {bind}:{SMTP_PORT} (backend usa {smtp_for_backend})\n")

    async with httpx.AsyncClient(timeout=90.0, follow_redirects=False) as c:
        tok = (await c.post(f"{BASE}/v1/auth/login", json={"email": ADMIN[0], "password": ADMIN[1]})).json()
        h = {"Authorization": f"Bearer {tok['access_token']}"}

        # ── configura o ambiente de teste ───────────────────────────
        original = {}
        cur = (await c.get(f"{BASE}/v1/settings", headers=h)).json()
        for group in cur.values():
            for it in group["items"]:
                original[it["key"]] = it["value"]
        test_settings = {
            "smtp_host": smtp_for_backend, "smtp_port": str(SMTP_PORT), "smtp_user": "", "smtp_password": "",
            "smtp_from_email": "alertas@zconnect.ia.br", "smtp_starttls": "false", "smtp_ssl": "false",
            "email_enabled": "true", "alerts_enabled": "true", "require_email_verification": "true",
            "public_base_url": "http://localhost:5177", "quiet_start": "", "quiet_end": "",
            "match_lookback_hours": "720", "free_digest_hour": str(__import__("datetime").datetime.now().hour),
        }
        await c.put(f"{BASE}/v1/settings", headers=h, json={"settings": test_settings})
        show("configura SMTP de teste", True, "porta local, janela de silêncio desligada")

        # ── cadastro ────────────────────────────────────────────────
        email = f"teste+{__import__('time').time_ns()}@exemplo.com.br"
        r = await c.post(f"{BASE}/v1/auth/register", json={
            "name": "Comprador Teste", "email": email, "password": "senha-forte-123", "phone": "(11) 98765-4321"})
        show("POST /auth/register", r.status_code == 201, r.json().get("detail", r.text))
        await asyncio.sleep(0.8)

        got = [m for m in inbox if email in m["to"]]
        show("e-mail de verificação chegou", bool(got), got[0]["subject"] if got else "caixa vazia")
        if not got:
            return 1
        m = re.search(r"/verificar-email\?token=([A-Za-z0-9_\-]+)", got[0]["html"])
        show("link de verificação no corpo", bool(m), m.group(0)[:60] if m else got[0]["html"][:120])
        if not m:
            return 1

        # login antes de verificar já funciona (a verificação trava o alerta, não o acesso)
        r = await c.post(f"{BASE}/v1/auth/login", json={"email": email, "password": "senha-forte-123"})
        show("POST /auth/login (usuário)", r.status_code == 200, f"role={r.json().get('role')}")
        uh = {"Authorization": f"Bearer {r.json()['access_token']}"}

        r = await c.get(f"{BASE}/v1/me", headers=uh)
        me = r.json()
        show("GET /me antes de verificar", r.status_code == 200 and not me["email_verified"],
             f"plano={me.get('plan')} limite_filtros={me.get('filters_limit')}")

        # ── usuário comum NÃO acessa o admin ────────────────────────
        r = await c.get(f"{BASE}/v1/sources", headers=uh)
        show("usuário comum bloqueado em /v1/sources", r.status_code == 403, f"HTTP {r.status_code}")
        r = await c.get(f"{BASE}/v1/users", headers=uh)
        show("usuário comum bloqueado em /v1/users", r.status_code == 403, f"HTTP {r.status_code}")

        # ── verifica o e-mail ───────────────────────────────────────
        r = await c.post(f"{BASE}/v1/auth/verify-email", params={"token": m.group(1)})
        show("POST /auth/verify-email", r.status_code == 200, r.text[:80])
        r = await c.post(f"{BASE}/v1/auth/verify-email", params={"token": m.group(1)})
        show("token de uso único não reaproveita", r.status_code == 400, f"HTTP {r.status_code}")

        # ── filtro salvo ────────────────────────────────────────────
        r = await c.post(f"{BASE}/v1/me/filters", headers=uh,
                         json={"criteria": {"category": "carros", "price_max": 200000}, "channels": ["email"]})
        show("POST /me/filters", r.status_code == 201, r.json().get("name", r.text)[:80])
        fid = r.json().get("id")

        r = await c.get(f"{BASE}/v1/me/filters/{fid}/preview", headers=uh)
        show("GET /me/filters/{id}/preview", r.status_code == 200, f"{r.json().get('total')} lotes casam hoje")

        # limite do plano gratuito (RN-007)
        limit = me["filters_limit"]
        for i in range(limit + 2):
            rr = await c.post(f"{BASE}/v1/me/filters", headers=uh,
                              json={"criteria": {"brand": f"Marca{i}"}, "channels": ["email"]})
            if rr.status_code == 403:
                show("RN-007: limite de filtros do plano gratuito", True, rr.json().get("detail", "")[:90])
                break
        else:
            show("RN-007: limite de filtros do plano gratuito", False, "não bloqueou")

        # ── matcher: filtro novo não recebe histórico ───────────────
        # Nem lote publicado antes dele, nem queda de preço anterior ao seu
        # último check. Um filtro recém-criado que dispara dezenas de alertas
        # parece spam e queima o canal.
        inbox.clear()
        await c.post(f"{BASE}/v1/jobs/match/run", headers=h)
        await asyncio.sleep(3)
        r = await c.get(f"{BASE}/v1/alerts", headers=h, params={"status": "pending"})
        mine = [a for a in r.json() if (a.get("user") or {}).get("email") == email]
        show("filtro novo não recebe histórico", len(mine) == 0,
             f"{len(mine)} alertas para a conta nova" + (f" ({mine[0]['reason']})" if mine else ""))

        # ── disparo real: relógio do filtro volta no tempo ──────────
        await reset_filter_clock(fid)
        inbox.clear()
        await c.post(f"{BASE}/v1/jobs/match/run", headers=h)
        await asyncio.sleep(4)
        r = await c.get(f"{BASE}/v1/alerts", headers=h, params={"status": "pending"})
        mine = [a for a in r.json() if (a.get("user") or {}).get("email") == email]
        show("matcher gera alertas ao reavaliar", len(mine) > 0, f"{len(mine)} pendentes")

        await c.post(f"{BASE}/v1/jobs/dispatch/run", headers=h)
        await asyncio.sleep(5)
        got = [m for m in inbox if email in m["to"]]
        show("e-mail de alerta entregue", bool(got), got[0]["subject"] if got else "caixa vazia")
        if got:
            html = got[0]["html"]
            show("alerta traz fonte e link do lote (RN-001)",
                 "/lote/" in html and "última coleta" in html, "link + data da coleta no corpo")
            show("alerta traz o disclaimer", "agregador" in html.lower(), "")

        r = await c.get(f"{BASE}/v1/me/alerts", headers=uh)
        sent = [a for a in r.json() if a["status"] == "sent"]
        show("GET /me/alerts mostra o histórico", len(sent) > 0, f"{len(sent)} enviados")

        # RN-006: rodar de novo não reenvia o mesmo lote
        inbox.clear()
        await c.post(f"{BASE}/v1/jobs/match/run", headers=h)
        await asyncio.sleep(2)
        await c.post(f"{BASE}/v1/jobs/dispatch/run", headers=h)
        await asyncio.sleep(3)
        repeated = len([m for m in inbox if email in m["to"]])
        show("RN-006: não reenvia o mesmo lote", repeated == 0, f"{repeated} e-mails repetidos")

        # ── plano pago, ativado pelo admin ──────────────────────────
        uid = (await c.get(f"{BASE}/v1/me", headers=uh)).json()["id"]
        r = await c.put(f"{BASE}/v1/users/{uid}/plan", headers=h,
                        json={"plan": "pro", "months": 1, "note": "teste automatizado"})
        show("PUT /users/{id}/plan -> pro", r.status_code == 200 and r.json().get("plan") == "pro",
             f"expira {str(r.json().get('plan_expires_at'))[:10]}")
        r = await c.get(f"{BASE}/v1/me", headers=uh)
        show("plano pago libera mais filtros e tempo real",
             r.json()["filters_limit"] > 3 and r.json()["realtime_alerts"],
             f"limite={r.json()['filters_limit']} tempo_real={r.json()['realtime_alerts']}")

        r = await c.get(f"{BASE}/v1/users/summary", headers=h)
        show("GET /users/summary", r.status_code == 200, str(r.json())[:130])

        # ── restaura as settings originais ──────────────────────────
        restore = {k: v for k, v in original.items() if k in test_settings and v != "********"}
        await c.put(f"{BASE}/v1/settings", headers=h, json={"settings": restore})
        show("settings restauradas", True, f"{len(restore)} chaves")
        return 0 if failures == 0 else 1

if __name__ == "__main__":
    try:
        code = asyncio.run(main())
    finally:
        print(f"\nFALHAS: {failures}")
    sys.exit(code)
