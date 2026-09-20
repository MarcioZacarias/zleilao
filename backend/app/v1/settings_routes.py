import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import SettingsUpdateRequest
from app.settings_service import get_all_settings, get_setting, update_settings

logger = logging.getLogger("zleilao.settings")
router = APIRouter()

GROUP_LABELS = {
    "llm": "Normalização (LLM)", "pipeline": "Pipeline", "health": "Saúde da coleta (RN-008)",
    "scraping": "Coleta", "portal": "Portal", "branding": "Marca",
    "alerts": "Alertas (RN-006/RN-007)", "email": "E-mail (SMTP)",
    "whatsapp": "WhatsApp", "accounts": "Contas de usuário",
    "comparator": "Comparador (RN-010)",
}


@router.get("")
async def list_settings(db: AsyncSession = Depends(get_db)):
    grouped: dict[str, dict] = {}
    for s in await get_all_settings(db):
        g = grouped.setdefault(s["group"], {"label": GROUP_LABELS.get(s["group"], s["group"]), "items": []})
        g["items"].append({"key": s["key"], "value": s["value"], "label": s["label"], "is_secret": s["is_secret"]})
    return grouped


@router.put("")
async def save_settings(body: SettingsUpdateRequest, db: AsyncSession = Depends(get_db)):
    clean = {k: v for k, v in body.settings.items() if v != "********"}
    await update_settings(db, clean)
    return {"status": "ok", "updated": len(clean)}


@router.post("/test-llm")
async def test_llm(db: AsyncSession = Depends(get_db)):
    """Faz uma chamada minima ao modelo configurado para validar chave e modelo."""
    api_key = await get_setting(db, "llm_api_key", "")
    model = await get_setting(db, "llm_model", "claude-haiku-4-5")
    if not api_key:
        return {"ok": False, "detail": "Preencha e salve a API Key antes de testar."}
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=api_key, max_retries=0, timeout=30.0)
    try:
        resp = await client.messages.create(
            model=model, max_tokens=64,
            messages=[{"role": "user", "content": "Responda apenas: ok"}],
        )
    except anthropic.AuthenticationError:
        return {"ok": False, "detail": "API Key inválida."}
    except anthropic.NotFoundError:
        return {"ok": False, "detail": f"Modelo '{model}' não encontrado."}
    except anthropic.RateLimitError:
        return {"ok": False, "detail": "Rate limit atingido — a chave funciona, tente de novo em instantes."}
    except anthropic.APIStatusError as exc:
        return {"ok": False, "detail": f"API respondeu {exc.status_code}: {str(exc)[:200]}"}
    except anthropic.APIConnectionError as exc:
        return {"ok": False, "detail": f"Sem conexão com a API: {exc.__class__.__name__}"}
    text = next((b.text for b in resp.content if b.type == "text"), "")
    usage = getattr(resp, "usage", None)
    return {
        "ok": True, "model": resp.model, "reply": text[:80],
        "usage": {"input": getattr(usage, "input_tokens", None), "output": getattr(usage, "output_tokens", None)},
        "detail": f"Conexão ok com {resp.model}.",
    }


class TestEmailRequest(BaseModel):
    to: str


@router.post("/test-email")
async def test_email(body: TestEmailRequest, db: AsyncSession = Depends(get_db)):
    """Envia uma mensagem real para o endereco informado. Vale mais que validar
    a configuracao no papel: SMTP costuma falhar so' no envio."""
    from app.notify.email import EmailUnavailable, is_valid_email, send_email

    if not is_valid_email(body.to):
        return {"ok": False, "detail": "Informe um e-mail valido para o teste."}
    html = (
        "<p>Este e um teste de configuracao do <b>ZConnect Leilao</b>.</p>"
        "<p>Se voce recebeu esta mensagem, o SMTP esta funcionando e os alertas "
        "por e-mail podem ser enviados.</p>"
    )
    try:
        await send_email(db, body.to, "Teste de envio — ZConnect Leilão", html)
    except EmailUnavailable as exc:
        return {"ok": False, "detail": f"SMTP indisponivel: {exc}"}
    except Exception as exc:
        return {"ok": False, "detail": f"Falha no envio: {exc}"}
    return {"ok": True, "detail": f"Mensagem enviada para {body.to}. Confira a caixa (e o spam)."}


@router.post("/test-whatsapp")
async def test_whatsapp(body: TestEmailRequest, db: AsyncSession = Depends(get_db)):
    """`to` aqui e o telefone com DDD."""
    from app.notify.whatsapp import WhatsAppUnavailable, normalize_phone, send_whatsapp

    if not normalize_phone(body.to):
        return {"ok": False, "detail": "Telefone invalido. Use DDD + numero."}
    try:
        await send_whatsapp(db, body.to, "Teste de configuracao do ZConnect Leilao. Se voce recebeu, o canal esta ok.")
    except WhatsAppUnavailable as exc:
        return {"ok": False, "detail": str(exc)}
    except Exception as exc:
        return {"ok": False, "detail": f"Falha no envio: {exc}"}
    return {"ok": True, "detail": f"Mensagem enviada para {body.to}."}
