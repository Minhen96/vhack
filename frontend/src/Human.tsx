import { useRef, useMemo } from 'react'
import { useFrame } from '@react-three/fiber'
import { useGLTF } from '@react-three/drei'
import * as THREE from 'three'
import type { Survivor } from './store'

// Model paths for all available human models
const MODEL_PATHS = [
  '/models/humans/Adventurer.glb',
  '/models/humans/Worker.glb',
] as const

type ModelPath = (typeof MODEL_PATHS)[number]

// Preload all models for instant loading
MODEL_PATHS.forEach((path) => {
  useGLTF.preload(path)
})

/**
 * Select a model path based on survivor ID for consistent model assignment
 */
function getModelPathForSurvivor(survivorId: string): ModelPath {
  // Create a simple hash from the survivor ID
  let hash = 0
  for (let i = 0; i < survivorId.length; i++) {
    const char = survivorId.charCodeAt(i)
    hash = ((hash << 5) - hash) + char
    hash = hash & hash // Convert to 32bit integer
  }
  // Use positive hash modulo model count
  const index = Math.abs(hash) % MODEL_PATHS.length
  return MODEL_PATHS[index]
}

/**
 * Individual Human component with GLTF model and thermal visualization
 */
export function Human({ survivor }: { survivor: Survivor }) {
  const modelPath = useMemo(() => getModelPathForSurvivor(survivor.id), [survivor.id])
  const { scene } = useGLTF(modelPath)
  const groupRef = useRef<THREE.Group>(null)
  const emissiveIntensityRef = useRef(0)

  // Create a unique ID for raycaster detection (S1, S2, S3, etc.)
  const survivorNumber = useMemo(() => {
    // Extract number from survivor ID or generate based on hash
    const match = survivor.id.match(/\d+/)
    if (match) {
      return `S${match[0]}`
    }
    // Fallback: generate sequential number from position
    const hash = Math.floor(
      Math.abs(survivor.position.x * 31 + survivor.position.z * 17) % 100
    )
    return `S${hash + 1}`
  }, [survivor.id, survivor.position.x, survivor.position.z])

  // Clone and enhance materials for thermal visualization
  const enhancedScene = useMemo(() => {
    const clonedScene = scene.clone(true)
    
    clonedScene.traverse((child) => {
      if (child instanceof THREE.Mesh) {
        // Clone material to avoid sharing issues
        const originalMaterial = child.material as THREE.MeshStandardMaterial
        const clonedMaterial = originalMaterial.clone()
        
        // Emissive color: dim blue for undetected, thermal orange for detected
        clonedMaterial.emissive = new THREE.Color(survivor.status === 'UNDETECTED' ? '#224466' : '#ff4400')
        clonedMaterial.emissiveIntensity = survivor.status === 'UNDETECTED' ? 0.05 : 0.3
        clonedMaterial.transparent = survivor.status === 'UNDETECTED'
        clonedMaterial.opacity = survivor.status === 'UNDETECTED' ? 0.4 : 1.0
        clonedMaterial.needsUpdate = true
        
        // Store reference for animation
        child.userData.isSurvivor = true
        child.userData.id = survivorNumber
        child.material = clonedMaterial
        
        // Enable shadows
        child.castShadow = true
        child.receiveShadow = true
      }
    })
    
    return clonedScene
  }, [scene, survivorNumber])

  const isUndetected = survivor.status === 'UNDETECTED'

  // Animate thermal pulsation (only for detected survivors)
  useFrame((state) => {
    if (isUndetected) return
    const time = state.clock.getElapsedTime()
    emissiveIntensityRef.current = Math.sin(time * 2) * 0.2 + 0.4
    if (groupRef.current) {
      groupRef.current.traverse((child) => {
        if (child instanceof THREE.Mesh) {
          const material = child.material as THREE.MeshStandardMaterial
          if (material.emissive) {
            material.emissiveIntensity = emissiveIntensityRef.current
          }
        }
      })
    }
  })

  return (
    <group
      ref={groupRef}
      position={[survivor.position.x, survivor.position.y, survivor.position.z]}
      rotation={[0, Math.PI, 0]}
      scale={0.8}
    >
      <primitive object={enhancedScene} />

      {/* Dim ghost indicator for undetected, bright thermal glow when detected */}
      {isUndetected ? (
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.01, 0]}>
          <ringGeometry args={[0.4, 1.0, 32]} />
          <meshBasicMaterial color="#4488ff" transparent opacity={0.08} side={THREE.DoubleSide} />
        </mesh>
      ) : (
        <>
          <pointLight position={[0, 1, 0]} color="#ff4400" intensity={0.5} distance={5} decay={2} />
          <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.01, 0]}>
            <ringGeometry args={[0.4, 1.2, 32]} />
            <meshBasicMaterial color="#ff5500" transparent opacity={0.15} side={THREE.DoubleSide} />
          </mesh>
        </>
      )}
    </group>
  )
}

/**
 * Get all unique survivor IDs from store for the Preload component
 */
export function getAllModelUrls(): string[] {
  return [...MODEL_PATHS]
}

export default Human
