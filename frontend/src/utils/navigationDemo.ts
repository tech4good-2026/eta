interface MapPoint {
  lat: number;
  lng: number;
}

export function createDemoOffRouteCoordinate(points: MapPoint[], fallback: MapPoint) {
  const start = points[0] || fallback;
  const end = points.at(-1) || fallback;
  const deltaLat = end.lat - start.lat;
  const deltaLng = end.lng - start.lng;
  const length = Math.hypot(deltaLat, deltaLng);
  const offset = 0.0015;

  if (length === 0) {
    return { latitude: start.lat + offset, longitude: start.lng - offset };
  }
  return {
    latitude: start.lat + (deltaLng / length) * offset,
    longitude: start.lng - (deltaLat / length) * offset,
  };
}
