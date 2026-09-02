/**
 * Localization, with direction as a first-class consequence of language.
 *
 * The product is jurisdiction-agnostic and its users are not: the first target market
 * reads right to left. Direction is set on the document element from the active language,
 * so a component never has to know which way the page runs -- CSS logical properties do
 * the rest.
 *
 * Findings themselves are not translated here. The server sends `reason_label` already
 * written in the user's language, because the wording belongs with the rule engine's
 * vocabulary and not with the UI's.
 */

import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import en from "@/i18n/en.json";
import fa from "@/i18n/fa.json";

export const RTL_LANGUAGES = new Set(["fa", "ar", "he", "ur"]);

export function directionFor(language: string): "rtl" | "ltr" {
  return RTL_LANGUAGES.has(language.split("-")[0] ?? "") ? "rtl" : "ltr";
}

export function applyDirection(language: string): void {
  const root = document.documentElement;
  root.lang = language;
  root.dir = directionFor(language);
}

void i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, fa: { translation: fa } },
  lng: localStorage.getItem("language") ?? "en",
  fallbackLng: "en",
  interpolation: { escapeValue: false },
});

i18n.on("languageChanged", (language) => {
  localStorage.setItem("language", language);
  applyDirection(language);
});

applyDirection(i18n.language);

export default i18n;
