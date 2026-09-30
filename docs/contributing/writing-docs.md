# Writing docs

How TaskForge's Markdown files are written: README, CHANGELOG, guides and reference pages. The goal is docs that read as if one careful person wrote them all.

`markdownlint` checks the mechanical rules (config in `.markdownlint.jsonc`). The rest is checked in review.

## Contents

- [Which file is which](#which-file-is-which)
- [Voice and tone](#voice-and-tone)
- [Structure](#structure)
- [Formatting](#formatting)
- [Code and commands](#code-and-commands)
- [Links and images](#links-and-images)
- [Callouts](#callouts)
- [Templates](#templates)

## Which file is which

| File | Audience | Purpose |
|---|---|---|
| `README.md` | Someone deciding whether to use TaskForge | Pitch, install, a 5-minute example, and links. Also the PyPI page. |
| `CHANGELOG.md` | Users upgrading | What changed in each release, breaking changes first. |
| `CONTRIBUTING.md` | New contributors | Dev setup, workflow, and links to these conventions. |
| `docs/*.md` | Users | Guides, concepts and reference (the future docs site). |
| `docs/contributing/*.md` | Contributors | Conventions like this one. |
| `docs/revamp/*.md` | Maintainers | Plans, audits and specs. They describe intent, not current behavior. |

**Naming:**

- Root-level files that GitHub treats specially use UPPERCASE: `README.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `LICENSE`.
- Everything else is `lowercase-kebab-case.md`: `docs/docker-postgres-setup.md`, not `DOCKER_PG_SETUP.md`.

## Voice and tone

- **Talk to the reader as "you".** Use "we" only for the project's own decisions ("we store timestamps in UTC").
- **Present tense, active voice:** "The worker claims a job", not "A job will be claimed by the worker".
- **Short sentences**, one idea per paragraph. Lead with the point; details come after.
- **Plain words.** Skip "simply", "just", "easy", "obviously": if it were obvious, the reader wouldn't be reading.
- **No hype.** No "blazing fast" or "enterprise-grade". Give numbers and trade-offs instead.
- **Be honest about limits.** If something isn't implemented or has a sharp edge, say so where the reader will hit it.
- **US English**, and the terms from the [glossary](code-style.md#glossary).
- **Dates** are ISO 8601 (`2026-09-30`). Use numerals for anything with a unit: 5 seconds, 3 attempts, 100 jobs/s.

## Structure

- **One H1 per file**: the title, on the first line.
- **Headings** are sentence case with no trailing punctuation ("Running workers", not "Running Workers:"). Don't skip levels.
- **Open with a sentence** saying what the page covers and who it's for.
- **Add a "Contents" list** for pages with more than about 5 sections.
- **Order content by what the reader does:** install, configure, use, troubleshoot. Reference material goes last.

## Formatting

- **Line length:** don't hard-wrap. Write each paragraph on one line and let the editor soft-wrap.
- **Code formatting** (backticks) for anything the reader types or sees literally: identifiers, file paths, commands, env vars, config keys, values (`TASKFORGE_DATABASE_URL`, `dead`, `pyproject.toml`).
- **Bold** for UI labels ("click **Merge**") and at most one key phrase per paragraph. Italics rarely.
- **Lists:** use `-` for bullets and `1.` for steps that must happen in order. Items are sentence case and parallel in form; end them with periods only when they're full sentences.
- **Tables** for reference data (options, env vars, states). Keep cells short; if a cell needs a paragraph, use a list or a subsection instead.
- **Emoji:** avoid them. The only exceptions are status markers in planning tables (✅ 🟡 ⬜) and `⚠️` in front of warnings a skimmer must not miss.

## Code and commands

- **Every fenced block has a language:** `python`, `bash`, `powershell`, `toml`, `text` (for output), `yaml`, `sql`.
- **Commands are copy-pasteable:** no `$` or `>` prompts, and no output mixed into the command block. Show output in a separate `text` block if it matters.
- **Placeholders use angle brackets:** `taskforge replay <job_id>`. Say what to replace them with if it isn't obvious.
- **OS-specific commands:** show **bash first, then PowerShell**. Skip this when the command is identical everywhere, such as `pip install` or `git`.

  ````markdown
  ```bash
  source .venv/bin/activate
  export TASKFORGE_DATABASE_URL="postgresql+psycopg://user:password@localhost:5432/app"
  ```

  ```powershell
  .venv\Scripts\Activate.ps1
  $env:TASKFORGE_DATABASE_URL = "postgresql+psycopg://user:password@localhost:5432/app"
  ```
  ````

  On the docs site these become tabs.
- **Python examples must run** as written, after the imports they show. Prefer complete small examples to fragments with `...`.
- **Use fake, obviously fake values:** `user:password`, `example.com`, `ada@example.com`. Never real hosts or credentials.

## Links and images

- **Link text says where it goes:** "see the [configuration reference](...)", never "click here".
- **Links between docs are relative:** `[Code style](code-style.md)`.
- **README and CHANGELOG use absolute GitHub URLs** (`https://github.com/B1CA16/taskforge/blob/main/...`), because they're also rendered on PyPI, where relative links break.
- **Link to a specific section** with an anchor (`code-style.md#docstrings`) rather than to the top of a long page.
- **Images** go in `docs/assets/`, with descriptive alt text: `![Dashboard overview showing queue depths](assets/dashboard-overview.png)`. Keep screenshots under 300 KB and crop them to what matters.

## Callouts

- **In GitHub-only files** (anything under `docs/`, `CONTRIBUTING.md`), use GitHub alerts:

  ```markdown
  > [!WARNING]
  > The test suite drops all tables. Never point it at a real database.
  ```

  Use `NOTE` for useful asides, `IMPORTANT` for things needed to succeed, and `WARNING` for risk of data loss or security issues. Use callouts sparingly: if everything is a callout, nothing is.
- **In `README.md` and `CHANGELOG.md`** (also shown on PyPI, which doesn't render alerts), use a plain blockquote with a bold label:

  ```markdown
  > **Warning:** the dashboard has no authentication yet.
  ```

## Templates

### Guide or concept page (`docs/*.md`)

```markdown
# <Title in sentence case>

<One or two sentences: what this page covers and who it's for.>

## <First task or concept>

<Explanation, then an example.>

## <Next section>

...

## Troubleshooting

<Only if there are known failure modes: symptom, then cause, then fix.>

## See also

- [<Related page>](<relative-link>.md)
```

### README

The README keeps this section order:

1. Title, one-line pitch, badges.
2. Status note (alpha, what isn't done yet).
3. Features (only what exists today).
4. Requirements.
5. Installation.
6. Quick start (5 minutes, copy-pasteable).
7. Usage, Configuration, CLI, Dashboard, Metrics (short, linking to the docs for depth).
8. Development.
9. License.

### CHANGELOG entry

Follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Add to `## [Unreleased]` in the same PR as the change, under these headings, in this order (omit empty ones):

```markdown
## [Unreleased]

### ⚠️ Breaking

- <What changed and what users must do.> Migration: <exact steps>.

### Added

- <New capability, from the user's point of view>.

### Changed

### Deprecated

### Removed

### Fixed

- <Symptom the user saw>, now <correct behavior>.

### Security

### Docs
```

- **Write entries for users, not for reviewers:** "Workers no longer crash when the metrics port is taken", not "Catch OSError in start_metrics_server".
- **Link the issue or PR** at the end of the entry when there is one: `(#42)`.
