---
'@betteroffice/docx': patch
'@betteroffice/docx-react': patch
---

`readSelectionInfo()` returns the engine `version` and the raw `range` (`story`, `start`/`end` `paraId` and UTF-16 `offset`) of the caret or selection, forward-normalized. Viewer cross-story reads report `range: null`; editable cross-story reads refuse instead of returning only one story.
