import ItemsTable from "./ItemsTable";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";

export default function Review() {
  useDocumentTitle("Revisão");
  return (
    <ItemsTable
      presetExtraction="review"
      showExtractionError
      title="Fila de revisão"
      subtitle="Itens cuja extração falhou após as tentativas configuradas (RN-003). Corrija a ficha e salve para publicar."
    />
  );
}
