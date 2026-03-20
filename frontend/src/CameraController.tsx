import { useRef, useEffect } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import { MapControls } from '@react-three/drei';
import { useViewStore } from './viewStore';
import { getDroneRef, getDroneObject } from './store';
import { SENSOR_CONFIG } from './constants';
import * as THREE from 'three';

const INITIAL_CAMERA_POS = new THREE.Vector3(30, 25, 30);
const INITIAL_CAMERA_TARGET = new THREE.Vector3(0, 0, 0);

export function CameraController() {
  const { camera } = useThree();
  const viewMode = useViewStore((state) => state.viewMode);
  const selectedDroneId = useViewStore((state) => state.selectedDroneId);
  const resetViewTrigger = useViewStore((state) => state.resetViewTrigger);
  
  const controlsRef = useRef<any>(null);

  // Reset camera to initial position when triggered
  useEffect(() => {
    if (resetViewTrigger === 0) return;
    camera.position.copy(INITIAL_CAMERA_POS);
    if (controlsRef.current) {
      controlsRef.current.target.copy(INITIAL_CAMERA_TARGET);
      controlsRef.current.update();
    }
  }, [resetViewTrigger]);

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
  const followAzimuthSmooth = useRef(0);
  
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

    // Initialization trigger for smoothed azimuths
    if (Math.abs(azimuthSmooth.current) < 0.001 && Math.abs(elevationSmooth.current) < 0.001) {
       azimuthSmooth.current = THREE.MathUtils.degToRad(-drone.spherical.azimuth);
       followAzimuthSmooth.current = azimuthSmooth.current;
    }

    const dronePos = new THREE.Vector3(drone.position.x, drone.position.y, drone.position.z);
    
    if (viewMode === 'FOLLOW') {
      camera.layers.enable(1); 
      if (camera instanceof THREE.PerspectiveCamera) {
        camera.near = 0.1;
        camera.updateProjectionMatrix();
      }
      
      // 1. GET DRONE WORLD OBJECT (telemetry root)
      const droneObj = getDroneObject(selectedDroneId);
      if (!droneObj) return;

      // Pre-allocated vectors for performance
      const _worldPos = new THREE.Vector3();
      const _worldQuat = new THREE.Quaternion();
      const _targetPos = new THREE.Vector3();
      const _cameraOffset = new THREE.Vector3();

      // 2. GET THE ROOT GROUP'S ABSOLUTE WORLD POSITION AND ROTATION
      droneObj.getWorldPosition(_worldPos);
      droneObj.getWorldQuaternion(_worldQuat);

      // 3. DEFINE A STRICT, HARD-CODED OFFSET (Normalized)
      // If -Z is Forward, then +Z is Behind.
      const IDEAL_OFFSET = new THREE.Vector3(0, 3, 10);
      
      // 4. APPLY THE ROTATION TO OUR OFFSET
      _cameraOffset.copy(IDEAL_OFFSET).applyQuaternion(_worldQuat);

      // 5. CALCULATE FINAL POSITION AND LERP
      _targetPos.copy(_worldPos).add(_cameraOffset);
      camera.position.lerp(_targetPos, 0.1);
      
      // 6. CAMERA LOOKS AT THE DRONE
      camera.lookAt(_worldPos);
      
      // 7. DYNAMIC OPTICS
      if (camera instanceof THREE.PerspectiveCamera) {
        camera.fov = THREE.MathUtils.lerp(camera.fov, 65, 0.05);
        camera.updateProjectionMatrix();
      }
    } 
    else if (viewMode === 'PILOT') {
      camera.layers.disable(1); 
      if (camera instanceof THREE.PerspectiveCamera && camera.near !== 0.01) {
        camera.near = 0.01;
        camera.updateProjectionMatrix();
      }

      // PILOT (1st Person): Located at the "Nose" of the drone
      // 1. DAMPED ROTATIONS
      const targetAzimuth = THREE.MathUtils.degToRad(-drone.spherical.azimuth);
      const targetElevation = THREE.MathUtils.degToRad(drone.spherical.elevation * SENSOR_CONFIG.ELEVATION_FACTOR);
      
      let azDiff = targetAzimuth - azimuthSmooth.current;
      while (azDiff > Math.PI) azDiff -= Math.PI * 2;
      while (azDiff < -Math.PI) azDiff += Math.PI * 2;
      azimuthSmooth.current += azDiff * Math.min(delta * SENSOR_CONFIG.DAMP_ROT_Y, 1);
      
      elevationSmooth.current = THREE.MathUtils.damp(elevationSmooth.current, targetElevation, SENSOR_CONFIG.DAMP_ROT_X, delta);

      // 2. CONSTRUCT NOSE OFFSET
      // In normalized pipeline: Nose is at -Z (offset -0.7)
      tempEuler.current.set(elevationSmooth.current, azimuthSmooth.current, 0, 'YXZ');
      tempQuat.current.setFromEuler(tempEuler.current);
      
      // Use NEGATIVE Z for the nose tip (matching -Z forward)
      noseOffset.current.set(0, 0, -SENSOR_CONFIG.PIVOT_OFFSET[2]).applyQuaternion(tempQuat.current);
      
      // 3. HOVER OSCILLATION SYNC
      const vel = Math.sqrt(
        (drone.position.x - cameraTargetPos.current.x)**2 + 
        (drone.position.z - cameraTargetPos.current.z)**2
      );
      const osc = Math.sin(state.clock.elapsedTime * 2) * 0.05 * (1 - Math.min(vel * 10, 1));

      // 4. DAMPED POSITION
      cameraTargetPos.current.x = THREE.MathUtils.damp(cameraTargetPos.current.x, dronePos.x, SENSOR_CONFIG.DAMP_POS, delta);
      cameraTargetPos.current.z = THREE.MathUtils.damp(cameraTargetPos.current.z, dronePos.z, SENSOR_CONFIG.DAMP_POS, delta);
      cameraTargetPos.current.y = THREE.MathUtils.damp(cameraTargetPos.current.y, dronePos.y, SENSOR_CONFIG.DAMP_POS, delta);
      
      camera.position.copy(cameraTargetPos.current).add(noseOffset.current);
      camera.position.y += osc;
      
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

      // 7. VIBRATION
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
