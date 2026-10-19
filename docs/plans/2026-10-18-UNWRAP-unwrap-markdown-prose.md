# Unwrap hard-wrapped Markdown prose

Slug: UNWRAP
Status: **Completed**

## Goal and scope

The repository's Markdown is hard-wrapped to a fixed width, which conflicts with the `AGENTS.md` rule to write each paragraph and list item as one line. Unwrap the existing prose so the documents follow that rule and later edits stop mixing both styles.

This is a docs-only change in its own commit, not mixed into feature work. Wording, content, and rendered output stay the same; only line breaks inside paragraphs and list items change.

In scope: `README.md`, `AGENTS.md`, `CLAUDE.md`, `CHANGELOG.md`, `docs/README.md`, `docs/research/*.md`, and all plans, including completed plans.

## Design

- Join wrapped lines of one paragraph or list item into one line. A list item's continuation lines join onto the item's line.
- Keep every break that Markdown needs: headings, list items, nested lists, table rows, block quotes, code blocks, front matter, link reference definitions, and blank lines between blocks.
- Keep hard line breaks that are intentional (two trailing spaces or a trailing backslash).
- Completed plans receive the same line-break-only cleanup; their historical wording and content stay unchanged.
- Python docstrings and comments are out of scope; the `AGENTS.md` rule covers Markdown only.
- A temporary Python script may join prose using Markdown parser paragraph boundaries, with manual review and before/after structure and rendering checks. The user approved this approach; do not commit the script.

## Implementation and verification

- [x] Decide with the user whether completed plans are included: include them.
- [x] Unwrap the in-scope files.
- [x] Verify no prose wording changed, apart from this plan's tracking updates and its index entry: `git diff --word-diff` shows only those tracking edits and redundant blockquote continuation markers.
- [x] Check that headings, lists, tables, code blocks, and links render the same as before.
- [x] Run `make check`.

Verification: 294 paragraphs reflowed across 12 Markdown files, including completed plans; `CLAUDE.md` and this plan already had unwrapped prose. Word comparison, CommonMark structure comparison, and GitHub-flavored rendered HTML comparison passed for all 14 Markdown files before the final tracking updates. Manual diff review preserved visible list boundaries, including over-indented lists in the initial development plan. `make check` passed all 324 tests, Ruff, syntax checks, and manifest validation; `git diff --check` passed. No runtime or manifest changes are needed for this line-break-only cleanup.
