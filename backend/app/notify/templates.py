"""Corpo das mensagens de alerta e de conta.

RN-001 vale tambem fora do portal: todo lote citado leva fonte, data da ultima
coleta e link para o site oficial. O rodape repete que a plataforma nao realiza
leilao nem recebe lance.
"""
from __future__ import annotations

from decimal import Decimal

BRAND_BG = "#0b1020"
SURFACE = "#121a33"
ACCENT = "#f59e0b"
TEXT = "#e8ecf8"
MUTED = "#93a0c4"

REASON_LABELS = {
    "new": "Novo lote",
    "price_drop": "Queda de lance",
    "new_session": "Nova sessão",
}


def brl(value: Decimal | float | None) -> str:
    if value is None:
        return "sob consulta"
    return f"R$ {float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def dt_br(value) -> str:
    return value.strftime("%d/%m/%Y %H:%M") if value else "—"


def _item_line_text(item, source_name: str, reason: str, detail: str | None, base_url: str) -> str:
    bits = [f"*{item.title}*"]
    sub = " · ".join(x for x in [item.brand, item.model, str(item.year_model or "")] if x)
    if sub:
        bits.append(sub)
    bits.append(f"{brl(item.price)}{' (2ª praça: ' + brl(item.price_second) + ')' if item.price_second else ''}")
    if detail:
        bits.append(detail)
    if item.city or item.state:
        bits.append(" / ".join(x for x in [item.city, item.state] if x))
    if item.next_session_at:
        bits.append(f"Pregão: {dt_br(item.next_session_at)}")
    bits.append(f"Fonte: {source_name} · coletado em {dt_br(item.last_seen_at)}")
    bits.append(f"{base_url}/lote/{item.id}")
    return "\n".join(bits)


def whatsapp_message(entries: list[dict], base_url: str, tagline: str = "") -> str:
    """`entries`: [{item, source_name, reason, detail}]"""
    header = "🔨 *ZConnect Leilão*" + (f" — {tagline}" if tagline else "")
    if len(entries) == 1:
        e = entries[0]
        body = f"{REASON_LABELS.get(e['reason'], 'Alerta')} que casa com seu filtro:\n\n" + \
               _item_line_text(e["item"], e["source_name"], e["reason"], e.get("detail"), base_url)
    else:
        body = f"{len(entries)} lotes casaram com seus filtros:\n\n" + "\n\n".join(
            _item_line_text(e["item"], e["source_name"], e["reason"], e.get("detail"), base_url) for e in entries
        )
    footer = ("\n\n_Somos um agregador: o lance é feito no site do leiloeiro. "
              "Confira as condições na fonte oficial._")
    return f"{header}\n\n{body}{footer}"


def _item_card_html(item, source_name: str, reason: str, detail: str | None, base_url: str) -> str:
    sub = " · ".join(x for x in [item.brand, item.model, str(item.year_model or "")] if x)
    price = brl(item.price)
    second = f'<div style="color:{MUTED};font-size:13px">2ª praça: {brl(item.price_second)}</div>' if item.price_second else ""
    detail_html = f'<div style="color:{ACCENT};font-size:13px;margin-top:4px">{detail}</div>' if detail else ""
    local = " / ".join(x for x in [item.city, item.state] if x)
    session = f'<div style="color:{MUTED};font-size:13px">Pregão: {dt_br(item.next_session_at)}</div>' if item.next_session_at else ""
    img = (f'<img src="{item.image_url}" alt="" width="150" '
           f'style="border-radius:8px;display:block;object-fit:cover" />') if item.image_url else ""
    return f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
           style="background:{SURFACE};border:1px solid rgba(255,255,255,.08);border-radius:12px;margin-bottom:12px">
      <tr>
        <td style="padding:16px" valign="top" width="166">{img}</td>
        <td style="padding:16px 16px 16px 0" valign="top">
          <div style="color:{ACCENT};font-size:11px;text-transform:uppercase;letter-spacing:.06em">
            {REASON_LABELS.get(reason, "Alerta")}
          </div>
          <div style="color:{TEXT};font-size:15px;font-weight:600;margin:4px 0">{item.title}</div>
          <div style="color:{MUTED};font-size:13px">{sub}</div>
          <div style="color:{ACCENT};font-size:20px;font-weight:700;margin-top:8px">{price}</div>
          {second}{detail_html}
          <div style="color:{MUTED};font-size:13px;margin-top:6px">{local}</div>
          {session}
          <div style="color:{MUTED};font-size:12px;margin-top:8px">
            Fonte: {source_name} · última coleta {dt_br(item.last_seen_at)}
          </div>
          <a href="{base_url}/lote/{item.id}"
             style="display:inline-block;margin-top:12px;background:{ACCENT};color:#1a1200;
                    padding:9px 16px;border-radius:8px;text-decoration:none;font-weight:600;font-size:14px">
            Ver o lote
          </a>
        </td>
      </tr>
    </table>"""


def _shell(title: str, intro: str, content: str, base_url: str, footer_note: str = "") -> str:
    return f"""<!DOCTYPE html>
