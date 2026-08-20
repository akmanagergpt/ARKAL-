#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    // No invoke handler is registered: the frontend has no native command,
    // shell, process, filesystem, credential, or browser-open capability.
    tauri::Builder::default()
        .run(tauri::generate_context!())
        .expect("ARKALI desktop runtime failed");
}
