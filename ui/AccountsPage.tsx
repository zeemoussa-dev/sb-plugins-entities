import { Fragment, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router';
import { useRememberedState, useUrlFilters } from '../../pluginHost/state';
import { accountLink, errorText, fetchAccounts, type AccountList, type AccountRow } from './accountsClient';

const SHOWN = ['all', 'customers', 'partners'] as const;
type Shown = typeof SHOWN[number];
const SORTS = ['name', 'opportunities', 'people', 'affiliates'] as const;
type Sort = typeof SORTS[number];
const SORT_LABELS: Record<Sort, string> = {
  name: 'Name', opportunities: 'Most opportunities', people: 'Most people', affiliates: 'Most affiliates',
};
const VIEWS = ['cards', 'list'] as const;
type View = typeof VIEWS[number];
const AFFILIATE_CHIPS = 6;

interface Hub {
  row: AccountRow;
  children: Hub[];
  // Summed over the hub and every affiliate below it, so a group sorts by its whole size.
  totals: { opportunities: number; people: number; affiliates: number };
}

function matches(row: AccountRow, query: string): boolean {
  if (!query) return true;
  const text = `${row.name} ${row.stem} ${row.domain} ${row.tag} ${row.description}`.toLowerCase();
  return query.toLowerCase().split(/\s+/).every((word) => text.includes(word));
}

function forest(rows: AccountRow[]): Hub[] {
  const byParent = new Map<string | null, AccountRow[]>();
  for (const row of rows) byParent.set(row.parent, [...(byParent.get(row.parent) ?? []), row]);
  const build = (row: AccountRow): Hub => {
    const children = (byParent.get(row.stem) ?? []).map(build);
    const sum = (key: 'opportunities' | 'people') => row[key] + children.reduce((total, child) => total + child.totals[key], 0);
    return {
      row, children,
      totals: {
        opportunities: sum('opportunities'), people: sum('people'),
        affiliates: children.length + children.reduce((total, child) => total + child.totals.affiliates, 0),
      },
    };
  };
  return (byParent.get(null) ?? []).map(build);
}

/** A hub stays when it or anything below it matches; its non-matching affiliates are dropped. */
function filtered(hubs: Hub[], query: string): Hub[] {
  if (!query) return hubs;
  return hubs.flatMap((hub) => {
    const children = filtered(hub.children, query);
    return matches(hub.row, query) || children.length ? [{ ...hub, children: matches(hub.row, query) ? hub.children : children }] : [];
  });
}

function sorted(hubs: Hub[], sort: Sort): Hub[] {
  const value = (hub: Hub) => (sort === 'name' ? 0 : hub.totals[sort]);
  return [...hubs]
    .sort((a, b) => value(b) - value(a) || a.row.name.localeCompare(b.row.name))
    .map((hub) => ({ ...hub, children: sorted(hub.children, 'name') }));
}

function initials(name: string): string {
  const words = name.replace(/[^\p{L}\p{N} ]/gu, ' ').split(/\s+/).filter(Boolean);
  if (words.length === 0) return '?';
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[1][0]).toUpperCase();
}

/** A stable hue per name, so a company keeps its colour from visit to visit. */
function hue(name: string): number {
  let hash = 0;
  for (const character of name) hash = (hash * 31 + character.charCodeAt(0)) % 360;
  return hash;
}

function Avatar({ name, size = 'md' }: { name: string; size?: 'sm' | 'md' }) {
  return (
    <span className={`entities-avatar entities-avatar-${size}`} style={{ ['--entities-hue' as string]: hue(name) }} aria-hidden="true">
      {initials(name)}
    </span>
  );
}

function Count({ icon, value, label }: { icon: string; value: number; label: string }) {
  return (
    <span className={`entities-count ${value ? '' : 'entities-count-zero'}`} title={`${value} ${label}`}>
      <span className="material-symbols-outlined" aria-hidden="true">{icon}</span>
      {value}
      <span className="entities-visually-hidden"> {label}</span>
    </span>
  );
}

