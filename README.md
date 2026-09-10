# stud

**Use ChatGPT to design your next construction project. See it in 3D. Get a real materials estimate.**

https://github.com/user-attachments/assets/3c090bcd-924d-44f1-95b7-147368a61008

Describe what you want to build: a garage workbench, storage shelves, or a framed wall with an opening. stud gives your AI a workshop for turning that conversation into a design you can inspect, revise, and price. You bring the idea and the measurements; the AI creates the model, and you decide what needs to change.

The current workflow runs through **[ChatGPT for desktop](https://chatgpt.com/download/)**, with stud's live viewer open alongside the conversation. You don't need to write code to design a project.

This source revision introduces CadQuery projects, explicit editing requests, saved alternatives and vector plan packets. For native release verification, see the [implementation ledger](docs/IMPLEMENTATION.md); previously published installers can use the older project format.

## What you get

**A 3D view as the design changes.** Explore the model, switch between front, side, top, and perspective views, and isolate assemblies to see how the pieces fit together. The viewer updates as the agent edits the project.

**Revisions through conversation.** Ask for a taller bench, a wider opening, or another shelf. Inspect individual parts and dimensions before deciding on the next change.

**Feedback attached to the design.** Comment on a part or capture an area of the viewer and describe what needs attention. Ask the agent to read your comments and revise the project. Saved screenshots keep the view you were discussing, even after the design changes.

**A material list and a working budget.** Review stock quantities, add supplier quotes, adjust quantities, and paste pricing from a spreadsheet. Export parts, materials, and costs as CSVs.

**Geometry checks while you iterate.** Find overlapping parts and pieces that don't fit the selected stock. Add requirements for contact, support, openings, and alignment; inspect the findings and coverage in the viewer.

**Project files you own.** Designs, comments, screenshots, and prices live in a local folder. Keep each project in its own repository or backup and return to it later. The modeling engine, checks, viewer, and exports run locally; your AI assistant has its own connection requirements.

## Install

### Desktop app (macOS and Windows)

Download an installer from [GitHub Releases](https://github.com/getstud/stud/releases). Current builds are marked **Pre-release**. Open the newest version's **Assets** section and choose the file for your computer:

| Platform | Installer filename |
| --- | --- |
| macOS, Apple Silicon (M-series) | `stud_<version>_aarch64.dmg` |
| macOS, Intel | `stud_<version>_x64.dmg` |
| Windows, x64 | `stud_<version>_x64-setup.exe` |

The desktop build includes stud, Python, CadQuery, PDF dependencies, Git and the browser viewer. You don't need to install Python, Git or Node.js separately. The desktop window handles setup and updates; you review designs in the browser.

**macOS**

1. Open the stud `.dmg` installer and drag stud into Applications.
2. Open stud and choose **Install command-line tool**. macOS may ask for an administrator password to add `/usr/local/bin/stud`.
3. Restart your terminal or Codex, then run `stud --version` to confirm installation.

**Windows**

1. Run the stud `-setup.exe` installer. It installs for your user account and adds stud to your PATH.
2. Restart your terminal or Codex, then run `stud --version` to confirm installation.
3. If the command isn't found, open stud and choose **Install command-line tool** to repair the PATH entry, then restart your terminal.

See the [desktop guide](docs/desktop.md) for building installers locally and details about updates.

### Run from source

Install Git, Python 3.13, and Node.js/npm.

The source launcher uses `STUD_PYTHON`, or looks for `python3` by default. Set it to the project's virtual environment before running stud, as shown below. In Windows PowerShell, after cloning and entering the checkout, replace the three Python/environment commands below with `py -3.13 -m venv .venv`, `.venv\Scripts\python.exe -m pip install --require-hashes -r requirements.lock`, and `$env:STUD_PYTHON = "$PWD\.venv\Scripts\python.exe"`.

From a terminal:

```sh
git clone https://github.com/getstud/stud.git
cd stud
python3.13 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements.lock
export STUD_PYTHON="$PWD/.venv/bin/python"
npm ci
npm link
```

Check that the command is available with `stud --version`. Keep the checkout in place: `npm link` points the command at this folder. If you prefer to skip `npm link`, run commands from the checkout as `npm run stud -- <command>`:

```sh
npm run stud -- --version
npm run stud -- init ../my-workbench --name "Garage workbench"
npm run stud -- serve ../my-workbench
```

Open [localhost:8765](http://127.0.0.1:8765) to view the project. Stop the server with Ctrl+C. The project directory must not already exist; keeping it outside the checkout makes it easier to update stud independently of your designs.

Run `stud doctor` to check CAD, PDF and Git availability.

The [CadQuery guide](docs/cadquery.md) covers authoring, request workspaces, native measurements and packets. A [detailed shed fixture](examples/cadquery-shed/README.md) exercises framed openings, sheathing cuts, birdsmouths and supported seams. The older [framed shed](examples/framed-shed/README.md) remains a legacy API example.

## Make something

Open Codex and describe your project:

> Use stud to design a workbench for my garage. It should be 6 feet wide and 24 inches deep, with a plywood top and a shelf underneath. Use standard lumber. Create a new project folder, open the viewer, and show me the dimensions and material list.

Have the agent create the project and open its viewer before building the design in stages. Existing designs appear immediately when the viewer opens. New parts drop into place and fade in after successful live rebuilds. The equivalent commands are:

```sh
stud init my-workbench --name "Garage workbench"
stud serve my-workbench
```

For each requested design change, the agent reads `stud status`, calls `stud begin`, edits the returned workspace, evaluates its captured source and calls `stud finish`. That saves one recoverable checkpoint. The **Versions** page compares alternatives, displays original estimates and restores an older design as a new checkpoint while keeping review history.

The command opens your browser before the first build. Use `--no-open` to open the printed URL in Codex’s in-app browser instead. You can also open [localhost:8765](http://127.0.0.1:8765) in Codex's in-app browser or another browser. Then keep the conversation going:

> Make it 36 inches tall and leave room below the shelf for my toolbox.

> Show me the frame without the top so I can see the connections.

> Read my comments and update the design.

> Update the material list and estimate the cost using the supplier prices I entered.

Give the agent the measurements and constraints that matter to your space. Review the resulting dimensions and checks as you refine the project.

## The checks

stud checks the geometry in the model and the requirements declared for the design:

| Check | What it looks for |
| --- | --- |
| Solid collision | Parts occupying the same space |
| Stock fit | Parts that don't fit the specified stock |
| Measured contact | Required contact between parts |
| Panel support | Declared support requirements for panels |
| Opening clearance | Space that must remain clear |
| Face alignment | Faces that should line up |

The native starter declares length and stock-fit requirements. Other relationships, including collisions, must be declared; the viewer's **Checks** section shows findings and coverage. A model with no declared relationships reports incomplete coverage.

These are geometry checks, not structural engineering or building-code approval. Native purchasing data includes actual stock cuts and explicit sheet layouts; missing fabrication details and prices remain visible. See the [CadQuery guide](docs/cadquery.md) for native measurements and the [legacy validation guide](docs/validation.md) for older projects.

## Your materials, your prices

The design defines the stock sizes and materials it uses. stud calculates quantities from the model, while the costs table lets you save supplier quotes and quantity overrides for your project. Coverage materials use a single-face purchase allowance rather than total surface area.

Parts, materials, and cost exports come from the same model revision. If a rebuild fails, stud retains the last good preview and exports so you can correct the design and try again.

## Pick up where you left off

The desktop app lists remembered projects, with their folder locations and missing-folder status. Projects are registered by `stud init`, `serve`, `build`, and `validate`; the list refreshes when the app regains focus or you select Refresh.

Use **Add project** in the desktop app to choose an existing project with the native folder picker. The folder must contain `design.py`; adding it does not execute the design. You can also register an existing project with `stud projects --add /path/to/project`. Use `stud projects` to list projects in a terminal, or `stud projects --json` for tools. Stud tracks the folders you use; it does not scan your computer. If you move a project, register its new location.

The catalog is stored separately from designs in `~/Library/Application Support/stud/projects.sqlite3` on macOS, `%LOCALAPPDATA%/stud/projects.sqlite3` on Windows, and `$XDG_DATA_HOME/stud/projects.sqlite3` (default `~/.local/share`) on Linux. `STUD_DATA_DIR` overrides the catalog directory.

Current projects keep immutable prompts and quotes in `records/`, saved reports in `checkpoints/`, and immutable PDF packets in `exports/`. Keep `.git` for history and `.stud` for recoverable drafts and artifacts when copying the folder. Legacy projects retain their `annotations/` and `output/model/` folders. Designs live separately from the app.

## The commands

The agent and the desktop installation use the same CLI:

```text
stud init <directory>              create a project with a starter model
stud init <directory> --example shed  create a detailed construction fixture
stud serve [directory]             start the live viewer
stud serve [directory] --port 8766  use a different port
stud status [directory]            inspect current request, build and option
stud begin [directory] ...         start an isolated editing request
stud evaluate [directory] ...      evaluate a captured source
stud finish [directory] ...        finalize one request and checkpoint
stud compare [directory] ...       compare two fixed checkpoints
stud plans [directory] ...         generate an immutable PDF packet
stud doctor                       inspect the installed runtime
stud build [directory]             evaluate the current design
stud validate [directory]          check the design
stud validate [directory] --json   return machine-readable findings
stud validate [directory] --strict fail on warnings or unverified coverage
stud --version                     print the installed version
```

`init` requires a new directory. Other project commands default to the current directory. Use a command's `--help` for its required identities and flags. Current geometry and its check outcome are separate; failed requirements remain inspectable.

## Under the hood

The AI writes ordinary Python and CadQuery, then registers named completed parts, requirements, purchasing data and drawings. Current models use millimeters, with Z pointing up; `inches()` converts imperial inputs. Legacy models retain their inch-based API.

The browser viewer uses Three.js. In a compatible browser, the optional WebMCP `show` tool lets an agent focus the viewer on particular parts or a region. Browsers without WebMCP still support the normal viewer interface.

See the [workshop guide](docs/workshop.md) for modeling, comments, pricing, exports, and viewer integration, or [framed assemblies](docs/assemblies.md) for reusable wall and opening builders.

## Troubleshooting

**The terminal can't find `stud`.** Enable the command through the desktop setup, then restart your terminal or Codex. For a source checkout, run `npm link` or use `npm run stud --` from the repository.

**The source launcher can't find Python.** Install the Python 3.13 environment and locked dependencies above, then set `STUD_PYTHON`. The desktop build includes its own runtime. `stud doctor` identifies missing or incompatible packages.

**The viewer still shows an older design.** A failed rebuild keeps the last good model. Check the reported build error and have the agent correct it. Viewer JavaScript or CSS changes require a browser refresh; server changes require a restart.

**The viewer port is already in use.** Stop the other server or run `stud serve <directory> --port 8766`, then open that port in your browser.

**Checks say the design is unverified.** Automatic checks don't cover every intended relationship. Ask the agent to declare the relevant requirements and review coverage in the Checks section.

Only open trusted projects: their design files execute Python. The viewer server binds to loopback for local use.

## Contributing

Bug reports, improvements, and pull requests are welcome. Use [GitHub issues](https://github.com/getstud/stud/issues) to report a reproducible problem or discuss a substantial change.

Development setup, the modeling API, project layout, and test commands are in [CONTRIBUTING.md](CONTRIBUTING.md). Desktop packaging and release instructions are in the [desktop guide](docs/desktop.md).

## License

The package metadata declares **ISC**. A standalone `LICENSE` file has not yet been added to this repository. Bundled desktop dependency notices are listed in [third-party notices](desktop/THIRD_PARTY_NOTICES.md).

To explore a design freely, choose **View → Fly**, then click the scene.
Use **W/A/S/D** to fly, **drag** to look around, **Q/E** to descend or ascend,
and hold **Shift** to move faster. Flight can pass through surfaces to inspect
interiors. **Esc** releases keyboard control; choose **3D** to return to orbit
controls, or **Fit design** to return to an overview.
