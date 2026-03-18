import { useStore } from './store';
import type { DroneStatus } from './store';
import { useState } from 'react';

// =============================================================================
// STYLES
// =============================================================================

const overlayContainerStyle: React.CSSProperties = {
  position: 'absolute',
  top: '20px',
  left: '20px',
  zIndex: 1000,
  fontFamily: '"JetBrains Mono", "Fira Code", "Consolas", monospace',
  pointerEvents: 'none',
};

const panelStyle: React.CSSProperties = {
  background: 'linear-gradient(135deg, rgba(0, 20, 25, 0.92) 0%, rgba(0, 10, 18, 0.95) 100%)',
  border: '1px solid rgba(0, 255, 255, 0.35)',
  borderRadius: '6px',
  padding: '16px 20px',
  minWidth: '260px',
  boxShadow: '0 0 30px rgba(0, 255, 255, 0.15), inset 0 0 40px rgba(0, 255, 255, 0.03)',
  backdropFilter: 'blur(10px)',
};

const panelCollapsedStyle: React.CSSProperties = {
  ...panelStyle,
  minWidth: '140px',
  padding: '10px 14px',
};

const headerStyle: React.CSSProperties = {
  color: '#00ffff',
  fontSize: '12px',
  fontWeight: 700,
  letterSpacing: '3px',
  textShadow: '0 0 10px rgba(0, 255, 255, 0.8)',
  marginBottom: '12px',
  paddingBottom: '8px',
  borderBottom: '1px solid rgba(0, 255, 255, 0.2)',
  display: 'flex',
  alignItems: 'center',
  gap: '8px',
};

const collapsedHeaderStyle: React.CSSProperties = {
  ...headerStyle,
  marginBottom: '0',
  paddingBottom: '4px',
};

const scanLineStyle: React.CSSProperties = {
  position: 'absolute',
  top: 0,
  left: 0,
  right: 0,
  bottom: 0,
  background: 'repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0, 255, 255, 0.02) 2px, rgba(0, 255, 255, 0.02) 4px)',
  pointerEvents: 'none',
  borderRadius: '6px',
};

const cornerStyle: React.CSSProperties = {
  position: 'absolute',
  color: 'rgba(0, 255, 255, 0.5)',
  fontSize: '14px',
  fontWeight: 100,
};

const droneItemStyle = (isHovered: boolean): React.CSSProperties => ({
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  padding: '8px 12px',
  margin: '4px 0',
  background: isHovered ? 'rgba(255, 200, 0, 0.15)' : 'rgba(0, 255, 255, 0.05)',
  borderRadius: '4px',
  borderLeft: `2px solid ${isHovered ? '#ffcc00' : 'rgba(0, 255, 255, 0.3)'}`,
  transition: 'all 0.2s ease',
  cursor: 'pointer',
  boxShadow: isHovered ? '0 0 12px rgba(255, 200, 0, 0.3)' : 'none',
  pointerEvents: 'auto',
});

const droneIdStyle = (isHovered: boolean): React.CSSProperties => ({
  color: isHovered ? '#ffcc00' : '#00ffff',
  fontSize: '11px',
  fontWeight: 600,
  letterSpacing: '1px',
  textShadow: isHovered ? '0 0 8px rgba(255, 200, 0, 0.6)' : 'none',
  transition: 'all 0.2s ease',
});

const statusStyle = (status: DroneStatus, isHovered: boolean): React.CSSProperties => {
  const colors: Record<DroneStatus, string> = {
    SCANNING: '#00ff88',
    RETURNING: '#ffaa00',
    IDLE: '#888888',
    SEARCHING: '#ff66aa',
  };
  return {
    color: isHovered ? '#ffdd44' : (colors[status] || '#00ff88'),
    fontSize: '9px',
    fontWeight: 700,
    letterSpacing: '1px',
    textShadow: `0 0 6px ${colors[status] || '#00ff88'}60`,
    transition: 'all 0.2s ease',
  };
};

const batteryStyle = (level: number, isHovered: boolean): React.CSSProperties => {
  let color = '#00ff88';
  if (level < 20) color = '#ff3366';
  else if (level < 50) color = '#ffaa00';
  
  return {
    color: isHovered ? '#ffdd44' : color,
    fontSize: '10px',
    fontWeight: 600,
    textShadow: `0 0 6px ${color}60`,
    display: 'flex',
    alignItems: 'center',
    gap: '4px',
    transition: 'all 0.2s ease',
  };
};

const emptyStyle: React.CSSProperties = {
  color: 'rgba(0, 255, 255, 0.4)',
  fontSize: '11px',
  textAlign: 'center',
  padding: '20px 0',
  fontStyle: 'italic',
};

const dividerStyle: React.CSSProperties = {
  height: '1px',
  background: 'linear-gradient(90deg, transparent, rgba(0, 255, 255, 0.3), transparent)',
  margin: '12px 0',
};

const toggleButtonStyle: React.CSSProperties = {
  position: 'absolute',
  top: '8px',
  right: '8px',
  background: 'rgba(0, 255, 255, 0.1)',
  border: '1px solid rgba(0, 255, 255, 0.3)',
  borderRadius: '4px',
  color: '#00ffff',
  fontSize: '12px',
  cursor: 'pointer',
  padding: '4px 8px',
  pointerEvents: 'auto',
  transition: 'all 0.2s ease',
};

// =============================================================================
// UTILITY FUNCTIONS
// =============================================================================