<html lang="pt-BR"><body style="margin:0;padding:24px;background:{BRAND_BG};font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:0 auto">
    <tr><td style="padding-bottom:20px">
      <div style="color:{ACCENT};font-size:20px;font-weight:800">ZConnect Leilão</div>
      <div style="color:{MUTED};font-size:13px">{title}</div>
    </td></tr>
    <tr><td style="color:{TEXT};font-size:15px;padding-bottom:16px">{intro}</td></tr>
    <tr><td>{content}</td></tr>
    <tr><td style="padding-top:20px;border-top:1px solid rgba(255,255,255,.08);color:{MUTED};font-size:12px;line-height:1.6">
      {footer_note}
      O ZConnect Leilão é um agregador: não realiza leilões, não recebe lances nem intermedeia
      transações. Os dados vêm dos sites dos leiloeiros e podem estar desatualizados — confira
      sempre a fonte oficial antes de participar.
      <div style="margin-top:10px"><a href="{base_url}/conta" style="color:{MUTED}">Gerenciar meus alertas</a></div>
    </td></tr>
  </table>
</body></html>"""


def alert_email(entries: list[dict], base_url: str) -> tuple[str, str]:
    """Devolve (assunto, html)."""
    n = len(entries)
    if n == 1:
        e = entries[0]
        subject = f"{REASON_LABELS.get(e['reason'], 'Alerta')}: {e['item'].title[:60]}"
        intro = "Um lote casou com um filtro que você salvou."
    else:
        subject = f"{n} lotes novos casaram com seus filtros"
        intro = f"{n} lotes casaram com os filtros que você salvou."
    cards = "".join(
        _item_card_html(e["item"], e["source_name"], e["reason"], e.get("detail"), base_url) for e in entries
    )
    return subject, _shell("Alerta de lotes", intro, cards, base_url)


def verify_email(link: str, base_url: str) -> tuple[str, str]:
    content = f"""
    <a href="{link}" style="display:inline-block;background:{ACCENT};color:#1a1200;padding:12px 22px;
       border-radius:8px;text-decoration:none;font-weight:700">Confirmar meu e-mail</a>
    <div style="color:{MUTED};font-size:12px;margin-top:14px">
      Se o botão não funcionar, copie este endereço:<br>{link}
    </div>"""
    return ("Confirme seu e-mail — ZConnect Leilão",
            _shell("Confirmação de e-mail", "Confirme o endereço para começar a receber seus alertas.",
                   content, base_url, "Você recebeu este e-mail porque criou uma conta no ZConnect Leilão. "))


def reset_email(link: str, base_url: str) -> tuple[str, str]:
    content = f"""
    <a href="{link}" style="display:inline-block;background:{ACCENT};color:#1a1200;padding:12px 22px;
       border-radius:8px;text-decoration:none;font-weight:700">Criar nova senha</a>
    <div style="color:{MUTED};font-size:12px;margin-top:14px">
      Se você não pediu isso, ignore este e-mail: sua senha continua a mesma.<br>{link}
    </div>"""
    return ("Redefinir sua senha — ZConnect Leilão",
            _shell("Redefinição de senha", "Recebemos um pedido para redefinir sua senha.",
                   content, base_url))
