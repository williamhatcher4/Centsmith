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

struct BackendProcess(Mutex<Option<Child>>);
struct DesktopToken(Mutex<Option<String>>);

const BACKEND_DIR_NAME: &str = "backend";
const BACKEND_EXE_NAME: &str = "credit-tracker-backend.exe";
const RUNTIME_FILE_NAME: &str = "runtime.json";
const BOOTSTRAP_PATH: &str = "/desktop-bootstrap";
const STARTUP_TIMEOUT: Duration = Duration::from_secs(30);

#[derive(Deserialize)]
struct RuntimeMetadata {
    port: u16,
    token: String,
}

fn user_data_dir() -> PathBuf {
    let base = env::var_os("APPDATA")
        .map(PathBuf::from)
        .unwrap_or_else(|| dirs_home().join("AppData").join("Roaming"));
    let dir = base.join("CreditTracker");
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

fn resolve_backend_exe(app: &AppHandle) -> Result<PathBuf, String> {
    let resource_dir = app
        .path()
        .resource_dir()
        .map_err(|e| format!("resource_dir: {e}"))?;
    debug_log(&format!("resource_dir = {}", resource_dir.display()));

    // NSIS places resources at their source path relative to the tauri project dir,
    // so "resources/backend/**" lands at <install_dir>/resources/backend/.
    let nsis = resource_dir
        .join("resources")
        .join(BACKEND_DIR_NAME)
        .join(BACKEND_EXE_NAME);
    debug_log(&format!(
        "nsis candidate = {} exists={}",
        nsis.display(),
        nsis.is_file()
    ));
    if nsis.is_file() {
        return Ok(nsis);
    }

    // Fallback: resource_dir already points into the resources subdir (dev mode).
    let candidate = resource_dir.join(BACKEND_DIR_NAME).join(BACKEND_EXE_NAME);
    debug_log(&format!(
        "candidate = {} exists={}",
        candidate.display(),
        candidate.is_file()
    ));
    if candidate.is_file() {
        return Ok(candidate);
    }

    // Dev fallback: repo-relative built backend.
    let dev = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../packaging/dist/credit-tracker-backend")
        .join(BACKEND_EXE_NAME);
    debug_log(&format!(
        "dev fallback = {} exists={}",
        dev.display(),
        dev.is_file()
    ));
    if dev.is_file() {
        return Ok(dev);
    }

    Err(format!(
        "Could not locate {BACKEND_EXE_NAME}. Looked in: {}, {}, and {}",
        nsis.display(),
        candidate.display(),
        dev.display()
    ))
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

fn read_runtime_metadata(timeout: Duration) -> Result<RuntimeMetadata, String> {
    let runtime_file = user_data_dir().join(RUNTIME_FILE_NAME);
    let deadline = Instant::now() + timeout;
    loop {
        if let Ok(contents) = fs::read_to_string(&runtime_file) {
            match serde_json::from_str::<RuntimeMetadata>(&contents) {
                Ok(metadata) => {
                    let _ = fs::remove_file(&runtime_file);
                    return Ok(metadata);
                }
                Err(e) => debug_log(&format!("runtime metadata parse error: {e}")),
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
    });
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    debug_log("run() called");
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.set_focus();
            }
        }))
        .manage(BackendProcess(Mutex::new(None)))
        .manage(DesktopToken(Mutex::new(None)))
        .on_page_load(|webview, payload| {
            if payload.event() != PageLoadEvent::Finished {
                return;
            }
            if payload.url().path() != BOOTSTRAP_PATH {
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
                if let Some(state) = app.try_state::<BackendProcess>() {
                    if let Some(mut child) = state.0.lock().unwrap().take() {
                        let _ = child.kill();
                        let _ = child.wait();
                    }
                }
            }
        });
}
