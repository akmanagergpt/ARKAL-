use std::{
    fs,
    io::{Read, Write},
    net::{SocketAddr, TcpStream},
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    thread,
    time::{Duration, Instant},
};

const BACKEND_ADDR: &str = "127.0.0.1:8000";
const STARTUP_TIMEOUT: Duration = Duration::from_secs(30);
const PROBE_TIMEOUT: Duration = Duration::from_millis(500);

#[derive(Debug, PartialEq, Eq)]
enum Probe {
    ArkaliReady,
    Unavailable,
    ForeignService,
}

pub struct BackendRuntime {
    child: Option<Child>,
    shutdown_sentinel: Option<PathBuf>,
}

impl BackendRuntime {
    pub fn start(repo_root: &Path, app_data: &Path, resource_dir: &Path) -> Result<Self, String> {
        match probe_backend() {
            Probe::ArkaliReady => {
                return Ok(Self {
                    child: None,
                    shutdown_sentinel: None,
                })
            }
            Probe::ForeignService => {
                return Err(format!(
                    "Port {BACKEND_ADDR} is occupied by a service that is not ARKALI"
                ));
            }
            Probe::Unavailable => {}
        }

        let bundled = resource_dir.join("arkali-backend.exe");
        let python = canonical_python(repo_root);
        let launcher = repo_root.join("scripts").join("run_command_center.py");
        let use_bundled = bundled.is_file();
        if !use_bundled && (!python.is_file() || !launcher.is_file()) {
            return Err("The bundled ARKALI backend runtime is unavailable".to_owned());
        }

        fs::create_dir_all(app_data)
            .map_err(|error| format!("Cannot create ARKALI app-data directory: {error}"))?;
        let database = app_data.join("command_center.db");
        let shutdown_sentinel = app_data.join("desktop-backend.owner");
        let _ = fs::remove_file(&shutdown_sentinel);

        let mut command = Command::new(if use_bundled { bundled } else { python });
        command.current_dir(repo_root);
        if !use_bundled {
            command.arg(launcher);
        }
        command
            .args(["--host", "127.0.0.1", "--port", "8000", "--db"])
            .arg(database)
            .arg("--shutdown-sentinel")
            .arg(&shutdown_sentinel)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null());
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            command.creation_flags(0x0800_0000);
        }
        let mut child = command
            .spawn()
            .map_err(|error| format!("Cannot start the ARKALI backend: {error}"))?;

        let deadline = Instant::now() + STARTUP_TIMEOUT;
        while Instant::now() < deadline {
            if let Some(status) = child
                .try_wait()
                .map_err(|error| format!("Cannot inspect the ARKALI backend: {error}"))?
            {
                return Err(format!("ARKALI backend exited during startup ({status})"));
            }
            match probe_backend() {
                Probe::ArkaliReady => {
                    return Ok(Self {
                        child: Some(child),
                        shutdown_sentinel: Some(shutdown_sentinel),
                    })
                }
                Probe::ForeignService => {
                    let _ = child.kill();
                    let _ = child.wait();
                    return Err(format!(
                        "Port {BACKEND_ADDR} was taken by a service that is not ARKALI"
                    ));
                }
                Probe::Unavailable => thread::sleep(Duration::from_millis(100)),
            }
        }
        let _ = child.kill();
        let _ = child.wait();
        Err("ARKALI backend did not become ready within 30 seconds".to_owned())
    }

    pub fn shutdown(&mut self) {
        if let Some(mut child) = self.child.take() {
            if let Some(sentinel) = self.shutdown_sentinel.take() {
                let _ = fs::remove_file(sentinel);
            }
            let deadline = Instant::now() + Duration::from_secs(5);
            while Instant::now() < deadline {
                match child.try_wait() {
                    Ok(Some(_)) => return,
                    Ok(None) => thread::sleep(Duration::from_millis(50)),
                    Err(_) => break,
                }
            }
            // Last-resort containment for a backend that ignored graceful exit.
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

impl Drop for BackendRuntime {
    fn drop(&mut self) {
        self.shutdown();
    }
}

fn canonical_python(repo_root: &Path) -> PathBuf {
    repo_root.join(".venv").join("Scripts").join("python.exe")
}

fn probe_backend() -> Probe {
    let address: SocketAddr = BACKEND_ADDR
        .parse()
        .expect("fixed loopback address is valid");
    let Ok(mut stream) = TcpStream::connect_timeout(&address, PROBE_TIMEOUT) else {
        return Probe::Unavailable;
    };
    let _ = stream.set_read_timeout(Some(PROBE_TIMEOUT));
    let _ = stream.set_write_timeout(Some(PROBE_TIMEOUT));
    if stream
        .write_all(b"GET /api/health HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
        .is_err()
    {
        return Probe::ForeignService;
    }
    let mut response = String::new();
    if stream.read_to_string(&mut response).is_err() {
        return Probe::ForeignService;
    }
    classify_health_response(&response)
}

fn classify_health_response(response: &str) -> Probe {
    let valid_status = response.starts_with("HTTP/1.1 200") || response.starts_with("HTTP/1.0 200");
    let valid_body =
        response.contains("\"status\":\"ready\"") && response.contains("\"schema_revision\":");
    if valid_status && valid_body {
        Probe::ArkaliReady
    } else {
        Probe::ForeignService
    }
}

pub fn repository_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .expect("src-tauri has a repository parent")
        .to_path_buf()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn canonical_runtime_path_is_fixed_below_the_repository() {
        assert_eq!(
            canonical_python(Path::new(r"C:\repo")),
            PathBuf::from(r"C:\repo\.venv\Scripts\python.exe")
        );
    }

    #[test]
    fn only_the_real_health_shape_is_accepted() {
        assert_eq!(
            classify_health_response(
                "HTTP/1.1 200 OK\r\n\r\n{\"status\":\"ready\",\"schema_revision\":\"0011\"}"
            ),
            Probe::ArkaliReady
        );
        for response in [
            "HTTP/1.1 200 OK\r\n\r\n{\"status\":\"ok\"}",
            "HTTP/1.1 500 Error\r\n\r\n{\"status\":\"ready\",\"schema_revision\":null}",
            "HTTP/1.1 200 OK\r\n\r\n{}",
        ] {
            assert_eq!(classify_health_response(response), Probe::ForeignService);
        }
    }

    #[test]
    fn real_backend_starts_over_app_data_and_stops_cleanly() {
        assert_eq!(probe_backend(), Probe::Unavailable);
        let unique = format!("arkali-desktop-test-{}", std::process::id());
        let app_data = std::env::temp_dir().join(unique);
        let _ = fs::remove_dir_all(&app_data);

        let mut runtime =
            BackendRuntime::start(&repository_root(), &app_data, Path::new("missing"))
                .expect("real Command Center backend starts");
        assert_eq!(probe_backend(), Probe::ArkaliReady);
        assert!(app_data.join("command_center.db").is_file());
        runtime.shutdown();

        let deadline = Instant::now() + Duration::from_secs(3);
        while Instant::now() < deadline && probe_backend() != Probe::Unavailable {
            thread::sleep(Duration::from_millis(50));
        }
        assert_eq!(probe_backend(), Probe::Unavailable);
        fs::remove_dir_all(app_data).expect("desktop integration temp data is removable");
    }
}
