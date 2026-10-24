import { useCallback, useEffect, useState, type KeyboardEvent } from 'react';
import { Link, useParams } from 'react-router';
import { Breadcrumbs } from '../../pluginHost/breadcrumbs';
import { VaultNoteEditor } from '../../pluginHost/noteEditor';
import { NoteText } from '../../pluginHost/noteText';
import { useUrlState } from '../../pluginHost/state';
import {
  accountLink, addCapture, errorText, fetchAccount, fetchAccountCost, savePersonalNotes,
  type Account, type AccountCost, type AccountKind, type AddedCapture, type CostRow,
} from './accountsClient';

const TABS = ['overview', 'notes', 'opportunities', 'people', 'activity'] as const;
type Tab = typeof TABS[number];
const TAB_LABELS: Record<Tab, string> = {
  overview: 'Overview', notes: 'Notes & Captures', opportunities: 'Opportunities', people: 'People', activity: 'Activity',
};
// The note's own sections this page shows elsewhere, or that are links the other tabs list better.
const SHOWN_ELSEWHERE = new Set(['Personal Notes', 'Affiliates', 'Opportunities', 'History & Captures']);

function money(value: number | null | undefined, currency: string | null | undefined): string {
  if (value === null || value === undefined) return '—';
  try {
    return new Intl.NumberFormat(undefined, {
      style: 'currency', currency: (currency || 'USD').trim(), notation: 'compact', maximumFractionDigits: 1,
    }).format(value);
  } catch {
    return `${Math.round(value).toLocaleString()} ${currency ?? ''}`.trim();
  }
}

function browse(stem: string): string {
  return `/browse/${encodeURIComponent(stem)}`;
}

/** A section the operator owns: rendered as the note shows it, edited as plain markdown.
 * Saving sends what was loaded too, so an edit made meanwhile in Obsidian is refused, not lost. */
function EditableSection({ title, text, emptyText, onSave }: {
  title: string;
  text: string;
  emptyText: string;
  onSave: (text: string, previous: string) => Promise<void>;
}) {
  const [draft, setDraft] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    if (draft === null) return;
    setSaving(true);
    setError(null);
    try {
      await onSave(draft, text);
      setDraft(null);
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="card entities-account-section">
      <div className="entities-account-section-head">
        <h2 className="entities-card-title">{title}</h2>
        {draft === null && <button type="button" className="btn" onClick={() => setDraft(text)}>Edit</button>}
      </div>
      {draft === null ? (
        text ? <div className="markdown-body"><NoteText text={text} /></div> : <p className="text-muted">{emptyText}</p>
      ) : (
        <>
          <textarea className="input entities-textarea" value={draft} rows={Math.max(8, draft.split('\n').length + 2)}
                    onChange={(event) => setDraft(event.target.value)} aria-label={title} autoFocus />
          <div className="entities-actions">
            <button type="button" className="btn btn-primary" disabled={saving} onClick={save}>{saving ? 'Saving…' : 'Save'}</button>
            <button type="button" className="btn" disabled={saving} onClick={() => { setDraft(null); setError(null); }}>Cancel</button>
          </div>
        </>
      )}
      {error && <p className="entities-error">{error}</p>}
    </section>
  );
}

