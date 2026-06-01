use std::env;
use std::fs;
use std::net::TcpStream;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

use serde::Deserialize;
use tauri::webview::PageLoadEvent;
use tauri::{AppHandle, Manager, RunEvent};
#[cfg(not(debug_assertions))]
use tauri_plugin_dialog::{DialogExt, MessageDialogButtons, MessageDialogKind};
#[cfg(not(debug_assertions))]
use tauri_plugin_updater::UpdaterExt;

struct BackendProcess(Mutex<Option<Child>>);
struct DesktopToken(Mutex<Option<String>>);
// Store the raw HANDLE as usize so it is Send + Sync without a wrapper type.
#[cfg(windows)]
struct BackendJob(Mutex<Option<usize>>);

const BACKEND_DIR_NAME: &str = "backend";
const BACKEND_EXE_NAME: &str = "centsmith-backend.exe";
const RUNTIME_FILE_NAME: &str = "runtime.json";
const BOOTSTRAP_PATH: &str = "/desktop-bootstrap";
const STARTUP_TIMEOUT: Duration = Duration::from_secs(30);

#[derive(Deserialize, Debug, PartialEq, Eq)]
struct RuntimeMetadata {
    port: u16,
    token: String,
}

fn pick_first_existing(candidates: &[PathBuf]) -> Option<PathBuf> {
    candidates.iter().find(|p| p.is_file()).cloned()
}

fn parse_runtime_metadata(raw: &str) -> Result<RuntimeMetadata, String> {
    serde_json::from_str(raw).map_err(|e| format!("runtime metadata parse error: {e}"))
}

fn is_bootstrap_path(path: &str) -> bool {
    path == BOOTSTRAP_PATH
}

fn user_data_dir() -> PathBuf {
    let base = env::var_os("APPDATA")
        .map(PathBuf::from)
        .unwrap_or_else(|| dirs_home().join("AppData").join("Roaming"));
    let dir = base.join("Centsmith");
    let _ = fs::create_dir_all(&dir);
    dir
}

fn dirs_home() -> PathBuf {
    env::var_os("USERPROFILE")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("."))
}

fn debug_log(msg: &str) {
    let path = user_data_dir().join("shell.log");
    let line = format!("[{}] {}\n", chrono_now(), msg);
    let _ = fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&path)
        .and_then(|mut f| {
            use std::io::Write;
            f.write_all(line.as_bytes())
        });
}

fn chrono_now() -> String {
    // Simple timestamp without pulling in chrono; good enough for debugging.
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| format!("{}s", d.as_secs()))
        .unwrap_or_else(|_| "?".into())
}

fn backend_exe_candidates(resource_dir: &PathBuf) -> [PathBuf; 3] {
    [
        // NSIS places resources at their source path relative to the tauri project dir,
        // so "resources/backend/**" lands at <install_dir>/resources/backend/.
        resource_dir
            .join("resources")
            .join(BACKEND_DIR_NAME)
            .join(BACKEND_EXE_NAME),
        // Fallback: resource_dir already points into the resources subdir (dev mode).
        resource_dir.join(BACKEND_DIR_NAME).join(BACKEND_EXE_NAME),
        // Dev fallback: repo-relative built backend.
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../packaging/dist/centsmith-backend")
            .join(BACKEND_EXE_NAME),
    ]
}

fn resolve_backend_exe(app: &AppHandle) -> Result<PathBuf, String> {
    let resource_dir = app
        .path()
        .resource_dir()
        .map_err(|e| format!("resource_dir: {e}"))?;
    debug_log(&format!("resource_dir = {}", resource_dir.display()));

    let candidates = backend_exe_candidates(&resource_dir);
    for candidate in &candidates {
        debug_log(&format!(
            "candidate = {} exists={}",
            candidate.display(),
            candidate.is_file()
        ));
    }

    pick_first_existing(&candidates).ok_or_else(|| {
        let summary = candidates
            .iter()
            .map(|p| p.display().to_string())
            .collect::<Vec<_>>()
            .join(", ");
        format!("Could not locate {BACKEND_EXE_NAME}. Looked in: {summary}")
    })
}

