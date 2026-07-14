/**
 * Test Mode drawer (visible only when the master Test Mode toggle is ON).
 *
 * Level 1 (this panel existing): Supabase is bypassed — profiles come from the
 * local JSON store and behave normally via the ProfileMenu.
 * Level 2 (nested "Manual weight overrides" sub-toggle): profile selection is
 * bypassed entirely and the raw weight toggles below drive /route directly.
 */
import React from 'react';
import './topbar.css';

const toggleStyle = {
  container: { display: 'flex', justifyContent: 'space-between', marginBottom: '12px', cursor: 'pointer' },
  switch: { position: 'relative', width: '36px', height: '18px', marginLeft: '10px' },
  slider: (isOn, activeColor, bgColor) => ({
    position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
    backgroundColor: isOn ? activeColor : bgColor, transition: '.3s', borderRadius: '18px',
  }),
  knob: (isOn) => ({
    position: 'absolute', height: '14px', width: '14px', left: '2px', bottom: '2px',
    backgroundColor: 'white', transition: '.3s', borderRadius: '50%',
    transform: isOn ? 'translateX(18px)' : 'translateX(0)',
  }),
};

const Toggle = ({ label, isOn, setIsOn, activeColor, theme }) => (
  <div style={toggleStyle.container} onClick={() => setIsOn(!isOn)}>
    <span style={{ fontSize: '13px', fontWeight: 'bold', color: theme.textMain }}>{label}</span>
    <div style={toggleStyle.switch}>
      <div style={toggleStyle.slider(isOn, activeColor, theme.toggleInactive)}>
        <div style={toggleStyle.knob(isOn)} />
      </div>
    </div>
  </div>
);

export default function TestModePanel({
  theme,
  manualWeightsMode,
  setManualWeightsMode,
  toggles,
  setters,
  onRefreshTfl,
  onRefreshTomtom,
  tflDisruptionStatus,
  tomtomDisruptionStatus,
}) {
  const refreshBtnStyle = {
    padding: '4px 10px', fontSize: '11px', background: theme.toggleInactive,
    border: `1px solid ${theme.border}`, borderRadius: '4px', cursor: 'pointer', color: theme.textMain,
  };

  return (
    <div className="ui-panel testmode-panel">
      <h4 className="testmode-panel__title">Test Mode</h4>
      <p className="testmode-panel__subtitle">
        Local profiles, no Supabase. Profiles and the wizard keep working from the local JSON file.
      </p>

      <div
        className="testmode-panel__subtoggle"
        onClick={() => setManualWeightsMode(!manualWeightsMode)}
        role="switch"
        aria-checked={manualWeightsMode}
      >
        <span className="testmode-panel__subtoggle-label">Manual weight overrides</span>
        <div style={toggleStyle.switch}>
          <div style={toggleStyle.slider(manualWeightsMode, '#7b1fa2', theme.toggleInactive)}>
            <div style={toggleStyle.knob(manualWeightsMode)} />
          </div>
        </div>
      </div>

      {manualWeightsMode ? (
        <>
          <div className="testmode-panel__subtoggle-hint">
            Profile selection is bypassed — the raw toggles below drive routing.
          </div>
          <div className="testmode-panel__group">Safety</div>
          <Toggle label="Avoid Accidents" isOn={toggles.useSafetyRouting} setIsOn={setters.setUseSafetyRouting} activeColor={theme.routeOptimized} theme={theme} />
          <Toggle label="Night Mode" isOn={toggles.useLighting} setIsOn={setters.setUseLighting} activeColor="#1976D2" theme={theme} />
          <Toggle label="TfL network (incl. quietways)" isOn={toggles.useTflCycleway} setIsOn={setters.setUseTflCycleway} activeColor="#1976D2" theme={theme} />
          <Toggle label="Car-free corridors" isOn={toggles.useVehicularFree} setIsOn={setters.setUseVehicularFree} activeColor="#7B1FA2" theme={theme} />
          <Toggle label="Speed stress" isOn={toggles.useSpeedStress} setIsOn={setters.setUseSpeedStress} activeColor="#E65100" theme={theme} />
          <Toggle label="Traffic signals" isOn={toggles.useSignals} setIsOn={setters.setUseSignals} activeColor="#F57C00" theme={theme} />
          <Toggle label="Barriers" isOn={toggles.useBarriers} setIsOn={setters.setUseBarriers} activeColor="#5D4037" theme={theme} />
          <Toggle label="Junction danger" isOn={toggles.useJunctionDanger} setIsOn={setters.setUseJunctionDanger} activeColor="#795548" theme={theme} />
          <Toggle label="Live TfL Disruptions" isOn={toggles.useTflLive} setIsOn={setters.setUseTflLive} activeColor={theme.disruptionColor} theme={theme} />
          {toggles.useTflLive && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px', marginLeft: '12px' }}>
              <button type="button" onClick={onRefreshTfl} style={refreshBtnStyle}>Refresh</button>
              <span style={{ fontSize: '10px', color: theme.textSub }}>{tflDisruptionStatus || 'Not loaded'}</span>
            </div>
          )}
          <Toggle label="Live TomTom Disruptions" isOn={toggles.useTomtomLive} setIsOn={setters.setUseTomtomLive} activeColor={theme.disruptionColor} theme={theme} />
          {toggles.useTomtomLive && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px', marginLeft: '12px' }}>
              <button type="button" onClick={onRefreshTomtom} style={refreshBtnStyle}>Refresh</button>
              <span style={{ fontSize: '10px', color: theme.textSub }}>{tomtomDisruptionStatus || 'Not loaded'}</span>
            </div>
          )}
          <div className="testmode-panel__group">Comfort</div>
          <Toggle label="Road Bike (Smooth)" isOn={toggles.useRoadBike} setIsOn={setters.setUseRoadBike} activeColor="#4CAF50" theme={theme} />
          <Toggle label="Flat Route" isOn={toggles.useHillRouting} setIsOn={setters.setUseHillRouting} activeColor="#FFA500" theme={theme} />
          <Toggle label="Traffic calming" isOn={toggles.useCalming} setIsOn={setters.setUseCalming} activeColor="#00838F" theme={theme} />
          <div className="testmode-panel__group">Scenery</div>
          <Toggle label="Green / scenic" isOn={toggles.useGreen} setIsOn={setters.setUseGreen} activeColor="#00796B" theme={theme} />
        </>
      ) : (
        <div className="testmode-panel__subtoggle-hint">
          Off — routing uses the profile selected in the top-bar menu (from the local store).
        </div>
      )}
    </div>
  );
}
