import { useMemo, useRef, useEffect } from 'react';
import * as THREE from 'three';
import { useStore, type BlockedArea } from './store';

// Seeded random number generator for deterministic random values
function seededRandom(seed: number): () => number {
  let state = seed;
  return () => {
    state = (state * 1103515245 + 12345) & 0x7fffffff;
    return state / 0x7fffffff;
  };
}

// Color palettes for different debris types
const CONCRETE_COLORS = ['#808080', '#707070', '#909090', '#606060', '#a0a0a0', '#757575'];
const RUST_COLORS = ['#8b4513', '#a0522d', '#704214', '#8b5a2b', '#6b4423'];

/**
 * Generate procedural noise texture for roughness variation
 */
function createNoiseTexture(size: number = 64): THREE.DataTexture {
  const data = new Uint8Array(size * size * 4);
  for (let i = 0; i < size * size; i++) {
    const value = Math.random() * 255;
    data[i * 4] = value;
    data[i * 4 + 1] = value;
    data[i * 4 + 2] = value;
    data[i * 4 + 3] = 255;
  }
  const texture = new THREE.DataTexture(data, size, size, THREE.RGBAFormat);
  texture.needsUpdate = true;
  return texture;
}

/**
 * Generate normal map texture for surface detail
 */
function createNormalMap(size: number = 64): THREE.DataTexture {
  const data = new Uint8Array(size * size * 4);
  for (let i = 0; i < size * size; i++) {
    // Random normal vector variations
    const nx = (Math.random() - 0.5) * 0.3;
    const ny = (Math.random() - 0.5) * 0.3;
    const nz = 1.0;
    
    // Normalize and convert to color
    const len = Math.sqrt(nx * nx + ny * ny + nz * nz);
    data[i * 4] = ((nx / len) * 0.5 + 0.5) * 255;
    data[i * 4 + 1] = ((ny / len) * 0.5 + 0.5) * 255;
    data[i * 4 + 2] = ((nz / len) * 0.5 + 0.5) * 255;
    data[i * 4 + 3] = 255;
  }
  const texture = new THREE.DataTexture(data, size, size, THREE.RGBAFormat);
  texture.needsUpdate = true;
  return texture;
}

/**
 * Rubble Component
 * Hyper-realistic earthquake debris using PBR materials and instanced rendering
 */
