/**
 * The three-valued verdict, rendered so the third value cannot be mistaken for a pass.
 *
 * Colour alone would not do it: indeterminate is amber, which reads as "warning" and a
 * hurried reader files warnings next to successes. The label is always shown, and the
 * summary states the count separately rather than folding it anywhere.
 */

import { useTranslation } from "react-i18next";

import type { Status } from "@/api/types";

const TONE: Record<Status, string> = {
  PASS: "pill pill--pass",
  FAIL: "pill pill--fail",
  INDETERMINATE: "pill pill--indeterminate",
};

export function StatusPill({ status }: { status: Status }) {
  const { t } = useTranslation();
  return <span className={TONE[status]}>{t(`status.${status}`)}</span>;
}
