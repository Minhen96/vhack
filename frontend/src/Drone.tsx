import { useRef, useEffect, useMemo, useState } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import { Html } from '@react-three/drei';
import * as THREE from 'three';
import { subscribeToDronePosition, sendMessage, useStore } from './store';
import type { DroneState, DroneStatus } from './store';

// =============================================================================
// TYPES
// =============================================================================

interface DroneProps {
  droneId: string;
}

// =============================================================================
// HOVER LABEL STYLES
// =============================================================================

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
 * 
 * Search and rescue quadcopter with:
 * - Realistic procedural geometry (body, arms, rotors)
 * - LED navigation lights (red port, green starboard, white front)
 * - Sensor FOV visualization (transparent cone)
 * - Smooth movement with banking physics
 * - Hover interaction with ground ring and label
 * - Raycast detection for survivor detection
 * 
 * Rotation: Uses -azimuth conversion for correct compass alignment
 * (Backend: 0=North, 90=East, clockwise | Three.js: CCW rotation)
 */
export function Drone({ droneId }: DroneProps) {
  const groupRef = useRef<THREE.Group>(null);
  const spotlightRef = useRef<THREE.SpotLight>(null);
  const coneRef = useRef<THREE.Mesh>(null);
  const rotorRefs = useRef<THREE.Mesh[]>([]);
  
  // Hover state - prefer store value, fallback to local for pointer events
  const storeHoveredDroneId = useStore((state) => state.hoveredDroneId);
  const setStoreHoveredDroneId = useStore((state) => state.setHoveredDroneId);
  const [localIsHovered, setLocalIsHovered] = useState(false);
  
  // Use store value if set from Overlay, otherwise use local pointer hover
  const isHovered = storeHoveredDroneId === droneId || localIsHovered;
  
  // Refs for velocity/turning calculation
  const previousPos = useRef(new THREE.Vector3(0, 10, 0));
  const currentPos = useRef(new THREE.Vector3(0, 10, 0));
  const currentRoll = useRef(0);
  const targetAzimuth = useRef(0);
  const currentSpherical = useRef({ azimuth: 0, elevation: 0, fov: 60, scan_radius: 10 });
  const droneStatus = useRef<DroneStatus>('SCANNING');
  // Track last scan_radius to avoid recreating cone geometry every frame
  const prevScanRadius = useRef(-1);
  const prevFov = useRef(-1);
  
  // Raycast detection state
  const lastDetectionTime = useRef(0);
  const detectedSurvivors = useRef<Set<string>>(new Set());
  const raycaster = useMemo(() => new THREE.Raycaster(), []);
  const downDirection = useMemo(() => new THREE.Vector3(0, -1, 0), []);
  
  // Get survivors and blocked areas from store for raycasting
  const survivors = useStore((state) => state.survivors);
  const blockedAreas = useStore((state) => state.blockedAreas);
  
  // Three.js scene access
  const { scene } = useThree();
  
  // Subscribe to high-frequency drone position updates
  useEffect(() => {
    const unsubscribe = subscribeToDronePosition(droneId, (drone: DroneState | null) => {
      if (!drone) return;
      
      // Store target position from WebSocket
      // Backend coordinates: x→x, y→z (ground), z→y (altitude)
      currentPos.current.set(drone.position.x, drone.position.y, drone.position.z);
      
      // Store spherical data for sensor visualization
      currentSpherical.current = { ...drone.spherical };
      
      // FIXED: Use -azimuth conversion instead of -90 offset
      // Backend: 0=North (Z+), 90=East (X+), clockwise
      // Three.js: Y rotation is counter-clockwise positive
      // Apply negative to flip direction
      targetAzimuth.current = THREE.MathUtils.degToRad(-drone.spherical.azimuth);
      
      // Determine status based on movement
      const dx = drone.position.x - previousPos.current.x;
      const dz = drone.position.z - previousPos.current.z;
      const velocity = Math.sqrt(dx * dx + dz * dz);
      
      if (velocity > 0.01) {
        droneStatus.current = 'SCANNING';
      } else if (drone.position.y < 8) {
        droneStatus.current = 'RETURNING';
      } else {
        droneStatus.current = 'IDLE';
      }
    });
    
    return unsubscribe;
  }, [droneId]);

  // Memoize materials for performance
  const materials = useMemo(() => ({
    body: new THREE.MeshStandardMaterial({ 
      color: '#1a1a1a', 
      metalness: 0.8, 
      roughness: 0.2 
    }),
    bodyTop: new THREE.MeshStandardMaterial({ 
      color: '#2d2d2d', 
      metalness: 0.7, 
      roughness: 0.3 
    }),
    arm: new THREE.MeshStandardMaterial({ 
      color: '#3d3d3d', 
      metalness: 0.9, 
      roughness: 0.1 
    }),
    rotor: new THREE.MeshStandardMaterial({ 
      color: '#4a4a4a', 
      transparent: true, 
      opacity: 0.7 
    }),
    ledRed: new THREE.MeshBasicMaterial({ color: '#ff0000' }),
    ledGreen: new THREE.MeshBasicMaterial({ color: '#00ff00' }),
    ledWhite: new THREE.MeshBasicMaterial({ color: '#ffffff' }),
    carbonFiber: new THREE.MeshStandardMaterial({ 
      color: '#1a1a1a', 
      metalness: 0.3, 
      roughness: 0.8 
    }),
    sensorCone: new THREE.MeshBasicMaterial({ 
      color: '#00ffff', 
      transparent: true, 
      opacity: 0.08,
      side: THREE.DoubleSide,
      depthWrite: false
    }),
  }), []);

  useFrame((state) => {
    if (!groupRef.current) return;
    
    const group = groupRef.current;
    const lerpFactor = 0.1;
    const rollLerpFactor = 0.08;
    
    // 1. Lerp position towards target
    group.position.lerp(currentPos.current, lerpFactor);
    
    // 2. Calculate horizontal velocity for banking
    const dx = currentPos.current.x - previousPos.current.x;
    const dz = currentPos.current.z - previousPos.current.z;
    const horizontalVelocity = new THREE.Vector2(dx, dz);
    const velocityMagnitude = horizontalVelocity.length();
    
    // 3. Calculate turn rate for banking
    let turnRate = 0;
    if (velocityMagnitude > 0.001) {
      const currentHeading = Math.atan2(dx, dz);
      const prevHeading = Math.atan2(
        previousPos.current.x - group.position.x,
        previousPos.current.z - group.position.z
      );
      
      let angleDiff = currentHeading - prevHeading;
      while (angleDiff > Math.PI) angleDiff -= Math.PI * 2;
      while (angleDiff < -Math.PI) angleDiff += Math.PI * 2;
      
      turnRate = angleDiff;
    }
    
    // 4. Calculate banking (roll) based on turn rate and speed
    const maxRoll = Math.PI / 4;
    const turnIntensity = Math.min(Math.abs(turnRate) * 15, 1);
    const speedFactor = Math.min(velocityMagnitude * 5, 1);
    const targetRoll = -Math.sign(turnRate) * maxRoll * turnIntensity * speedFactor;
    
    currentRoll.current = THREE.MathUtils.lerp(currentRoll.current, targetRoll, rollLerpFactor);
    
    // 5. Apply rotation with FIXED azimuth conversion
    const spherical = currentSpherical.current;
    const targetRotationX = THREE.MathUtils.degToRad(spherical.elevation * 0.5 || 0);
    
    group.rotation.y = THREE.MathUtils.lerp(group.rotation.y, targetAzimuth.current, lerpFactor);
    group.rotation.x = THREE.MathUtils.lerp(group.rotation.x, targetRotationX, lerpFactor);
    group.rotation.z = THREE.MathUtils.lerp(group.rotation.z, currentRoll.current, rollLerpFactor);
    
    // 6. Add subtle hover oscillation when stationary
    const time = state.clock.elapsedTime;
    const hoverAmount = 0.1;
    const hoverSpeed = 2;
    const baseY = group.position.y;
    group.position.y = baseY + Math.sin(time * hoverSpeed) * hoverAmount * (1 - Math.min(velocityMagnitude * 10, 1));
    
    previousPos.current.copy(group.position);
    
    // 7. Update spotlight based on spherical data
    if (spotlightRef.current) {
      const spot = spotlightRef.current;
      
      const fovRad = THREE.MathUtils.degToRad(spherical.fov);
      spot.angle = fovRad;
      spot.penumbra = THREE.MathUtils.mapLinear(spherical.scan_radius, 1, 20, 0.2, 1);
      spot.distance = spherical.scan_radius * 3;
      
      const altitude = currentPos.current.y;
      spot.intensity = THREE.MathUtils.mapLinear(altitude, 5, 30, 80, 30);
    }
    
    // 8. Update sensor cone visualization
    if (coneRef.current) {
      const coneHeight = spherical.scan_radius * 2;
      const coneRadius = Math.tan(THREE.MathUtils.degToRad(spherical.fov / 2)) * coneHeight;

      // Only recreate geometry when scan_radius or fov actually changes (not every frame)
      if (spherical.scan_radius !== prevScanRadius.current || spherical.fov !== prevFov.current) {
        prevScanRadius.current = spherical.scan_radius;
        prevFov.current = spherical.fov;
        const coneGeo = coneRef.current.geometry as THREE.ConeGeometry;
        coneGeo.dispose();
        coneRef.current.geometry = new THREE.ConeGeometry(coneRadius, coneHeight, 32, 1, true);
        coneRef.current.position.y = -coneHeight / 2;
      }

      // Pulse cone opacity: active scan = rhythmic glow, idle = faint
      const isScanning = droneStatus.current === 'SCANNING';
      const targetOpacity = isScanning
        ? 0.06 + Math.abs(Math.sin(time * 2.5)) * 0.12  // pulse 0.06–0.18
        : 0.03;
      const coneMat = coneRef.current.material as THREE.MeshBasicMaterial;
      coneMat.opacity = THREE.MathUtils.lerp(coneMat.opacity, targetOpacity, 0.05);
    }
    
    // 9. Spin rotors
    rotorRefs.current.forEach((rotor) => {
      if (rotor) {
        rotor.rotation.z += 0.5;
      }
    });
    
    // =============================================================================
    // RAYCAST DETECTION (The Sensor)
    // =============================================================================
    // Use raycaster pointing directly down from drone (elevation direction)
    // Check if intersects with any survivor (objects with userData.isSurvivor === true)
    // within scan_radius
    
    const now = state.clock.getElapsedTime();
    const scanCooldown = 1.0; // 1 second between detections per survivor
    
    // Only scan if enough time has passed and drone is at operational altitude
    if (now - lastDetectionTime.current >= scanCooldown && currentPos.current.y > 3) {
      // Set raycaster origin at drone position, direction down
      raycaster.set(group.position.clone(), downDirection);
      
      // Get all meshes in scene
      const meshes: THREE.Object3D[] = [];
      scene.traverse((obj) => {
        if (obj instanceof THREE.Mesh) {
          meshes.push(obj);
        }
      });
      
      // Check intersections
      const intersects = raycaster.intersectObjects(meshes, false);
      
      for (const intersect of intersects) {
        const obj = intersect.object;
        
        // Check if this is a survivor
        if (obj.userData.isSurvivor === true) {
          const survivorId = obj.userData.survivorId || obj.uuid;
          const distance = intersect.distance;
          
          // Check if within scan radius
          if (distance <= spherical.scan_radius) {
            // Check if not already detected (prevent spam)
            if (!detectedSurvivors.current.has(survivorId)) {
              // Mark as detected
              detectedSurvivors.current.add(survivorId);
              
              // Send message to Go server
              const payload = {
                type: 'survivor_detected',
                drone_id: droneId,
                survivor_id: survivorId,
                x: obj.position.x,
                y: obj.position.z, // Three.js Z -> Backend Y
                z: obj.position.y, // Three.js Y -> Backend Z (altitude)
                distance: distance,
                scan_radius: spherical.scan_radius,
                timestamp: Date.now(),
              };
              
              sendMessage(payload);
              
              console.log(`[${droneId}] Survivor detected: ${survivorId} at distance ${distance.toFixed(1)}m`);
            }
          }
        }
      }
      
      lastDetectionTime.current = now;
    }
  });

  const spherical = currentSpherical.current;
  const coneHeight = spherical.scan_radius * 2;
  const coneRadius = Math.tan(THREE.MathUtils.degToRad(spherical.fov / 2)) * coneHeight;
  const altitude = currentPos.current.y;

  return (
    <group ref={groupRef} position={[0, 10, 0]}>
      {/* =========================================================================
          PROCEDURAL QUADCOPTER GEOMETRY
      ========================================================================= */}
      
      {/* Invisible hitbox for hover detection */}
      <mesh
        onPointerOver={(e) => { e.stopPropagation(); setLocalIsHovered(true); setStoreHoveredDroneId(droneId); }}
        onPointerOut={() => { setLocalIsHovered(false); setStoreHoveredDroneId(null); }}
        visible={false}
      >
        <boxGeometry args={[3, 1, 3]} />
        <meshBasicMaterial transparent opacity={0} />
      </mesh>
      
      {/* Visible drone parts */}
      <group
        onPointerOver={(e) => { e.stopPropagation(); setLocalIsHovered(true); setStoreHoveredDroneId(droneId); }}
        onPointerOut={() => { setLocalIsHovered(false); setStoreHoveredDroneId(null); }}
      >
        {/* Central body - main fuselage with carbon fiber look */}
        <mesh castShadow position={[0, 0, 0]}>
          <boxGeometry args={[1.4, 0.25, 1.0]} />
          <primitive object={materials.body} />
        </mesh>
        
        {/* Body top shell - aerodynamic dome */}
        <mesh castShadow position={[0, 0.18, 0]}>
          <cylinderGeometry args={[0.35, 0.5, 0.15, 16]} />
          <primitive object={materials.bodyTop} />
        </mesh>
        
        {/* Body bottom camera housing */}
        <mesh castShadow position={[0, -0.15, 0]}>
          <cylinderGeometry args={[0.25, 0.3, 0.1, 12]} />
          <primitive object={materials.body} />
        </mesh>
        
        {/* Front sensor array */}
        <mesh castShadow position={[0, 0, 0.55]}>
          <boxGeometry args={[0.4, 0.12, 0.15]} />
          <primitive object={materials.carbonFiber} />
        </mesh>
        
        {/* Motor housings - 4 corners */}
        {[
          [1.3, 0, 1.3],
          [-1.3, 0, 1.3],
          [1.3, 0, -1.3],
          [-1.3, 0, -1.3],
        ].map((pos, i) => (
          <mesh key={i} castShadow position={pos as [number, number, number]}>
            <cylinderGeometry args={[0.18, 0.15, 0.2, 12]} />
            <primitive object={materials.arm} />
          </mesh>
        ))}
        
        {/* Arms - carbon fiber tubes */}
        <mesh castShadow position={[0.9, 0, 0.9]} rotation={[0, Math.PI / 4, 0]}>
          <boxGeometry args={[1.1, 0.08, 0.1]} />
          <primitive object={materials.carbonFiber} />
        </mesh>
        <mesh castShadow position={[-0.9, 0, 0.9]} rotation={[0, -Math.PI / 4, 0]}>
          <boxGeometry args={[1.1, 0.08, 0.1]} />
          <primitive object={materials.carbonFiber} />
        </mesh>
        <mesh castShadow position={[0.9, 0, -0.9]} rotation={[0, -Math.PI / 4, 0]}>
          <boxGeometry args={[1.1, 0.08, 0.1]} />
          <primitive object={materials.carbonFiber} />
        </mesh>
        <mesh castShadow position={[-0.9, 0, -0.9]} rotation={[0, Math.PI / 4, 0]}>
          <boxGeometry args={[1.1, 0.08, 0.1]} />
          <primitive object={materials.carbonFiber} />
        </mesh>
        
        {/* Propellers with spinning animation */}
        {[
          [1.3, 0.15, 1.3],
          [-1.3, 0.15, 1.3],
          [1.3, 0.15, -1.3],
          [-1.3, 0.15, -1.3],
        ].map((pos, i) => (
          <mesh 
            key={i} 
            ref={(el) => { if (el) rotorRefs.current[i] = el; }}
            position={pos as [number, number, number]} 
            rotation={[0, 0, Math.PI / 2]}
          >
            <cylinderGeometry args={[0.5, 0.5, 0.02, 2]} />
            <primitive object={materials.rotor} />
          </mesh>
        ))}
        
        {/* Propeller guards */}
        {[
          [1.3, 0, 1.3],
          [-1.3, 0, 1.3],
          [1.3, 0, -1.3],
          [-1.3, 0, -1.3],
        ].map((pos, i) => (
          <mesh key={i} position={pos as [number, number, number]} rotation={[Math.PI / 2, 0, 0]}>
            <torusGeometry args={[0.55, 0.02, 8, 24]} />
            <primitive object={materials.arm} />
          </mesh>
        ))}
        
        {/* =========================================================================
            LED NAVIGATION LIGHTS
        ========================================================================= */}
        
        {/* Port (left) - Red LED */}
        <mesh position={[-0.7, 0, 0.5]}>
          <sphereGeometry args={[0.06, 8, 8]} />
          <primitive object={materials.ledRed} />
        </mesh>
        <pointLight position={[-0.7, 0, 0.5]} color="#ff0000" intensity={3} distance={8} />
        
        {/* Starboard (right) - Green LED */}
        <mesh position={[0.7, 0, 0.5]}>
          <sphereGeometry args={[0.06, 8, 8]} />
          <primitive object={materials.ledGreen} />
        </mesh>
        <pointLight position={[0.7, 0, 0.5]} color="#00ff00" intensity={3} distance={8} />
        
        {/* Front - White LED */}
        <mesh position={[0, 0, 0.7]}>
          <sphereGeometry args={[0.05, 8, 8]} />
          <primitive object={materials.ledWhite} />
        </mesh>
        <pointLight position={[0, 0, 0.7]} color="#ffffff" intensity={2} distance={5} />
        
        {/* Rear - Amber LED */}
        <mesh position={[0, 0, -0.6]}>
          <sphereGeometry args={[0.04, 8, 8]} />
          <meshBasicMaterial color="#ffaa00" />
        </mesh>
        <pointLight position={[0, 0, -0.6]} color="#ffaa00" intensity={1.5} distance={4} />
        
        {/* =========================================================================
            SENSOR FOV VISUALIZATION
        ========================================================================= */}
        
        {/* Transparent cone showing scan area */}
        <mesh 
          ref={coneRef}
          position={[0, -coneHeight / 2, 0]}
          rotation={[Math.PI, 0, 0]}
        >
          <coneGeometry args={[coneRadius, coneHeight, 32, 1, true]} />
          <primitive object={materials.sensorCone} />
        </mesh>
        
        {/* =========================================================================
            SEARCH SPOTLIGHT
        ========================================================================= */}
        
        <spotLight
          ref={spotlightRef}
          position={[0, -0.3, 0]}
          target-position={[0, -10, 0]}
          angle={0.4}
          penumbra={0.5}
          intensity={50}
          color="#ffffff"
          castShadow
          shadow-mapSize-width={1024}
          shadow-mapSize-height={1024}
          shadow-bias={-0.0001}
        />
      </group>
      
      {/* =========================================================================
          HOVER INTERACTION - Ground Ring Indicator
      ========================================================================= */}
      
      {/* Glowing ring on ground when hovered */}
      {isHovered && (
        <mesh 
          position={[0, 0.05, 0]} 
          rotation={[-Math.PI / 2, 0, 0]}
        >
          <ringGeometry args={[1.5, 2, 32]} />
          <meshBasicMaterial 
            color="#ffcc00" 
            transparent 
            opacity={0.5}
            side={THREE.DoubleSide}
          />
        </mesh>
      )}
      

      
      {isHovered && (
        <Html
          position={[0, 2.5, 0]}
          center
          style={{
            pointerEvents: 'none',
            transform: 'translate3d(-50%, -50%, 0)',
          }}
        >
          <div style={hoverLabelStyle}>
            ◆ TARGET: {droneId}
          </div>
        </Html>
      )}
    </group>
  );
}

// =============================================================================
// DRONES CONTAINER - Renders all drones from store
// =============================================================================

/**
 * Drones - Container component that renders all drones from the store
 * Maps over the drones in Zustand store and renders a Drone component for each
 */
export function Drones() {
  const drones = useStore((state) => state.drones);
  
  // Convert drones object to array
  const droneList = Object.keys(drones);
  
  return (
    <>
      {droneList.map((droneId) => (
        <Drone key={droneId} droneId={droneId} />
      ))}
    </>
  );
}

export default Drone;
