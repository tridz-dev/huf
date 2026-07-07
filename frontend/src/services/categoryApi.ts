import { db } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';
import { doctype } from '@/data/doctypes';

type CategoryDoctype =
  | typeof doctype['Agent Prompt Category']
  | typeof doctype['Agent Summary Prompt Category'];

function resolveCategoryDoctype(kind: 'prompt' | 'summary'): CategoryDoctype {
  return kind === 'summary'
    ? doctype['Agent Summary Prompt Category']
    : doctype['Agent Prompt Category'];
}

export interface CategoryDoc {
  name: string;
  category_name: string;
  description?: string;
  icon?: string;
  color?: string;
  parent_category?: string;
  modified?: string;
}

export interface GetCategoriesParams {
  search?: string;
  parent_category?: string;
  [key: string]: unknown;
}

export async function getCategories(
  params?: GetCategoriesParams,
  kind: 'prompt' | 'summary' = 'prompt',
): Promise<CategoryDoc[]> {
  try {
    const categoryDoctype = resolveCategoryDoctype(kind);
    const filters: Array<[string, string, unknown]> = [];

    if (params?.search && params.search.trim()) {
      filters.push(['category_name', 'like', `%${params.search.trim()}%`]);
    }

    if (params?.parent_category) {
      filters.push(['parent_category', '=', params.parent_category]);
    }

    const response = await db.getDocList(categoryDoctype, {
      fields: [
        'name',
        'category_name',
        'description',
        'icon',
        'color',
        'parent_category',
        'modified',
      ],
      filters: filters.length > 0 ? (filters as any) : undefined,
      limit: 1000,
      orderBy: { field: 'modified', order: 'desc' },
    });

    return response as CategoryDoc[];
  } catch (error) {
    handleFrappeError(error, 'Error fetching categories');
    throw error;
  }
}

export async function getCategory(
  name: string,
  kind: 'prompt' | 'summary' = 'prompt',
): Promise<CategoryDoc> {
  try {
    const response = await db.getDoc(resolveCategoryDoctype(kind), name);
    return response as CategoryDoc;
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

export async function createCategory(
  data: Partial<CategoryDoc>,
  kind: 'prompt' | 'summary' = 'prompt',
): Promise<CategoryDoc> {
  try {
    const response = await db.createDoc(resolveCategoryDoctype(kind), data);
    return response as CategoryDoc;
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

export async function updateCategory(
  name: string,
  data: Partial<CategoryDoc>,
  kind: 'prompt' | 'summary' = 'prompt',
): Promise<CategoryDoc> {
  try {
    let targetName = name;
    const categoryDoctype = resolveCategoryDoctype(kind);

    if (
      data.category_name &&
      data.category_name.trim().length > 0 &&
      data.category_name !== name
    ) {
      try {
        await db.renameDoc(categoryDoctype, name, data.category_name);
        targetName = data.category_name;
      } catch (error: unknown) {
        console.warn('rename_doc failed, falling back to updateDoc', error);
        targetName = name;
      }
    }

    const response = await db.updateDoc(categoryDoctype, targetName, data);
    return response as CategoryDoc;
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

export async function deleteCategory(
  name: string,
  kind: 'prompt' | 'summary' = 'prompt',
): Promise<void> {
  try {
    await db.deleteDoc(resolveCategoryDoctype(kind), name);
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

export const getSummaryPromptCategories = (params?: GetCategoriesParams) =>
  getCategories(params, 'summary');