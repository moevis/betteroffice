use std::env;
use std::fs;
use std::path::{Path, PathBuf};

const FAMILIES: &[&str] = &["NotoSansJP"];

fn main() {
    let root = PathBuf::from(env::var_os("CARGO_MANIFEST_DIR").expect("CARGO_MANIFEST_DIR"));
    let packaged = root.join("assets");
    let assets = if packaged.join("manifest.json").is_file() {
        packaged
    } else {
        root.join("../../packages/fonts-cjk/assets")
            .canonicalize()
            .expect("font pack assets")
    };
    println!("cargo:rerun-if-changed={}", assets.display());
    println!("cargo:rerun-if-changed={}", root.display());
    let mut manifest: serde_json::Value = serde_json::from_slice(
        &fs::read(assets.join("manifest.json")).expect("font pack manifest"),
    )
    .expect("valid font pack manifest");
    manifest["faces"]
        .as_array_mut()
        .expect("font faces")
        .retain(|face| {
            face["family"]
                .as_str()
                .is_some_and(|family| FAMILIES.contains(&family))
        });
    let out = PathBuf::from(env::var_os("OUT_DIR").expect("OUT_DIR"));
    let filtered = out.join("manifest.json");
    fs::write(
        &filtered,
        serde_json::to_vec(&manifest).expect("serialize manifest"),
    )
    .expect("write manifest");
    println!("cargo:rustc-env=FONT_PACK_MANIFEST={}", filtered.display());
    fs::write(out.join("faces.rs"), faces(&manifest, &assets)).expect("write faces");
    println!("cargo:rustc-env=FONT_PACK_ASSETS={}", assets.display());
}

fn faces(manifest: &serde_json::Value, assets: &Path) -> String {
    let mut files: Vec<&str> = manifest["faces"]
        .as_array()
        .expect("font faces")
        .iter()
        .map(|face| face["file"].as_str().expect("face file"))
        .collect();
    files.sort_unstable();
    files.dedup();
    assert!(!files.is_empty(), "no font faces for {FAMILIES:?}");
    let mut source = format!("pub static FACES: [(&str, &[u8]); {}] = [\n", files.len());
    for file in files {
        assert!(
            !file.contains('/') && !file.contains('\\'),
            "font pack face {file} is not a plain file name"
        );
        assert!(
            assets.join(file).is_file(),
            "font pack face {file} is missing from {}",
            assets.display()
        );
        let path = format!("concat!(env!(\"FONT_PACK_ASSETS\"), \"/{file}\")");
        source.push_str(&format!("    ({file:?}, include_bytes!({path})),\n"));
    }
    source.push_str("];\n\npub fn face(file: &str) -> Option<&'static [u8]> {\n    FACES.iter().find(|face| face.0 == file).map(|face| face.1)\n}\n");
    source
}
