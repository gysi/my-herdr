# Unwrap hard-wrapped Markdown prose

Slug: UNWRAP
Status: **Planned**

## Goal and scope

The repository's Markdown is hard-wrapped to a fixed width, which conflicts with the `AGENTS.md` rule to write each paragraph and list item as one line. Unwrap the existing prose so the documents follow that rule and later edits stop mixing both styles.

This is a docs-only change in its own commit, not mixed into feature work. Wording, content, and rendered output stay the same; only line breaks inside paragraphs and list items change.

In scope: `README.md`, `AGENTS.md`, `CLAUDE.md`, `CHANGELOG.md`, `docs/README.md`, `docs/research/*.md`, and active plans.

## Design

- Join wrapped lines of one paragraph or list item into one line. A list item's continuation lines join onto the item's line.
- Keep every break that Markdown needs: headings, list items, nested lists, table rows, block quotes, code blocks, front matter, link reference definitions, and blank lines between blocks.
- Keep hard line breaks that are intentional (two trailing spaces or a trailing backslash).
- Completed plans are historical design records and stay as they are, unless the user decides to include them.
- Python docstrings and comments are out of scope; the `AGENTS.md` rule covers Markdown only.
- Bulk-editing many files may need a throwaway script. Per `AGENTS.md`, ask the user before using Python for file edits, and do not commit the script.

## Implementation and verification

- [ ] Decide with the user whether completed plans are included.
- [ ] Unwrap the in-scope files.
- [ ] Verify no wording changed: `git diff --word-diff` shows no word additions or removals.
- [ ] Check that headings, lists, tables, code blocks, and links render the same as before.
- [ ] Run `make check`.
