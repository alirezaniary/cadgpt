#!/bin/bash
# PreToolUse hook, scoped to an agent's own frontmatter (builder/reviewer).
# Non-blocking: never denies a tool call. Reads real usage from the agent's
# own transcript and injects a short reminder into its context, once per
# threshold crossing — 180k is a heads-up, 220k is a stronger nudge to wrap
# up. The agent stays aware of docs/agents.md's budget; nothing stops it.

WARN_LOW="${CONTEXT_BUDGET_WARN_LOW:-180000}"
WARN_HIGH="${CONTEXT_BUDGET_WARN_HIGH:-220000}"

command -v jq >/dev/null 2>&1 || exit 0

input="$(cat)"
transcript="$(echo "$input" | jq -r '.transcript_path // empty')"
[ -f "$transcript" ] || exit 0

# Input tokens are cumulative per API call (latest value already reflects
# the whole conversation); output tokens are per-turn and must be summed.
last_input=$(jq -s '
  [.[] | select(.message.usage.input_tokens != null)] | last
  | (.message.usage.input_tokens // 0) + (.message.usage.cache_read_input_tokens // 0)
' "$transcript" 2>/dev/null)
total_output=$(jq -s '
  [.[] | select(.message.usage.output_tokens != null) | .message.usage.output_tokens] | add // 0
' "$transcript" 2>/dev/null)

[ -z "$last_input" ] && exit 0
[ -z "$total_output" ] && total_output=0
total=$((last_input + total_output))

# One state file per transcript, so each threshold notes exactly once per
# session instead of repeating on every subsequent tool call.
state_file="${transcript}.budget-state"
notified=""
[ -f "$state_file" ] && notified="$(cat "$state_file" 2>/dev/null)"

if [ "$total" -ge "$WARN_HIGH" ] && [[ "$notified" != *HIGH* ]]; then
  echo "LOWHIGH" > "$state_file"
  jq -n --arg ctx "Context budget: ~${total} tokens used, past the 220k line from docs/agents.md's budget. Stop pushing forward. In your next message: either finish — full evidence block, make verify's result, the real path's actual output, the wiring line quoted, no half-finished task — or write the handoff into the task file right now: what's done, what's verified, what's left, the exact next command. Do not open a new line of investigation or start another broad tool call before you have done one of those two things." \
    '{hookSpecificOutput: {hookEventName: "PreToolUse", additionalContext: $ctx}}'
  exit 0
elif [ "$total" -ge "$WARN_LOW" ] && [[ "$notified" != *LOW* ]]; then
  echo "${notified}LOW" > "$state_file"
  jq -n --arg ctx "Context budget: ~${total} tokens used, entered the 180k-220k range from docs/agents.md's budget. Decide now: either finish within the next few messages — full evidence block, make verify's result, the real path's actual output, the wiring line quoted, no half-finished task — or stop and write the handoff into the task file: what's done, what's verified, what's left, the exact next command. Do not keep exploring without having picked one of those two." \
    '{hookSpecificOutput: {hookEventName: "PreToolUse", additionalContext: $ctx}}'
  exit 0
fi

exit 0
