import { useMemo } from 'react';
import * as THREE from 'three';

/**
 * CommandBase - Realistic Helipad Component
 * 
 * Creates a command base / helipad for the search and rescue operation
 * positioned at [0, 0.1, 40] serving as the "Safe Zone" in the sunlight
 * 
 * Features:
 * - Procedural helipad with CylinderGeometry base
 * - "H" marking for helicopter landing zone
 * - Yellow/orange safety perimeter markings
 * - Emergency equipment props (crates, radio equipment, batteries)
 * - SpotLight creating a distinct "Safe Zone" effect
 * - Shadow casting enabled
 */

export function CommandBase() {
  // Generate procedural texture for the helipad surface
  const helipadTexture = useMemo(() => {
    const canvas = document.createElement('canvas');
    canvas.width = 256;
    canvas.height = 256;
    const ctx = canvas.getContext('2d')!;

    // Base concrete/asphalt color
    ctx.fillStyle = '#3d3d3d';
    ctx.fillRect(0, 0, 256, 256);

    // Add noise for weathered texture
    for (let i = 0; i < 3000; i++) {
      const x = Math.random() * 256;
      const y = Math.random() * 256;
      const gray = Math.random() * 30 + 40;
      ctx.fillStyle = `rgb(${gray}, ${gray}, ${gray})`;
      ctx.fillRect(x, y, 2, 2);
    }

    // Add some cracks
    ctx.strokeStyle = '#2a2a2a';
    ctx.lineWidth = 1;
    for (let i = 0; i < 5; i++) {
      ctx.beginPath();
      ctx.moveTo(Math.random() * 256, Math.random() * 256);
      ctx.lineTo(Math.random() * 256, Math.random() * 256);
      ctx.stroke();
    }

    const texture = new THREE.CanvasTexture(canvas);
    return texture;
  }, []);

  // Generate texture for crates
  const crateTexture = useMemo(() => {
    const canvas = document.createElement('canvas');
    canvas.width = 64;
    canvas.height = 64;
    const ctx = canvas.getContext('2d')!;

    // Wood/box color
    ctx.fillStyle = '#8B7355';
    ctx.fillRect(0, 0, 64, 64);

    // Add wood grain
    for (let i = 0; i < 20; i++) {
      ctx.strokeStyle = '#6B5344';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(0, i * 3 + Math.random() * 2);
      ctx.lineTo(64, i * 3 + Math.random() * 2);
      ctx.stroke();
    }

    // Add border
    ctx.strokeStyle = '#5a4535';
    ctx.lineWidth = 3;
    ctx.strokeRect(2, 2, 60, 60);

    const texture = new THREE.CanvasTexture(canvas);
    texture.wrapS = THREE.RepeatWrapping;
    texture.wrapT = THREE.RepeatWrapping;
    return texture;
  }, []);

  return (
    <group position={[0, 0.1, 40]}>
      {/* ========== HELIPAD PLATFORM ========== */}
      
      {/* Main helipad disk - Concrete base */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} receiveShadow castShadow>
        <cylinderGeometry args={[6, 6, 0.15, 32]} />
        <meshStandardMaterial
          map={helipadTexture}
          color="#4a4a4a"
          roughness={0.85}
          metalness={0.1}
        />
      </mesh>

      {/* Inner circle - Slightly raised for visual distinction */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.01, 0]} receiveShadow>
        <cylinderGeometry args={[5.5, 5.5, 0.05, 32]} />
        <meshStandardMaterial
          color="#3a3a3a"
          roughness={0.8}
          metalness={0.05}
        />
      </mesh>

      {/* Orange/Yellow safety perimeter - Outer ring */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.08, 0]} receiveShadow>
        <ringGeometry args={[5.7, 5.9, 32]} />
        <meshStandardMaterial
          color="#ff6b00"
          roughness={0.6}
          metalness={0.1}
          side={THREE.DoubleSide}
        />
      </mesh>

      {/* Secondary safety ring */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.08, 0]} receiveShadow>
        <ringGeometry args={[5.2, 5.35, 32]} />
        <meshStandardMaterial
          color="#ff6b00"
          roughness={0.6}
          metalness={0.1}
          side={THREE.DoubleSide}
        />
      </mesh>

      {/* "H" Marking - Main helipad identifier */}
      <group position={[0, 0.16, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        {/* Vertical bar of H */}
        <mesh position={[-0.6, 0, 0]} receiveShadow>
          <planeGeometry args={[0.5, 2.5]} />
          <meshStandardMaterial
            color="#ffffff"
            roughness={0.5}
            metalness={0.1}
          />
        </mesh>
        {/* Vertical bar of H (right side) */}
        <mesh position={[0.6, 0, 0]} receiveShadow>
          <planeGeometry args={[0.5, 2.5]} />
          <meshStandardMaterial
            color="#ffffff"
            roughness={0.5}
            metalness={0.1}
          />
        </mesh>
        {/* Horizontal bar of H */}
        <mesh position={[0, -0.3, 0.01]} receiveShadow>
          <planeGeometry args={[2.2, 0.5]} />
          <meshStandardMaterial
            color="#ffffff"
            roughness={0.5}
            metalness={0.1}
          />
        </mesh>
      </group>

      {/* Corner safety markings (yellow triangles) */}
      {[0, 90, 180, 270].map((angle, i) => {
        const rad = (angle * Math.PI) / 180;
        const radius = 5.5;
        return (
          <mesh
            key={i}
            position={[Math.cos(rad) * radius, 0.12, Math.sin(rad) * radius]}
            rotation={[-Math.PI / 2, 0, rad]}
            receiveShadow
          >
            <ringGeometry args={[0.3, 0.5, 3]} />
            <meshStandardMaterial
              color="#ffd700"
              roughness={0.5}
              metalness={0.1}
              side={THREE.DoubleSide}
            />
          </mesh>
        );
      })}

      {/* ========== EMERGENCY EQUIPMENT PROPS ========== */}

      {/* Large Supply Crate 1 */}
      <group position={[-4, 0.15, 3]}>
        <mesh castShadow receiveShadow>
          <boxGeometry args={[1.2, 0.8, 0.8]} />
          <meshStandardMaterial
            map={crateTexture}
            color="#a08060"
            roughness={0.9}
            metalness={0.0}
          />
        </mesh>
        {/* Crate bands */}
        <mesh position={[0, 0, 0.41]} castShadow>
          <boxGeometry args={[1.22, 0.82, 0.02]} />
          <meshStandardMaterial color="#4a4a4a" roughness={0.7} metalness={0.3} />
        </mesh>
      </group>

      {/* Large Supply Crate 2 */}
      <group position={[-4.5, 0.15, 4]}>
        <mesh castShadow receiveShadow>
          <boxGeometry args={[1, 0.6, 1]} />
          <meshStandardMaterial
            map={crateTexture}
            color="#a08060"
            roughness={0.9}
            metalness={0.0}
          />
        </mesh>
      </group>

      {/* Medical Supply Crate (white/red) */}
      <group position={[4.2, 0.15, 2.5]}>
        <mesh castShadow receiveShadow>
          <boxGeometry args={[0.8, 0.6, 0.5]} />
          <meshStandardMaterial
            color="#e8e8e8"
            roughness={0.8}
            metalness={0.1}
          />
        </mesh>
        {/* Red cross */}
        <mesh position={[0, 0, 0.26]} rotation={[-Math.PI / 2, 0, 0]}>
          <planeGeometry args={[0.5, 0.15]} />
          <meshStandardMaterial color="#cc0000" roughness={0.5} />
        </mesh>
        <mesh position={[0, 0, 0.26]} rotation={[-Math.PI / 2, 0, 0]}>
          <planeGeometry args={[0.15, 0.5]} />
          <meshStandardMaterial color="#cc0000" roughness={0.5} />
        </mesh>
      </group>

      {/* Radio Equipment Box */}
      <group position={[4, 0.15, -2]}>
        {/* Main box */}
        <mesh castShadow receiveShadow>
          <boxGeometry args={[0.7, 0.5, 0.5]} />
          <meshStandardMaterial
            color="#2a2a2a"
            roughness={0.6}
            metalness={0.4}
          />
        </mesh>
        {/* Antenna */}
        <mesh position={[0.2, 0.5, 0]} castShadow>
          <cylinderGeometry args={[0.02, 0.02, 0.8, 8]} />
          <meshStandardMaterial color="#333333" roughness={0.5} metalness={0.5} />
        </mesh>
        {/* Antenna tip */}
        <mesh position={[0.2, 0.9, 0]}>
          <sphereGeometry args={[0.05, 8, 8]} />
          <meshStandardMaterial color="#ff0000" emissive="#ff0000" emissiveIntensity={0.5} />
        </mesh>
        {/* Solar panel */}
        <mesh position={[-0.3, 0.4, 0]} rotation={[0, 0, 0.3]} castShadow>
          <boxGeometry args={[0.6, 0.02, 0.4]} />
          <meshStandardMaterial
            color="#1a3a5c"
            roughness={0.3}
            metalness={0.6}
          />
        </mesh>
      </group>

      {/* Battery Pack */}
      <group position={[-3.5, 0.15, -3]}>
        <mesh castShadow receiveShadow>
          <boxGeometry args={[0.6, 0.4, 0.4]} />
          <meshStandardMaterial
            color="#1a1a2e"
            roughness={0.5}
            metalness={0.3}
          />
        </mesh>
        {/* Battery indicator lights */}
        <mesh position={[0, 0.05, 0.21]}>
          <planeGeometry args={[0.3, 0.1]} />
          <meshStandardMaterial color="#00ff00" emissive="#00ff00" emissiveIntensity={0.8} />
        </mesh>
      </group>

      {/* Additional Battery Pack */}
      <group position={[-2.8, 0.15, -3]}>
        <mesh castShadow receiveShadow>
          <boxGeometry args={[0.5, 0.35, 0.35]} />
          <meshStandardMaterial
            color="#1a1a2e"
            roughness={0.5}
            metalness={0.3}
          />
        </mesh>
      </group>

      {/* Generator/Fuel Can */}
      <group position={[3.5, 0.2, -3.5]}>
        <mesh castShadow receiveShadow>
          <cylinderGeometry args={[0.25, 0.25, 0.6, 12]} />
          <meshStandardMaterial
            color="#cc3300"
            roughness={0.7}
            metalness={0.3}
          />
        </mesh>
        {/* Handle */}
        <mesh position={[0, 0.4, 0]} castShadow>
          <torusGeometry args={[0.15, 0.02, 8, 16, Math.PI]} />
          <meshStandardMaterial color="#333333" roughness={0.6} metalness={0.4} />
        </mesh>
      </group>

      {/* Small Equipment Box */}
      <group position={[-5, 0.1, 0]}>
        <mesh castShadow receiveShadow>
          <boxGeometry args={[0.4, 0.2, 0.3]} />
          <meshStandardMaterial
            color="#4a4a4a"
            roughness={0.8}
            metalness={0.2}
          />
        </mesh>
      </group>

      {/* First Aid Kit Box */}
      <group position={[5, 0.1, 0]}>
        <mesh castShadow receiveShadow>
          <boxGeometry args={[0.5, 0.15, 0.3]} />
          <meshStandardMaterial
            color="#ffffff"
            roughness={0.7}
            metalness={0.1}
          />
        </mesh>
        {/* Red cross on first aid */}
        <mesh position={[0, 0.08, 0]}>
          <planeGeometry args={[0.2, 0.06]} />
          <meshStandardMaterial color="#cc0000" roughness={0.5} />
        </mesh>
        <mesh position={[0, 0.08, 0]}>
          <planeGeometry args={[0.06, 0.2]} />
          <meshStandardMaterial color="#cc0000" roughness={0.5} />
        </mesh>
      </group>

      {/* ========== LIGHTING - Safe Zone Spotlight ========== */}
      
      {/* Main spotlight creating the "Safe Zone" effect */}
      <spotLight
        position={[0, 15, 0]}
        angle={Math.PI / 4}
        penumbra={0.5}
        intensity={3}
        color="#fff5e6"
        castShadow
        shadow-mapSize-width={1024}
        shadow-mapSize-height={1024}
        shadow-bias={-0.0001}
        target-position={[0, 0, 0]}
      />

      {/* Secondary fill light for the command base area */}
      <pointLight
        position={[0, 3, 0]}
        intensity={0.5}
        color="#ffeedd"
        distance={15}
        decay={2}
      />

      {/* Small indicator light on radio */}
      <pointLight
        position={[4, 1, -2]}
        intensity={0.3}
        color="#ff4444"
        distance={3}
        decay={2}
      />
    </group>
  );
}

export default CommandBase;
