/**
 * The fishing readout in the language of the coast it is for: INCOIS says where the fish
 * are likely to be (its own Potential Fishing Zone advisory, read as published), Satelight
 * adds how deep the warm water goes there, from satellites only.
 *
 * The sentences below were machine-translated from the English and have not yet been
 * checked by a native speaker of each language; the panel says so every time it shows
 * one. Speech uses the browser's own voices (Web Speech API): where a browser has no
 * voice for a language, the button says so instead of reading it in another.
 */

import { Cartesian3, Color, PointPrimitiveCollection } from "@cesium/engine";
import type { Viewer } from "@cesium/widgets";

export interface PfzPoint {
  coast: string; direction: string; lat: number; lon: number; depth_m: [number, number];
  sector: string; sector_name: string; valid_till: string | null;
  state: string; d20_m: number | null; mld_m: number | null; floor_m: number | null;
}

type Lang = "en" | "hi" | "ta" | "ml" | "te" | "kn" | "mr" | "gu" | "bn" | "or";

export const LANGS: Record<Lang, { name: string; bcp47: string }> = {
  en: { name: "English", bcp47: "en-IN" }, hi: { name: "हिन्दी", bcp47: "hi-IN" },
  ta: { name: "தமிழ்", bcp47: "ta-IN" }, ml: { name: "മലയാളം", bcp47: "ml-IN" },
  te: { name: "తెలుగు", bcp47: "te-IN" }, kn: { name: "ಕನ್ನಡ", bcp47: "kn-IN" },
  mr: { name: "मराठी", bcp47: "mr-IN" }, gu: { name: "ગુજરાતી", bcp47: "gu-IN" },
  bn: { name: "বাংলা", bcp47: "bn-IN" }, or: { name: "ଓଡ଼ିଆ", bcp47: "or-IN" },
};

// The language of each INCOIS sector's coast. Goa's is Konkani, which is not here yet:
// Marathi, also widely read on that coast, stands in and the panel says so.
export const SECTOR_LANG: Record<string, Lang> = {
  SEC001: "gu", SEC002: "mr", SEC003: "mr", SEC004: "kn", SEC005: "ml", SEC006: "ta",
  SEC007: "ta", SEC008: "te", SEC009: "te", SEC010: "or", SEC011: "bn", SEC012: "hi",
  SEC013: "hi", SEC014: "ml",
};

