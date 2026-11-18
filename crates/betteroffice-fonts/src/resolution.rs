use serde::Deserialize;

use crate::catalog::{BundledFontFace, WordFamilySubstitute, catalog};

#[derive(Clone, Copy, Debug, Default, Deserialize, Eq, PartialEq)]
#[serde(rename_all = "lowercase")]
pub enum LastResortOffice {
    #[default]
    PowerPoint,
    Word,
}

impl LastResortOffice {
    fn key(self) -> &'static str {
        match self {
            Self::PowerPoint => "powerpoint",
            Self::Word => "word",
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct LastResortChoice {
    pub face: &'static BundledFontFace,
    pub only_if_primary_fails: bool,
}

fn whitespace(ch: char) -> bool {
    (ch.is_whitespace() && ch != '\u{85}') || ch == '\u{feff}'
}

fn key(family: &str) -> String {
    family.trim_matches(whitespace).to_lowercase()
}

/// The substitution table entry for an Office family name, matched case-insensitively.
pub fn resolve_word_family_substitute(family: &str) -> Option<&'static WordFamilySubstitute> {
    catalog().word_family_substitutes.get(&key(family))
}

fn matches_style(face: &BundledFontFace, bold: bool, italic: bool) -> bool {
    face.weight == if bold { 700 } else { 400 }
        && face.style == if italic { "italic" } else { "normal" }
}

/// The bundled Kai face, which keeps its Regular weight whatever the style.
const KAI_FAMILY: &str = "Northstar Kai";
/// Word spellings of the Kai face; they reach it only once the pack ships it.
const KAI_WORD_NAMES: [&str; 5] = [
    "kaiti",
    "楷体",
    "kaiti_gb2312",
    "kaiti gb2312",
    "kaiti-gb2312",
];

fn bundled_family_name(key: &str) -> Option<&'static str> {
    catalog()
        .faces
        .iter()
        .rev()
        .find(|face| face.family.to_lowercase() == key)
        .map(|face| face.family.as_str())
}

fn kai_family() -> Option<&'static str> {
    catalog()
        .faces
        .iter()
        .find(|face| face.family == KAI_FAMILY)
        .map(|face| face.family.as_str())
}

fn metric_compat_family(key: &str) -> Option<&'static str> {
    if KAI_WORD_NAMES.contains(&key) && let Some(family) = kai_family() {
        return Some(family);
    }
    let key = catalog()
        .word_family_aliases
        .get(key)
        .map_or(key, String::as_str);
    catalog().faces.iter().rev().find_map(|face| {
        face.metric_compat_with
            .as_ref()
            .filter(|name| name.to_lowercase() == key)
            .map(|_| face.family.as_str())
    })
}

pub fn resolve_metric_compat_family(word_family: &str) -> Option<&'static str> {
    metric_compat_family(&key(word_family))
}

const STATIC_WEIGHT_SUFFIXES: [(&str, u16); 15] = [
    ("thin", 100),
    ("hairline", 100),
    ("extralight", 200),
    ("ultralight", 200),
    ("light", 300),
    ("demilight", 350),
    ("semilight", 350),
    ("regular", 400),
    ("medium", 500),
    ("demibold", 600),
    ("semibold", 600),
    ("bold", 700),
    ("extrabold", 800),
    ("black", 900),
    ("heavy", 900),
];

fn split_weight_suffix(name: &str) -> Option<(&str, &str)> {
    let trimmed = name.trim_matches(whitespace);
    let (end, last) = trimmed
        .char_indices()
        .rev()
        .find(|&(_, ch)| !whitespace(ch) && ch != '-')?;
    let end = end + last.len_utf8();
    let (separator, ch) = trimmed[..end]
        .char_indices()
        .rev()
        .find(|&(_, ch)| whitespace(ch) || ch == '-')?;
    Some((&trimmed[..separator], &trimmed[separator + ch.len_utf8()..end]))
}

