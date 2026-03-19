import { useRef } from 'react'
import * as THREE from 'three'
import type { Survivor } from './store'

/**
 * Individual Survivor component - renders a human-shaped figure with thermal visualization
 * Uses simple capsule/sphere geometry that works reliably for multiple instances
 */
export function Human({ survivor }: { survivor: Survivor }) {
  const groupRef = useRef<THREE.Group>(null)
  const isUndetected = survivor.status === 'UNDETECTED'
  
  // Colors based on detection status
  const bodyColor = isUndetected ? '#446688' : '#ff6622'
  const emissiveColor = isUndetected ? '#223344' : '#ff4400'
  const emissiveIntensity = isUndetected ? 0.1 : 0.5

  return (
    <group
      ref={groupRef}
      position={[survivor.position.x, survivor.position.y, survivor.position.z]}
    >
      {/* Body - capsule shape */}
      <mesh position={[0, 0.9, 0]} castShadow>
        <capsuleGeometry args={[0.3, 1, 4, 8]} />
        <meshStandardMaterial
          color={bodyColor}
          emissive={emissiveColor}
          emissiveIntensity={emissiveIntensity}
          transparent={isUndetected}
          opacity={isUndetected ? 0.6 : 1}
        />
      </mesh>
      
      {/* Head - sphere */}
      <mesh position={[0, 1.8, 0]} castShadow>
        <sphereGeometry args={[0.25, 16, 16]} />
        <meshStandardMaterial
          color={bodyColor}
          emissive={emissiveColor}
          emissiveIntensity={emissiveIntensity}
          transparent={isUndetected}
          opacity={isUndetected ? 0.6 : 1}
        />
      </mesh>

      {/* Point light for thermal glow (only when detected) */}
      {!isUndetected && (
        <pointLight position={[0, 1.5, 0]} color="#ff4400" intensity={1.5} distance={10} />
      )}

      {/* Ground ring indicator */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.01, 0]}>
        <ringGeometry args={[0.4, isUndetected ? 1.0 : 1.2, 32]} />
        <meshBasicMaterial
          color={isUndetected ? '#4488ff' : '#ff5500'}
          transparent
          opacity={isUndetected ? 0.08 : 0.15}
          side={THREE.DoubleSide}
        />
      </mesh>
    </group>
  )
}

export function getAllModelUrls(): string[] {
  return []
}

export default Human
