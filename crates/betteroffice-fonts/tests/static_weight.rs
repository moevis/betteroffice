#![cfg(feature = "manager")]

use betteroffice_fonts::catalog::{BundledFontFace, catalog};
use betteroffice_fonts::{
    resolve_bundled_family_face, resolve_family_script_fallback_face, resolve_light_variant_face,
    resolve_metric_compat_face, resolve_metric_compat_family, resolve_script_fallback_face,
};

fn file(face: Option<&BundledFontFace>) -> Option<&str> {
    face.map(|face| face.file.as_str())
}

fn weight(face: Option<&BundledFontFace>) -> Option<u16> {
    face.map(|face| face.weight)
}

#[test]
fn a_named_weight_wins_over_the_bold_flag() {
    for name in [
        "Carlito Bold",
        "carlito-bold",
        "  CARLITO   Bold ",
        "Calibri Bold",
    ] {
        for bold in [false, true] {
            for italic in [false, true] {
                let face = resolve_bundled_family_face(name, bold, italic).unwrap();
                assert_eq!(face.family, "Carlito", "{name}");
                assert_eq!(face.weight, 700, "{name}");
                assert_eq!(face.style, "normal", "{name}");
            }
        }
    }
    assert_eq!(
        weight(resolve_metric_compat_face("Calibri Bold", false, false)),
        Some(700)
    );
    assert_eq!(
        weight(resolve_metric_compat_face("Calibri Regular", false, false)),
        Some(400)
    );
}

#[test]
fn only_a_family_that_ships_the_weight_names_it() {
    let cases: [(&str, u16); 6] = [
        ("Regular", 400),
        ("Bold", 700),
        ("Medium", 500),
        ("Light", 300),
        ("SemiBold", 600),
        ("Black", 900),
    ];
    for (suffix, named) in cases {
        for face in catalog()
            .faces
            .iter()
            .filter(|face| face.weight == named && face.style == "normal")
        {
            if resolve_metric_compat_family(&face.family) != Some(face.family.as_str()) {
                continue;
            }
            let name = format!("{} {suffix}", face.family);
            assert_eq!(
                file(resolve_bundled_family_face(&name, false, false)),
                Some(face.file.as_str()),
                "{name}"
            );
        }
        for face in catalog()
            .faces
            .iter()
            .filter(|face| face.weight == 400 && face.style == "normal")
        {
            let ships = catalog().faces.iter().any(|other| {
                other.family == face.family && other.weight == named && other.style == "normal"
            });
            if ships {
                continue;
            }
            let name = format!("{} {suffix}", face.family);
            assert_ne!(
                weight(resolve_bundled_family_face(&name, false, false)),
                Some(named),
                "{name} borrows a weight its family does not ship"
            );
        }
    }
}

#[test]
fn lighter_and_heavier_names_keep_the_legacy_variant() {
    for name in ["Calibri Light", "Calibri light", "Calibri--Light"] {
        assert_eq!(file(resolve_metric_compat_face(name, false, false)), None);
        assert_eq!(
            file(resolve_light_variant_face(name, false, false)),
            Some("Carlito-Regular.ttf.zst"),
            "{name}"
        );
        assert_eq!(
            file(resolve_light_variant_face(name, true, false)),
            Some("Carlito-Regular.ttf.zst"),
            "{name}"
        );
        assert_eq!(
            file(resolve_light_variant_face(name, false, true)),
            Some("Carlito-Italic.ttf.zst"),
            "{name}"
        );
    }
    assert_eq!(file(resolve_metric_compat_face("Calibri Black", false, false)), None);
    assert_eq!(
        file(resolve_light_variant_face("Inter Light", false, false)),
        Some("Inter-Regular.ttf.zst")
    );
    assert_eq!(
        file(resolve_light_variant_face("Inter-Thin", false, false)),
        Some("Inter-Regular.ttf.zst")
    );
    assert_eq!(
        file(resolve_metric_compat_face("Segoe UI Semibold", true, false)),
        Some("Selawik-Bold.ttf.zst")
    );
    assert_eq!(
        file(resolve_metric_compat_face("Segoe UI Light", false, false)),
        Some("Selawik-Light.ttf.zst")
    );
}

