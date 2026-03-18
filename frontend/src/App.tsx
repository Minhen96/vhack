import { useEffect } from 'react';
import { Scene } from './Scene';
import { Overlay } from './Overlay';
import { connectWebSocket, disconnectWebSocket, useStore } from './store';
import './App.css';

export default function App() {
  const connectionStatus = useStore((state) => state.connectionStatus);
  const survivors = useStore((state) => state.survivors);

  // Connect to WebSocket on mount, disconnect on unmount
  useEffect(() => {
    connectWebSocket();
    return () => {
      disconnectWebSocket();
    };
  }, []);

  // Get status color and label
  const getStatusConfig = () => {
    switch (connectionStatus) {
      case 'connected':
        return { color: '#00ff88', label: 'CONNECTED', pulse: false };
      case 'connecting':
        return { color: '#ffaa00', label: 'CONNECTING', pulse: true };
      case 'error':
        return { color: '#ff3366', label: 'ERROR', pulse: false };
      default:
        return { color: '#666677', label: 'DISCONNECTED', pulse: false };
    }
  };

  const statusConfig = getStatusConfig();

  return (
    <div style={{ width: '100vw', height: '100vh', background: '#0a0a0f', position: 'relative' }}>
      {/* Global Drone Status Overlay */}
      <Overlay />

      {/* HUD Overlay */}
      <div className="hud-container">
        {/* Header */}
        <div className="hud-header">Command Center</div>

        {/* Connection Status */}
        <div className="hud-row">
          <span className="hud-label">LINK</span>
          <div className="hud-row" style={{ gap: 8, marginBottom: 0 }}>
            <span
              className={`status-indicator ${statusConfig.pulse ? 'pulse' : ''}`}
              style={{ background: statusConfig.color, color: statusConfig.color }}
            />
            <span className="status-text" style={{ color: statusConfig.color }}>
              {statusConfig.label}
            </span>
          </div>
        </div>

        {/* Survivors Count */}
        <div className="hud-row">
          <span className="hud-label">VITALS</span>
          <span className="status-text" style={{ color: survivors.length > 0 ? '#ffaa00' : '#00ff88' }}>
            {survivors.length} DETECTED
          </span>
        </div>

        {/* Scan line effect */}
        <div className="scan-lines" />
      </div>

      <Scene />
    </div>
  );
}