fn name_key(name: &str) -> Option<String> {
    let mut key = String::with_capacity(name.len());
    for word in name
        .split(|ch| whitespace(ch) || ch == '-')
        .filter(|word| !word.is_empty())
    {
        if !key.is_empty() {
            key.push(' ');
        }
        key.extend(word.chars().flat_map(char::to_lowercase));
    }
    (!key.is_empty()).then_some(key)
}

/// The weight a name such as `Noto Sans SC Medium` spells out, with the family that ships it.
fn static_weight(name: &str) -> Option<(&'static str, u16)> {
    let (prefix, suffix) = split_weight_suffix(name)?;
    let mut suffixes = STATIC_WEIGHT_SUFFIXES.iter();
    let weight = suffixes.find(|entry| suffix.eq_ignore_ascii_case(entry.0))?.1;
    let name = name_key(prefix)?;
    let family = metric_compat_family(&name).or_else(|| bundled_family_name(&name))?;
    Some((family, weight))
}

/// The upright face a name such as `Noto Sans SC Medium` spells out, when that family ships the weight.
fn static_weight_face(name: &str) -> Option<&'static BundledFontFace> {
    let (family, weight) = static_weight(name)?;
    upright_face(catalog().faces.iter(), family, weight)
}

fn upright_face<'a>(
    mut faces: impl Iterator<Item = &'a BundledFontFace>,
    family: &str,
    weight: u16,
) -> Option<&'a BundledFontFace> {
    faces.find(|face| face.family == family && face.weight == weight && face.style == "normal")
}

fn is_cjk_family(family: &str) -> bool {
    catalog()
        .faces
        .iter()
        .find(|face| face.family == family)
        .and_then(|face| face.script.as_deref())
        .is_some_and(|script| script.starts_with("cjk-"))
}

pub fn resolve_metric_compat_face(
    word_family: &str,
    bold: bool,
    italic: bool,
) -> Option<&'static BundledFontFace> {
    if let Some(face) = static_weight_face(word_family) {
        return Some(face);
    }
    let family = resolve_metric_compat_family(word_family)?;
    if family == "Selawik" {
        if italic {
            return None;
        }
        let key = key(word_family);
        let target = if bold && key == "segoe ui semibold" {
            "segoe ui"
        } else {
            &key
        };
        let weight = if bold && target == "segoe ui" {
            700
        } else {
            400
        };
        return catalog().faces.iter().find(|face| {
            face.metric_compat_with
                .as_ref()
                .is_some_and(|name| name.to_lowercase() == target)
                && face.weight == weight
        });
    }
    if let Some(face) = family_face(family, bold, italic) {
        return Some(face);
    }
    if is_cjk_family(family) && let Some(face) = family_face(family, bold, false) {
        return Some(face);
    }
    family_face(family, false, false)
}

fn family_face(family: &str, bold: bool, italic: bool) -> Option<&'static BundledFontFace> {
    catalog()
        .faces
        .iter()
        .find(|face| face.family == family && matches_style(face, bold, italic))
}

pub fn resolve_bundled_family_face(
    family: &str,
    bold: bool,
    italic: bool,
) -> Option<&'static BundledFontFace> {
    if let Some(face) = static_weight_face(family) {
        return Some(face);
    }
    if resolve_metric_compat_family(family) == Some("Selawik") {
        return if italic {
            None
        } else {
            resolve_metric_compat_face(family, bold, false)
        };
    }
    let key = key(family);
    let bundled = bundled_family_name(&key)
        .or_else(|| {
            catalog()
                .unvendored_noto_serif
                .get(&key)
                .map(String::as_str)
        })
        .or_else(|| metric_compat_family(&key))?;
    family_face(bundled, bold, italic)
}

fn script_faces(script: &str) -> Option<impl Iterator<Item = &'static BundledFontFace> + Clone> {
    let files = catalog().script_fallback_order.get(script)?;
    Some(files.iter().filter_map(|file| catalog().faces.iter().find(|face| &face.file == file)))
}

