import { useRef, useMemo, Suspense } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import {
  OrbitControls,
  Environment,
  Loader,
} from '@react-three/drei';
import {
  EffectComposer,
  Bloom,
  Vignette,
  SSAO,
  SMAA,
  ColorAverage,
} from '@react-three/postprocessing';
import { BlendFunction } from 'postprocessing';
import * as THREE from 'three';

import { Drone, Drones } from './Drone';
import { Rubble } from './Rubble';
import { Survivors } from './Survivors';
import { Buildings } from './Buildings';
import { CommandBase } from './CommandBase';
import { ThermalHeatmap } from './ThermalHeatmap';

// Seeded random number generator for deterministic random values
function seededRandom(seed: number): () => number {
  let state = seed;
  return () => {
    state = (state * 1103515245 + 12345) & 0x7fffffff;
    return state / 0x7fffffff;
  };
}

/**
 * Dust Particle System
 * Uses InstancedMesh for performance (500-1000 particles)
 * Animated slowly floating in the air with brownish/gray tint
 */
function DustParticles({ count = 800 }: { count?: number }) {
  const meshRef = useRef<THREE.InstancedMesh>(null);
  const dummy = useMemo(() => new THREE.Object3D(), []);
  const randomRef = useRef(seededRandom(42));

  // Generate random initial positions and velocities
  const particles = useMemo(() => {
    const random = seededRandom(42); // Fixed seed for deterministic results
    const temp = [];
    for (let i = 0; i < count; i++) {
      temp.push({
        position: new THREE.Vector3(
          (random() - 0.5) * 100,
          random() * 20,
          (random() - 0.5) * 100
        ),
        velocity: new THREE.Vector3(
          (random() - 0.5) * 0.02,
          random() * 0.01 + 0.005,
          (random() - 0.5) * 0.02
        ),
        scale: random() * 0.15 + 0.05,
      });
    }
    return temp;
  }, [count]);

  useFrame(() => {
    if (!meshRef.current) return;

    particles.forEach((particle, i) => {
      // Update position
      particle.position.add(particle.velocity);

      // Wrap around when particles go out of bounds
      if (particle.position.y > 25) {
        particle.position.y = 0;
        const random = randomRef.current;
        particle.position.x = (random() - 0.5) * 100;
        particle.position.z = (random() - 0.5) * 100;
      }

      // Add slight horizontal drift
      particle.position.x += Math.sin(Date.now() * 0.001 + i) * 0.002;
      particle.position.z += Math.cos(Date.now() * 0.001 + i) * 0.002;

      // Update instance matrix
      dummy.position.copy(particle.position);
      dummy.scale.setScalar(particle.scale);
      dummy.updateMatrix();
      meshRef.current!.setMatrixAt(i, dummy.matrix);
    });

    meshRef.current.instanceMatrix.needsUpdate = true;
  });

  return (
    <instancedMesh
      ref={meshRef}
      args={[undefined, undefined, count]}
      castShadow={false}
      receiveShadow={false}
    >
      <sphereGeometry args={[0.1, 6, 6]} />
      <meshBasicMaterial
        color="#8b7355"
        transparent
        opacity={0.3}
        depthWrite={false}
      />
    </instancedMesh>
  );
}

/**
 * Ground Plane with sunset-lit rubble terrain
 */
function Ground() {
  // Create a procedural gritty texture with warm tones
  const groundTexture = useMemo(() => {
    const random = seededRandom(100); // Fixed seed for deterministic results
    const canvas = document.createElement('canvas');
    canvas.width = 512;
    canvas.height = 512;
    const ctx = canvas.getContext('2d')!;

    // Base warm dark brown-gray color (sunset-lit ground)
    ctx.fillStyle = '#2a2420';
    ctx.fillRect(0, 0, 512, 512);

    // Add noise/grain for grit with warm undertones
    for (let i = 0; i < 10000; i++) {
      const x = random() * 512;
      const y = random() * 512;
      const warmGray = random() * 40 + 30;
      ctx.fillStyle = `rgb(${warmGray}, ${warmGray - 5}, ${warmGray - 10})`;
      ctx.fillRect(x, y, 2, 2);
    }

    // Add rubble spots with warm brown tones
    for (let i = 0; i < 200; i++) {
      const x = random() * 512;
      const y = random() * 512;
      const size = random() * 8 + 2;
      ctx.fillStyle = `rgb(${random() * 25 + 35}, ${random() * 20 + 25}, ${random() * 15 + 20})`;
      ctx.beginPath();
      ctx.ellipse(x, y, size, size * 0.7, random() * Math.PI, 0, Math.PI * 2);
      ctx.fill();
    }

    const texture = new THREE.CanvasTexture(canvas);
    texture.wrapS = THREE.RepeatWrapping;
    texture.wrapT = THREE.RepeatWrapping;
    texture.repeat.set(20, 20);
    return texture;
  }, []);

  return (
    <mesh
      rotation={[-Math.PI / 2, 0, 0]}
      position={[0, -0.5, 0]}
      receiveShadow
    >
      <planeGeometry args={[200, 200]} />
      <meshStandardMaterial
        map={groundTexture}
        color="#3d322a"
        roughness={0.92}
        metalness={0.05}
      />
    </mesh>
  );
}

