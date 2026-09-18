"""Smoke test da API contra um backend em execucao.

    .venv/Scripts/python scripts/smoke_api.py http://localhost:8005 admin@zconnect.ia.br admin123

Imprime um resumo compacto de cada endpoint (status + campos-chave). Sai com
codigo 1 se algum endpoint essencial falhar.
"""
from __future__ import annotations

import json
import sys

import httpx

base = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8005").rstrip("/")
email = sys.argv[2] if len(sys.argv) > 2 else "admin@zconnect.ia.br"
password = sys.argv[3] if len(sys.argv) > 3 else "admin123"
failed = 0


def show(label: str, resp: httpx.Response, pick=None) -> dict | list | None:
    global failed
    ok = resp.status_code < 400
    if not ok:
        failed += 1
    body = None
    try:
        body = resp.json()
    except ValueError:
        body = resp.text[:200]
    summary = ""
    if pick and isinstance(body, (dict, list)):
        try:
            summary = json.dumps(pick(body), ensure_ascii=False, default=str)[:300]
        except Exception as exc:  # noqa: BLE001
            summary = f"(pick falhou: {exc})"
    elif not ok:
        summary = json.dumps(body, ensure_ascii=False)[:300]
    print(f"{'OK ' if ok else 'ERR'} {resp.status_code} {label:<48} {summary}")
    return body


with httpx.Client(timeout=60.0, follow_redirects=False) as c:
    show("GET /health", c.get(f"{base}/health"), lambda b: b)
    tok = show("POST /v1/auth/login", c.post(f"{base}/v1/auth/login", json={"email": email, "password": password}), lambda b: {"role": b.get("role")})
    headers = {"Authorization": f"Bearer {tok['access_token']}"} if isinstance(tok, dict) and tok.get("access_token") else {}

    show("GET /v1/portal/branding", c.get(f"{base}/v1/portal/branding"), lambda b: {"title": b["site_title"]})
    show("GET /v1/portal/stats", c.get(f"{base}/v1/portal/stats"), lambda b: {k: b[k] for k in ("items_published", "sources_active", "auctions_upcoming_7d")})
    cats = show("GET /v1/portal/categories", c.get(f"{base}/v1/portal/categories"), lambda b: [(x["slug"], x["items_count"], len(x["fields"])) for x in b])
    page = show("GET /v1/portal/items?page_size=3", c.get(f"{base}/v1/portal/items", params={"page_size": 3}),
                lambda b: {"total": b["meta"]["total"], "facets": {k: len(v) for k, v in b["facets"].items()}, "first": (b["items"][0]["title"] if b["items"] else None)})
    show("GET /v1/portal/items?q=fox", c.get(f"{base}/v1/portal/items", params={"q": "fox", "page_size": 3}), lambda b: {"total": b["meta"]["total"]})
    show("GET /v1/portal/items?category=carros&sort=price_asc", c.get(f"{base}/v1/portal/items", params={"category": "carros", "sort": "price_asc", "page_size": 3}),
         lambda b: {"total": b["meta"]["total"], "prices": [x["price"] for x in b["items"]]})
    show("GET /v1/portal/brands", c.get(f"{base}/v1/portal/brands"), lambda b: b[:5])
    show("GET /v1/portal/auctions/upcoming", c.get(f"{base}/v1/portal/auctions/upcoming"), lambda b: [(x["title"], x["items_count"]) for x in b[:3]])
    first_id = page["items"][0]["id"] if isinstance(page, dict) and page.get("items") else None
    if first_id:
        det = show(f"GET /v1/portal/items/{first_id}", c.get(f"{base}/v1/portal/items/{first_id}"),
                   lambda b: {"brand": b["brand"], "model": b["model"], "year": b["year_model"], "cond": b["condition"], "fields": len(b["field_defs"]),
                              "attrs": {k: v for k, v in list(b["attributes"].items())[:6]}, "sessions": len(b["auction"]["sessions"]) if b.get("auction") else 0,
                              "ext": b["extraction_version"]})
        r = c.get(f"{base}/v1/portal/items/{first_id}/go")
        print(f"{'OK ' if r.status_code == 302 else 'ERR'} {r.status_code} {'GET /v1/portal/items/{id}/go':<48} -> {r.headers.get('location', '')[:80]}")
        if isinstance(det, dict) and det.get("auction"):
            show(f"GET /v1/portal/auctions/{det['auction']['id']}", c.get(f"{base}/v1/portal/auctions/{det['auction']['id']}"), lambda b: {"items": len(b["items"])})

    if headers:
        show("GET /v1/dashboard", c.get(f"{base}/v1/dashboard", headers=headers),
             lambda b: {"total": b["items_total"], "status": b["items_by_status"], "extraction": b["items_by_extraction"], "incidents": b["open_incidents"]})
        show("GET /v1/sources", c.get(f"{base}/v1/sources", headers=headers), lambda b: [(x["slug"], x["health_status"], x["last_items_count"], x["items_published"]) for x in b])
        show("GET /v1/sources/parsers", c.get(f"{base}/v1/sources/parsers", headers=headers), lambda b: [x["key"] for x in b])
        show("GET /v1/categories", c.get(f"{base}/v1/categories", headers=headers), lambda b: [x["slug"] for x in b])
        show("GET /v1/items?extraction_status=review", c.get(f"{base}/v1/items", params={"extraction_status": "review"}, headers=headers), lambda b: {"total": b["meta"]["total"]})
        show("GET /v1/items/summary", c.get(f"{base}/v1/items/summary", headers=headers), lambda b: b)
        show("GET /v1/incidents?status=all", c.get(f"{base}/v1/incidents", params={"status": "all"}, headers=headers), lambda b: [(x["kind"], x["status"]) for x in b[:5]])
        show("GET /v1/jobs", c.get(f"{base}/v1/jobs", headers=headers), lambda b: [(x["job_type"], x["status"], x["items_processed"]) for x in b[:6]])
        show("GET /v1/jobs/scheduler", c.get(f"{base}/v1/jobs/scheduler", headers=headers), lambda b: b)
        show("GET /v1/duplicates?status=all", c.get(f"{base}/v1/duplicates", params={"status": "all"}, headers=headers), lambda b: len(b))
        show("GET /v1/settings", c.get(f"{base}/v1/settings", headers=headers), lambda b: list(b.keys()))
        show("POST /v1/settings/test-llm", c.post(f"{base}/v1/settings/test-llm", headers=headers), lambda b: b.get("detail"))
        if first_id:
            show(f"GET /v1/items/{first_id}", c.get(f"{base}/v1/items/{first_id}", headers=headers), lambda b: {"ext": b["extraction_status"], "attempts": b["extraction_attempts"]})
            show(f"POST /v1/items/{first_id}/renormalize", c.post(f"{base}/v1/items/{first_id}/renormalize", headers=headers), lambda b: {"ext": b["extraction_status"], "ver": b["extraction_version"]})
        srcs = c.get(f"{base}/v1/sources", headers=headers).json()
        leilo = next((s for s in srcs if s["slug"] == "leilo"), None)
        if leilo:
            show(f"POST /v1/sources/{leilo['id']}/test", c.post(f"{base}/v1/sources/{leilo['id']}/test", headers=headers),
                 lambda b: {"ok": b["ok"], "found": b["items_found"], "ms": b["duration_ms"], "err": b["error"]})

print("\nFALHAS:", failed)
sys.exit(1 if failed else 0)
