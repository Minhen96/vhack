import { useRef, useMemo, useEffect } from 'react';
import * as THREE from 'three';
import { Html } from '@react-three/drei';
import { useStore, type Survivor } from './store';

// Scratch variables for instance updates
const _obj = new THREE.Object3D();

/**
 * Survivors Component - Optimized with InstancedMesh
 * Reduces draw calls from 3 per human to 3 per scene.
 */
export function Survivors() {
  const survivors = useStore(state => state.survivors);
  
  const bodyMeshRef = useRef<THREE.InstancedMesh>(null);
  const headMeshRef = useRef<THREE.InstancedMesh>(null);
  const ringMeshRef = useRef<THREE.InstancedMesh>(null);

  const { bodyGeom, headGeom, ringGeom, undetectedMat, detectedMat, aidedMat, undetectedRingMat, detectedRingMat, aidedRingMat } = useMemo(() => ({
    bodyGeom: new THREE.CapsuleGeometry(0.3, 1, 4, 8),
    headGeom: new THREE.SphereGeometry(0.25, 16, 16),
    ringGeom: new THREE.RingGeometry(0.4, 1.2, 32),
    undetectedMat: new THREE.MeshStandardMaterial({
      color: '#446688', emissive: '#ee2200', emissiveIntensity: 0.2, transparent: true, opacity: 0.6 
    }),
    detectedMat: new THREE.MeshStandardMaterial({
      color: '#ffcc00', emissive: '#ffaa00', emissiveIntensity: 0.5 
    }),
    aidedMat: new THREE.MeshStandardMaterial({
      color: '#00ff88', emissive: '#00ff44', emissiveIntensity: 0.8 
    }),
    aidedRingMat: new THREE.MeshBasicMaterial({
      color: '#00ff88', transparent: true, opacity: 0.3, side: THREE.DoubleSide 
    }),
    undetectedRingMat: new THREE.MeshBasicMaterial({
      color: '#ff0000', transparent: true, opacity: 0.15, side: THREE.DoubleSide 
    }),
    detectedRingMat: new THREE.MeshBasicMaterial({
      color: '#ffaa00', transparent: true, opacity: 0.25, side: THREE.DoubleSide 
    })
  }), []);

  // 3-Stage Lifecycle Splitting
  const trapped = useMemo(() => survivors.filter(s => s.status === 'TRAPPED'), [survivors]);
  const detected = useMemo(() => survivors.filter(s => s.status === 'DETECTED'), [survivors]);
  const aided = useMemo(() => survivors.filter(s => s.status === 'AID_SENT'), [survivors]);

  useEffect(() => {
    if (!bodyMeshRef.current || !headMeshRef.current || !ringMeshRef.current) return;

    trapped.forEach((s, i) => {
      // Update Body Instance
      _obj.position.set(s.position.x, 0.9, s.position.z);
      _obj.rotation.set(0, 0, 0);
      _obj.updateMatrix();
      bodyMeshRef.current!.setMatrixAt(i, _obj.matrix);
      
      // Update Head Instance
      _obj.position.set(s.position.x, 1.8, s.position.z);
      _obj.updateMatrix();
      headMeshRef.current!.setMatrixAt(i, _obj.matrix);

      // Update Ring Instance
      _obj.position.set(s.position.x, 0.01, s.position.z);
      _obj.rotation.set(-Math.PI / 2, 0, 0);
      _obj.updateMatrix();
      ringMeshRef.current!.setMatrixAt(i, _obj.matrix);
    });

    bodyMeshRef.current.instanceMatrix.needsUpdate = true;
    headMeshRef.current.instanceMatrix.needsUpdate = true;
    ringMeshRef.current.instanceMatrix.needsUpdate = true;
  }, [trapped]);

  return (
    <group>
      {/* TRAPPED Humans (Red) */}
      {trapped.length > 0 && (
        <>
          <instancedMesh ref={bodyMeshRef} args={[bodyGeom, undetectedMat, trapped.length]} />
          <instancedMesh ref={headMeshRef} args={[headGeom, undetectedMat, trapped.length]} />
          <instancedMesh ref={ringMeshRef} args={[ringGeom, undetectedRingMat, trapped.length]} />
        </>
      )}

      {/* DETECTED Humans (Yellow/Search) */}
      {detected.length > 0 && (
        <HumansInstanced 
          survivors={detected} 
          bodyGeom={bodyGeom} 
          headGeom={headGeom} 
          ringGeom={ringGeom} 
          bodyMat={detectedMat} 
          ringMat={detectedRingMat} 
          icon="🔍"
        />
      )}

      {/* AID_SENT Humans (Green/Safe) */}
      {aided.length > 0 && (
        <HumansInstanced 
          survivors={aided} 
          bodyGeom={bodyGeom} 
          headGeom={headGeom} 
          ringGeom={ringGeom} 
          bodyMat={aidedMat} 
          ringMat={aidedRingMat} 
          icon="📦"
        />
      )}
    </group>
  );
}

function HumansInstanced({ survivors, bodyGeom, headGeom, ringGeom, bodyMat, ringMat, icon }: any) {
  const bodyRef = useRef<THREE.InstancedMesh>(null);
  const headRef = useRef<THREE.InstancedMesh>(null);
  const ringRef = useRef<THREE.InstancedMesh>(null);

  useEffect(() => {
    if (!bodyRef.current || !headRef.current || !ringRef.current) return;
    
    survivors.forEach((s: Survivor, i: number) => {
      _obj.rotation.set(0, 0, 0);
      _obj.position.set(s.position.x, 0.9, s.position.z);
      _obj.updateMatrix();
      bodyRef.current!.setMatrixAt(i, _obj.matrix);

      _obj.position.set(s.position.x, 1.8, s.position.z);
      _obj.updateMatrix();
      headRef.current!.setMatrixAt(i, _obj.matrix);

      _obj.position.set(s.position.x, 0.01, s.position.z);
      _obj.rotation.set(-Math.PI / 2, 0, 0);
      _obj.updateMatrix();
      ringRef.current!.setMatrixAt(i, _obj.matrix);
    });
    
    bodyRef.current.instanceMatrix.needsUpdate = true;
    headRef.current.instanceMatrix.needsUpdate = true;
    ringRef.current.instanceMatrix.needsUpdate = true;
  }, [survivors]);

  return (
    <group>
      <instancedMesh ref={bodyRef} args={[bodyGeom, bodyMat, survivors.length]} castShadow />
      <instancedMesh ref={headRef} args={[headGeom, bodyMat, survivors.length]} castShadow />
      <instancedMesh ref={ringRef} args={[ringGeom, ringMat, survivors.length]} />
      
      {/* Status Labels */}
      {survivors.map((s: Survivor) => (
        <Html
          key={s.id}
          position={[s.position.x, 2.5, s.position.z]}
          center
          distanceFactor={15}
          occlude
        >
          <div className="status-label flex items-center justify-center bg-black/60 backdrop-blur-sm rounded-full w-8 h-8 border border-white/20 shadow-lg text-lg animate-bounce-subtle">
            {icon}
          </div>
        </Html>
      ))}
    </group>
  );
}
