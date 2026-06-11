import { db } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';
import { doctype } from '@/data/doctypes';

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
  params?: GetCategoriesParams
): Promise<CategoryDoc[]> {
  try {
    const filters: Array<[string, string, unknown]> = [];

    if (params?.search && params.search.trim()) {
      filters.push(['category_name', 'like', `%${params.search.trim()}%`]);
    }

    if (params?.parent_category) {
      filters.push(['parent_category', '=', params.parent_category]);
    }

    const response = await db.getDocList(doctype['Agent Prompt Category'], {
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

export async function getCategory(name: string): Promise<CategoryDoc> {
  try {
    const response = await db.getDoc(doctype['Agent Prompt Category'], name);
    return response as CategoryDoc;
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

export async function createCategory(
  data: Partial<CategoryDoc>
): Promise<CategoryDoc> {
  try {
    const response = await db.createDoc(
      doctype['Agent Prompt Category'],
      data
    );
    return response as CategoryDoc;
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

export async function updateCategory(
  name: string,
  data: Partial<CategoryDoc>
): Promise<CategoryDoc> {
  try {
    let targetName = name;

    if (
      data.category_name &&
      data.category_name.trim().length > 0 &&
      data.category_name !== name
    ) {
      try {
        await db.renameDoc(
          doctype['Agent Prompt Category'],
          name,
          data.category_name
        );
        targetName = data.category_name;
      } catch (error: any) {
        console.warn('rename_doc failed, falling back to updateDoc', error);
        // Some doctype configs may still not allow rename; continue with current name
        targetName = name;
      }
    }

    const response = await db.updateDoc(
      doctype['Agent Prompt Category'],
      targetName,
      data
    );
    return response as CategoryDoc;
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

export async function deleteCategory(name: string): Promise<void> {
  try {
    await db.deleteDoc(doctype['Agent Prompt Category'], name);
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}