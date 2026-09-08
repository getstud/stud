//! Exercise Tauri's real feed parsing and signature verification without
//! installing anything. The fixture key is test-only; its private key is absent.
use std::{
    io::{Read, Write},
    net::TcpListener,
    thread,
    time::Duration,
};
use tauri::test::{mock_builder, mock_context, noop_assets};
use tauri_plugin_updater::UpdaterExt;

fn mock_app(allow_http: bool) -> tauri::App<tauri::test::MockRuntime> {
    let mut context = mock_context(noop_assets());
    context.config_mut().plugins.0.insert(
        "updater".into(),
        serde_json::json!({
            "pubkey": include_str!("../../desktop/test-fixtures/update.pub").trim(),
            "endpoints": [], "dangerousInsecureTransportProtocol": allow_http
        }),
    );
    mock_builder()
        .plugin(tauri_plugin_updater::Builder::new().build())
        .build(context)
        .unwrap()
}

#[test]
#[cfg(not(debug_assertions))]
fn production_updater_rejects_plain_http() {
    let app = mock_app(false);
    assert!(app
        .updater_builder()
        .endpoints(vec!["http://127.0.0.1/latest.json".parse().unwrap()])
        .is_err());
}

fn download_fixture(tamper: bool) {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let endpoint = format!("http://{}", listener.local_addr().unwrap());
    let manifest = serde_json::to_vec(&serde_json::json!({
        "version": "99.0.0", "platforms": { "test-platform": {
            "url": format!("{endpoint}/update"),
            "signature": include_str!("../../desktop/test-fixtures/update.txt.sig").trim()
        }}
    }))
    .unwrap();
    let server = thread::spawn(move || {
        for index in 0..2 {
            let (mut socket, _) = listener.accept().unwrap();
            socket
                .set_read_timeout(Some(Duration::from_secs(10)))
                .unwrap();
            let mut request = [0_u8; 8192];
            socket.read(&mut request).unwrap();
            let payload = if index == 0 {
                manifest.clone()
            } else if tamper {
                b"tampered update".to_vec()
            } else {
                include_bytes!("../../desktop/test-fixtures/update.txt").to_vec()
            };
            write!(socket, "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n", payload.len()).unwrap();
            socket.write_all(&payload).unwrap();
        }
    });
    let app = mock_app(true); // HTTP is enabled only for this loopback test.
    tauri::async_runtime::block_on(async {
        let updater = app
            .updater_builder()
            .target("test-platform")
            .endpoints(vec![format!("{endpoint}/latest.json").parse().unwrap()])
            .unwrap()
            .timeout(Duration::from_secs(10))
            .build()
            .unwrap();
        let update = updater.check().await.unwrap().expect("new version");
        assert_eq!(update.version, "99.0.0");
        let downloaded = update.download(|_, _| {}, || {}).await;
        if tamper {
            assert!(
                downloaded.is_err(),
                "A changed payload must fail signature verification"
            );
        } else {
            assert_eq!(
                downloaded.unwrap(),
                include_bytes!("../../desktop/test-fixtures/update.txt")
            );
        }
    });
    server.join().unwrap();
}

#[test]
fn signed_update_download_is_verified() {
    download_fixture(false);
}
#[test]
fn tampered_update_download_is_rejected() {
    download_fixture(true);
}