/**
 * Main Scene Component
 * Sets up the complete 3D environment for the Search and Rescue Drone Simulation
 * Photorealistic daytime earthquake rubble field with high-noon sunlight
 */
export function Scene() {
  return (
    <Canvas
      shadows
      shadow-mapSize-width={2048}
      shadow-mapSize-height={2048}
      camera={{
        position: [30, 25, 30],
        fov: 60,
        near: 0.1,
        far: 500,
      }}
      gl={{
        antialias: true,
        toneMapping: THREE.ACESFilmicToneMapping,
        toneMappingExposure: 1.2,
        powerPreference: 'high-performance',
      }}
      style={{ background: '#1a1520' }}
    >
      {/* Environment Map - Custom HDR for realistic PBR reflections */}
      <Environment files="/models/grasslands_sunset_1k.hdr" background={false} />

      {/* Fog - Sunset atmospheric haze */}
      <fog attach="fog" args={['#2d1f3d', 40, 150]} />

      {/* Lighting Setup - Dramatic Sunset */}
      
      {/* Ambient - Warm sunset fill */}
      <ambientLight intensity={0.3} color="#ffd4a3" />

      {/* Main Sun - Low angle sunset */}
      <directionalLight
        position={[-30, 15, -50]}
        intensity={3}
        color="#ff7b00"
        castShadow
        shadow-mapSize-width={2048}
        shadow-mapSize-height={2048}
        shadow-camera-far={200}
        shadow-camera-left={-60}
        shadow-camera-right={60}
        shadow-camera-top={60}
        shadow-camera-bottom={-60}
        shadow-bias={-0.0001}
      />

      {/* Secondary warm light - Orange glow */}
      <directionalLight
        position={[40, 20, 30]}
        intensity={1.5}
        color="#ff9500"
      />

      {/* Cool fill light - Blue hour from sky */}
      <directionalLight
        position={[0, 40, 0]}
        intensity={0.5}
        color="#4a6fa5"
      />

      {/* Rim light - Golden edge highlighting */}
      <directionalLight
        position={[50, 10, -20]}
        intensity={1}
        color="#ffb347"
      />

      {/* Hemisphere light - Sky/ground color blend */}
      <hemisphereLight
        color="#ff9966"
        groundColor="#2d1f3d"
        intensity={0.4}
      />

      {/* Ground Plane */}
      <Ground />

      {/* Thermal Heatmap - persistent fog-of-war heat overlay */}
      <ThermalHeatmap />

      {/* Dust Particle System */}
      <DustParticles count={800} />

      {/* Drones - Renders all drones from store */}
      <Drones />
      <Rubble />
      {/* Buildings - server-generated box obstacles */}
      <Buildings />
      {/* Survivors - Async GLTF models loaded with Suspense */}
      <Suspense fallback={null}>
        <Survivors />
      </Suspense>
      <CommandBase />

      {/* Camera Controls */}
      <OrbitControls
        enablePan={true}
        enableZoom={true}
        enableRotate={true}
        minDistance={5}
        maxDistance={100}
        maxPolarAngle={Math.PI / 2 - 0.1}
        target={[0, 0, 0]}
      />

      {/* Post-Processing Effects - Cinematic sunset look */}
      <EffectComposer enableNormalPass>
        {/* SSAO - Screen Space Ambient Occlusion */}
        <SSAO
          blendFunction={BlendFunction.MULTIPLY}
          samples={31}
          radius={0.15}
          intensity={25}
          luminanceInfluence={0.1}
          color={new THREE.Color('#000000')}
        />

        {/* SMAA - Subpixel Morphological Antialiasing */}
        <SMAA />

        {/* Bloom - Warm glow for sunset */}
        <Bloom
          luminanceThreshold={0.8}
          luminanceSmoothing={0.9}
          intensity={0.5}
          mipmapBlur
        />

        {/* Vignette - Cinematic framing */}
        <Vignette
          offset={0.3}
          darkness={0.4}
          blendFunction={BlendFunction.NORMAL}
        />
      </EffectComposer>
    </Canvas>
  );
}

export default Scene;
