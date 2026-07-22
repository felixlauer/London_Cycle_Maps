import React, { useState } from 'react';
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
import { useIsMobile } from '../../hooks/useMediaQuery';
import { useAuth } from '../../../auth/AuthProvider';
import { useSidebar } from '../SidebarContext';
import {
  avatarStyleForEmail,
  initialsFromEmail,
} from '../avatar';
import '../../routing/routing.css';

/**
 * Top-left routing core.
 * Desktop: fixed-width panel. Mobile: full width with profile pill + side route pill.
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
    endPlaceholder,
    locationAsStart = false,
    routeStart = null,
    favouriteOrder,
    onEditFavourites,
    onMapPickTargetChange,
  } = props;

  const isMobile = useIsMobile();
  const { user, isLoading } = useAuth();
  const { open, toggleSidebar } = useSidebar();
  const [viasCollapsed, setViasCollapsed] = useState(false);

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
    setViasCollapsed(false);
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
    if (isMobile) {
      depart.collapse();
      if (hasVias) setViasCollapsed(true);
    }
    onGetRoute();
  };

  const initials = initialsFromEmail(user?.email);
  const avatarStyle = user ? avatarStyleForEmail(user.email) : undefined;

  return (
    <section
      className="shell-zone shell-zone--routing rc-panel"
      aria-label="Routing"
      data-zone="routing-core"
    >
      <div className="rc-toprow">
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
        <button
          type="button"
          className={[
            'rc-mobile-avatar',
            'md:hidden',
            user ? 'is-signed-in' : 'is-guest',
            isLoading ? 'is-loading' : '',
          ].filter(Boolean).join(' ')}
          aria-label={open ? 'Close profile sidebar' : 'Open profile sidebar'}
          aria-expanded={open}
          onClick={toggleSidebar}
        >
          <span
            className={[
              'rc-mobile-avatar__face',
              user ? 'is-signed-in' : 'is-guest',
              isLoading ? 'is-loading' : '',
            ].filter(Boolean).join(' ')}
            style={avatarStyle}
            aria-hidden
          >
            {!isLoading && (
              <span className={`profile-pill__initials${user ? '' : ' is-guest-label'}`}>
                {user ? initials : 'Guest'}
              </span>
            )}
          </span>
        </button>
      </div>

      <div className="rc-route-stack">
        <div className="rc-wp-with-pill">
          <div className="rc-wp-with-pill__fields">
            <WaypointFields
              theme={theme}
              start={start}
              end={end}
              startLabel={startLabel}
              endLabel={endLabel}
              vias={vias}
              onChangeWaypoints={(next) => {
                setViasCollapsed(false);
                onChangeWaypoints(next);
              }}
              onRemoveVia={(i) => {
                setViasCollapsed(false);
                onRemoveVia(i);
              }}
              onFlyTo={onFlyTo}
              startPlaceholder={startPlaceholder}
              endPlaceholder={endPlaceholder}
              onMapPickTargetChange={onMapPickTargetChange}
              viasCollapsed={isMobile && viasCollapsed}
              onExpandVias={() => setViasCollapsed(false)}
            />
          </div>
          <div className="rc-wp-with-pill__side">
            <GetRouteButton
              start={routeStart ?? start}
              end={end}
              isCalculating={isCalculating}
              canGetRoute={canGetRoute}
              onClick={handleGetRouteClick}
              variant="icon"
            />
          </div>
        </div>

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

        <div className="rc-get-route-desktop">
          <GetRouteButton
            start={routeStart ?? start}
            end={end}
            isCalculating={isCalculating}
            canGetRoute={canGetRoute}
            onClick={handleGetRouteClick}
            variant="full"
          />
        </div>
      </div>
    </section>
  );
}
