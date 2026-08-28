# Context Architecture - How We Manage State

## The Problem
Conversation context fills up with old work, summaries, file dumps, etc.
Result: "context length exceeded" errors and lost work.

## The Solution: Disk as Memory, Context as Working Set

### Layered Memory Model

```
┌─────────────────────────────────────────────┐
│  Conversation Context (200K token limit)     │  ← loaded fresh each turn
│  - Current task only                         │
│  - Active decisions                          │
│  - Pointers to files (not file contents)    │
└──────────────┬───────────────────────────────┘
               │ pointers
┌──────────────▼───────────────────────────────┐
│  current_session.md (always-on, ~3K tokens)  │  ← updated frequently
│  - Active goal                               │
│  - Recent decisions                          │
│  - Next action                               │
└──────────────┬───────────────────────────────┘
               │ references
┌──────────────▼───────────────────────────────┐
│  context/ folder (disk, unbounded)           │  ← long-form reference
│  - experiment_log.md (cumulative results)    │
│  - project_context.md (architecture)         │
│  - architecture_guide.md (code map)          │
│  - archive/ (old session segments)           │
└──────────────┬───────────────────────────────┘
               │ deep history
┌──────────────▼───────────────────────────────┐
│  memory/ folder (cross-session, loaded       │  ← user facts, preferences
│  via MEMORY.md at session start)             │
│  - project-overview.md                       │
│  - tools-and-workflow.md                      │
│  - current-focus.md                          │
└─────────────────────────────────────────────┘
```

## File Purposes

| File | Updated When | Read When |
|------|-------------|-----------|
| `current_session.md` | After each decision | Session start, after compact |
| `experiment_log.md` | After each experiment | When recalling specific result |
| `project_context.md` | Architecture changes | Code questions |
| `architecture_guide.md` | Code refactoring | Finding modules |
| `memory/MEMORY.md` | New persistent fact | Session start (auto-loaded) |
| `archive/session_*.md` | Before clearing context | Rarely, when digging up history |

## Session Lifecycle

### Start of Session
1. Auto-loaded: `memory/MEMORY.md` (~1K tokens of pointers)
2. Read: `context/current_session.md` (~3K tokens)
3. Optional: relevant context file based on task
4. **Total startup: ~5K tokens** (vs ~50K previously)

### During Session
- Read files on demand (with `Read` tool, can use `head_limit`/`offset`)
- Update `current_session.md` at decision points
- Dump large outputs to disk, reference by path
- Never paste full files into chat

### Before /compact
- Verify `current_session.md` is current
- Archive conversation transcript to `archive/`
- Note: actual conversation transcripts are auto-archived by Claude Code

## Token Math

| Old Approach | New Approach |
|--------------|--------------|
| 50K context → 100K → 200K → CRASH | 5K start + 10K active = 15K |
| Compaction tries to summarize 200K | Compaction summarizes 15K (cheap) |
| Context loss high | Context loss minimal |

## Rules of Thumb

1. **Never Read files > 1000 lines into chat** — use `head_limit` or `offset`
2. **Update `current_session.md` after each major decision** — keep it current
3. **Reference files by path in chat** — "see context/foo.md" not "as we discussed..."
4. **Large experiment outputs → file** — print summary in chat, save full to JSON
5. **When in doubt, write to disk** — disk is free, context is expensive

## When to use grep vs Read full file

- `Grep` for: "find me the function that does X"
- `Read head_limit=100` for: "I know which file, want the top of it"
- `Read full` for: files < 300 lines that are central to current task
- `Read offset=200 limit=100` for: "I know roughly where in the file"
