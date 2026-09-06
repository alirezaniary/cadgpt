# Projects: the changelist

Reconstructed on 2026-09-06 from T-0073 and T-0074, after the fact.

**As a** architect running several permit submissions at once
**I want** my reviews filed under the building they belong to
**So that** when a colleague asks "where did the Niavaran tower land", I can answer without
reading through a list of every model this office has ever checked

## Acceptance criteria

- Given a workspace with projects, when I open the app, then I land on the changelist and
  see each project with how many reviews it holds and when it was created.
- Given a project row, when I click anywhere on it, then I open that project — the whole
  row is the target, not just the name.
- Given a brand-new workspace, when the list is empty, then I am told so in a sentence that
  names the next step, rather than shown an empty table.
- Given I add a project, when it is created, then I land on **its own detail page**, not
  back on the list — because the next thing anyone does after creating a project is put a
  review in it.
- **Given the list request fails, when the page renders, then it says so** — it must never
  fall through to the empty state, which would read as "you have no projects" and is a
  different, worse claim than "we could not load them".
- Given I am inside a project, when I look above the card, then a breadcrumb trail names
  every ancestor and each one is a link.
- Given a project's review count, when it is displayed, then it counts that project's
  reviews and not the workspace's.

## Explicitly out of scope

- Renaming, archiving or deleting a project from the UI. Deletion is a live question — see
  T-0075.
- Search, filtering, sorting and pagination on the changelist. It renders one page as the
  API returns it.
- Anything about who on the team owns or last touched a project.

## Assumptions / open questions

- The changelist is modelled on Django admin deliberately: list, add form behind a button,
  detail view behind a row. That was the product owner's call in T-0074, replacing a single
  dashboard page.
- No project has yet been seen with enough reviews to make the count column interesting, so
  whether "Reviews: 47" is useful or just noise is unknown.
- Pagination is unbuilt and unmeasured. An office with two hundred projects would meet the
  first page and nothing else.
