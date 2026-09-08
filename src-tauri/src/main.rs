#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use fs2::FileExt;
use serde::Serialize;
use std::{
    fs::{self, File, OpenOptions},
    process::Command,
    sync::Mutex,
    time::Duration,
};
use tauri::{Manager, State};
use tauri_plugin_dialog::DialogExt;
use tauri_plugin_updater::UpdaterExt;
#[path = "../../desktop/integration.rs"]
mod integration;

#[derive(Default)]
struct Updates(Mutex<Option<tauri_plugin_updater::Update>>);

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct Status {
    version: String,
    python: String,
    cli_path: String,
    cli_installed: bool,
    updates_configured: bool,
}

fn updates_configured(app: &tauri::AppHandle) -> bool {
    app.config()
        .plugins
        .0
        .get("updater")
        .and_then(|v| v.get("endpoints"))
        .and_then(|v| v.as_array())
        .map(|v| !v.is_empty())
        .unwrap_or(false)
}

#[tauri::command]
async fn status(app: tauri::AppHandle) -> Result<Status, String> {
    let resources = app.path().resource_dir().map_err(|e| e.to_string())?;
    #[cfg(windows)]
    let python = resources.join("runtime/python.exe");
    #[cfg(not(windows))]
    let python = resources.join("runtime/bin/python3");
    let output = tauri::async_runtime::spawn_blocking(move || {
        let mut command = Command::new(python);
        command.args(["-E", "-s", "--version"]);
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            command.creation_flags(0x08000000);
        }
        command.output()
    })
    .await
    .map_err(|e| e.to_string())?;
    let python = match output {
        Ok(out) if out.status.success() => String::from_utf8_lossy(&out.stdout).trim().to_owned(),
        _ => "Runtime unavailable — rebuild or reinstall stud".into(),
    };
    Ok(Status {
        version: app.package_info().version.to_string(),
        python,
        cli_path: integration::cli_source()?.display().to_string(),
        cli_installed: integration::cli_installed(),
        updates_configured: updates_configured(&app),
    })
}

#[tauri::command]
async fn list_projects(app: tauri::AppHandle) -> Result<serde_json::Value, String> {
    project_catalog(app, None).await
}

#[tauri::command]
async fn add_project(app: tauri::AppHandle, window: tauri::WebviewWindow) -> Result<bool, String> {
    let dialog = app
        .dialog()
        .file()
        .set_title("Add a Stud project")
        .set_parent(&window);
    let selected = tauri::async_runtime::spawn_blocking(move || dialog.blocking_pick_folder())
        .await
        .map_err(|e| e.to_string())?;
    let Some(selected) = selected else {
        return Ok(false);
    };
    let path = selected.into_path().map_err(|e| e.to_string())?;
    project_catalog(app, Some(path)).await?;
    Ok(true)
}

async fn project_catalog(
    app: tauri::AppHandle,
    add: Option<std::path::PathBuf>,
) -> Result<serde_json::Value, String> {
    let resources = app.path().resource_dir().map_err(|e| e.to_string())?;
    tauri::async_runtime::spawn_blocking(move || {
        #[cfg(windows)]
        let python = resources.join("runtime/python.exe");
        #[cfg(not(windows))]
        let python = resources.join("runtime/bin/python3");
        let mut command = Command::new(python);
        command
            .args(["-B", "-E", "-s"])
            .arg(resources.join("engine/stud_cli.py"))
            .args(["projects", "--json"]);
        if let Some(path) = add {
            command.arg("--add").arg(path);
        }
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            command.creation_flags(0x08000000);
        }
        let output = command.output().map_err(|e| e.to_string())?;
        if !output.status.success() {
            return Err(String::from_utf8_lossy(&output.stderr).trim().to_owned());
        }
        serde_json::from_slice(&output.stdout).map_err(|e| e.to_string())
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
async fn install_cli() -> Result<String, String> {
    tauri::async_runtime::spawn_blocking(integration::install_cli)
        .await
        .map_err(|e| e.to_string())?
}

#[tauri::command]
async fn check_update(
    app: tauri::AppHandle,
    updates: State<'_, Updates>,
) -> Result<Option<String>, String> {
    if !updates_configured(&app) {
        return Err("This local build has no release channel configured.".into());
    }
    let update = app
        .updater_builder()
        .timeout(Duration::from_secs(20))
        .build()
        .map_err(|e| e.to_string())?
        .check()
        .await
        .map_err(|e| e.to_string())?;
    let version = update.as_ref().map(|u| u.version.clone());
    *updates.0.lock().map_err(|e| e.to_string())? = update;
    Ok(version)
}

fn update_lock(app: &tauri::AppHandle) -> Result<File, String> {
    let directory = app.path().app_data_dir().map_err(|e| e.to_string())?;
    fs::create_dir_all(&directory).map_err(|e| e.to_string())?;
    let file = OpenOptions::new()
        .create(true)
        .truncate(false)
        .read(true)
        .write(true)
        .open(directory.join("runtime.lock"))
        .map_err(|e| e.to_string())?;
    file.try_lock_exclusive().map_err(|_| {
        "Stop running stud viewers and CLI commands before installing an update.".to_owned()
    })?;
    Ok(file)
}

#[tauri::command]
async fn install_update(app: tauri::AppHandle, updates: State<'_, Updates>) -> Result<(), String> {
    let _lock = update_lock(&app)?;
    let update = updates
        .0
        .lock()
        .map_err(|e| e.to_string())?
        .take()
        .ok_or("Check for an update first.")?;
    update
        .download_and_install(|_, _| {}, || {})
        .await
        .map_err(|e| e.to_string())?;
    app.restart();
}

fn main() {
    // Installer hooks operate before opening a WebView or initializing plugins.
    #[cfg(windows)]
    match std::env::args().nth(1).as_deref() {
        Some("--install-cli") => std::process::exit(if integration::install_cli().is_ok() {
            0
        } else {
            1
        }),
        Some("--uninstall-cli") => std::process::exit(if integration::uninstall_cli().is_ok() {
            0
        } else {
            1
        }),
        _ => {}
    }
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .manage(Updates::default())
        .setup(|app| {
            if updates_configured(app.handle()) {
                app.handle()
                    .plugin(tauri_plugin_updater::Builder::new().build())?;
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            status,
            list_projects,
            add_project,
            install_cli,
            check_update,
            install_update
        ])
        .run(tauri::generate_context!())
        .expect("Could not start stud");
}

#[cfg(test)]
mod update_tests;