function HubCard({ hub, query }: { hub: Hub; query: string }) {
  const { row, children, totals } = hub;
  const shownChildren = children.slice(0, AFFILIATE_CHIPS);
  return (
    <article className={`entities-hub-card entities-kind-${row.kind}`}>
      <Link className="entities-hub-card-link" to={accountLink(row.kind, row.stem)} aria-label={row.name} />
      <header className="entities-hub-card-head">
        <Avatar name={row.name} />
        <div className="entities-hub-card-title">
          <h3>{row.name}</h3>
          <span className="text-muted">{row.domain || (row.kind === 'partner' ? 'Partner' : 'Customer')}</span>
        </div>
        {row.has_commitment && <span className="entities-pill entities-pill-macc" title="A signed Azure commitment is on the note">MACC</span>}
      </header>
      <p className={`entities-hub-card-description ${row.description ? '' : 'text-muted'}`}>
        {row.description || 'No description yet.'}
      </p>
      <footer className="entities-hub-card-foot">
        <div className="entities-counts">
          <Count icon="work" value={totals.opportunities} label="opportunities" />
          <Count icon="group" value={totals.people} label="people" />
          <Count icon="account_tree" value={totals.affiliates} label="affiliates" />
        </div>
        {children.length > 0 && (
          <div className="entities-chips">
            {shownChildren.map((child) => (
              <Link key={child.row.stem} to={accountLink(child.row.kind, child.row.stem)}
                    className={`entities-chip ${query && matches(child.row, query) ? 'entities-chip-match' : ''}`}>
                {child.row.name}{child.children.length ? ` +${child.totals.affiliates}` : ''}
              </Link>
            ))}
            {children.length > AFFILIATE_CHIPS && (
              <Link to={accountLink(row.kind, row.stem)} className="entities-chip entities-chip-more">
                +{children.length - AFFILIATE_CHIPS} more
              </Link>
            )}
          </div>
        )}
      </footer>
    </article>
  );
}

function ListRows({ hubs, depth, query, open, toggle }: {
  hubs: Hub[]; depth: number; query: string; open: Set<string>; toggle: (key: string) => void;
}) {
  return (
    <>
      {hubs.map((hub) => {
        const key = `${hub.row.kind}:${hub.row.stem}`;
        // A search opens every group it reaches into, so a matching affiliate is never hidden.
        const expanded = open.has(key) || (query !== '' && hub.children.length > 0);
        return (
          <Fragment key={key}>
            <tr className={`entities-list-row ${depth ? 'entities-list-child' : ''}`}>
              <td>
                <div className="entities-list-name" style={{ paddingLeft: depth * 28 }}>
                  {hub.children.length > 0 ? (
                    <button type="button" className="entities-expander" aria-expanded={expanded}
                            aria-label={`${expanded ? 'Hide' : 'Show'} affiliates of ${hub.row.name}`} onClick={() => toggle(key)}>
                      <span className="material-symbols-outlined" aria-hidden="true">{expanded ? 'expand_more' : 'chevron_right'}</span>
                    </button>
                  ) : <span className="entities-expander-space" />}
                  <Avatar name={hub.row.name} size="sm" />
                  <div>
                    <Link to={accountLink(hub.row.kind, hub.row.stem)} className="entities-list-link">{hub.row.name}</Link>
                    {hub.row.description && <div className="text-muted entities-list-description">{hub.row.description}</div>}
                  </div>
                </div>
              </td>
              <td className="text-muted">{hub.row.domain || '—'}</td>
              <td><span className={`entities-pill entities-pill-${hub.row.kind}`}>{hub.row.kind === 'partner' ? 'Partner' : 'Customer'}</span></td>
              <td className="num">{hub.totals.affiliates || ''}</td>
              <td className="num">{hub.totals.opportunities || ''}</td>
              <td className="num">{hub.totals.people || ''}</td>
              <td>{hub.row.has_commitment && <span className="entities-pill entities-pill-macc">MACC</span>}</td>
            </tr>
            {expanded && <ListRows hubs={hub.children} depth={depth + 1} query={query} open={open} toggle={toggle} />}
          </Fragment>
        );
      })}
    </>
  );
}

function Stat({ label, value, icon }: { label: string; value: number; icon: string }) {
  return (
    <div className="entities-stat">
      <span className="material-symbols-outlined entities-stat-icon" aria-hidden="true">{icon}</span>
      <div>
        <strong>{value.toLocaleString()}</strong>
        <span className="text-muted">{label}</span>
      </div>
    </div>
  );
}

