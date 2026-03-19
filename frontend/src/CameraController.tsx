import { useRef } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import { MapControls } from '@react-three/drei';
import * as THREE from 'three';
import { useViewStore } from './viewStore';
import { getDroneRef } from './store';
import { SENSOR_CONFIG } from './constants';

export function CameraController() {
  const { camera } = useThree();
  const viewMode = useViewStore((state) => state.viewMode);
  const selectedDroneId = useViewStore((state) => state.selectedDroneId);
  
  const controlsRef = useRef<any>(null);
  
  // Pre-allocated vectors for performance (GC pressure reduction)
  const targetLookAt = useRef(new THREE.Vector3());
  const noseOffset = useRef(new THREE.Vector3());
  const tempEuler = useRef(new THREE.Euler(0, 0, 0, 'YXZ'));
  const tempQuat = useRef(new THREE.Quaternion());
  const prevFov = useRef(0);
  const prevNear = useRef(0);
  const azimuthSmooth = useRef(0);
  const elevationSmooth = useRef(0);
  const cameraTargetPos = useRef(new THREE.Vector3());
  
  useFrame((state, delta) => {

    if (viewMode === 'GLOBAL') {
      camera.layers.enable(1); // Show drones in global
      if (camera instanceof THREE.PerspectiveCamera) {
        camera.near = 0.1;
        camera.updateProjectionMatrix();
      }
      return;
    }

    if (!selectedDroneId) return;
    const drone = getDroneRef(selectedDroneId);
    if (!drone) return;

    const dronePos = new THREE.Vector3(drone.position.x, drone.position.y, drone.position.z);
    
    if (viewMode === 'FOLLOW') {
      camera.layers.enable(1); // Show drone in follow
      if (camera instanceof THREE.PerspectiveCamera) {
        camera.near = 0.1;
        camera.updateProjectionMatrix();
      }
      
      // FOLLOW (3rd Person): 5 units behind, 3 units above
      // Calculate "behind" based on drone's azimuth
      const azimuthRad = THREE.MathUtils.degToRad(drone.spherical.azimuth);
      // Backend azimuth: 0=North(Z+), 90=East(X+). 
      // Camera should be opposite to direction of travel
      const offsetX = Math.sin(azimuthRad) * -7;
      const offsetZ = Math.cos(azimuthRad) * -7;
      
      const idealPos = dronePos.clone().add(new THREE.Vector3(offsetX, 4, offsetZ));
      const idealLookAt = dronePos.clone().add(new THREE.Vector3(0, 1, 0)); // Look slightly above center

      // Smooth lag using lerp
      camera.position.lerp(idealPos, 0.1);
      
      // Use a proxy for lookAt to smooth it too
      targetLookAt.current.lerp(idealLookAt, 0.1);
      camera.lookAt(targetLookAt.current);
      
      // Ensure FOV is standard
      if (camera instanceof THREE.PerspectiveCamera) {
        camera.fov = THREE.MathUtils.lerp(camera.fov, 60, 0.1);
        camera.updateProjectionMatrix();
      }
    } 
    else if (viewMode === 'PILOT') {
      camera.layers.disable(1); // GHOST DRONE: Hide drone for its own FPV
      if (camera instanceof THREE.PerspectiveCamera && camera.near !== 0.01) {
        camera.near = 0.01;
        camera.updateProjectionMatrix();
      }

      // PILOT (1st Person): Located at the "Nose" of the drone for true FPV
      // 1. DAMPED ROTATIONS (Shortest Path)
      const targetAzimuth = THREE.MathUtils.degToRad(-drone.spherical.azimuth);
      const targetElevation = THREE.MathUtils.degToRad(drone.spherical.elevation * SENSOR_CONFIG.ELEVATION_FACTOR);
      
      // Horizontal Wrap Handling
      let azDiff = targetAzimuth - azimuthSmooth.current;
      while (azDiff > Math.PI) azDiff -= Math.PI * 2;
      while (azDiff < -Math.PI) azDiff += Math.PI * 2;
      azimuthSmooth.current += azDiff * Math.min(delta * SENSOR_CONFIG.DAMP_ROT_Y, 1);
      
      // Vertical Smoothing
      elevationSmooth.current = THREE.MathUtils.damp(elevationSmooth.current, targetElevation, SENSOR_CONFIG.DAMP_ROT_X, delta);

      // Determine Roll (Simulated banking derived from horizontal velocity)
      // (This should match the drone's logic exactly for perfect parity)
      // Note: We bypass manual roll for the pilot to keep the horizon stable 
      // UNLESS the user wants absolute "in-cockpit" realism.
      // For now, we align Azimuth and Elevation perfectly.

      // 2. CONSTRUCT NOSE OFFSET (Full 3D Coupling)
      // tip is at [0, 0, 0.7] in local space of visualGroupRef
      tempEuler.current.set(elevationSmooth.current, azimuthSmooth.current, 0, 'YXZ');
      tempQuat.current.setFromEuler(tempEuler.current);
      
      // Calculate nose in world space relative to drone center
      noseOffset.current.set(0, 0, SENSOR_CONFIG.PIVOT_OFFSET[2]).applyQuaternion(tempQuat.current);
      
      // 3. HOVER OSCILLATION SYNC
      const vel = Math.sqrt(
        (drone.position.x - cameraTargetPos.current.x)**2 + 
        (drone.position.z - cameraTargetPos.current.z)**2
      );
      const osc = Math.sin(state.clock.elapsedTime * 2) * 0.05 * (1 - Math.min(vel * 10, 1));

      // 4. DAMPED POSITION (World Space)
      cameraTargetPos.current.x = THREE.MathUtils.damp(cameraTargetPos.current.x, dronePos.x, SENSOR_CONFIG.DAMP_POS, delta);
      cameraTargetPos.current.z = THREE.MathUtils.damp(cameraTargetPos.current.z, dronePos.z, SENSOR_CONFIG.DAMP_POS, delta);
      cameraTargetPos.current.y = THREE.MathUtils.damp(cameraTargetPos.current.y, dronePos.y, SENSOR_CONFIG.DAMP_POS, delta);
      
      camera.position.copy(cameraTargetPos.current).add(noseOffset.current);
      camera.position.y += osc; // Add hover sway
      
      // 5. APPLY CAMERA ROTATION
      camera.rotation.order = 'YXZ';
      camera.rotation.set(elevationSmooth.current, azimuthSmooth.current, 0);

      // 6. FOV & OPTICS
      if (camera instanceof THREE.PerspectiveCamera) {
        const targetFov = drone.spherical.fov > 0 ? drone.spherical.fov : 90;
        camera.fov = THREE.MathUtils.lerp(camera.fov, targetFov, SENSOR_CONFIG.FOV_LERP);
        
        if (Math.abs(camera.fov - prevFov.current) > 0.01 || Math.abs(camera.near - prevNear.current) > 0.001) {
          camera.updateProjectionMatrix();
          prevFov.current = camera.fov;
          prevNear.current = camera.near;
        }
      }

      // 7. VIBRATION (Small high-freq noise)
      camera.position.x += (Math.random() - 0.5) * SENSOR_CONFIG.VIBRATION_SHAKE;
      camera.position.y += (Math.random() - 0.5) * SENSOR_CONFIG.VIBRATION_SHAKE;
      camera.position.z += (Math.random() - 0.5) * SENSOR_CONFIG.VIBRATION_SHAKE;
    }
  });

  return (
    <>
      {viewMode === 'GLOBAL' && (
        <MapControls
          ref={controlsRef}
          enablePan={true}
          enableZoom={true}
          enableRotate={true}
          minDistance={5}
          maxDistance={150}
          maxPolarAngle={Math.PI / 2 - 0.1}
          makeDefault
        />
      )}
    </>
  );
}

export default CameraController;
