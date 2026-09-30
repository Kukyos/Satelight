// Every number the cards draw, read from the harness output rather than typed.
// check.mjs covers the spoken lines and lower thirds in script.json the same way.
// Adapted from SIH26P3 video/src/data.ts.
import e from './eval.json'; // written by check.mjs from data/eval-latest.json

// No '-0.00': a change that rounds to zero is shown as zero.
const f = (x: number, d: number) => (Math.abs(x) < 0.5 * 10 ** -d ? 0 : x).toFixed(d);
const thousands = (x: number) => x.toLocaleString('en-US');
type S = { n?: number; rmse?: number; bias?: number; r?: number };
const E = e as unknown as {
  depths: number[]; test_days: number; selection: { headline: string };
  argo_counts: Record<string, number>; argo: Record<string, Record<string, S[]>>;
  gap_closed: Record<string, Record<string, (number | null)[]>>;
  hazard: Record<string, Record<string, Record<string, S>>>;
  cyclones: Record<string, { before: string; after: string; change: Record<string, (number | null)[]>;
    tchp_box_mean: Record<string, { before: number; after: number }> }>;
  embedding: Record<string, { mld_probe?: Record<string, { r2_test: number }> }>;
  embedding_screen: { chosen: string };
  heatwave: Record<string, Record<string, { n: number; observed: number; by: Record<string,
    { hits: number; false_alarms: number; misses: number; pod: number | null; far: number | null; hss: number | null }> }>>;
  nowcast: { latency: { measured: string; sources: Record<string, { last_day: string; days_behind: number }> };
    tiers: Record<string, { run: string; days: [string, string]; casts: number; argo: Record<string, Record<string, S[]>> }> };
  prefloat: { floats: { profiles_per_year: Record<string, number> }; casts: number; scored: [string, string];
    argo: Record<string, Record<string, S[]>> };
};

export const HEAD = `${E.selection.headline} (selected)`;
export const BOX = 'North Indian Ocean (whole box)';
export const depths = E.depths;
export const regions: [string, string][] = [[BOX, 'Whole box'], ['Bay of Bengal', 'Bay of Bengal'], ['Arabian Sea', 'Arabian Sea']];

// RMSE by depth for the headline test block, the nowcast (no GLORYS: it does not reach
// those days), or 1993-2009, per basin.
export const rmseFor = (source?: string) => regions.map(([key, title]) => {
  const tab = source === 'prefloat' ? E.prefloat.argo
    : source?.startsWith('nowcast-') ? E.nowcast.tiers[source.slice(8)].argo : E.argo;
  const reg = tab[key];
  const ours = source ? Object.keys(reg).find((k) => k.startsWith('nowcast') || k.includes('before the floats'))! : HEAD;
  return {
    title, n: thousands(reg.climatology.reduce((a, s) => a + (s.n ?? 0), 0)),
    clim: reg.climatology.map((s) => s.rmse!), ours: reg[ours].map((s) => s.rmse!),
    glorys: reg['GLORYS (ceiling)'] ? reg['GLORYS (ceiling)'].map((s) => s.rmse!) : null,
  };
});

export const rmse = regions.map(([key, title]) => ({
  title,
  n: thousands(E.argo[key].climatology.reduce((a, s) => a + (s.n ?? 0), 0)),
  clim: E.argo[key].climatology.map((s) => s.rmse!),
  ours: E.argo[key][HEAD].map((s) => s.rmse!),
  glorys: E.argo[key]['GLORYS (ceiling)'].map((s) => s.rmse!),
}));

const c = E.argo_counts;
export const counts = [
  { value: thousands(c.casts_found), label: 'Argo casts in the box, 2023–24' },
  { value: thousands(c.casts_used), label: 'scored, beside every model' },
  { value: thousands(c.levels_rejected_by_qc), label: 'levels failing QC: counted, not dropped' },
  { value: thousands(c.casts_rejected_no_good_level), label: 'casts with no good level: rejected, counted' },
];

const gap = E.gap_closed;
const at = (d: number) => depths.indexOf(d);
export const gaps = [
  { value: `${f(100 * gap[BOX][HEAD][at(0)]!, 0)} %`, label: 'of the gap closed at the surface, whole box' },
  { value: `${f(100 * gap['Bay of Bengal'][HEAD][at(75)]!, 0)} %`, label: 'at 75 m in the Bay of Bengal' },
  { value: `${f(100 * gap[BOX][HEAD][at(300)]!, 0)} %`, label: 'at 300 m, whole box: the deep ocean is harder' },
];