/** Loaded on its own: Cost Manager computes the burn on asking, and the page should not wait for it. */
function CostPanel({ account }: { account: Account }) {
  const [cost, setCost] = useState<AccountCost | null>(null);
  useEffect(() => {
    let current = true;
    fetchAccountCost(account.kind, account.stem)
      .then((answer) => { if (current) setCost(answer); })
      .catch((caught) => { if (current) setCost({ available: true, row: null, error: errorText(caught) }); });
    return () => { current = false; };
  }, [account.kind, account.stem]);

  // Most Partners are never linked, so "not linked" is only worth saying on a Customer.
  const quietWhenUnlinked = account.kind === 'partner';
  if (!cost) return quietWhenUnlinked ? null : <section className="card"><p className="text-muted">Loading Azure consumption…</p></section>;
  if (!cost.available) return null;
  if (quietWhenUnlinked && !cost.row && !cost.error) return null;
  const row: CostRow | null = cost.row;
  return (
    <section className="card">
      <div className="entities-account-section-head">
        <h2 className="entities-card-title">Azure consumption</h2>
        {row?.route && <Link className="btn" to={row.route}>Open in Azure Customer 360</Link>}
      </div>
      {cost.error && <p className="entities-error">Azure Customer 360 could not answer: {cost.error}</p>}
      {!row && !cost.error && <p className="text-muted">Not linked to a customer in Azure Customer 360.</p>}
      {row && (
        <>
          <div className="entities-tiles">
            <div><span className="text-muted">Signed</span><strong>{money(row.signed, row.currency)}</strong></div>
            <div><span className="text-muted">Consumed</span><strong>{row.burn ? `${row.burn.consumed_pct}%` : '—'}</strong>
              {row.burn && <span className="text-muted">{money(row.burn.consumed, row.currency)} · term {row.burn.elapsed_pct}%</span>}</div>
            <div><span className="text-muted">Last month</span><strong>{money(row.last_month?.actual, row.currency)}</strong>
              {row.last_month && <span className="text-muted">{row.last_month.month}</span>}</div>
            <div><span className="text-muted">Projected at end</span><strong>{money(row.burn?.projected_at_end, row.currency)}</strong>
              {row.burn?.end && <span className="text-muted">term ends {row.burn.end}</span>}</div>
          </div>
          {row.burn && (
            <div className="entities-burn" title={`${row.burn.consumed_pct}% consumed, ${row.burn.elapsed_pct}% of the term elapsed`}>
              <div className={`entities-burn-fill ${row.burn.consumed_pct >= row.burn.elapsed_pct ? 'ahead' : 'behind'}`}
                   style={{ width: `${Math.min(row.burn.consumed_pct, 100)}%` }} />
              <div className="entities-burn-marker" style={{ left: `${Math.min(row.burn.elapsed_pct, 100)}%` }} />
            </div>
          )}
          <p className="text-muted entities-small">
            {row.enrollments} enrollment{row.enrollments === 1 ? '' : 's'} · status {row.status}
            {row.synced_at && <> · synced {row.synced_at.slice(0, 10)}{row.stale ? ' (stale)' : ''}</>}
          </p>
        </>
      )}
    </section>
  );
}

function Overview({ account }: { account: Account }) {
  const commitment = account.commitment;
  const sections = account.sections.filter((section) => !SHOWN_ELSEWHERE.has(section.name) && section.text);
  return (
    <>
      {commitment && (
        <section className="card">
          <h2 className="entities-card-title">Signed commitment</h2>
          <div className="entities-tiles">
            <div><span className="text-muted">{commitment.type || 'Commitment'}</span><strong>{money(commitment.amount, commitment.currency)}</strong></div>
            <div><span className="text-muted">Term</span><strong>{commitment.start} → {commitment.end}</strong></div>
            <div><span className="text-muted">Marketplace counts</span><strong>{commitment.include_marketplace ? 'Yes' : 'No'}</strong></div>
            <div><span className="text-muted">Credits subtract</span><strong>{commitment.subtract_credits ? 'Yes' : 'No'}</strong></div>
            <div><span className="text-muted">Affiliates</span>
              <strong>{commitment.affiliates === 'own' ? 'Sign their own' : 'Roll up into it'}</strong></div>
          </div>
          {commitment.note && <p className="text-muted">{commitment.note}</p>}
        </section>
      )}
      <CostPanel account={account} />
      {account.intro && <section className="card markdown-body"><NoteText text={account.intro} /></section>}
      {sections.map((section) => (
        <section className="card" key={section.name}>
          <h2 className="entities-card-title">{section.name}</h2>
          <div className="markdown-body"><NoteText text={section.text} /></div>
        </section>
      ))}
      {account.news && (
        <section className="card">
          <h2 className="entities-card-title">News</h2>
          <div className="markdown-body"><NoteText text={account.news} /></div>
        </section>
      )}
      {!commitment && !account.intro && sections.length === 0 && !account.news && (
        <p className="text-muted">This note has nothing written in it yet.</p>
      )}
    </>
  );
}

/** The whole Captures note -- real ones keep their content in sections of their
 * own, not only under Notes -- and a new capture as a section of its own, titled
 * and signed with who added it and when (operator, 2026-10-24). */
