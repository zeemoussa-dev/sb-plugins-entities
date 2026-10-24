import { apiFetch } from '../../pluginHost/api';

const BASE = '/plugins/entities/accounts';

export type AccountKind = 'customer' | 'partner';

export interface AccountRow {
  kind: AccountKind;
  name: string;
  stem: string;
  tag: string;
  parent: string | null;
  domain: string;
  description: string;
  affiliates: number;
  opportunities: number;
  people: number;
  has_commitment: boolean;
}

export interface AccountList {
  customers: AccountRow[];
  partners: AccountRow[];
}

export interface Commitment {
  type: string;
  amount: number | null;
  currency: string;
  start: string;
  end: string;
  note: string;
  include_marketplace: boolean;
  subtract_credits: boolean;
  /** A parent's affiliates: their consumption burns this commitment, or each signed its own. */
  affiliates?: 'roll up' | 'own';
}

export interface Opportunity {
  id: string;
  title: string;
  stem: string;
  customer: string;
  affiliate: string | null;
  status: string;
  stage: string;
  product: string[];
  route: string;
  partner: string[];
  expected_monthly_usd: number | null;
  consumption_start: string;
  updated: string;
}

export interface Person {
  stem: string;
  name: string;
  email: string;
  role: string;
  department: string;
}

export interface ActivityItem {
  kind: 'meeting' | 'thread';
  stem: string;
  title: string;
  date: string;
}

/** The hub's Captures note: the whole body, and the stem the vault editor opens. */
export interface Captures {
  exists: boolean;
  stem: string;
  body: string;
}

/** Azure Cost Manager's portfolio row for a linked customer (its service, not this plugin's). */
export interface CostRow {
  id: string;
  name: string;
  currency: string | null;
  signed: number | null;
  enrollments: number;
  burn: {
    consumed: number;
    remaining: number;
    consumed_pct: number;
    elapsed_pct: number;
    projected_at_end: number | null;
    projected_shortfall: number | null;
    end: string;
  } | null;
  last_month: { month: string; actual: number; mom_pct?: number | null } | null;
  recent: { month: string; actual: number }[];
  status: string;
  synced_at: string | null;
  stale: boolean;
  route?: string;
}

export interface Account {
  kind: AccountKind;
  name: string;
  stem: string;
  tag: string;
  domain: string;
  description: string;
  aliases: string[];
  tags: string[];
  lineage: { name: string; stem: string }[];
  affiliates: { name: string; stem: string }[];
  commitment: Commitment | null;
  intro: string;
  sections: { name: string; text: string }[];
  personal_notes: string;
  captures: Captures;
  news: string | null;
  opportunities: Opportunity[];
  people: Person[];
  activity: ActivityItem[];
}

export interface AccountCost {
  available: boolean;
  row: CostRow | null;
  error?: string;
}

function path(kind: AccountKind, stem: string): string {
  return `${BASE}/${kind}/${encodeURIComponent(stem)}`;
}

export function fetchAccounts(): Promise<AccountList> {
  return apiFetch(BASE);
}

export function fetchAccount(kind: AccountKind, stem: string): Promise<Account> {
  return apiFetch(path(kind, stem));
}

export function savePersonalNotes(kind: AccountKind, stem: string, text: string, previous: string): Promise<{ text: string }> {
  return apiFetch(`${path(kind, stem)}/personal-notes`, { method: 'PUT', body: JSON.stringify({ text, previous }) });
}

/** What saving a capture did: the title it got, and whether Compass's tidy was used (and why not). */
export interface AddedCapture extends Captures {
  added: { title: string; tidied: boolean; note: string };
}

/** A new capture: its own section in the Captures note, signed with who added it and when.
 *  An empty `title` asks Compass to title it and fix its typing. */
export function addCapture(kind: AccountKind, stem: string, title: string, text: string): Promise<AddedCapture> {
  return apiFetch(`${path(kind, stem)}/captures`, { method: 'POST', body: JSON.stringify({ title, text }) });
}

export function accountLink(kind: AccountKind, stem: string): string {
  return `/entities/${kind}/${encodeURIComponent(stem)}`;
}

/** The backend's own sentence: a refused call arrives as `{"detail": "..."}`. */
export function errorText(error: unknown): string {
  const message = error instanceof Error ? error.message : String(error);
  try {
    const parsed = JSON.parse(message);
    if (typeof parsed?.detail === 'string') return parsed.detail;
  } catch {
    // not JSON: the message is already a sentence
  }
  return message;
}

export function fetchAccountCost(kind: AccountKind, stem: string): Promise<AccountCost> {
  return apiFetch(`${path(kind, stem)}/cost`);
}
