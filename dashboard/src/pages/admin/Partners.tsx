import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Handshake, MousePointerClick, Eye, RefreshCw, Info } from "lucide-react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from "recharts";
import { partnersApi } from "../../services/operations";
import { errorMessage } from "../../services/api";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import type { PartnersReport } from "../../services/types";
import { Card, CardContent, CardHeader } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { Table, Thead, Th, Tr, Td } from "../../components/ui/Table";
import { TableSkeleton, Skeleton } from "../../components/ui/Skeleton";
import { EmptyState } from "../../components/ui/EmptyState";
import { formatInt, formatPercent } from "../../lib/format";

const PERIODOS = [7, 30, 90] as const;

/** dd/mm a partir de "2026-09-20", sem passar por Date (fuso não interessa aqui). */
function diaCurto(iso: string): string {
  const [, m, d] = iso.split("-");
  return `${d}/${m}`;
}

/**
 * Relatório de audiência e leads por fonte — critério de aceite da F5.
 *
 * "Aberturas" é abertura de ficha do lote, não visitante único: não há
 * identificação do visitante e não vamos inventar uma para engordar o número
 * que vai numa proposta comercial. A tela diz isso em vez de esconder.
 */
export default function Partners() {
  useDocumentTitle("Parcerias");
  const [days, setDays] = useState<number>(30);
  const [data, setData] = useState<PartnersReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    partnersApi
      .report(days)
      .then(setData)
      .catch((e) => setError(errorMessage(e, "Não foi possível carregar o relatório")))
      .finally(() => setLoading(false));
  }, [days]);

  useEffect(load, [load]);

  const totals = data?.totals;
  const semDado = !!data && totals?.views === 0 && totals?.clicks === 0;

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3 md:mb-6">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-bold text-gray-900 md:text-2xl">
            <Handshake size={22} className="text-primary-600" /> Parcerias
          </h1>
          <p className="mt-0.5 text-sm text-gray-500">
            Audiência e leads que o ZConnect entrega a cada leiloeiro
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex rounded-lg border border-gray-200 p-0.5">
            {PERIODOS.map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => setDays(p)}
                className={`rounded-md px-3 py-1 text-xs font-medium transition-colors ${
                  days === p ? "bg-primary-600 text-white" : "text-gray-600 hover:bg-gray-50"
                }`}
              >
                {p} dias
              </button>
            ))}
          </div>
          <Button variant="secondary" size="sm" onClick={load} disabled={loading}>
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} /> Atualizar
          </Button>
        </div>
      </div>

      {/* Totais */}
      <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-3 md:mb-6">
        {loading && !data
          ? Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-20 w-full" />)
          : [
              { label: "Aberturas de ficha", value: formatInt(totals?.views), icon: Eye, color: "text-blue-600 bg-blue-50" },
              { label: "Cliques para o leiloeiro", value: formatInt(totals?.clicks), icon: MousePointerClick, color: "text-emerald-600 bg-emerald-50" },
              {
                label: "Taxa de saída",
                value: totals?.ctr === null || totals?.ctr === undefined ? "—" : formatPercent(totals.ctr * 100),
                icon: Handshake,
                color: "text-indigo-600 bg-indigo-50",
              },
            ].map((k) => (
              <Card key={k.label}>
                <CardContent className="flex items-center gap-3 py-4">
                  <div className={`rounded-lg p-2.5 ${k.color}`}>
                    <k.icon size={20} />
                  </div>
                  <div className="min-w-0">
                    <p className="text-2xl font-bold tabular-nums text-gray-900">{k.value}</p>
                    <p className="truncate text-xs text-gray-500">{k.label}</p>
                  </div>
                </CardContent>
              </Card>
            ))}
      </div>

      <p className="mb-4 flex items-start gap-2 rounded-lg bg-blue-50 p-3 text-xs leading-relaxed text-blue-900 md:mb-6">
        <Info size={14} className="mt-0.5 shrink-0" />
        <span>
          <strong>Abertura de ficha</strong> é cada vez que alguém abriu a página de um lote daquela fonte — não é
          visitante único, porque não identificamos o visitante. <strong>Clique</strong> é a saída pelo botão “Ver no
          leilão oficial”, que é o lead entregue ao leiloeiro. A taxa é a razão entre os dois, e é o único número que o
          parceiro consegue conferir do lado dele. Acessos de robô não entram na contagem.
        </span>
      </p>

      {error ? (
        <Card>
          <CardContent>
            <EmptyState
              compact
              title="Erro ao carregar"
              description={error}
              action={
                <Button size="sm" onClick={load}>
                  Tentar novamente
                </Button>
              }
            />
          </CardContent>
        </Card>
      ) : semDado ? (
        <Card>
          <CardContent>
            <EmptyState
              compact
              icon={Eye}
              title="Nenhuma abertura no período"
              description="A medição começa a contar a partir da primeira visita à ficha de um lote. Em ambiente recém-publicado é normal levar alguns dias."
            />
          </CardContent>
        </Card>
      ) : (
        <>
          <Card className="mb-4 md:mb-6">
            <CardHeader>
              <h2 className="text-base font-semibold text-gray-900 md:text-lg">Por fonte</h2>
              <p className="text-xs text-gray-500">Ordenado por leads entregues</p>
            </CardHeader>
            <CardContent className="p-0">
              {loading && !data ? (
                <TableSkeleton rows={4} cols={6} />
              ) : (
                <Table minWidth={720}>
                  <Thead>
                    <tr>
                      <Th>Fonte</Th>
                      <Th>Lotes publicados</Th>
                      <Th>Aberturas</Th>
                      <Th>Aberturas por lote</Th>
                      <Th>Cliques</Th>
                      <Th>Taxa de saída</Th>
                    </tr>
                  </Thead>
                  <tbody>
                    {(data?.sources ?? []).map((s) => (
                      <Tr key={s.source_id}>
                        <Td className="font-medium text-gray-900">
                          <Link to={`/admin/itens?source_id=${s.source_id}`} className="hover:text-primary-600 hover:underline">
                            {s.name}
                          </Link>
                        </Td>
                        <Td className="tabular-nums">{formatInt(s.items_published)}</Td>
                        <Td className="tabular-nums">{formatInt(s.views)}</Td>
                        <Td className="tabular-nums text-gray-500">{s.views_per_item === null ? "—" : s.views_per_item.toLocaleString("pt-BR")}</Td>
                        <Td className="tabular-nums font-semibold text-gray-900">{formatInt(s.clicks)}</Td>
                        {/* Sem abertura não há taxa: "—", nunca 0%. */}
                        <Td className="tabular-nums">{s.ctr === null ? "—" : formatPercent(s.ctr * 100)}</Td>
                      </Tr>
                    ))}
                  </tbody>
                </Table>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <h2 className="text-base font-semibold text-gray-900 md:text-lg">Dia a dia</h2>
              <p className="text-xs text-gray-500">Todas as fontes somadas, desde {data ? diaCurto(data.from) : "—"}</p>
            </CardHeader>
            <CardContent>
              {loading && !data ? (
                <Skeleton className="h-64 w-full" />
              ) : (data?.daily?.length ?? 0) === 0 ? (
                <EmptyState compact title="Sem histórico ainda" description="O gráfico aparece a partir do primeiro dia com audiência." />
              ) : (
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={(data?.daily ?? []).map((d) => ({ ...d, dia: diaCurto(d.day) }))} margin={{ top: 5, right: 8, bottom: 0, left: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                      <XAxis dataKey="dia" tick={{ fontSize: 11 }} />
                      <YAxis tick={{ fontSize: 11 }} allowDecimals={false} width={40} />
                      <Tooltip
                        formatter={(v: number, n: string) => [formatInt(v), n === "views" ? "Aberturas" : "Cliques"]}
                        labelFormatter={(l) => `Dia ${l}`}
                      />
                      <Legend formatter={(v) => (v === "views" ? "Aberturas" : "Cliques")} />
                      <Line type="monotone" dataKey="views" stroke="#2563eb" strokeWidth={2} dot={false} />
                      <Line type="monotone" dataKey="clicks" stroke="#059669" strokeWidth={2} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
