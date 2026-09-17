import { apiFetch } from '../../pluginHost/api';

// The host mounts this plugin's backend under /plugins/<plugin-id>/.
const BASE = '/plugins/entities/entities';

export interface Entity {
  name: string;
  section: 'customer' | 'partner';
  aliases: string;
  affiliate_of: string;
  created: boolean;
  ignore: boolean;
  domain: string;
}

export interface EntityPatch {
  name?: string;
  section?: string;
  aliases?: string;
  affiliate_of?: string;
  domain?: string;
  ignore?: boolean;
}

export interface NewEntity {
  name: string;
  section: 'customer' | 'partner';
  domain?: string;
  aliases?: string;
  affiliate_of?: string;
}

export function fetchEntities(): Promise<{ entities: Entity[] }> {
  return apiFetch(BASE);
}

export function updateEntity(name: string, patch: EntityPatch): Promise<Entity> {
  return apiFetch<Entity>(`${BASE}/${encodeURIComponent(name)}`, { method: 'PATCH', body: JSON.stringify(patch) });
}

export function deleteEntity(name: string): Promise<{ deleted: boolean }> {
  return apiFetch(`${BASE}/${encodeURIComponent(name)}`, { method: 'DELETE' });
}

export function createEntity(fields: NewEntity): Promise<Entity> {
  return apiFetch<Entity>(BASE, { method: 'POST', body: JSON.stringify(fields) });
}
