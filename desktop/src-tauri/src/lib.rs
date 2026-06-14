use std::env;
use std::fs;
use std::net::TcpStream;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

use serde::Deserialize;
use tauri::webview::PageLoadEvent;
use tauri::{AppHandle, Manager, RunEvent};
// Dialog API is used only by the release-only update prompt below.
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
#[cfg_attr(debug_assertions, allow(dead_code))]
const LICENSE_FILE_NAME: &str = "license.token";
// Last update-check outcome, written beside the database so the local backend
// can serve it to the Settings UI (`GET /api/v1/maintenance/update-status`).
const UPDATE_CHECK_FILE_NAME: &str = "update-check.json";
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

// Used by the release-only updater (`#[cfg(not(debug_assertions))]`) and tests,
// so a plain debug build sees them as unused — allow that without hiding real
// dead code in release.
#[cfg_attr(debug_assertions, allow(dead_code))]
fn license_token_path(dir: &Path) -> PathBuf {
    dir.join(LICENSE_FILE_NAME)
}

/// Read the stored license token, returning `None` when the file is absent or
/// blank. The token is the gate the updater attaches as a bearer header.
///
/// Reading/writing the token from the UI moved to the local backend
/// (`/api/v1/maintenance/license`) because the desktop webview is served from a
/// remote origin where Tauri IPC `invoke` is unreliable. The backend writes this
/// same `license.token` file in the data dir, so the updater still reads it here.
#[cfg_attr(debug_assertions, allow(dead_code))]
fn read_license_token_from(dir: &Path) -> Option<String> {
    let contents = fs::read_to_string(license_token_path(dir)).ok()?;
    let trimmed = contents.trim();
    if trimmed.is_empty() {
        None
    } else {
        Some(trimmed.to_string())
    }
}

/// Format an epoch-seconds timestamp as ISO-8601 UTC (e.g. `2026-06-09T08:15:00Z`)
/// without pulling in chrono. Date math is Howard Hinnant's `civil_from_days`,
/// exact for the whole unix era.
fn iso8601_from_epoch(secs: u64) -> String {
    let days = (secs / 86_400) as i64;
    let rem = secs % 86_400;
    let (h, m, s) = (rem / 3600, (rem % 3600) / 60, rem % 60);
    let z = days + 719_468;
    let era = z / 146_097;
    let doe = z - era * 146_097;
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let day = doy - (153 * mp + 2) / 5 + 1;
    let month = if mp < 10 { mp + 3 } else { mp - 9 };
    let year = yoe + era * 400 + if month <= 2 { 1 } else { 0 };
    format!("{year:04}-{month:02}-{day:02}T{h:02}:{m:02}:{s:02}Z")
}

/// Scrub the license token out of a detail string before it is persisted.
/// Updater errors echo request context (URLs, headers), so never trust them
/// to be token-free.
fn sanitize_update_detail(detail: &str, token: Option<&str>) -> String {
    match token {
        Some(t) if !t.is_empty() => detail.replace(t, "[redacted]"),
        _ => detail.to_string(),
    }
}

fn update_check_status_json(result: &str, detail: &str, checked_at_epoch: u64) -> String {
    serde_json::json!({
        "checked_at": iso8601_from_epoch(checked_at_epoch),
        "result": result,
        "detail": detail,
    })
    .to_string()
}

fn write_update_check_status_to(dir: &Path, result: &str, detail: &str) {
    let epoch = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    let _ = fs::write(
        dir.join(UPDATE_CHECK_FILE_NAME),
        update_check_status_json(result, detail, epoch),
    );
}

/// Record the outcome of an update-check attempt where the backend can serve it
/// to Settings. `result` is one of `ok-uptodate` / `ok-update-available` /
/// `skipped-no-license` / `error`; `detail` is sanitized so the stored license
/// token can never land in the file.
#[cfg_attr(debug_assertions, allow(dead_code))]
fn record_update_check(result: &str, detail: &str) {
    let dir = user_data_dir();
    let detail = sanitize_update_detail(detail, read_license_token_from(&dir).as_deref());
    write_update_check_status_to(&dir, result, &detail);
}

