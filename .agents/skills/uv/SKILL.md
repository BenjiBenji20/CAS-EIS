---
# python-uv-project-conventions
Description:
  Python uv package manager conventions, dependency management, lockfile synchronization, virtual environment execution, and modular source import path rules.
---

# Python uv & Project Conventions

This skill dictates package dependency workflows, lockfile synchronization (`uv.lock`), command execution, and module import path conventions in this codebase.

---

## 1. Dependency Management with `uv`

This project uses `uv` as the fast, deterministic package and project manager configured via `pyproject.toml`:

```bash
# Add a runtime dependency to [project.dependencies]
uv add "package_name>=1.0.0"

# Add a development/testing dependency to [dependency-groups.dev]
uv add --dev "pytest-mock>=3.14.0"

# Remove a dependency
uv remove "package_name"
```

---

## 2. Lockfile Maintenance (`uv.lock`)

- **Deterministic Builds**: The `uv.lock` file is committed to version control and guarantees identical dependency trees across dev, test, and production environments.
- **Lockfile Synchronization**:
  ```bash
  # Sync the virtual environment with the exact lockfile
  uv sync

  # Update lockfile after manual changes to pyproject.toml
  uv lock
  ```
- **Rule**: Never edit `uv.lock` manually. Always use `uv add`, `uv remove`, or `uv lock`.

---

## 3. CLI & Command Execution (`uv run`)

Always execute application entrypoints, tests, and database tools inside the `uv` virtual environment using `uv run`:

```bash
# Start FastAPI local development server
uv run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# Execute full test suite
uv run pytest

```

---

## 4. Modular Source Imports (`src/` Root)

The workspace is configured with `src` as the package source root in `pyproject.toml`:

```toml
[tool.setuptools.packages.find]
where = ["src"]
```

### Import Rules:
1. **Absolute Root Imports**: Always import modules starting from root sub-packages under `src/`.
```python
# ✅ CORRECT (Clean, absolute imports)
from core.settings import settings
from db.base import Base, uuid_pk
from modules.authentication.auth_model import User
from clients.postgresql import init_db
from exceptions.app_exception import NotFoundException

# ❌ WRONG (Avoid relative upward traversing)
from ...core.settings import settings
from ..db.base import Base
```
2. **Environment Pathing**: `src/main.py` and `alembic/env.py` programmatically ensure `src` is in `sys.path`. Keep all new domain modules under `src/modules/<domain>/`.
