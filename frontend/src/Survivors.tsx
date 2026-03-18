import { useMemo } from 'react';
import { useStore } from './store';
import { Human } from './Human';

/**
 * Survivors Component
 * Thermal signatures of survivors in the disaster area
 * These will glow with the Bloom effect for visibility
 */
export function Survivors() {
  const storeSurvivors = useStore(state => state.survivors);
  
  // DEBUG: Log survivor counts
  console.log('[Survivors] Store survivors count:', storeSurvivors.length);
  console.log('[Survivors] Using fallback:', storeSurvivors.length === 0 ? 'YES' : 'NO');
  
  // Enhanced fallback survivors for demo - more survivors at various locations
  const fallbackSurvivors = useMemo(() => [
    // Near command base (easy to spot)
    { position: { x: 8, y: 0.3, z: -5 }, id: 'demo-1', confidence: 0.9, status: 'DETECTED' as const, thermalSignature: true, timestamp: Date.now(), detected_by: 'demo' },
    
    // Behind collapsed building
    { position: { x: -12, y: 0.3, z: 8 }, id: 'demo-2', confidence: 0.9, status: 'DETECTED' as const, thermalSignature: true, timestamp: Date.now(), detected_by: 'demo' },
    
    // Near rubble pile
    { position: { x: 20, y: 0.3, z: 15 }, id: 'demo-3', confidence: 0.9, status: 'DETECTED' as const, thermalSignature: true, timestamp: Date.now(), detected_by: 'demo' },
    
    // Under broken pillar
    { position: { x: -5, y: 0.3, z: -15 }, id: 'demo-4', confidence: 0.9, status: 'DETECTED' as const, thermalSignature: true, timestamp: Date.now(), detected_by: 'demo' },
    
    // Far corner
    { position: { x: 15, y: 0.3, z: -20 }, id: 'demo-5', confidence: 0.9, status: 'DETECTED' as const, thermalSignature: true, timestamp: Date.now(), detected_by: 'demo' },
    
    // Additional survivors - scattered around the area
    { position: { x: -25, y: 0.3, z: -18 }, id: 'demo-6', confidence: 0.85, status: 'DETECTED' as const, thermalSignature: true, timestamp: Date.now(), detected_by: 'demo' },
    { position: { x: 25, y: 0.3, z: -10 }, id: 'demo-7', confidence: 0.8, status: 'DETECTED' as const, thermalSignature: true, timestamp: Date.now(), detected_by: 'demo' },
    { position: { x: -8, y: 0.3, z: 25 }, id: 'demo-8', confidence: 0.88, status: 'DETECTED' as const, thermalSignature: true, timestamp: Date.now(), detected_by: 'demo' },
    { position: { x: 30, y: 0.3, z: 5 }, id: 'demo-9', confidence: 0.75, status: 'DETECTED' as const, thermalSignature: true, timestamp: Date.now(), detected_by: 'demo' },
    { position: { x: -18, y: 0.3, z: -25 }, id: 'demo-10', confidence: 0.82, status: 'DETECTED' as const, thermalSignature: true, timestamp: Date.now(), detected_by: 'demo' },
    
    // Near ruined buildings
    { position: { x: -22, y: 0.3, z: -5 }, id: 'demo-11', confidence: 0.9, status: 'CONFIRMED' as const, thermalSignature: true, timestamp: Date.now(), detected_by: 'demo' },
    { position: { x: 18, y: 0.3, z: -18 }, id: 'demo-12', confidence: 0.78, status: 'DETECTED' as const, thermalSignature: true, timestamp: Date.now(), detected_by: 'demo' },
    
    // Additional hidden survivors (harder to find)
    { position: { x: 5, y: 0.3, z: 28 }, id: 'demo-13', confidence: 0.65, status: 'DETECTED' as const, thermalSignature: true, timestamp: Date.now(), detected_by: 'demo' },
    { position: { x: -28, y: 0.3, z: 12 }, id: 'demo-14', confidence: 0.7, status: 'DETECTED' as const, thermalSignature: true, timestamp: Date.now(), detected_by: 'demo' },
    { position: { x: 12, y: 0.3, z: 25 }, id: 'demo-15', confidence: 0.72, status: 'DETECTED' as const, thermalSignature: true, timestamp: Date.now(), detected_by: 'demo' },
  ], []);
  
  console.log('[Survivors] Fallback survivors count:', fallbackSurvivors.length);
  
  // Use store survivors if available, otherwise use fallback
  const displaySurvivors = storeSurvivors.length > 0 ? storeSurvivors : fallbackSurvivors;
  
  console.log('[Survivors] Displaying survivors count:', displaySurvivors.length);
  console.log('[Survivors] Survivor positions:', displaySurvivors.map(s => `(${s.position.x.toFixed(1)}, ${s.position.z.toFixed(1)})`).join(', '));

  return (
    <group>
      {displaySurvivors.map((survivor) => (
        <Human
          key={survivor.id}
          survivor={survivor}
        />
      ))}
    </group>
  );
}
