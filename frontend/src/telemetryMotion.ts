export type Coordinate = [number, number];
const MAX_LATITUDE = 85.0511287798066;

export function validCoordinate(point: Coordinate): boolean {
  return Array.isArray(point) && point.length === 2 && point.every(Number.isFinite)
    && Math.abs(point[0]) <= 180 && Math.abs(point[1]) <= 90;
}

// Interpolate in the map's Web Mercator plane, crossing the date line by
// the shortest path. Clamp only the rendering projection, never source data.
export function interpolatePosition(from: Coordinate, to: Coordinate, fraction: number): Coordinate {
  const t = Math.max(0, Math.min(1, fraction));
  const projectY = (latitude: number) => {
    const radians = Math.max(-MAX_LATITUDE, Math.min(MAX_LATITUDE, latitude)) * Math.PI / 180;
    return Math.log(Math.tan(Math.PI / 4 + radians / 2));
  };
  const delta = ((to[0] - from[0] + 540) % 360 + 360) % 360 - 180;
  const y = projectY(from[1]) + (projectY(to[1]) - projectY(from[1])) * t;
  return [from[0] + delta * t, (2 * Math.atan(Math.exp(y)) - Math.PI / 2) * 180 / Math.PI];
}

export function movementDuration(previous: number | undefined, next: number, speed: number, animate: boolean): number {
  const gap = previous === undefined ? 0 : next - previous;
  // A long GPS outage gives no evidence of the path travelled in between.
  if (!animate || !Number.isFinite(gap) || gap <= 0 || gap > 90) return 0;
  return Math.min(900, Math.max(80, gap / Math.max(1, Number.isFinite(speed) ? speed : 1) * 1000));
}
