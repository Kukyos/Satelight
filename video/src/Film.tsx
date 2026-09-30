// The Satelight film. Adapted from SIH26P3 video/src/Film.tsx: the same grammar (near-black
// cards, one idea each, footage with lower thirds), new cards, the viewer's own yellow.
import React from 'react';
import {
  AbsoluteFill, Audio, Img, Loop, OffthreadVideo, Sequence, Series, interpolate, staticFile,
  useCurrentFrame, useVideoConfig,
} from 'remotion';
import script from '../script.json';
import voice from './voice.json';
import {
  counts, cyclone, depths, evidence, floatsPerYear, gaps, harnessCommand, heat, hidden, latency,
  latencyMeasured, quantity, repo, rmseFor, s4,
} from './data';

// Near-black ground, one idea per card, light type, one accent: the viewer's own yellow.
const C = { ground: '#05080C', ink: '#F2F4F7', dim: '#8C94A1', faint: '#4A525E', accent: '#F5C542', warn: '#E8876A', navy: '#0D1B2A' };
const FONT = 'Inter, sans-serif';
export const FPS = 30;

type Clip = { name: string; seconds: number };
type Scene = {
  id: string; act: string; say: string; card?: string; seconds?: number; clips?: Clip[];
  lower?: string; lowers?: string[]; quote?: string; cite?: string; lines?: string[]; lowerAt?: 'left' | 'right' | 'center'; image?: string; big?: string;
  tiles?: { title: string; clip?: string; from?: number; card?: string }[];
  quantity?: string; units?: string; heading?: string; tier?: string; source?: string;
};
const scenes = script.scenes as Scene[];

// A scene is as long as its clips, or its card's seconds. Nothing is a hand-counted frame.
const frames = (s: Scene) =>
  Math.round(FPS * (s.clips ? s.clips.reduce((n, c) => n + c.seconds, 0) : s.seconds!));
export const TOTAL = scenes.reduce((n, s) => n + frames(s), 0);