fn spawn_backend(app: &AppHandle) -> Result<Child, String> {
    let exe = resolve_backend_exe(app)?;
    // Remove stale runtime metadata before spawning so we wait for fresh data
    // from the current backend instance.
    let runtime_file = user_data_dir().join(RUNTIME_FILE_NAME);
    let _ = fs::remove_file(&runtime_file);
    debug_log(&format!("spawning backend: {}", exe.display()));
    Command::new(&exe)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|e| format!("failed to spawn backend: {e}"))
}

#[cfg(windows)]
fn assign_to_job(child: &Child) -> Option<usize> {
    use std::mem::{size_of, zeroed};
    use std::os::windows::io::AsRawHandle;
    use windows_sys::Win32::Foundation::CloseHandle;
    use windows_sys::Win32::System::JobObjects::{
        AssignProcessToJobObject, CreateJobObjectW, JobObjectExtendedLimitInformation,
        SetInformationJobObject, JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
    };

    unsafe {
        let job = CreateJobObjectW(std::ptr::null(), std::ptr::null());
        if job.is_null() {
            debug_log("CreateJobObjectW failed");
            return None;
        }

        let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = zeroed();
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;

        if SetInformationJobObject(
            job,
            JobObjectExtendedLimitInformation,
            &info as *const _ as *const _,
            size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
        ) == 0
        {
            debug_log("SetInformationJobObject failed");
            CloseHandle(job);
            return None;
        }

        if AssignProcessToJobObject(job, child.as_raw_handle()) == 0 {
            debug_log("AssignProcessToJobObject failed");
            CloseHandle(job);
            return None;
        }

        debug_log("backend assigned to job object (KILL_ON_JOB_CLOSE)");
        Some(job as usize)
    }
}

fn read_runtime_metadata(timeout: Duration) -> Result<RuntimeMetadata, String> {
    let runtime_file = user_data_dir().join(RUNTIME_FILE_NAME);
    let deadline = Instant::now() + timeout;
    loop {
        if let Ok(contents) = fs::read_to_string(&runtime_file) {
            match parse_runtime_metadata(&contents) {
                Ok(metadata) => {
                    let _ = fs::remove_file(&runtime_file);
                    return Ok(metadata);
                }
                Err(e) => debug_log(&e),
            }
        }
        if Instant::now() >= deadline {
            return Err(format!("timed out waiting for {}", runtime_file.display()));
        }
        thread::sleep(Duration::from_millis(100));
    }
}

fn wait_for_port_open(port: u16, timeout: Duration) -> Result<(), String> {
    let addr = format!("127.0.0.1:{port}");
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        if TcpStream::connect_timeout(&addr.parse().unwrap(), Duration::from_millis(250)).is_ok() {
            return Ok(());
        }
        thread::sleep(Duration::from_millis(100));
    }
    Err(format!("backend did not start listening on port {port}"))
}

fn navigate_to_backend(app: AppHandle) {
    thread::spawn(move || {
        debug_log("navigate thread started");

        let metadata = match read_runtime_metadata(STARTUP_TIMEOUT) {
            Ok(value) => {
                debug_log(&format!("read runtime metadata for port {}", value.port));
                value
            }
            Err(e) => {
                debug_log(&format!("read_runtime_metadata error: {e}"));
                return;
            }
        };

        if let Err(e) = wait_for_port_open(metadata.port, STARTUP_TIMEOUT) {
            debug_log(&format!("wait_for_port error: {e}"));
            return;
        }
        debug_log(&format!("port {} is open", metadata.port));

        // Stash the token before navigation so the on_page_load handler can
        // inject it into the bootstrap page via eval(), keeping it out of the
        // URL (and out of any URL-based logs / nav history).
        app.state::<DesktopToken>()
            .0
            .lock()
            .unwrap()
            .replace(metadata.token);

        let url = format!("http://127.0.0.1:{}{}", metadata.port, BOOTSTRAP_PATH);

        match app.get_webview_window("main") {
            None => debug_log("get_webview_window returned None"),
            Some(window) => {
                debug_log(&format!(
                    "got window, navigating to backend on port {}",
                    metadata.port
                ));
                let parsed = url.parse().expect("valid url");
                match window.navigate(parsed) {
                    Ok(_) => debug_log("navigate() succeeded"),
                    Err(e) => {
                        debug_log(&format!("navigate() failed: {e}"));
                    }
                }
            }
        }

        // Only check for updates once the backend is reachable, so the
        // prompt never appears before the user has seen the app.
        spawn_update_check(app);
    });
}

