use std::env;
use std::fs;
use std::net::TcpStream;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

use tauri::{AppHandle, Manager, RunEvent};

struct BackendProcess(Mutex<Option<Child>>);

const BACKEND_DIR_NAME: &str = "backend";
const BACKEND_EXE_NAME: &str = "credit-tracker-backend.exe";
const PORT_FILE_NAME: &str = "port.txt";
const STARTUP_TIMEOUT: Duration = Duration::from_secs(30);

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
        .and_then(|mut f| { use std::io::Write; f.write_all(line.as_bytes()) });
}

fn chrono_now() -> String {
    // Simple timestamp without pulling in chrono — good enough for debugging.
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
    let candidate = resource_dir.join(BACKEND_DIR_NAME).join(BACKEND_EXE_NAME);
    debug_log(&format!("candidate = {} exists={}", candidate.display(), candidate.is_file()));
    if candidate.is_file() {
        return Ok(candidate);
    }
    // Dev fallback: repo-relative built backend.
    let dev = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../packaging/dist/credit-tracker-backend")
        .join(BACKEND_EXE_NAME);
    debug_log(&format!("dev fallback = {} exists={}", dev.display(), dev.is_file()));
    if dev.is_file() {
        return Ok(dev);
    }
    Err(format!(
        "Could not locate {BACKEND_EXE_NAME}. Looked in: {} and {}",
        candidate.display(),
        dev.display()
    ))
}

fn spawn_backend(app: &AppHandle) -> Result<Child, String> {
    let exe = resolve_backend_exe(app)?;
    // Remove stale port.txt before spawning so read_port always waits for a
    // freshly written file from the current backend instance.
    let port_file = user_data_dir().join(PORT_FILE_NAME);
    let _ = fs::remove_file(&port_file);
    debug_log(&format!("spawning backend: {}", exe.display()));
    Command::new(&exe)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|e| format!("failed to spawn backend: {e}"))
}

fn read_port(timeout: Duration) -> Result<u16, String> {
    let port_file = user_data_dir().join(PORT_FILE_NAME);
    let deadline = Instant::now() + timeout;
    loop {
        if let Ok(contents) = fs::read_to_string(&port_file) {
            if let Ok(port) = contents.trim().parse::<u16>() {
                return Ok(port);
            }
        }
        if Instant::now() >= deadline {
            return Err(format!("timed out waiting for {}", port_file.display()));
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

        let port = match read_port(STARTUP_TIMEOUT) {
            Ok(p) => { debug_log(&format!("read port: {p}")); p }
            Err(e) => { debug_log(&format!("read_port error: {e}")); return; }
        };

        if let Err(e) = wait_for_port_open(port, STARTUP_TIMEOUT) {
            debug_log(&format!("wait_for_port error: {e}"));
            return;
        }
        debug_log(&format!("port {port} is open"));

        let url = format!("http://127.0.0.1:{port}/");

        match app.get_webview_window("main") {
            None => debug_log("get_webview_window returned None"),
            Some(window) => {
                debug_log(&format!("got window, calling eval to navigate to {url}"));
                // Use JS eval rather than window.navigate() to avoid WebView2
                // blocking cross-scheme navigation from tauri:// to http://.
                let js = format!("window.location.replace({url:?})");
                match window.eval(&js) {
                    Ok(_) => debug_log("eval succeeded"),
                    Err(e) => {
                        debug_log(&format!("eval failed: {e}, trying navigate()"));
                        let parsed = url.parse().expect("valid url");
                        match window.navigate(parsed) {
                            Ok(_) => debug_log("navigate() succeeded"),
                            Err(e2) => debug_log(&format!("navigate() also failed: {e2}")),
                        }
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
