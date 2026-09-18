import { ReactNode, MouseEventHandler, ThHTMLAttributes, TdHTMLAttributes } from "react";

interface TableProps {
  children: ReactNode;
  minWidth?: number;
}

export function Table({ children, minWidth = 600 }: TableProps) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm" style={{ minWidth }}>
        {children}
      </table>
    </div>
  );
}

export function Thead({ children }: { children: ReactNode }) {
  return <thead className="bg-gray-50 border-b border-gray-200">{children}</thead>;
}

// Th/Td repassam os atributos nativos da celula (title, colSpan, scope...).
// Sem isso, `title` para texto truncado vira erro de tipo em cada chamada.
export function Th({ children, className = "", ...rest }: ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      {...rest}
      className={`px-3 md:px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap ${className}`}
    >
      {children}
    </th>
  );
}

export function Td({ children, className = "", ...rest }: TdHTMLAttributes<HTMLTableCellElement>) {
  return (
    <td {...rest} className={`px-3 md:px-4 py-3 text-gray-700 align-middle ${className}`}>
      {children}
    </td>
  );
}

export function Tr({
  children,
  className = "",
  onClick,
}: {
  children: ReactNode;
  className?: string;
  onClick?: MouseEventHandler<HTMLTableRowElement>;
}) {
  return (
    <tr
      onClick={onClick}
      className={`border-b border-gray-100 hover:bg-gray-50 transition-colors ${
        onClick ? "cursor-pointer" : ""
      } ${className}`}
    >
      {children}
    </tr>
  );
}