const T = E.hazard['TCHP (kJ/cm²)'];
export const heat = regions.map(([key, title]) => ({
  title,
  clim: T[key].climatology.rmse!, ours: T[key][HEAD].rmse!, glorys: T[key]['GLORYS (ceiling)'].rmse!,
}));

export const cyclone = (name: string) => {
  const cy = E.cyclones[name];
  const t = cy.tchp_box_mean;
  return {
    before: cy.before, after: cy.after,
    ours0: f(cy.change.reconstruction[0]!, 2), glorys0: f(cy.change.GLORYS[0]!, 2), clim0: f(cy.change.climatology[0]!, 2),
    tOurs: `${f(t.reconstruction.before, 1)} → ${f(t.reconstruction.after, 1)}`,
    tGlorys: `${f(t.GLORYS.before, 1)} → ${f(t.GLORYS.after, 1)}`,
    tClim: `${f(t.climatology.before, 1)} → ${f(t.climatology.after, 1)}`,
  };
};

const probeRun = E.embedding_screen.chosen;
const probe = E.embedding[probeRun].mld_probe!;
const key = (p: string) => Object.keys(probe).find((k) => k.startsWith(p))!;
type Seasons = { nmi_clusters_vs_season: number; day_of_year_control: { nmi_clusters_vs_season: number } };
const headSeasons = (E.embedding[E.selection.headline] as unknown as { seasons: Seasons }).seasons;
export const s4 = {
  run: probeRun, emb: f(probe[key('embedding')].r2_test, 3), raw: f(probe[key('raw')].r2_test, 3),
  head: E.selection.headline,
  nmi: f(headSeasons.nmi_clusters_vs_season, 3), nmiDoy: f(headSeasons.day_of_year_control.nmi_clusters_vs_season, 3),
};

export const evidence = [
  { value: thousands(c.casts_used), label: 'held-out Argo casts scored' },
  { value: String(E.test_days), label: 'test days, one file each' },
  { value: String(depths.length), label: 'standard depths, 0 to 1,000 m' },
  { value: `${f(T[BOX][HEAD].rmse!, 1)}`, label: `kJ/cm² heat-potential error (climatology ${f(T[BOX].climatology.rmse!, 1)})` },
  { value: `${f(100 * gap[BOX][HEAD][at(0)]!, 0)} %`, label: 'of the floor-to-ceiling gap closed at the surface' },
  { value: s4.emb, label: `mixed-layer probe R² on the embedding (raw inputs ${s4.raw})` },
];

// A quantity from the hazard block (D20, MLD, TCHP) per basin, for the bar cards.
export const quantity = (q: string) => regions.map(([key, title]) => ({
  title, clim: E.hazard[q][key].climatology.rmse!, ours: E.hazard[q][key][HEAD].rmse!,
  glorys: E.hazard[q][key]['GLORYS (ceiling)'].rmse!,
}));

const HW = E.heatwave['Hidden: warm layer, normal surface'];
export const hidden = (() => {
  const r = HW[BOX], b = HW['Bay of Bengal'];
  const o = r.by[HEAD], g = r.by['GLORYS (ceiling)'], ob = b.by[HEAD];
  return [
    { value: `${o.hits} of ${r.observed}`, label: 'hidden warm layers Argo found, flagged by Satelight' },
    { value: f(o.hss!, 2), label: `skill (Heidke; GLORYS ${f(g.hss!, 2)}, climatology 0)` },
    { value: `${ob.hits} of ${b.observed}`, label: `in the Bay of Bengal, skill ${f(ob.hss!, 2)}` },
    { value: thousands(o.false_alarms), label: 'false alarms, consistent with the warm thermocline' },
  ];
})();

const NL = E.nowcast.latency;
export const latency = Object.entries(NL.sources).map(([k, v]) => ({
  name: ({ sst: 'Sea surface temperature', sss: 'Salinity', ssh: 'Sea level', oscar: 'Currents',
           ccmp: 'Winds', glorys: 'GLORYS reanalysis' } as Record<string, string>)[k] ?? k,
  days: v.days_behind, last: v.last_day, model: k === 'glorys',
}));
export const latencyMeasured = NL.measured;

export const floatsPerYear = Array.from({ length: 2011 - 1993 }, (_, i) => 1993 + i)
  .map((y) => ({ y, n: E.prefloat.floats.profiles_per_year[String(y)] ?? 0 }));
export const harnessCommand = 'python -m satelight.evaluate';
export const repo = 'github.com/Kukyos/Satelight';
