# WORKCENTER.md — <workcenter name>

<!-- Lives at the root of a workcenter repository. Its presence is what
     makes the repository a workcenter to skills/attached-repos. The
     install script copies this file to /opt/workcenters/<name>/ so an
     environment without the repository attached still finds it.
     Tables over prose. Same shape for every workcenter. -->

<One sentence: the kind of work this workcenter does and what "done"
means for it.>

## Tools

| Tool | Version | Command | Installed by |
|---|---|---|---|
| <tool> | <version> | `<command>` | `install.sh` |

## Skills

<!-- One row per folder in .claude/skills/. "Use when" is the step of
     the work, not a description of the skill. -->

| Skill | Use when |
|---|---|
| `<skill-name>` | <the step of the work this skill covers> |

## Gates

<!-- Binding on every project that uses this workcenter. A project may
     add gates; it may not remove these. Each gate is 1 command with a
     pass condition that is true or false. -->

| Gate | Command | Pass condition | Runs before |
|---|---|---|---|
| <gate> | `<command>` | <condition> | <the step it guards> |

## Paths

| Purpose | Path |
|---|---|
| Install root | `/opt/workcenters/<name>` |
| Tool cache | `<path outside every project>` |
| Project output | `<path inside the project, relative>` |

## Project requirements

<!-- What a project must hold so the tools work. The first commit that
     uses the workcenter adds these. -->

- `.gitignore` entries: `<pattern>`
- Files: `<file the tools expect at the project root>`
