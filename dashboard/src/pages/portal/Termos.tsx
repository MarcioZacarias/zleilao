import { Link } from "react-router-dom";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import { useBranding } from "../../hooks/useBranding";

/**
 * Termos de uso.
 *
 * O ponto que o texto precisa deixar sem ambiguidade é o limite do serviço:
 * quem arremata, paga e assume o bem lida com o leiloeiro, não conosco. Um
 * agregador que deixa isso vago convida reclamação que não tem como resolver.
 *
 * Texto de partida, não substitui revisão jurídica.
 */
export default function Termos() {
  useDocumentTitle("Termos de uso");
  const branding = useBranding();
  const site = branding.site_title || "ZConnect Leilão";

  return (
    <div className="mx-auto max-w-3xl px-4 py-8 sm:px-6">
      <h1 className="text-2xl font-bold text-radar-text md:text-3xl">Termos de uso</h1>
      <p className="mt-2 text-sm text-radar-muted">Última atualização: 11 de outubro de 2026</p>

      <div className="mt-8 space-y-6 text-sm leading-relaxed text-radar-text/90">
        <Secao titulo="O que este serviço é — e o que não é">
          <p>
            O {site} reúne, num só lugar, lotes publicados nos sites de leiloeiros oficiais, com
            link para a fonte de cada um.
          </p>
          <p className="rounded-lg bg-white/[0.04] p-3">
            <strong>Não somos leiloeiros.</strong> Não realizamos leilões, não recebemos lances,
            não intermediamos pagamento, não guardamos nem entregamos bens, e não participamos de
            nenhuma etapa da negociação. Toda disputa, pagamento e retirada acontecem entre você e
            o leiloeiro responsável, pelas regras do edital dele.
          </p>
        </Secao>

        <Secao titulo="Sobre as informações exibidas">
          <p>
            Os dados são coletados automaticamente das páginas públicas dos leiloeiros e podem
            estar <strong>desatualizados</strong>: preço, data de pregão e disponibilidade mudam na
            fonte sem aviso. Por isso toda ficha mostra a data da última coleta e o link oficial.
          </p>
          <p>
            <strong>Confira sempre na fonte antes de dar lance.</strong> O edital do leiloeiro é o
            documento que vale; o que está aqui é um índice para você chegar até ele.
          </p>
        </Secao>

        <Secao titulo="Sobre a comparação de preço">
          <p>
            Quando exibimos comparação com a tabela FIPE e desconto estimado, trata-se de{" "}
            <strong>estimativa</strong>, calculada sobre o lance inicial somado a comissão e
            despesas informadas. O lance inicial é o piso do pregão: o valor de arremate costuma ser
            maior. O estado real do bem, débitos, restrições e custos de regularização não entram na
            conta e podem mudar tudo. Não é recomendação de compra nem avaliação técnica.
          </p>
        </Secao>

        <Secao titulo="Uso da conta">
          <p>
            A conta serve para salvar filtros e receber alertas. Você é responsável por manter a
            senha em sigilo. Pedimos que não use o serviço para coleta automatizada em massa, nem
            para qualquer finalidade ilícita.
          </p>
        </Secao>

        <Secao titulo="Publicidade">
          <p>
            O site pode exibir anúncios, sempre identificados com a etiqueta “Publicidade”.
            Anunciante não influencia a ordem dos lotes na busca nem os cálculos de comparação.
            Publicidade é publicidade; resultado de busca é resultado de busca.
          </p>
        </Secao>

        <Secao titulo="Limitação de responsabilidade">
          <p>
            Fazemos o possível para que as informações estejam corretas e atualizadas, mas não
            garantimos exatidão, disponibilidade contínua nem adequação a qualquer finalidade
            específica. Não respondemos por prejuízo decorrente de decisão tomada com base no que
            foi exibido aqui — a fonte oficial é o leiloeiro.
          </p>
        </Secao>

        <Secao titulo="Direitos de terceiros">
          <p>
            Marcas, imagens e descrições pertencem aos seus titulares. Se você é leiloeiro e quer
            que sua fonte deixe de ser indexada, basta pedir: retiramos.
          </p>
        </Secao>

        <Secao titulo="Mudanças e contato">
          <p>
            Estes termos podem mudar; a data no topo indica a última revisão. Dúvidas:{" "}
            <a href="mailto:contato@zconnect.ia.br" className="text-accent hover:underline">
              contato@zconnect.ia.br
            </a>
            .
          </p>
        </Secao>
      </div>

      <div className="mt-10 border-t border-radar-border pt-6 text-sm">
        <Link to="/privacidade" className="text-accent hover:underline">
          Política de privacidade
        </Link>
        <span className="mx-2 text-radar-muted">·</span>
        <Link to="/" className="text-accent hover:underline">
          Voltar para a vitrine
        </Link>
      </div>
    </div>
  );
}

function Secao({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="mb-2 text-base font-semibold text-radar-text">{titulo}</h2>
      <div className="space-y-2">{children}</div>
    </section>
  );
}
