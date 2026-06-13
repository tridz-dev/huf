import { db, call, file } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import type { SkillDoc, SkillOption } from '@/types/skill.types';
import { handleFrappeError } from '@/lib/frappe-error';
import { fetchPaginatedCount } from './utilsApi';

export interface SkillDestination {
  name: string;
  repo_url: string;
  path?: string;
  ref?: string;
}

export interface SkillRegistrySkill {
  name: string;
  title: string;
  description?: string;
  path?: string;
  author?: string;
  version?: string;
  category?: string;
}

export interface SkillRegistry {
  name?: string;
  description?: string;
  source_url?: string;
  ref?: string;
  skills_path?: string;
  skills?: SkillRegistrySkill[];
}

const SKILL_LIST_FIELDS = [
  'name',
  'skill_name',
  'title',
  'description',
  'source_type',
  'status',
  'skill_category',
  'version',
  'author',
  'modified',
];

export interface GetSkillsParams {
  page?: number;
  limit?: number;
  start?: number;
  search?: string;
  status?: string;
  source_type?: string;
}

export interface PaginatedSkillsResponse {
  items: SkillDoc[];
  hasMore: boolean;
  total?: number;
}

export async function getSkills(params?: GetSkillsParams): Promise<PaginatedSkillsResponse> {
  try {
    const {
      page = 1,
      limit = 20,
      start = (page - 1) * limit,
      search,
      status,
      source_type,
    } = params || {};

    const filters: Array<[string, string, unknown]> = [];

    if (status && status !== 'all') {
      filters.push(['status', '=', status]);
    }
    if (source_type && source_type !== 'all') {
      filters.push(['source_type', '=', source_type]);
    }
    if (search && search.trim()) {
      filters.push(['title', 'like', `%${search.trim()}%`]);
    }

    const skills = await db.getDocList(doctype.Skill, {
      fields: SKILL_LIST_FIELDS,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      filters: filters.length > 0 ? (filters as any) : undefined,
      limit: limit + 1,
      ...(start > 0 && { limit_start: start }),
      orderBy: { field: 'modified', order: 'desc' },
    });

    const mapped = skills as SkillDoc[];
    const hasMore = mapped.length > limit;
    const items = hasMore ? mapped.slice(0, limit) : mapped;

    const total = await fetchPaginatedCount(page, items.length, doctype.Skill, filters);

    return { items, hasMore, total };
  } catch (error) {
    handleFrappeError(error, 'Error fetching skills');
  }
}

export async function getSkill(name: string): Promise<SkillDoc> {
  try {
    const doc = await db.getDoc(doctype.Skill, name);
    return doc as SkillDoc;
  } catch (error) {
    handleFrappeError(error, `Error fetching skill ${name}`);
  }
}

export async function createSkill(data: Partial<SkillDoc>): Promise<SkillDoc> {
  try {
    const doc = await db.createDoc(doctype.Skill, data);
    return doc as SkillDoc;
  } catch (error) {
    handleFrappeError(error, 'Error creating skill');
  }
}

export async function updateSkill(name: string, data: Partial<SkillDoc>): Promise<SkillDoc> {
  try {
    await db.updateDoc(doctype.Skill, name, data);
    const updated = await db.getDoc(doctype.Skill, name);
    return updated as SkillDoc;
  } catch (error) {
    handleFrappeError(error, `Error updating skill ${name}`);
  }
}

export async function deleteSkill(name: string): Promise<void> {
  try {
    await db.deleteDoc(doctype.Skill, name);
  } catch (error) {
    handleFrappeError(error, `Error deleting skill ${name}`);
  }
}

export async function importSkillFromGit(
  repo_url: string,
  path = 'skills',
  ref = 'main'
): Promise<{ success: boolean; message?: string; skills?: string[] }> {
  try {
    const result = await call.post('huf.ai.skills.api.import_skill_from_git', {
      repo_url,
      path,
      ref,
    });
    const message = (result as { message?: unknown }).message ?? result;
    return (Array.isArray(message) ? { success: true, skills: message } : message) as {
      success: boolean;
      message?: string;
      skills?: string[];
    };
  } catch (error) {
    handleFrappeError(error, 'Error importing skill from Git');
  }
}

