import { FormEvent, useEffect, useState } from "react";
import { KeyRound, Save } from "lucide-react";
import { toast } from "sonner";
import { Button } from "../ui/Button";
import { Toggle } from "../ui/Toggle";
import { accountApi } from "../../services/account";
import { errorMessage } from "../../services/api";
import type { AccountMe } from "../../services/types";
import { isValidPhone, isValidTimeWindow, maskPhone, phoneDigits } from "../../lib/format";

const MIN_PASSWORD = 8;

interface PerfilSectionProps {
  me: AccountMe;
  onSaved: (me: AccountMe) => void;
}

export function PerfilSection({ me, onSaved }: PerfilSectionProps) {
  const [name, setName] = useState(me.name ?? "");
  const [phone, setPhone] = useState(maskPhone(me.phone));
  const [emailOptIn, setEmailOptIn] = useState(me.email_opt_in);
  const [whatsOptIn, setWhatsOptIn] = useState(me.whatsapp_opt_in);
  const [quietStart, setQuietStart] = useState(me.quiet_start ?? "");
  const [quietEnd, setQuietEnd] = useState(me.quiet_end ?? "");
  const [saving, setSaving] = useState(false);

  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [changing, setChanging] = useState(false);

  useEffect(() => {
    setName(me.name ?? "");
    setPhone(maskPhone(me.phone));
    setEmailOptIn(me.email_opt_in);
    setWhatsOptIn(me.whatsapp_opt_in);
    setQuietStart(me.quiet_start ?? "");
    setQuietEnd(me.quiet_end ?? "");
  }, [me]);

  const saveProfile = async (e: FormEvent) => {
    e.preventDefault();
    if (phone && !isValidPhone(phone)) {
      toast.error("Telefone inválido. Informe DDD + número.");
      return;
    }
    if (!isValidTimeWindow(quietStart) || !isValidTimeWindow(quietEnd)) {
      toast.error("A janela de silêncio usa o formato HH:MM.");
      return;
    }
    if (whatsOptIn && !phone) {
      toast.error("Cadastre um telefone antes de ativar o WhatsApp.");
      return;
    }
    setSaving(true);
    try {
      const updated = await accountApi.update({
        name: name.trim(),
        phone: phone ? phoneDigits(phone) : null,
        email_opt_in: emailOptIn,
        whatsapp_opt_in: me.whatsapp_channel_available ? whatsOptIn : false,
        quiet_start: quietStart || null,
        quiet_end: quietEnd || null,
      });
      onSaved(updated);
      toast.success("Perfil atualizado");
    } catch (err) {
      toast.error(errorMessage(err, "Não foi possível salvar o perfil"));
    }
    setSaving(false);
  };

  const changePassword = async (e: FormEvent) => {
    e.preventDefault();
    if (next.length < MIN_PASSWORD) {
      toast.error(`A nova senha precisa ter ao menos ${MIN_PASSWORD} caracteres.`);
      return;
    }
    if (next !== confirm) {
      toast.error("As senhas não conferem.");
      return;
    }
    setChanging(true);
    try {
      await accountApi.changePassword(current, next);
      setCurrent("");
      setNext("");
      setConfirm("");
      toast.success("Senha alterada");
    } catch (err) {
      toast.error(errorMessage(err, "Não foi possível alterar a senha"));
    }
    setChanging(false);
  };

  return (
    <div className="space-y-6">
      <form onSubmit={saveProfile} className="portal-card p-5">
        <h2 className="text-lg font-bold text-radar-text">Perfil</h2>
        <p className="mt-0.5 text-sm text-radar-muted">Seus dados e como podemos falar com você.</p>

        <div className="mt-5 grid gap-4 sm:grid-cols-2">
          <div>
            <label className="mb-1 block text-sm font-medium text-radar-text/90" htmlFor="perfil-nome">
              Nome
            </label>
            <input
              id="perfil-nome"
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={100}
              className="portal-input"
              autoComplete="name"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-radar-text/90" htmlFor="perfil-email">
              E-mail
            </label>
            <input id="perfil-email" value={me.email} disabled className="portal-input opacity-60" />
            <p className="mt-1 text-xs text-radar-muted">
              Para trocar o e-mail da conta, fale com o suporte.
            </p>
          </div>
          <div className="sm:col-span-2">
            <label className="mb-1 block text-sm font-medium text-radar-text/90" htmlFor="perfil-telefone">
              Telefone
            </label>
            <input
              id="perfil-telefone"
              type="tel"
              inputMode="numeric"
              value={phone}
              onChange={(e) => setPhone(maskPhone(e.target.value))}
              className="portal-input sm:max-w-xs"
              placeholder="(11) 98765-4321"
              autoComplete="tel"
            />
          </div>
        </div>

        <div className="mt-6 border-t border-radar-border pt-5">
          <h3 className="text-sm font-semibold text-radar-text">Onde você aceita receber alertas</h3>
          <div className="mt-3 space-y-3">
            <div className="flex items-center justify-between gap-4 rounded-lg bg-radar-surface2/40 px-3 py-2.5">
              <div className="min-w-0">
                <p className="text-sm text-radar-text">E-mail</p>
                <p className="text-xs text-radar-muted">Avisos dos filtros salvos em {me.email}.</p>
              </div>
              <Toggle checked={emailOptIn} onChange={setEmailOptIn} />
            </div>

            {/* O canal só aparece quando o servidor tem WhatsApp ligado. */}
            {me.whatsapp_channel_available && (
              <div className="flex items-center justify-between gap-4 rounded-lg bg-radar-surface2/40 px-3 py-2.5">
                <div className="min-w-0">
                  <p className="text-sm text-radar-text">WhatsApp</p>
                  <p className="text-xs text-radar-muted">
                    {phone ? "Mensagens no número cadastrado acima." : "Cadastre um telefone para ativar."}
                  </p>
                </div>
                <Toggle checked={whatsOptIn} onChange={setWhatsOptIn} disabled={!phone} />
              </div>
            )}
          </div>
        </div>

        <div className="mt-6 border-t border-radar-border pt-5">
          <h3 className="text-sm font-semibold text-radar-text">Janela de silêncio</h3>
          <p className="mt-0.5 text-xs text-radar-muted">
            Horário em que não queremos te incomodar. Deixe os dois campos em branco para usar a janela padrão do
            sistema.
          </p>
          <div className="mt-3 flex flex-wrap items-end gap-3">
            <div>
              <label className="mb-1 block text-xs text-radar-muted" htmlFor="quiet-start">
                Início (HH:MM)
              </label>
              <input
                id="quiet-start"
                type="time"
                value={quietStart}
                onChange={(e) => setQuietStart(e.target.value)}
                className="portal-input w-32"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-radar-muted" htmlFor="quiet-end">
                Fim (HH:MM)
              </label>
              <input
                id="quiet-end"
                type="time"
                value={quietEnd}
                onChange={(e) => setQuietEnd(e.target.value)}
                className="portal-input w-32"
              />
            </div>
            {(quietStart || quietEnd) && (
              <button
                type="button"
                onClick={() => {
                  setQuietStart("");
                  setQuietEnd("");
                }}
                className="pb-2 text-xs text-radar-muted hover:text-radar-text"
              >
                Usar a janela padrão
              </button>
            )}
          </div>
        </div>

        <div className="mt-6 flex justify-end">
          <Button type="submit" variant="accent" loading={saving}>
            <Save size={15} /> Salvar perfil
          </Button>
        </div>
      </form>

      <form onSubmit={changePassword} className="portal-card p-5">
        <h2 className="text-lg font-bold text-radar-text">Trocar senha</h2>
        <div className="mt-4 grid gap-4 sm:grid-cols-3">
          <div>
            <label className="mb-1 block text-sm font-medium text-radar-text/90" htmlFor="senha-atual">
              Senha atual
            </label>
            <input
              id="senha-atual"
              type="password"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
              required
              autoComplete="current-password"
              className="portal-input"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-radar-text/90" htmlFor="senha-nova">
              Nova senha
            </label>
            <input
              id="senha-nova"
              type="password"
              value={next}
              onChange={(e) => setNext(e.target.value)}
              required
              minLength={MIN_PASSWORD}
              autoComplete="new-password"
              className="portal-input"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-radar-text/90" htmlFor="senha-confirma">
              Repita a nova senha
            </label>
            <input
              id="senha-confirma"
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              required
              minLength={MIN_PASSWORD}
              autoComplete="new-password"
              className="portal-input"
            />
          </div>
        </div>
        <div className="mt-4 flex items-center justify-between gap-3">
          <p className="text-xs text-radar-muted">Mínimo de {MIN_PASSWORD} caracteres.</p>
          <Button type="submit" variant="outline-dark" loading={changing}>
            <KeyRound size={15} /> Alterar senha
          </Button>
        </div>
      </form>
    </div>
  );
}