/// Build the script injected into the local loader page when startup fails.
///
/// The loader is a static page (spinner + "Starting Centsmith…"), so every
/// failure path used to leave it spinning forever. This swaps it for a visible
/// error: what failed, where the shell log lives, and what to try. Strings are
/// JSON-encoded so reasons/paths (quotes, backslashes) can never break out of
/// the script. Kept as a pure helper so it is unit-testable.
fn startup_error_script(reason: &str, log_path: &str) -> String {
    let reason_json =
        serde_json::to_string(reason).unwrap_or_else(|_| "\"Startup failed.\"".to_string());
    let log_json =
        serde_json::to_string(log_path).unwrap_or_else(|_| "\"shell.log\"".to_string());
    format!(
        "(() => {{ \
            const apply = () => {{ \
                const spinner = document.querySelector('.spinner'); \
                if (spinner) spinner.style.display = 'none'; \
                const title = document.querySelector('.title'); \
                if (title) title.textContent = 'Centsmith could not start'; \
                const hint = document.querySelector('.hint'); \
                if (hint) {{ \
                    hint.style.opacity = '0.85'; \
                    hint.style.maxWidth = '36rem'; \
                    hint.style.textAlign = 'center'; \
                    hint.style.lineHeight = '1.6'; \
                    hint.style.padding = '0 24px'; \
                    hint.textContent = {reason} + ' Details were logged to ' + {log} + '. Try restarting the app; if this keeps happening, reinstall Centsmith.'; \
                }} \
            }}; \
            if (document.readyState === 'loading') {{ document.addEventListener('DOMContentLoaded', apply); }} else {{ apply(); }} \
        }})();",
        reason = reason_json,
        log = log_json,
    )
}

