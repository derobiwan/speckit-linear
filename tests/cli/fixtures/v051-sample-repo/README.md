# v0.5.1 Sample Fixture

Minimal layout used by `tests/cli/test_upgrade_from_v051.py` to exercise
the `specify upgrade-from-v051` command's R6 algorithm:

```
.claude/commands/speckit.*.md       ← legacy command files
skills/speckit-*/SKILL.md           ← legacy skill directories
.specify/config/linear.md           ← preserved across upgrade (NOT moved)
```

The test copies this tree into a tmp dir, runs the upgrade module, and
asserts the legacy dirs end up under `.specify/legacy-v051/<ts>/` while
`.specify/config/linear.md` remains in place.
