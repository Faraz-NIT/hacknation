/**
 * Capture languages. The expert can speak any of these; rules are stored in
 * English and the tutor always teaches in English, translating the quotes.
 * `code` is the ElevenAgents language override, `speech` the browser locale.
 */
export type LangCode = "en" | "fr" | "de" | "hi";

export const LANGUAGES: Record<LangCode, { name: string; native: string; speech: string }> = {
  en: { name: "English", native: "English", speech: "en-US" },
  fr: { name: "French", native: "Français", speech: "fr-FR" },
  de: { name: "German", native: "Deutsch", speech: "de-DE" },
  hi: { name: "Hindi", native: "हिन्दी", speech: "hi-IN" },
};
