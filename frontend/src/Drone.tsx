import { useRef, useEffect, useMemo } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import { Html } from '@react-three/drei';
import * as THREE from 'three';
import { subscribeToDronePosition, sendMessage, useStore } from './store';
import { useViewStore } from './viewStore';
import type { DroneState, DroneStatus, SphericalCoords } from './store';
import { SENSOR_CONFIG } from './constants';

// =============================================================================
// TYPES & STYLES
// =============================================================================

interface DroneProps {
  droneId: string;
}

const hoverLabelStyle: React.CSSProperties = {
  background: 'linear-gradient(135deg, rgba(0, 20, 25, 0.95) 0%, rgba(0, 10, 18, 0.98) 100%)',
  border: '1px solid rgba(255, 200, 0, 0.6)',
  borderRadius: '4px',
  padding: '6px 12px',
  color: '#ffcc00',
  fontSize: '11px',
  fontWeight: 600,
  fontFamily: '"JetBrains Mono", "Fira Code", "Consolas", monospace',
  letterSpacing: '1px',
  textShadow: '0 0 8px rgba(255, 200, 0, 0.6)',
  boxShadow: '0 0 20px rgba(255, 200, 0, 0.2)',
  whiteSpace: 'nowrap',
  pointerEvents: 'none',
};

/**
 * Drone Component - Individual drone instance
 * Optimized for performance and visual stability.
 */
