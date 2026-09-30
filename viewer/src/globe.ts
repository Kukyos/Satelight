/**
 * The planet under the cube: sharp land and sea floor, and the same day's satellite sea
 * surface temperature on the cube's own colour bar, so the reconstruction stands inside
 * the real ocean rather than on a flat map.
 *
 * Land: NASA Blue Marble shaded relief and bathymetry through GIBS (about 600 m a pixel,
 * public domain, no key), over Natural Earth II as the offline fallback. The relief layer
 * and its fallback are adapted from SIH26P3 viewer/src/main.ts.
 *
 * Ocean: OSTIA for the day (satelight/globe.py), display only, labelled with its product
 * and date wherever it shows. Nothing from GLORYS.
 */

import {
  ImageryLayer, Rectangle, SingleTileImageryProvider, TextureMagnificationFilter,
  TextureMinificationFilter, TileMapServiceImageryProvider, UrlTemplateImageryProvider,
  WebMercatorTilingScheme,
} from "@cesium/engine";
import type { Viewer } from "@cesium/widgets";

import { api, u8 } from "./api";

export class Planet {
  private sea?: ImageryLayer;
  private seaKey = "";
  source = "";

  constructor(private viewer: Viewer) {}

  async land(): Promise<void> {
    const layers = this.viewer.imageryLayers;
    try {
      const base = new ImageryLayer(
        await TileMapServiceImageryProvider.fromUrl("/cesium/Assets/Textures/NaturalEarthII"));
      base.brightness = 0.6;
      layers.add(base, 0);
    } catch { /* the plain globe colour stands in */ }
    const relief = new UrlTemplateImageryProvider({
      url: "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_ShadedRelief_Bathymetry/" +
        "default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg",
      tilingScheme: new WebMercatorTilingScheme(),
      maximumLevel: 8,
      credit: "NASA Blue Marble shaded relief and bathymetry, via NASA GIBS",
    });
    const layer = new ImageryLayer(relief);
    let failures = 0;
    relief.errorEvent.addEventListener(() => {
      failures += 1;
      if (failures === 12) layers.remove(layer);   // unreachable: Natural Earth shows
    });
    layer.brightness = 0.8;
    layer.saturation = 0.85;
    layers.add(layer);
  }

  /**
   * Paint the ocean with this day's satellite SST through the cube's own colour bar
   * (`lut`, and `pos` placing a value on it), or clear it (`show` false, e.g. for the
   * error field, whose colour bar is not °C). `bar` names the bar, so a new one repaints.
   */
  async ocean(day: string, show: boolean, lut: Uint8ClampedArray, pos: (v: number) => number,
              bar: string): Promise<void> {
    const key = `${day}|${bar}|${show}`;
    if (key === this.seaKey) return;
    this.seaKey = key;
    if (!show) { this.clear(); return; }
    let g;
    try { g = await api.globe(day); } catch { this.clear(); return; }
    if (this.seaKey !== key) return;                 // a newer day asked meanwhile
    const [ny, nx] = g.shape;
    const q = u8(g.values);
    const [glo, ghi] = g.range;
    const canvas = document.createElement("canvas");
    canvas.width = nx;
    canvas.height = ny;
    const img = new ImageData(nx, ny);
    for (let j = 0; j < ny; j += 1) {
      for (let i = 0; i < nx; i += 1) {
        const b = q[j * nx + i];
        if (b === 255) continue;                     // land and ice-covered cells: relief shows
        const t = glo + (b / 254) * (ghi - glo);
        const k = Math.max(0, Math.min(255, Math.round(pos(t) * 255)));
        img.data.set([lut[k * 4], lut[k * 4 + 1], lut[k * 4 + 2], 255], ((ny - 1 - j) * nx + i) * 4);
      }
    }
    canvas.getContext("2d")!.putImageData(img, 0, 0);
    const provider = await SingleTileImageryProvider.fromUrl(canvas.toDataURL(), {
      rectangle: Rectangle.fromDegrees(g.west, g.south, g.west + nx * g.res, g.south + ny * g.res),
      credit: `Sea surface temperature ${g.day}: ${g.source} (Copernicus Marine), satellite`,
    });
    if (this.seaKey !== key) return;
    const layer = new ImageryLayer(provider);
    layer.magnificationFilter = TextureMagnificationFilter.LINEAR;
    layer.minificationFilter = TextureMinificationFilter.LINEAR;
    layer.alpha = 0.72;   // the sea floor's relief shows through, so the water has depth
    const old = this.sea;
    this.viewer.imageryLayers.add(layer);
    this.sea = layer;
    this.source = `${g.source}, ${g.day}`;
    if (old) this.viewer.imageryLayers.remove(old);
    this.viewer.scene.requestRender();
  }

  private clear(): void {
    if (this.sea) this.viewer.imageryLayers.remove(this.sea);
    this.sea = undefined;
    this.source = "";
    this.viewer.scene.requestRender();
  }
}