const getStatusLabel = (status: DroneStatus): string => {
  const labels: Record<DroneStatus, string> = {
    SCANNING: 'ACTIVE',
    RETURNING: 'RETURN',
    IDLE: 'STANDBY',
    SEARCHING: 'SEARCH',
  };
  return labels[status] || status;
};

const getBatteryIcon = (level: number): string => {
  if (level > 80) return '▮▮▮▮';
  if (level > 60) return '▮▮▮▯';
  if (level > 40) return '▮▮▯▯';
  if (level > 20) return '▮▯▯▯';
  return '▯▯▯▯';
};

// =============================================================================
// COMPONENT
// =============================================================================

/**
 * Overlay - Global Status UI Component
 * 
 * Displays a futuristic panel at Top Left showing all active drones
 * with their drone_id, battery level, and operational status.
 * 
 * Reads from Zustand store and updates in real-time.
 * Can be collapsed to show only the header with connection status.
 */
export function Overlay() {
  const drones = useStore((state) => state.drones);
  const connectionStatus = useStore((state) => state.connectionStatus);
  const setHoveredDroneId = useStore((state) => state.setHoveredDroneId);
  const [isCollapsed, setIsCollapsed] = useState(false);
  
  // Local hover state for UI styling (synced with store)
  const [hoveredDroneId, setHoveredDroneIdLocal] = useState<string | null>(null);
  
  // Convert drones object to array for rendering
  const droneList = Object.values(drones);
  
  // Sort by drone_id for consistent ordering
  droneList.sort((a, b) => a.drone_id.localeCompare(b.drone_id));
  
  const toggleCollapse = () => setIsCollapsed(!isCollapsed);
  
  // Handle mouse enter/leave for hover effects
  const handleMouseEnter = (droneId: string) => {
    setHoveredDroneIdLocal(droneId);
    setHoveredDroneId(droneId);
  };
  const handleMouseLeave = () => {
    setHoveredDroneIdLocal(null);
    setHoveredDroneId(null);
  };
  
  return (
    <div style={overlayContainerStyle}>
      <div style={isCollapsed ? panelCollapsedStyle : panelStyle}>
        {/* Scan line effect - only when expanded */}
        {!isCollapsed && <div style={scanLineStyle} />}
        
        {/* Corner brackets */}
        <div style={{ ...cornerStyle, top: '4px', left: '6px' }}>┌</div>
        <div style={{ ...cornerStyle, top: '4px', right: '6px' }}>┐</div>
        {!isCollapsed && (
          <>
            <div style={{ ...cornerStyle, bottom: '4px', left: '6px' }}>└</div>
            <div style={{ ...cornerStyle, bottom: '4px', right: '6px' }}>┘</div>
          </>
        )}
        
        {/* Toggle button */}
        <button 
          style={toggleButtonStyle} 
          onClick={toggleCollapse}
          title={isCollapsed ? 'Expand panel' : 'Collapse panel'}
        >
          {isCollapsed ? '▼' : '▲'}
        </button>
        
        {/* Header */}
        <div style={isCollapsed ? collapsedHeaderStyle : headerStyle}>
          <span style={{ 
            width: '8px', 
            height: '8px', 
            borderRadius: '50%', 
            background: connectionStatus === 'connected' ? '#00ff88' : connectionStatus === 'connecting' ? '#ffaa00' : '#ff3366',
            boxShadow: `0 0 8px ${connectionStatus === 'connected' ? '#00ff88' : connectionStatus === 'connecting' ? '#ffaa00' : '#ff3366'}`,
            display: 'inline-block',
          }} />
          FLIGHT COMMAND
        </div>
        
        {/* Drone list - only show when expanded */}
        {!isCollapsed && (
          <>
            {droneList.length === 0 ? (
              <div style={emptyStyle}>
                ● NO ACTIVE DRONES
              </div>
            ) : (
              <>
                {droneList.map((drone) => {
                  const isHovered = hoveredDroneId === drone.drone_id;
                  return (
                    <div 
                      key={drone.drone_id} 
                      style={droneItemStyle(isHovered)}
                      onMouseEnter={() => handleMouseEnter(drone.drone_id)}
                      onMouseLeave={handleMouseLeave}
                    >
                      <div>
                        <div style={droneIdStyle(isHovered)}>
                          {isHovered && <span style={{ marginRight: '4px' }}>◆</span>}
                          {!isHovered && <span style={{ marginRight: '4px' }}>◇</span>}
                          {drone.drone_id}
                          {isHovered && <span style={{ marginLeft: '8px', color: '#ffcc00', fontSize: '9px' }}>TARGET</span>}
                        </div>
                        <div style={statusStyle(drone.status, isHovered)}>
                          ● {getStatusLabel(drone.status)}
                        </div>
                      </div>
                      <div style={batteryStyle(drone.battery, isHovered)}>
                        {getBatteryIcon(drone.battery)} {drone.battery}%
                      </div>
                    </div>
                  );
                })}
              </>
            )}
            
            <div style={dividerStyle} />
          </>
        )}
        
        {/* Summary - always visible */}
        <div style={{ 
          color: 'rgba(0, 255, 255, 0.6)', 
          fontSize: '10px',
          letterSpacing: '1px',
          display: 'flex',
          justifyContent: 'space-between',
        }}>
          <span>FLEET: {droneList.length}</span>
          <span>LINK: {connectionStatus.toUpperCase()}</span>
        </div>
      </div>
    </div>
  );
}

export default Overlay;