export function Drone({ droneId }: DroneProps) {
  const groupRef = useRef<THREE.Group>(null);
  const visualGroupRef = useRef<THREE.Group>(null);
  const spotlightRef = useRef<THREE.SpotLight>(null);
  const coneRef = useRef<THREE.Mesh>(null);
  const rotorRefs = useRef<THREE.Mesh[]>([]);
  
  // Store interaction
  const storeHoveredDroneId = useStore((state) => state.hoveredDroneId);
  const setStoreHoveredDroneId = useStore((state) => state.setHoveredDroneId);
  const isHovered = storeHoveredDroneId === droneId;
  const { viewMode, selectedDroneId, setFollowView, setPilotView, setGlobalView } = useViewStore();

  // Telemetry & State Refs
  const previousPos = useRef(new THREE.Vector3(0, 10, 0));
  const currentPos = useRef(new THREE.Vector3(0, 10, 0));
  const currentRoll = useRef(0);
  const targetAzimuth = useRef(0);
  const currentSpherical = useRef<SphericalCoords>({ azimuth: 0, elevation: 0, fov: 60, scan_radius: 10, roll: 0 });
  const droneStatus = useRef<DroneStatus>('SCANNING');
  
  // Throttle & Optimization Refs
  const { scene } = useThree();
  
  // Restore missing refs
  const lastDetectionTime = useRef(0);
  const detectedSurvivors = useRef<Set<string>>(new Set());
  const lastVisualUpdate = useRef({ fov: -1, alt: -1, elevation: -999 });
  const lerpedFov = useRef(90);
  const spotlightTargetRef = useRef<THREE.Object3D>(null);

  // Performance Optimization: Cache survivor meshes to avoid scene traversal
  const survivorMeshes = useMemo(() => {
    const meshes: THREE.Mesh[] = [];
    scene.traverse((obj) => {
      if (obj instanceof THREE.Mesh && obj.userData.isSurvivor) {
        meshes.push(obj);
      }
    });
    return meshes;
  }, [scene, useStore.getState().survivors.length]); 

  // Scratch variables to prevent GC thrashing
  const _raycaster = useMemo(() => new THREE.Raycaster(), []);
  const _downDir = useMemo(() => new THREE.Vector3(0, -1, 0), []);

  // Web Socket Subscription
  useEffect(() => {
    const unsubscribe = subscribeToDronePosition(droneId, (drone: DroneState | null) => {
      if (!drone) return;
      currentPos.current.set(drone.position.x, drone.position.y, drone.position.z);
      currentSpherical.current = { ...drone.spherical };
      targetAzimuth.current = THREE.MathUtils.degToRad(-drone.spherical.azimuth);
      
      const dx = drone.position.x - previousPos.current.x;
      const dz = drone.position.z - previousPos.current.z;
      if (Math.sqrt(dx * dx + dz * dz) > 0.01) droneStatus.current = 'SCANNING';
      else if (drone.position.y < 8) droneStatus.current = 'RETURNING';
      else droneStatus.current = 'IDLE';
    });
    return unsubscribe;
  }, [droneId]);

  // Ghost Drone Layers + Rotation Order (assigned once)
  useEffect(() => {
    if (visualGroupRef.current) {
      // Match camera rotation order (YXZ = yaw first, then pitch)
      // Without this, cone direction diverges from camera view when both azimuth & elevation are non-zero
      visualGroupRef.current.rotation.order = 'YXZ';
      visualGroupRef.current.traverse((obj) => obj.layers.set(1));
    }
  }, []);

  // Performance Materials
  const materials = useMemo(() => ({
    body: new THREE.MeshStandardMaterial({ color: '#1a1a1a', metalness: 0.8, roughness: 0.2 }),
    bodyTop: new THREE.MeshStandardMaterial({ color: '#2d2d2d', metalness: 0.7, roughness: 0.3 }),
    arm: new THREE.MeshStandardMaterial({ color: '#3d3d3d', metalness: 0.9, roughness: 0.1 }),
    rotor: new THREE.MeshStandardMaterial({ color: '#4a4a4a', transparent: true, opacity: 0.7 }),
    ledRed: new THREE.MeshBasicMaterial({ color: '#ff0000' }),
    ledGreen: new THREE.MeshBasicMaterial({ color: '#00ff00' }),
    ledWhite: new THREE.MeshBasicMaterial({ color: '#ffffff' }),
    carbonFiber: new THREE.MeshStandardMaterial({ color: '#1a1a1a', metalness: 0.3, roughness: 0.8 }),
    sensorCone: new THREE.MeshBasicMaterial({ color: '#00ffff', transparent: true, opacity: 0.08, side: THREE.DoubleSide, depthWrite: false }),
  }), []);

  useFrame((state, delta) => {
    if (!groupRef.current || !visualGroupRef.current) return;
    
    const group = groupRef.current;
    const visual = visualGroupRef.current;
    const time = state.clock.elapsedTime;
    
    // 1. POSITION DAMPING (Synced with Camera)
    group.position.x = THREE.MathUtils.damp(group.position.x, currentPos.current.x, SENSOR_CONFIG.DAMP_POS, delta);
    group.position.z = THREE.MathUtils.damp(group.position.z, currentPos.current.z, SENSOR_CONFIG.DAMP_POS, delta);
    group.position.y = THREE.MathUtils.damp(group.position.y, currentPos.current.y, SENSOR_CONFIG.DAMP_POS, delta);
    
    // 2. BANKING PHYSICS
    const dx = currentPos.current.x - previousPos.current.x;
    const dz = currentPos.current.z - previousPos.current.z;
    const vel = Math.sqrt(dx * dx + dz * dz);
    
    // Roll comes from backend telemetry (spherical.roll) — computed in move_to
    // per step from azimuth change, same formula as before. Damp for smooth animation.
    const targetRollRad = THREE.MathUtils.degToRad(currentSpherical.current.roll ?? 0);
    currentRoll.current = THREE.MathUtils.damp(currentRoll.current, targetRollRad, SENSOR_CONFIG.DAMP_ROLL, delta);
    
    // 3. ROTATION (Visual group only)
    const spherical = currentSpherical.current;
    
    // Smooth Azimuth (Handle wrap)
    let azDiff = targetAzimuth.current - visual.rotation.y;
    while (azDiff > Math.PI) azDiff -= Math.PI * 2;
    while (azDiff < -Math.PI) azDiff += Math.PI * 2;
    visual.rotation.y += azDiff * Math.min(delta * SENSOR_CONFIG.DAMP_ROT_Y, 1);
    
    // Body stays level — only roll (banking). Camera and cone handle elevation separately.
    visual.rotation.x = 0;
    visual.rotation.z = currentRoll.current;
    
    // 4. STATIONARY HOVER
    const osc = Math.sin(time * 2) * 0.05 * (1 - Math.min(vel * 10, 1));
    visual.position.y = osc;
    
    previousPos.current.copy(group.position);

    // 5. THROTTLED VISUALS (FOV / ALTITUDE)
    const currentAlt = group.position.y + 0.5;
    const targetFov = spherical.fov || 90;
    
    // Smoothly transition FOV to match camera lerp
    lerpedFov.current = THREE.MathUtils.lerp(lerpedFov.current, targetFov, SENSOR_CONFIG.FOV_LERP);
    const currentFov = lerpedFov.current;

    // Throttle check: update if alt, FOV, or elevation changes
    if (
      Math.abs(lastVisualUpdate.current.alt - currentAlt) > 0.05 ||
      Math.abs(lastVisualUpdate.current.fov - currentFov) > 0.1 ||
      Math.abs(lastVisualUpdate.current.elevation - spherical.elevation) > 0.5
    ) {
      const fovRad = THREE.MathUtils.degToRad(currentFov);
      if (spotlightRef.current) {
        spotlightRef.current.angle = fovRad / 2;
        spotlightRef.current.intensity = THREE.MathUtils.mapLinear(currentAlt, 5, 30, 100, 30);
      }
      if (coneRef.current) {
        // rotation.x = PI/2 + elevationRad:
        //   PI/2 alone  → cone opens in -Z (forward, horizon)
        //   + elevation → tilts down (e.g. -PI/4 → forward-down 45°)
        const elevationRad = THREE.MathUtils.degToRad(spherical.elevation * SENSOR_CONFIG.ELEVATION_FACTOR);
        coneRef.current.rotation.x = Math.PI / 2 + elevationRad;

        // Cone length = slant distance from drone nose to ground.
        // slant = altitude / |sin(elevation)| so the base circle lands on y=0.
        // Cap when elevation is near-horizontal (sin → 0) to avoid infinite length.
        const sinEl = Math.sin(elevationRad);
        // +0.5 accounts for the visual ground plane being at y=-0.5 in the scene
        const droneHeight = group.position.y + 0.5;
        const coneLength = sinEl < -0.05
          ? Math.min(droneHeight / Math.abs(sinEl), droneHeight * 10)
          : droneHeight * 2; // fallback for near-horizontal / upward cameras

        const radius = Math.tan(fovRad / 2) * coneLength;
        coneRef.current.scale.set(radius, coneLength, radius);

        // Place apex at drone nose. After Rx(PI/2+elRad), apex local coords:
        //   y = -(coneLength/2)*sin(elRad),  z = (coneLength/2)*cos(elRad)
        // Offset position so apex lands at (0, 0, PIVOT_OFFSET).
        coneRef.current.position.y = (coneLength / 2) * Math.sin(elevationRad);
        coneRef.current.position.z = SENSOR_CONFIG.PIVOT_OFFSET[2] - (coneLength / 2) * Math.cos(elevationRad);
      }
      lastVisualUpdate.current = { fov: currentFov, alt: currentAlt, elevation: spherical.elevation };
    }

    // 6. SENSOR OPACITY PULSE
    if (coneRef.current) {
      const targetOpacity = droneStatus.current === 'SCANNING' ? 0.05 + Math.abs(Math.sin(time * 3)) * 0.08 : 0.02;
      (coneRef.current.material as THREE.MeshBasicMaterial).opacity = THREE.MathUtils.lerp((coneRef.current.material as THREE.MeshBasicMaterial).opacity, targetOpacity, 0.1);
    }
    
    rotorRefs.current.forEach((r) => r && (r.rotation.y += 0.8));

    // 7. RAYCAST DETECTION (Optimized)
    const now = state.clock.getElapsedTime();
    if (now - lastDetectionTime.current >= 1.0 && currentAlt > 3) {
      _raycaster.set(group.position, _downDir);
      
      // Use cached survivor meshes instead of traversing the whole scene
      const intersects = _raycaster.intersectObjects(survivorMeshes, false);
      
      for (const intersect of intersects) {
        if (intersect.distance <= spherical.scan_radius) {
          const sId = intersect.object.userData.survivorId || intersect.object.uuid;
          
          // O(1) lookup in transient ref
          if (!detectedSurvivors.current.has(sId)) {
            detectedSurvivors.current.add(sId);
            sendMessage({
              type: 'survivor_detected',
              drone_id: droneId,
              survivor_id: sId,
              x: intersect.object.position.x,
              y: intersect.object.position.z, // Mapping Three.js Z to backend Y
              z: intersect.object.position.y,
              distance: intersect.distance,
              scan_radius: spherical.scan_radius,
              timestamp: Date.now(),
            });
          }
        }
      }
      lastDetectionTime.current = now;
    }
  });

  return (
    <group ref={groupRef}>
      {/* Interaction Hitbox (Invisible) */}
      <mesh 
        visible={false} 
        onPointerOver={() => setStoreHoveredDroneId(droneId)}
        onPointerOut={() => setStoreHoveredDroneId(null)}
        onClick={() => {
          if (selectedDroneId !== droneId) setFollowView(droneId);
          else {
            if (viewMode === 'FOLLOW') setPilotView(droneId);
            else if (viewMode === 'PILOT') setGlobalView();
            else setFollowView(droneId);
          }
        }}
      >
        <sphereGeometry args={[1.8]} />
        <meshBasicMaterial transparent opacity={0} />
      </mesh>

      {/* Visual Drone Body (Rotates) */}
      <group ref={visualGroupRef}>
        <mesh castShadow><boxGeometry args={[1.4, 0.25, 1.0]} /><primitive object={materials.body} /></mesh>
        <mesh castShadow position={[0, 0.18, 0]}><cylinderGeometry args={[0.35, 0.5, 0.15, 16]} /><primitive object={materials.bodyTop} /></mesh>
        <mesh castShadow position={[0, -0.15, 0]}><cylinderGeometry args={[0.25, 0.3, 0.1, 12]} /><primitive object={materials.body} /></mesh>
        <mesh castShadow position={[0, 0, 0.55]}><boxGeometry args={[0.4, 0.12, 0.15]} /><primitive object={materials.carbonFiber} /></mesh>
        
        {/* Components */}
        {[ [1.3,0,1.3], [-1.3,0,1.3], [1.3,0,-1.3], [-1.3,0,-1.3] ].map((pos, i) => (
          <group key={i} position={pos as [number, number, number]}>
            <mesh castShadow><cylinderGeometry args={[0.18, 0.15, 0.2, 12]} /><primitive object={materials.arm} /></mesh>
            <mesh ref={(el) => { if (el) rotorRefs.current[i] = el; }} position={[0, 0.15, 0]}><cylinderGeometry args={[0.5, 0.5, 0.02, 2]} /><primitive object={materials.rotor} /></mesh>
            <mesh rotation={[Math.PI/2, 0, 0]}><torusGeometry args={[0.55, 0.02, 8, 24]} /><primitive object={materials.arm} /></mesh>
          </group>
        ))}

        {/* Navigation Lights */}
        <mesh position={[-0.7, 0, 0.5]}><sphereGeometry args={[0.1, 8, 8]} /><primitive object={materials.ledRed} /></mesh>
        <mesh position={[0.7, 0, 0.5]}><sphereGeometry args={[0.1, 8, 8]} /><primitive object={materials.ledGreen} /></mesh>
        <mesh position={[0, 0, 0.7]}><sphereGeometry args={[0.1, 8, 8]} /><primitive object={materials.ledWhite} /></mesh>
        
        {/* SENSOR ARRAY: Tip at the Nose (Aligned with Pilot Camera) */}
        {/* rotation.x=PI/2 reorients the cone from +Y (default up) to -Z (forward), matching camera look direction */}
        <mesh ref={coneRef} rotation={[Math.PI / 2, 0, 0]}>
          <coneGeometry args={[1, 1, 32, 1, true]} />
          <primitive object={materials.sensorCone} />
        </mesh>
        
        {/* Spotlight with dedicated target for precision (Nose-Aligned) */}
        <object3D ref={spotlightTargetRef} position={[0, -10, SENSOR_CONFIG.PIVOT_OFFSET[2]]} />
        <spotLight 
          ref={spotlightRef} 
          position={[0, -0.1, SENSOR_CONFIG.PIVOT_OFFSET[2]]} 
          target={spotlightTargetRef.current || undefined}
          penumbra={0.3} 
          intensity={50} 
          color="#ffffff" 
          castShadow 
        />
      </group>

      {/* Static Interaction FX (Do Not Rotate) */}
      <group>
        {isHovered && groupRef.current && (
          <mesh position={[0, -groupRef.current.position.y + 0.05, 0]} rotation={[-Math.PI / 2, 0, 0]}>
            <ringGeometry args={[1.6, 2.2, 32]} />
            <meshBasicMaterial color="#ffcc00" transparent opacity={0.6} side={THREE.DoubleSide} />
          </mesh>
        )}
        {isHovered && (
          <Html position={[0, 2.5, 0]} center style={{ pointerEvents: 'none' }}>
            <div style={hoverLabelStyle}>◆ TARGET: {droneId}</div>
          </Html>
        )}
      </group>
    </group>
  );
}

/**
 * Drones Container - Optimized to only re-render when drone IDs change
 */
export function Drones() {
  const droneIds = useStore((state) => Object.keys(state.drones).join(','));
  const ids = useMemo(() => droneIds.split(','), [droneIds]);

  if (!droneIds) return null;

  return (
    <>
      {ids.map((id) => (id ? <Drone key={id} droneId={id} /> : null))}
    </>
  );
}

export default Drone;
