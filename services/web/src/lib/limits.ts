/**
 * The upload ceiling, stated where the user picks a file rather than only after the
 * server rejects it.
 *
 * T-0033 (`docs/tasks/T-0033-measured-upload-ceiling.md`): the number itself is derived
 * from measured worker memory, not chosen here -- it must match
 * `services/api/cadgpt/config/settings/base.py`'s `MAX_UPLOAD_BYTES`, whose comment
 * carries the measurement and the derivation. There is no runtime config endpoint this
 * reads it from (out of scope here; chunked/resumable upload and a config API are both
 * named as deliberately not built in `docs/plan.md`), so the two constants are kept in
 * sync by hand -- change one, change the other in the same commit.
 */
export const MAX_MODEL_UPLOAD_BYTES = 126 * 1024 * 1024;

/** `1_048_576` -> `"1.0 MB"`. Matches the units Django's `filesizeformat` renders. */
export function formatBytes(bytes: number): string {
  const units = ["bytes", "KB", "MB", "GB", "TB"];
  if (bytes < 1024) return `${bytes} bytes`;
  let value = bytes;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(1)} ${units[unitIndex]}`;
}
