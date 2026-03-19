import { create } from 'zustand';

export type ViewMode = 'GLOBAL' | 'FOLLOW' | 'PILOT';

interface ViewState {
  viewMode: ViewMode;
  selectedDroneId: string | null;
  
  // Actions
  setGlobalView: () => void;
  setFollowView: (droneId: string) => void;
  setPilotView: (droneId: string) => void;
  setSelectedDroneId: (id: string | null) => void;
}

export const useViewStore = create<ViewState>((set) => ({
  viewMode: 'GLOBAL',
  selectedDroneId: null,

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
}));

export default useViewStore;
