# Embedded report font

CrossTaxSansSC-Regular.ttf is a static wght=400 instance derived from Google Fonts Noto Sans SC.
The family was renamed CrossTax Sans SC when producing this instance; OFL.txt accompanies the font.
The upstream URL, fixed repository commit and original/derived SHA-256 values are recorded in source.json.
Upstream: https://github.com/google/fonts/tree/48133440178622e215912d34d386c5ee1682c677/ofl/notosanssc

This binary is intentionally packaged under backend/reports so Docker and wheel installations include it.
Production rendering never downloads fonts and needs no system font installation.
fontTools was used only during asset preparation (instantiateVariableFont with wght=400, name IDs 1/2/4/6/16/17 renamed).
It is not a runtime dependency. Future replacements must preserve licensing, update source.json and pass PDF visual/text tests.
Characters outside the font coverage are explicitly escaped in prose; the JSON appendix uses Unicode escapes for exact values.
