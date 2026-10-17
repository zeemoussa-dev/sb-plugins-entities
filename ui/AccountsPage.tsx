import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router';
import { useUrlFilters } from '../../pluginHost/state';
import { accountLink, errorText, fetchAccounts, type AccountList, type AccountRow } from './accountsClient';

const SHOWN = ['all', 'customers', 'partners'] as const;
type Shown = typeof SHOWN[number];

function matches(row: AccountRow, query: string): boolean {
  if (!query) return true;
  const text = `${row.name} ${row.stem} ${row.domain} ${row.tag}`.toLowerCase();
  return query.toLowerCase().split(/\s+/).every((word) => text.includes(word));
}

/** Rows as a tree: each hub followed by its affiliates, indented by depth. A
 * search keeps a match's ancestors, so an affiliate never shows without its parent. */
function tree(rows: AccountRow[], query: string): { row: AccountRow; depth: number; match: boolean }[] {
  const children = new Map<string | null, AccountRow[]>();
  for (const row of rows) {
    const siblings = children.get(row.parent) ?? [];
    siblings.push(row);
    children.set(row.parent, siblings);
  }
  const result: { row: AccountRow; depth: number; match: boolean }[] = [];
  const visit = (parent: string | null, depth: number): boolean => {
    let anyShown = false;
    const sorted = [...(children.get(parent) ?? [])].sort((a, b) => a.name.localeCompare(b.name));
    for (const row of sorted) {
      const at = result.length;
      const match = matches(row, query);
      const descendantShown = visit(row.stem, depth + 1);
      if (match || descendantShown) {
        result.splice(at, 0, { row, depth, match });
        anyShown = true;
      }
    }
    return anyShown;
  };
  visit(null, 0);
  return result;
}

function AccountGroup({ title, rows, query }: { title: string; rows: AccountRow[]; query: string }) {
  const shown = useMemo(() => tree(rows, query), [rows, query]);
  const topLevel = rows.filter((row) => !row.parent).length;
  return (
    <section className="card entities-accounts-group">
      <h2 className="entities-card-title">{title} <span className="text-muted">{topLevel} · {rows.length - topLevel} affiliates</span></h2>
      {shown.length === 0 && <p className="text-muted">No matches.</p>}
      <table className="entities-accounts-table">
        <thead>
          <tr><th>Name</th><th>Domain</th><th className="num">Affiliates</th><th className="num">Opportunities</th><th className="num">People</th><th /></tr>
        </thead>
        <tbody>
          {shown.map(({ row, depth, match }) => (
            <tr key={row.stem} className={match ? '' : 'entities-accounts-context'}>
              <td style={{ paddingLeft: `calc(var(--space-2) + ${depth * 20}px)` }}>
                {depth > 0 && <span className="text-muted" aria-hidden="true">↳ </span>}
                <Link to={accountLink(row.kind, row.stem)}>{row.name}</Link>
                {row.description && <div className="text-muted entities-accounts-description">{row.description}</div>}
              </td>
              <td className="text-muted">{row.domain || '—'}</td>
              <td className="num">{row.affiliates || ''}</td>
              <td className="num">{row.opportunities || ''}</td>
              <td className="num">{row.people || ''}</td>
              <td>{row.has_commitment && <span className="badge badge-success" title="A signed Azure commitment is on the note">MACC</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

export function AccountsPage() {
  const [filters, setFilter] = useUrlFilters({ q: '', show: 'all' });
  const show: Shown = (SHOWN as readonly string[]).includes(filters.show) ? filters.show as Shown : 'all';
  const [accounts, setAccounts] = useState<AccountList | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchAccounts().then(setAccounts).catch((caught) => setError(errorText(caught)));
  }, []);

  return (
    <div className="page entities-accounts">
      <h1>Customers &amp; Partners</h1>
      <div className="entities-accounts-toolbar">
        <input className="input" type="search" placeholder="Search by name, domain or tag" value={filters.q}
               onChange={(event) => setFilter('q', event.target.value)} aria-label="Search" />
        <div className="entities-segmented" role="group" aria-label="Show">
          {SHOWN.map((option) => (
            <button key={option} type="button" className={`btn ${show === option ? 'btn-primary' : ''}`}
                    onClick={() => setFilter('show', option)}>
              {option === 'all' ? 'All' : option === 'customers' ? 'Customers' : 'Partners'}
            </button>
          ))}
        </div>
      </div>
      {error && <p className="entities-error">{error}</p>}
      {!accounts && !error && <p className="text-muted">Loading…</p>}
      {accounts && show !== 'partners' && <AccountGroup title="Customers" rows={accounts.customers} query={filters.q} />}
      {accounts && show !== 'customers' && <AccountGroup title="Partners" rows={accounts.partners} query={filters.q} />}
    </div>
  );
}
