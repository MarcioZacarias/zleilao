import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { SearchX } from "lucide-react";
import { Drawer } from "../ui/Drawer";
import { Button } from "../ui/Button";
import { EmptyState } from "../ui/EmptyState";
import { ItemCardSkeleton } from "../ui/Skeleton";
import { ItemCard } from "../portal/ItemCard";
import { accountApi } from "../../services/account";
import { errorMessage } from "../../services/api";
import type { FilterPreview, SavedFilter } from "../../services/types";
import { criteriaToSearch } from "../../lib/criteria";

const PREVIEW_LIMIT = 6;

/** "Ver o que este filtro pega hoje" — `GET /me/filters/{id}/preview`. */
export function FilterPreviewDrawer({ filter, onClose }: { filter: SavedFilter | null; onClose: () => void }) {
  const [data, setData] = useState<FilterPreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!filter) return;
    let alive = true;
    setLoading(true);
    setError("");
    setData(null);
    accountApi
      .previewFilter(filter.id, PREVIEW_LIMIT)
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(errorMessage(e, "Não foi possível carregar a prévia")))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [filter]);

  return (
    <Drawer
      open={!!filter}
      onClose={onClose}
      tone="dark"
      width="max-w-2xl"
      title={filter ? `O que "${filter.name}" pega hoje` : ""}
      subtitle={filter?.description}
    >
      {error ? (
        <EmptyState tone="dark" icon={SearchX} title="Erro ao carregar" description={error} />
      ) : loading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <ItemCardSkeleton key={i} />
          ))}
        </div>
      ) : data ? (
        <>
          <p className="mb-4 text-sm text-radar-muted">
            {data.total === 0 ? (
              "Nenhum lote na vitrine corresponde a este filtro agora."
            ) : (
              <>
                <strong className="text-radar-text">{data.total.toLocaleString("pt-BR")}</strong>{" "}
                {data.total === 1 ? "lote corresponde" : "lotes correspondem"} a este filtro hoje. O alerta avisa
                apenas sobre novidades daqui para a frente.
              </>
            )}
          </p>

          {data.items.length === 0 ? (
            <EmptyState
              tone="dark"
              icon={SearchX}
              title="Nada por enquanto"
              description="Assim que um lote novo se encaixar no filtro, você recebe o aviso."
            />
          ) : (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              {data.items.map((it) => (
                <ItemCard key={it.id} item={it} compact />
              ))}
            </div>
          )}

          {filter && data.total > data.items.length && (
            <div className="mt-5">
              <Link to={criteriaToSearch(filter.criteria)} onClick={onClose}>
                <Button variant="outline-dark" className="w-full">
                  Ver todos os {data.total.toLocaleString("pt-BR")} lotes na busca
                </Button>
              </Link>
            </div>
          )}
        </>
      ) : null}
    </Drawer>
  );
}
