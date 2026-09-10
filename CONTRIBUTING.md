# Contributing to stud

Bug reports, documentation improvements, and code contributions are welcome through [GitHub issues](https://github.com/getstud/stud/issues) and pull requests. For bugs, include reproduction steps, your OS and runtime versions, and a small design that demonstrates the problem. Discuss substantial changes in an issue before implementing them.

To develop locally, follow the source setup below, then run:

```sh
npm test
node --check web/app.js
```

The test suite covers the Python engine and JavaScript behavior and uses temporary models; it does not require your local designs. Add a regression test when fixing behavior, and update the relevant documentation when changing the CLI or modeling API.

| Path | Contents |
| --- | --- |
| `stud/` | Python modeling engine and assemblies |
| `stud_cli.py` | Project creation and command-line entry point |
| `build.py`, `validate.py`, `serve.py` | Export, validation, and local server |
| `web/` | Browser viewer |
| `tests/` | Python and JavaScript tests |
| `src-tauri/`, `desktop/`, `scripts/` | Desktop app, bundled launcher, and build tooling |
| `docs/` | User and developer guides |

Viewer JavaScript and CSS changes need a browser refresh; server changes need a restart. The legacy `clubhouse` Python import remains compatible with `stud`.

### Run from source

Install Python 3.13, Git and Node.js/npm. The CAD/PDF runtime is pinned in `requirements.lock`.

```sh
git clone https://github.com/getstud/stud.git
cd stud
python3.13 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements.lock
.venv/bin/python -m pip install pypdf==6.0.0
export PATH="$PWD/.venv/bin:$PATH"
export STUD_PYTHON="$PWD/.venv/bin/python"
npm ci
npm run stud -- init ../my-workshop --name "My workshop"
npm run stud -- serve ../my-workshop
```

Open [localhost:8765](http://127.0.0.1:8765) in your browser or Codex's in-app browser. The viewer rebuilds automatically as the project changes. Stop the server with Ctrl+C.

`init` creates a starter model and requires a directory that does not already exist. Designs live separately from the stud checkout.

### Modeling API

Current projects use ordinary CadQuery with the registration interface in [cadquery.md](docs/cadquery.md). Changes run in explicit request workspaces and finish as checkpoints. The example below documents the preserved legacy API; it is not source for a new CadQuery manifest.

Designs are stored as Python so agents and contributors can inspect and edit them. A project's `design.py` exposes a `project` object:

```python
from stud import Project

project = Project("My frame")
project.stock(
    "2x4", "Untreated 2x4", "#ddbd8b",
    section=(1.5, 3.5), lengths=(96, 120, 144),
)
project.box(
    "frame.stud.01", "Frame", "2x4",
    size=(1.5, 3.5, 80), origin=(0, 0, 0),
)
project.dimension("Height", (-4, 0, 0), (-4, 0, 80))
project.validation = {
    "version": 1,
    "automatic": ["solid_collision", "stock_fit"],
    "rules": [],
}
```

Dimensions are in **inches**, with X for width, Y for depth, and Z for elevation. Give each part a stable, unique ID so comments and checks can refer to it. Import local Python helpers to organize larger designs.

See [framed assemblies](docs/assemblies.md) for reusable wall and opening builders and the [validation guide](docs/validation.md) for adding design requirements.

### CLI reference

Run these from the stud checkout:

| Command | Purpose |
| --- | --- |
| `npm run stud -- init <directory>` | Create a new project |
| `npm run stud -- serve <directory>` | Start the local viewer |
| `npm run stud -- serve <directory> --port 8766` | Serve another project on a different port |
| `npm run stud -- build <directory>` | Validate and write JSON and CSV exports |
| `npm run stud -- validate <directory> --json` | Print machine-readable validation results |
| `npm run stud -- validate <directory> --strict` | Fail on warnings or unverified coverage as well as errors |

To install the source checkout's `stud` command, run `npm link`. You can also invoke `python3 /path/to/stud/stud_cli.py` directly. Set `STUD_PYTHON` if the npm launcher should use a different Python interpreter.

`serve`, `build`, and `validate` default to the current directory when no project path is supplied. Strict validation exits with `1` for failures, `2` for warnings or unverified work, and `0` otherwise.

### Project files

```text
my-workshop/
├── design.py                 # Model source; created by init
├── README.md
├── annotations/              # Created as comments and prices are saved
│   ├── comments.json
│   ├── prices.json
│   └── screenshots/
└── output/model/             # Generated model and CSV exports
```

Keep source files, helper modules, project documents, and the entire `annotations/` folder in your project's repository or backup. Generated `output/model/` files can be rebuilt. The app repository contains no default design; its ignored `projects/` folder is only a convenience for local work.

Invalid rebuilds keep the last good preview and exports. The viewer watches top-level project Python files and `src/` helpers.

Design files execute Python, so only open trusted projects. The viewer server binds to loopback for local use.

### Validation behavior

A starter project has automatic collision and stock-fit checks but no declared relationships, so its coverage is reported as unverified. See the [validation guide](docs/validation.md) for coverage, tolerances, and supported checks.


See [Environment assets](docs/environment.md) for project-local procedural Three.js geometry, including a tree example.
