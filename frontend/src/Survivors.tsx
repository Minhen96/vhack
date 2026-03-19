import { useStore } from './store';
import { Human } from './Human';

/**
 * Survivors Component
 * Thermal signatures of survivors in the disaster area
 * These will glow with the Bloom effect for visibility
 */
export function Survivors() {
  const storeSurvivors = useStore(state => state.survivors);
  const displaySurvivors = storeSurvivors;

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
