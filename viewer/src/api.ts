/** Talking to satelight/api.py. Arrays arrive as base64 little-endian float32 or uint8. */

export interface Meta {
  run: string;
  days: string[];
  fields: string[];
  depths: number[];
  regions: Record<string, { lon: [number, number]; lat: [number, number] }>;
  inputs: { key: string; title: string; units: string }[];
  splits: Record<string, [string, string]>;
  zero_metre_rule: string;
}

export interface CubeResponse {
  day: string; field: string; region: string;
  dimensions: [number, number, number];
  lons: number[]; lats: number[]; depths: number[];
  valueRange: [number, number];
  values: string; seafloor: string; units: string;
}

export interface InputField {
  key: string; title: string; units: string; range: [number, number]; values: string;
  source?: string;
}

export interface Cast {
  platform: string; cycle: number | null; lat: number; lon: number; day: string;
  data_mode: string; source_file: string; levels_rejected: number;
  obs: (number | null)[]; pred: Record<string, (number | null)[]>;
}

export interface Column {
  day: string; lat: number; lon: number; depths: number[];
  profiles: Record<string, (number | null)[]>; seafloor: number | null;
}

export type Scores = { n: number; rmse?: number; bias?: number; r?: number; anomaly_r?: number };
export interface Eval {
  generated: string; contenders: string[]; depths: number[];
  argo: Record<string, Record<string, Scores[]>>;
  argo_counts: Record<string, number>;
  hazard?: Record<string, Record<string, Record<string, Scores & { obs_mean?: number | null }>>>;
  heatwave?: Record<string, Record<string, { n: number; observed: number; by: Record<string, {
    hits: number; false_alarms: number; misses: number;
    pod: number | null; far: number | null; hss: number | null }> }>>;
}

export interface Lens {
  day: string; lens: string; title: string; units: string; what: string;
  dimensions: [number, number]; lons: number[]; lats: number[]; range: [number, number];
  values: string;
}

export interface TrackPoint { time: string; lat: number; lon: number; grade: string;
                              grade_name: string; wind_kt: number | null }

export interface Globe {
  day: string; source: string; shape: [number, number]; range: [number, number];
  west: number; south: number; res: number; values: string;
}

export class ApiError extends Error {}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(path);
  if (!r.ok) {
    let detail = `${r.status}`;
    try { detail = (await r.json()).detail ?? detail; } catch { /* not JSON */ }
    throw new ApiError(detail);
  }
  return r.json() as Promise<T>;
}

export const f32 = (b64: string): Float32Array => {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i += 1) bytes[i] = bin.charCodeAt(i);
  return new Float32Array(bytes.buffer);
};

export const u8 = (b64: string): Uint8Array => {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i += 1) bytes[i] = bin.charCodeAt(i);
  return bytes;
};

const q = (o: Record<string, string | number>) => new URLSearchParams(
  Object.entries(o).map(([k, v]) => [k, String(v)])).toString();

export const api = {
  meta: () => get<Meta>("/api/meta"),
  cube: (day: string, name: string, region: string) =>
    get<CubeResponse>(`/api/cube?${q({ day, name, region })}`),
  inputs: (day: string) =>
    get<{ day: string; shape: [number, number]; inputs: InputField[] }>(`/api/inputs?${q({ day })}`),
  embedding: (day: string) =>
    get<{ day: string; run: string; shape: [number, number]; dims: number; rgb: string; sea: string }>(
      `/api/embedding?${q({ day })}`),
  casts: (day: string) => get<{ casts: Cast[] }>(`/api/casts?${q({ day, window: 3 })}`),
  column: (day: string, lat: number, lon: number) =>
    get<Column>(`/api/column?${q({ day, lat, lon })}`),
  evaluation: () => get<Eval>("/api/eval"),
  globe: (day: string) => get<Globe>(`/api/globe?${q({ day })}`),
  lens: (day: string, name: string, region: string) =>
    get<Lens>(`/api/lens?${q({ day, name, region })}`),
  lensAt: (day: string, lat: number, lon: number) =>
    get<{ day: string; lat: number; lon: number; values: Record<string, number | null> }>(
      `/api/lens/at?${q({ day, lat, lon })}`),
  track: (name: string) => get<{ name: string; source: string; points: TrackPoint[] }>(
    `/api/track?${q({ name })}`),
};
