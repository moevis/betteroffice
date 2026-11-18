pub const MANIFEST: &str = include_str!(concat!(env!("FONT_PACK_ASSETS"), "/manifest.json"));

mod embedded {
    include!(concat!(env!("OUT_DIR"), "/faces.rs"));
}

pub fn face(file: &str) -> Option<&'static [u8]> {
    betteroffice_fonts_cjk_sc::face(file)
        .or_else(|| betteroffice_fonts_cjk_tc::face(file))
        .or_else(|| betteroffice_fonts_cjk_jp::face(file))
        .or_else(|| betteroffice_fonts_cjk_kr::face(file))
        .or_else(|| betteroffice_fonts_cjk_serif_sc::face(file))
        .or_else(|| embedded::face(file))
}

#[cfg(test)]
mod tests {
    use super::{MANIFEST, face};

    type Face = fn(&str) -> Option<&'static [u8]>;

    const CHILDREN: [(&str, Face); 5] = [
        ("cjk-sc", betteroffice_fonts_cjk_sc::face),
        ("cjk-tc", betteroffice_fonts_cjk_tc::face),
        ("cjk-jp", betteroffice_fonts_cjk_jp::face),
        ("cjk-kr", betteroffice_fonts_cjk_kr::face),
        ("cjk-serif-sc", betteroffice_fonts_cjk_serif_sc::face),
    ];

    #[test]
    fn manifest_faces_have_the_encoded_length() {
        let manifest: serde_json::Value = serde_json::from_str(MANIFEST).unwrap();
        assert!(!manifest["faces"].as_array().unwrap().is_empty());
        for entry in manifest["faces"].as_array().unwrap() {
            let file = entry["file"].as_str().unwrap();
            let providers: Vec<&str> = CHILDREN
                .iter()
                .filter(|(_, embedded)| embedded(file).is_some())
                .map(|(name, _)| *name)
                .collect();
            assert!(providers.len() <= 1, "{file} is embedded by {providers:?}");
            assert_eq!(
                providers.is_empty(),
                super::embedded::face(file).is_some(),
                "{file} must be embedded either here or by exactly one child crate"
            );
            assert_eq!(
                face(file).unwrap().len() as u64,
                entry["encodedLength"].as_u64().unwrap()
            );
        }
        assert!(face("unknown.ttf.zst").is_none());
    }
}
