import { DomUtil, type ZoomAnimEvent } from 'leaflet';
import { useEffect, useMemo, useRef } from 'react';
import { Pane, useMap } from 'react-leaflet';

import { buildFogSurface } from '../fogSurface';
import type { FogLayerCell } from '../types';

export default function FogSurfaceLayer({ cells }: { cells: FogLayerCell[] }) {
  const map = useMap();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const surface = useMemo(() => buildFogSurface(cells), [cells]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !surface) return;
    const context = canvas.getContext('2d');
    if (!context) return;

    canvas.width = surface.width;
    canvas.height = surface.height;
    const image = context.createImageData(surface.width, surface.height);
    image.data.set(surface.pixels);
    context.putImageData(image, 0, 0);

    const northWest: [number, number] = [surface.bounds[1][0], surface.bounds[0][1]];
    const southEast: [number, number] = [surface.bounds[0][0], surface.bounds[1][1]];
    const position = () => {
      const topLeft = map.latLngToLayerPoint(northWest);
      const bottomRight = map.latLngToLayerPoint(southEast);
      const size = bottomRight.subtract(topLeft);
      DomUtil.setTransform(canvas, topLeft, 1);
      canvas.style.width = `${size.x}px`;
      canvas.style.height = `${size.y}px`;
    };
    const animateZoom = (event: ZoomAnimEvent) => {
      const scale = map.getZoomScale(event.zoom);
      const offset = map.project(northWest, event.zoom)
        .subtract(map.project(event.center, event.zoom))
        .add(map.getSize().divideBy(2))
        .add(map.containerPointToLayerPoint([0, 0]));
      DomUtil.setTransform(canvas, offset, scale);
    };

    position();
    map.on('zoomend viewreset resize', position);
    map.on('zoomanim', animateZoom);
    return () => {
      map.off('zoomend viewreset resize', position);
      map.off('zoomanim', animateZoom);
    };
  }, [map, surface]);

  if (!surface) return null;

  return (
    <Pane name='gk2a-fog-surface' style={{ zIndex: 350, pointerEvents: 'none' }}>
      <canvas
        ref={canvasRef}
        className='fog-surface-canvas leaflet-zoom-animated'
        aria-hidden='true'
      />
    </Pane>
  );
}
