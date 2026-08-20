#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod backend_runtime;

use std::sync::{Arc, Mutex};

use backend_runtime::{repository_root, BackendRuntime};
use tauri::Manager;

fn main() {
    // No invoke handler is registered: lifecycle is owned by this fixed native
    // composition root and is unreachable from frontend input.
    let backend = Arc::new(Mutex::new(None::<BackendRuntime>));
    let setup_backend = Arc::clone(&backend);
    let app = tauri::Builder::default()
        .setup(move |app| {
            let app_data = app
                .path()
                .app_data_dir()
                .map_err(|error| format!("Cannot resolve ARKALI app data: {error}"))?;
            let runtime = BackendRuntime::start(&repository_root(), &app_data)?;
            *setup_backend
                .lock()
                .map_err(|_| "Backend state lock failed")? = Some(runtime);
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("ARKALI desktop runtime failed");

    app.run(move |_handle, event| {
        if matches!(event, tauri::RunEvent::Exit) {
            if let Ok(mut state) = backend.lock() {
                if let Some(mut runtime) = state.take() {
                    runtime.shutdown();
                }
            }
        }
    });
}
