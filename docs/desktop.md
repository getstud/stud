# stud desktop

stud's Tauri v2 build includes Python, CadQuery, the vector PDF runtime, Git,
the browser viewer and the native `stud` command. Node and system Python/Git
installations are not required on the user's computer. Verified platform and
release results are recorded in [IMPLEMENTATION.md](IMPLEMENTATION.md).

The app includes the `stud-design` Codex skill at `skills/stud-design` in its
resources (`stud.app/Contents/Resources` on macOS; the installation directory on
Windows). On macOS, setup links the skill into `$CODEX_HOME/skills` (or
`~/.codex/skills` when `CODEX_HOME` is unset), so it follows app updates. On
Windows, copy that entire folder into your Codex skills directory to enable it.
The version-controlled source is `skills/stud-design`; desktop builds bundle it
along with the engine README and validation reference it uses.

The first desktop window handles setup and updates. Codex remains the design
workspace: it runs `stud` against a project folder and opens the local viewer URL
in its in-app browser. The desktop WebView does not load executable project
content or expose its desktop permissions to the model viewer.

## Install and use

### macOS

1. Open the DMG and drag stud into Applications.
2. Open stud and choose **Connect CLI and skill**. macOS may request an
   administrator password to add `/usr/local/bin/stud`.
3. In a new Codex terminal, run `stud --version`.

The CLI and skill are symlinks into the app, so app updates update both. The
setup window checks both connections on launch (including after an update) and
when it regains focus. Links to an older Stud installation show **Repair
connections**; missing links show setup. Correct links need no repair or password.
Custom commands, unrelated links, and copied or edited skill folders are preserved
and reported as conflicts. Back them up and move them aside before connecting.
Start a new Codex task to load an updated skill; existing tasks can retain the
skill instructions they already loaded. App update status is separate from
connection status.

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

The preparation script downloads SHA-256-verified Python and Git archives, installs
the platform-compatible CAD/PDF packages with `--require-hashes` from
`requirements.lock`, runs a native solid/PDF import trial, and records their hashes
and versions. The build then compiles the Rust CLI and stages engine/docs/examples
and viewer dependencies. Local projects, tests and caches are not shipped. Upstream
license files remain with the bundled runtimes; see [dependency notices](../desktop/THIRD_PARTY_NOTICES.md).

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

The browser viewer also displays a dismissible notice for newer releases on the installed channel,
with a release link and instructions to update through the desktop app. It checks
on load, when the tab becomes visible, and every 15 minutes; the local server
caches successful release checks for six hours and retries failures after 15
minutes. Offline checks do not interrupt the viewer. Dismissal lasts for that
version in the current tab session. Signed release builds embed the repository;
source checkouts can set `STUD_RELEASE_REPOSITORY=owner/repository`. Local builds
without a repository do not check for updates. Source checkouts default to stable;
set `STUD_RELEASE_CHANNEL=preview` to check preview releases.

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
   code signing. Tagged macOS builds explicitly sign the bundled Python
   executables and native libraries before app signing and notarization; CI then
   verifies the app signature and stapled notarization ticket.
5. Keep `package.json`, `src-tauri/Cargo.toml`, and
   `desktop/launcher/Cargo.toml` versions in sync, then push `v<version>`. Use `X.Y.Z` for stable or `X.Y.Z-preview.N` for preview.
   Other prerelease formats are rejected before building.

`.github/workflows/desktop.yml` builds the three targets and creates a **draft**
GitHub Release with installers, signed update artifacts, and `latest.json`.
Check every build and smoke test before publishing the draft. The updater reads
`https://github.com/<owner>/<repository>/releases/latest/download/latest.json`.
A manual workflow run on a branch produces test installers as Actions artifacts.
A manual run on a release tag follows the signed release path.

### Stable and preview channels

Stable is for everyday use. Preview is for testing selected upcoming changes
without building from source. Preview releases are published when there is
something ready to test, rather than on a nightly schedule.

| Channel | Version / tag example | Updater feed |
| --- | --- | --- |
| Stable | `1.0.0` / `v1.0.0` | `releases/latest/download/latest.json` |
| Preview | `1.1.0-preview.1` / `v1.1.0-preview.1` | `releases/download/channel-preview/latest.json` |

The version selects the channel at build time, including local signed builds.
Both channels use the same updater signing key and app identity. Install the
installer for the desired channel to switch; they replace the same app and CLI,
not two side-by-side installations. Preview installations follow preview releases;
install a stable release explicitly to leave the preview channel.

1. Update all three version manifests (and their lockfiles), commit, and push the
   matching version tag. Never reuse a published version tag.
2. Wait for **Desktop installers** to finish successfully for all three targets.
   The final job validates the combined updater manifest and attaches
   `release-ready.json` to the draft only after all smoke tests pass. The marker
   binds to the manifest SHA-256 and is cleared before a draft rebuild. Published
   versions cannot be rebuilt.
3. Inspect the installers and perform the signed old-to-new update test before
   publishing. Stable releases must not be marked prerelease; preview releases must.
4. Publishing a preview triggers **Publish preview update feed**, which validates the
   readiness marker and all three signed artifact entries, then copies only the
   manifest to the reserved `channel-preview` prerelease. Artifact URLs continue to
   point to the immutable versioned release. Older preview publications cannot move
   the feed backward. Do not delete or manually repurpose `channel-preview`.
5. The feed workflow must exist on the default branch before publication. If a
   publication used `GITHUB_TOKEN` (which does not trigger another workflow), or a
   feed update failed, manually run **Publish preview update feed** with the published
   preview tag. Rerunning is safe.

Stable updates become available when GitHub marks the published stable release
as Latest. The preview feed prerelease is never marked Latest. Draft releases are
not available to installed apps. Do not publish a draft without its readiness
marker; stable publication is a manual release gate.

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