fn style_ladder(
    faces: impl Iterator<Item = &'static BundledFontFace> + Clone,
    bold: bool,
    italic: bool,
) -> Option<&'static BundledFontFace> {
    let pick = |bold: bool, italic: bool| faces.clone().find(|face| matches_style(face, bold, italic));
    pick(bold, italic)
        .or_else(|| pick(bold, false))
        .or_else(|| pick(false, false))
        .or_else(|| faces.clone().next())
}

fn serif_family_for(
    family: &str,
    mut faces: impl Iterator<Item = &'static BundledFontFace>,
    kai: bool,
) -> Option<&'static str> {
    if !kai && !looks_serif(family) {
        return None;
    }
    faces
        .find(|face| face.family.starts_with("Noto Serif "))
        .map(|face| face.family.as_str())
}

pub fn resolve_script_fallback_face(
    script: &str,
    bold: bool,
    italic: bool,
) -> Option<&'static BundledFontFace> {
    style_ladder(script_faces(script)?, bold, italic)
}

/// The script fallback for text that requests `family`: a CJK request keeps the
/// family it names, or the script's serif for a serif name, when the script
/// covers it; otherwise [`resolve_script_fallback_face`].
pub fn resolve_family_script_fallback_face(
    family: &str,
    script: &str,
    bold: bool,
    italic: bool,
) -> Option<&'static BundledFontFace> {
    let key = key(family);
    if let Some(face) = catalog()
        .requested_family_script_fallback
        .get(&key)
        .and_then(|scripts| scripts.get(script))
        .and_then(|file| catalog().faces.iter().find(|face| &face.file == file))
    {
        return Some(face);
    }
    let faces = script_faces(script)?;
    if script.starts_with("cjk-") {
        if let Some((family, weight)) = static_weight(family)
            && let Some(face) = upright_face(faces.clone(), family, weight)
        {
            return Some(face);
        }
        let requested = metric_compat_family(&key).or_else(|| bundled_family_name(&key));
        let preferred = requested
            .filter(|family| *family != KAI_FAMILY && faces.clone().any(|face| face.family == *family))
            .or_else(|| serif_family_for(family, faces.clone(), requested == Some(KAI_FAMILY)));
        if let Some(preferred) = preferred {
            return style_ladder(faces.filter(|face| face.family == preferred), bold, italic);
        }
    }
    style_ladder(faces, bold, italic)
}

fn variant(family: &str, italic: bool, heavy: bool) -> Option<&'static BundledFontFace> {
    let family = family.trim_matches(whitespace);
    if family.ends_with('-') {
        return None;
    }
    let mut words: Vec<_> = family
        .split(|ch| whitespace(ch) || ch == '-')
        .filter(|word| !word.is_empty())
        .collect();
    if words.len() < 2 {
        return None;
    }
    let suffix = words.pop()?.to_lowercase();
    let variants = if heavy {
        &catalog().heavier_than_regular
    } else {
        &catalog().lighter_than_regular
    };
    if !variants.contains(&suffix) {
        return None;
    }
    resolve_metric_compat_face(&words.join(" "), heavy, italic)
}

pub fn resolve_light_variant_face(
    family: &str,
    _bold: bool,
    italic: bool,
) -> Option<&'static BundledFontFace> {
    variant(family, italic, false)
}

fn looks_serif(family: &str) -> bool {
    let lower = family.to_lowercase();
    let pattern = &catalog().serif_exclusion_pattern;
    let exclusions = [
        pattern.replace("[ -]?", ""),
        pattern.replace("[ -]?", " "),
        pattern.replace("[ -]?", "-"),
    ];
    !exclusions.iter().any(|pattern| lower.contains(pattern))
        && catalog()
            .serif_markers
            .iter()
            .any(|marker| lower.contains(marker))
}

