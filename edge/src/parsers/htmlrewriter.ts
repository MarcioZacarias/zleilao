/**
 * Coleta de campos com HTMLRewriter.
 *
 * O parser em Python navegava uma árvore: pegava o card e descia nele com
 * `select_one`. Aqui não existe árvore — o HTMLRewriter entrega os elementos
 * em fluxo, na ordem do documento, e quem reconstrói o agrupamento somos nós.
 *
 * O preço disso é uma máquina de estado; o ganho é que o parsing roda em Rust
 * dentro do runtime, fora do orçamento de 10 ms de CPU do Worker — que é a
 * única razão pela qual este produto cabe no plano gratuito.
 */

/** Um registro em construção: cada seletor deposita seu pedaço aqui. */
export type Registro = Record<string, string | undefined>;

export interface CampoSpec {
  /** Seletor CSS relativo ao item (concatenado ao seletor raiz). */
  sel: string;
  /** Nome do campo no registro. */
  campo: string;
  /** `text` pega o conteúdo textual; senão, lê este atributo. */
  attr?: string;
}

export interface ListaSpec {
  /** Seletor do elemento que delimita cada item. */
  raiz: string;
  /** Atributo do elemento raiz a guardar (ex.: `data-key`). */
  raizAttr?: string;
  campos: CampoSpec[];
  /** Sub-listas repetidas dentro do item (ex.: as praças de um lote). */
  grupos?: { sel: string; nome: string; campos: CampoSpec[] }[];
}

export interface ItemColetado {
  raiz?: string;
  campos: Registro;
  grupos: Record<string, Registro[]>;
}

/**
 * Agrupa os campos por seletor.
 *
 * Cada `rw.on` instala um matcher que roda contra toda tag do documento, então
 * dois campos no mesmo seletor custam o dobro do necessário. Em `.card-title`
 * queremos o texto e o href: é um matcher, não dois.
 */
function porSeletor(campos: CampoSpec[]): Map<string, CampoSpec[]> {
  const m = new Map<string, CampoSpec[]>();
  for (const c of campos) {
    const lista = m.get(c.sel);
    if (lista) lista.push(c);
    else m.set(c.sel, [c]);
  }
  return m;
}

/**
 * Roda a especificação sobre o HTML e devolve um registro por item.
 *
 * Só a primeira ocorrência de cada campo dentro do item é guardada, que é o
 * comportamento do `select_one` que os parsers em Python usam.
 */
export async function extrairLista(html: string, spec: ListaSpec): Promise<ItemColetado[]> {
  const itens: ItemColetado[] = [];
  let atual: ItemColetado | null = null;
  let grupoAtual: Registro | null = null;

  const rw = new HTMLRewriter();

  rw.on(spec.raiz, {
    element(el) {
      const meu: ItemColetado = {
        raiz: spec.raizAttr ? el.getAttribute(spec.raizAttr) ?? undefined : undefined,
        campos: {},
        grupos: {},
      };
      atual = meu;
      el.onEndTag(() => {
        if (meu.raiz || Object.keys(meu.campos).length) itens.push(meu);
        if (atual === meu) atual = null;
      });
    },
  });

  for (const g of spec.grupos ?? []) {
    rw.on(`${spec.raiz} ${g.sel}`, {
      element(el) {
        if (!atual) return;
        const reg: Registro = {};
        grupoAtual = reg;
        const dono = atual;
        el.onEndTag(() => {
          if (Object.keys(reg).length) (dono.grupos[g.nome] ||= []).push(reg);
          if (grupoAtual === reg) grupoAtual = null;
        });
      },
    });

    for (const [sel, lista] of porSeletor(g.campos)) {
      const textuais = lista.filter((c) => !c.attr);
      const atributos = lista.filter((c) => c.attr);
      let buf = "";
      rw.on(`${spec.raiz} ${g.sel} ${sel}`, {
        element(el) {
          if (!grupoAtual) return;
          buf = "";
          for (const c of atributos) {
            const v = el.getAttribute(c.attr!);
            if (v != null && grupoAtual[c.campo] === undefined) grupoAtual[c.campo] = v;
          }
        },
        text(t) {
          if (!grupoAtual || !textuais.length) return;
          buf += t.text;
          if (!t.lastInTextNode) return;
          const v = buf.replace(/\s+/g, " ").trim();
          buf = "";
          if (!v) return;
          for (const c of textuais) if (!grupoAtual[c.campo]) grupoAtual[c.campo] = v;
        },
      });
    }
  }

  for (const [sel, lista] of porSeletor(spec.campos)) {
    const textuais = lista.filter((c) => !c.attr);
    const atributos = lista.filter((c) => c.attr);
    let buf = "";
    rw.on(`${spec.raiz} ${sel}`, {
      element(el) {
        if (!atual) return;
        buf = "";
        for (const c of atributos) {
          const v = el.getAttribute(c.attr!);
          if (v != null && atual.campos[c.campo] === undefined) atual.campos[c.campo] = v;
        }
      },
      text(t) {
        if (!atual || !textuais.length) return;
        buf += t.text;
        if (!t.lastInTextNode) return;
        const v = buf.replace(/\s+/g, " ").trim();
        buf = "";
        if (!v) return;
        for (const c of textuais) if (!atual.campos[c.campo]) atual.campos[c.campo] = v;
      },
    });
  }

  // `transform` é preguiçoso: o parsing só acontece ao consumir o corpo.
  // Medido: `arrayBuffer()` é ~2,5x mais rápido que drenar num WritableStream,
  // porque o ralo em JS força uma ida ao JS por chunk do corpo. A saída
  // reescrita é descartada; o que interessa já ficou nos handlers.
  await rw.transform(new Response(html)).arrayBuffer();
  return itens;
}