// {p} place, {d} depth to 20 °C, {m} mixed layer, {f} sea floor, {t} date.
const T: Record<Lang, { deep: string; floor: string }> = {
  en: { deep: "{p}: warm water down to about {d} m, mixed layer {m} m. Satellite estimate for {t}.",
        floor: "{p}: warm all the way to the sea floor ({f} m). Satellite estimate for {t}." },
  hi: { deep: "{p}: गर्म पानी लगभग {d} मीटर की गहराई तक, मिश्रित परत {m} मीटर। {t} का उपग्रह अनुमान।",
        floor: "{p}: समुद्र तल ({f} मीटर) तक पूरा पानी गर्म। {t} का उपग्रह अनुमान।" },
  ta: { deep: "{p}: சுமார் {d} மீட்டர் ஆழம் வரை வெதுவெதுப்பான நீர், கலப்பு அடுக்கு {m} மீட்டர். {t} அன்றைய செயற்கைக்கோள் மதிப்பீடு.",
        floor: "{p}: கடல் தரை ({f} மீட்டர்) வரை முழு நீரும் வெதுவெதுப்பாக உள்ளது. {t} அன்றைய செயற்கைக்கோள் மதிப்பீடு." },
  ml: { deep: "{p}: ഏകദേശം {d} മീറ്റർ ആഴം വരെ ചൂടുവെള്ളം, മിശ്ര പാളി {m} മീറ്റർ. {t} ലെ ഉപഗ്രഹ കണക്ക്.",
        floor: "{p}: കടലിന്റെ അടിത്തട്ട് ({f} മീറ്റർ) വരെ മുഴുവൻ വെള്ളവും ചൂടാണ്. {t} ലെ ഉപഗ്രഹ കണക്ക്." },
  te: { deep: "{p}: సుమారు {d} మీటర్ల లోతు వరకు వెచ్చని నీరు, మిశ్రమ పొర {m} మీటర్లు. {t} నాటి ఉపగ్రహ అంచనా.",
        floor: "{p}: సముద్రపు అడుగు ({f} మీటర్లు) వరకు నీరంతా వెచ్చగా ఉంది. {t} నాటి ఉపగ్రహ అంచనా." },
  kn: { deep: "{p}: ಸುಮಾರು {d} ಮೀಟರ್ ಆಳದವರೆಗೆ ಬೆಚ್ಚಗಿನ ನೀರು, ಮಿಶ್ರ ಪದರ {m} ಮೀಟರ್. {t} ರ ಉಪಗ್ರಹ ಅಂದಾಜು.",
        floor: "{p}: ಸಮುದ್ರದ ತಳದವರೆಗೆ ({f} ಮೀಟರ್) ನೀರು ಪೂರ್ತಿ ಬೆಚ್ಚಗಿದೆ. {t} ರ ಉಪಗ್ರಹ ಅಂದಾಜು." },
  mr: { deep: "{p}: सुमारे {d} मीटर खोलीपर्यंत उबदार पाणी, मिश्र थर {m} मीटर. {t} चा उपग्रह अंदाज.",
        floor: "{p}: समुद्रतळापर्यंत ({f} मीटर) सर्व पाणी उबदार आहे. {t} चा उपग्रह अंदाज." },
  gu: { deep: "{p}: આશરે {d} મીટર ઊંડાઈ સુધી ગરમ પાણી, મિશ્ર સ્તર {m} મીટર. {t} નો ઉપગ્રહ અંદાજ.",
        floor: "{p}: દરિયાના તળિયા ({f} મીટર) સુધી બધું પાણી ગરમ છે. {t} નો ઉપગ્રહ અંદાજ." },
  bn: { deep: "{p}: প্রায় {d} মিটার গভীরতা পর্যন্ত উষ্ণ জল, মিশ্র স্তর {m} মিটার। {t} তারিখের উপগ্রহ অনুমান।",
        floor: "{p}: সমুদ্রের তলদেশ ({f} মিটার) পর্যন্ত সব জল উষ্ণ। {t} তারিখের উপগ্রহ অনুমান।" },
  or: { deep: "{p}: ପ୍ରାୟ {d} ମିଟର ଗଭୀରତା ପର୍ଯ୍ୟନ୍ତ ଉଷ୍ମ ପାଣି, ମିଶ୍ରିତ ସ୍ତର {m} ମିଟର। {t} ର ଉପଗ୍ରହ ଆକଳନ।",
        floor: "{p}: ସମୁଦ୍ର ତଳ ({f} ମିଟର) ପର୍ଯ୍ୟନ୍ତ ସମସ୍ତ ପାଣି ଉଷ୍ମ। {t} ର ଉପଗ୍ରହ ଆକଳନ।" },
};

/** The sentence for one zone, or null where Satelight has nothing to add there. */
export function sentence(p: PfzPoint, lang: Lang, day: string): string | null {
  const place = `${p.coast} (${p.direction})`;
  const fill = (s: string) => s.replace("{p}", place).replace("{d}", String(p.d20_m))
    .replace("{m}", p.mld_m == null ? "—" : String(p.mld_m)).replace("{f}", String(p.floor_m))
    .replace("{t}", day);
  if (p.state === "thermocline" && p.d20_m != null) return fill(T[lang].deep);
  if (p.state === "warm to the sea floor" && p.floor_m != null) return fill(T[lang].floor);
  return null;
}

/** Read it aloud in its own language, or say why not. Returns what happened. */
export function speak(text: string, lang: Lang): string {
  if (!("speechSynthesis" in window)) return "This browser cannot speak.";
  const want = LANGS[lang].bcp47.slice(0, 2);
  const voice = speechSynthesis.getVoices().find((v) => v.lang.toLowerCase().startsWith(want));
  if (!voice) return `No ${LANGS[lang].name} voice in this browser; the text stands.`;
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.voice = voice;
  u.lang = voice.lang;
  speechSynthesis.speak(u);
  return `Reading with ${voice.name}.`;
}

/** The zones as points on the cube's top: bright where there is a thermocline depth. */
export class Zones {
  private dots = new PointPrimitiveCollection();

  constructor(private viewer: Viewer) { viewer.scene.primitives.add(this.dots); }

  show(points: PfzPoint[], height: number): void {
    this.dots.removeAll();
    points.forEach((p, i) => this.dots.add({
      position: Cartesian3.fromDegrees(p.lon, p.lat, height + 7000),
      pixelSize: p.state === "thermocline" ? 8 : 5,
      color: Color.fromCssColorString(p.state === "thermocline" ? "#FF9A1F" : "#FFD9A8"),
      outlineColor: Color.BLACK, outlineWidth: 1, id: { zone: i },
    }));
    this.viewer.scene.requestRender();
  }

  clear(): void { this.dots.removeAll(); this.viewer.scene.requestRender(); }
}

export type { Lang };
