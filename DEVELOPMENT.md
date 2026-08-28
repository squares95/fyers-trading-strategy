# Development Setup

## One-time install (Windows / PowerShell)

```powershell
# Install dev tools
py -m pip install -r requirements-dev.txt

# Install pre-commit hooks (auto-fix on every commit)
py -m pip install pre-commit
pre-commit install
```

## Daily workflow

Once pre-commit is installed, every `git commit` automatically:
1. Runs `ruff --fix` (auto-fixes imports, unused vars, modernization)
2. Runs `ruff-format` (formats code)
3. Runs `black` (formats code)
4. Fails the commit if issues can't be auto-fixed

## Manual commands

```powershell
# Lint (check for issues, no changes)
py -m ruff check .

# Lint + auto-fix
py -m ruff check --fix .

# Format
py -m ruff format .
py -m black .

# Type check (slower, run occasionally)
py -m mypy Strategies/ Paper/
```

## What gets checked

- **E/W**: pycodestyle (PEP 8 style)
- **F**: pyflakes (unused imports, undefined names)
- **I**: isort (import order)
- **B**: bugbear (common bugs)
- **UP**: pyupgrade (use modern Python: `dict | None` not `Optional[Dict]`, `list[str]` not `List[str]`)
- **N**: pep8-naming
- **SIM**: simplify (use `if x in []` not `if any([x == y])`)
- **RUF**: ruff-specific

## What's excluded

- `Data/` and `_slim/` — CSV data folders
- `Research/GroqAnalysis/` — generated JSON/CSV reports
- `__pycache__/`, `.git/`, `*.bak*`
- `Research/exp*.py` — late imports allowed in scripts
- `**/legacy_*.py` — legacy code, don't auto-touch

## IDE setup (VSCode)

`.vscode/settings.json` already has Pylance. Add:
```json
{
  "[python]": {
    "editor.defaultFormatter": "ms-python.black-formatter",
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
      "source.fixAll.ruff": "explicit",
      "source.organizeImports.ruff": "explicit"
    }
  }
}
```
