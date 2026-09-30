// Copied from SIH26P3 video/src/Root.tsx; the font is served from public/ instead of Google.
import React from 'react';
import { Composition, staticFile } from 'remotion';
import { Film, TOTAL, FPS } from './Film';

// Inter, variable weight, from public/fonts (copied from @fontsource-variable/inter), so a
// render never waits on a font server. Plain CSS: a FontFace().load() wrapped in
// delayRender() never settled inside render tabs and timed the render out.
const FONT_CSS = `@font-face { font-family: 'Inter'; font-weight: 100 900; font-display: block;
  src: url('${staticFile('fonts/inter-latin-wght-normal.woff2')}') format('woff2'); }`;

const WithFont: React.FC = () => (<><style>{FONT_CSS}</style><Film /></>);

export const RemotionRoot: React.FC = () => (
  <Composition id="Film" component={WithFont} durationInFrames={TOTAL} fps={FPS} width={1920} height={1080} />
);
