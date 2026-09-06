# Preview archive

How each screen looked, and when. One row per build of the workbench
(`services/web`, `pnpm run build-workbench`).

## Why this file, and not the builds themselves

A dated export is ~8 MB, and committing one per milestone would put a few hundred megabytes
of regenerable bytes into a repository whose entire point is that the source is the record.
The stories *are* code: every state's definition is a committed file, so any row below is
reproducible exactly from its own commit —

```sh
git checkout <sha>
cd services/web && pnpm install && pnpm run build-workbench
python3 -m http.server 6099 -d storybook-static      # then open http://127.0.0.1:6099
```

`git log services/web/src/**/*.stories.tsx` is the evolution of a screen's states;
`git log services/web/src/mocks/fixtures.ts` is the evolution of the data it was reviewed
against. The exports under `design-previews/_live/` are the convenience copy — kept on
disk, not in git (see the root `.gitignore`), with `latest` symlinked at the newest.

Automated visual diffing (Chromatic, Percy, Playwright `toHaveScreenshot`) is the next
level up and is deliberately not adopted yet: the UI is still moving enough that a diff
would be noise. Revisit when a milestone passes without a screen changing shape.

## Builds

| Date | Build | Commit | Stories | What changed, and why |
|---|---|---|---|---|
| 2026-09-06 | `_live/2026-09-06-t0079` | T-0079 | 31 | First build. Baseline capture of every screen as it stood after T-0074's changelist split and T-0072's account menu — nothing was redesigned to produce it. Two defects found on first run: the report overflows horizontally at 390px, and the catalogue filter has three placeholder-only inputs. Both recorded in `docs/tasks/T-0079-*.md`, neither fixed here. |

## Reading a build

`index.html` is the workbench proper — sidebar, language toolbar, a11y panel. The states
are grouped `Screens/…` (whole pages, mounted through the real router and session) and
`Components/…` (a component on its own).

Two things are worth doing in the browser and cannot be done to a screenshot:

- **Resize it.** The report is known to overflow below roughly 640px.
- **Run a check.** `Screens/Review/Detail/Never Checked` → select a pack → run. The mock
  advances the run on a real clock and the app's own polling carries it from Queued to a
  rendered report.
