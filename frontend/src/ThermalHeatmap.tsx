import { useRef, useEffect, useMemo } from 'react';
import * as THREE from 'three';
import { useStore } from './store';

const MAX_TILES = 2000;

/**
 * Map a temperature in °C to a colour.
 *
 * Gradient (cold → hot):
 *   ≤12°C  deep cold blue   #001a4d
 *   18°C   cool blue        #0055cc
 *   24°C   cyan             #00bbcc
 *   28°C   warm yellow      #ffdd00
 *   34°C   orange           #ff6600
 *   ≥37°C  hot white        #ffffff  (survivor body heat)
 */
function tempToColor(temp: number, out: THREE.Color): THREE.Color {
  if (temp <= 12) return out.set('#001a4d');
  if (temp <= 18) return out.setRGB(
    THREE.MathUtils.mapLinear(temp, 12, 18, 0.0, 0.0),
    THREE.MathUtils.mapLinear(temp, 12, 18, 0.1, 0.33),
    THREE.MathUtils.mapLinear(temp, 12, 18, 0.3, 0.8),
  );
  if (temp <= 24) return out.setRGB(
    0,
    THREE.MathUtils.mapLinear(temp, 18, 24, 0.33, 0.73),
    THREE.MathUtils.mapLinear(temp, 18, 24, 0.8, 0.8),
  );
  if (temp <= 28) return out.setRGB(
    THREE.MathUtils.mapLinear(temp, 24, 28, 0.0, 1.0),
    THREE.MathUtils.mapLinear(temp, 24, 28, 0.73, 0.87),
    THREE.MathUtils.mapLinear(temp, 24, 28, 0.8, 0.0),
  );
  if (temp <= 34) return out.setRGB(
    1.0,
    THREE.MathUtils.mapLinear(temp, 28, 34, 0.87, 0.4),
    0.0,
  );
  return out.setRGB(
    1.0,
    THREE.MathUtils.mapLinear(temp, 34, 37, 0.4, 1.0),
    THREE.MathUtils.mapLinear(temp, 34, 37, 0.0, 1.0),
  );
}

/**
 * ThermalHeatmap
 *
 * Renders accumulated scan data as coloured 1×1 ground tiles.
 * Each cell the drone has scanned gets a colour based on the highest
 * temperature ever recorded there — creating a persistent fog-of-war
 * heat overlay on the terrain.
 *
 * Uses InstancedMesh (pre-allocated to MAX_TILES) for performance.
 * Unused slots are hidden by scaling to zero.
 */
export function ThermalHeatmap() {
  const heatTiles = useStore((state) => state.heatTiles);
  const meshRef = useRef<THREE.InstancedMesh>(null);

  // Flat horizontal plane geometry — rotated to lie on the XZ ground plane
  const geometry = useMemo(() => {
    const g = new THREE.PlaneGeometry(1, 1);
    g.rotateX(-Math.PI / 2);
    return g;
  }, []);

  // Material with per-instance colour; slightly above ground to avoid z-fighting
  const material = useMemo(() => new THREE.MeshBasicMaterial({
    transparent: true,
    opacity: 0.55,
    depthWrite: false,
    vertexColors: true,
  }), []);

  useEffect(() => {
    const mesh = meshRef.current;
    if (!mesh) return;

    const dummy = new THREE.Object3D();
    const color = new THREE.Color();
    const entries = Object.entries(heatTiles);
    const count = Math.min(entries.length, MAX_TILES);

    // Update occupied tiles
    entries.slice(0, MAX_TILES).forEach(([key, temp], i) => {
      const [x, y] = key.split(',').map(Number);
      dummy.position.set(x, -0.47, y); // just above ground plane at y = -0.5
      dummy.scale.set(1, 1, 1);
      dummy.updateMatrix();
      mesh.setMatrixAt(i, dummy.matrix);
      mesh.setColorAt(i, tempToColor(temp, color));
    });

    // Hide unused slots by scaling to zero
    dummy.scale.set(0, 0, 0);
    dummy.updateMatrix();
    for (let i = count; i < MAX_TILES; i++) {
      mesh.setMatrixAt(i, dummy.matrix);
    }

    mesh.count = count;
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  }, [heatTiles]);

  return (
    <instancedMesh
      ref={meshRef}
      args={[geometry, material, MAX_TILES]}
      frustumCulled={false}
    />
  );
}
