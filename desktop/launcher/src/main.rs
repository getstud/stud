use fs2::FileExt;
use std::{
    env,
    fs::{self, OpenOptions},
    path::PathBuf,
    process::{Command, ExitCode},
};

fn resources() -> Result<PathBuf, Box<dyn std::error::Error>> {
    let executable = fs::canonicalize(env::current_exe()?)?;
    let parent = executable
        .parent()
        .ok_or("Cannot locate stud installation")?;
    #[cfg(target_os = "macos")]
    let root = parent.join("../Resources");
    #[cfg(not(target_os = "macos"))]
    let root = parent.to_path_buf();
    Ok(root)
}

fn run() -> Result<i32, Box<dyn std::error::Error>> {
    let resources = resources()?;
    #[cfg(windows)]
    let python = resources.join("runtime/python.exe");
    #[cfg(not(windows))]
    let python = resources.join("runtime/bin/python3");
    let script = resources.join("engine/stud_cli.py");
    if !python.is_file() || !script.is_file() {
        return Err(
            "stud's bundled runtime is missing. Reinstall the app; do not copy the CLI out of it."
                .into(),
        );
    }
    #[cfg(windows)]
    let support = PathBuf::from(env::var_os("APPDATA").ok_or("APPDATA is unavailable")?)
        .join("app.stud.desktop");
    #[cfg(target_os = "macos")]
    let support = PathBuf::from(env::var_os("HOME").ok_or("HOME is unavailable")?)
        .join("Library/Application Support/app.stud.desktop");
    #[cfg(not(any(windows, target_os = "macos")))]
    let support = PathBuf::from(env::var_os("HOME").ok_or("HOME is unavailable")?)
        .join(".local/share/app.stud.desktop");
    fs::create_dir_all(&support)?;
    let lock = OpenOptions::new()
        .create(true)
        .truncate(false)
        .read(true)
        .write(true)
        .open(support.join("runtime.lock"))?;
    FileExt::try_lock_shared(&lock)
        .map_err(|_| "stud is being updated. Try again when the update finishes.")?;
    let mut command = Command::new(python);
    command
        .args(["-B", "-E", "-s", "-X", "utf8"])
        .arg(script)
        .args(env::args_os().skip(1))
        .env_remove("PYTHONHOME")
        .env_remove("PYTHONPATH")
        .env_remove("PYTHONUSERBASE");
    #[cfg(unix)]
    {
        use std::os::{fd::AsRawFd, unix::process::CommandExt};
        // Keep the shared update lock in Python across exec, while preserving
        // normal terminal signals and the caller's working directory.
        let fd = lock.as_raw_fd();
        if unsafe { libc::fcntl(fd, libc::F_SETFD, 0) } == -1 {
            return Err(std::io::Error::last_os_error().into());
        }
        Err(command.exec().into())
    }
    #[cfg(not(unix))]
    {
        let status = command.status()?;
        drop(lock);
        Ok(status.code().unwrap_or(1))
    }
}

fn main() -> ExitCode {
    match run() {
        Ok(code) => ExitCode::from(code.clamp(0, 255) as u8),
        Err(error) => {
            eprintln!("stud: {error}");
            ExitCode::FAILURE
        }
    }
}