function CapturesPanel({ account, onChange }: { account: Account; onChange: (account: Account) => void }) {
  const [composing, setComposing] = useState(false);
  const [text, setText] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<AddedCapture['added'] | null>(null);
  // The editor loads the note itself; a new capture written beside it needs it to load again.
  const [revision, setRevision] = useState(0);
  const captures = account.captures;

  const close = () => { setComposing(false); setText(''); setError(null); };

  // Clicking away is "done", as in the vault editor: there is no Save button to find.
  const finish = async () => {
    if (saving) return;
    if (!text.trim()) { close(); return; }
    setSaving(true);
    setError(null);
    try {
      const result = await addCapture(account.kind, account.stem, '', text);
      onChange({ ...account, captures: { exists: result.exists, stem: result.stem, body: result.body } });
      setSaved(result.added);
      setRevision((current) => current + 1);
      close();
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setSaving(false);
    }
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) { event.preventDefault(); void finish(); }
    if (event.key === 'Escape') { event.preventDefault(); close(); }
  };

  return (
    <section className="card">
      <div className="entities-account-section-head">
        <h2 className="entities-card-title">Captures</h2>
        {captures.exists && <Link className="btn" to={browse(captures.stem)}>Edit in vault</Link>}
      </div>
      {!composing && !saving && (
        <button type="button" className="entities-capture-start" onClick={() => { setSaved(null); setComposing(true); }}>
          <span className="material-symbols-outlined" aria-hidden="true">edit_note</span>
          Type a new capture…
        </button>
      )}
      {(composing || saving) && (
        <div className="entities-capture-inplace">
          <textarea value={text} autoFocus readOnly={saving} rows={Math.max(4, text.split('\n').length + 1)}
                    placeholder="What happened, what was said… Click away when you're done."
                    onChange={(event) => setText(event.target.value)} onBlur={() => void finish()} onKeyDown={onKeyDown}
                    aria-label="New capture" />
          <p className="text-muted entities-small">
            {saving ? '✨ Compass is titling it and tidying the typing…'
              : 'Saves when you click away (or Ctrl+Enter) -- titled and tidied by Compass, signed with your name and the time. Esc cancels.'}
          </p>
        </div>
      )}
      {error && <p className="entities-error">{error}</p>}
      {saved && (
        <p className="entities-capture-saved">
          Saved as <strong>{saved.title}</strong>{saved.tidied ? ', typing tidied.' : '.'}
          {saved.note && <span className="text-muted"> {saved.note}</span>}
        </p>
      )}
      {captures.exists
        ? <VaultNoteEditor key={revision} stem={captures.stem} offerTidy />
        : <p className="text-muted">No captures yet.</p>}
    </section>
  );
}