/// Surface a startup failure in the loader window instead of leaving the
/// spinner forever. Best-effort: failures here are only logged.
fn show_startup_error(app: &AppHandle, reason: &str) {
    let log_path = user_data_dir().join("shell.log").display().to_string();
    let script = startup_error_script(reason, &log_path);
    match app.get_webview_window("main") {
        None => debug_log("show_startup_error: get_webview_window returned None"),
        Some(window) => match window.eval(&script) {
            Ok(_) => debug_log("startup error surfaced in loader window"),
            Err(e) => debug_log(&format!("show_startup_error eval failed: {e}")),
        },
    }
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
                show_startup_error(
                    &app,
                    "The local Centsmith service was launched but never reported it was ready \
                     (it may have crashed or been blocked by antivirus).",
                );
                return;
            }
        };

        if let Err(e) = wait_for_port_open(metadata.port, STARTUP_TIMEOUT) {
            debug_log(&format!("wait_for_port error: {e}"));
            show_startup_error(
                &app,
                "The local Centsmith service started but never began accepting connections.",
            );
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
                        show_startup_error(
                            &app,
                            "The local Centsmith service is running but the app window could not open it.",
                        );
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
    // Updates are gated by the paid license: the token is attached as a bearer
    // header so the Worker can authorize the feed + installer download. With no
    // license stored we skip the check entirely — the app still runs fully.
    let Some(token) = read_license_token_from(&user_data_dir()) else {
        debug_log("no license token stored; skipping update check");
        record_update_check(
            "skipped-no-license",
            "No license stored; update checks are disabled.",
        );
        return Ok(());
    };

    debug_log("checking for updates");
    let update = app
        .updater_builder()
        .header("Authorization", format!("Bearer {token}"))?
        .build()?
        .check()
        .await?;
    let Some(update) = update else {
        debug_log("no update available");
        record_update_check("ok-uptodate", "");
        return Ok(());
    };

    debug_log(&format!(
        "update available: current={} latest={}",
        update.current_version, update.version
    ));
    record_update_check(
        "ok-update-available",
        &format!(
            "current={} latest={}",
            update.current_version, update.version
        ),
    );

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
            record_update_check("error", &e.to_string());
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
            let child = match spawn_backend(&app.handle()) {
                Ok(child) => child,
                Err(e) => {
                    // Keep the window alive and show the failure in it — erroring
                    // out of setup() would tear the app down to a blank nothing
                    // (exactly what an antivirus-quarantined backend used to do).
                    debug_log(&format!("spawn_backend error: {e}"));
                    let handle = app.handle().clone();
                    thread::spawn(move || {
                        // Give the loader page a beat to render before injecting.
                        thread::sleep(Duration::from_millis(750));
                        show_startup_error(
                            &handle,
                            "The local Centsmith service could not be launched \
                             (it may be missing or blocked by antivirus).",
                        );
                    });
                    return Ok(());
                }
            };

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
        // No frontend Tauri IPC commands remain — the webview is served from the
        // local backend (a remote origin where IPC invoke is unreliable), so all
        // shell actions (backup, open-data-folder, license) go through backend
        // HTTP routes instead. The `withGlobalTauri` + capability `remote.urls`
        // are kept only so `window.__TAURI__` exists for desktop detection.
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
    fn user_data_dir_is_under_centsmith() {
        // The resolved data dir always ends in the Centsmith app folder.
        assert!(user_data_dir().ends_with("Centsmith"));
    }

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
    fn read_license_token_reads_trimmed_value() {
        // The updater reads the token file the local backend writes. Token
        // management itself now lives in the backend (`/maintenance/license`).
        let dir = tempdir().unwrap();
        assert_eq!(read_license_token_from(dir.path()), None);
        fs::write(license_token_path(dir.path()), "  tok-ABCD1234  ").unwrap();
        assert_eq!(
            read_license_token_from(dir.path()),
            Some("tok-ABCD1234".to_string())
        );
    }

    #[test]
    fn read_license_token_treats_blank_as_absent() {
        let dir = tempdir().unwrap();
        fs::write(license_token_path(dir.path()), "   \n").unwrap();
        assert_eq!(read_license_token_from(dir.path()), None);
    }

    #[test]
    fn iso8601_from_epoch_formats_known_timestamps() {
        assert_eq!(iso8601_from_epoch(0), "1970-01-01T00:00:00Z");
        // Leap day.
        assert_eq!(iso8601_from_epoch(1_709_209_845), "2024-02-29T12:30:45Z");
        assert_eq!(iso8601_from_epoch(1_750_000_000), "2025-06-15T15:06:40Z");
        assert_eq!(iso8601_from_epoch(1_780_992_900), "2026-06-09T08:15:00Z");
    }

    #[test]
    fn sanitize_update_detail_redacts_token_occurrences() {
        let detail = "GET https://host/x?k=lic-SECRET failed; header Bearer lic-SECRET";
        assert_eq!(
            sanitize_update_detail(detail, Some("lic-SECRET")),
            "GET https://host/x?k=[redacted] failed; header Bearer [redacted]"
        );
        // No token stored (or blank) leaves the detail untouched.
        assert_eq!(sanitize_update_detail(detail, None), detail);
        assert_eq!(sanitize_update_detail(detail, Some("")), detail);
    }

    #[test]
    fn update_check_status_json_has_expected_shape() {
        let raw = update_check_status_json("ok-uptodate", "", 1_780_992_900);
        let parsed: serde_json::Value = serde_json::from_str(&raw).unwrap();
        assert_eq!(parsed["checked_at"], "2026-06-09T08:15:00Z");
        assert_eq!(parsed["result"], "ok-uptodate");
        assert_eq!(parsed["detail"], "");
    }

    #[test]
    fn write_update_check_status_creates_parseable_file() {
        let dir = tempdir().unwrap();
        write_update_check_status_to(dir.path(), "error", "connection refused");
        let raw = fs::read_to_string(dir.path().join(UPDATE_CHECK_FILE_NAME)).unwrap();
        let parsed: serde_json::Value = serde_json::from_str(&raw).unwrap();
        assert_eq!(parsed["result"], "error");
        assert_eq!(parsed["detail"], "connection refused");
        // checked_at is a real ISO-8601 UTC stamp.
        let stamp = parsed["checked_at"].as_str().unwrap();
        assert!(stamp.ends_with('Z') && stamp.len() == 20, "got {stamp}");
    }

    #[test]
    fn startup_error_script_embeds_reason_log_location_and_recovery_steps() {
        let script = startup_error_script(
            "The local Centsmith service could not be launched.",
            r"C:\Users\x\AppData\Roaming\Centsmith\shell.log",
        );
        assert!(script.contains("The local Centsmith service could not be launched."));
        assert!(script.contains("shell.log"));
        assert!(script.contains("Centsmith could not start"));
        assert!(script.contains("Try restarting the app"));
        assert!(script.contains("reinstall Centsmith"));
        // Defensive: applies after DOMContentLoaded if the page is still loading.
        assert!(script.contains("DOMContentLoaded"));
    }

    #[test]
    fn startup_error_script_escapes_embedded_strings() {
        let script = startup_error_script(
            "a \"quoted\" reason\nwith newline",
            r"C:\path\with\backslashes",
        );
        // JSON encoding keeps quotes/backslashes/newlines inside the literals,
        // so a hostile-looking reason can never break out of the script.
        assert!(script.contains(r#"\"quoted\""#));
        assert!(script.contains(r"C:\\path\\with\\backslashes"));
        assert!(!script.contains('\n'));
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
