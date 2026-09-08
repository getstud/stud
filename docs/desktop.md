# stud desktop

stud is distributed as a Tauri v2 application that includes the Python runtime,
modeling engine, browser viewer, and native `stud` command. Node and a system
Python installation are not required on the user's computer.

The first desktop window handles setup and updates. Codex remains the design
workspace: it runs `stud` against a project folder and opens the local viewer URL
in its in-app browser. The desktop WebView does not load executable project
content or expose its desktop permissions to the model viewer.

## Install and use

### macOS

1. Open the DMG and drag stud into Applications.
2. Open stud and choose **Install command-line tool**. macOS may request an
   administrator password to add `/usr/local/bin/stud`.
3. In a new Codex terminal, run `stud --version`.

The command is a symlink into the app, so app updates update the CLI too. If an
unrelated `stud` command already occupies that path, the app refuses to overwrite
it. If you move or rename the app later, run CLI installation again.

### Windows

Run the NSIS `-setup.exe` installer. It installs for the current user, includes
WebView2's offline installer, and adds the installed directory to the user's
PATH. Restart Codex and existing terminals after installation. The setup window
also provides **Install command-line tool** to repair the PATH entry. Uninstall
removes that installation's PATH entry and leaves project folders untouched.

### Work from any project folder

```sh
stud init my-project
stud serve my-project
stud build my-project
stud validate my-project
```

With no folder argument, `serve`, `build`, and `validate` use the current working
directory. Paths with spaces are supported. Copy the CLI path from the app if
Codex's process has not picked up a changed PATH.

Projects are executable Python plus project-owned annotations. They are never
stored in the app bundle. The CLI uses the bundled Python rather than searching
PATH; exports and comments are written into the selected project only.

## Build locally

Build requirements: Node 22+, Rust stable, and the platform's Tauri prerequisites
(Xcode Command Line Tools on macOS; MSVC C++ build tools on Windows). These are
build-machine requirements, not user requirements.

```sh
npm ci
npm run desktop:build
```

The build script downloads a pinned, SHA-256-verified Python standalone archive
from Astral's official release, compiles the small Rust CLI, and stages an explicit
list of engine files and viewer dependencies. Local projects, tests, development
tools, and caches are not shipped. Third-party notices shipped with Python and
Three.js remain in the bundle.

Supported targets:

| Build target | Native build host | Installer |
| --- | --- | --- |
| `darwin-arm64` | Apple Silicon macOS | `.app`, `.dmg` |
| `darwin-x64` | Intel macOS | `.app`, `.dmg` |
| `win32-x64` | Windows x64 | NSIS `.exe` |

Use `npm run desktop:build -- --target darwin-x64` on a matching host, or use the
GitHub Actions matrix. A local Windows cross-build is also available on macOS
with MinGW-w64, NSIS, and Rust's `x86_64-pc-windows-gnu` target:
`npm run desktop:build -- --target win32-x64 --rust-target x86_64-pc-windows-gnu`.
Cross-built installers still require testing on Windows; production CI uses the
native MSVC toolchain. Outputs are under
`src-tauri/target/<rust-target>/release/bundle/`. `npm run desktop:dev` prepares
resources and launches Tauri in development mode.

Local builds deliberately show **release channel not configured**. They are
not production-signed, notarized, or connected to an invented update feed.

## GitHub Releases and updates

stud checks for updates when the setup window opens and every six hours while
it stays open. Available updates install with **Update and restart**. Downloads
must pass Tauri's signature verification; endpoints use HTTPS. The app, CLI,
viewer, and Python are replaced together. Projects are not modified.

The browser viewer also displays a dismissible notice for newer stable releases,
with a release link and instructions to update through the desktop app. It checks
on load, when the tab becomes visible, and every 15 minutes; the local server
caches successful release checks for six hours and retries failures after 15
minutes. Offline checks do not interrupt the viewer. Dismissal lasts for that
version in the current tab session. Signed release builds embed the repository;
source checkouts can set `STUD_RELEASE_REPOSITORY=owner/repository`. Local builds
without a repository do not check for updates.

A running CLI/viewer holds a shared runtime lock. The app cannot update while
that lock is held. On Windows, NSIS takes the same exclusive lock before
installing or uninstalling files, so protection continues after the app exits.
Stop the viewer and retry the update if stud reports that it is in use.

### Release setup

1. Push the repository to GitHub. Releases are hosted in that repository.
2. Generate an updater signing key outside the repository:
   `npx tauri signer generate -w <secure-path>/stud.key`.
   Keep the private key and its password in secure storage with a backup. The
   same key must sign future updates; do not regenerate it for each release.
3. Set the repository variable `STUD_UPDATER_PUBLIC_KEY` to the **contents** of
   the `.pub` file. Set secrets `TAURI_SIGNING_PRIVATE_KEY` and
   `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` to the private key and its password.
4. Configure platform code signing separately. For macOS, provide
   `APPLE_CERTIFICATE`, `APPLE_CERTIFICATE_PASSWORD`, `APPLE_SIGNING_IDENTITY`,
   `APPLE_ID`, `APPLE_PASSWORD`, and `APPLE_TEAM_ID` to the workflow. For Windows,
   configure an Authenticode certificate/signing provider through Tauri's
   Windows signing configuration. Updater signatures do not replace platform
   code signing. Verify nested Python libraries are included in signing before
   a public release.
5. Keep `package.json`, `src-tauri/Cargo.toml`, and
   `desktop/launcher/Cargo.toml` versions in sync, then push `v<version>`.

`.github/workflows/desktop.yml` builds the three targets and creates a **draft**
GitHub Release with installers, signed update artifacts, and `latest.json`.
Check every build and smoke test before publishing the draft. The updater reads
`https://github.com/<owner>/<repository>/releases/latest/download/latest.json`.
A manual workflow run produces unsigned test installers as Actions artifacts.

For a local signed updater build, copy `desktop/release.example.json` to
`desktop/release.local.json`, fill in the repository and public key, set
`TAURI_SIGNING_PRIVATE_KEY` and its password in the environment, and run:

```sh
npm run desktop:build -- --release
```

Do not commit private keys or the local release configuration. Production keys,
platform certificates, and a published GitHub release are required to enable
real end-to-end updates; the local build does not provision those accounts.

## Verification

```sh
npm test
cargo test --release --manifest-path src-tauri/Cargo.toml --bin stud-desktop
node scripts/smoke-desktop.mjs /path/to/packaged/stud
```

The Rust tests check a real signed update fixture, rejection of tampered bytes,
and production HTTPS enforcement without installing an update.

The smoke test uses only the app's Python, creates an external project with spaces
and Unicode in its name, builds and validates it, serves all viewer assets, saves
a comment, and checks that CLI sessions and updates exclude each other. The CI
Windows job installs the actual NSIS artifact before running that smoke test,
then uninstalls it. Test a signed old-to-new update on both platforms before the
first public release.

References: [Tauri v2 updater](https://v2.tauri.app/plugin/updater/),
[Windows installers](https://v2.tauri.app/distribute/windows-installer/),
[macOS signing](https://v2.tauri.app/distribute/sign/macos/),
[Python standalone](https://github.com/astral-sh/python-build-standalone).
