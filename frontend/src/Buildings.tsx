import { useStore } from './store';

/**
 * Buildings Component
 * Renders server-generated uncorrupted buildings as 3D box meshes.
 * Building data comes from the sim server via init_connection.
 * Coordinates: server {x, y=groundZ} → Three.js {x, height/2, y}
 */
export function Buildings() {
  const buildings = useStore((state) => state.buildings);

  return (
    <group>
      {buildings.map((b) => (
        <mesh
          key={b.id}
          position={[b.x, b.height / 2, b.y]}
          castShadow
          receiveShadow
        >
          <boxGeometry args={[b.width, b.height, b.depth]} />
          <meshStandardMaterial
            color="#5a5048"
            roughness={0.85}
            metalness={0.05}
          />
        </mesh>
      ))}
    </group>
  );
}