fn stop_backend(app: &AppHandle) {
    #[cfg(windows)]
    if let Some(state) = app.try_state::<BackendJob>() {
        if let Some(raw) = state.0.lock().unwrap().take() {
            use windows_sys::Win32::Foundation::CloseHandle;
            debug_log("closing job handle (kills backend)");
            unsafe { CloseHandle(raw as *mut core::ffi::c_void); }
        }
    }

    if let Some(state) = app.try_state::<BackendProcess>() {
        if let Some(mut child) = state.0.lock().unwrap().take() {
            debug_log("stopping backend process");
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

#[cfg(not(debug_assertions))]
async fn check_for_update(app: AppHandle) -> tauri_plugin_updater::Result<()> {
    debug_log("checking for updates");
    let Some(update) = app.updater()?.check().await? else {
        debug_log("no update available");
        return Ok(());
    };

    debug_log(&format!(
        "update available: current={} latest={}",
        update.current_version, update.version
    ));

    // blocking_show() is intentional: we're already on a tokio worker thread
    // (not the main thread, which would deadlock), and treating the dialog as
    // a synchronous gate keeps the control flow straight. The async show()
    // variant adds a callback indirection without any real benefit here.
    let should_install = app
        .dialog()
        .message(format!(
            "Centsmith {} is available. Install it now?",
            update.version
        ))
        .title("Update available")
        .kind(MessageDialogKind::Info)
        .buttons(MessageDialogButtons::OkCancelCustom(
            "Install".to_string(),
            "Later".to_string(),
        ))
        .blocking_show();

    if !should_install {
        debug_log("user deferred update");
        return Ok(());
    }

    const PROGRESS_LOG_INTERVAL: usize = 1024 * 1024; // 1 MiB
    let mut downloaded = 0usize;
    let mut next_log_at = PROGRESS_LOG_INTERVAL;
    let app_for_install = app.clone();
    update
        .download_and_install(
            |chunk_length, content_length| {
                downloaded += chunk_length;
                if downloaded >= next_log_at {
                    debug_log(&format!(
                        "downloaded update bytes: {} of {:?}",
                        downloaded, content_length
                    ));
                    next_log_at = downloaded + PROGRESS_LOG_INTERVAL;
                }
            },
            move || {
                // Stop the backend before NSIS runs so it releases its lock on
                // DLLs inside resources/backend/_internal/ (e.g. VCRUNTIME140.dll).
                debug_log("update download finished, stopping backend before install");
                stop_backend(&app_for_install);
            },
        )
        .await?;

    debug_log("update installed, restarting app");
    app.restart();
}

#[cfg(not(debug_assertions))]
fn spawn_update_check(app: AppHandle) {
    tauri::async_runtime::spawn(async move {
        if let Err(e) = check_for_update(app).await {
            debug_log(&format!("update check failed: {e}"));
        }
    });
}

#[cfg(debug_assertions)]
fn spawn_update_check(_app: AppHandle) {}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    debug_log("run() called");
    let builder = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.set_focus();
            }
        }))
        .manage(BackendProcess(Mutex::new(None)))
        .manage(DesktopToken(Mutex::new(None)));

    #[cfg(windows)]
    let builder = builder.manage(BackendJob(Mutex::new(None)));

    builder
        .on_page_load(|webview, payload| {
            if payload.event() != PageLoadEvent::Finished {
                return;
            }
            if !is_bootstrap_path(payload.url().path()) {
                return;
            }
            let token = webview
                .app_handle()
                .state::<DesktopToken>()
                .0
                .lock()
                .unwrap()
                .take();
            let Some(token) = token else {
                debug_log("on_page_load: bootstrap loaded but no token available");
                return;
            };
            let token_json =
                serde_json::to_string(&token).unwrap_or_else(|_| "\"\"".to_string());
            let script = format!(
                "(async () => {{ \
                    const resp = await fetch('/desktop-login', {{ \
                        method: 'POST', \
                        headers: {{'Content-Type': 'application/x-www-form-urlencoded'}}, \
                        body: new URLSearchParams({{token: {token}}}).toString() \
                    }}); \
                    if (resp.ok) {{ window.location.replace('/'); }} \
                    else {{ const s = document.getElementById('status'); \
                        if (s) s.textContent = 'Desktop login failed: ' + resp.status; }} \
                }})();",
                token = token_json,
            );
            if let Err(e) = webview.eval(&script) {
                debug_log(&format!("eval failed: {e}"));
            } else {
                debug_log("bootstrap login script evaluated");
            }
        })
        .setup(|app| {
            debug_log("setup() called");
            let child = spawn_backend(&app.handle()).map_err(|e| {
                debug_log(&format!("spawn_backend error: {e}"));
                std::io::Error::new(std::io::ErrorKind::Other, e)
            })?;

            #[cfg(windows)]
            if let Some(raw) = assign_to_job(&child) {
                *app.state::<BackendJob>().0.lock().unwrap() = Some(raw);
            }

            app.state::<BackendProcess>()
                .0
                .lock()
                .unwrap()
                .replace(child);

            navigate_to_backend(app.handle().clone());
            debug_log("setup() done, navigate thread launched");
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app, event| {
            if let RunEvent::ExitRequested { .. } = event {
                stop_backend(app);
            }
        });
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs::File;
    use tempfile::tempdir;

    #[test]
    fn pick_first_existing_returns_first_match() {
        let dir = tempdir().unwrap();
        let missing = dir.path().join("nope.exe");
        let exists = dir.path().join("real.exe");
        File::create(&exists).unwrap();
        let result = pick_first_existing(&[missing.clone(), exists.clone()]);
        assert_eq!(result, Some(exists));
    }

    #[test]
    fn pick_first_existing_prefers_earlier_candidate() {
        let dir = tempdir().unwrap();
        let first = dir.path().join("first.exe");
        let second = dir.path().join("second.exe");
        File::create(&first).unwrap();
        File::create(&second).unwrap();
        let result = pick_first_existing(&[first.clone(), second]);
        assert_eq!(result, Some(first));
    }

    #[test]
    fn pick_first_existing_returns_none_when_all_missing() {
        let dir = tempdir().unwrap();
        let a = dir.path().join("a.exe");
        let b = dir.path().join("b.exe");
        assert!(pick_first_existing(&[a, b]).is_none());
    }

    #[test]
    fn parse_runtime_metadata_accepts_valid_json() {
        let parsed = parse_runtime_metadata(r#"{"port": 8012, "token": "abc"}"#).unwrap();
        assert_eq!(
            parsed,
            RuntimeMetadata {
                port: 8012,
                token: "abc".to_string()
            }
        );
    }

    #[test]
    fn parse_runtime_metadata_rejects_malformed_json() {
        let err = parse_runtime_metadata("not json").unwrap_err();
        assert!(err.contains("parse error"));
    }

    #[test]
    fn parse_runtime_metadata_rejects_missing_fields() {
        let err = parse_runtime_metadata(r#"{"port": 8012}"#).unwrap_err();
        assert!(err.contains("parse error"));
    }

    #[test]
    fn parse_runtime_metadata_rejects_wrong_port_type() {
        let err = parse_runtime_metadata(r#"{"port": "8012", "token": "abc"}"#).unwrap_err();
        assert!(err.contains("parse error"));
    }

    #[test]
    fn is_bootstrap_path_matches_only_exact_bootstrap() {
        assert!(is_bootstrap_path("/desktop-bootstrap"));
        assert!(!is_bootstrap_path("/desktop-bootstrap/"));
        assert!(!is_bootstrap_path("/desktop-bootstrap?token=x"));
        assert!(!is_bootstrap_path("/desktop-bootstrap/extra"));
        assert!(!is_bootstrap_path("/"));
        assert!(!is_bootstrap_path("/Desktop-Bootstrap"));
    }

    #[test]
    fn backend_exe_candidates_includes_nsis_dev_subdir_and_repo_fallback() {
        let resource_dir = PathBuf::from("C:\\Program Files\\Centsmith");
        let candidates = backend_exe_candidates(&resource_dir);
        assert!(candidates[0]
            .to_string_lossy()
            .contains("resources"));
        assert!(candidates[1].to_string_lossy().contains(BACKEND_DIR_NAME));
        assert!(candidates[2]
            .to_string_lossy()
            .contains("packaging/dist/centsmith-backend") ||
            candidates[2]
                .to_string_lossy()
                .contains("packaging\\dist\\centsmith-backend"));
        for c in &candidates {
            assert!(c.to_string_lossy().ends_with(BACKEND_EXE_NAME));
        }
    }
}
