import { useEffect, useState } from 'react';
import { Link } from 'react-router';
import { Field } from './Field';
import { createEntity, deleteEntity, fetchEntities, updateEntity, type Entity, type NewEntity } from './client';

type Draft = { aliases: string; affiliate_of: string; domain: string };

const EMPTY_NEW: NewEntity = { name: '', section: 'customer', domain: '', aliases: '', affiliate_of: '' };

function draftFrom(entity: Entity): Draft {
  return { aliases: entity.aliases, affiliate_of: entity.affiliate_of, domain: entity.domain };
}

export function EntitiesPage() {
  const [entities, setEntities] = useState<Entity[] | null>(null);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [newEntity, setNewEntity] = useState<NewEntity>(EMPTY_NEW);
  const [message, setMessage] = useState<string | null>(null);
  const [search, setSearch] = useState('');

  function reload() {
    fetchEntities().then((result) => {
      setEntities(result.entities);
      setDrafts(Object.fromEntries(result.entities.map((entity) => [entity.name, draftFrom(entity)])));
    });
  }

  useEffect(() => {
    reload();
  }, []);

  function updateDraft(name: string, patch: Partial<Draft>) {
    setDrafts((prev) => ({ ...prev, [name]: { ...prev[name], ...patch } }));
  }

  function toggleExpanded(name: string) {
    setExpanded((prev) => ({ ...prev, [name]: !prev[name] }));
  }

  async function handleSaveDraft(name: string) {
    await updateEntity(name, drafts[name]);
    reload();
  }

  async function handleToggleIgnore(entity: Entity) {
    await updateEntity(entity.name, { ignore: !entity.ignore });
    reload();
  }

  async function handleSection(entity: Entity, section: string) {
    await updateEntity(entity.name, { section });
    reload();
  }

  async function handleDelete(name: string) {
    await deleteEntity(name);
    reload();
  }

  async function handleCreate(event: React.FormEvent) {
    event.preventDefault();
    setMessage(null);
    if (!newEntity.name.trim()) return;
    try {
      await createEntity(newEntity);
      setNewEntity(EMPTY_NEW);
      reload();
    } catch {
      setMessage('Could not add entity — an entity with that name may already exist.');
    }
  }

  function renderRow(entity: Entity) {
    const draft = drafts[entity.name] ?? draftFrom(entity);
    const isOpen = expanded[entity.name] ?? false;
    return (
      <div className="item-row" key={entity.name} data-entity-row={entity.name} style={{ flexDirection: 'column', alignItems: 'stretch' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 'var(--space-2)' }}>
          <button
            type="button"
            onClick={() => toggleExpanded(entity.name)}
            style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', color: 'inherit', background: 'none', border: 'none', cursor: 'pointer', padding: 0, textAlign: 'left', flex: 1 }}
          >
            <span className="material-symbols-outlined" aria-hidden="true" style={{ fontSize: '18px', color: 'var(--color-text-muted)' }}>
              {isOpen ? 'expand_more' : 'chevron_right'}
            </span>
            <span className="item-row-title">
              {entity.name}{' '}
              <span className={`badge ${entity.created ? 'badge-success' : 'badge-warning'}`}>
                {entity.created ? 'Hub created' : 'Not created yet'}
              </span>
            </span>
          </button>
          <div className="item-row-actions">
            <button type="button" className="btn" onClick={() => handleToggleIgnore(entity)}>
              {entity.ignore ? 'Approve' : 'Mark ignored'}
            </button>
            <button type="button" className="btn btn-danger" onClick={() => handleDelete(entity.name)}>Delete</button>
          </div>
        </div>
        {isOpen && (
          <div className="item-row-actions" style={{ marginTop: 'var(--space-3)', flexWrap: 'wrap', alignItems: 'flex-end' }}>
            <Field label="Type">
              <select
                className="input"
                style={{ width: 'auto' }}
                value={entity.section}
                onChange={(event) => handleSection(entity, event.target.value)}
              >
                <option value="customer">Company</option>
                <option value="partner">Partner</option>
              </select>
            </Field>
            <Field label="Aliases">
              <input className="input" value={draft.aliases} onChange={(event) => updateDraft(entity.name, { aliases: event.target.value })} />
            </Field>
            <Field label="Affiliate of">
              <input className="input" value={draft.affiliate_of} onChange={(event) => updateDraft(entity.name, { affiliate_of: event.target.value })} />
            </Field>
            <Field label="Domain">
              <input className="input" value={draft.domain} onChange={(event) => updateDraft(entity.name, { domain: event.target.value })} />
            </Field>
            <button type="button" className="btn" onClick={() => handleSaveDraft(entity.name)}>Save</button>
          </div>
        )}
      </div>
    );
  }

  function renderGroup(label: string, list: Entity[]) {
    return (
      <>
        <p className="text-muted" style={{ fontSize: 'var(--font-size-sm)', textTransform: 'uppercase', marginTop: 'var(--space-4)' }}>
          {label} ({list.length})
        </p>
        <div className="item-list" style={{ marginBottom: 'var(--space-4)' }}>
          {list.map(renderRow)}
          {list.length === 0 && <p className="text-muted">No matches.</p>}
        </div>
      </>
    );
  }

  const query = search.trim().toLowerCase();
  const matches = (entity: Entity) =>
    !query
    || entity.name.toLowerCase().includes(query)
    || entity.domain.toLowerCase().includes(query)
    || entity.aliases.toLowerCase().includes(query);

  // Discovery and "Add entity" both append to the end of a section, so each
  // group is shown newest first. A newly discovered entry defaults to
  // Ignore: Yes and so lands in Needs review; Companies and Partners show only
  // reviewed entries, so no entry appears twice.
  const needsReview = entities?.filter((entity) => entity.ignore && matches(entity)).reverse() ?? [];
  const companies = entities?.filter((entity) => entity.section === 'customer' && !entity.ignore && matches(entity)).reverse() ?? [];
  const partners = entities?.filter((entity) => entity.section === 'partner' && !entity.ignore && matches(entity)).reverse() ?? [];

  return (
    <>
      <p className="text-muted"><Link className="text-muted" to="/settings">&larr; Settings</Link></p>
      <h1>Entities</h1>
      <p className="text-muted" style={{ fontSize: 'var(--font-size-sm)' }}>
        Your Customer/Partner discovery registry — the same file the company-review Hermes Skills read and
        write. Approve marks an entry reviewed; the hub note itself is still created by the existing automation.
        Click a row to expand it and edit its fields.
      </p>

      <Field label="Search by name or domain">
        <input className="input" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="e.g. oracle, .ae" />
      </Field>

      {entities && (
        <>
          {renderGroup('Needs review', needsReview)}
          {renderGroup('Companies', companies)}
          {renderGroup('Partners', partners)}
        </>
      )}

      {message && <p className="text-muted">{message}</p>}
      <form onSubmit={handleCreate} className="item-row-actions" style={{ flexWrap: 'wrap', alignItems: 'flex-end' }}>
        <Field label="Company name">
          <input className="input" value={newEntity.name} onChange={(event) => setNewEntity((prev) => ({ ...prev, name: event.target.value }))} />
        </Field>
        <Field label="Type">
          <select
            className="input"
            style={{ width: 'auto' }}
            value={newEntity.section}
            onChange={(event) => setNewEntity((prev) => ({ ...prev, section: event.target.value as 'customer' | 'partner' }))}
          >
            <option value="customer">Company</option>
            <option value="partner">Partner</option>
          </select>
        </Field>
        <Field label="Domain">
          <input className="input" value={newEntity.domain} onChange={(event) => setNewEntity((prev) => ({ ...prev, domain: event.target.value }))} />
        </Field>
        <button type="submit" className="btn btn-primary">Add entity</button>
      </form>
    </>
  );
}
