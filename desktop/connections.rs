//! Inspect only Stud-owned symlinks; copied/custom installations need user action.
use std::{
    fs,
    path::{Path, PathBuf},
};

#[derive(Debug, PartialEq, Eq)]
pub enum Connection {
    Connected,
    Missing,
    Stale,
    Conflict,
}
impl Connection {
    pub fn label(&self) -> &'static str {
        match self {
            Self::Connected => "connected",
            Self::Missing => "missing",
            Self::Stale => "stale",
            Self::Conflict => "conflict",
        }
    }
}

pub fn inspect(destination: &Path, source: &Path, suffix: &Path) -> Result<Connection, String> {
    let metadata = match fs::symlink_metadata(destination) {
        Ok(value) => value,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(Connection::Missing),
        Err(e) => return Err(format!("Cannot inspect {}: {e}", destination.display())),
    };
    if !metadata.file_type().is_symlink() {
        return Ok(Connection::Conflict);
    }
    let target = fs::read_link(destination).map_err(|e| e.to_string())?;
    let target = if target.is_absolute() {
        target
    } else {
        destination.parent().unwrap().join(target)
    };
    // Canonical paths avoid false mismatches from casing on macOS or relative links.
    if target == source
        || matches!((target.canonicalize(), source.canonicalize()), (Ok(a), Ok(b)) if a == b)
    {
        return Ok(Connection::Connected);
    }
    Ok(if target.ends_with(suffix) {
        Connection::Stale
    } else {
        Connection::Conflict
    })
}

pub fn skill_destination(home: &Path) -> PathBuf {
    std::env::var_os("CODEX_HOME")
        .filter(|s| !s.is_empty())
        .map(PathBuf::from)
        .unwrap_or_else(|| home.join(".codex"))
        .join("skills/stud-design")
}

pub const CLI_SUFFIX: &str = "Contents/MacOS/stud";
pub const SKILL_SUFFIX: &str = "Contents/Resources/skills/stud-design";

pub fn check_repair(
    destination: &Path,
    source: &Path,
    suffix: &Path,
) -> Result<Connection, String> {
    let state = inspect(destination, source, suffix)?;
    if state == Connection::Conflict {
        return Err(format!("{} contains a custom installation or copied skill. Back it up and move it aside before connecting Stud; it has not been replaced.", destination.display()));
    }
    Ok(state)
}