export function AccountsPage() {
  const [filters, setFilter] = useUrlFilters({ q: '', show: 'all', sort: 'name' });
  const show: Shown = (SHOWN as readonly string[]).includes(filters.show) ? filters.show as Shown : 'all';
  const sort: Sort = (SORTS as readonly string[]).includes(filters.sort) ? filters.sort as Sort : 'name';
  const [view, setView] = useRememberedState<View>('entities.accounts.view', 'cards');
  const [accounts, setAccounts] = useState<AccountList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<Set<string>>(new Set());

  useEffect(() => {
    fetchAccounts().then(setAccounts).catch((caught) => setError(errorText(caught)));
  }, []);

  const groups = useMemo(() => {
    if (!accounts) return [];
    const all = [
      { key: 'customers' as const, title: 'Customers', hubs: forest(accounts.customers) },
      { key: 'partners' as const, title: 'Partners', hubs: forest(accounts.partners) },
    ];
    return all
      .filter((group) => show === 'all' || show === group.key)
      .map((group) => ({ ...group, hubs: sorted(filtered(group.hubs, filters.q), sort) }));
  }, [accounts, show, sort, filters.q]);

  const stats = useMemo(() => {
    if (!accounts) return null;
    const every = [...accounts.customers, ...accounts.partners];
    return {
      customers: accounts.customers.filter((row) => !row.parent).length,
      partners: accounts.partners.filter((row) => !row.parent).length,
      affiliates: every.filter((row) => row.parent).length,
      commitments: every.filter((row) => row.has_commitment).length,
      opportunities: every.reduce((total, row) => total + row.opportunities, 0),
      people: every.reduce((total, row) => total + row.people, 0),
    };
  }, [accounts]);

  const toggle = (key: string) => setOpen((current) => {
    const next = new Set(current);
    if (next.has(key)) next.delete(key); else next.add(key);
    return next;
  });

  return (
    <div className="page entities-accounts">
      <header className="entities-accounts-hero">
        <div>
          <h1>Customers &amp; Partners</h1>
          <p className="text-muted">Every company in the vault, with its affiliates, pipeline and people.</p>
        </div>
        {stats && (
          <div className="entities-stats">
            <Stat icon="apartment" label="Customers" value={stats.customers} />
            <Stat icon="handshake" label="Partners" value={stats.partners} />
            <Stat icon="account_tree" label="Affiliates" value={stats.affiliates} />
            <Stat icon="verified" label="MACCs signed" value={stats.commitments} />
            <Stat icon="work" label="Opportunities" value={stats.opportunities} />
            <Stat icon="group" label="People" value={stats.people} />
          </div>
        )}
      </header>

      <div className="entities-accounts-toolbar">
        <label className="entities-search">
          <span className="material-symbols-outlined" aria-hidden="true">search</span>
          <input type="search" placeholder="Search by name, domain, tag or description" value={filters.q}
                 onChange={(event) => setFilter('q', event.target.value)} aria-label="Search" />
        </label>
        <div className="entities-segmented" role="group" aria-label="Show">
          {SHOWN.map((option) => (
            <button key={option} type="button" aria-pressed={show === option}
                    className={show === option ? 'active' : ''} onClick={() => setFilter('show', option)}>
              {option === 'all' ? 'All' : option === 'customers' ? 'Customers' : 'Partners'}
            </button>
          ))}
        </div>
        <select className="input entities-sort" value={sort} onChange={(event) => setFilter('sort', event.target.value)} aria-label="Sort">
          {SORTS.map((option) => <option key={option} value={option}>{SORT_LABELS[option]}</option>)}
        </select>
        <div className="entities-segmented" role="group" aria-label="View">
          {VIEWS.map((option) => (
            <button key={option} type="button" aria-pressed={view === option} title={option === 'cards' ? 'Cards' : 'List'}
                    className={view === option ? 'active' : ''} onClick={() => setView(option)}>
              <span className="material-symbols-outlined" aria-hidden="true">{option === 'cards' ? 'grid_view' : 'view_list'}</span>
              <span className="entities-visually-hidden">{option === 'cards' ? 'Cards' : 'List'}</span>
            </button>
          ))}
        </div>
      </div>

      {error && <p className="entities-error">{error}</p>}
      {!accounts && !error && (
        <div className="entities-card-grid" aria-busy="true">
          {Array.from({ length: 8 }, (_, index) => <div key={index} className="entities-hub-card entities-skeleton" />)}
        </div>
      )}

      {groups.map((group) => (
        <section key={group.key} className="entities-accounts-section">
          <h2 className="entities-section-title">
            {group.title} <span className="entities-section-count">{group.hubs.length}</span>
          </h2>
          {group.hubs.length === 0 && <p className="text-muted">No {group.title.toLowerCase()} match “{filters.q}”.</p>}
          {group.hubs.length > 0 && view === 'cards' && (
            <div className="entities-card-grid">
              {group.hubs.map((hub) => <HubCard key={hub.row.stem} hub={hub} query={filters.q} />)}
            </div>
          )}
          {group.hubs.length > 0 && view === 'list' && (
            <div className="entities-list-wrap">
              <table className="entities-list">
                <thead>
                  <tr>
                    <th>Name</th><th>Domain</th><th>Kind</th>
                    <th className="num">Affiliates</th><th className="num">Opportunities</th><th className="num">People</th><th />
                  </tr>
                </thead>
                <tbody>
                  <ListRows hubs={group.hubs} depth={0} query={filters.q} open={open} toggle={toggle} />
                </tbody>
              </table>
            </div>
          )}
        </section>
      ))}
    </div>
  );
}