function Opportunities({ account }: { account: Account }) {
  if (account.opportunities.length === 0) return <p className="text-muted">No opportunities.</p>;
  return (
    <section className="card">
      <table className="entities-accounts-table">
        <thead>
          <tr><th>Opportunity</th><th>{account.kind === 'partner' ? 'Customer' : 'Affiliate'}</th><th>Status</th><th>Stage</th><th>Product</th><th>Route</th><th className="num">Monthly</th><th>Updated</th></tr>
        </thead>
        <tbody>
          {account.opportunities.map((opportunity) => (
            <tr key={opportunity.id || opportunity.stem}>
              <td><Link to={browse(opportunity.stem)}>{opportunity.title}</Link></td>
              <td>{account.kind === 'partner' ? (opportunity.affiliate ?? opportunity.customer) : (opportunity.affiliate ?? '—')}</td>
              <td><span className={`badge ${opportunity.status === 'Won' ? 'badge-success' : opportunity.status === 'Lost' ? 'badge-danger' : ''}`}>{opportunity.status}</span></td>
              <td>{opportunity.stage}</td>
              <td>{opportunity.product.join(', ')}</td>
              <td className="text-muted">{opportunity.route}</td>
              <td className="num">{money(opportunity.expected_monthly_usd, 'USD')}</td>
              <td className="text-muted">{opportunity.updated}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function People({ account }: { account: Account }) {
  if (account.people.length === 0) return <p className="text-muted">No people filed under {account.name}.</p>;
  return (
    <section className="card">
      <table className="entities-accounts-table">
        <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Department</th></tr></thead>
        <tbody>
          {account.people.map((person) => (
            <tr key={person.stem}>
              <td><Link to={browse(person.stem)}>{person.name}</Link></td>
              <td className="text-muted">{person.email}</td>
              <td>{person.role}</td>
              <td>{person.department}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function Activity({ account }: { account: Account }) {
  if (account.activity.length === 0) return <p className="text-muted">No meetings or threads tagged {account.tag}.</p>;
  return (
    <section className="card">
      <ul className="entities-activity">
        {account.activity.map((item) => (
          <li key={`${item.kind}-${item.stem}`}>
            <span className="text-muted entities-activity-date">{item.date.slice(0, 10)}</span>
            <span className="badge">{item.kind === 'meeting' ? 'Meeting' : 'Thread'}</span>
            <Link to={item.kind === 'meeting' ? `/meeting-cockpit/${encodeURIComponent(item.stem)}` : `/inbox-cockpit/${encodeURIComponent(item.stem)}`}>
              {item.title}
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function AccountPage() {
  const { kind, stem } = useParams();
  const accountKind = kind as AccountKind;
  const [tab, setTab] = useUrlState<Tab>('tab', 'overview', { valid: TABS });
  const [account, setAccount] = useState<Account | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!stem) return;
    setError(null);
    fetchAccount(accountKind, stem).then(setAccount).catch((caught) => setError(errorText(caught)));
  }, [accountKind, stem]);

  useEffect(() => {
    setAccount(null);
    load();
  }, [load]);

  const group = accountKind === 'partner' ? 'Partners' : 'Customers';
  const counts: Partial<Record<Tab, number>> = account ? {
    opportunities: account.opportunities.length, people: account.people.length, activity: account.activity.length,
  } : {};

  return (
    <div className="page entities-account">
      <Breadcrumbs items={[
        { label: 'Customers & Partners', to: `/entities?show=${group.toLowerCase()}` },
        ...(account?.lineage ?? []).map((above) => ({ label: above.name, to: accountLink(accountKind, above.stem) })),
        { label: account?.name ?? stem ?? '' },
      ]} />
      <div className="entities-account-header">
        <div>
          <h1>{account?.name ?? stem}</h1>
          {account && (
            <p className="text-muted entities-small">
              {accountKind === 'partner' ? 'Partner' : 'Customer'}
              {account.domain && <> · {account.domain}</>}
              {account.aliases.length > 0 && <> · also {account.aliases.join(', ')}</>}
              {' · '}<code>{account.tag}</code>
            </p>
          )}
          {account?.description && <p className="entities-account-description">{account.description}</p>}
        </div>
        {account && <Link className="btn" to={browse(account.stem)}>Open note</Link>}
      </div>
      {account && account.affiliates.length > 0 && (
        <p className="entities-affiliates">
          <span className="text-muted">Affiliates: </span>
          {account.affiliates.map((affiliate, index) => (
            <span key={affiliate.stem}>{index > 0 && ' · '}<Link to={accountLink(accountKind, affiliate.stem)}>{affiliate.name}</Link></span>
          ))}
        </p>
      )}
      {error && <p className="entities-error">{error}</p>}
      {!account && !error && <p className="text-muted">Loading…</p>}
      {account && (
        <>
          <div className="entities-tabs" role="tablist">
            {TABS.map((option) => (
              <button key={option} type="button" role="tab" aria-selected={tab === option}
                      className={`entities-tab ${tab === option ? 'active' : ''}`} onClick={() => setTab(option)}>
                {TAB_LABELS[option]}{counts[option] ? <span className="text-muted"> {counts[option]}</span> : null}
              </button>
            ))}
          </div>
          {tab === 'overview' && <Overview account={account} />}
          {tab === 'notes' && (
            <>
              {account.sections.some((section) => section.name === 'Personal Notes') ? (
                <section className="card">
                  {/* The editor draws the section's own heading. It is the vault's own editor, bounded to this one section: the hub's other
                      sections are Hermes' and never enter the editor or a save. */}
                  <VaultNoteEditor stem={account.stem} sections={['Personal Notes']} offerTidy />
                </section>
              ) : (
                // A hub written before the section existed: the plain editor adds it.
                <EditableSection
                  title="Personal Notes"
                  text={account.personal_notes}
                  emptyText="Nothing written yet."
                  onSave={async (draft, previous) => {
                    const saved = await savePersonalNotes(account.kind, account.stem, draft, previous);
                    setAccount({ ...account, personal_notes: saved.text, sections: [...account.sections, { name: 'Personal Notes', text: saved.text }] });
                  }}
                />
              )}
              <CapturesPanel account={account} onChange={setAccount} />
            </>
          )}
          {tab === 'opportunities' && <Opportunities account={account} />}
          {tab === 'people' && <People account={account} />}
          {tab === 'activity' && <Activity account={account} />}
        </>
      )}
    </div>
  );
}