#[test]
fn a_name_without_a_bundled_family_keeps_its_resolution() {
    for name in ["Bold", "Medium", "noto sans sc medium extra"] {
        assert_eq!(file(resolve_bundled_family_face(name, false, false)), None, "{name}");
        assert_eq!(file(resolve_metric_compat_face(name, false, false)), None, "{name}");
    }
    assert_eq!(
        weight(resolve_bundled_family_face("Carlito", true, false)),
        Some(700)
    );
    assert_eq!(
        weight(resolve_bundled_family_face("Carlito", false, false)),
        Some(400)
    );
}

#[test]
fn cjk_script_fallback_keeps_the_requested_cjk_family() {
    for (family, script, bold, italic, expected) in [
        ("SimSun", "cjk-sc", true, true, "NotoSerifSC-Bold.otf.zst"),
        ("SimSun", "cjk-sc", false, true, "NotoSerifSC-Regular.otf.zst"),
        ("SimSun", "cjk-sc", true, false, "NotoSerifSC-Bold.otf.zst"),
        ("KaiTi", "cjk-sc", true, true, "NotoSerifSC-Bold.otf.zst"),
        ("KaiTi", "cjk-sc", false, false, "NotoSerifSC-Regular.otf.zst"),
        ("楷体", "cjk-sc", true, true, "NotoSerifSC-Bold.otf.zst"),
        ("Kaiti GB2312", "cjk-sc", true, true, "NotoSerifSC-Bold.otf.zst"),
        (
            "Noto Sans SC Medium",
            "cjk-sc",
            false,
            false,
            "NotoSansSC-Medium.otf.zst",
        ),
        ("Times New Roman", "cjk-tc", true, true, "NotoSerifTC-Bold.otf.zst"),
        ("Times New Roman", "cjk-sc", true, true, "NotoSerifSC-Bold.otf.zst"),
        ("Microsoft YaHei", "cjk-sc", true, true, "NotoSansSC-Bold.otf.zst"),
        ("MS Mincho", "cjk-jp", true, false, "NotoSerifJP-Bold.otf.zst"),
    ] {
        assert_eq!(
            file(resolve_family_script_fallback_face(family, script, bold, italic)),
            Some(expected),
            "{family} {script} bold={bold} italic={italic}"
        );
    }
    assert_eq!(
        file(resolve_script_fallback_face("cjk-sc", true, true)),
        Some("NotoSansSC-Bold.otf.zst")
    );
    assert_eq!(
        file(resolve_metric_compat_face("SimSun", true, true)),
        Some("NotoSerifSC-Bold.otf.zst")
    );
    assert_eq!(
        file(resolve_family_script_fallback_face(
            "Simplified Arabic",
            "arabic",
            true,
            true
        )),
        Some("NotoNaskhArabic-Regular.ttf.zst")
    );
}

#[test]
fn word_families_keep_their_bundled_family() {
    for face in catalog()
        .faces
        .iter()
        .filter(|face| face.style == "normal")
    {
        if let Some(word) = &face.metric_compat_with {
            assert_eq!(
                resolve_metric_compat_family(word),
                Some(face.family.as_str()),
                "{word}"
            );
        }
    }
    for (alias, target) in &catalog().word_family_aliases {
        if let Some(face) = catalog().faces.iter().rev().find(|face| {
            face.metric_compat_with
                .as_deref()
                .is_some_and(|word| word.to_lowercase() == *target)
        }) {
            assert_eq!(
                resolve_metric_compat_family(alias),
                Some(face.family.as_str()),
                "{alias}"
            );
        }
    }
}
