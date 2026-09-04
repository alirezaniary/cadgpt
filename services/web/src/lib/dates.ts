/**
 * Date rendering for the changelist/detail tables (T-0074): a project's created date, a
 * review's latest-run date, a run's own date. `Intl.DateTimeFormat` reads the active
 * `i18n.language` (hardcoded `"fa"`, `src/i18n/index.ts`) itself -- no separate locale
 * constant to keep in sync by hand.
 */
import i18n from "i18next";

export function formatDate(iso: string): string {
  return new Intl.DateTimeFormat(i18n.language, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(iso));
}
