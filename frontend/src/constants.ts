/**
 * Unified Sensor & Camera Constants
 * Use these to ensure absolute parity between the pilot's FPV camera 
 * and the drone's visual sensors (spotlight, sensor cone).
 */

export const SENSOR_CONFIG = {
  // Pivot point (Nose of the drone)
  PIVOT_OFFSET: [0, 0, 0.7] as [number, number, number],
  
  // Multipliers
  ELEVATION_FACTOR: 0.5, // 50% pitch relative to telemetry
  
  // Damping Factors (Higher = More Responsive)
  DAMP_POS: 5.0,
  DAMP_ROT_Y: 5.0,
  DAMP_ROT_X: 5.0,
  DAMP_ROLL: 5.0,
  
  // Smoothing
  FOV_LERP: 0.1,
  
  // Interaction
  VIBRATION_SHAKE: 0.015,
};
