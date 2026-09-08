use std::path::{Path, PathBuf};
#[cfg(target_os = "macos")]
use std::{fs, process::Command};

pub fn cli_source() -> Result<PathBuf, String> {
    let executable = std::env::current_exe().map_err(|e| e.to_string())?;
    Ok(executable
        .parent()
        .ok_or("Missing application directory")?
        .join(if cfg!(windows) { "stud.exe" } else { "stud" }))
}

pub fn cli_installed() -> bool {
    let Ok(source) = cli_source() else {
        return false;
    };
    #[cfg(target_os = "macos")]
    {
        fs::read_link("/usr/local/bin/stud").ok().as_ref() == Some(&source)
    }
    #[cfg(windows)]
    {
        user_path()
            .map(|p| {
                path_entries(&p)
                    .iter()
                    .any(|p| same_path(p, source.parent().unwrap()))
            })
            .unwrap_or(false)
    }
    #[cfg(not(any(windows, target_os = "macos")))]
    {
        false
    }
}

#[cfg(target_os = "macos")]
fn shell_quote(value: &str) -> String {
    format!("'{}'", value.replace('\'', "'\\''"))
}

#[cfg(target_os = "macos")]
pub fn install_cli() -> Result<String, String> {
    let source = cli_source()?;
    if !source.is_file() {
        return Err("The bundled CLI is missing. Build or reinstall stud.".into());
    }
    let text = source.to_string_lossy();
    if text.contains("/AppTranslocation/") || text.starts_with("/Volumes/") {
        return Err(
            "Move stud to Applications and open it there before installing the CLI.".into(),
        );
    }
    let destination = Path::new("/usr/local/bin/stud");
    if let Ok(metadata) = fs::symlink_metadata(destination) {
        let owned = metadata.file_type().is_symlink()
            && fs::read_link(destination)
                .map(|p| p.ends_with("Contents/MacOS/stud"))
                .unwrap_or(false);
        if !owned {
            return Err("/usr/local/bin/stud already exists and is not a stud app launcher. Move it aside first.".into());
        }
    }
    // Re-check ownership inside the privileged operation as well.
    let script = format!("set -eu; mkdir -p /usr/local/bin; if [ -e /usr/local/bin/stud ] || [ -L /usr/local/bin/stud ]; then case $(readlink /usr/local/bin/stud) in */Contents/MacOS/stud) ;; *) exit 1;; esac; fi; ln -sfn {} /usr/local/bin/stud", shell_quote(&text));
    let apple_script = format!(
        "do shell script {} with administrator privileges",
        serde_json::to_string(&script).map_err(|e| e.to_string())?
    );
    let output = Command::new("/usr/bin/osascript")
        .args(["-e", &apple_script])
        .output()
        .map_err(|e| e.to_string())?;
    if !output.status.success() {
        return Err("CLI installation was cancelled or could not be completed.".into());
    }
    Ok("Installed at /usr/local/bin/stud. Open a new Codex terminal to use it.".into())
}

#[cfg(windows)]
fn user_path() -> Result<String, String> {
    use winreg::{enums::HKEY_CURRENT_USER, RegKey};
    let env = RegKey::predef(HKEY_CURRENT_USER)
        .open_subkey("Environment")
        .map_err(|e| e.to_string())?;
    match env.get_value("Path") {
        Ok(value) => Ok(value),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(String::new()),
        Err(e) => Err(e.to_string()),
    }
}
#[cfg(windows)]
fn path_entries(value: &str) -> Vec<PathBuf> {
    value
        .split(';')
        .filter(|s| !s.is_empty())
        .map(PathBuf::from)
        .collect()
}
#[cfg(windows)]
fn same_path(a: &Path, b: &Path) -> bool {
    a.to_string_lossy()
        .trim_end_matches('\\')
        .eq_ignore_ascii_case(b.to_string_lossy().trim_end_matches('\\'))
}
#[cfg(windows)]
fn write_user_path(value: &str) -> Result<(), String> {
    use windows_sys::Win32::UI::WindowsAndMessaging::{
        SendMessageTimeoutW, HWND_BROADCAST, SMTO_ABORTIFHUNG, WM_SETTINGCHANGE,
    };
    use winreg::{
        enums::{HKEY_CURRENT_USER, REG_EXPAND_SZ},
        types::ToRegValue,
        RegKey,
    };
    let (env, _) = RegKey::predef(HKEY_CURRENT_USER)
        .create_subkey("Environment")
        .map_err(|e| e.to_string())?;
    let mut raw = value.to_reg_value();
    raw.vtype = REG_EXPAND_SZ;
    env.set_raw_value("Path", &raw).map_err(|e| e.to_string())?;
    let name: Vec<u16> = "Environment\0".encode_utf16().collect();
    unsafe {
        SendMessageTimeoutW(
            HWND_BROADCAST,
            WM_SETTINGCHANGE,
            0,
            name.as_ptr() as isize,
            SMTO_ABORTIFHUNG,
            5000,
            std::ptr::null_mut(),
        );
    }
    Ok(())
}
#[cfg(windows)]
pub fn install_cli() -> Result<String, String> {
    let source = cli_source()?;
    if !source.is_file() {
        return Err("The bundled CLI is missing. Reinstall stud.".into());
    }
    let directory = source.parent().unwrap();
    let current = user_path()?;
    if !path_entries(&current)
        .iter()
        .any(|p| same_path(p, directory))
    {
        let separator = if current.is_empty() || current.ends_with(';') {
            ""
        } else {
            ";"
        };
        write_user_path(&format!("{current}{separator}{}", directory.display()))?;
    }
    Ok("CLI installed for your account. Restart Codex and your terminal to refresh PATH.".into())
}
#[cfg(windows)]
pub fn uninstall_cli() -> Result<(), String> {
    let source = cli_source()?;
    let current = user_path()?;
    let kept: Vec<_> = current
        .split(';')
        .filter(|p| !same_path(Path::new(p), source.parent().unwrap()))
        .collect();
    write_user_path(&kept.join(";"))
}
#[cfg(not(any(windows, target_os = "macos")))]
pub fn install_cli() -> Result<String, String> {
    Err("stud desktop supports macOS and Windows.".into())
}
