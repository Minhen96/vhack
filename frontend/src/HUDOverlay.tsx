import React from 'react';
import { useViewStore } from './viewStore';
import { useStore } from './store';

/**
 * HUDOverlay - Digital Tactical Interface
 * Renders when in FOLLOW or PILOT modes.
 */
export function HUDOverlay() {
  const viewMode = useViewStore((state) => state.viewMode);
  const selectedDroneId = useViewStore((state) => state.selectedDroneId);
  const setGlobalView = useViewStore((state) => state.setGlobalView);
  const drones = useStore((state) => state.drones);

  const drone = selectedDroneId ? drones[selectedDroneId] : null;

  if (viewMode === 'GLOBAL' || !drone) return null;

  const altitude = drone.position.y.toFixed(1);
  const azimuth = drone.spherical.azimuth.toFixed(0);
  const battery = drone.battery;
  const status = drone.status;

  return (
    <div style={hudContainerStyle}>
      {/* Scanline Effect */}
      <div style={scanLineStyle} />
      
      {/* Top Compass Tape */}
      <div style={compassTapeStyle}>
        <div style={compassContainerStyle}>
          <div style={compassMarkerStyle}>▼</div>
          <div style={compassValueStyle}>{azimuth}°</div>
          <div style={compassTapeTicksStyle(drone.spherical.azimuth)}>
            {[0, 45, 90, 135, 180, 225, 270, 315].map((deg) => (
              <div key={deg} style={tickStyle}>
                <div style={tickLineStyle} />
                <div style={tickTextStyle}>{deg === 0 ? 'N' : deg === 90 ? 'E' : deg === 180 ? 'S' : deg === 270 ? 'W' : deg}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Left Altitude Ladder */}
      <div style={altitudeLadderStyle}>
        <div style={ladderContainerStyle}>
          <div style={ladderPointerStyle}>► {altitude}m</div>
          <div style={ladderTicksStyle(drone.position.y)}>
            {[40, 30, 20, 10, 0].map((h) => (
              <div key={h} style={altitudeTickStyle}>
                <span>- {h}</span>
              </div>
            ))}
          </div>
          <div style={ladderLabelStyle}>ALT</div>
        </div>
      </div>

      {/* Center Reticle (only PILOT) */}
      {viewMode === 'PILOT' && (
        <div style={reticleStyle}>
          <div style={reticleCircleStyle} />
          <div style={reticleHorizontalStyle} />
          <div style={reticleVerticalStyle} />
          <div style={reticleCornerStyle('top', 'left')} />
          <div style={reticleCornerStyle('top', 'right')} />
          <div style={reticleCornerStyle('bottom', 'left')} />
          <div style={reticleCornerStyle('bottom', 'right')} />
        </div>
      )}

      {/* Right Telemetry */}
      <div style={rightTelemetryStyle}>
        <div style={telemetryBoxStyle}>
          <div style={telemetryHeaderStyle}>DRONE_ID: {selectedDroneId}</div>
          <div style={telemetryLineStyle}>STATUS: {status}</div>
          <div style={telemetryLineStyle}>BATT: {battery}%</div>
          <div style={telemetryLineStyle}>MODE: {viewMode}</div>
        </div>
      </div>

      {/* Bottom Controls / Exit */}
      <div style={bottomControlsStyle}>
        <button style={exitButtonStyle} onClick={setGlobalView}>
          EXIT TO COMMAND [ESC]
        </button>
      </div>

      {/* Glitch/Static Overlays */}
      <div style={vignetteStyle} />
    </div>
  );
}

// =============================================================================
// STYLES
// =============================================================================

const hudContainerStyle: React.CSSProperties = {
  position: 'absolute',
  top: 0,
  left: 0,
  width: '100vw',
  height: '100vh',
  pointerEvents: 'none',
  zIndex: 1000,
  fontFamily: '"JetBrains Mono", monospace',
  color: '#00ffff',
  overflow: 'hidden',
};

const scanLineStyle: React.CSSProperties = {
  position: 'absolute',
  top: 0,
  left: 0,
  right: 0,
  bottom: 0,
  background: 'repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0, 255, 255, 0.03) 2px, rgba(0, 255, 255, 0.03) 4px)',
  zIndex: 10,
};

const compassTapeStyle: React.CSSProperties = {
  position: 'absolute',
  top: '40px',
  left: '50%',
  transform: 'translateX(-50%)',
  width: '400px',
  height: '50px',
  border: '1px solid rgba(0, 255, 255, 0.3)',
  background: 'rgba(0, 10, 20, 0.4)',
  display: 'flex',
  justifyContent: 'center',
  overflow: 'hidden',
};

const compassContainerStyle: React.CSSProperties = {
  position: 'relative',
  width: '100%',
};

const compassMarkerStyle: React.CSSProperties = {
  position: 'absolute',
  top: '-15px',
  left: '50%',
  transform: 'translateX(-50%)',
  fontSize: '10px',
};

const compassValueStyle: React.CSSProperties = {
  position: 'absolute',
  top: '5px',
  left: '50%',
  transform: 'translateX(-50%)',
  fontSize: '14px',
  fontWeight: 'bold',
};

const compassTapeTicksStyle = (azimuth: number): React.CSSProperties => ({
  display: 'flex',
  gap: '40px',
  position: 'absolute',
  bottom: '5px',
  transition: 'transform 0.1s linear',
  transform: `translateX(calc(-${azimuth * 1.11}px + 200px))`,
});

const tickStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  width: '20px',
};

const tickLineStyle: React.CSSProperties = {
  width: '1px',
  height: '8px',
  background: '#00ffff',
};

const tickTextStyle: React.CSSProperties = {
  fontSize: '9px',
  marginTop: '2px',
};

const altitudeLadderStyle: React.CSSProperties = {
  position: 'absolute',
  left: '60px',
  top: '50%',
  transform: 'translateY(-50%)',
  width: '80px',
  height: '300px',
  borderLeft: '1px solid rgba(0, 255, 255, 0.3)',
  background: 'rgba(0, 10, 20, 0.2)',
};

const ladderContainerStyle: React.CSSProperties = {
  position: 'relative',
  height: '100%',
};

const ladderPointerStyle: React.CSSProperties = {
  position: 'absolute',
  left: '-10px',
  top: '50%',
  transform: 'translateY(-50%)',
  background: '#00ffff',
  color: '#000',
  padding: '2px 6px',
  fontSize: '12px',
  fontWeight: 'bold',
  whiteSpace: 'nowrap',
};

const ladderTicksStyle = (alt: number): React.CSSProperties => ({
  position: 'absolute',
  top: '50%',
  transform: `translateY(${alt * 10 - 150}px)`,
  display: 'flex',
  flexDirection: 'column',
  gap: '80px',
  transition: 'transform 0.1s ease-out',
});


const altitudeTickStyle: React.CSSProperties = {
  fontSize: '10px',
};

const ladderLabelStyle: React.CSSProperties = {
  position: 'absolute',
  bottom: '-25px',
  left: '0',
  fontSize: '10px',
  letterSpacing: '2px',
};

const reticleStyle: React.CSSProperties = {
  position: 'absolute',
  top: '50%',
  left: '50%',
  transform: 'translate(-50%, -50%)',
  width: '200px',
  height: '200px',
};

const reticleCircleStyle: React.CSSProperties = {
  position: 'absolute',
  top: '50%',
  left: '50%',
  transform: 'translate(-50%, -50%)',
  width: '4px',
  height: '4px',
  background: '#00ffff',
  borderRadius: '50%',
};

const reticleHorizontalStyle: React.CSSProperties = {
  position: 'absolute',
  top: '50%',
  left: '50%',
  transform: 'translate(-50%, -50%)',
  width: '40px',
  height: '1px',
  background: 'rgba(0, 255, 255, 0.5)',
};

const reticleVerticalStyle: React.CSSProperties = {
  position: 'absolute',
  top: '50%',
  left: '50%',
  transform: 'translate(-50%, -50%)',
  width: '1px',
  height: '40px',
  background: 'rgba(0, 255, 255, 0.5)',
};

const reticleCornerStyle = (v: 'top' | 'bottom', h: 'left' | 'right'): React.CSSProperties => ({
  position: 'absolute',
  [v]: 0,
  [h]: 0,
  width: '20px',
  height: '20px',
  borderTop: v === 'top' ? '2px solid #00ffff' : 'none',
  borderBottom: v === 'bottom' ? '2px solid #00ffff' : 'none',
  borderLeft: h === 'left' ? '2px solid #00ffff' : 'none',
  borderRight: h === 'right' ? '2px solid #00ffff' : 'none',
  opacity: 0.6,
});

const rightTelemetryStyle: React.CSSProperties = {
  position: 'absolute',
  right: '60px',
  top: '50%',
  transform: 'translateY(-50%)',
};

const telemetryBoxStyle: React.CSSProperties = {
  background: 'rgba(0, 20, 30, 0.6)',
  border: '1px solid rgba(0, 255, 255, 0.3)',
  padding: '16px',
  borderRadius: '4px',
  minWidth: '180px',
};

const telemetryHeaderStyle: React.CSSProperties = {
  fontSize: '11px',
  fontWeight: 'bold',
  borderBottom: '1px solid rgba(0, 255, 255, 0.2)',
  paddingBottom: '8px',
  marginBottom: '8px',
};

const telemetryLineStyle: React.CSSProperties = {
  fontSize: '10px',
  margin: '4px 0',
  letterSpacing: '1px',
};

const bottomControlsStyle: React.CSSProperties = {
  position: 'absolute',
  bottom: '40px',
  left: '50%',
  transform: 'translateX(-50%)',
  pointerEvents: 'auto',
};

const exitButtonStyle: React.CSSProperties = {
  background: 'rgba(255, 50, 50, 0.15)',
  border: '1px solid rgba(255, 50, 50, 0.5)',
  color: '#ff5555',
  padding: '8px 20px',
  fontSize: '11px',
  letterSpacing: '2px',
  cursor: 'pointer',
  transition: 'all 0.2s',
  textShadow: '0 0 8px rgba(255, 55, 55, 0.5)',
};

const vignetteStyle: React.CSSProperties = {
  position: 'absolute',
  top: 0,
  left: 0,
  right: 0,
  bottom: 0,
  background: 'radial-gradient(circle, transparent 40%, rgba(0, 10, 20, 0.4) 100%)',
};

export default HUDOverlay;
