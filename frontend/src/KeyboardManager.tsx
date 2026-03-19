import { useEffect } from 'react';
import { useViewStore } from './viewStore';
import { useStore } from './store';

/**
 * KeyboardManager - Centralized keyboard shortcut listener
 */
export function KeyboardManager() {
  const { viewMode, setGlobalView, setFollowView, setPilotView, selectedDroneId } = useViewStore();
  const drones = useStore((state) => state.drones);
  
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't trigger shortcuts if user is typing in an input or textarea
      if (document.activeElement?.tagName === 'INPUT' || document.activeElement?.tagName === 'TEXTAREA') {
        return;
      }

      const key = e.key.toUpperCase();
      const droneList = Object.keys(drones).sort();

      // View Mode Switches
      if (key === 'G' || e.key === 'Escape') {
        setGlobalView();
      } else if (key === 'F') {
        if (selectedDroneId) {
          setFollowView(selectedDroneId);
        } else if (droneList.length > 0) {
          setFollowView(droneList[0]);
        }
      } else if (key === 'P') {
        if (selectedDroneId) {
          setPilotView(selectedDroneId);
        } else if (droneList.length > 0) {
          setPilotView(droneList[0]);
        }
      }

      // Drone Selection (1-9)
      if (e.key >= '1' && e.key <= '9') {
        const index = parseInt(e.key) - 1;
        if (index < droneList.length) {
          const droneId = droneList[index];
          if (viewMode === 'GLOBAL') {
            setFollowView(droneId); // Default to follow when switching from global
          } else if (viewMode === 'FOLLOW') {
            setFollowView(droneId);
          } else if (viewMode === 'PILOT') {
            setPilotView(droneId);
          }
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [viewMode, selectedDroneId, drones, setGlobalView, setFollowView, setPilotView]);

  return null; // Side-effect only component
}

export default KeyboardManager;