export function Rubble() {
  const blockedAreas = useStore(state => state.blockedAreas);
  
  // Refs for instanced meshes
  const concreteMeshRef = useRef<THREE.InstancedMesh>(null);
  const metalMeshRef = useRef<THREE.InstancedMesh>(null);
  const smallDebrisMeshRef = useRef<THREE.InstancedMesh>(null);
  
  // Create PBR materials with procedural textures using useMemo
  const { concreteMaterial, rustMetalMaterial, darkConcreteMaterial } = useMemo(() => {
    const noiseTexture = createNoiseTexture(64);
    const normalMap = createNormalMap(64);
    
    // Concrete PBR material
    const concreteMat = new THREE.MeshStandardMaterial({
      color: '#808080',
      roughness: 0.92,
      metalness: 0.05,
      roughnessMap: noiseTexture,
      normalMap: normalMap,
      normalScale: new THREE.Vector2(0.3, 0.3),
    });
    
    // Darker concrete for variety
    const darkConcreteMat = new THREE.MeshStandardMaterial({
      color: '#505050',
      roughness: 0.95,
      metalness: 0.02,
      roughnessMap: noiseTexture,
    });
    
    // Rusty metal material
    const rustMetalMat = new THREE.MeshStandardMaterial({
      color: '#8b4513',
      roughness: 0.45,
      metalness: 0.75,
      roughnessMap: noiseTexture,
    });
    
    return {
      concreteMaterial: concreteMat,
      rustMetalMaterial: rustMetalMat,
      darkConcreteMaterial: darkConcreteMat,
    };
  }, []);
  
  // Create different geometries for variety
  const { concreteGeometry, metalGeometry, smallDebrisGeometry } = useMemo(() => {
    return {
      // Large concrete chunks - dodecahedron for irregular shape
      concreteGeometry: new THREE.DodecahedronGeometry(1, 0),
      // Twisted metal pieces - icosahedron for angular look
      metalGeometry: new THREE.IcosahedronGeometry(1, 0),
      // Small debris - mixed tetrahedrons for sharp fragments
      smallDebrisGeometry: new THREE.TetrahedronGeometry(1, 0),
    };
  }, []);
  
  // Generate debris data from blocked areas or fallback
  const { concretePieces, metalPieces, smallDebrisPieces } = useMemo(() => {
    const random = seededRandom(12345);
    const concrete: Array<{
      position: [number, number, number];
      scale: [number, number, number];
      rotation: [number, number, number];
    }> = [];
    const metal: Array<{
      position: [number, number, number];
      scale: [number, number, number];
      rotation: [number, number, number];
    }> = [];
    const smallDebris: Array<{
      position: [number, number, number];
      scale: [number, number, number];
      rotation: [number, number, number];
    }> = [];
    
    // Use blocked areas if available
    if (blockedAreas && blockedAreas.length > 0) {
      blockedAreas.forEach((area: BlockedArea) => {
        const x = area.x;
        const z = area.y; // Backend Y maps to Three.js Z
        const baseRadius = Math.max(area.radius * 0.8, 1);
        
        // Create pile formation around blocked area center
        const piecesInPile = Math.floor(baseRadius * 3) + 2;
        
        for (let i = 0; i < piecesInPile; i++) {
          // Random offset within pile radius
          const offsetX = (random() - 0.5) * baseRadius * 2;
          const offsetZ = (random() - 0.5) * baseRadius * 2;
          const distFromCenter = Math.sqrt(offsetX * offsetX + offsetZ * offsetZ);
          
          if (distFromCenter <= baseRadius) {
            // Determine piece type (70% concrete, 20% metal, 10% small debris)
            const typeRoll = random();
            
            if (typeRoll < 0.7) {
              // Large concrete chunk
              const scale = random() * 1.5 + 0.5;
              concrete.push({
                position: [x + offsetX, scale * 0.4, z + offsetZ],
                scale: [scale, scale * 0.6, scale],
                rotation: [
                  random() * Math.PI * 0.4,
                  random() * Math.PI * 2,
                  random() * Math.PI * 0.4,
                ],
              });
            } else if (typeRoll < 0.9) {
              // Metal/rebar piece
              const scale = random() * 1.2 + 0.3;
              metal.push({
                position: [x + offsetX, scale * 0.3, z + offsetZ],
                scale: [scale * 0.3, scale, scale * 0.3], // Elongated
                rotation: [
                  random() * Math.PI,
                  random() * Math.PI * 2,
                  random() * Math.PI,
                ],
              });
            } else {
              // Small debris
              const scale = random() * 0.5 + 0.15;
              smallDebris.push({
                position: [x + offsetX, scale * 0.3, z + offsetZ],
                scale: [scale, scale, scale],
                rotation: [
                  random() * Math.PI * 2,
                  random() * Math.PI * 2,
                  random() * Math.PI * 2,
                ],
              });
            }
          }
        }
      });
    }
    
    // Fallback: Generate random debris field for demo
    if (concrete.length === 0 && metal.length === 0 && smallDebris.length === 0) {
      // Large concrete blocks
      for (let i = 0; i < 40; i++) {
        const position: [number, number, number] = [
          (random() - 0.5) * 60,
          random() * 0.4,
          (random() - 0.5) * 60,
        ];
        
        const scale: [number, number, number] = [
          random() * 2.5 + 0.8,
          random() * 1.5 + 0.4,
          random() * 2.5 + 0.8,
        ];
        
        concrete.push({
          position,
          scale,
          rotation: [
            (random() - 0.5) * 0.5,
            random() * Math.PI * 2,
            (random() - 0.5) * 0.5,
          ],
        });
      }
      
      // Metal/rebar pieces
      for (let i = 0; i < 25; i++) {
        const position: [number, number, number] = [
          (random() - 0.5) * 70,
          random() * 0.3,
          (random() - 0.5) * 70,
        ];
        
        const scale: [number, number, number] = [
          random() * 0.4 + 0.1,
          random() * 2 + 0.5,
          random() * 0.4 + 0.1,
        ];
        
        metal.push({
          position,
          scale,
          rotation: [
            random() * Math.PI,
            random() * Math.PI * 2,
            random() * Math.PI * 0.5,
          ],
        });
      }
      
      // Small debris fragments
      for (let i = 0; i < 150; i++) {
        const position: [number, number, number] = [
          (random() - 0.5) * 80,
          random() * 0.15,
          (random() - 0.5) * 80,
        ];
        
        const scale: [number, number, number] = [
          random() * 0.6 + 0.1,
          random() * 0.6 + 0.1,
          random() * 0.6 + 0.1,
        ];
        
        smallDebris.push({
          position,
          scale,
          rotation: [
            random() * Math.PI * 2,
            random() * Math.PI * 2,
            random() * Math.PI * 2,
          ],
        });
      }
    }
    
    return { concretePieces: concrete, metalPieces: metal, smallDebrisPieces: smallDebris };
  }, [blockedAreas]);
  
  // Apply instance matrices
  useEffect(() => {
    const dummy = new THREE.Object3D();
    
    // Update concrete instances
    if (concreteMeshRef.current && concretePieces.length > 0) {
      const mesh = concreteMeshRef.current;
      concretePieces.forEach((piece, i) => {
        dummy.position.set(...piece.position);
        dummy.scale.set(...piece.scale);
        dummy.rotation.set(piece.rotation[0], piece.rotation[1], piece.rotation[2]);
        dummy.updateMatrix();
        mesh.setMatrixAt(i, dummy.matrix);
      });
      mesh.instanceMatrix.needsUpdate = true;
      mesh.count = concretePieces.length;
    }
    
    // Update metal instances
    if (metalMeshRef.current && metalPieces.length > 0) {
      const mesh = metalMeshRef.current;
      metalPieces.forEach((piece, i) => {
        dummy.position.set(...piece.position);
        dummy.scale.set(...piece.scale);
        dummy.rotation.set(piece.rotation[0], piece.rotation[1], piece.rotation[2]);
        dummy.updateMatrix();
        mesh.setMatrixAt(i, dummy.matrix);
      });
      mesh.instanceMatrix.needsUpdate = true;
      mesh.count = metalPieces.length;
    }
    
    // Update small debris instances
    if (smallDebrisMeshRef.current && smallDebrisPieces.length > 0) {
      const mesh = smallDebrisMeshRef.current;
      smallDebrisPieces.forEach((piece, i) => {
        dummy.position.set(...piece.position);
        dummy.scale.set(...piece.scale);
        dummy.rotation.set(piece.rotation[0], piece.rotation[1], piece.rotation[2]);
        dummy.updateMatrix();
        mesh.setMatrixAt(i, dummy.matrix);
      });
      mesh.instanceMatrix.needsUpdate = true;
      mesh.count = smallDebrisPieces.length;
    }
  }, [concretePieces, metalPieces, smallDebrisPieces]);
  
  // Static rubble elements - destroyed structures
  const staticRubble = useMemo(() => (
    <>
      {/* =====================================================================
          RUINED BUILDINGS - Different heights for depth
      ===================================================================== */}
      
      {/* Tall ruined building - partially collapsed tower */}
      <group position={[-25, 0, -20]}>
        {/* Main structure - tilted */}
        <mesh position={[0, 6, 0]} rotation={[0.05, 0.3, 0.08]} castShadow receiveShadow>
          <boxGeometry args={[5, 12, 5]} />
          <meshStandardMaterial color="#4a4a4a" roughness={0.9} metalness={0.1} />
        </mesh>
        {/* Broken top section */}
        <mesh position={[1.5, 13, 0.5]} rotation={[0.2, 0.8, 0.15]} castShadow receiveShadow>
          <boxGeometry args={[3, 2.5, 3]} />
          <meshStandardMaterial color="#555555" roughness={0.92} metalness={0.05} />
        </mesh>
        {/* Windows (dark recesses) */}
        <mesh position={[0, 4, 2.51]}>
          <planeGeometry args={[1.5, 2]} />
          <meshStandardMaterial color="#1a1a1a" roughness={1} />
        </mesh>
        <mesh position={[0, 8, 2.51]}>
          <planeGeometry args={[1.5, 2]} />
          <meshStandardMaterial color="#1a1a1a" roughness={1} />
        </mesh>
      </group>

      {/* Medium ruined building - half collapsed */}
      <group position={[20, 0, -15]}>
        <mesh position={[0, 4, 0]} rotation={[-0.1, -0.5, 0.05]} castShadow receiveShadow>
          <boxGeometry args={[6, 8, 5]} />
          <meshStandardMaterial color="#525252" roughness={0.88} metalness={0.08} />
        </mesh>
        {/* Collapsed section */}
        <mesh position={[2, 1.5, 2]} rotation={[0.3, 0.2, 0.4]} castShadow receiveShadow>
          <boxGeometry args={[3, 3, 2]} />
          <meshStandardMaterial color="#5a5a5a" roughness={0.9} metalness={0.05} />
        </mesh>
      </group>

      {/* Low rubble - destroyed small structure */}
      <group position={[30, 0, 10]}>
        <mesh position={[0, 1.5, 0]} rotation={[0.15, 0.8, 0.1]} castShadow receiveShadow>
          <boxGeometry args={[4, 3, 4]} />
          <meshStandardMaterial color="#606060" roughness={0.92} metalness={0.05} />
        </mesh>
        <mesh position={[1, 0.5, 1.5]} castShadow receiveShadow>
          <dodecahedronGeometry args={[1, 0]} />
          <meshStandardMaterial color="#555555" roughness={0.9} metalness={0.06} />
        </mesh>
      </group>

      {/* Broken pillars - varying heights */}
      <group position={[-10, 0, -25]}>
        <mesh position={[0, 3, 0]} castShadow receiveShadow>
          <cylinderGeometry args={[0.6, 0.7, 6, 12]} />
          <meshStandardMaterial color="#6a6a6a" roughness={0.85} metalness={0.1} />
        </mesh>
        <mesh position={[4, 2, -2]} rotation={[0.2, 0, 0.1]} castShadow receiveShadow>
          <cylinderGeometry args={[0.5, 0.6, 4, 12]} />
          <meshStandardMaterial color="#5f5f5f" roughness={0.87} metalness={0.08} />
        </mesh>
        <mesh position={[-3, 1.5, 3]} rotation={[0.3, 0.5, 0.15]} castShadow receiveShadow>
          <cylinderGeometry args={[0.4, 0.5, 3, 12]} />
          <meshStandardMaterial color="#656565" roughness={0.86} metalness={0.07} />
        </mesh>
      </group>

      {/* =====================================================================
          COLLAPSED WALLS
      ===================================================================== */}
      
      {/* Collapsed wall section 1 */}
      <mesh position={[-18, 1.2, -12]} rotation={[0.15, 0.6, 0.08]} castShadow receiveShadow>
        <boxGeometry args={[10, 3.5, 0.6]} />
        <meshStandardMaterial color="#555555" roughness={0.92} metalness={0.05} />
      </mesh>
      
      {/* Collapsed wall section 2 - tilted */}
      <mesh position={[-14, 0.6, -9]} rotation={[0.25, 1.2, 0.12]} castShadow receiveShadow>
        <boxGeometry args={[6, 2.2, 0.5]} />
        <meshStandardMaterial color="#484848" roughness={0.94} metalness={0.03} />
      </mesh>

      {/* Long broken wall */}
      <mesh position={[15, 0.8, -8]} rotation={[0.1, -0.3, 0.05]} castShadow receiveShadow>
        <boxGeometry args={[12, 1.8, 0.4]} />
        <meshStandardMaterial color="#505050" roughness={0.91} metalness={0.05} />
      </mesh>

      {/* =====================================================================
          RUBBLE PILES
      ===================================================================== */}
      
      {/* Rubble pile - large concrete chunks */}
      <group position={[12, 0, 18]}>
        <mesh position={[0, 1.5, 0]} rotation={[0.2, 0.5, 0.1]} castShadow receiveShadow>
          <dodecahedronGeometry args={[2.2, 0]} />
          <meshStandardMaterial color="#606060" roughness={0.9} metalness={0.05} />
        </mesh>
        <mesh position={[1.5, 0.8, 1]} rotation={[0.4, 1.2, 0.2]} castShadow receiveShadow>
          <dodecahedronGeometry args={[1.5, 0]} />
          <meshStandardMaterial color="#707070" roughness={0.92} metalness={0.04} />
        </mesh>
        <mesh position={[-1.2, 0.5, 1.5]} rotation={[0.1, 2.1, 0.15]} castShadow receiveShadow>
          <dodecahedronGeometry args={[1.2, 0]} />
          <meshStandardMaterial color="#555555" roughness={0.88} metalness={0.06} />
        </mesh>
        <mesh position={[0.8, 0.3, -1]} rotation={[0.3, 0.8, 0.25]} castShadow receiveShadow>
          <icosahedronGeometry args={[0.9, 0]} />
          <meshStandardMaterial color="#656565" roughness={0.91} metalness={0.04} />
        </mesh>
      </group>
      
      {/* Rubble pile - secondary */}
      <group position={[-8, 0, 20]}>
        <mesh position={[0, 0.9, 0]} rotation={[0.15, 0.3, 0.1]} castShadow receiveShadow>
          <dodecahedronGeometry args={[1.5, 0]} />
          <meshStandardMaterial color="#5a5a5a" roughness={0.9} metalness={0.05} />
        </mesh>
        <mesh position={[1, 0.4, 0.5]} castShadow receiveShadow>
          <icosahedronGeometry args={[0.8, 0]} />
          <meshStandardMaterial color="#686868" roughness={0.88} metalness={0.04} />
        </mesh>
      </group>

      {/* Additional rubble piles at different locations */}
      <group position={[-30, 0, 5]}>
        <mesh position={[0, 1, 0]} rotation={[0.25, 1.5, 0.1]} castShadow receiveShadow>
          <dodecahedronGeometry args={[1.8, 0]} />
          <meshStandardMaterial color="#595959" roughness={0.91} metalness={0.05} />
        </mesh>
        <mesh position={[1.2, 0.5, 0.8]} castShadow receiveShadow>
          <dodecahedronGeometry args={[1, 0]} />
          <meshStandardMaterial color="#626262" roughness={0.89} metalness={0.06} />
        </mesh>
      </group>

      <group position={[25, 0, -25]}>
        <mesh position={[0, 0.7, 0]} rotation={[0.1, 2.0, 0.2]} castShadow receiveShadow>
          <dodecahedronGeometry args={[1.3, 0]} />
          <meshStandardMaterial color="#575757" roughness={0.9} metalness={0.05} />
        </mesh>
      </group>

      {/* =====================================================================
          EXPOSED REBAR/METAL PIECES
      ===================================================================== */}
      
      {/* Exposed rebar/metal pieces */}
      <mesh position={[-16, 0.3, -10]} rotation={[Math.PI * 0.3, 0.5, 0.2]} castShadow receiveShadow>
        <cylinderGeometry args={[0.08, 0.1, 2.5, 6]} />
        <meshStandardMaterial color="#6b4423" roughness={0.5} metalness={0.7} />
      </mesh>
      <mesh position={[-15, 0.25, -11]} rotation={[Math.PI * 0.4, 1.2, 0.3]} castShadow receiveShadow>
        <cylinderGeometry args={[0.06, 0.08, 1.8, 5]} />
        <meshStandardMaterial color="#704214" roughness={0.55} metalness={0.65} />
      </mesh>
      <mesh position={[10, 0.2, 16]} rotation={[Math.PI * 0.35, 2.1, 0.15]} castShadow receiveShadow>
        <cylinderGeometry args={[0.07, 0.09, 2.2, 6]} />
        <meshStandardMaterial color="#8b5a2b" roughness={0.48} metalness={0.72} />
      </mesh>
      
      {/* More rebar scattered around */}
      <mesh position={[-22, 0.25, -18]} rotation={[Math.PI * 0.25, 0.8, 0.1]} castShadow receiveShadow>
        <cylinderGeometry args={[0.05, 0.07, 2, 5]} />
        <meshStandardMaterial color="#5a3a1a" roughness={0.55} metalness={0.65} />
      </mesh>
      <mesh position={[18, 0.2, -12]} rotation={[Math.PI * 0.3, 1.5, 0.2]} castShadow receiveShadow>
        <cylinderGeometry args={[0.06, 0.08, 1.5, 5]} />
        <meshStandardMaterial color="#6b4423" roughness={0.52} metalness={0.68} />
      </mesh>
      <mesh position={[28, 0.15, 8]} rotation={[Math.PI * 0.35, 2.2, 0.1]} castShadow receiveShadow>
        <cylinderGeometry args={[0.04, 0.06, 1.8, 5]} />
        <meshStandardMaterial color="#704214" roughness={0.5} metalness={0.7} />
      </mesh>
    </>
  ), []);
  
  // Calculate instance counts
  const maxConcrete = Math.max(concretePieces.length, 1);
  const maxMetal = Math.max(metalPieces.length, 1);
  const maxSmallDebris = Math.max(smallDebrisPieces.length, 1);
  
  return (
    <group>
      {/* Instanced concrete debris */}
      <instancedMesh
        ref={concreteMeshRef}
        args={[concreteGeometry, concreteMaterial, maxConcrete]}
        castShadow
        receiveShadow
      />
      
      {/* Instanced metal debris */}
      <instancedMesh
        ref={metalMeshRef}
        args={[metalGeometry, rustMetalMaterial, maxMetal]}
        castShadow
        receiveShadow
      />
      
      {/* Instanced small debris fragments */}
      <instancedMesh
        ref={smallDebrisMeshRef}
        args={[smallDebrisGeometry, darkConcreteMaterial, maxSmallDebris]}
        castShadow
        receiveShadow
      />
      
      {/* Static rubble elements */}
      {staticRubble}
    </group>
  );
}