export async function importSkillFromCommonDestination(
  destination_name: string
): Promise<{ success: boolean; message?: string; skills?: string[] }> {
  try {
    const result = await call.post('huf.ai.skills.api.import_skill_from_common_destination', {
      destination_name,
    });
    const message = (result as { message?: unknown }).message ?? result;
    return message as { success: boolean; message?: string; skills?: string[] };
  } catch (error) {
    handleFrappeError(error, 'Error importing skill from common destination');
  }
}

export async function syncAppSkills(): Promise<{ success: boolean; message?: string; skills?: string[] }> {
  try {
    const result = await call.post('huf.ai.skills.api.sync_app_skills', {});
    const message = (result as { message?: unknown }).message ?? result;
    return message as { success: boolean; message?: string; skills?: string[] };
  } catch (error) {
    handleFrappeError(error, 'Error syncing app skills');
  }
}

export async function getSkillOptions(): Promise<SkillOption[]> {
  try {
    const result = await call.get('huf.ai.skills.api.get_skill_options');
    const message = (result as { message?: unknown }).message ?? result;
    return (Array.isArray(message) ? message : []) as SkillOption[];
  } catch (error) {
    handleFrappeError(error, 'Error fetching skill options');
  }
}

export async function getSkillDestinations(): Promise<SkillDestination[]> {
  try {
    const result = await call.get('huf.ai.skills.api.get_skill_destinations');
    const message = (result as { message?: unknown }).message ?? result;
    return (Array.isArray(message) ? message : []) as SkillDestination[];
  } catch (error) {
    handleFrappeError(error, 'Error fetching skill destinations');
  }
}

export function exportSkillAsHuf(skill_name: string): void {
  const url = `/api/method/huf.ai.skills.api.download_skill_huf?skill_name=${encodeURIComponent(skill_name)}`;
  const a = document.createElement('a');
  a.href = url;
  a.download = `${skill_name}.huf`;
  document.body.appendChild(a);
  a.click();
  a.remove();
}

export async function importSkillFromHuf(
  fileToUpload: File
): Promise<{ skill?: string; warnings?: string[]; success?: boolean; message?: string }> {
  try {
    const uploadResponse = await file.uploadFile(fileToUpload, { isPrivate: false });
    const uploadData = (uploadResponse as { data?: { message?: { file_url?: string }; file_url?: string } }).data;
    const file_url = uploadData?.message?.file_url || uploadData?.file_url;
    if (!file_url) {
      throw new Error('File upload did not return a file URL');
    }
    const result = await call.post('huf.ai.skills.api.import_skill_from_huf', { file_url });
    const message = (result as { message?: unknown }).message ?? result;
    return (message as { skill?: string; warnings?: string[]; success?: boolean; message?: string }) || { success: true };
  } catch (error) {
    handleFrappeError(error, 'Error importing skill from .huf');
  }
}

export async function fetchSkillRegistry(
  repo_url: string,
  ref = 'main',
  path = '_index.json'
): Promise<SkillRegistry> {
  try {
    const result = await call.get('huf.ai.skills.api.fetch_skill_registry', {
      repo_url,
      ref,
      path,
    });
    const message = (result as { message?: unknown }).message ?? result;
    return (message as SkillRegistry) || {};
  } catch (error) {
    handleFrappeError(error, 'Error fetching skill registry');
  }
}

export async function importSkillFromRegistry(
  repo_url: string,
  skill_name: string,
  path = 'skills',
  ref = 'main'
): Promise<{ success: boolean; message?: string; skills?: string[] }> {
  try {
    const result = await call.post('huf.ai.skills.api.import_skill_from_registry', {
      repo_url,
      skill_name,
      path,
      ref,
    });
    const message = (result as { message?: unknown }).message ?? result;
    return message as { success: boolean; message?: string; skills?: string[] };
  } catch (error) {
    handleFrappeError(error, 'Error importing skill from registry');
  }
}
