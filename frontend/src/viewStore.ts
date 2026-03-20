import { create } from 'zustand';

export type ViewMode = 'GLOBAL' | 'FOLLOW' | 'PILOT';

interface ViewState {
  viewMode: ViewMode;
  selectedDroneId: string | null;
  highDensity: boolean;
  isTerminalOpen: boolean;
  resetViewTrigger: number;

  // Actions
  setGlobalView: () => void;
  setFollowView: (droneId: string) => void;
  setPilotView: (droneId: string) => void;
  setSelectedDroneId: (id: string | null) => void;
  toggleHighDensity: () => void;
  setTerminalOpen: (open: boolean) => void;
  triggerResetView: () => void;
}

export const useViewStore = create<ViewState>((set) => ({
  viewMode: 'GLOBAL',
  selectedDroneId: null,
  highDensity: false,
  isTerminalOpen: false,
  resetViewTrigger: 0,

  setGlobalView: () => set({ 
    viewMode: 'GLOBAL', 
    selectedDroneId: null 
  }),

  setFollowView: (droneId: string) => set({ 
    viewMode: 'FOLLOW', 
    selectedDroneId: droneId 
  }),

  setPilotView: (droneId: string) => set({ 
    viewMode: 'PILOT', 
    selectedDroneId: droneId 
  }),

  setSelectedDroneId: (id: string | null) => set({ 
    selectedDroneId: id 
  }),

  toggleHighDensity: () => set((state) => ({ 
    highDensity: !state.highDensity 
  })),

  setTerminalOpen: (open: boolean) => set({
    isTerminalOpen: open
  }),

  triggerResetView: () => set((state) => ({
    resetViewTrigger: state.resetViewTrigger + 1,
    viewMode: 'GLOBAL',
    selectedDroneId: null,
  })),
}));

export default useViewStore;
