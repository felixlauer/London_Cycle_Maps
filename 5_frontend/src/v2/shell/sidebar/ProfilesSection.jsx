import React, { useMemo, useState } from 'react';
import { Equal, Pencil, Plus, X } from 'lucide-react';
import { useAuth } from '../../../auth/AuthProvider';
import { BIKE_OPTIONS, PRESET_META } from '../../routing/constants';
import { useSidebar } from '../SidebarContext';

function isCustomProfile(p) {
  if (!p) return false;
  if (p.is_system) return false;
  if (PRESET_META[p.id]) return false;
  if (String(p.id).startsWith('preset_')) return false;
  return true;
}

function bikeLabel(bikeType) {
  return BIKE_OPTIONS.find((b) => b.id === bikeType)?.label || 'Regular';
}

function sortCustoms(customs, order) {
  if (!order?.length) return customs;
  const rank = new Map(order.map((id, i) => [id, i]));
  return [...customs].sort((a, b) => {
    const ra = rank.has(a.id) ? rank.get(a.id) : 9999;
    const rb = rank.has(b.id) ? rank.get(b.id) : 9999;
    if (ra !== rb) return ra - rb;
    return String(a.name || '').localeCompare(String(b.name || ''));
  });
}

/**
 * Profiles — single-line rows; Santander-style status dot on the left = active.
 * Mobile: edit/delete icons only when a row is expanded by tap.
 */
export default function ProfilesSection({
  profiles = [],
  activeProfileId,
  sectionRef,
  onDeleteProfile,
}) {
  const { user, isLoading } = useAuth();
  const { favouriteOrder, setFavouriteOrder, openWizard, openAuthPanel } = useSidebar();
  const [dragId, setDragId] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [expandedId, setExpandedId] = useState(null);

  const customs = useMemo(() => {
    const list = (profiles || []).filter(isCustomProfile);
    return sortCustoms(list, favouriteOrder);
  }, [profiles, favouriteOrder]);

  const onDragStart = (id) => (e) => {
    setDragId(id);
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', id);
  };

  const onDragOver = (e) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
  };

  const onDrop = (targetId) => (e) => {
    e.preventDefault();
    const fromId = dragId || e.dataTransfer.getData('text/plain');
    setDragId(null);
    if (!fromId || fromId === targetId) return;
    const ids = customs.map((p) => p.id);
    const from = ids.indexOf(fromId);
    const to = ids.indexOf(targetId);
    if (from < 0 || to < 0) return;
    const next = [...ids];
    next.splice(from, 1);
    next.splice(to, 0, fromId);
    setFavouriteOrder(next);
  };

  const handleDelete = async (e, profile) => {
    e.stopPropagation();
    e.preventDefault();
    if (!onDeleteProfile || busyId) return;
    const ok = window.confirm(`Delete profile “${profile.name}”? This cannot be undone.`);
    if (!ok) return;
    setBusyId(profile.id);
    try {
      await onDeleteProfile(profile.id);
    } finally {
      setBusyId(null);
    }
  };

  const toggleExpanded = (id) => {
    setExpandedId((cur) => (cur === id ? null : id));
  };

  return (
    <section
      className="sb-section sb-profiles"
      ref={sectionRef}
      aria-labelledby="sb-profiles-heading"
    >
      <div className="sb-section__head">
        <h2 id="sb-profiles-heading" className="sb-section__title">Riding profiles</h2>
        <p className="sb-section__hint">Top 3 appear as favourites in quick settings</p>
      </div>

      {isLoading ? (
        <div className="sb-skeleton sb-skeleton--block" />
      ) : !user ? (
        <p className="sb-empty">
          <button
            type="button"
            className="sb-text-link"
            onClick={() => openAuthPanel('login')}
          >
            Sign in
          </button>
          {' '}
          to create a profile.
        </p>
      ) : (
        <>
          {customs.length === 0 ? (
            <p className="sb-empty">No custom profiles yet.</p>
          ) : (
            <>
              {customs.length > 3 && (
                <p className="sb-section__band">Quick picks</p>
              )}
              <div className="sb-card">
                {customs.map((p, index) => {
                  const quick = index < 3;
                  const showMoreBand = index === 3;
                  const active = p.id === activeProfileId;
                  const expanded = expandedId === p.id;
                  return (
                    <React.Fragment key={p.id}>
                      {showMoreBand && (
                        <>
                          <div className="sb-card__divider" aria-hidden />
                          <div className="sb-card__band">More profiles</div>
                        </>
                      )}
                      {index > 0 && index !== 3 && (
                        <div className="sb-card__divider" aria-hidden />
                      )}
                      <div
                        className={[
                          'sb-card__row',
                          'sb-profile-row',
                          quick ? 'is-quick' : '',
                          active ? 'is-active' : '',
                          expanded ? 'is-expanded' : '',
                          dragId === p.id ? 'is-dragging' : '',
                        ].filter(Boolean).join(' ')}
                        draggable
                        onDragStart={onDragStart(p.id)}
                        onDragOver={onDragOver}
                        onDrop={onDrop(p.id)}
                        onDragEnd={() => setDragId(null)}
                        onClick={() => toggleExpanded(p.id)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            toggleExpanded(p.id);
                          }
                        }}
                        role="button"
                        tabIndex={0}
                        aria-expanded={expanded}
                      >
                        <span className="sb-profile-row__lead" aria-hidden>
                          <span
                            className={`sb-profile-row__dot${active ? ' is-on' : ''}`}
                          />
                          {quick ? (
                            <span className="sb-badge">{`C${index + 1}`}</span>
                          ) : (
                            <span className="sb-badge sb-badge--spacer" />
                          )}
                        </span>
                        <span className="sb-profile-row__name">{p.name}</span>
                        <span className="sb-profile-row__bike">{bikeLabel(p.bike_type)}</span>
                        <div className="sb-profile-row__actions">
                          <button
                            type="button"
                            className="sb-profile-row__action"
                            title="Edit profile"
                            aria-label={`Edit ${p.name}`}
                            onClick={(e) => {
                              e.stopPropagation();
                              e.preventDefault();
                              openWizard({ profileId: p.id });
                            }}
                          >
                            <Pencil size={14} strokeWidth={2.2} aria-hidden />
                          </button>
                          <button
                            type="button"
                            className="sb-profile-row__action is-danger"
                            title="Delete profile"
                            aria-label={`Delete ${p.name}`}
                            disabled={busyId === p.id}
                            onClick={(e) => handleDelete(e, p)}
                          >
                            <X size={15} strokeWidth={2.25} aria-hidden />
                          </button>
                        </div>
                        <button
                          type="button"
                          className="sb-profile-row__grip"
                          aria-label={`Reorder ${p.name}`}
                          tabIndex={-1}
                          onClick={(e) => e.stopPropagation()}
                        >
                          <Equal size={15} strokeWidth={2.2} aria-hidden />
                        </button>
                      </div>
                    </React.Fragment>
                  );
                })}
              </div>
            </>
          )}

          <div className="sb-card sb-create-card">
            <button
              type="button"
              className="sb-card__row sb-create-profile"
              onClick={() => openWizard()}
            >
              <span className="sb-create-profile__icon" aria-hidden>
                <Plus size={15} strokeWidth={2.4} />
              </span>
              <span className="sb-card__label">Create profile</span>
            </button>
          </div>
        </>
      )}
    </section>
  );
}