pub fn link_skill(destination: &Path, source: &Path) -> Result<(), String> {
    use std::os::unix::fs::symlink;
    if !source.join("SKILL.md").is_file() {
        return Err("The bundled skill is missing. Reinstall Stud.".into());
    }
    if check_repair(destination, source, Path::new(SKILL_SUFFIX))? == Connection::Connected {
        return Ok(());
    }
    fs::create_dir_all(destination.parent().ok_or("Missing skills directory")?)
        .map_err(|e| e.to_string())?;
    let temporary = destination.with_file_name(format!(".stud-design-{}", std::process::id()));
    symlink(source, &temporary).map_err(|e| e.to_string())?;
    let result = (|| {
        check_repair(destination, source, Path::new(SKILL_SUFFIX))?;
        fs::rename(&temporary, destination).map_err(|e| e.to_string())
    })();
    let _ = fs::remove_file(temporary);
    result
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::symlink;
    struct Fixture(PathBuf);
    impl Fixture {
        fn new() -> Self {
            static NEXT: std::sync::atomic::AtomicUsize = std::sync::atomic::AtomicUsize::new(0);
            let path = std::env::temp_dir().join(format!(
                "stud-connections-{}-{}",
                std::process::id(),
                NEXT.fetch_add(1, std::sync::atomic::Ordering::Relaxed)
            ));
            fs::create_dir_all(&path).unwrap();
            Self(path)
        }
        fn source(&self) -> PathBuf {
            let p = self.0.join("Stud.app").join(SKILL_SUFFIX);
            fs::create_dir_all(&p).unwrap();
            fs::write(p.join("SKILL.md"), "new skill").unwrap();
            p
        }
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }
    #[test]
    fn missing_setup_and_bundle_update() {
        let f = Fixture::new();
        let src = f.source();
        let dst = f.0.join("skills/stud-design");
        assert_eq!(
            inspect(&dst, &src, Path::new(SKILL_SUFFIX)).unwrap(),
            Connection::Missing
        );
        link_skill(&dst, &src).unwrap();
        link_skill(&dst, &src).unwrap();
        fs::write(src.join("SKILL.md"), "updated skill").unwrap();
        assert_eq!(
            fs::read_to_string(dst.join("SKILL.md")).unwrap(),
            "updated skill"
        );
        assert_eq!(
            inspect(&dst, &src, Path::new(SKILL_SUFFIX)).unwrap(),
            Connection::Connected
        );
    }
    #[test]
    fn stale_and_dangling_stud_links_are_repaired() {
        let f = Fixture::new();
        let src = f.source();
        let dst = f.0.join("stud-design");
        symlink(f.0.join("old.app").join(SKILL_SUFFIX), &dst).unwrap();
        assert_eq!(
            inspect(&dst, &src, Path::new(SKILL_SUFFIX)).unwrap(),
            Connection::Stale
        );
        link_skill(&dst, &src).unwrap();
        assert_eq!(fs::read_link(dst).unwrap(), src);
    }
    #[test]
    fn custom_skill_directory_and_link_are_preserved() {
        let f = Fixture::new();
        let src = f.source();
        let dst = f.0.join("stud-design");
        fs::create_dir(&dst).unwrap();
        fs::write(dst.join("SKILL.md"), "custom").unwrap();
        assert!(link_skill(&dst, &src).is_err());
        assert_eq!(fs::read_to_string(dst.join("SKILL.md")).unwrap(), "custom");
        let link = f.0.join("custom-link");
        symlink(&dst, &link).unwrap();
        assert!(link_skill(&link, &src).is_err());
        assert_eq!(fs::read_link(link).unwrap(), dst);
    }
    #[test]
    fn cli_distinguishes_stale_build_from_custom_launcher() {
        let f = Fixture::new();
        let src = f.0.join("Stud.app").join(CLI_SUFFIX);
        let dst = f.0.join("stud");
        symlink(f.0.join("dev.app").join(CLI_SUFFIX), &dst).unwrap();
        assert_eq!(
            inspect(&dst, &src, Path::new(CLI_SUFFIX)).unwrap(),
            Connection::Stale
        );
        fs::remove_file(&dst).unwrap();
        fs::write(&dst, "custom launcher").unwrap();
        assert!(check_repair(&dst, &src, Path::new(CLI_SUFFIX)).is_err());
        assert_eq!(fs::read_to_string(dst).unwrap(), "custom launcher");
    }
    #[test]
    fn canonical_alias_to_current_cli_is_connected() {
        let f = Fixture::new();
        let source = f.0.join("Stud.app").join(CLI_SUFFIX);
        fs::create_dir_all(source.parent().unwrap()).unwrap();
        fs::write(&source, "launcher").unwrap();
        let alias = f.0.join("alias");
        symlink(&source, &alias).unwrap();
        let destination = f.0.join("stud");
        symlink("alias", &destination).unwrap();
        assert_eq!(
            check_repair(&destination, &source, Path::new(CLI_SUFFIX)).unwrap(),
            Connection::Connected
        );
    }

    #[test]
    fn missing_bundled_skill_does_not_replace_existing_link() {
        let f = Fixture::new();
        let dst = f.0.join("stud-design");
        let old = f.0.join("old.app").join(SKILL_SUFFIX);
        symlink(&old, &dst).unwrap();
        assert!(link_skill(&dst, &f.0.join("missing")).is_err());
        assert_eq!(fs::read_link(dst).unwrap(), old);
    }
}