const Fade: React.FC<{ children: React.ReactNode; dur: number; edge?: number }> = ({ children, dur, edge = 10 }) => {
  const f = useCurrentFrame();
  const o = interpolate(f, [0, edge, dur - edge, dur], [0, 1, 1, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  return <AbsoluteFill style={{ opacity: o }}>{children}</AbsoluteFill>;
};

// Rises in after `at` frames.
const Rise: React.FC<{ at?: number; children: React.ReactNode; style?: React.CSSProperties }> = ({ at = 0, children, style }) => {
  const f = useCurrentFrame();
  const t = interpolate(f, [at, at + 18], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  return <div style={{ opacity: t, transform: `translateY(${(1 - t) * 14}px)`, ...style }}>{children}</div>;
};

// ------------------------------------------------------------------ over the footage

// Bottom-left, clear of the viewer's timeline and status bar; right or centre where a dock or
// the lesson card sits there.
const Lower: React.FC<{ act: string; text?: string; dur: number; at?: Scene['lowerAt'] }> = ({ act, text, dur, at = 'left' }) => {
  if (!act && !text) return null;
  const place: React.CSSProperties = at === 'right' ? { right: 56 } : at === 'center' ? { left: '50%', transform: 'translateX(-50%)' } : { left: 56 };
  return (
    <Sequence from={12} durationInFrames={Math.max(1, dur - 12)} layout="none">
      <Fade dur={dur - 12} edge={12}>
        <div style={{ position: 'absolute', ...place, bottom: 96, maxWidth: 1100, background: 'rgba(5,8,12,0.82)',
          borderLeft: `3px solid ${C.accent}`, padding: '14px 22px', fontFamily: FONT }}>
          {act && <div style={{ color: C.accent, fontSize: 17, letterSpacing: '0.18em', textTransform: 'uppercase', fontWeight: 500 }}>{act}</div>}
          {text && <div style={{ color: C.ink, fontSize: 27, fontWeight: 400, marginTop: act ? 6 : 0 }}>{text}</div>}
        </div>
      </Fade>
    </Sequence>
  );
};

const Footage: React.FC<{ s: Scene }> = ({ s }) => {
  let at = 0;
  return (
    <AbsoluteFill style={{ background: C.ground }}>
      {s.clips!.map((c, i) => {
        const d = Math.round(c.seconds * FPS);
        const el = (
          <Sequence key={c.name} from={at} durationInFrames={d}>
            <Fade dur={d} edge={s.clips!.length > 1 ? 6 : 10}>
              <OffthreadVideo src={staticFile(`clips/${c.name}.mp4`)} muted />
            </Fade>
            <Lower act={i === 0 || s.lowers ? s.act : ''} text={s.lowers ? s.lowers[i] : i === 0 ? s.lower : undefined} dur={d} at={s.lowerAt} />
          </Sequence>
        );
        at += d;
        return el;
      })}
    </AbsoluteFill>
  );
};

// ------------------------------------------------------------------ cards

const Card: React.FC<{ children: React.ReactNode; act?: string }> = ({ children, act }) => (
  <AbsoluteFill style={{ background: C.ground, fontFamily: FONT, color: C.ink, padding: '110px 150px', justifyContent: 'center' }}>
    {act && <Rise><div style={{ color: C.accent, fontSize: 20, letterSpacing: '0.2em', textTransform: 'uppercase', fontWeight: 500, marginBottom: 36 }}>{act}</div></Rise>}
    {children}
  </AbsoluteFill>
);

// The viewer's favicon: the water column, surface to depth.
const Mark: React.FC<{ size: number }> = ({ size }) => (
  <svg width={size} height={size} viewBox="0 0 16 16"><rect width="16" height="16" rx="3" fill={C.navy} />
    <path d="M2 5h12M4 8h8M6 11h4" stroke={C.accent} strokeWidth="1.6" /></svg>
);

const Title: React.FC = () => (
  <Card>
    <Rise><div style={{ display: 'flex', alignItems: 'center', gap: 44 }}><Mark size={150} />
      <div style={{ fontSize: 168, fontWeight: 200, letterSpacing: '-0.04em' }}>Satelight</div></div></Rise>
    <Rise at={20}><div style={{ fontSize: 44, fontWeight: 300, color: C.dim, marginTop: 16 }}>The ocean below, seen from space.</div></Rise>
    <Rise at={40}><div style={{ fontSize: 22, color: C.faint, marginTop: 72, letterSpacing: '0.06em' }}>
      SIH 2026 · PS 26066 · INCOIS, Ministry of Earth Sciences · Disaster Management</div></Rise>
  </Card>
);

const Quote: React.FC<{ s: Scene }> = ({ s }) => (
  <Card act={s.act}>
    <Rise at={8}><div style={{ fontSize: 58, fontWeight: 300, lineHeight: 1.3, maxWidth: 1500 }}>“{s.quote}”</div></Rise>
    <Rise at={30}><div style={{ fontSize: 24, color: C.dim, marginTop: 48 }}>{s.cite}</div></Rise>
  </Card>
);

// A grid of big numbers with labels.
const Tiles: React.FC<{ s: Scene; items: { value: string; label: string }[]; cols?: number; foot?: React.ReactNode }> = ({ s, items, cols = 2, foot }) => (
  <Card act={s.act}>
    <div style={{ display: 'grid', gridTemplateColumns: `repeat(${cols}, 1fr)`, gap: '56px 72px' }}>
      {items.map((x, i) => (
        <Rise key={x.label} at={8 + i * 10}>
          <div style={{ fontSize: 96, fontWeight: 200, color: i === 0 ? C.accent : C.ink, letterSpacing: '-0.02em' }}>{x.value}</div>
          <div style={{ fontSize: 26, color: C.dim, marginTop: 6 }}>{x.label}</div>
        </Rise>
      ))}
    </div>
    {foot}
  </Card>
);
const Counts: React.FC<{ s: Scene }> = ({ s }) => <Tiles s={s} items={counts} />;
const Gap: React.FC<{ s: Scene }> = ({ s }) => (
  <Tiles s={s} items={gaps} cols={3} foot={<Rise at={60}><div style={{ fontSize: 26, color: C.dim, marginTop: 72, lineHeight: 1.5 }}>
    {s.lines![0]}</div></Rise>} />
);
const Evidence: React.FC<{ s: Scene }> = ({ s }) => (
  <Tiles s={s} items={evidence} cols={3} foot={<Rise at={70}><div style={{ fontSize: 26, color: C.dim, marginTop: 72, fontFamily: 'Consolas, monospace' }}>
    {repo} · <span style={{ color: C.ink }}>{harnessCommand}</span></div></Rise>} />
);

// Heading | text rows, revealed one by one.
const Rows: React.FC<{ s: Scene }> = ({ s }) => {
  const rows = s.lines!.map((l) => l.split('|'));
  const step = Math.max(24, Math.floor((frames(s) - 60) / rows.length));
  return (
    <Card act={s.act}>
      {rows.map(([h, t], i) => (
        <Rise key={h} at={10 + i * step}>
          <div style={{ marginBottom: rows.length > 5 ? 30 : 46 }}>
            <div style={{ fontSize: rows.length > 5 ? 40 : 48, fontWeight: 300 }}>{h}</div>
            <div style={{ fontSize: 27, color: C.dim, marginTop: 6 }}>{t}</div>
          </div>
        </Rise>
      ))}
    </Card>
  );
};

// The pipeline, left to right.
const PIPE: [string, string][] = [
  ['8 surface fields', 'SST, salinity, sea level, anomaly, currents U V, winds U V'],
  ['One grid', '0.25°, daily, 45–105°E × 5–30°N; block means, never upsampled'],
  ['Encoder', 'CNN + transformer, over the whole basin at once'],
  ['Embedding', '32 numbers per cell per day, saved as a file'],
  ['Decoder', '15 standard depths, 0 to 1,000 m; masked below the sea floor'],
  ['Harness', 'held-out Argo, per depth and basin, beside climatology and GLORYS'],
];
const Pipeline: React.FC<{ s: Scene }> = ({ s }) => {
  const step = Math.floor(frames(s) * 0.55 / PIPE.length);   // all six up by just past half-way
  return (
    <Card act={s.act}>
      <div style={{ display: 'flex', gap: 18, alignItems: 'stretch' }}>
        {PIPE.map(([h, t], i) => (
          <React.Fragment key={h}>
            {i > 0 && <Rise at={10 + i * step}><div style={{ fontSize: 44, color: C.faint, marginTop: 70 }}>→</div></Rise>}
            <Rise at={10 + i * step} style={{ flex: 1 }}>
              <div style={{ border: `1px solid ${C.faint}`, borderTop: `3px solid ${h === 'Embedding' ? C.accent : C.dim}`, padding: '24px 22px', minHeight: 330 }}>
                <div style={{ fontSize: 32, fontWeight: 400, marginBottom: 16, color: h === 'Embedding' ? C.accent : C.ink }}>{h}</div>
                <div style={{ fontSize: 22, color: C.dim, lineHeight: 1.4 }}>{t}</div>
              </div>
            </Rise>
          </React.Fragment>
        ))}
      </div>
      <Rise at={frames(s) - 110}><div style={{ fontSize: 26, color: C.dim, marginTop: 56 }}>{s.lines![0]}</div></Rise>
    </Card>
  );
};

// RMSE by depth against held-out Argo, drawn in: climatology, GLORYS, then ours, per basin.
const RMSE: React.FC<{ s: Scene }> = ({ s }) => {
  const f = useCurrentFrame();
  const W = 470, H = 600, max = 2.4;
  const y = (k: number) => 20 + (k / (depths.length - 1)) * (H - 40);
  const x = (v: number) => 60 + (v / max) * (W - 80);
  const path = (vals: number[], t: number) => {
    const n = Math.max(2, Math.ceil(t * vals.length));
    return vals.slice(0, n).map((v, k) => `${k ? 'L' : 'M'}${x(v).toFixed(1)},${y(k).toFixed(1)}`).join(' ');
  };
  const draw = (at: number) => interpolate(f, [at, at + 45], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  return (
    <Card act={s.act}>
      <Rise><div style={{ fontSize: 46, fontWeight: 300, marginBottom: 26 }}>{
        s.source === 'prefloat' ? 'Error against Argo, 2005–2009, by depth · RMSE °C'
          : s.source ? 'Error against real-time Argo, by depth · RMSE °C'
          : 'Error against held-out Argo, by depth · RMSE °C'}</div></Rise>
      <div style={{ display: 'flex', gap: 60 }}>
        {rmseFor(s.source).map((r, i) => (
          <Rise key={r.title} at={6 + i * 6}>
            <div style={{ fontSize: 28, marginBottom: 4 }}>{r.title}</div>
            <div style={{ fontSize: 20, color: C.faint, marginBottom: 8 }}>{r.n} cast-depth pairs</div>
            <svg width={W} height={H + 30}>
              {[0, 0.5, 1, 1.5, 2].map((v) => <g key={v}><line x1={x(v)} x2={x(v)} y1={10} y2={H - 10} stroke="#1A222C" />
                <text x={x(v)} y={H + 18} fill={C.faint} fontSize={16} textAnchor="middle">{v}</text></g>)}
              {depths.map((d, k) => (k % 2 === 0 || d === 1000) && <text key={d} x={50} y={y(k) + 5} fill={C.faint} fontSize={16} textAnchor="end">{d}</text>)}
              <rect x={60} y={y(6) - 8} width={W - 80} height={y(9) - y(6) + 16} fill={C.warn} opacity={0.08 * draw(150)} />
              <path d={path(r.clim, draw(20))} stroke={C.dim} strokeWidth={2.5} strokeDasharray="6 6" fill="none" />
              {r.glorys && <path d={path(r.glorys, draw(55))} stroke={C.warn} strokeWidth={2.5} fill="none" />}
              <path d={path(r.ours, draw(90))} stroke={C.accent} strokeWidth={4.5} fill="none" />
            </svg>
          </Rise>
        ))}
      </div>
      <Rise at={120}><div style={{ fontSize: 24, color: C.dim, marginTop: 10, display: 'flex', gap: 44 }}>
        <span>– – climatology, the floor</span>
        <span><span style={{ color: C.accent }}>━</span> {s.source === 'nowcast-fast' ? 'Satelight nowcast, four fields' : s.source === 'prefloat' ? 'Satelight, before its training years' : 'Satelight, satellites only'}</span>
        {s.source?.startsWith('nowcast') ? <span style={{ color: C.warn }}>no GLORYS: it does not reach these days yet</span>
          : <span><span style={{ color: C.warn }}>━</span> GLORYS, the ceiling: it assimilated these floats</span>}
        <span style={{ color: C.faint }}>depth in m</span>
      </div></Rise>
    </Card>
  );
};

// Heat potential RMSE against Argo: bars to scale, per basin.
const Heat: React.FC<{ s: Scene }> = ({ s }) => {
  const f = useCurrentFrame();
  const data = s.quantity ? quantity(s.quantity) : heat;
  const max = Math.max(...data.map((h) => Math.max(h.clim, h.ours, h.glorys)));
  const bar = (v: number, color: string, at: number, bold = false) => {
    const t = interpolate(f, [at, at + 24], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
    return <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
      <div style={{ height: 24, width: (v / max) * 820 * t, background: color, borderRadius: 2 }} />
      <span style={{ fontSize: 24, color: bold ? C.ink : C.dim, fontWeight: bold ? 600 : 400, opacity: t }}>{v.toFixed(1)}</span></div>;
  };
  return (
    <Card act={s.act}>
      <Rise><div style={{ fontSize: 48, fontWeight: 300, marginBottom: 8 }}>{s.heading ?? 'Cyclone heat potential, error against Argo'}</div></Rise>
      <Rise at={6}><div style={{ fontSize: 26, color: C.dim, marginBottom: 44 }}>{s.lines![0]}</div></Rise>
      {data.map((h, i) => (
        <div key={h.title} style={{ display: 'flex', alignItems: 'center', marginBottom: 34 }}>
          <div style={{ width: 280, fontSize: 30, color: C.dim }}>{h.title}</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {bar(h.clim, C.faint, 20 + i * 14)}{bar(h.ours, C.accent, 30 + i * 14, true)}{bar(h.glorys, C.warn, 40 + i * 14)}
          </div>
        </div>
      ))}
      <Rise at={80}><div style={{ fontSize: 22, color: C.dim, marginTop: 10, display: 'flex', gap: 40 }}>
        <span><span style={{ color: C.faint }}>■</span> climatology</span><span><span style={{ color: C.accent }}>■</span> Satelight</span>
        <span><span style={{ color: C.warn }}>■</span> GLORYS</span><span style={{ color: C.faint }}>RMSE, {s.units ?? 'kJ/cm²'}</span></div></Rise>
    </Card>
  );
};

// A harness figure beside the lines that read it.
const Figure: React.FC<{ s: Scene }> = ({ s }) => {
  const cy = s.big ? cyclone(s.big) : null;
  const lines = cy ? [
    `Surface change, box mean: Satelight ${cy.ours0} °C · GLORYS ${cy.glorys0} · climatology ${cy.clim0}`,
    `Heat potential, kJ/cm²: Satelight ${cy.tOurs} · GLORYS ${cy.tGlorys}`,
    ...(s.lines || []),
  ] : s.id === 'embedding' ? [...(s.lines || []),
    `Mixed-layer depth, never trained on, linear probe R² (${s4.run}): embedding ${s4.emb} · raw inputs ${s4.raw}`,
    `Seasons, clustering NMI (${s4.head}, the headline): embedding ${s4.nmi} · day of year alone ${s4.nmiDoy}`,
    'No single embedding does both yet: S4 is half met.'] : (s.lines || []);
  return (
    <Card act={s.act}>
      <div style={{ display: 'flex', gap: 64, alignItems: 'center' }}>
        <Rise at={4}><Img src={staticFile(`img/${s.image}`)} style={{ height: 700, maxWidth: 1000, objectFit: 'contain', borderRadius: 4 }} /></Rise>
        <div style={{ flex: 1 }}>
          {lines.map((l, i) => (
            <Rise key={l} at={30 + i * 40}><div style={{ fontSize: i === 0 ? 32 : 27, color: i === 0 ? C.ink : C.dim, lineHeight: 1.4, marginBottom: 28 }}>{l}</div></Rise>
          ))}
        </div>
      </div>
    </Card>
  );
};

// Argo profiles per year in the box: the years the floats missed.
const Floats: React.FC<{ s: Scene }> = ({ s }) => {
  const f = useCurrentFrame();
  const max = Math.max(...floatsPerYear.map((x) => x.n));
  return (
    <Card act={s.act}>
      <Rise><div style={{ fontSize: 48, fontWeight: 300, marginBottom: 40 }}>Argo profiles per year in the box</div></Rise>
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 14, height: 360 }}>
        {floatsPerYear.map((x, i) => {
          const t = interpolate(f, [12 + i * 3, 30 + i * 3], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
          return (
            <div key={x.y} style={{ flex: 1, textAlign: 'center' }}>
              <div style={{ fontSize: 17, color: x.n ? C.dim : C.accent, marginBottom: 6, opacity: t }}>{x.n.toLocaleString('en-US')}</div>
              <div style={{ height: Math.max(3, (x.n / max) * 300 * t), background: x.n ? C.dim : C.accent, borderRadius: 2 }} />
              <div style={{ fontSize: 17, color: C.faint, marginTop: 8 }}>{String(x.y).slice(2)}</div>
            </div>
          );
        })}
      </div>
      <Rise at={110}><div style={{ fontSize: 24, color: C.dim, marginTop: 18 }}>{s.lines![0]}</div></Rise>
    </Card>
  );
};

// How late each input is against GLORYS, and the nowcast's score on real-time floats.
const Latency: React.FC<{ s: Scene }> = ({ s }) => {
  const f = useCurrentFrame();
  const max = Math.max(...latency.map((x) => x.days));
  return (
    <Card act={s.act}>
      <Rise><div style={{ fontSize: 48, fontWeight: 300, marginBottom: 36 }}>Days behind, measured {latencyMeasured}</div></Rise>
      {latency.map((x, i) => {
        const t = interpolate(f, [12 + i * 8, 36 + i * 8], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
        return (
          <div key={x.name} style={{ display: 'flex', alignItems: 'center', marginBottom: 20 }}>
            <div style={{ width: 380, fontSize: 28, color: x.model ? C.warn : C.dim }}>{x.name}</div>
            <div style={{ height: 26, width: Math.max(4, (x.days / max) * 900 * t), background: x.model ? C.warn : C.accent, borderRadius: 2 }} />
            <span style={{ fontSize: 26, marginLeft: 16, opacity: t, color: x.model ? C.warn : C.ink }}>{x.days} {x.days === 1 ? 'day' : 'days'}</span>
          </div>
        );
      })}
      <Rise at={120}><div style={{ fontSize: 24, color: C.dim, marginTop: 18 }}>{s.lines![0]}</div></Rise>
    </Card>
  );
};

const Hidden: React.FC<{ s: Scene }> = ({ s }) => (
  <Tiles s={s} items={hidden} foot={<Rise at={60}><div style={{ fontSize: 24, color: C.dim, marginTop: 56 }}>{s.lines![0]}</div></Rise>} />
);

// What is coming: every chapter as a looping thumbnail, lit as the narration names it.
// Copied from SIH26P3 video/src/Film.tsx (Index).
const sceneById = (id: string) => scenes.find((x) => x.card === id || x.id === id)!;
const Index: React.FC<{ s: Scene }> = ({ s }) => {
  const f = useCurrentFrame();
  const tiles = s.tiles!;
  const W = 500, H = Math.round(W * 9 / 16);
  const each = (frames(s) - 30) / tiles.length;
  return (
    <AbsoluteFill style={{ background: C.ground, fontFamily: FONT, alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ display: 'grid', gridTemplateColumns: `repeat(3, ${W}px)`, gap: '22px 40px' }}>
        {tiles.map((t, i) => {
          const lit = f >= 15 + i * each && f < 15 + (i + 1) * each;
          const tIn = interpolate(f, [i * 4, i * 4 + 14], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
          return (
            <div key={t.title} style={{ opacity: tIn * (lit ? 1 : 0.55), transform: `scale(${lit ? 1.03 : 1})` }}>
              <div style={{ width: W, height: H, overflow: 'hidden', position: 'relative', background: '#0B1017',
                outline: `2px solid ${lit ? C.accent : 'transparent'}` }}>
                {t.clip ? (
                  <Loop durationInFrames={60}>
                    <OffthreadVideo src={staticFile(`clips/${t.clip}.mp4`)} startFrom={Math.round((t.from ?? 0) * FPS)} muted
                      style={{ width: W, height: H, objectFit: 'cover' }} />
                  </Loop>
                ) : (
                  <div style={{ width: 1920, height: 1080, transform: `scale(${W / 1920})`, transformOrigin: 'top left' }}>
                    {React.createElement(CARDS[sceneById(t.card!).card!], { s: sceneById(t.card!) })}
                  </div>
                )}
              </div>
              <div style={{ color: lit ? C.ink : C.dim, fontSize: 24, marginTop: 10, fontWeight: lit ? 500 : 400 }}>
                <span style={{ color: C.accent, marginRight: 10 }}>{i + 1}</span>{t.title}</div>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

const End: React.FC = () => (
  <Card>
    <Rise><div style={{ display: 'flex', alignItems: 'center', gap: 36 }}><Mark size={120} />
      <div style={{ fontSize: 140, fontWeight: 200, letterSpacing: '-0.04em' }}>Satelight</div></div></Rise>
    <Rise at={18}><div style={{ fontSize: 48, fontWeight: 300, color: C.accent, marginTop: 24, fontFamily: 'Consolas, monospace' }}>{repo}</div></Rise>
    <Rise at={30}><div style={{ fontSize: 26, color: C.dim, marginTop: 20 }}>Idea-stage prototype · every number from <span style={{ fontFamily: 'Consolas, monospace' }}>{harnessCommand}</span></div></Rise>
    <Rise at={48}><div style={{ fontSize: 22, color: C.faint, marginTop: 72, letterSpacing: '0.06em' }}>
      Team Null · K26125 · SIH 2026 · PS 26066 · INCOIS, Ministry of Earth Sciences</div></Rise>
  </Card>
);

const CARDS: Record<string, React.FC<{ s: Scene }>> = {
  title: Title, quote: Quote, counts: Counts, gap: Gap, evidence: Evidence, rows: Rows,
  pipeline: Pipeline, rmse: RMSE, heat: Heat, figure: Figure, end: End,
  floats: Floats, latency: Latency, hidden: Hidden, index: Index,
};

// ------------------------------------------------------------------ the film

// A recorded line, public/voice/<scene>.<ext>, plays from half a second into its scene.
// check.mjs finds them and writes voice.json; it fails if a line runs past its scene.
const VOICE = voice as Record<string, string>;

export const Film: React.FC = () => {
  useVideoConfig();
  return (
    <AbsoluteFill style={{ background: C.ground }}>
      <Series>
        {scenes.map((s) => {
          const d = frames(s);
          const Body = s.card ? CARDS[s.card] : null;
          return (
            <Series.Sequence key={s.id} durationInFrames={d}>
              {Body ? <Fade dur={d}><Body s={s} /></Fade> : <Footage s={s} />}
              {VOICE[s.id] && (
                <Sequence from={Math.round(0.5 * FPS)} layout="none"><Audio src={staticFile(`voice/${VOICE[s.id]}`)} /></Sequence>
              )}
            </Series.Sequence>
          );
        })}
      </Series>
    </AbsoluteFill>
  );
};
