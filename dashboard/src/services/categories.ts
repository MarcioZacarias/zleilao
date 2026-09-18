import api from "./api";
import type { Category, CategoryField, CategoryFieldInput, CategoryInput } from "./types";

export const categoriesApi = {
  tree: () => api.get<Category[]>("/categories").then((r) => r.data),
  create: (body: CategoryInput) => api.post<Category>("/categories", body).then((r) => r.data),
  update: (id: number, body: Partial<CategoryInput>) =>
    api.put<Category>(`/categories/${id}`, body).then((r) => r.data),
  remove: (id: number) => api.delete(`/categories/${id}`).then((r) => r.data),
  fields: (categoryId: number) =>
    api.get<CategoryField[]>(`/categories/${categoryId}/fields`).then((r) => r.data),
  createField: (categoryId: number, body: CategoryFieldInput) =>
    api.post<CategoryField>(`/categories/${categoryId}/fields`, body).then((r) => r.data),
  updateField: (fieldId: number, body: Partial<CategoryFieldInput>) =>
    api.put<CategoryField>(`/categories/fields/${fieldId}`, body).then((r) => r.data),
  removeField: (fieldId: number) => api.delete(`/categories/fields/${fieldId}`).then((r) => r.data),
};

/** Achata a árvore em lista com profundidade (para selects e listagens). */
export function flattenCategories(
  tree: Category[],
  depth = 0
): { category: Category; depth: number }[] {
  const out: { category: Category; depth: number }[] = [];
  for (const c of tree) {
    out.push({ category: c, depth });
    if (c.children?.length) out.push(...flattenCategories(c.children, depth + 1));
  }
  return out;
}

export function findCategory(tree: Category[], id: number): Category | null {
  for (const c of tree) {
    if (c.id === id) return c;
    const found = c.children?.length ? findCategory(c.children, id) : null;
    if (found) return found;
  }
  return null;
}
