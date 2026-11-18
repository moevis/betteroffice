#!/usr/bin/env python3
"""Converts a TrueType face to a name-keyed CFF/OTF face under a new font name.

Pinned to fontTools 4.60.1. `glyf` outlines are converted to Type 2 charstrings
on the integer grid (tolerance 0.5), which bounds outline drift at one half font
unit; hints are dropped, because TrueType instructions have no CFF equivalent.
Every other table is copied verbatim, so cmap, UVS, GSUB, GPOS, GDEF, hmtx and
vmtx of the derivative equal the source's. The name table gets the given family
and PostScript names; localized records of the renamed IDs are dropped, and the
copyright, licence and version records are kept.

Usage: ttf-to-cff.py <input.ttf> <output.otf> --ps-name <name> --family <family>
       --style <style> --description <text> --modified <YYYY-MM-DD>
"""

import argparse
import datetime
import sys
from collections import Counter
from pathlib import Path

from fontTools.cffLib import (
    CFFFontSet,
    CharStrings,
    GlobalSubrsIndex,
    PrivateDict,
    TopDict,
    TopDictIndex,
)
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.ttLib import TTFont, newTable

FONTTOOLS_VERSION = "4.60.1"
RENAMED = (1, 2, 3, 4, 6, 16, 17, 18)
MAC_EPOCH = datetime.datetime(1904, 1, 1)


def name_records(font, names, style, ps_name):
    """Replaces the family, subfamily and PostScript records of the face."""
    family, unique = names, f"{names} {style}"
    values = {
        1: family,
        2: style,
        3: f"{ps_name} derivative",
        4: unique,
        6: ps_name,
        16: family,
        17: style,
        18: unique,
    }
    table = font["name"]
    kept = [record for record in table.names if record.nameID not in RENAMED]
    table.names = kept
    for name_id, value in values.items():
        table.setName(value, name_id, 3, 1, 0x409)
        table.setName(value, name_id, 1, 0, 0)
    return table


def conversion(font, ps_name):
    """The CFF table holding the face's outlines, desubroutinized and unhinted."""
    order = font.getGlyphOrder()
    glyphs = font.getGlyphSet()
    metrics = font["hmtx"].metrics
    private = PrivateDict()
    private.defaultWidthX = Counter(metrics[name][0] for name in order).most_common(1)[0][0]
    private.nominalWidthX = 0
    font_set = CFFFontSet()
    font_set.major = 1
    font_set.minor = 0
    font_set.otFont = font
    font_set.fontNames = [ps_name]
    font_set.topDictIndex = TopDictIndex()
    global_subrs = GlobalSubrsIndex()
    font_set.GlobalSubrs = global_subrs
    top = TopDict()
    top.charset = order
    top.Private = private
    top.GlobalSubrs = global_subrs
    units = font["head"].unitsPerEm
    top.FontMatrix = [1 / units, 0, 0, 1 / units, 0, 0]
    head = font["head"]
    top.FontBBox = [head.xMin, head.yMin, head.xMax, head.yMax]
    char_strings = CharStrings(None, order, global_subrs, private, None, None)
    for name in order:
        pen = T2CharStringPen(metrics[name][0], glyphs, roundTolerance=0.5)
        glyphs[name].draw(pen)
        char_string = pen.getCharString()
        char_string.private = private
        char_string.globalSubrs = global_subrs
        char_strings[name] = char_string
    top.CharStrings = char_strings
    font_set.topDictIndex.append(top)
    return font_set


def build(source, target, names, style, ps_name, description, modified):
    font = TTFont(source, lazy=False, recalcBBoxes=False, recalcTimestamp=False)
    order = font.getGlyphOrder()
    font_set = conversion(font, ps_name)
    top = font_set.topDictIndex[0]
    top.FamilyName = names
    top.FullName = f"{names} {style}"
    top.Weight = style
    font["CFF "] = newTable("CFF ")
    font["CFF "].cff = font_set
    font.sfntVersion = "OTTO"
    for tag in ("glyf", "loca", "gasp"):
        if tag in font:
            del font[tag]
    font["maxp"].tableVersion = 0x00005000
    font["post"].formatType = 3.0
    if 10 in [record.nameID for record in font["name"].names]:
        font["name"].removeNames(nameID=10)
    font["name"].setName(description, 10, 3, 1, 0x409)
    font["head"].modified = int(
        (datetime.datetime.combine(modified, datetime.time()) - MAC_EPOCH).total_seconds()
    )
    name_records(font, names, style, ps_name)
    font.save(target)
    return order


def check(source, target, order, ps_name, names):
    """Fails unless the derivative keeps the source's tables, metrics and cmap."""
    original = TTFont(source, lazy=False, recalcBBoxes=False, recalcTimestamp=False)
    derivative = TTFont(target, lazy=False, recalcBBoxes=False, recalcTimestamp=False)
    if derivative.getGlyphOrder() != order:
        raise SystemExit("glyph order changed")
    for tag in ("GSUB", "GPOS", "GDEF", "cmap", "hmtx", "vmtx", "hhea", "vhea", "OS/2"):
        if original.reader[tag] != derivative.reader[tag]:
            raise SystemExit(f"{tag} differs from the source")
    if derivative.sfntVersion != "OTTO" or "glyf" in derivative:
        raise SystemExit("derivative is not a CFF face")
    if derivative["CFF "].cff.fontNames != [ps_name]:
        raise SystemExit("CFF FontName was not renamed")
    for record in derivative["name"].names:
        if record.nameID in RENAMED + (6,):
            text = str(record)
            if any(token in text for token in ("LXGW", "霞鹜", "ZhenKai", "臻楷")):
                raise SystemExit(f"reserved name in name ID {record.nameID}: {text}")
    if names not in str(derivative["name"].getDebugName(1)):
        raise SystemExit("family name was not applied")
    source_glyphs = original.getGlyphSet()
    target_glyphs = derivative.getGlyphSet()
    worst = 0.0
    for name in order:
        left, right = BoundsPen(source_glyphs), BoundsPen(target_glyphs)
        source_glyphs[name].draw(left)
        target_glyphs[name].draw(right)
        if left.bounds is None and right.bounds is None:
            continue
        if left.bounds is None or right.bounds is None:
            raise SystemExit(f"outline of {name} disappeared")
        worst = max(worst, max(abs(a - b) for a, b in zip(left.bounds, right.bounds)))
    if worst > 1.0:
        raise SystemExit(f"outline drift of {worst} font units exceeds the integer grid")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source", type=Path, help="TrueType face to convert")
    parser.add_argument("target", type=Path, help="CFF/OTF face to write")
    parser.add_argument("--ps-name", required=True, help="PostScript and CFF font name")
    parser.add_argument("--family", required=True, help="family name of the derivative")
    parser.add_argument("--style", required=True, help="subfamily name of the derivative")
    parser.add_argument("--description", required=True, help="name ID 10 of the derivative")
    parser.add_argument("--modified", required=True, help="head.modified date, YYYY-MM-DD")
    args = parser.parse_args()
    import fontTools

    if fontTools.version != FONTTOOLS_VERSION:
        raise SystemExit(f"fonttools {FONTTOOLS_VERSION} is required, found {fontTools.version}")
    modified = datetime.date.fromisoformat(args.modified)
    order = build(
        args.source,
        args.target,
        args.family,
        args.style,
        args.ps_name,
        args.description,
        modified,
    )
    check(args.source, args.target, order, args.ps_name, args.family)
    print(f"{args.target.name}: {len(order)} glyphs converted from {args.source.name}")


if __name__ == "__main__":
    sys.exit(main())
