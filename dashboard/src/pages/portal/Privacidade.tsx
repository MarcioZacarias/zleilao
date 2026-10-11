import { Link } from "react-router-dom";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import { useBranding } from "../../hooks/useBranding";

/**
 * Política de privacidade.
 *
 * Existe por duas razões, nessa ordem: a LGPD obriga quem trata dado pessoal
 * a dizer o que faz com ele, e o Google exige a página para aprovar o AdSense.
 *
 * O texto é um ponto de partida honesto sobre o que o sistema realmente faz —
 * não um modelo genérico. Ainda assim, **não substitui revisão jurídica**, e a
 * seção de publicidade precisa ser conferida quando o AdSense for ligado de
 * fato, porque ela descreve um tratamento que hoje ainda não acontece.
 */
export default function Privacidade() {
  useDocumentTitle("Política de privacidade");
  const branding = useBranding();
  const site = branding.site_title || "ZConnect Leilão";

  return (
    <div className="mx-auto max-w-3xl px-4 py-8 sm:px-6">
      <h1 className="text-2xl font-bold text-radar-text md:text-3xl">Política de privacidade</h1>
      <p className="mt-2 text-sm text-radar-muted">Última atualização: 11 de outubro de 2026</p>

      <div className="prose-zleilao mt-8 space-y-6 text-sm leading-relaxed text-radar-text/90">
        <Secao titulo="Quem somos e o que fazemos">
          <p>
            O {site} é um <strong>agregador de leilões</strong>: reunimos num só lugar lotes
            publicados nos sites de leiloeiros oficiais, com link para a fonte. Não realizamos
            leilões, não recebemos lances, não intermediamos pagamentos e não temos posse dos bens.
          </p>
        </Secao>

        <Secao titulo="Quais dados tratamos">
          <p>Só coletamos o que o serviço precisa para funcionar:</p>
          <ul className="ml-5 list-disc space-y-1">
            <li>
              <strong>E-mail e senha</strong>, se você criar conta para receber alertas. A senha é
              guardada como hash — não temos como lê-la.
            </li>
            <li>
              <strong>Telefone</strong>, apenas se você optar por receber alertas por WhatsApp.
            </li>
            <li>
              <strong>Seus filtros salvos</strong> (marca, faixa de preço, cidade de referência),
              porque sem eles não há como saber o que te avisar.
            </li>
            <li>
              <strong>Dados de navegação</strong>: quais lotes foram abertos e quais cliques
              seguiram para o site do leiloeiro. Usamos de forma agregada, para medir quais fontes
              interessam ao público — não montamos perfil individual.
            </li>
          </ul>
          <p>
            <strong>Não coletamos</strong> documentos, dados bancários ou de cartão. Nunca pedimos
            isso, e o pagamento de um lote acontece sempre no site do leiloeiro.
          </p>
        </Secao>

        <Secao titulo="Dados de terceiros que exibimos">
          <p>
            As informações dos lotes vêm de páginas públicas dos leiloeiros. Placas de veículos
            aparecem <strong>mascaradas</strong>, e não publicamos nome, CPF ou endereço de
            proprietários. Se um dado pessoal seu apareceu aqui por vir da fonte, escreva para nós
            que removemos.
          </p>
        </Secao>

        <Secao titulo="Cookies e publicidade">
          <p>
            Usamos armazenamento local do navegador para manter você conectado e lembrar
            preferências de busca. Isso não é compartilhado com ninguém.
          </p>
          <p>
            O site pode exibir <strong>publicidade</strong>, sempre identificada com a etiqueta
            “Publicidade”. Quando a publicidade vem do Google AdSense, o Google e seus parceiros
            podem usar cookies para exibir anúncios com base em visitas anteriores suas a este e a
            outros sites. Você pode desativar a publicidade personalizada nas{" "}
            <a
              href="https://www.google.com/settings/ads"
              target="_blank"
              rel="noopener noreferrer"
              className="text-accent hover:underline"
            >
              configurações de anúncios do Google
            </a>{" "}
            ou em{" "}
            <a
              href="https://www.aboutads.info"
              target="_blank"
              rel="noopener noreferrer"
              className="text-accent hover:underline"
            >
              aboutads.info
            </a>
            .
          </p>
        </Secao>

        <Secao titulo="Com quem compartilhamos">
          <p>
            Com ninguém, para fins comerciais. Seus dados não são vendidos nem cedidos. Usamos
            serviços de infraestrutura (hospedagem e envio de e-mail) que tratam dados apenas para
            entregar o serviço, sob nossa instrução.
          </p>
        </Secao>

        <Secao titulo="Seus direitos (LGPD)">
          <p>
            Você pode a qualquer momento pedir acesso, correção ou exclusão dos seus dados, retirar
            consentimento e cancelar alertas. Na sua conta é possível apagar filtros e encerrar o
            cadastro. Para o restante, fale com a gente pelo contato abaixo — respondemos em até 15
            dias.
          </p>
        </Secao>

        <Secao titulo="Por quanto tempo guardamos">
          <p>
            Dados de conta enquanto ela existir. Encerrada a conta, apagamos os dados pessoais e
            mantemos apenas contagens agregadas, que não identificam ninguém.
          </p>
        </Secao>

        <Secao titulo="Contato">
          <p>
            Dúvidas sobre esta política ou pedidos relativos aos seus dados:{" "}
            <a href="mailto:contato@zconnect.ia.br" className="text-accent hover:underline">
              contato@zconnect.ia.br
            </a>
            .
          </p>
        </Secao>
      </div>

      <div className="mt-10 border-t border-radar-border pt-6 text-sm">
        <Link to="/termos" className="text-accent hover:underline">
          Termos de uso
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
