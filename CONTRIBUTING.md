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

Viewer JavaScript and CSS changes need a browser refresh; server changes need a restart.

Viewer features include their conversation interface: define representative voice requests, expose the same operations through WebMCP, and verify both the returned context and visible behavior through the registered tools. Reuse the shared control activity wrapper so its glow lasts through rendering and asynchronous jobs. See the [existing parity inventory and contracts](docs/voice-viewer.md); feature owners preserve that parity as their UI evolves.

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

Open [localhost:8765](http://127.0.0.1:8765) in your browser or Codex's in-app browser. Begin a request, edit its isolated workspace, capture source, and evaluate explicitly to update the viewer. Stop the server with Ctrl+C.

`init` creates a starter model and requires a directory that does not already exist. Designs live separately from the stud checkout.

### Modeling API

Projects use ordinary CadQuery with the registration interface in [cadquery.md](docs/cadquery.md). A valid `stud.json` declares the engine, units and source files. `design.py` exports `model = Model(...)` from `stud.cad`. Changes run in explicit request workspaces and finish as checkpoints.

Use `stud init PATH --example shed` for a framing example, or author solids with CadQuery and register stable part IDs, named references, requirements, purchasing demands and drawings. Native framing helpers live in `stud.buildings`; stock operations live in `stud.construction`. Project units are fixed at initialization, with X/Y horizontal and Z up.

### CLI reference

Run these from the stud checkout:

| Command | Purpose |
| --- | --- |
| `npm run stud -- init <directory>` | Create a new project |
| `npm run stud -- serve <directory>` | Start the local viewer |
| `npm run stud -- serve <directory> --port 8766` | Serve another project on a different port |
| `npm run stud -- build <directory>` | Evaluate the saved checkpoint or active request workspace |
| `npm run stud -- validate <directory> --json` | Print machine-readable validation results |
| `npm run stud -- validate <directory> --strict` | Fail on warnings or unverified coverage as well as errors |

To install the source checkout's `stud` command, run `npm link`. You can also invoke `python3 /path/to/stud/stud_cli.py` directly. Set `STUD_PYTHON` if the npm launcher should use a different Python interpreter.

`serve`, `build`, and `validate` default to the current directory when no project path is supplied. Strict validation exits with `1` for failures, `2` for warnings or unverified work, and `0` otherwise.

### Project files

```text
my-workshop/
├── stud.json                 # Project identity, engine, units and source patterns
├── design.py                 # Model source
├── records/                  # Versioned prompts, captures and prices
├── checkpoints/              # Saved reports
├── exports/                  # Immutable drawing packets and CSVs
├── .git/                     # Project history
└── .stud/                    # Coordinator state, isolated drafts and native artifacts
```

Keep the full project folder when copying or backing it up. Initialization requires a new folder outside another repository. A missing or invalid manifest is an error; serving or building that folder never selects another Python API. A failed evaluation retains the previous complete geometry with a distinct source/build identity.

Design files execute Python, so only open trusted projects. The viewer server binds to loopback for local use.

### Validation behavior

The starter declares length and stock-fit requirements. Native findings distinguish failures, unresolved or unsupported checks, and coverage gaps. See [CadQuery geometric evidence](docs/cadquery.md#native-geometric-evidence). Geometry checks do not establish structural capacity or construction approval.
