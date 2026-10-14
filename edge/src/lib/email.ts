/**
 * Envio de e-mail a partir do Worker.
 *
 * O Worker não fala SMTP: o envio precisa ir por um provedor com API HTTP
 * (Resend, Brevo, SES…). O provedor ainda não foi escolhido, então
 * `enviarEmail` hoje sempre recusa com `EmailIndisponivel`. Quem chama trata
 * isso como o backend em Python trata SMTP desligado: a conta é criada mesmo
 * assim e o usuário pode pedir o reenvio depois.
 *
 * Para ligar um provedor, basta implementar o `fetch` dentro de `enviarEmail`
 * e guardar a chave como segredo do Worker. Os templates abaixo não mudam.
 */
import type { Env } from "../tipos";

export class EmailIndisponivel extends Error {}

export async function enviarEmail(
  _env: Env,
  _para: string,
  _assunto: string,
  _html: string,
): Promise<void> {
  throw new EmailIndisponivel("nenhum provedor de e-mail configurado no Worker");
}

/* ── Templates (mesmo visual do backend em Python) ─────────────────── */

const FUNDO = "#0b1020";
const DESTAQUE = "#f59e0b";
const TEXTO = "#e8ecf8";
const APAGADO = "#93a0c4";

function moldura(titulo: string, intro: string, conteudo: string, base: string, nota = ""): string {
  return `<!DOCTYPE html>
<html lang="pt-BR"><body style="margin:0;padding:24px;background:${FUNDO};font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:0 auto">
    <tr><td style="padding-bottom:20px">
      <div style="color:${DESTAQUE};font-size:20px;font-weight:800">ZConnect Leilão</div>
      <div style="color:${APAGADO};font-size:13px">${titulo}</div>
    </td></tr>
    <tr><td style="color:${TEXTO};font-size:15px;padding-bottom:16px">${intro}</td></tr>
    <tr><td>${conteudo}</td></tr>
    <tr><td style="padding-top:20px;border-top:1px solid rgba(255,255,255,.08);color:${APAGADO};font-size:12px;line-height:1.6">
      ${nota}
      O ZConnect Leilão é um agregador: não realiza leilões, não recebe lances nem intermedeia
      transações. Os dados vêm dos sites dos leiloeiros e podem estar desatualizados — confira
      sempre a fonte oficial antes de participar.
      <div style="margin-top:10px"><a href="${base}/conta" style="color:${APAGADO}">Gerenciar meus alertas</a></div>
    </td></tr>
  </table>
</body></html>`;
}

function botao(link: string, rotulo: string, rodape: string): string {
  return `
    <a href="${link}" style="display:inline-block;background:${DESTAQUE};color:#1a1200;padding:12px 22px;
       border-radius:8px;text-decoration:none;font-weight:700">${rotulo}</a>
    <div style="color:${APAGADO};font-size:12px;margin-top:14px">${rodape}<br>${link}</div>`;
}

export function emailVerificacao(link: string, base: string): [string, string] {
  return [
    "Confirme seu e-mail — ZConnect Leilão",
    moldura(
      "Confirmação de e-mail",
      "Confirme o endereço para começar a receber seus alertas.",
      botao(link, "Confirmar meu e-mail", "Se o botão não funcionar, copie este endereço:"),
      base,
      "Você recebeu este e-mail porque criou uma conta no ZConnect Leilão. ",
    ),
  ];
}

export function emailRedefinicao(link: string, base: string): [string, string] {
  return [
    "Redefinir sua senha — ZConnect Leilão",
    moldura(
      "Redefinição de senha",
      "Recebemos um pedido para redefinir sua senha.",
      botao(link, "Criar nova senha", "Se você não pediu isso, ignore este e-mail: sua senha continua a mesma."),
      base,
    ),
  ];
}
