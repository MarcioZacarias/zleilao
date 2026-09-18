import { Link } from "react-router-dom";
import { Compass } from "lucide-react";
import { EmptyState } from "../../components/ui/EmptyState";
import { Button } from "../../components/ui/Button";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";

export default function NotFound() {
  useDocumentTitle("Página não encontrada");
  return (
    <div className="mx-auto max-w-3xl px-4 py-20 sm:px-6">
      <div className="portal-card">
        <EmptyState
          tone="dark"
          icon={Compass}
          title="Página não encontrada"
          description="O endereço pode estar errado ou a página foi movida."
          action={
            <Link to="/">
              <Button variant="accent" size="sm">Voltar ao início</Button>
            </Link>
          }
        />
      </div>
    </div>
  );
}
