import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { BellPlus } from "lucide-react";
import { useAuth } from "../../context/AuthContext";
import { Button } from "../ui/Button";
import { FilterFormDrawer } from "../conta/FilterFormDrawer";
import { accountApi } from "../../services/account";
import { criteriaFromParams } from "../../lib/criteria";
import type { AccountMe } from "../../services/types";

/** Marca na URL a intenção de criar o alerta, preservada através do login. */
export const CREATE_ALERT_PARAM = "criar_alerta";

/**
 * O gancho principal do produto: transforma a busca atual em filtro salvo.
 * Sem sessão, manda para /entrar levando a busca inteira em `next` — o
 * usuário volta exatamente aqui e o formulário abre sozinho.
 */
export function CreateAlertButton({ className = "" }: { className?: string }) {
  const [sp, setSp] = useSearchParams();
  const { token } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [me, setMe] = useState<AccountMe | null>(null);

  const criteria = criteriaFromParams(sp);
  const wanted = sp.get(CREATE_ALERT_PARAM) === "1";

  // whatsapp_channel_available decide se o canal aparece no formulário.
  useEffect(() => {
    if (!token || !open || me) return;
    let alive = true;
    accountApi
      .me()
      .then((d) => alive && setMe(d))
      .catch(() => alive && setMe(null));
    return () => {
      alive = false;
    };
  }, [token, open, me]);

  // Voltando do login com a intenção preservada: abre e limpa a URL.
  useEffect(() => {
    if (!wanted) return;
    const next = new URLSearchParams(sp);
    next.delete(CREATE_ALERT_PARAM);
    setSp(next, { replace: true });
    if (token) setOpen(true);
  }, [wanted, token, sp, setSp]);

  const start = () => {
    if (token) {
      setOpen(true);
      return;
    }
    const target = new URLSearchParams(sp);
    target.set(CREATE_ALERT_PARAM, "1");
    const next = `/busca?${target.toString()}`;
    navigate(`/entrar?next=${encodeURIComponent(next)}`);
  };

  return (
    <>
      <Button variant="accent" size="sm" className={className} onClick={start}>
        <BellPlus size={14} /> Criar alerta desta busca
      </Button>

      <FilterFormDrawer
        open={open}
        onClose={() => setOpen(false)}
        criteria={criteria}
        whatsappAvailable={!!me?.whatsapp_channel_available}
        onSaved={() => navigate("/conta?aba=filtros")}
      />
    </>
  );
}
