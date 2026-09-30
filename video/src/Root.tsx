// Copied from SIH26P3 video/src/Root.tsx.
import React from 'react';
import { Composition, continueRender, delayRender } from 'remotion';
// Inter from the npm package, bundled: the render never waits on a font server.
import '@fontsource-variable/inter';
import { Film, TOTAL, FPS } from './Film';


// No frame is taken before the font has loaded.
const fontReady = delayRender('Inter');
// ponytail: capped at 8 s; in some render tabs fonts.load never settles though the face is
// bundled and already in use, so the cap keeps a tab from timing out the render.
Promise.race([
  Promise.all([200, 300, 400, 500, 600].map((w) => document.fonts.load(`${w} 40px 'Inter Variable'`))),
  new Promise((r) => setTimeout(r, 8000)),
]).finally(() => continueRender(fontReady));

export const RemotionRoot: React.FC = () => (
  <Composition id="Film" component={Film} durationInFrames={TOTAL} fps={FPS} width={1920} height={1080} />
);
