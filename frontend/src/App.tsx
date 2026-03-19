import { useEffect } from 'react';
import { Scene } from './Scene';
import { Overlay } from './Overlay';
import { connectWebSocket, disconnectWebSocket } from './store';
import { KeyboardManager } from './KeyboardManager';
import './App.css';

export default function App() {
  // Connect to WebSocket on mount, disconnect on unmount
  useEffect(() => {
    connectWebSocket();
    return () => {
      disconnectWebSocket();
    };
  }, []);

  return (
    <div className="w-screen h-screen relative overflow-hidden">
      <KeyboardManager />
      
      {/* Global Mission Control Dashboard */}
      <Overlay />
      
      {/* 3D Simulation Canvas */}
      <Scene />
    </div>
  );
}
