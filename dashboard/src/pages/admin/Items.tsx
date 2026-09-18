import ItemsTable from "./ItemsTable";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";

export default function Items() {
  useDocumentTitle("Itens");
  return <ItemsTable title="Itens" subtitle="Todos os lotes coletados — clique em uma linha para editar" />;
}
