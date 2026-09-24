# AGENTS.md

## Project context

This repository is a Docker-based Odoo 18 environment. The running app is defined in [compose.yaml](compose.yaml), and custom modules live under [addons](addons). Existing module examples include [addons/base_account_budget](addons/base_account_budget) and [addons/base_accounting_kit](addons/base_accounting_kit).

The goal is to develop and maintain Odoo modules without changing unrelated infrastructure, platform settings, or other modules unless the task explicitly requires it.

## Working rules for AI coding agents

- Keep all module changes inside the relevant folder under [addons](addons), especially the target module’s `models/`, `views/`, `security/`, `wizard/`, `report/`, and `data/` directories.
- Do not modify unrelated Docker, database, config, or asset files unless the task truly requires it.
- Preserve existing module behavior and keep new work isolated. Do not rename, delete, or refactor unrelated modules as part of a feature change.
- Prefer additive, backward-compatible changes over broad rewrites.
- When working on a new module, follow the conventional Odoo structure: `__init__.py`, `__manifest__.py`, `models/`, `views/`, `security/`, and optional `wizard/`, `report/`, and `data/`.
- In the manifest, keep the dependency list minimal and explicit. Use the module’s actual required dependencies rather than broad or unnecessary ones.
- If the module adds models, also add the appropriate access rights in `security/ir.model.access.csv` and security XML files when needed.
- Use existing module patterns from the repo as the default reference instead of inventing a new structure.

## Odoo 18 conventions to follow

- Use Odoo 18-compatible manifest metadata, with versions in the repo’s existing pattern such as `18.0.x.y.z`.
- Keep `depends` values scoped to the modules that are truly required.
- Keep XML and CSV data files in the order expected by Odoo’s module install flow.
- Prefer small, focused model/view changes rather than introducing large cross-cutting architecture changes.
- For any UI or report addition, ensure the relevant XML view or template is registered in the module manifest data list.

## Development workflow

### Start the environment

```bash
docker compose up -d --build
```

### Reset the environment when needed

```bash
docker compose down -v
```

### Enter the Odoo container

```bash
docker exec -it odoo18-web-1 bash
```

### Create a new module

```bash
odoo scaffold <your-module-name> /mnt/extra-addons
```

## Validation expectations

- Validate Python syntax for any changed files before finishing.
- Check that XML and CSV files remain valid for Odoo module loading.
- Prefer verifying the affected module in the running Odoo instance rather than making broad project-wide edits.
- If a change affects multiple modules, keep the patch tightly scoped and explain the dependency clearly.

## Helpful references in this repo

- [compose.yaml](compose.yaml) for the local Docker setup
- [addons/base_account_budget](addons/base_account_budget) for a typical Odoo custom module layout
- [addons/base_accounting_kit](addons/base_accounting_kit) for a more feature-rich module example
- [addons/base_account_budget/README.rst](addons/base_account_budget/README.rst)
- [addons/base_accounting_kit/README.rst](addons/base_accounting_kit/README.rst)

## Guardrails

- Do not change unrelated app logic or third-party package versions unless the task explicitly requires it.
- Do not broaden the scope of a feature into reworking the entire project or platform stack.
- Keep the repo stable: the default goal is to add or adjust Odoo modules while leaving everything else as-is.
