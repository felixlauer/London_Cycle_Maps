import React from 'react';
import { Plus } from 'lucide-react';
import ModeBikeSantanderRow from '../../routing/ModeBikeSantanderRow';
import WaypointFields from '../../routing/WaypointFields';
import GetRouteButton from '../../routing/GetRouteButton';
import {
  useDepartAtControl,
  DepartAtTrigger,
  DepartAtPanel,
} from '../../routing/DepartAtControl';
import { MAX_VIAS, BLOCKED } from '../../routing/constants';
import '../../routing/routing.css';

/**
 * Top-left routing core.
 * Fixed-width panel; dropdown menus overlay so the panel never resizes with
 * transient content. The only sanctioned height change is the inline
 * depart-at expansion above Get Route.
 */
export default function RoutingCoreZone(props) {
  const {
    theme,
    profiles,
    activeProfileId,
    onSelectProfile,
    sessionBikeType,
    onSelectBike,
    santanderMode,
    onSantanderChange,
    bikePulse,
    start,
    end,
    startLabel,
    endLabel,
    vias,
    onChangeWaypoints,
    onAddVia,
    onRemoveVia,
    onFlyTo,
    departMode,
    departAtIso,
    onDepartChange,
    onGetRoute,
    isCalculating,
    canGetRoute,
    onBlocked,
    startPlaceholder,
    locationAsStart = false,
    routeStart = null,
    favouriteOrder,
    onEditFavourites,
  } = props;

  const hasVias = (vias || []).length > 0;
  const santanderDisabled = hasVias;
  const departDisabled = santanderMode;
  const atMaxVias = (vias || []).length >= MAX_VIAS;
  const addStopBlocked = santanderMode || atMaxVias;

  const depart = useDepartAtControl({
    mode: departMode,
    departAtIso,
    onChange: onDepartChange,
    disabled: departDisabled,
    onBlocked,
  });

  const handleAddStop = () => {
    if (santanderMode) {
      onBlocked?.(BLOCKED.addStopNeedsNoSantander);
      return;
    }
    if (atMaxVias) {
      onBlocked?.(BLOCKED.addStopMax);
      return;
    }
    onAddVia();
  };

  const handleGetRouteClick = () => {
    if (isCalculating) {
      onBlocked?.(BLOCKED.getRouteBusy);
      return;
    }
    if (!start && !locationAsStart) {
      onBlocked?.(BLOCKED.getRouteNeedsStart);
      return;
    }
    if (!end) {
      onBlocked?.(BLOCKED.getRouteNeedsEnd);
      return;
    }
    if ((vias || []).some((v) => !v.coord)) {
      onBlocked?.(BLOCKED.getRouteNeedsStops);
      return;
    }
    onGetRoute();
  };

  return (
    <section
      className="shell-zone shell-zone--routing rc-panel"
      aria-label="Routing"
      data-zone="routing-core"
    >
      <ModeBikeSantanderRow
        profiles={profiles}
        favouriteOrder={favouriteOrder}
        activeProfileId={activeProfileId}
        onSelectProfile={onSelectProfile}
        sessionBikeType={sessionBikeType}
        onSelectBike={onSelectBike}
        santanderMode={santanderMode}
        onSantanderChange={onSantanderChange}
        santanderDisabled={santanderDisabled}
        bikePulse={bikePulse}
        onBlocked={onBlocked}
        onEditFavourites={onEditFavourites}
      />

      <WaypointFields
        theme={theme}
        start={start}
        end={end}
        startLabel={startLabel}
        endLabel={endLabel}
        vias={vias}
        onChangeWaypoints={onChangeWaypoints}
        onRemoveVia={onRemoveVia}
        onFlyTo={onFlyTo}
        startPlaceholder={startPlaceholder}
      />

      <div className={`rc-subrow${depart.disabled ? ' is-depart-disabled' : ''}`}>
        <DepartAtTrigger
          linkLabel={depart.linkLabel}
          open={depart.open}
          disabled={depart.disabled}
          onToggle={depart.toggleOpen}
        />
        <button
          type="button"
          className={`rc-textlink rc-subrow__add${addStopBlocked ? ' is-disabled' : ''}`}
          aria-disabled={addStopBlocked}
          onClick={handleAddStop}
        >
          <Plus size={14} strokeWidth={2.2} aria-hidden />
          <span>Add stop</span>
        </button>
      </div>

      {depart.open && !depart.disabled && (
        <DepartAtPanel {...depart} />
      )}

      <GetRouteButton
        start={routeStart ?? start}
        end={end}
        isCalculating={isCalculating}
        canGetRoute={canGetRoute}
        onClick={handleGetRouteClick}
      />
    </section>
  );
}