fn looks_mono(family: &str) -> bool {
    let lower = family.to_lowercase();
    let word = catalog()
        .mono_pattern
        .strip_prefix(r"(^|[\s-])")
        .and_then(|pattern| pattern.strip_suffix(r"([\s-]|$)"))
        .expect("bundled monospace pattern");
    catalog()
        .mono_markers
        .iter()
        .any(|marker| lower.contains(marker))
        || lower
            .split(|ch| whitespace(ch) || ch == '-')
            .any(|candidate| candidate == word)
}

fn resolve_base_face(
    family: &str,
    mut bold: bool,
    italic: bool,
    office: LastResortOffice,
    exclude_glyph_fallback: bool,
) -> &'static BundledFontFace {
    let light = variant(family, italic, false);
    let allowed = |face: &&BundledFontFace| {
        !exclude_glyph_fallback || !catalog().glyph_fallback_families.contains(&face.family)
    };
    if let Some(face) = light.filter(allowed) {
        return face;
    }
    if light.is_some() {
        bold = false;
    }
    if let Some(face) = variant(family, italic, true).filter(allowed) {
        return face;
    }
    if catalog().emulated_symbol_families.contains(&key(family)) {
        return resolve_metric_compat_face("Arial", bold, italic).expect("bundled Arial face");
    }
    let families = &catalog().last_resort_families[office.key()];
    if looks_mono(family) {
        return family_face(&families.mono, bold, italic).expect("bundled monospace face");
    }
    if let Some(matched) = catalog().width_matched_substitutes.get(&key(family))
        && let Some(face) = resolve_metric_compat_face(&matched.family, bold, italic)
    {
        return face;
    }
    let base = if looks_serif(family) {
        &families.serif
    } else {
        &families.sans
    };
    family_face(base, bold, italic).expect("bundled base face")
}

pub fn resolve_last_resort_choice(
    family: &str,
    bold: bool,
    italic: bool,
    office: LastResortOffice,
) -> LastResortChoice {
    let primary = resolve_metric_compat_face(family, bold, italic);
    let base = resolve_base_face(family, bold, italic, office, primary.is_some());
    if primary.is_some_and(|primary| primary.file == base.file) {
        let alternate = if base.family == catalog().last_resort_families["word"].sans {
            &catalog().last_resort_families["powerpoint"].sans
        } else {
            &catalog().last_resort_families["word"].sans
        };
        LastResortChoice {
            face: family_face(alternate, bold, italic).expect("bundled alternate base face"),
            only_if_primary_fails: true,
        }
    } else {
        LastResortChoice {
            face: base,
            only_if_primary_fails: false,
        }
    }
}

pub fn resolve_last_resort_face(
    family: &str,
    bold: bool,
    italic: bool,
    office: LastResortOffice,
) -> &'static BundledFontFace {
    resolve_last_resort_choice(family, bold, italic, office).face
}

pub fn resolve_glyph_fallback_face(
    family: &str,
    bold: bool,
    italic: bool,
    office: LastResortOffice,
) -> Option<&'static BundledFontFace> {
    let primary = resolve_metric_compat_face(family, bold, italic);
    let face = primary.unwrap_or_else(|| resolve_base_face(family, bold, italic, office, false));
    if !catalog().glyph_fallback_families.contains(&face.family) {
        return None;
    }
    Some(if primary.is_some() {
        resolve_last_resort_face(family, bold, italic, office)
    } else {
        resolve_base_face(family, bold, italic, office, true)
    })
}

pub fn resolve_digit_advance(family: &str, bold: bool, italic: bool) -> Option<f64> {
    let style = match (bold, italic) {
        (false, false) => "regular",
        (true, false) => "bold",
        (false, true) => "italic",
        (true, true) => "boldItalic",
    };
    catalog()
        .width_matched_substitutes
        .get(&key(family))?
        .digit_advances
        .get(style)
        .copied()
}
