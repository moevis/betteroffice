pub const MANIFEST: &str = include_str!(env!("FONT_PACK_MANIFEST"));

mod embedded {
    include!(concat!(env!("OUT_DIR"), "/faces.rs"));
}

pub fn face(file: &str) -> Option<&'static [u8]> {
    embedded::face(file)
}

#[cfg(test)]
mod tests {
    use super::{MANIFEST, face};

    #[test]
    fn manifest_faces_have_the_encoded_length() {
        let manifest: serde_json::Value = serde_json::from_str(MANIFEST).unwrap();
        assert!(!manifest["faces"].as_array().unwrap().is_empty());
        for entry in manifest["faces"].as_array().unwrap() {
            let file = entry["file"].as_str().unwrap();
            assert_eq!(
                face(file).unwrap().len() as u64,
                entry["encodedLength"].as_u64().unwrap()
            );
        }
        assert!(face("unknown.ttf.zst").is_none());
    }
}
