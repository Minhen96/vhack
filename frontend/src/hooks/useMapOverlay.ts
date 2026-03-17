/**
 * useMapOverlay — manages which overlay mode is active on CommandMap2D.
 * Kept as a hook (not store) because overlay state is local to the map view.
 */
import { useState, useCallback } from 'react'
import type { OverlayMode } from '@/lib/types'

interface MapOverlay {
  overlay: OverlayMode
  setOverlay: (mode: OverlayMode) => void
  toggleOverlay: (mode: OverlayMode) => void
  showPaths: boolean
  togglePaths: () => void
  showMesh: boolean
  toggleMesh: () => void
}

export function useMapOverlay(): MapOverlay {
  const [overlay, setOverlay] = useState<OverlayMode>('none')
  const [showPaths, setShowPaths] = useState(false)
  const [showMesh, setShowMesh] = useState(false)

  const toggleOverlay = useCallback(
    (mode: OverlayMode) => setOverlay((prev) => (prev === mode ? 'none' : mode)),
    [],
  )

  const togglePaths = useCallback(() => setShowPaths((v) => !v), [])
  const toggleMesh = useCallback(() => setShowMesh((v) => !v), [])

  return { overlay, setOverlay, toggleOverlay, showPaths, togglePaths, showMesh, toggleMesh }
}
