"""Build the one-line lab summary shown on the app.py /patient page.

The /patient page shows a compact summary of the patient's most recent
labs: one token per category, in a fixed order, using the same
shorthand that gets written into the patient's yellow sticky note, eg

    11/2026- UA nl, TSH 2.5, A1c 6, LDL 104, LpA nl, uric acid 6.8, HBV/HCV neg

`build_lab_summary()` is a pure function mapping patient lab rows to a string.

Input
-----
`labs` must be **newest first**: ORDER BY result_date DESC NULLS LAST, id DESC

In each category, we use the first matchin row and ignore older rows.

For each row we read:

`name` (str or None)
    The lab test name e.g. "UA, Routine". Matching is done
    after stripping and lower-casing. In-house is lower case, Quest is all
    upper case, and LabCorp is title case.
`result` (str or None)
    JSON array of item dicts, each with at least `itemName` and `value` plus a
    `flag`, a reference `range` (e.g. `232-1245`) that may be empty, and a
    `paramNotes` result note. Quest sends "N" (normal)/"A" (abnormal) flags
    while LabCorp seds H/L/A abnormal and mostly empty flag if normal.
    paramNotes is used for stool-culture `No ... isolated`, for
    stool-parasite / C. diff toxin `Not Detected` etc.
    Imaging rows have the report instead: an array of dicts whose `notes`
    fields are the report text (`FINDINGS` / `IMPRESSION`).
`result_date` (str or None)
    ISO result date used for the leading `mm/yyyy`.
`date` (str or None)
    ISO order date; only used as a fallback for the leading `mm/yyyy`.

Rules
-----
An item counts as *abnormal* when its `flag` is nonempty and not N.

Abnormal tokens include the violated reference-range limit in
parentheses if known, eg `42(35)`: the upper limit for an `H` flag, the lower
limit for an `L` flag, via `_bound_for`. Values are written raw, with trailing
zeros stripped (_g), to one decimal (_round1), or as integers.

Tokens are emitted in this fixed order and joined with `, `.

1.  **UA**. Normal: `UA nl`. Abnormal: `UA ` + the abnormal items joined with
    commas: `pH {num}` / `pH<{num}` / `pH>{num}` for pH,
    `crystals+` for an abnormal crystals item, and
    `{name} {value}` in lower case (a `trace` value gains a `+`, eg
    `protein trace+`) for the rest. Omit squamous epithelial cells,
    the `Microscopic Examination` section header, `Bacteria` = `Few`,
    `Ketones` = `Trace` or `2+`, `Occult Blood` = `Trace` or `1+`, and
    -- at
    any value -- `Specific Gravity`, `Appearance` and `WBC Esterase`
    (Quest's `Leukocyte Esterase`). Omit microscopy count items
    (`WBC` / `RBC` / `Epithelial Cells (non renal)` / `Epithelial
    Cells (renal)`) when their value is an absent
    text (`None seen` / LabCorp's `NOSEE`, ...) or eg `0-5` range indicating
    the tech could not confirm a presence. WBC is additionally omitted for
    a range at or below `10` (eg `6-10`, the tech's read for a count just
    above the `0-5` reference). Note that LabCorp flags its
    `Epithelial Cells (renal)` item A on the normal `0-10` value.
1a. **Ucx** urine culture. `Ucx neg` or `Ucx {value}` with the organism eg
    `Ucx Staphy` or `Ucx- E Coli`.
1b. **HCG** pregnancy test. `HCG neg` or `HCG+`.
2.  **TSH**. Always emit `TSH {val}/T4 nl` or `TSH {val}/T4 {val}`. Free T4
    can be from the same order or a standalone `free t4` order.
2a. **Thyroid cluster**: free T3, standalone free T4, the TPO and
    thyroglobulin antibodies, and TSI. Join normal members with `/` plus a
    single trailing ` nl` eg `TPO/thyroglobulin nl`. Each abnormal member
    reports a `{label} {val}({bound})`. Omit free T4 if it was used with TSH.
3.  **FSH**. Normal: `FSH nl`. Abnormal: `FSH {val}({bound})`.
4.  **Estradiol**. `Estradiol nl` or `Estradiol {val}({bound})`.
4a. **Testosterone**. Panel orders: all normal `testosterone T/F nl`,
    similarly if one is normal. Each abnormal item:
    `testosterone T {val}({bound})` or `testosterone F {val}({bound})`.
    Quest's standalone order: emit `testosterone {val}`.
4b. **Cortisol**. `cortisol nl` or `cortisol {val}`.
4c. **Prolactin**. `prolactin nl` or `prolactin {val}`.
4d. **LH**: `LH nl` or `LH {val}.
4e. **Progesterone**. `Progesterone nl` or `Progesterone {val}`.
4f. **AMH**. `AMH nl` or `AMH {val}({bound})`.
4g. **Metanephrine**. Both normal: `metanephrine nl`. Each abnormal
    `normetanephrine {val}({bound})` / `metanephrine {val}({bound})`.
    A flagged value without a result (pending) gives no token.
5.  **Glucose/A1c**. If we have both, always emit `Glu {glu}/A1c {val}`.
    If only A1c, always emit `A1c {val}`. The pair is unsigned at any
    value (the yellow notes sign neither member). If only glucose, emit
    `Glu {val}({bound})` if abnormal else omit.
6.  **Alb/Cr**. Normal: `Alb/Cr<30`. Abnormal: `Alb/Cr {val}{+}`.
7.  **LDL / HDL**. If lipid panel triglycerides are high and we know
    HDL, emit `{HDL}/{LDL}/{TG}({bound})`  eg `60/132+/210+(150)`.
    Else: if HDL is low emit `HDL {val}({bound})`, and always emit
    `LDL {val}{+}`. We ignore other abnormal values like total cholesterol,
    non-HDL cholestrerol, CHOL/HDLC ratio, LDL particle number, LDL peak
    size / pattern, HDL large, LDL small/medium, and high VLDL.
8.  **LpA**. Normal: `LpA nl`. Abnormal: `LpA {val}({bound})`.
9.  **ApoB**. Normal: `ApoB nl`. Abnormal: `ApoB {val}({bound})`.
9a. **CT CAC**. One token: `CAC={score}; {pctl}`. Additional
    findings: the `Aorta` section's sentence(s) naming an aortic ectasia
    / aneurysm / dilation e.g. `Ascending aortic ectasia 3.6 cm`.
    One `{vessel} {score}%` token per vessel at 90-100 stenosis.
    One `lung nodule(s)` token per `Other Findings` / `Aorta` / `Pericardium`
    sentence naming a pulmonary nodule, with its size and an `x{count}` if
    count > 1 eg `lung nodules x2 4 mm`.
9b. **Mammo**. BI-RADS 1-2: `Mammo nl`. Else report the `IMPRESSION` findings
    in full eg `Mammo: Probably benign right breast mass, which may reflect
    a fibroadenoma`.
9c. **US**. Region label shortened from order name: `abd`, `breast`, `thyroid`,
    `renal`, `pelvic`, `carotid`, `AAA`, `neck`, `soft tissue`, `testicular`,
    else the first name word. `IMPRESSION` (or `ASSESSMENT/MANAGEMENT` in
    Plus breast reports'). `US {label} nl` or the finding sentences in full eg
    `US thyroid: Left mid thyroid nodule measuring 1.4 cm, moderately
    suspicious (TI-RADS 4); follow-up recommended at 1, 2, 3, 5 years`. A
    breast report with a `BI-RADS {n}` line is like the mammo: 1-2 -> `US
    breast nl`.
9d. **BONE DENSITY**. All sites above -1.0: `Bone density nl`. Else the
    lowest T-score's site and value eg eg `Bone density femur -1.9`.
9e. **CT**. `chest` / `head` / `abd/pelvic` / `abd`, else the first part after
    CT. The report's `IMPRESSION` (or `CONCLUSION` /
    `ASSESSMENT`) section. `CT {label} nl` when the impression has no findings,
    else the finding sentences eg `CT chest: Multiple pulmonary nodules
    up to 6.3 mm. Recommend a repeat low-dose CT chest in 6 months`.
10. **CBC**. Normal: omit. Abnormal: eg `RBC {val}({bound})`.
10a. **MCV**. Normal: omit. Abnormal: `MCV {val}({bound})`.
10b. **WBC / Hb / Plt (same CBC rows)**. Normal: omit.
    Abnormal: one token per abnormal item, in that order,
    `WBC` / `Hb` / `Plt` as `{label} {val}({bound})`.
    The hematocrit is always omitted.
10c. **Eos**.  Normal: omit. Abnormal: `Eos {val}({bound})`.
    Use the *absolute* eosinophil item only.
10d. **Plt est**. Normal (`ADEQUATE`): omit. Abnormal (`DECREASED` value):
    `plt est decreased` unless the newest CBC has already reported an
    abnormal platelet count.
11. **VitD**. Always emit `VitD {val}{+}` (a value above 50 gains a
    `+`). A flagged value gains its range limit in parens, eg
    `VitD 23(30)` (low), `VitD 110+(100)` (high); a flagged value
    without a parsable range stays plain `VitD {val}`.
12. **PTH**. Normal: `PTH nl`. Abnormal: `PTH {val}({bound})`.
12a. **Free Calcium**. Normal: `Free Calcium nl`.
    Abnormal: `Free Calcium {val}({bound})`.
13. **Mg**. Normal: `Mg nl`. Abnormal: `Mg {val}({bound})`.
13a. **Mg RBC** (red-cell magnesium; Quest's `MAGNESIUM, RBC` order
    and LabCorp's `Magnesium, RBC` order -- a different test from the
    serum magnesium of rule 13, with its own reference range).  Normal:
    `Mg RBC nl`. Abnormal: `Mg RBC {val}({bound})`.
14. **Phos**. Normal: `Phos nl`. Abnormal: `Phos {val}({bound})`.
15. **Zinc**. Normal: `zinc nl`. Abnormal: `zinc {val}({bound})`.
15a. **Zinc RBC** (red-cell zinc; Quest's `ZINC, RBC` order -- a
    different test from the serum / plasma zinc of rule 15, with its
    own reference range).  Normal: `zinc RBC nl`. Abnormal: `zinc RBC
    {val}({bound})`.
16. **Uric acid**. `uric acid {val}` or `uric acid {val}({bound})`.
17. **PSA**. Always emit `PSA {val}{+}` for the total PSA. When the total is
    borderline (4-10 ng/mL) and free% is under 25, also emit `PSA%free {val}`.
18. **INR / PT**. One token per abnormal item, `INR` first: `INR {val}({bound})`
    / `PT {val}({bound})` (trailing zeros stripped; the `INR` item
    usually carries no reference range, so plain `INR {val}`).
    Normal: `INR/PT nl` when both items are present, `INR nl` /
    `PT nl` when only one is.
19. **PTT**. Normal: `PTT nl`. Abnormal: `PTT {val}({bound})`.
20. **BNP**. Normal: `BNP nl`. Abnormal: `BNP {val}({bound})`.
21. **HBV/HCV/HIV/RPR/G-C/Treponema**. All negative:
    `HBV/HCV/HIV/RPR/HSV/G-C/Treponema neg`. Only the hep
    B/C screens: `HBV/HCV neg`. The HBV/HCV group is negative when
    the surface-antigen and HCV Ab screen rows are present and their
    results are normal (reactive surface-Ab means immunity, not relevant here).
    An abnormal surface-antigen / HCV result emits its own `HBsAg+` / `HCV+` token.
    `HIV+`, `RPR+`. A negative surface-Ag screen with no HCV row emits a
    `HBV neg` token. Report `HIV/HDV` if both negative.
21a. **HSV 1/2 IgG**. The negative types join the STD token's ` neg` list,
    after `RPR`: both types negative contribute `HSV` (`HBV/HCV/HIV/RPR/HSV
    neg`), one type negative contributes `HSV1` / `HSV2` (`HBV/HCV/
    HIV/RPR/HSV2 neg`). A positive type is its own token right
    after the STD token, `HSV1+` / `HSV2+`, or one combined
    `HSV1/HSV2+` when both types are positive. Use value not the flag.
22. **HBV DNA**. `HBV DNA neg` for a not-detected result (LabCorp's
    `HBV DNA not detected` text counts); `HBV DNA <{lim}` for a
    result detected below the quantification limit (a limit reported
    in log10 is rendered as 10**lim: `<1.00 DETECTED` -> `HBV DNA
    <10`); otherwise `HBV DNA {linear}/{log10}`, the level written
    with its log10 the way the yellow notes do it (a value reported
    in log10 is reconstructed as 10**value, rounded to a whole
    number: `2.62` -> `HBV DNA 417/2.62`).
22a. **HCV RNA**. Quantitative viral load, not a screen. The HCV
    Ab order with reflex to RNA is a Ab screen not in this category.
    `HCV RNA neg`, `HCV RNA <{lim}` if detected below the quantification limit,
    else `HCV RNA {linear}/{log10}`. Quest reports linear `IU/mL` first and
    `Log IU/mL` second. We report linear, computing 10**value if only log10 is
    given.
23. **eAg**. Both `eAg/AFP neg` then emit grouped. Else `eAg neg` or `eAg+`.
24. **HBcAb**. `HBcAb neg` / `HBcAb+` like the eAg.
24a. **HDV**. Both `HIV/HDV neg`: group with STDs. Else `HDV neg` or `HDV+`.
24b. **Hb electrophoresis / HTLV**. Eg `Hb electrophoresis/HTLV neg`,
    `HTLV neg`, `Hb electrophoresis+`, or `HTLV+`.
24c. **HBV Ab**. Report `HBV Ab+` when reactive or immune (above 10
    mIU/mL). A non-immune surface Ab reports `HBV Ab neg` when the
    patient has HBV infection (a positive surface-Ag screen or a
    detected HBV DNA level -- the vaccine does not help an infected
    patient); otherwise it contributes the token's `HBV` component to
    the `RTC ... vacc` token (rule 25). A positive HAV total Ab
    (rule 25) condenses the two tokens into one `HAV/HBV Ab+`.
25. **HAV / RTC-vacc**. `HAV Ab+` when the HAV total antibody is
    positive. A positive surface Ab (rule 24c) condenses the two
    tokens into one `HAV/HBV Ab+`. One `RTC {X} vacc` token (return to clinic for the
    vaccine), the components joined with `/` in the fixed HAV / HBV /
    MMR order (`RTC HAV vacc`, `RTC HAV/HBV vacc`, `RTC HAV/HBV/MMR
    vacc`), for each of: HAV -- the total Ab shows no confirmed immunity (Quest's
    `NON-REACTIVE` / `BORDERLINE`, LabCorp's `Negative`); HBV -- the
    surface Ab is non-immune and the patient has no HBV infection
    (rule 24c; an infected patient's negative surface Ab reports
    `HBV Ab neg` instead); MMR -- any of the measles / mumps / rubella tests is
    non-immune (a level at or below its Ab+ threshold, the equivocal
    bands included, or a negative / non-immune text value; the MMR
    vaccine covers all three, so one non-immune component needs it).
    An inconclusive result counts as needing the vaccine (it does not
    confirm immunity); a pending / empty value gives no signal. The
    token is emitted at the very end of the summary, after all the
    other tokens.
25a. **HAV IgM**. Emit `HAV IgM+` or omit.
26. **Measles**. Emit `measles Ab+` if the IgG level > 16.49, else omit.
    The flag is unreliable.
26a. **Mumps**. Emit `mumps Ab+` when the IgG level > 10.99, else omit.
26b. **Rubella**. `rubella Ab+` if the index is immune (above 0.99). Else omit.
    All three components positive condense into one `MMR Ab+`. If the
    MMR vaccine is needed, the per-component Ab+ tokens are suppressed.
26c. **Varicella**. If positive / reactive: `varicella Ab+`. 
    Use the value because LabCorp does not set a flag:
    `Reactive` / `Positive` text is positive,
    `Non Reactive` / `Negative` negative; a numeric S/CO level >= 1.00 is
    positive; a numeric index level >= 165.00 is positive. Else omit (tend
    to need varicella vacc).
27. **Iron**. `iron {tIBC} nl` if every item of the panel is normal
    (the TIBC value is always shown, eg `iron 334 nl`; plain `iron nl`
    when the panel carries no TIBC value). Else one token per abnormal
    item, in report order, `{label} {val}({bound})` with the labels
    `iron`, `TIBC`, `iron%sat` and `ferritin`.
27a. **Ferritin**. Always reported next to the iron token: the panel's
    own `Ferritin` item when it is usable, else the newest standalone
    ferritin order (and the standalone order is reported on its own
    when no iron order is present). Normal: `ferritin {val}`; abnormal:
    `ferritin {val}({bound})` (an abnormal panel item is reported in
    the panel token itself, rule 27).
27b. **Iron**. Normal: omit. Abnormal: `iron {val}({bound})`.
27c. **Copper**. `copper nl` or `copper {val}({bound})`.
28. **B12**. Abnormal: `B12 {val}({bound})`. normal: `B12 {val}`.
28a. **B1/B6**. Normal items grouped eg `B1/B6 nl`.
    Each abnormal `{label} {val}({bound})`.
28b. **B2**. `B2 nl` or `B2 {val}({bound})`.
29. **FA**. `FA nl` or `FA {val}({bound})`.
30. **AST/ALT**. Emitted only when a value is high:
    `AST/ALT {ast}{+}({bound})/{alt}{+}({bound})` eg `AST/ALT 34+/30`. When
    only one of the two items is present the high one is emitted alone,
    eg `ALT 54+(46)`. Omit if neither value is high. A high total protein
    is reported right after as its own `protein {val}{+}({bound})`
    token. For other panel items, omit if normal else: `BUN`, `Cr` / `CrCl`
    (both abnormal -> one combined `Cr/CrCl {cr}/{crcl}({bound})`).
    Omit Cr / CrCl for a low Cr, but report Cr / CrCl if the eGFR is abnormal.
    A low CrCl is still reported, `bilirubin` (total only), `AP`, `albumin`,
    `Ca`, `Na`, `Cl`, `CO2`, `K`. The panel's remaining items are ignored.
30a. **GGT** (standalone order). Normal: omit. Abnormal: `GGT {val}({bound})`.
30b. **CK**. `CK nl` or `CK {val}({bound})`.
31. **amylase**. `amylase nl` or `amylase {val}({bound})`.
32. **lipase**. `lipase nl` or `lipase {val}({bound})`.
33. **ANA**. `ANA+` when any ANA item is flagged abnormal, and the item's
    `1:{titer}` value appended when one is present: `ANA+ 1:80`.
    `ANA nl` when no ANA item is flagged abnormal.
34. **ESR / CRP**. `ESR/CRP nl` if both normal. Abnormal as `ESR {val}({bound})`
    / `CRP {val}({bound})`. Use `ESR nl` / `CRP nl` only when the other test
    is absent.
34a. **RF**. `RF nl` or `RF {val}({bound})`.
34b. **Anti-CCP**. `Anti-CCP nl` or `Anti-CCP {val}`.
34c. **C3 / C4**. One token per abnormal item
    `C3 {val}({bound})` / `C4 {val}({bound})`. `C3/C4 nl` when both are normal,
    `C3 nl` / `C4 nl` when only one is.
34d. **dsDNA**. `dsDNA+` if abnormal; `dsDNA neg` when its value is in the
    negative set, or its flag is normal. LabCorp sends '' on a
    negative, whose value is a small number such as 2; Quest sends
    flag N on a negative.
34e. **Cardiac CRP (hs-CRP)**. `hsCRP nl` or `hsCRP {val}({bound})`.
35. **H pylori**. `H pylori neg` or `H pylori+`.
36. **stool occult**. `stool occult+` or `stool occult neg`.
36a. **Stool culture**. `stool culture neg` if every order is negative.
    One `{label}+` token per positive order:
    `Campylobacter+` / `E. coli O157:H7+` / `Salmonella/Shigella+` in that
    order . Negative members are not reported.
36b. **Stool parasites**. One `stool {label} neg` token per present
    negative order -- `stool O-P neg` / `stool Giardia neg` /
    `stool Cryptosporidium neg` in that order; one `{label}+` token per
    positive order, `O-P+` / `Giardia+` / `Cryptosporidium+`. Negative
    members are not reported next to a positive one.
36c. **C. diff**. `C diff neg` or `C diff+`.
37. **AFP**. If both `eAg/AFP neg` then emit grouped.
    Else `AFP nl` or `AFP {val}({bound})`.
38. **CEA**. `CEA nl` or `CEA {val}`.
39. **CA 125**. `CA 125 nl` or `CA 125 {val}({bound})`.
40. **CA 19-9**. `CA 19-9 nl` or `CA 19-9 {val}({bound})`.
41. **LDH**. `LDH nl` or `LDH {val}({bound})`.
42. **QTB**. `QTB neg` or `QTB+`.
42a. **Shield** (Guardant Shield colorectal-cancer blood test).
    `Shield blood test neg` or `Shield blood test+` from the `SHIELD CRC
    BLOOD TEST` item's value (the `SHIELD ID` item is the sample ID, not
    a result).
43. **ABO / Rh**. `ABO {group}{rho}` eg `ABO A+`.
44. **Allergy**. The panel's items are grouped by their code tag's letter:
    `M` mold, `D` dust mite, `E` cat/dog dander, `T` / `W` / `G` tree / weed /
    grass pollen and `F` food. The negative groups are joined eg
    `allergy mold/dust mite/pollen neg`. Each positive group gets one
    `{group} {val}+({bound})` token, the group's highest positive
    value.

A row that matches no rule above produces no token.
We don't have rules for orders with no results in the db: DHEA, troponin,
D-dimer, ANCA.

The leading date is `mm/yyyy` (zero-padded month) of the newest result.
"""

import json
import math
import re
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from summary_ct import ct_label, ct_token, ct_findings
from summary_us import us_label, us_token, us_findings

_PLT_ITEMS = frozenset({"platelet count", "platelets"})

# Glucose item per vendor (lower-cased): Quest's CMP items spell it
# `GLUCOSE`, LabCorp's (on the in-house CMP) `Glucose, Serum`; the
# standalone hepatic function panels carry no glucose item.  The
# value joins the A1c token as `Glu {val}/A1c {val}`.
_GLUCOSE_ITEMS = frozenset({"glucose", "glucose, serum"})

# Quest: REACTIVE / NON-REACTIVE, LabCorp: Positive / Negative.
_POSITIVE_VALUES = frozenset({"reactive", "positive"})

_NEGATIVE_VALUES = frozenset(
    {"negative", "non-reactive", "non reactive",
     "hiv negative", "not detected"})

# The HAV total-Ab values meaning no confirmed HAV immunity (the
# yellow notes say `RTC HAV vacc`). Quest's `BORDERLINE` counts:
# it does not confirm immunity (like the MMR equivocal bands), and
# the HAV vaccine is safe on an already-immune patient.
_HAV_SUSCEPTIBLE = frozenset(
    {"non-reactive", "negative", "borderline"})

# In-house orders report their allergens as `... IGE` items named `{ALLERGEN} ({CODE}) IGE`
# LabCorp's `Allergy Profile, Food` panel reports `{CODE}-IgE {ALLERGEN}` items (eg `F014-IgE Soybean`). We ignore the `CLASS` / `Class Description` items.
# Code: M mold, D dust mite, E animal dander, T/W/G tree/weed/grass pollen, F food. 
# LabCorp items' range field carries their IgE class label (`Class 0/I`)
_ALLERGY_NAMES = [
    "allergy evaluation 9, northwest",
    "respiratory allergy profile region xvii",
    # in-house panel: code-tagged `D001-IgE ...` items (letter = group)
    "allergy respiratory",
]

# Category key -> row names.  The three hep B/C categories are
# separate so the HBV/HCV group of the STD token can require the
# surface-Ag and HCV Ab screen rows to be present and normal
# (the surface-Ab row's result is not consulted).
_CATEGORY_NAMES = {
    "ua": [
        "ua, routine",  # LabCorp
        "urinalysis, complete",  # LabCorp. Includes a manual-microscopy block.
        "ua, urine routine",  # Quest
        "urinalysis reflex",  # in-house
    ],
    "ucx": [
        # LabCorp, has items `Urine Culture, Routine` report and `Result 1`
        "culture urine, routine",
        "culture, urine, routine",  # in-house with one item named after order
        "urine reflex to culture",  # Quest, REFLEXIVE URINE CULTURE
        "ua/m w/rflx culture, routine",  # LabCorp
    ],
    "hcg": [
        "hcg, total, qn",  # Quest, mIU/mL
        "hcg, ql, urine",  # Quest/in-house, NEGATIVE / POSITIVE
    ],
    "cbc": [
        "cbc (includes diff/plt)",
        "cbc with differential/platelet",
        "cbc/diff ambiguous default",  # LabCorp
    ],
    "plt_est": ["platelet estimation"],  # in-house, ADEQUATE / DECREASED
    "tsh": [
        "tsh w/reflex to ft4",
        "tsh reflex to t4f",
        "tsh+free t4",
        "tsh rfx on abnormal to free t4",
        "tsh",  # standalone, both vendors, single `TSH` item
        "thyroid cascade profile",  # LabCorp, has `TSH` item and interp note
    ],
    "t3": [
        "free t3",  # Quest, reports "T3, FREE"
        "free t3, serum",  # LabCorp, reports "Triiodothyronine,Free,Serum"
    ],
    "t4": ["free t4"],  # reports _T4_ITEMS
    "tpo": [
        "thyroid peroxidase (tpo) ab",  # LabCorp
        "thyroid antibodies",  # LabCorp, also adds Thyroglobulin Antibody
        # Quest, `THYROID PEROXIDASE$ ANTIBODIES` and `THYROGLOBULIN ANTIBODIES` items
        "thyroid peroxidase and thyroglobulin antibodies",
    ],
    "tgab": [
        "thyroid antibodies",
        "thyroid peroxidase and thyroglobulin antibodies",
        "thyroglobulin antibody",
        "thyroglobulin antibodies",
    ],
    "tsi": [
        # Quest: `Thyroid Stim Immunoglobulin` item in IU/L, 0.00-0.55
        "thyroid stim immunoglobulin",
        # Quest: TSI item in % baseline, >= 140 is positive
        "tsi (thyroid stimulating immunoglobulin)",
    ],
    "a1c": ["hemoglobin a1c"],
    "glu": ["glucose", "glucose, serum"],
    "lipid": [
        "lipid panel",
        "lipid panel with ratios",
        "lipid panel with reflex to direct ldl",
        "lipid panel with ratios (refl)",
        "lipid panel with ldl/hdl ratio",
        "lipid _ cardio iq(r) advanced lipid panel",
        "lipid panel+apob",  # same layout as LapCorp lipid panel
    ],
    "lpa": [  # from CARDIO IQ panel and standalone order
        "lipoprotein (a)",
        "lipid _ cardio iq(r) advanced lipid panel",
    ],
    "apob": [
        "lipid _ apolipoprotein b", "lipid_ apolipoprotein b",
        "lipid _ cardio iq(r) advanced lipid panel",
        "lipid panel+apob",
    ],
    "vitd": ["vitamin d,25-oh,total,ia", "vitamin d, 25-hydroxy"],
    "pth": ["pth, intact without calcium", "pth, intact"],
    "ica": ["calcium, ionized, serum", "calcium, ionized"],
    "mg": ["magnesium"],
    "mg_rbc": ["magnesium, rbc"],
    "phos": ["phosphorus, serum", "phosphorus"],
    "zinc": ["zinc, plasma or serum", "zinc"],
    "zinc_rbc": ["zinc, rbc"],
    "fsh": ["fsh, serum", "fsh"],
    "estradiol": ["estradiol"],
    "testo": [
        "testosterone, free,bio and total, lc/ms/ms",
        "testosterone,free and total",
        "testosterone  total/free",
        "testosterone, total, males (adult),ia (refl)",
    ],
    "cortisol": ["cortisol, a.m."],  # reference range is in paramNotes
    "prolactin": ["prolactin"],  # reference range is in paramNotes
    "lh": [
        # in-house with single `LH` item. Phase-dependent ref range in paramNotes
        "lh hormone",
        "lh, serum",
        "lh (luteinizing hormone)",
    ],
    # reference range is in paramNotes (depends on follicular / luteal phases)
    "progesterone": ["progesterone"],
    "amh": [
        # in-house, reports "ANTI-MULLERIAN HORMONE (AMH), FEMALE"
        "infertility _ amh _ anti-mullerian hormone",
        # labcorp, reports Anti-Mullerian Hormone (AMH)
        "amh _ anti-mullerian hormone",
    ],
    "metanephrine": [
        # LabCorp `Metanephrines, Frac., Pl. Free`:
        # `Normetanephrine, Pl` / `Metanephrine, Pl` items, pg/mL
        "metanephrines, frac., pl. free",
    ],
    "uric": ["uric acid, serum", "uric acid"],
    "psa": [
        "psa, total",
        "psa",
        "psa total (reflex to free)",
        "psa total+% free",
    ],
    "inrpt": [
        "inr",  # "PT" and "INR" items
        "inr /pt",  # "INR" and "Prothrombin Time" items
         "prothrombin w/inr + partial thromboplastin times"  # obth plus "PTT" item
     ],
    "ptt": ["ptt", "prothrombin w/inr + partial thromboplastin times"],
    "bnp": ["bnp"],
    "hpylori": [
        "h pylori, urea breath test",
        "h pylori breath test",
        "h pylori ag, eia, stool",  # usually pending, no value
        "h. pylori breath collection",  # usually pending, no value
    ],
    "stool": ["stool occult", "stool occult blood"],
    "stool_cx_campy": ["stool culture - campylobacter"],
    "stool_cx_ecoli": ["stool culture for ecoli o157:h7"],
    "stool_cx_salm": ["salmonella and shigella, culture"],
    "stool_ova": [
        # Quest has one `OVA AND PARASITES,$CONC AND PERM SMEAR` item
        # result note has the result lines (CONCENTRATION 1: ..., TRICHROME 1: ...)
        "stool ova and parasite",
        # LabCorp, "Final report" item plus "Result 1" item
        "stool ova + parasite exam",
    ],
    "stool_giardia": ["stool giardia ag, eia"],
    "stool_crypto": ["stool cryptosporidium ag, eia"],
    # Only item `CLOSTRIDIUM DIFFICILE$TOXIN/GDH W/REFL TO PCR` has empty val.
    # Result note has GDH / Toxin A and B lines and
    # `No toxigenic C. difficile detected`.
    "stool_cdiff": [
        "stool c-diff toxin",
        # LabCorp, single `C difficile Toxins A+B, EIA` item
        "stool c-diff toxin, eia",
    ],
    "albcr": [
        "microalb/creat ratio, randm ur",
        "microalbumin, random urine (w/creatinine)",
    ],
    "hav": ["hep a total ab", "hep a ab, total"],
    "hav_igm": ["hav igm", "hep a ab, igm"],
    "measles": [
        "measles _ rubeola, igg",
        "measle _ rubeola _ igg",
        "mmr (igg) panel (measles, mumps, rubella)",
        "mmr",
    ],
    # Quest and LabCorp
    "mumps": ["mmr (igg) panel (measles, mumps, rubella)", "mmr"],
    "rubella": [
        "rubella immune status",
        "rubella antibodies, igg",
        "mmr (igg) panel (measles, mumps, rubella)",
        "mmr",
    ],
    "varicella": [
        "varicella zoster virus antibody (igg)",
        "varicella-zoster v ab, igg",
        "varicella zoster virus antibodies (igg,igm)",  # LabCorp combo
    ],
    "iron": [
        "iron and tibc",
        "iron, tibc and ferritin panel",
        "iron and total iron binding capacity",
    ],
    "ferritin": ["ferritin", "ferritin, serum"],
    "iron_standalone": ["iron", "iron, serum"],
    "b12": [
        "vitamin b12",
        "vitamin b12/folate, serum panel",
        "vitamin b12 and folate",
    ],
    "b1": [
        # reports "Vit. B1, Whole Blood" in nmol/L
        "vitamin b1 (thiamine), blood",
        # Quest, reports "VITAMIN B1 (THIAMINE)," (sic) in nmol/L
        "vitamin b1 (thiamine), serum/plasma, lc/ms/ms",
    ],
    "b6": ["vitamin b6, plasma"],
    # Quest item name is `VITAMIN B2 (RIBOFLAVIN),` with trailing comma
    "b2": ["vitamin b2 (riboflavin), plasma"],
    "fa": [
        "vitamin b12/folate, serum panel",
        "vitamin b12 and folate",
    ],
    "liver": [
        "cmp",
        "bmp",
        "hepatic function panel",
        "hepatic function panel (7)",
    ],
    "ggt": ["ggt"],
    # Quest and LabCorp respectively
    "ck": ["creatine kinase, total", "creatine kinase, total,serum"],
    "copper": ["copper"],
    "amylase": [
        "amylase",
        # LabCorp, single `Amylase, Serum` item
        "amylase, serum",
    ],
    "lipase": ["lipase", "lipase, serum"],
    "ana": [
        "antinuclear antibodies   titer and pattern",  # Quest, sic
        "antinuclear antibodies, ifa",
        "antinuclear antibody",
        "ana screen",
        "ana screen, ifa, w/refl titer and pattern",
        "ana scr, ifa, w/refl titer/pattern/rheumatoid arthritis panel 1",
    ],
    "esr": [
        "esr",
        "sed rate",
        "erythrocyte sedimentation rate",
    ],
    "crp": ["crp", "crp, quant"],
    "rf": [
        "rheumatoid factor",  # Quest
        # LabCorp, has RF item of same name plus CCP and ANA items
        "ana scr, ifa, w/refl titer/pattern/rheumatoid arthritis panel 1",
    ],
    "ccp": [
        "anti-ccp abs",  # Quest
        # LabCorp
        "ana scr, ifa, w/refl titer/pattern/rheumatoid arthritis panel 1",
    ],
    "c3c4": ["complement comp c3 + c4"],
    "dsdna": ["anti ds-dna"],
    # single `C-Reactive Protein, Cardiac` item in mg/L.
    # cardiac risk: low <1.00, average 1.00-3.00, high >3.00.
    "crp_cardiac": [
        "crp, cardiac",
        # in-house, single `HS CRP` item
        "crp hs",
    ],
    "afp": [
        "afp",
        "afp, serum, tumor marker",
        "alpha fetoprotein, tumor marker",  # Quest
    ],
    "cea": ["cea"],
    "ca125": ["ca 125", "ca-125"],
    "ca199": ["ca 19-9"],
    "ldh": ["ldh"],  # only item is LabCorp `LDH` or Quest `LD`
    "qtb": [
        "quantiferon-tb gold plus",
        "quantiferon(r)-tb gold plus, 1 tube",
    ],
    "shield": ["guardant shield colorectal cancer blood"],
    "abo": [
        # LabCorp, reports "ABO Grouping" -> A/B/AB/O,
        # "Rh Factor" -> Positive / Negative
        "abo grouping and rho(d) typing",
        # Quest, reports "ABO GROUP" and "RH TYPE"
        # (`RH(D) POSITIVE` / `RH(D) NEGATIVE`)
        "abo group and rh type",
    ],
    "allergy_mold": _ALLERGY_NAMES + ["allergy mold panel, complete"],
    # two mite IgG4 orders report the mite item code-less
    "allergy_mite": _ALLERGY_NAMES + [
        "allergy _ d farinae mite igg4*",
        "allergy  _ d pteronyssinus mite igg4*",
        # in-house single-mite orders (`D003-IgE D microceras`,
        # `D070-IgE Acarus Mite` items)
        "allergy ige acarus mite",
        "allergy _ d003-d. microceras (mite)",
    ],
    "allergy_animal": _ALLERGY_NAMES + ["allergy _ cat ige"],
    # tree / weed / grass items. No standalone order.
    "allergy_pollen": _ALLERGY_NAMES,
    "allergy_food": _ALLERGY_NAMES + [
        "food allergy panel (refl)",
        "food allergy profile with reflexes",
        "allergy profile, food",
    ],
    "hcv": [
        # LabCorp. `Interpretation:` note and `HCV Ab` result items.
        "hep c ab rfx to quant pcr",
        # Quest
        "hep c ab reflex to rna, qn, pcr",
        # Quest. Single `HEPATITIS C ANTIBODY` item.
        "hepatitis c ab w/rfl rna, pcr w/rfl genotype,lipa",
    ],
    "hbsag": ["hep b surface ag"],
    "hbsab": ["hep b surface ab"],
    "hbsabq": ["hep b surf ab quant"],
    "hiv": [
        "hiv 1/2 ag/ab, 4th generation",
        "hiv",
        "hiv-1/hiv-2 qualitative rna",  # LabCorp
    ],
    "rpr": [
        "rpr (dx) w/ confirmatory",
        "rpr",
        "rpr, rfx qn rpr/confirm tp"
    ],
    "hsv": [
        # Quest. `HSV 1/2 IGG TYPE SPECIFIC$AB` index items
        "hsv 1/2 igg, herpeselect w/refl hsv2 inhibition",
        # LabCorp. `HSV N IgG, Type Spec` Reactive / Non Reactive items.
        "hsv 1 and 2 ab, igg",
    ],
    "gc": [
        # `CHLAMYDIA TRACHOMATIS` / `NEISSERIA GONORRHOEAE` items
        "chlamydia / gc urine",
        # LabCorp. `... , NAA` items (Negative / Positive values)
        "chlamydia/gc amplification",
        # Quest. `$RNA, TMA` items (NOT DETECTED / DETECTED values)
        "chlamydia/n. gonorrhoeae rna, tma",
        # Quest
        "chlamydia trachomatis rna, tma",
        # in-house chlamydia-only order: the `CHLAMYDIA TRACHOMATIS,TMA`
        # item of the alternate-target reflex re-test
        "chlamydia trachomatis, tma (alternate target)",
    ],
    "treponema": ["treponema pallidum ab"],
    # results are `NOT DETECTED`, `<10 DETECTED`, or IU/mL number.
    "hbv_dna": [
        "hep b dna, pcr",
        "hbv dna",
        "hep b real-time pcr, quant",
        "hbv rt pcr, quant (graph)",
        # LabCorp, `Hepatitis B Quantitation` (linear) + `HBV log10` items
        "hbv dna realtime abbott",
    ],
    "hcv_rna": [
        "hcv rna, quantitative real time pcr",
        "hcv rna, quantitative real time pcr",
        "hcv rt-pcr, quant (non-graph)",
    ],
    "eag": [
        "hep b eag",  # Quest, item "HEPATITIS BE ANTIGEN"
        "hep be ag",  # LabCorp
    ],
    "hbcab": ["hep b core ab", "hep b core ab, tot"],
    "hdv": [
        "hep d antibody",  # Quest, `HEPATITIS D ANTIBODY,` (sic)
        "hepatitis d antibody, igg/igm"  # LabCorp, `HDV Antibody, IgG/IgM`
    ],
    "hb_elec": ["hb electrophoresis"],
    "htlv": ["htlv-i/ii antibodies, qual"],  # LabCorp
}


_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
def _first_num(s: str) -> float | None:
    if m := _NUMBER_RE.search(s):
        return float(m.group())


def _parse_items(result):
    """Parse a row's `result` JSON into a list of item dicts.

    Returns `None` when the row has no usable result.
    Items are normalised to `{"name": str, "value": str, "flag": str | None,
    "range": str, "units": str, "notes": str}` with "" for missing values.
    Item names are lower-case matched throughout, and the interface's `$`
    separator (lab_results_json; the 'By Patient (All)' screen renders it as
    a space) is normalised to a space so rows written by either
    update_lab_result() / update_patient_labs() match the same names.
    """
    if not result:
        return None
    try:
        data = json.loads(result)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(data, list):
        return None
    items = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        item_name = entry.get("itemName")
        if item_name is None:
            continue
        value = entry.get("value")
        rng = entry.get("range")
        notes = entry.get("paramNotes")
        items.append({
            "name": str(item_name).replace("$", " "),
            "value": "" if value is None else str(value),
            "flag": entry.get("flag"),
            "range": "" if rng is None else str(rng),
            "units": str(entry.get("units") or ""),
            "notes": "" if notes is None else str(notes),
        })
    return items or None


def _is_abnormal(flag):
    """True when an item flag marks the item abnormal."""
    if flag is None:
        return False
    return str(flag).strip().lower() not in ["", "n"]


def _abnormal_items(items):
    """The abnormal items of a parsed result, in report order."""
    return [it for it in items if _is_abnormal(it["flag"])]


def _bound_for(flag, rng):
    """The reference-range limit a flagged value violates, rendered
    without trailing zeros (``<75.0`` -> ``75``, ``16-77`` + ``H`` ->
    ``77``, ``2.5-10.2`` + ``L`` -> ``2.5``).  ``None`` when the
    range has no parsable limit for the flag: an empty range, an
    ``A`` flag on a two-sided range, or a one-sided bound in the
    other direction (an ``H`` flag on ``>39``).  Multi-letter
    direction flags (``HH`` / ``LL``, which Quest sends on some CBC
    rows, e.g. its high-RBC ``HH`` in ``4.14-5.80``) are read by
    their last letter, like the single-letter ones.
    """
    rng = rng.strip()
    if not rng:
        return None
    # The direction letter; `A` and the empty flag are undirected.
    last = flag[-1].upper() if flag else ""
    if rng.startswith("<"):
        # One-sided upper limit; violated by a high (or an
        # undirected abnormal) flag.  The bound's number is parsed
        # out, so both `<75.0` and `< OR = 75` render `75`.
        part = rng if last in "HA" else None
    elif rng.startswith(">"):
        # One-sided lower limit; violated by a low flag.
        part = rng if last in "LA" else None
    elif "-" in rng:
        lo, hi = (part.strip() for part in rng.split("-", 1))
        part = hi if last == "H" else (lo if last == "L" else None)
    else:
        part = None
    if part is None:
        return None
    num = _first_num(part)
    return None if num is None else f"{num:g}"


def _first_item(items, names):
    for item in items:
        if item["name"].strip().lower() in names:
            return item


def _item_value(item):
    return item["value"].strip() if item else None


def _first_value(items, names):
    return _item_value(_first_item(items, names))


def _normalize_flag(item):
    return str(item["flag"] or "").strip().upper()


def _is_usable_abnormal(item):
    return (
        item is not None
        and _is_abnormal(item["flag"])
        and bool(item["value"].strip())
    )


def _val_bound(label, it, fmt, sign=True):
    """`{label} {val}({bound})` for one flagged item: the value via
    `fmt` when given (Cr writes its raw value, CrCl via `%g`), the
    bound via `_bound_for` (a plain `{label} {val}` when unparseable).
    A high value (see `_value_above`) gains a `+` on the value when
    `sign` is set, eg `INR 2.1+(1.1)`."""
    value = it["value"].strip()
    shown = fmt(value) if fmt is not None else value
    if sign and _value_above(it):
        shown += "+"
    bound = _bound_for(str(it["flag"] or "").strip().upper(), it["range"])
    if not bound:
        return f"{label} {shown}"
    return f"{label} {shown}({bound})"


def _format_token(label, rendered, bound=None):
    return f"{label} {rendered}({bound})" if bound else f"{label} {rendered}"


def _item_bound(item):
    return _bound_for(_normalize_flag(item), item["range"])


def _named_item_token(items, names, label, fmt, sign=True):
    """Format the first matching item in `items` if it is abnormal and non-empty;
    return `None` otherwise (including when the first name match is normal).
    A high value (see `_value_above`) gains a `+` on the value when
    `sign` is set, eg `Mg 6.5+(6.4)`, `albumin 5.4+(5.1)`."""
    item = _first_item(items, names)
    if not _is_usable_abnormal(item):
        return None
    rendered = fmt(item["value"].strip())
    if sign and _value_above(item):
        rendered += "+"
    return _format_token(label, rendered, _item_bound(item))


def _named_flag_token(items, names, label, fmt=None, sign=True):
    """`{label} nl` if normal else `{label} {val}({bound})` (a high
    value gains a `+` on the value when `sign` is set)."""
    item = _first_item(items, names)
    if item is None:
        return None
    if not _is_abnormal(item["flag"]):
        return f"{label} nl"
    raw_value = item["value"].strip()
    if not raw_value:
        return None

    rendered = fmt(raw_value) if fmt is not None else raw_value
    if sign and _value_above(item):
        rendered += "+"
    return _format_token(label, rendered, _item_bound(item))


def _flag_token(label, items, fmt=None, sign=True):
    """`{label} nl` if normal or `{label} {val}({bound})` (a high
    value gains a `+` on the value when `sign` is set)."""
    it = items[0]
    if not _is_abnormal(it["flag"]):
        return f"{label} nl"
    value = it["value"].strip()
    if not value:
        return None
    shown = fmt(value) if fmt is not None else value
    if sign and _value_above(it):
        shown += "+"
    bound = _bound_for(str(it["flag"] or "").strip().upper(), it["range"])
    if not bound:
        return f"{label} {shown}"
    return f"{label} {shown}({bound})"


def _ua_ph_token(value):
    """The `pH` shorthand for an abnormal pH value (see the module
    docstring): the value's number (trailing zeros stripped) with the
    value's own comparison (`< OR = 5.0` -> `pH<5`, `> OR = 8.0` ->
    `pH>8`, `4.5` -> `pH 4.5`); a non-numeric value is written out
    raw.  None when the value is empty."""
    value = value.strip()
    num = _first_num(value)
    if num is not None:
        num = f"{num:g}"
        if "<" in value:
            return f"pH<{num}"
        if ">" in value:
            return f"pH>{num}"
        return f"pH {num}"
    return f"pH {value}" if value else None


# item ranges are `NONE OR FEW` / `NONE SEEN`
# LabCorp uses `NOSEE`
_UA_MICRO_ABSENT = frozenset(
    {"", "none", "none seen", "nosee", "absent", "negative", "few"})


# The WBC count range whose upper bound at or below this is not a
# finding: the tech reports `6-10` for a count just above the `0-5`
# reference (MRN 13976), which is not significant pyuria.
_UA_WBC_CUTOFF = 10


def _micro_count_absent(name, value):
    """True when a microscopy count item's value is not a finding: an
    absent text (`None seen` / `NOSEE`, ...), a count range starting
    at 0 (`0-5` -- the tech could not confirm a presence), or -- for
    WBC only -- a range at or below `_UA_WBC_CUTOFF` (`6-10`)."""
    if value.lower() in _UA_MICRO_ABSENT:
        return True
    m = re.match(r"\s*(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*$", value)
    if m:
        if not float(m.group(1)):
            return True
        if name == "wbc" and float(m.group(2)) <= _UA_WBC_CUTOFF:
            return True
    return False


# Item names that are not reported at any value: the
# contamination-artifact `squamous epithelial cells`, the
# `Microscopic Examination` section header, and `specific gravity` /
# `appearance` (dilute-sample / clarity readings) and WBC esterase at
# any level (Quest: `leukocyte esterase`).
_UA_IGNORED_NAMES = frozenset({
    "squamous epithelial cells",
    "microscopic examination",
    "specific gravity",
    "appearance",
    "wbc esterase",
    "leukocyte esterase",  # Quest's name for WBC esterase
})

# The ignored (item name, lower-cased value) pairs: benign readings
# that are not reported.
_UA_IGNORED = frozenset({
    ("ketones", "trace"),
    ("ketones", "2+"),
    ("occult blood", "trace"),
    ("occult blood", "1+"),
    ("bacteria", "few"),
})

# The microscopy count items whose absent / `0-x` values are not a
# finding (see `_micro_count_absent`).
_UA_MICRO_COUNT_ITEMS = frozenset(
    {"wbc", "rbc", "epithelial cells (non renal)",
     "epithelial cells (renal)"})


def _ua_token(items):
    """Token for a UA result: `UA nl`, or `UA ` + the abnormal items
    in report order as short tokens (see the module docstring):
    `pH<5`-style for pH, `crystals+` for an abnormal crystals item, and
    `{name} {value}` in lower case (a `trace` value gains a `+`) for
    the rest.  The ignored items (at any value) and the ignored
    (item, value) pairs are not reported, nor are the microscopy count
    items' absent / `0-x` values, nor WBC's at-or-below-cutoff range
    (`6-10`)."""
    parts = []
    for it in _abnormal_items(items):
        name = it["name"].strip().lower()
        value = it["value"].strip()
        if name in _UA_IGNORED_NAMES:
            continue
        if (name, value.lower()) in _UA_IGNORED:
            continue
        if name in _UA_MICRO_COUNT_ITEMS and _micro_count_absent(name, value):
            continue
        if "crystals" in name:
            if value.lower() not in _UA_MICRO_ABSENT:
                parts.append("crystals+")
            continue
        if name == "ph":
            token = _ua_ph_token(value)
            if token:
                parts.append(token)
            continue
        if value.lower() == "trace":
            value = "trace+"
        else:
            value = value.lower()
        parts.append(f"{name} {value}" if value else name)
    if not parts:
        return "UA nl"
    return "UA " + ", ".join(parts)


def _ucx_token(items):
    """Return `Ucx neg` for negative urine-culture results, `Ucx {value}`
    for other non-empty values, or None."""
    names = ["result 1", "culture, urine, routine", "reflexive urine culture"]
    if value := _first_value(items, names):
        if value.lower() in ["no growth", "none", "negative"]:
            return "Ucx neg"
        return f"Ucx {value}"


def _hcg_token(items):
    """The pregnancy-test token (rule 1b): `HCG neg` when negative /
    non-reactive (the urine qualitative test's `NEGATIVE` value; the
    serum quantitative test's below-cutoff value -- its reference
    range sits in the item's paramNotes, so an unflagged numeric
    value or a `<5`-style value is below it) and `HCG+` when
    positive / reactive (a positive serum value is flagged H); a
    pending / empty value produces nothing."""
    it = items[0]
    value = it["value"].strip()
    if not value:
        return None
    low = value.lower()
    if low in _POSITIVE_VALUES:
        return "HCG+"
    if low in _NEGATIVE_VALUES:
        return "HCG neg"
    if _is_abnormal(it["flag"]):
        return "HCG+"
    if re.search(r"\d", value) or value.startswith("<"):
        return "HCG neg"


def _round1(value):
    """Round to one decimal, half up (6.85 -> 6.9)."""
    try:
        rounded = Decimal(value.strip()).quantize(
            Decimal("0.1"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return value
    return f"{rounded:f}"


def _g(value):
    """Strip trailing zeros"""
    try:
        return f"{float(value):g}"
    except ValueError:
        return value


def _b6_value(value):
    """Round to integer above 10, else two sig figs eg 3.4."""
    try:
        num = float(value.strip())
    except ValueError:
        return value
    return f"{num:.0f}" if abs(num) >= 10 else f"{num:.2g}"


def _cbc_mcv_token(items):
    """Return `MCV {val}({bound})` or `MCV {val}` for an abnormal MCV item
    with a non-empty value. Returns `None` if missing, normal, or empty.
    """
    item = _first_item(items, ["mcv"])
    if not _is_usable_abnormal(item):
        return None

    shown = _int_value(item["value"].strip())
    if _value_above(item):
        shown += "+"
    raw_bound = _item_bound(item)
    bound = _int_value(raw_bound) if raw_bound else None
    return _format_token("MCV", shown, bound)


def _plt_est_token(items, cbc_plt_token):
    """`plt est {value}` (lower-cased, eg `plt est decreased`) for an
    abnormal platelet estimation (rule 10d; the in-house order's
    single item reports `ADEQUATE` / `DECREASED`): a `DECREASED`
    value, flagged or not, or a flagged value, yields the token; a
    normal / pending / empty value yields nothing.  `cbc_plt_token`
    is the newest CBC's rule 10b `Plt` token: when it is not `None`
    the measured count already reports the abnormality and the
    estimate is suppressed."""
    if cbc_plt_token is not None:
        return None
    it = items[0]
    value = it["value"].strip()
    if not value:
        return None
    if value.lower() != "decreased" and not _is_abnormal(it["flag"]):
        return None
    return f"plt est {value.lower()}"


def _liver_electrolyte_tokens(items):
    """The liver panel's electrolyte tokens (rule 30): one token per
    abnormal item, in the order Ca / Na / Cl / CO2 / K, `{label}
    {val} ({bound})` (the value's trailing zeros stripped via `%g`,
    the bound via `_bound_for`; a plain `{label} {val}` when
    unparseable) -- e.g. `Ca 10.3+(10.2), Na 134(136), Cl 109(107),
    K 6+(5.1)` (a high Ca / Na / K is signed; Cl / CO2 mark a high
    with the bound only) -- and nothing for the normal items, like BUN / Cr.
    CO2 is the panel's carbon-dioxide (bicarbonate) item."""
    tokens = []
    # Quest and LabCorp respectively; Cl / CO2 mark a high with the
    # bound only (no `+`), like BUN / Cr
    elec_specs = [
        (["calcium", "calcium, serum"], "Ca", True),
        (["sodium", "sodium, serum"], "Na", True),
        (["chloride", "chloride, serum"], "Cl", False),
        (["carbon dioxide", "carbon dioxide, total"], "CO2", False),
        (["potassium", "potassium, serum"], "K", True),
    ]
    for names, label, sign in elec_specs:
        token = _named_item_token(items, names, label, _g, sign)
        if token:
            tokens.append(token)
    return tokens


def _cr_token(items):
    """Combined or single `Cr` / `CrCl` token for abnormal items.

    Quest's race-paired eGFR layouts report two eGFR items and flag abnormal
    only the race-appropriate one, so get the first abnormal eGFR item with a
    non-empty value.

    A low Cr (`L` flag) suppresses the whole token, unless the eGFR is also
    abnormal (then the combined token is kept unchanged); a low CrCl is kept
    (as is a high Cr paired with a low CrCl).
    """
    # Quest and LabCorp respectively
    cr = _first_item(items, ["creatinine", "creatinine, serum"])

    # Race-paired eGFR layouts report two entries and flag only the active one;
    # prefer a non-empty abnormal entry before falling back to the first listed.
    names = [
        "egfr",
        "egfr african american", "egfr non-afr. american",
        "egfr if africn am", "egfr if nonafricn am",
    ]
    egfrs = [item for item in items if item["name"].strip().lower() in names]
    egfr = next(
        (item for item in egfrs if _is_usable_abnormal(item)),
        egfrs[0] if egfrs else None,
    )

    cr_abn = _is_usable_abnormal(cr)
    egfr_abn = _is_usable_abnormal(egfr)

    if not cr_abn and not egfr_abn:
        return None
    # A low Cr (L flag) suppresses the whole Cr token when the eGFR is
    # normal; with an abnormal eGFR the combined token is kept unchanged
    if cr_abn and not egfr_abn and str(cr["flag"]).strip().upper()[-1] == "L":
        return None
    if cr_abn and not egfr_abn:
        return _val_bound("Cr", cr, None, sign=False)
    if egfr_abn and not cr_abn:
        return _val_bound("CrCl", egfr, _g, sign=False)

    egfr_flag = str(egfr["flag"] or "").strip().upper()
    cr_flag = str(cr["flag"] or "").strip().upper()
    bound = _bound_for(egfr_flag, egfr["range"]) or _bound_for(cr_flag, cr["range"])

    cr_val = cr["value"].strip()
    egfr_val = _g(egfr["value"].strip())
    token = f"Cr/CrCl {cr_val}/{egfr_val}"
    return f"{token}({bound})" if bound else token


def _t4_item(items):
    """The free-T4 item of a TSH result, or None.

    Matches `T4, FREE` (the `TSH+FREE T4` layout), `T4F` / `Free
    T4` (LabCorp's reflex T4F item), `T4,Free (Direct)` (the `TSH
    RFX ON ABNORMAL TO FREE T4` layout) and `FT4` (Quest's reflex
    item); the TSH item of `TSH W/REFLEX TO FT4` is not it (its only
    `t4` sits inside `ft4`).
    """
    for it in items:
        name = it["name"].strip().lower()
        if name == "ft4" or re.search(r"(?<![a-z])t4", name):
            return it
    return None


def _t4_suffix(t4):
    if t4 is None:
        return ""
    t4_value = t4["value"].strip()
    if not t4_value:
        return ""
    if not _is_abnormal(t4["flag"]):
        return "/T4 nl"
    shown = t4_value
    if bound := _item_bound(t4):
        # a high T4 is marked by its bound, not a `+` (like TSH)
        shown = f"{shown}({bound})"
    return f"/T4 {shown}"


_T4_ITEMS = frozenset({
    "t4, free",  # Quest
    "t4,free(direct)",  # LabCorp
})

# TSH item names per vendor layout: the standalone / `TSH+FREE T4` /
# thyroid-cascade `TSH` item and Quest's `TSH W/REFLEX TO FT4` item.
# The free-T4 item may come first in report order (LabCorp's `TSH
# reflex to T4F` layout), so the TSH item is matched by name, not
# taken as the order's first item.
_TSH_ITEMS = frozenset({"tsh", "tsh w/reflex to ft4"})


def _tsh_token(latest):
    """Return `TSH {val:.1f}` (or raw `TSH {val}` if non-numeric) from
    the TSH item of `latest["tsh"]` (matched by name; a result whose
    layout leads with its free-T4 item, like LabCorp's `TSH reflex to
    T4F`, would otherwise report the T4 as the TSH), an abnormal value
    gaining its violated bound (`TSH 9.7(4.5)`; a plain value when the
    range is unparseable), with an optional `/T4 nl` or `/T4 {val}` or
    `/T4 {val}({bound})` suffix from a matching free-T4 item in `items`
    or `latest["t4"]`.
    TSH / T4 highs are marked by the bound only, never a `+`.
    """
    items = latest["tsh"]
    tsh = _first_item(items, _TSH_ITEMS) or items[0]
    value = tsh["value"].strip()
    if not value:
        return None

    try:
        shown = f"{float(value):.1f}"
    except ValueError:
        shown = value
    if _is_abnormal(tsh["flag"]):
        if bound := _item_bound(tsh):
            shown = f"{shown}({bound})"
    token = f"TSH {shown}"

    t4 = _t4_item(items)
    if t4 is None and "t4" in latest:
        t4 = _first_item(latest["t4"], _T4_ITEMS)

    return token + _t4_suffix(t4)


_THYROID_MEMBERS = (
    ("t3", "T3", ("t3, free", "triiodothyronine,free,serum")),
    ("tpo", "TPO", ("thyroid peroxidase (tpo) ab", "thyroid peroxidase antibodies")),
    ("tgab", "thyroglobulin", ("thyroglobulin antibody", "thyroglobulin antibodies")),
    ("tsi", "TSI", ("thyroid stim immunoglobulin", "tsi")),
)


def _thyroid_cluster_tokens(latest):
    """Return normal (`{A}/{B} nl`) and abnormal (`{Label} {val}({bound})`)
    tokens for non-TSH thyroid members present in `latest`, in fixed order.

    Excludes `T4` when `tsh` is present in `latest` without its own T4 item
    (since `T4` joins the TSH token instead). Members with no usable item or
    value are omitted.
    """
    t4_joined = (
        "tsh" in latest
        and _t4_item(latest["tsh"]) is None
        and "t4" in latest
    )

    candidates = []
    if "t4" in latest and not t4_joined:
        candidates.append(("t4", "T4", _T4_ITEMS))
    candidates.extend(
        (category, label, names)
        for category, label, names in _THYROID_MEMBERS
        if category in latest
    )

    normal_labels = []
    abnormal_tokens = []
    for category, label, names in candidates:
        # a standalone T4 marks an abnormal value with its bound only,
        # like the T4 of the TSH token; the other members sign a high
        token = _named_flag_token(latest[category], names, label,
                                  sign=category != "t4")
        if token is None:
            continue
        if token.endswith(" nl"):
            normal_labels.append(label)
        else:
            abnormal_tokens.append(token)

    tokens = [f"{'/'.join(normal_labels)} nl"] if normal_labels else []
    tokens.extend(abnormal_tokens)
    return tokens


def _testo_tokens(items):
    """Return testosterone summary tokens for panel (`T`/`F`) or standalone
    total-testosterone results.
    """
    # standalone order does not have free testosterone
    testo_free_items = [
        "testosterone, free",
        "free testosterone(direct)",
        "free testosterone, serum",
    ]
    testo_total_items = [
        "testosterone, total, lc/ms/ms",
        "testosterone, serum",
        "testosterone, serum (total)",
        "testosterone, total,",
    ]
    if _first_item(items, testo_free_items) is None:
        item = _first_item(items, testo_total_items)
        if val := _item_value(item):
            shown = _g(val)
            if _value_above(item):
                shown += "+"
            return [f"testosterone {shown}"]
        return []

    normal_labels = []
    abnormal_tokens = []

    for label, names in (("T", testo_total_items), ("F", testo_free_items)):
        token = _named_flag_token(items, names, f"testosterone {label}")
        if token is None:
            continue
        if token.endswith(" nl"):
            normal_labels.append(label)
        else:
            abnormal_tokens.append(token)

    tokens = [f"testosterone {'/'.join(normal_labels)} nl"] if normal_labels else []
    tokens.extend(abnormal_tokens)
    return tokens


def _metanephrine_tokens(items):
    tokens = []
    found = False
    for label, names in (("normetanephrine", ("normetanephrine, pl",)),
                         ("metanephrine", ("metanephrine, pl",))):
        item = _first_item(items, names)
        if item is None:
            continue
        found = True
        if _is_abnormal(item["flag"]) and not item["value"].strip():
            # a pending abnormal result is no signal
            return []
        if _is_usable_abnormal(item):
            tokens.append(_val_bound(label, item, _g))
    if tokens:
        return tokens
    return ["metanephrine nl"] if found else []


def _a1c_token(items, glu=None):
    """`A1c {val}`. When `glu` is not None the token is instead `Glu
    {glu}/A1c {val}`."""
    it = items[0]
    value = it["value"].strip()
    if not value:
        return None
    a1c = f"A1c {_g(value)}"
    return a1c if glu is None else f"Glu {_g(glu)}/{a1c}"


_LDL_ITEMS = frozenset(
    {"ldl chol calc (nih)", "ldl-cholesterol", "ldl-c (nih calc)"})
_HDL_ITEMS = frozenset({"hdl cholesterol", "hdl-c"})
_TG_ITEMS = frozenset({"triglycerides"})

def _ldl_token(items):
    """`{hdl}/{ldl}/{tg}({bound})` if TG abnormal and both HDL and LDL exist,
    else `LDL {ldl}` if LDL has a value, else None.  A high component
    (LDL always, HDL / TG in the triplet) gains a `+` on its value,
    eg `60/132+/210+(150)`."""
    ldl = _first_item(items, _LDL_ITEMS)
    ldl_value = _item_value(ldl)
    if not ldl_value:
        return None

    ldl_shown = ldl_value + ("+" if _value_above(ldl) else "")

    tg = _first_item(items, _TG_ITEMS)
    if not _is_usable_abnormal(tg):
        return f"LDL {ldl_shown}"

    hdl = _first_item(items, _HDL_ITEMS)
    hdl_value = _item_value(hdl)
    if not hdl_value:
        return f"LDL {ldl_shown}"

    hdl_shown = hdl_value + ("+" if _value_above(hdl) else "")
    tg_shown = _item_value(tg) + ("+" if _value_above(tg) else "")
    panel_values = f"{hdl_shown}/{ldl_shown}/{tg_shown}"
    bound = _item_bound(tg)
    return f"{panel_values}({bound})" if bound else panel_values


def _hdl_token(items):
    """Return the `HDL` token when HDL is usable-abnormal and TG is not
    abnormal, else None."""
    tg = _first_item(items, _TG_ITEMS)
    if tg is not None and _is_abnormal(tg["flag"]):
        return None

    hdl = _first_item(items, _HDL_ITEMS)
    if not _is_usable_abnormal(hdl):
        return None

    shown = _item_value(hdl)
    if _value_above(hdl):
        shown += "+"
    return _format_token("HDL", shown, _item_bound(hdl))


def _albc_token(items):
    """Return `Alb/Cr<30` when no item in `items` is abnormal, or
    `Alb/Cr {val}` for the first ratio item when abnormal. Else None."""
    ratio = next((item for item in items if "ratio" in item["name"].lower()), None)
    if ratio is None:
        return None

    if not _abnormal_items(items):
        return "Alb/Cr<30"

    value = ratio["value"].strip()
    if not value:
        return None
    if _value_above(ratio):
        value += "+"
    return f"Alb/Cr {value}"


def _int_value(value):
    """A value rendered as an integer (`227.3` -> `227`, `42.2` ->
    `42`); an unparseable value is written out raw."""
    try:
        return f"{float(value):.0f}"
    except ValueError:
        return value


def _imaging_notes(result):
    if not result:
        return ""
    try:
        data = json.loads(result)
    except (TypeError, json.JSONDecodeError):
        return ""

    if not isinstance(data, list):
        return ""

    notes = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        note = str(entry.get("notes") or "").strip()
        if note:
            notes.append(note)

    return "\n".join(notes)


def _ct_cac_section(notes, *heads):
    """The text after `Head:` up to the next line-opening `Head:` or the end
    of the report. Case insensitive.
    """
    for head in heads:
        m = re.search(
            rf"^\s*{re.escape(head)}\s*:\s*(.+?)"
            r"(?=^\s*[A-Z][A-Za-z\- ]+\s*:|\Z)",
            notes, re.M | re.S | re.I,
        )
        if m:
            return re.sub(r"\s+", " ", m.group(1)).strip()
    return ""


# `Total Agatston CAC score: 274` or
# `Total Agatston calcium score 274.` or
# `The total Agatston CAC score is 92.` or
# `... coronary calcium score is 92.`
# \b to exclude `Vessel-level Agatston CAC scoring:`
_CAC_SCORE_RE = re.compile(
    r"[Tt]otal Agatston (?:CAC|coronary calcium|calcium) score\b"
    r"(?: is)?\s*[:\-]?\s*(\d+(?:\.\d+)?)")
# `... CAC score percentile: 55th` or `... percentile:  25`
_CAC_PCTL_RE = re.compile(r"percentile\s*:[ \t]*([^\n]+)", re.I)


def _ct_cac_pctl(raw):
    """`75th percentile` / `75` / `75.` / `75%` -> `75%`.
    `Less than 30th percentile` -> `<30%`.
    `Greater than 90th percentile` -> `>90%`.
    The `0-25th` band -> `<25%` and other bands `25-50%` / `50-75%` / `75-90%`.
    """
    text = raw.strip().strip(".").lower()
    m = re.match(r"less than\s*(\d+)", text)
    if m:
        return f"<{m.group(1)}%"
    m = re.match(r"greater than\s*(\d+)", text)
    if m:
        return f">{m.group(1)}%"
    m = re.match(r"(\d+)\s*[-–]\s*(\d+)", text)
    if m:
        lo, hi = m.groups()
        return f"<{hi}%" if lo == "0" else f"{lo}-{hi}%"
    m = re.match(r"(\d+(?:\.\d+)?)", text)
    if m is None:
        return None
    return f"{float(m.group(1)):g}%"


def _ct_cac_token(notes):
    """`CAC={score}; {pctl}`."""
    parts = []
    if m := _CAC_SCORE_RE.search(notes):
        parts.append(f"CAC={float(m.group(1)):g}")
    m = _CAC_PCTL_RE.search(notes)
    if m is not None:
        pctl = _ct_cac_pctl(m.group(1))
        if pctl:
            parts.append(pctl)
    if not parts:
        return None
    return "; ".join(parts)


# Strip `Nondilated` / `Non-dilated` and `without aneurysm` text before, so a
# section that opens `Nondilated ascending aorta.` only reports its
# genuinely abnormal sentence(s).
_CAC_AORTA_ABNORMAL = re.compile(
    r"\bectasia\b|\bectasis\b|\bectatic\b|\baneurysm\b"
    r"|\bdilat(?:ed|ation|ion)\b", re.I)


def _ct_cac_aorta_token(notes):
    # Eg `Ascending aortic ectasia 3.6 cm`, without `measuring` or period
    text = _ct_cac_section(notes, "Aorta")
    if not text:
        return None
    sents = []
    for sent in re.split(r"(?<=[.;])\s+", text):
        cleaned = re.sub(r"without\s+aneurysm", "", sent, flags=re.I)
        cleaned = re.sub(r"\bnon-?dilated\b", "", cleaned, flags=re.I)
        if not _CAC_AORTA_ABNORMAL.search(cleaned):
            continue
        out = re.sub(r"\bmeasuring\b\s*", "", sent, flags=re.I)
        out = re.sub(r"\s+", " ", out).strip().rstrip(".")
        if out:
            sents.append(out)
    if not sents:
        return None
    return ". ".join(sents)


_CAC_VESSEL_LINES = (
    (re.compile(r"^\s*left\s+main\s*:\s*(\d+(?:\.\d+)?)\s*$", re.I | re.M),
     "LM"),
    (re.compile(r"^\s*left\s+anterior\s+descending\s*:\s*(\d+(?:\.\d+)?)\s*$",
                re.I | re.M), "LAD"),
    (re.compile(r"^\s*circumflex\s*:\s*(\d+(?:\.\d+)?)\s*$",
                re.I | re.M), "Cx"),
    (re.compile(r"^\s*right\s+coronary\s*:\s*(\d+(?:\.\d+)?)\s*$",
                re.I | re.M), "RCA"),
    (re.compile(r"^\s*lm\s*:\s*(\d+(?:\.\d+)?)\s*$", re.I | re.M), "LM"),
    (re.compile(r"^\s*lad\s*:\s*(\d+(?:\.\d+)?)\s*$", re.I | re.M), "LAD"),
    (re.compile(r"^\s*lcx\s*:\s*(\d+(?:\.\d+)?)\s*$", re.I | re.M), "LCX"),
    (re.compile(r"^\s*rca(?:/pda)?\s*:\s*(\d+(?:\.\d+)?)\s*$",
                re.I | re.M), "RCA"),
)


def _ct_cac_vessel_tokens(notes):
    """`{vessel} {score}%` for 90-100% stenosis."""
    tokens, seen = [], set()
    for pattern, abbr in _CAC_VESSEL_LINES:
        m = pattern.search(notes)
        if m is None or abbr in seen:
            continue
        seen.add(abbr)
        value = float(m.group(1))
        if value.is_integer() and 90 <= value < 100:
            tokens.append(f"{abbr} {int(value)}%")
    return tokens


# The `N mm` / `N-M mm` size measure of a nodule sentence.
_CAC_NODULE_SIZE_RE = re.compile(
    r"(\d+(?:\.\d+)?(?:\s*-\s*\d+(?:\.\d+)?)?)\s*mm")
# Nodule-count words of the report's `Other Findings` text (rule 9a).
_CAC_NODULE_COUNT_WORDS = {
    "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}


def _ct_cac_nodule_token(sent):
    low = sent.lower().replace("\u2013", "-").replace("\u2014", "-")
    size = None
    m = _CAC_NODULE_SIZE_RE.search(low)
    if m:
        nums = [f"{float(part):g}"
                for part in m.group(1).replace(" ", "").split("-")]
        size = "-".join(nums) + " mm"
    count = None
    for word, n in _CAC_NODULE_COUNT_WORDS.items():
        if re.search(rf"\b{word}\b", low):
            count = n
            break
    if count is None:
        m = re.match(r"\s*(\d+)(?!\s*mm)(?!\s*-\s*\d+\s*mm)", low)
        if m:
            count = int(m.group(1))
    plural = "nodules" in low
    if count is None:
        label = "lung nodules" if plural else "lung nodule"
    elif count == 1 and not plural:
        label = "lung nodule"
    else:
        label = f"lung nodules x{count}"
    return f"{label} {size}" if size else label


def _ct_cac_nodule_tokens(notes):
    """`lung nodule {size}` or `lung nodules x{count} {size}`."""
    tokens = []
    for head in ("Other Findings", "Aorta", "Pericardium"):
        text = _ct_cac_section(notes, head)
        if not text or "nodule" not in text.lower():
            continue
        for sent in re.split(r"(?<=[.;])\s+", text):
            low = sent.lower()
            if "nodule" not in low:
                continue
            if re.search(r"\bno\s+nod|without\s+nod|no evidence", low):
                continue
            tokens.append(_ct_cac_nodule_token(sent))
    return tokens


_BIRADS_RE = re.compile(r"BI-?RADS\s*(\d)", re.I)
# Impression sentences that are boilerplate, not findings (rule 9b):
# the lifetime-risk paragraph, the `Key images` procedure-planning /
# patient-discussion / outside-comparison lines, the same-day-ultrasound
# referral lines, and the `Mammogram Plus Heart` dense-tissue
# counseling block.
_MAMMO_SKIP_RE = re.compile(
    r"lifetime\s+risk|tyrer-?cuzick|key\s+images"
    r"|discussed\s+(?:at\s+length\s+)?with\s+the\s+patient"
    r"|addendum|referred\s+to\s+another|disc\s+of\s+(?:her|his)\s+images"
    r"|whole\s+breast\s+ultrasound\s+was\s+performed\s+the\s+same\s+day"
    r"|please\s+see\s+(?:that|the)\s+separate\s+report"
    r"|we\s+will\s+recall\s+this\s+patient"
    r"|prior\s+pathology\s+report"
    r"|breast\s+arterial\s+calcifications|cardiovascular\s+risk"
    r"|adding\s+screening\s+ultrasound"
    r"|increased\s+breast\s+density\s*(?:\([^)]*\))?\s*is\s+associated"
    r"|which\s+may\s+benefit\s+this\s+patient\s+with\s+dense\s+breast\s+tissue"
    r"|due\s+for\s+annual\s+screening\s+mammography", re.I)
# A `No ...` sentence is a finding when it names a finding (a stable
# probably-benign mass, eg 16389's `No suspicious change in probably
# benign left breast 9:00 N3 mass`); the rest are the `No evidence of
# malignancy` / `No suspicious mammographic findings` negative
# statements.
_MAMMO_FINDING_RE = re.compile(
    r"\bmass(es)?\b|calcif|asymmetr|distortion|cyst|nodule|retraction"
    r"|lymph\s+node", re.I)
# Section heads some impression sentences open with.
_MAMMO_HEAD_RE = re.compile(r"^(?:recommendation|note|findings)\s*:\s*", re.I)


def _mammo_findings(notes):
    m = re.search(r"^\s*IMPRESSION\s*:?\s*", notes, re.M | re.I)
    if m is None:
        return []
    rest = notes[m.end():]
    m = re.search(r"\bBI-?RADS\b", rest, re.I)
    if m is not None:
        rest = rest[:m.start()]
    # Numbered finding lines lose their `1. ` / `2. ` numbering.
    rest = re.sub(r"(?m)^\s*\d+\.\s*", "", rest)
    out = []
    for para in re.split(r"\n\s*\n", rest):
        para = re.sub(r"\s+", " ", para).strip()
        for sent in re.split(r"(?<=[.!?;])\s+(?=[A-Z\"(])", para):
            sent = _MAMMO_HEAD_RE.sub("", sent.strip()).strip()
            if not sent or _MAMMO_SKIP_RE.search(sent):
                continue
            if re.match(r"no\b", sent, re.I) and not _MAMMO_FINDING_RE.search(sent):
                continue
            out.append(sent.rstrip("."))
    return out


def _mammo_token(notes):
    matches = list(_BIRADS_RE.finditer(notes))
    if not matches:
        return None
    n = int(matches[-1].group(1))
    if n in (1, 2):
        return "Mammo nl"
    findings = _mammo_findings(notes)
    if not findings:
        return None
    return "Mammo: " + ". ".join(findings)



# The site block head of a bone-density report: an
# optional `Left` or `Right` or `Left/Right` side prefix,
# then the site name and the block's colon.
_BMD_SITE_RE = re.compile(
    r"^\s*(?:\d+\.\s*)?(?:left|right|left\s*/\s*right)?\s*((?:lumbar\s+)?spine|femoral\s+neck|total\s+hip|forearm|distal\s+radius)\b", re.I)
# `T-Score: -0.6` or `T-Score: -1.4 -1.9`, or `T-Score: Not reported`.
_BMD_TSCORE_LINE_RE = re.compile(r"^\s*T-?Score\s*:\s*(.+)$", re.I)


def _bmd_sites(notes):
    sites = []
    site = None
    for line in notes.splitlines():
        m = _BMD_SITE_RE.match(line)
        if m:
            name = m.group(1).lower()
            if "spine" in name:
                site = "lumbar"
            elif "femoral" in name:
                site = "femur"
            elif "hip" in name:
                site = "hip"
            else:  # forearm / distal radius
                site = "forearm"
            continue
        m = _BMD_TSCORE_LINE_RE.match(line)
        if m is None or site is None:
            continue
        best = None
        for text in re.findall(r"[-+]?\d+(?:\.\d+)?", m.group(1)):
            value = float(text)
            if best is None or value < best[0]:
                best = (value, text)
        if best is not None:
            sites.append((site, best))
    return sites


def _bmd_token(notes):
    sites = _bmd_sites(notes)
    if not sites:
        return None
    site, (value, text) = min(sites, key=lambda s: s[1][0])
    if value > -1.0:
        return "Bone density nl"
    return f"Bone density {site} {value:g}"


def _vitd_token(items):
    """Always emit `VitD {val}`; a value above 50 gets a `+` on the
    value, eg `VitD 62+` (15225's 62.2 in 20.0-100.0). A flagged
    value gets its violated range limit in parens, eg `VitD 23(30)`
    (22586's 23, L in 30-100) or `VitD 110+(100)`; a flagged value
    without a parsable range stays plain `VitD {val}`."""
    for item in items:
        if "vitamin d" in item["name"].lower():
            break
    else:
        item = items[0]

    value = item["value"].strip()
    if not value:
        return None
    shown = _int_value(value)
    try:
        if float(value) > 50:
            shown += "+"
    except ValueError:
        pass
    bound = _bound_for(_normalize_flag(item), item["range"])
    if bound:
        shown += f"({bound})"
    return f"VitD {shown}"


def _pth_token(items):
    """`PTH nl` when the intact-PTH result (single item in both
    vendors' layouts) is normal; `PTH {val}({bound})` when abnormal:
    the bound is the reference-range limit the value violates (upper
    limit for `H`, lower limit for `L`, parsed from a `lo-hi`
    range); without a parsable range the token is plain `PTH {val}`."""
    it = items[0]
    if not _is_abnormal(it["flag"]):
        return "PTH nl"
    value = it["value"].strip()
    if not value:
        return None
    flag = str(it["flag"] or "").strip().upper()
    rng = it["range"].strip()
    bound = rng
    if "-" in rng:
        lo, hi = (part.strip() for part in rng.split("-", 1))
        bound = hi if flag == "H" else (lo if flag == "L" else rng)
    shown = value
    if _value_above(it):
        shown += "+"
    if not bound:
        return f"PTH {shown}"
    return f"PTH {shown}({bound})"


def _uric_token(items):
    """normal `uric acid {val}`. abnormal `uric acid {val}({bound})`."""
    it = items[0]
    value = it["value"].strip()
    if not value:
        return None
    shown = _g(value)
    if _is_abnormal(it["flag"]) and _value_above(it):
        shown += "+"
    if not _is_abnormal(it["flag"]):
        return f"uric acid {shown}"
    bound = _bound_for(str(it["flag"] or "").strip().upper(), it["range"])
    if not bound:
        return f"uric acid {shown}"
    return f"uric acid {shown}({bound})"


def _parse_float(raw):
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _psa_tokens(items):
    """Return `["PSA {val}"]` for total PSA, appending `"PSA%free {val}"`
    when total PSA is in the borderline window and free PSA% is under 25.
    """
    names = ["prostate specific ag, serum", "psa, total"]
    total_item = _first_item(items, names)
    if total_item is None:
        total_item = items[0]

    value = total_item["value"].strip()
    if not value:
        return []

    total = _parse_float(value)
    if total is not None:
        shown = _g(_round1(value))
        if _value_above(total_item):
            shown += "+"
        first = f"PSA {shown}"
    else:
        first = f"PSA {value}"
    tokens = [first]

    pct_item = _first_item(items, ["% free psa"])
    if pct_item is None or total is None:
        return tokens

    pct_value = pct_item["value"].strip()
    pct_num = _parse_float(pct_value)
    if pct_num is None:
        return tokens

    # Use the violated reference upper bound if parseable; otherwise default to 4.0.
    bound = _bound_for(_normalize_flag(total_item), total_item["range"])
    upper = _parse_float(bound)
    if upper is None:
        upper = 4.0

    if upper <= total < 10.0 and pct_num < 25.0:
        tokens.append(f"PSA%free {_int_value(pct_value)}")

    return tokens


def _inrpt_tokens(items):
    """Return a list of abnormal `INR` / `PT` tokens (in `INR`, `PT` order),
    or `["INR/PT nl"]` / `["INR nl"]` / `["PT nl"]` when neither is abnormal
    and one or both valued items are present; `[]` otherwise.
    """
    pairs = [
        ("INR", _first_item(items, ["inr"])),
        ("PT", _first_item(items, ["pt", "prothrombin time"])),
    ]

    abnormal_tokens = [
        # a high INR is signed; PT marks a high with its bound only
        _val_bound(label, item, _g, sign=label == "INR")
        for label, item in pairs
        if _is_usable_abnormal(item)
    ]
    if abnormal_tokens:
        return abnormal_tokens

    present_labels = [
        label
        for label, item in pairs
        if item is not None and item["value"].strip()
    ]
    if len(present_labels) == 2:
        return ["INR/PT nl"]
    if len(present_labels) == 1:
        return [f"{present_labels[0]} nl"]
    return []


def _hav_ab_state(items):
    """`pos` / `neg` for the HAV total Ab item (single item in both
    vendors' layouts), `None` when the result is pending / empty.
    `BORDERLINE` counts as `neg`: it does not confirm immunity."""
    value = items[0]["value"].strip().lower()
    if value in _POSITIVE_VALUES:
        return "pos"
    if value in _HAV_SUSCEPTIBLE:
        return "neg"
    return None


def _hav_token(items):
    return "HAV Ab+" if _hav_ab_state(items) == "pos" else None


def _hav_igm_token(items):
    """`HAV IgM+` when the HAV IgM screen (the acute-hepatitis-A test;
    the single item in both vendors' layouts) is positive (Quest's
    `REACTIVE`, LabCorp's `Positive`); a negative value produces
    nothing -- the yellow notes omit a negative HAV IgM (rule 25a)."""
    value = items[0]["value"].strip().lower()
    return "HAV IgM+" if value in _POSITIVE_VALUES else None


# The MMR components' item names and IgG immune thresholds (the
# equivocal bands sit just below each threshold). Quest's classic and
# current (`... AB (IGG), IMMUNE STATUS`) layouts and LabCorp's, per
# component; _mmr_needed and the Ab+ tokens must use the same lists.
_MMR_COMPONENTS = {
    "measles": (["measles antibody (igg)", "measles ab (igg), immune status",
                 "rubeola ab, igg", "measles antibodies, igg"], 16.49),
    "mumps": (["mumps virus antibody (igg)", "mumps virus ab (igg), immune status",
               "mumps abs, igg"], 10.99),
    "rubella": (["rubella antibody (igg)", "rubella ab (igg), immune status",
                 "rubella antibodies, igg"],
                0.99),
}


def _mmr_needed(latest):
    """True when any tested MMR component is non-immune: a level at or
    below the component's immune threshold (the equivocal bands count)
    or a negative / non-immune text value. Pending / number-less
    results give no signal. The MMR vaccine covers all three
    components, so one non-immune component needs it."""
    names = _MMR_COMPONENTS
    for category, (item_names, threshold) in names.items():
        if category not in latest:
            continue
        item = _first_item(latest[category], item_names)
        if item is None:
            continue
        value = item["value"].strip().lower()
        if value in _NEGATIVE_VALUES:
            return True
        num = _first_num(value)
        if num is not None and num <= threshold:
            return True
    return False


def _vacc_token(latest):
    parts = []
    if "hav" in latest and _hav_ab_state(latest["hav"]) == "neg":
        parts.append("HAV")
    if _hbv_ab_state(latest) == "neg" and not _hbv_infected(latest):
        parts.append("HBV")
    if _mmr_needed(latest):
        parts.append("MMR")
    return f"RTC {'/'.join(parts)} vacc" if parts else None


def _positive_titer_token(items, names, threshold, token):
    """Return `token` if the first item matching `names` has a numeric value
    strictly greater than `threshold`, else `None`.
    """
    item = _first_item(items, names)
    if item is None:
        return None

    num = _first_num(item["value"].strip())
    return token if num is not None and num > threshold else None


def _measles_token(items):
    # immune threhold in AU/mL. 13.5-16.49 is the equivocal band.
    # Quest sends "N" on a strong positive
    # LabCorp sends "L" on a non-immune value
    return _positive_titer_token(
        items, *_MMR_COMPONENTS["measles"], token="measles Ab+"
    )


def _mumps_token(items):
    # IgG immune threshold in AU/mL. capped `>300.00` counts.
    # 9.00-10.99 is equivocal.
    return _positive_titer_token(
        items, *_MMR_COMPONENTS["mumps"], token="mumps Ab+"
    )


def _rubella_token(items):
    # immune IgG index. 0.90-0.99 is equivocal.
    return _positive_titer_token(
        items, *_MMR_COMPONENTS["rubella"], token="rubella Ab+"
    )


def _mmr_ab_tokens(latest):
    """The rule-26 MMR tokens: one `MMR Ab+` when all three components
    are immune, else one `{component} Ab+` per immune component, in the
    fixed measles / mumps / rubella order. Called only when no tested
    component needs the vaccine."""
    tokens = []
    if "measles" in latest:
        tokens.append(_measles_token(latest["measles"]))
    if "mumps" in latest:
        tokens.append(_mumps_token(latest["mumps"]))
    if "rubella" in latest:
        tokens.append(_rubella_token(latest["rubella"]))
    tokens = [t for t in tokens if t]
    return ["MMR Ab+"] if len(tokens) == 3 else tokens


def _varicella_state(it):
    """`pos` / `neg` for one VZV IgG item (rule 26c), or `None` when
    the result is undetermined (a pending / empty value, the index
    layout's 135.00-164.99 equivocal band, or an unrecognized value
    on a layout with no numeric cutoff).  The value decides, not the
    flag (LabCorp sends none): `Reactive` / `Positive` text is
    positive, `Non Reactive` / `Negative` negative; a numeric S/CO
    level is positive at or above 1.00 (a capped `<1.00` is below the
    cutoff, so negative); a numeric index level is positive at or
    above 165.00, negative below 135.00, and equivocal in between
    (a capped value in the equivocal band is undetermined)."""
    if it is None:
        return None
    value = it["value"].strip()
    if not value:
        return None
    low = value.lower()
    if low in _POSITIVE_VALUES:
        return "pos"
    if low in _NEGATIVE_VALUES:
        return "neg"
    num = _first_num(value)
    if num is None:
        return None
    units = it["units"].strip().lower()
    if "s/co" in units:
        if value.startswith("<"):
            return "neg"
        # S/CO IgG cutoff
        return "pos" if num >= 1.00 else "neg"
    if "index" in units:
        if value.startswith("<"):
            return "neg" if num < 135.00 else None
        if num >= 165.00:
            return "pos"
        if num < 135.00:
            return "neg"


_VARICELLA_IGG_NAMES = (
    "varicella zoster virus antibody (igg)",
    "varicella zoster igg",
    "varicella zoster virus antibody (igg)",
)


def _varicella_token(items):
    item = _first_item(items, _VARICELLA_IGG_NAMES)
    return "varicella Ab+" if _varicella_state(item) == "pos" else None


def _iron_label(name):
    n = name.strip().lower()
    if n in ["iron, serum", "iron, total"]:
        return "iron"
    if n in ["iron bind.cap.(tibc)", "iron binding capacity"]:
        return "TIBC"
    if n in ["iron saturation", "% saturation"]:
        return "iron%sat"
    if n in ["ferritin"]:
        return "ferritin"
    # None for UIBC etc


def _iron_token(items):
    """`iron {tIBC} nl` when every item of the iron panel is normal (the
    TIBC value shown, trailing zeros stripped; plain `iron nl` when the
    panel carries no TIBC value).  When the panel is abnormal, one token
    per abnormal item, in report order, `{label} {val}({bound})` (labels
    via `_iron_label`; the bound via `_bound_for`, a plain `{label} {val}`
    when unparseable; the value's trailing zeros stripped via `%g`; an
    abnormal item with no label or an empty value yields no token of its
    own but still suppresses the normal token, like `UIBC`)."""
    tokens = []
    for it in _abnormal_items(items):
        label = _iron_label(it["name"])
        if label is None:
            continue
        value = it["value"].strip()
        if not value:
            continue
        shown = _g(value)
        if _value_above(it):
            shown += "+"
        bound = _bound_for(str(it["flag"] or "").strip().upper(), it["range"])
        tokens.append(
            f"{label} {shown}({bound})" if bound else f"{label} {shown}")
    if not tokens:
        if _abnormal_items(items):
            return None
        tibc = _first_item(
            items, ["iron bind.cap.(tibc)", "iron binding capacity"])
        if tibc is not None and tibc["value"].strip():
            return f"iron {_g(tibc['value'])} nl"
        return "iron nl"
    return ", ".join(tokens)


def _ferritin_token(latest):
    """The ferritin value next to the iron token (rule 27a): the
    panel's own `Ferritin` item when it is usable, else the newest
    standalone ferritin order. Normal: `ferritin {val}`; abnormal:
    `ferritin {val}({bound})`. An abnormal panel item is reported in
    the panel token (rule 27), so it is not reported here twice."""
    if "iron" in latest:
        item = _first_item(latest["iron"], ["ferritin"])
        if item is not None and item["value"].strip():
            if _is_abnormal(item["flag"]):
                return None
            return f"ferritin {_g(item['value'].strip())}"
    if "ferritin" in latest:
        item = _first_item(latest["ferritin"], ["ferritin", "ferritin, serum"])
        if item is None or not item["value"].strip():
            return None
        if not _is_abnormal(item["flag"]):
            return f"ferritin {_g(item['value'].strip())}"
        shown = _g(item["value"].strip())
        if _value_above(item):
            shown += "+"
        return _format_token("ferritin", shown, _item_bound(item))
    return None


def _range_bound(rng, flag):
    """Extract the violated bound from a range string for `H` or `L` flags,
    falling back to the full stripped range.
    """
    stripped = (rng or "").strip()
    if "-" in stripped:
        lo, hi = (part.strip() for part in stripped.split("-", 1))
        if flag == "H":
            return hi
        if flag == "L":
            return lo
    return stripped


def _b12_token(items):
    """Return `B12 {val}` if normal, `B12 {val}({bound})` if abnormal, or
    `None` if missing or empty-valued.
    """
    item = _first_item(items, ["vitamin b12"])
    if item is None:
        return None

    value = item["value"].strip()
    if not value:
        return None

    if not _is_abnormal(item["flag"]):
        return f"B12 {value}"

    flag = _normalize_flag(item)
    bound = _range_bound(item["range"], flag)
    return _format_token("B12", value, bound)


# Quest and LabCorp respectively
_B6_ITEMS = ("vitamin b6, plasma", "vitamin b6")


def _b6_token(items):
    """Return `B6 nl` if the first matching item is normal, `B6 {val}({bound})`
    or `B6 {val}` (both formatted via `_b6_value`) if abnormal with a value,
    or `None` if no item matches or an abnormal item has an empty value.
    """
    item = _first_item(items, _B6_ITEMS)
    if item is None:
        return None
    if not _is_abnormal(item["flag"]):
        return "B6 nl"

    value = item["value"].strip()
    if not value:
        return None

    shown = _b6_value(value)
    if _value_above(item):
        shown += "+"
    bound = _item_bound(item)
    rendered_bound = _b6_value(bound) if bound else None
    return _format_token("B6", shown, rendered_bound)


def _b1b6_tokens(latest):
    """Normal `B1/B6 nl`. Abnormal `{label} {val}({bound})`."""
    members = (
        ("b1", "B1", ["vit. b1, whole blood", "vitamin b1 (thiamine),"]),
        ("b6", "B6", _B6_ITEMS),
    )

    normal, abnormal = [], []
    for category, label, item_names in members:
        if category not in latest:
            continue
        token = (
            _b6_token(latest[category])
            if category == "b6"
            else _named_flag_token(latest[category], item_names, label)
        )
        if token is None:
            continue
        if token.endswith(" nl"):
            normal.append(label)
        else:
            abnormal.append(token)
    tokens = ["/".join(normal) + " nl"] if normal else []
    tokens.extend(abnormal)
    return tokens


def _value_above(it):
    """True when an item's value is above its reference range's upper
    limit: an `H` flag (a multi-letter flag ending in `H`, e.g.
    Quest's `HH`, counts too -- read by its last letter, like
    `_bound_for`), or an undirected `A` flag whose value parses above
    a `lo-hi` range's limit (an `A` on a one-sided or empty range is
    not above).  Normal and low flags are not above."""
    flag = str(it["flag"] or "").strip().upper()
    last = flag[-1] if flag else ""
    if last == "H":
        return True
    if last != "A":
        return False
    rng = it["range"].strip()
    if "-" not in rng:
        return False
    hi = _first_num(rng.split("-", 1)[1])
    val = _first_num(it["value"])
    if hi is None or val is None:
        return False
    return val > hi


def _hi_bound(rng):
    """The upper limit of a reference range as a number without
    trailing zeros (`10-35` -> `35`, `9-46` -> `46`, `<46` -> `46`);
    None when the range has no parsable upper limit (an empty range,
    a one-sided lower limit such as `> OR = 60`, or no number)."""
    rng = rng.strip()
    if not rng or rng.startswith(">"):
        return None
    part = rng.split("-", 1)[1] if "-" in rng else rng
    num = _first_num(part)
    return None if num is None else f"{num:g}"


def _astalt_token(items):
    """Return `AST/ALT ...` when either AST or ALT is above range (or a
    single-item token when only one is present and high), else `None`.
    A high AST / ALT gains a `+` on its value, eg `AST/ALT 34+/30`.
    """
    pairs = (
        ("AST", _first_item(items, ["ast", "ast (sgot)"])),
        ("ALT", _first_item(items, ["alt", "alt (sgpt)"])),
    )

    vals = []
    any_high = False
    for label, it in pairs:
        if it is None:
            continue
        value = it["value"].strip()
        if not value:
            continue

        if _value_above(it):
            any_high = True
            bound = _hi_bound(it["range"])
            value += "+"
            rendered = f"{value}({bound})" if bound else value
        else:
            rendered = value
        vals.append((label, rendered))

    if not any_high:
        return None
    if len(vals) == 1:
        label, rendered = vals[0]
        return f"{label} {rendered}"
    return f"AST/ALT {'/'.join(rendered for _, rendered in vals)}"


def _protein_token(items):
    """Return `protein {val}+({bound})` or `protein {val}+` when total
    protein is high with a non-empty value (the token is high-only,
    so the value is always signed), else `None`.
    """
    # Quest and LabCorp respectively
    it = _first_item(items, ["protein, total", "protein, total, serum"])
    if it is None:
        return None

    value = it["value"].strip()
    if not value or not _value_above(it):
        return None

    return _format_token("protein", value + "+", _hi_bound(it["range"]))


def _hiv_negative(items):
    """True when an HIV result is negative.

    Quest's 4th-gen Ag/Ab screen can be REACTIVE (flag N) on an
    HIV-negative patient: the reflex HIV 1/2 Ab and HIV RNA work-up
    decides, and its verdict is the `HIV FINAL INTERPRETATION` item
    (``HIV NEGATIVE``).  A result without that item (LabCorp's
    single `HIV Screen 4th Generation wRfx` item, and LabCorp's
    `HIV-1/HIV-2 Qualitative RNA` confirmatory order's `HIV-1 RNA`
    / `HIV-2 RNA` items) is negative when nothing is flagged
    abnormal and every item value is non-reactive / negative.
    """
    if _abnormal_items(items):
        return False
    for it in items:
        if "final interpretation" in it["name"].lower():
            return it["value"].strip().lower() in _NEGATIVE_VALUES
    valued = [it for it in items if it["value"].strip()]
    return bool(valued) and all(
        it["value"].strip().lower() in _NEGATIVE_VALUES for it in valued)


def _rpr_negative(items):
    """True when an RPR (syphilis screen) result is negative: nothing
    flagged abnormal and every item value non-reactive / negative
    (Quest's `RPR (DX) W/REFL TITER AND$CONFIRMATORY TESTING` item,
    LabCorp's `RPR` item)."""
    if _abnormal_items(items):
        return False
    valued = [it for it in items if it["value"].strip()]
    return bool(valued) and all(
        it["value"].strip().lower() in _NEGATIVE_VALUES for it in valued)


def _hsv_type_state(it):
    """pos or neg for one HSV type-specific IgG item"""
    if it is None:
        return None
    value = it["value"].strip()
    if not value:
        return None
    low = value.lower()
    # LabCorp reports Reactive / Non Reactive
    if low in _NEGATIVE_VALUES or low.startswith("<"):
        return "neg"
    if low in _POSITIVE_VALUES:
        return "pos"
    num = _first_num(value)
    if num is None:
        return None
    # Quest HerpesSelect index cutoffs.
    # Quest flags a positive index H.
    if num > 1.09:
        return "pos"
    if num < 0.90:
        return "neg"


def _hdv_negative(items):
    if _abnormal_items(items):
        return False
    valued = [it for it in items if it["value"].strip()]
    return bool(valued) and all(
        it["value"].strip().lower() in _NEGATIVE_VALUES for it in valued)


_HSV1_NAMES = frozenset({"hsv 1 igg type specific ab", "hsv 1 igg, type spec"})
_HSV2_NAMES = frozenset({"hsv 2 igg type specific ab", "hsv 2 igg, type spec"})


def _hsv_states(latest):
    """Return `(state1, state2)` for HSV-1 and HSV-2 type-specific IgG items
    via `_hsv_type_state`, or `(None, None)` if `"hsv"` is absent.
    """
    items = latest.get("hsv")
    if not items:
        return None, None

    h1 = _first_item(items, _HSV1_NAMES)
    h2 = _first_item(items, _HSV2_NAMES)
    return _hsv_type_state(h1), _hsv_type_state(h2)


def _std_token(latest, gc_states):
    """The STD-marker token: one segment per group that is present
    and negative -- `HBV/HCV` (the hep B/C screens), `HIV`, `RPR`, HSV types
    (`HSV` when both types are negative, `HSV1` / `HSV2` when only one is),
    G-C, `Treponema`. Joined with `/` and a trailing ` neg`,
    e.g. `HBV/HCV/HIV/RPR/HSV/G-C/Treponema neg` when everything is
    negative and `HBV/HCV neg` when only the hep B/C screens are.
    A negative HDV screen joins the negative HIV segment as `HIV/HDV`; an HDV
    screen with no negative HIV screen to join keeps its own
    `HDV neg` / `HDV+` token."""
    parts = []
    # the surface-Ab row is immunity status (rule 24c), not an
    # infection marker: the group needs only the two screen rows
    if "hcv" in latest and "hbsag" in latest \
            and not _abnormal_items(latest["hcv"]) \
            and not _abnormal_items(latest["hbsag"]):
        parts.append("HBV/HCV")
    if "hiv" in latest and _hiv_negative(latest["hiv"]):
        # a negative HDV screen joins the segment (the notes'
        # `HIV/HDV neg`); a positive / undetermined one keeps its own
        # token (rule 24a)
        parts.append(
            "HIV/HDV" if "hdv" in latest and _hdv_negative(latest["hdv"])
            else "HIV")
    if "rpr" in latest and _rpr_negative(latest["rpr"]):
        parts.append("RPR")
    neg = [t for t, state in zip(("1", "2"), _hsv_states(latest))
           if state == "neg"]
    if len(neg) == 2:
        parts.append("HSV")
    elif neg:
        parts.append(f"HSV{neg[0]}")
    chlam, gonorr = _gc_states(gc_states)
    if chlam == "neg" and gonorr == "neg":
        parts.append("G-C")
    elif chlam == "neg":
        parts.append("chlamydia")
    elif gonorr == "neg":
        parts.append("gonorrhea")
    if _treponema_state(latest) is False:
        parts.append("Treponema")
    if not parts:
        return None
    return "/".join(parts) + " neg"


def _hbv_neg_token(latest):
    """`HBV neg` right after the STD token when a surface-Ag screen
    is negative with no HCV row, so the negative result would
    otherwise be silent. With both screen rows present the STD token
    reports `HBV/HCV neg` instead."""
    if "hbsag" not in latest:
        return None
    # both screen rows present: the STD token reports the HBV/HCV
    # group, no separate token
    if "hcv" in latest:
        return None
    if _abnormal_items(latest["hbsag"]):
        return None
    # the explicit negative value decides: a pending / empty screen
    # is undetermined, not negative
    if not any(it["value"].strip().lower() in _NEGATIVE_VALUES
               for it in latest["hbsag"]):
        return None
    return "HBV neg"


def _hiv_positive(items):
    """True when an HIV result is positive: something flagged
    abnormal, or a `HIV POSITIVE` final interpretation of the reflex
    work-up (mirroring `_hiv_negative`, whose `HIV NEGATIVE`
    interpretation decides the negative side -- a REACTIVE 4th-gen
    Ag/Ab screen (flag N) on a patient whose work-up says `HIV
    NEGATIVE` is not positive).  A pending / empty result is
    undetermined, not positive."""
    if _abnormal_items(items):
        return True

    for it in items:
        if "final interpretation" in it["name"].lower():
            value = it["value"].strip().lower()
            return value in _POSITIVE_VALUES or value == "hiv positive"

    return any(
        it["value"].strip().lower() in _POSITIVE_VALUES
        for it in items
        if it["value"].strip()
    )


def _rpr_positive(items):
    """True when an RPR result is positive: something flagged
    abnormal (Quest's REACTIVE screen item, a flagged titer) or a
    valued item that reads reactive / positive (mirroring
    `_rpr_negative`).  A pending / empty result is undetermined, not
    positive."""
    if _abnormal_items(items):
        return True
    valued = [it for it in items if it["value"].strip()]
    return any(it["value"].strip().lower() in _POSITIVE_VALUES
               for it in valued)


def _hsv_tokens(latest):
    pos = [
        f"HSV{t}+" for t, state in zip(("1", "2"), _hsv_states(latest))
        if state == "pos"
    ]
    if len(pos) == 2:
        return ["HSV1/HSV2+"]
    return pos


def _naa_state(item):
    """`neg` / `pos` for one NAA pathogen item of the G-C / Treponema
    groups (rule 21), or `None` when undetermined (an empty / pending
    value or an unrecognized value).  A flagged-abnormal item is
    positive (Quest flags a detected NAA `A`, LabCorp a positive one
    `A`); a negative / not-detected value is negative; a positive /
    detected value is positive."""
    value = item["value"].strip().lower()
    if _is_abnormal(item["flag"]):
        return "pos"
    if value in _POSITIVE_VALUES or value == "detected":
        return "pos"
    if value in _NEGATIVE_VALUES:
        return "neg"


def _gc_pathogen_state(items, names):
    states = [_naa_state(it) for it in items
              if it["name"].strip().lower() in names]
    if not states:
        return None
    if any(state == "pos" for state in states):
        return "pos"
    if all(state == "neg" for state in states):
        return "neg"
    return None


# Quest's `CHLAMYDIA/N. GONORRHOEAE$RNA, TMA` layout spells them with the
# `$RNA, TMA` suffix (the in-house order without it); the in-house
# `CHLAMYDIA TRACHOMATIS, TMA (ALTERNATE TARGET)` reflex re-test
# reports its chlamydia item bare.
_CHLAMYDIA_ITEMS = frozenset({
    "chlamydia trachomatis",  # in-house / Quest
    "chlamydia trachomatis, naa",  # LabCorp
    "chlamydia trachomatis rna, tma",  # Quest
    "chlamydia trachomatis,tma",  # in-house alternate target
})
_GONORRHEA_ITEMS = frozenset({
    "neisseria gonorrhoeae",  # in-house / Quest
    "neisseria gonorrhoeae, naa",  # LabCorp
    "neisseria gonorrhoeae rna, tma",  # Quest
})


def _gc_pathogen_states(rows):
    gc_names = _CATEGORY_NAMES["gc"]
    states = {}
    for row, items in rows:  # newest first
        name = (row.get("name") or "").strip().lower().replace("$", " ")
        if name not in gc_names:
            continue
        for pathogen, names in (("chlamydia", _CHLAMYDIA_ITEMS),
                                ("gonorrhea", _GONORRHEA_ITEMS)):
            if pathogen in states:
                continue
            state = _gc_pathogen_state(items, names)
            if state is not None:
                states[pathogen] = state
    return states


def _gc_states(gc_states):
    """`(chlamydia, gonorrhea)` states, each `pos` / `neg` / None."""
    return (gc_states.get("chlamydia"), gc_states.get("gonorrhea"))


def _gc_tokens(gc_states):
    """One `chlamydia+` / `gonorrhea+` per detected pathogen, or one combined
    `chlamydia/gonorrhea+` when both positive. A negative pathogen is
    skipped here (part of STD neg list)."""
    pos = [
        f"{pathogen}+" for pathogen, state in
        zip(("chlamydia", "gonorrhea"), _gc_states(gc_states))
        if state == "pos"
    ]
    if len(pos) == 2:
        return ["chlamydia/gonorrhea+"]
    return pos


def _treponema_state(latest):
    """`Treponema+`, False if negative, or None."""
    if "treponema" not in latest:
        return None
    items = latest["treponema"]
    states = [
        _naa_state(it)
        for it in items
        if it["name"].strip().lower() == "treponema pallidum ab"
    ]
    if "pos" in states:
        return "Treponema+"
    if states and all(state == "neg" for state in states):
        return False


def _qtb_token(items):
    for it in items:
        value = it["value"].strip().lower()
        if value == "positive":
            return "QTB+"
        if value == "negative":
            return "QTB neg"
        if value == "indeterminate":
            return None


def _shield_token(items):
    """`Shield blood test neg` / `Shield blood test+` (rule 42a): the
    Guardant Shield CRC blood test's value (the `SHIELD ID` item is the
    sample ID, not a result)."""
    item = _first_item(items, ["shield crc blood test"])
    if item is None:
        return None
    value = item["value"].strip().lower()
    if value in _POSITIVE_VALUES:
        return "Shield blood test+"
    if value in _NEGATIVE_VALUES:
        return "Shield blood test neg"
    return None


def _abo_token(items):
    """`ABO {group}{sign}` for the ABO-grouping / Rho(D)-typing
    result (rule 43): the ABO group letter (`ABO Grouping` /
    `ABO GROUP` item's value, written as reported: `A` / `B` / `AB`
    / `O`) plus a `+` for a Rho(D)-positive result (`Rh Factor` =
    `Positive`, `RH TYPE` = `RH(D) POSITIVE`) and a `-` for a
    Rho(D)-negative one -- the yellow notes' blood-type shorthand
    (eg `ABO A+`, `ABO O+`).  A pending / empty group or Rh value
    produces nothing."""
    abo = next(
        (it for it in items if it["name"].strip().lower() in ["abo grouping", "abo group"]),
        None,
    )
    rh = next(
        (it for it in items if it["name"].strip().lower() in ["rh factor", "rh type"]),
        None,
    )
    if abo is None or rh is None:
        return None
    group = abo["value"].strip()
    rh_value = rh["value"].strip()
    if not group or not rh_value:
        return None
    low = rh_value.lower()
    if "positive" in low:
        return f"ABO {group}+"
    if "negative" in low:
        return f"ABO {group}-"
    return None


def _allergy_group(name):
    groups = {
        "m": "mold",
        "d": "dust mite",
        "e": "animal",
        "t": "pollen",
        "w": "pollen",
        "g": "pollen",
        "f": "food",
    }
    name = name.strip().lower()
    if m := re.search(r"\(([a-z])\d+\)", name):
        return groups.get(m.group(1))
    # LabCorp `{CODE}-IgE` item prefix
    if m := re.match(r"^([a-z])\d+-ige\b", name):
        return groups.get(m.group(1))
    if name in ["d farinae mite", "d pteronyssinus mite"]:
        return "dust mite"
    return None


def _allergy_bound(it):
    """The item's positivity threshold (rule 44): its range's upper
    limit when the range is numeric (the mite IgG4 items' `<0.50`),
    None for the range-less specific-IgE items and the LabCorp items
    whose range field carries the IgE class label (`Class 0/I`), not
    a numeric range -- the 0.10 kU/L cutoff applies to those."""
    rng = it["range"].strip()
    if not rng or rng.lower().startswith("class"):
        return None
    return _hi_bound(rng)


def _allergy_positive(it, group, allergy_pos):
    """True when one allergen item is positive: a flagged-
    abnormal item (the lab flags a positive level H), or an
    unflagged numeric value at / above the positivity threshold --
    the mite IgG4 items' range upper limit when their range carries
    one (`<0.50` -> 0.5), the specific-IgE 0.10 kU/L cutoff for the
    rest (the `<0.10`-style value is below it, so negative; the
    `TNP`-valued not-performed items are below it)."""
    if _is_abnormal(it["flag"]):
        return True
    value = it["value"].strip()
    if not value or value.startswith("<"):
        return False
    num = _first_num(value)
    if num is None:
        return False
    bound = _allergy_bound(it)
    if bound is not None:
        return num >= float(bound)
    return num >= allergy_pos


def _allergy_tokens(latest):
    """The allergy-panel tokens (rule 44): the negative groups join
    one token, their labels in the fixed group order `mold` /
    `dust mite` / `pollen` / `animal` / `food` joined with `/` plus
    a single trailing ` neg` (eg `allergy mold/dust mite/pollen
    neg`; the yellow notes write a negative panel as `all.ergy
    mold/dust mite/Pollen neg`); each positive group reports one
    `{group} {val}+({bound})` token right after that one, in group
    order -- the group's highest positive value (20116's note reports
    `Timothy grass 14(0.1)`, not the panel's other flagged items)
    -- (the value's trailing zeros stripped; the parenthesized bound
    the item's positivity threshold -- the mite IgG4 items' range
    upper limit, the specific-IgE 0.10 cutoff for the rest -- 21309's
    yellow note writes a positive mite `dust mite 0.23+(0.1)`).  A
    group whose newest row has no usable item / value produces
    nothing (a pending panel)."""
    # kU/L. IgE items don't give a ref range, so unflagged numbers use this hardcoded cutoff.
    allergy_pos = 0.10
    groups = (
        ("allergy_mold", "mold"),
        ("allergy_mite", "dust mite"),
        ("allergy_pollen", "pollen"),
        ("allergy_animal", "animal"),
        ("allergy_food", "food"),
    )
    normal = []
    tokens = []
    for key, group in groups:
        if key not in latest:
            continue
        items = [it for it in latest[key]
                 if _allergy_group(it["name"]) == group]
        usable = [it for it in items if it["value"].strip()]
        if not usable:
            continue
        positives = [it for it in usable
                     if _allergy_positive(it, group, allergy_pos)]
        if positives:
            # one token per group (highest value)
            def level(it):
                num = _first_num(it["value"])
                return (num is not None, num or 0.0)
            worst = max(positives, key=level)
            shown = _g(worst["value"].strip())
            bound = _allergy_bound(worst)
            if bound is None:
                bound = str(allergy_pos)
            tokens.append(f"{group} {shown}+({bound})")
        else:
            normal.append(group)
    if normal:
        tokens.insert(0, "allergy " + "/".join(normal) + " neg")
    return tokens


def _ana_token(items):
    """`ANA+` (with the item's titer appended, `ANA+ 1:80`, when a
    result value is one) when any ANA item (`_ANA_ITEMS`) is flagged
    abnormal; `ANA nl` when no ANA item is flagged abnormal (Quest's
    negative results and its empty-valued items both fall here);
    any other nonempty ANA item value produces nothing (rule 33).
    The panel's RF / CCP items are the categories of rules 34a /
    b, not ANA items, so their values do not affect the verdict."""
    ana_items = [
        "ana pattern",  # Quest
        "ana titer",  # Quest
        "antinuclear antibodies, ifa",  # LabCorp
        "ana direct",  # LabCorp
        "ana screen, ifa",  # Quest and LabCorp
    ]
    ana = [it for it in items if it["name"].strip().lower() in ana_items]
    if _abnormal_items(ana):
        for it in ana:
            value = it["value"].strip()
            if re.fullmatch(r"1:\d+", value):
                return f"ANA+ {value}"
        return "ANA+"
    for it in ana:
        value = it["value"].strip().lower()
        if not value:
            continue
        if value in _NEGATIVE_VALUES:
            continue
        return None
    return "ANA nl"


def _esrcrp_tokens(latest):
    """Normal `ESR/CRP nl` else `ESR {val}({bound})` / `CRP {val}({bound})`.
    A normal item reports `ESR nl` / `CRP nl` only if the other is absent."""
    esr = _flag_token("ESR", latest["esr"]) if "esr" in latest else None
    crp = _flag_token("CRP", latest["crp"], _int_value) \
        if "crp" in latest else None
    if esr == "ESR nl" and crp == "CRP nl":
        return ["ESR/CRP nl"]
    parts = []
    for token, other in ((esr, crp), (crp, esr)):
        if token is None:
            continue
        if token.endswith(" nl") and other is not None:
            continue
        parts.append(token)
    return parts


def _c3c4_tokens(items):
    """The complement C3 / C4 tokens (rule 34c): the order's `C3C`
    and `C4C` items, both on the one order.  One token per abnormal
    item, C3 first: `C3 {val}({bound})` / `C4 {val}({bound})` (the
    values' trailing zeros stripped via `%g`, the bound via
    `_bound_for`); a normal member reports `C3 nl` / `C4 nl` only
    when the other component is absent.  When neither item is
    abnormal: `C3/C4 nl` when both items are present (a valued
    item), `C3 nl` / `C4 nl` when only one is."""
    c3 = next(
        (it for it in items if it["name"].strip().lower() in ["complement component c3c"]),
        None,
    )
    c4 = next(
        (it for it in items if it["name"].strip().lower() in ["complement component c4c"]),
        None,
    )
    tokens = []
    for label, it in (("C3", c3), ("C4", c4)):
        if it is None:
            continue
        if _is_abnormal(it["flag"]) and it["value"].strip():
            tokens.append(_val_bound(label, it, _g))
    if tokens:
        return tokens
    present = [label for label, it in (("C3", c3), ("C4", c4))
               if it is not None and it["value"].strip()]
    if len(present) == 2:
        return ["C3/C4 nl"]
    if len(present) == 1:
        return [f"{present[0]} nl"]
    return []


def _dsdna_token(items):
    """`dsDNA+` when the `DNA (DS) ANTIBODY` item is flagged
    abnormal; `dsDNA neg` when its value is in the negative set, or
    when its flag is normal -- LabCorp sends '' on a negative (the
    value is a small number, eg 2), Quest sends flag N on a
    negative; a pending / unrecognized value produces nothing
    (rule 34d)."""
    it = next(
        (it for it in items if it["name"].strip().lower() in ["dna (ds) antibody"]),
        None,
    )
    if it is None:
        return None
    if _is_abnormal(it["flag"]):
        return "dsDNA+"
    value = it["value"].strip().lower()
    if value in _NEGATIVE_VALUES or not _is_abnormal(it["flag"]):
        return "dsDNA neg"
    return None


def _hbv_dna_token(items):
    """The HBV DNA token (rule 22).  The result is one of:
    - `HBV DNA neg` for a not-detected result (`NOT DETECTED`,
      `<1.00 NOT DETECTED`, ...);
    - `HBV DNA <{lim}` for a result detected below the
      quantification limit -- Quest's current assay reports the
      limit as a log10 (`<1.00 DETECTED` is `HBV DNA <10`, since
      10**1.00 = 10 IU/mL); a linear `<10 DETECTED` or a leading
      `<` value such as LabCorp's `<10` is `HBV DNA <10`;
    - `HBV DNA {linear}/{log}` for a numeric value: the yellow notes
      write the level with its log10 (`2000` IU/mL -> `HBV DNA
      2000/3.3`, `147000` -> `HBV DNA 147000/5.17`).  Quest's
      current assay reports the log10 directly (units `Log IU/mL`),
      so the linear level is reconstructed as 10**value, rounded to
      a whole number (`2.62` -> `HBV DNA 417/2.62`); a value without
      log units is treated as linear IU/mL and its log10 is
      computed.
    A pending / empty value (Quest's `TNP`) produces nothing.
    We ignore LabCorp log10 and information items and use linear value."""
    it = items[0]
    value = str(it.get("value") or "").strip()
    if not value:
        return ""
    is_log = "log" in str(it.get("units") or "").lower()
    low = value.lower()
    if "tnp" in low:
        return ""
    if "not detected" in low or low in ("negative", "non-reactive",
                                        "non reactive"):
        return "HBV DNA neg"
    m = re.search(r"(\d+(?:\.\d+)?)", value)
    if "detected" in low or value.startswith("<"):
        if m:
            lim = float(m.group(1))
            if is_log:
                lim = 10.0 ** lim
            return f"HBV DNA <{_g(lim)}"
        return "HBV DNA det" if "detected" in low else ""
    if m is None:
        return ""
    num = float(m.group(1))
    if is_log:
        # the assay reports log10; the yellow notes pair the level
        # with its log, so reconstruct a whole-number linear level
        linear, log = round(10.0 ** num), num
    else:
        linear, log = num, (math.log10(num) if num > 0 else None)
    # whole-number levels are written out in full (no %g scientific
    # notation: 4450000, not 4.45e+06)
    shown = (str(int(linear)) if float(linear).is_integer()
             else _g(linear))
    if log is None:
        return f"HBV DNA {shown}"
    lg = f"{log:.2f}".rstrip("0").rstrip(".")
    return f"HBV DNA {shown}/{lg}"


def _hcv_rna_token(items):
    """The HCV RNA token (rule 22a), the same shorthand as the HBV
    DNA token: `HCV RNA neg` for a not-detected result (Quest's
    `<15 NOT DETECTED`, LabCorp's `HCV Not Detected` text counts);
    `HCV RNA <{lim}` for a result detected below the quantification
    limit (a limit reported in log10 is rendered as 10**lim); and
    `HCV RNA {linear}/{log}` for a numeric level.  The first item
    decides, like the HBV DNA: Quest's layout reports the linear
    `IU/mL` item first (its log10 is computed: `53` IU/mL -> `HCV
    RNA 53/1.72`), and a value reported in log10 is reconstructed as
    10**value, rounded to a whole number.  A pending / empty value
    (Quest's `TNP`) produces nothing; the `COMMENT` / `Test
    Information:` note items are not it."""
    it = items[0]
    value = str(it.get("value") or "").strip()
    if not value:
        return ""
    is_log = "log" in str(it.get("units") or "").lower()
    low = value.lower()
    if "tnp" in low:
        return ""
    if "not detected" in low or low in ("negative", "non-reactive",
                                        "non reactive"):
        return "HCV RNA neg"
    m = re.search(r"(\d+(?:\.\d+)?)", value)
    if "detected" in low or value.startswith("<"):
        if m:
            lim = float(m.group(1))
            if is_log:
                lim = 10.0 ** lim
            return f"HCV RNA <{_g(lim)}"
        return "HCV RNA det" if "detected" in low else ""
    if m is None:
        return ""
    num = float(m.group(1))
    if is_log:
        linear, log = round(10.0 ** num), num
    else:
        linear, log = num, (math.log10(num) if num > 0 else None)
    shown = (str(int(linear)) if float(linear).is_integer()
             else _g(linear))
    if log is None:
        return f"HCV RNA {shown}"
    lg = f"{log:.2f}".rstrip("0").rstrip(".")
    return f"HCV RNA {shown}/{lg}"


def _qualitative_label(value, label):
    if value in _POSITIVE_VALUES:
        return f"{label}+"
    if value in _NEGATIVE_VALUES:
        return f"{label} neg"
    return None


def _qualitative_token(items, names, prefix):
    """`{prefix}+` or `{prefix} neg`. Used for eAg, HBcAb, and HDV."""
    item = _first_item(items, names)
    if item is None:
        return None
    return _qualitative_label(item["value"].strip().lower(), prefix)


# Quest and LabCorp respectively
_EAG_ITEMS = ["hepatitis be antigen", "hep be ag"]


def _eag_state(latest):
    """`neg` / `pos` / None by value."""
    item = _first_item(latest.get("eag", []), _EAG_ITEMS)
    if item is None:
        return None
    value = item["value"].strip().lower()
    if value in _POSITIVE_VALUES:
        return "pos"
    if value in _NEGATIVE_VALUES:
        return "neg"
    return None


def _afp_normal(items):
    return not _is_abnormal(items[0]["flag"])


def _eag_afp_token(latest):
    """`eAg/AFP neg` when both negative, else `eAg neg` / `eAg+`."""
    state = _eag_state(latest)
    if state == "pos":
        return "eAg+"
    if state != "neg":
        return None
    if "afp" in latest and _afp_normal(latest["afp"]):
        return "eAg/AFP neg"
    return "eAg neg"


def _hb_htlv_tokens(latest):
    specs = (
        ("hb_elec", "Hb electrophoresis", ["hemoglobin (hgb) solubility"]),
        ("htlv", "HTLV", ["htlv-i/ii antibodies, qual"]),
    )
    normal, positive = [], []
    for category, label, item_names in specs:
        if category not in latest:
            continue
        item = _first_item(latest[category], item_names)
        if item is None:
            continue
        value = item["value"].strip().lower()
        if value in _POSITIVE_VALUES:
            positive.append(f"{label}+")
        elif value in _NEGATIVE_VALUES:
            normal.append(label)

    tokens = [f"{'/'.join(normal)} neg"] if normal else []
    tokens.extend(positive)
    return tokens


def _hbv_infected(latest):
    """True when the patient has (chronic) HBV infection: a positive
    surface-Ag screen or a detected HBV DNA level. A negative surface
    Ab in such a patient reports `HBV Ab neg` (serology) instead of
    the RTC HBV vacc component -- the vaccine does not help an
    infected patient (20739 / 20939's `HBsAg+, HBV DNA detected,
    HBV Ab neg` sticky lines)."""
    if _abnormal_items(latest.get("hbsag", [])):
        return True
    if "hbv_dna" in latest:
        token = _hbv_dna_token(latest["hbv_dna"])
        if token is not None and token != "HBV DNA neg":
            return True
    return False


def _hbv_ab_state(latest):
    """`pos` / `neg` for the newest surface-Ab result, `None` when it
    gives no signal (a pending / number-less result). The quantitative
    order wins when both are present: above 10 mIU/mL is immune;
    otherwise the qualitative order's value decides (`REACTIVE` /
    `Positive` pos, a negative or `BORDERLINE` value neg -- the band
    does not confirm immunity)."""
    if "hbsabq" in latest:
        item = _first_item(latest["hbsabq"], ["hepatitis b surf ab quant"])
        if item is None:
            return None
        ab = _first_num(item["value"].strip())
        if ab is None:
            return None
        return "pos" if ab > 10.0 else "neg"

    if "hbsab" in latest:
        names = ["hepatitis b surface antibody ql", "hep b surface ab, qual"]
        item = _first_item(latest["hbsab"], names)
        if item is None:
            return None
        value = item["value"].strip().lower()
        if value in _POSITIVE_VALUES:
            return "pos"
        # the in-house BORDERLINE band does not confirm immunity, so
        # it counts as needing the vaccine (like HAV's BORDERLINE)
        if value in _NEGATIVE_VALUES or value == "borderline":
            return "neg"
    return None


def _hbsab_token(latest):
    """`HBV Ab+` when the surface Ab is reactive or immune (above
    10 mIU/mL). A non-immune surface Ab reports `HBV Ab neg` when the
    patient has HBV infection (rule 24c: the vaccine does not help an
    infected patient); otherwise it contributes the `HBV` component
    to the `RTC ... vacc` token (rule 25)."""
    state = _hbv_ab_state(latest)
    if state == "pos":
        return "HBV Ab+"
    if state == "neg" and _hbv_infected(latest):
        return "HBV Ab neg"
    return None


def _hav_hbv_ab_tokens(latest):
    """The rules-24c/25 Ab+ tokens: one `HAV/HBV Ab+` when both the
    HAV total Ab and the HBV surface Ab are positive, else the
    individual `HBV Ab+` / `HAV Ab+` tokens, HBV first (a negative /
    infected `HBV Ab neg` condenses nothing)."""
    hbsab = _hbsab_token(latest)
    hav = _hav_token(latest["hav"]) if "hav" in latest else None
    if hbsab == "HBV Ab+" and hav == "HAV Ab+":
        return ["HAV/HBV Ab+"]
    return [t for t in (hbsab, hav) if t]


def _hpylori_token(items):
    if _abnormal_items(items):
        return "H pylori+"
    for item in items:
        if value := item["value"].strip().lower():
            return "H pylori neg" if value in _NEGATIVE_VALUES else None


def _stool_token(items):
    if not items:
        return None
    if _abnormal_items(items):
        return "stool occult+"
    for item in items:
        value = item["value"].strip().lower()
        if not value:
            continue
        return "stool occult neg" if value in _NEGATIVE_VALUES else None
    return "stool occult neg"


_STOOL_CX_SPECS = (
    ("stool_cx_campy", None, "Campylobacter"),
    ("stool_cx_ecoli", "no escherichia coli o157 isolated", "E. coli O157:H7"),
    ("stool_cx_salm", "no salmonella or shigella isolated", "Salmonella/Shigella"),
)


def _stool_cx_state(items, negative_note):
    item = _first_item(items, ["culture"])
    if item is None:
        return None

    if _is_abnormal(item["flag"]):
        return "pos"

    value = item["value"].strip().lower()
    if value == "not isolated":
        return "neg"
    if value == "isolated":
        return "pos"
    if value:
        return None

    notes = (item.get("notes") or "").lower()
    if negative_note and negative_note in notes:
        return "neg"
    return None


def _stool_cx_tokens(latest) -> list[str]:
    """Return positive pathogen tokens (`+`), `['stool culture neg']` when
    all present cultures are negative, or `[]` otherwise.
    """
    states = [
        (label, _stool_cx_state(latest[key], note))
        for key, note, label in _STOOL_CX_SPECS
        if key in latest
    ]
    if not states:
        return []

    positive = [f"{label}+" for label, state in states if state == "pos"]
    if positive:
        return positive

    if all(state == "neg" for _, state in states):
        return ["stool culture neg"]

    return []


def _stool_ova_state(items):
    """`neg` / `pos` for one ova-and-parasite order's result, or
    `None` when the result is pending / unrecognized (rule 36b).
    The Quest layout (`Stool Ova and Parasite`) carries the smear
    result lines (`CONCENTRATION 1: ...`, `TRICHROME 1: ...`) on the
    order's item -- its reference-range line also carries the `No
    ova or parasites seen` text, so the smear lines decide: a `No
    ova or parasites seen` line is a negative smear, a seen-line
    naming anything else a positive one.  The LabCorp layout's
    (`Stool Ova + Parasite Exam`) result item is the `Result 1`
    item, whose note is the result text itself (`No ova, cysts, or
    parasites seen`)."""
    it = _first_item(items, "result 1") or items[0]
    value = it["value"].strip()
    if value:
        low = value.lower()
        if low in _NEGATIVE_VALUES:
            return "neg"
        if low in _POSITIVE_VALUES or _is_abnormal(it["flag"]):
            return "pos"
        return None
    if _is_abnormal(it["flag"]):
        return "pos"

    # parse notes
    notes = it["notes"].lower()
    states = []
    for line in notes.splitlines():
        label, sep, text = line.partition(":")
        if not sep or not label.strip().lower().startswith(
                ("concentration", "trichrome")):
            continue
        if text.strip().startswith("no ova or parasites"):
            states.append("neg")
        elif "seen" in text:
            states.append("pos")
    if states:
        return "pos" if "pos" in states else "neg"
    if "no ova, cysts, or parasites seen" in notes:
        return "neg"
    if "seen" in notes:
        return "pos"
    return None


def _stool_ag_state(items):
    """`neg` / `pos` for one stool-antigen order's result (the
    giardia / cryptosporidium EIA orders, rule 36b), or `None` when
    the result is pending / unrecognized.  The single item's empty
    value is a negative result when its note carries the `Not
    Detected` text; a `Detected` value / note or a flagged item is a
    positive one."""
    it = items[0]
    value = it["value"].strip()
    if value:
        low = value.lower()
        if low in _NEGATIVE_VALUES:
            return "neg"
        if (low == "detected" or low in _POSITIVE_VALUES
                or _is_abnormal(it["flag"])):
            return "pos"
        return None
    if _is_abnormal(it["flag"]):
        return "pos"
    notes = " ".join(it["notes"].lower().split())
    if "not detected" in notes:
        return "neg"
    if "detected" in notes:
        return "pos"
    return None


def _stool_para_tokens(latest):
    """The stool-parasite tokens (rule 36b): one `stool {label} neg`
    token per present negative ova-and-parasite / giardia /
    cryptosporidium order -- `stool O-P neg` / `stool Giardia neg` /
    `stool Cryptosporidium neg`, in that order -- and one `{label}+`
    token per positive order (`O-P+` / `Giardia+` /
    `Cryptosporidium+`); the negative members are not reported next to
    a positive one.  Pending / unrecognized orders produce nothing (a
    lone negative next to a pending one reports nothing either)."""
    states = [
        (label, state(latest[key]))
        for key, state, label in (
            ("stool_ova", _stool_ova_state, "O-P"),
            ("stool_giardia", _stool_ag_state, "Giardia"),
            ("stool_crypto", _stool_ag_state, "Cryptosporidium"),
        )
        if key in latest
    ]
    if not states:
        return []
    positive = [f"{label}+" for label, state in states if state == "pos"]
    if positive:
        return positive
    if all(state == "neg" for _, state in states):
        return [f"stool {label} neg" for label, state in states]
    return []


def _stool_cdiff_token(items):
    """`C diff neg` when the C. diff toxin result is negative / not
    detected (the order's single item carries an empty value whose
    note carries the `Toxin A and B: Not Detected` line and the `No
    toxigenic C. difficile detected` comment); `C diff+` when
    positive / detected; a pending / empty value produces nothing
    (rule 36c)."""
    it = items[0]
    value = it["value"].strip()
    if value:
        low = value.lower()
        if low in _NEGATIVE_VALUES:
            return "C diff neg"
        if (low == "detected" or low in _POSITIVE_VALUES
                or _is_abnormal(it["flag"])):
            return "C diff+"
        return None
    if _is_abnormal(it["flag"]):
        return "C diff+"
    # the note's lines are column-aligned (`Toxin A and B:     Not
    # Detected`), so the whitespace is collapsed before matching
    notes = " ".join(it["notes"].lower().split())
    if ("toxin a and b: not detected" in notes
            or "no toxigenic c. difficile detected" in notes):
        return "C diff neg"
    if "toxin a and b: detected" in notes:
        return "C diff+"
    return None


ct_cac_names = (
    "ct cardiac scoring",
    "ct cardiac calcium score plus",
    "cardiac calcium score plus",
)


def build_lab_summary(labs):
    """Build the /patient one-line lab summary from lab rows.

    `labs` is a sequence of row mappings (keys `name`, `result`,
    `result_date`, `date`; see the module docstring for the full
    contract: newest-first ordering, result parsing, the per-category
    token rules and their fixed output order, the `mm/yyyy` leading
    date, and the `""` return when nothing qualifies).
    """
    if not labs:
        return ""

    # Rows with a usable result, in the caller's newest-first order.
    rows = []
    # The newest CT cardiac-scoring row's report notes or None;
    # the newest mammogram row's report notes or None;
    # the newest row per US region label's report notes (rule 9c);
    # the newest bone-density row whose report names a T-score (rule
    # 9d) or None;
    # the newest row per CT region label's report notes (rule 9e);
    # `first` is the newest row that contributes to the summary (a row
    # with result items, or a CAC / mammo / BMD / US / CT row with
    # report notes).
    ct_notes = None
    mammo_notes = None
    bmd_notes = None
    us_notes = {}
    ct_scan_notes = {}
    first = None
    for row in labs:
        # the interface's `$` separator (kept in row and item names, the
        # 'By Patient (All)' screen renders it as a space) is normalised so
        # rows written by either update_lab_result() / update_patient_labs()
        # match the same names
        name = (row.get("name") or "").strip().lower().replace("$", " ")
        if name in ct_cac_names:
            if ct_notes is None:
                notes = _imaging_notes(row.get("result"))
                if notes:
                    ct_notes = notes
                    if first is None:
                        first = row
            continue
        if re.search(r"mammo|mamo", name):
            if mammo_notes is None:
                notes = _imaging_notes(row.get("result"))
                if notes:
                    mammo_notes = notes
                    if first is None:
                        first = row
            continue
        if re.match(r"^us\b", name):
            notes = _imaging_notes(row.get("result"))
            if notes:
                label = us_label(name)
                if label not in us_notes:
                    # a `refer to ... report` deferral is not used for
                    # the region's newest result
                    if us_findings(notes)[1]:
                        us_notes[label] = notes
                        if first is None:
                            first = row
            continue
        if re.search("bone density", name):
            if bmd_notes is None:
                notes = _imaging_notes(row.get("result"))
                if notes and _bmd_sites(notes):
                    # skip a report that names no T-score
                    bmd_notes = notes
                    if first is None:
                        first = row
            continue
        if re.match(r"^ct[\s\-]*(?:chest|head|abdomen)\b", name):
            notes = _imaging_notes(row.get("result"))
            if notes:
                label = ct_label(name)
                if label not in ct_scan_notes:
                    # skip a report without an `IMPRESSION` section
                    if ct_findings(notes)[1]:
                        ct_scan_notes[label] = notes
                        if first is None:
                            first = row
            continue
        items = _parse_items(row.get("result"))
        if items is not None:
            rows.append((row, items))
            if first is None:
                first = row
    if (not rows and ct_notes is None and mammo_notes is None
            and bmd_notes is None and not us_notes
            and not ct_scan_notes):
        return ""

    # The newest (first) row per category.
    latest = {}
    for row, items in rows:
        name = (row.get("name") or "").strip().lower().replace("$", " ")
        for category, names in _CATEGORY_NAMES.items():
            if name in names and category not in latest:
                latest[category] = items

    gc_states = _gc_pathogen_states(rows)

    tokens = []

    def add(token):
        if token:
            tokens.append(token)

    # Fixed token order (see the module docstring).
    if "ua" in latest:
        add(_ua_token(latest["ua"]))
    if "ucx" in latest:
        add(_ucx_token(latest["ucx"]))
    if "hcg" in latest:
        add(_hcg_token(latest["hcg"]))
    if "tsh" in latest:
        add(_tsh_token(latest))
    for token in _thyroid_cluster_tokens(latest):
        add(token)
    if "fsh" in latest:
        add(_flag_token("FSH", latest["fsh"]))
    if "estradiol" in latest:
        add(_named_flag_token(latest["estradiol"], ["estradiol"], "Estradiol"))
    if "testo" in latest:
        for token in _testo_tokens(latest["testo"]):
            add(token)
    if "cortisol" in latest:
        # a high cortisol is marked by its bound only, not a `+`
        add(_flag_token("cortisol", latest["cortisol"], sign=False))
    if "prolactin" in latest:
        add(_flag_token("prolactin", latest["prolactin"]))
    if "lh" in latest:
        add(_named_flag_token(latest["lh"], ["lh", "lh (luteinizing hormone)"], "LH", _int_value))
    if "progesterone" in latest:
        add(_flag_token("Progesterone", latest["progesterone"]))
    if "amh" in latest:
        amh_items = [
            "anti-mullerian hormone (amh), female",
            "anti-mullerian hormone (amh)",
        ]
        add(_named_flag_token(latest["amh"], amh_items, "AMH", _g))
    if "metanephrine" in latest:
        for token in _metanephrine_tokens(latest["metanephrine"]):
            add(token)
    if "a1c" in latest:
        glu = _first_value(latest["liver"], _GLUCOSE_ITEMS) if "liver" in latest else None
        token = _a1c_token(latest["a1c"], glu)
        if not token and "liver" in latest:
            # a pending / empty A1c leaves the panel's glucose
            # unpaired: report it like the standalone order's
            token = _named_item_token(latest["liver"], _GLUCOSE_ITEMS,
                                      "Glu", _g, sign=False)
        add(token)
    elif "liver" in latest:
        # no A1c order: the panel's glucose stands in for the
        # standalone-glucose token of rule 5a
        add(_named_item_token(latest["liver"], _GLUCOSE_ITEMS, "Glu", _g,
                              sign=False))
    if "glu" in latest:
        add(_named_item_token(latest["glu"], _GLUCOSE_ITEMS, "Glu", _g,
                              sign=False))
    if "albcr" in latest:
        add(_albc_token(latest["albcr"]))
    if "lipid" in latest:
        add(_hdl_token(latest["lipid"]))
        add(_ldl_token(latest["lipid"]))
    if "lpa" in latest:
        add(_named_flag_token(latest["lpa"], ["lipoprotein (a)"], "LpA", _int_value))
    if "apob" in latest:
        add(_named_flag_token(latest["apob"], ["apolipoprotein b"], "ApoB"))
    if ct_notes is not None:
        add(_ct_cac_token(ct_notes))
        add(_ct_cac_aorta_token(ct_notes))
        for token in _ct_cac_vessel_tokens(ct_notes):
            add(token)
        for token in _ct_cac_nodule_tokens(ct_notes):
            add(token)
    if mammo_notes is not None:
        add(_mammo_token(mammo_notes))
    if us_notes:
        us_labels = (
            "abd w/ liver elastography", "abd", "breast", "thyroid", "renal",
            "pelvic", "carotid", "AAA", "neck", "testicular", "soft tissue",
        )
        for label in us_labels:
            if label in us_notes:
                add(us_token(us_notes[label], label))
        for label in us_notes:
            if label not in us_labels:
                add(us_token(us_notes[label], label))
    if bmd_notes is not None:
        add(_bmd_token(bmd_notes))
    if ct_scan_notes:
        ct_label_order = ("chest", "head", "abd/pelvic", "abd")
        for label in ct_label_order:
            if label in ct_scan_notes:
                add(ct_token(ct_scan_notes[label], label))
        for label in ct_scan_notes:
            if label not in ct_label_order:
                add(ct_token(ct_scan_notes[label], label))
    if "cbc" in latest:
        add(_named_item_token(latest["cbc"], ["red blood cell count", "rbc"], "RBC", _round1))
        add(_cbc_mcv_token(latest["cbc"]))
        add(_named_item_token(latest["cbc"], ["white blood cell count", "wbc"], "WBC", _round1))
        add(_named_item_token(latest["cbc"], ["hemoglobin"], "Hb", _round1))
        add(_named_item_token(latest["cbc"], _PLT_ITEMS, "Plt", _g))
        eos_items = [
            "absolute eosinophils",  # Quest cells/uL, range `15-500`
            "eos (absolute)",  # LabCorp, x10E3/uL, range `0.0-0.4`
        ]
        add(_named_item_token(latest["cbc"], eos_items, "Eos", _g))
    if "plt_est" in latest:
        # like the A1c's liver-panel glucose: cross-category state is
        # recomputed from `latest` at the call site
        cbc_plt = _named_item_token(latest["cbc"], _PLT_ITEMS, "Plt", _g) if "cbc" in latest else None
        add(_plt_est_token(latest["plt_est"], cbc_plt))
    if "vitd" in latest:
        add(_vitd_token(latest["vitd"]))
    if "pth" in latest:
        add(_pth_token(latest["pth"]))
    if "ica" in latest:
        add(_flag_token("Free Calcium", latest["ica"]))
    if "mg" in latest:
        add(_flag_token("Mg", latest["mg"]))
    if "mg_rbc" in latest:
        add(_flag_token("Mg RBC", latest["mg_rbc"]))
    if "phos" in latest:
        add(_flag_token("Phos", latest["phos"]))
    if "zinc" in latest:
        add(_flag_token("zinc", latest["zinc"]))
    if "zinc_rbc" in latest:
        add(_flag_token("zinc RBC", latest["zinc_rbc"]))
    if "uric" in latest:
        add(_uric_token(latest["uric"]))
    if "psa" in latest:
        for token in _psa_tokens(latest["psa"]):
            add(token)
    if "inrpt" in latest:
        for token in _inrpt_tokens(latest["inrpt"]):
            add(token)
    if "ptt" in latest:
        ptt_items = [
        "partial thromboplastin time, activated",
        "partial thromboplastin time, activated",  # Quest
        ]
        add(_named_flag_token(latest["ptt"], ptt_items, "PTT", sign=False))
    if "bnp" in latest:
        bnp_items = [
        "b-type natriuretic peptide",
        "b type natriuretic peptide (bnp)",
        ]
        add(_named_flag_token(latest["bnp"], bnp_items, "BNP"))
    add(_std_token(latest, gc_states))
    add(_hbv_neg_token(latest))
    add("HBsAg+" if _abnormal_items(latest.get("hbsag", [])) else None)
    add("HCV+" if _abnormal_items(latest.get("hcv", [])) else None)
    add("HIV+" if _hiv_positive(latest.get("hiv", [])) else None)
    add("RPR+" if _rpr_positive(latest.get("rpr", [])) else None)
    for token in _hsv_tokens(latest):
        add(token)
    for token in _gc_tokens(gc_states):
        add(token)
    add(_treponema_state(latest))
    if "hbv_dna" in latest:
        add(_hbv_dna_token(latest["hbv_dna"]))
    if "hcv_rna" in latest:
        add(_hcv_rna_token(latest["hcv_rna"]))
    if "eag" in latest:
        add(_eag_afp_token(latest))
    if "hbcab" in latest:
        # Quest and LabCorp respectively
        hbcab_items = ["hepatitis b core ab total", "hep b core ab, tot"]
        add(_qualitative_token(latest["hbcab"], hbcab_items, "HBcAb"))
    if "hdv" in latest:
        # emit HDV token by itself if not both `HIV/HDV neg`
        joined = ("hiv" in latest and _hiv_negative(latest["hiv"])
                  and _hdv_negative(latest["hdv"]))
        if not joined:
            add(_qualitative_token(
                latest["hdv"],
                ["hepatitis d antibody,", "hdv antibody, igg/igm"], "HDV"))
    for token in _hb_htlv_tokens(latest):
        add(token)
    for token in _hav_hbv_ab_tokens(latest):
        add(token)
    if "hav_igm" in latest:
        add(_hav_igm_token(latest["hav_igm"]))
    if not _mmr_needed(latest):
        # If needed we only report `RTC MMR vacc`
        for token in _mmr_ab_tokens(latest):
            add(token)
    if "varicella" in latest:
        add(_varicella_token(latest["varicella"]))
    if "iron" in latest:
        add(_iron_token(latest["iron"]))
    # ferritin always rides next to the iron token (rule 27a), even
    # when normal; with no panel it covers the standalone order
    add(_ferritin_token(latest))
    if "iron_standalone" in latest:
        add(_named_item_token(latest["iron_standalone"], ["iron, total", "iron, serum"], "iron", _g))
    if "copper" in latest:
        add(_flag_token("copper", latest["copper"], _g, sign=False))
    if "b12" in latest:
        add(_b12_token(latest["b12"]))
    for token in _b1b6_tokens(latest):
        add(token)
    if "b2" in latest:
        add(_flag_token("B2", latest["b2"]))
    if "fa" in latest:
        fa_names = [
            "folate, serum",
            "folate (folic acid), serum",
            "folate",
        ]
        add(_named_flag_token(latest["fa"], fa_names, "FA", _g))
    if "liver" in latest:
        add(_astalt_token(latest["liver"]))
        add(_protein_token(latest["liver"]))
        add(_named_item_token(latest["liver"], ["urea nitrogen (bun)", "bun"], "BUN", _g, sign=False))
        add(_cr_token(latest["liver"]))
        add(_named_item_token(latest["liver"], ["bilirubin, total"], "bilirubin", _g))
        add(_named_item_token(latest["liver"], ["alkaline phosphatase", "alkaline phosphatase, s"], "AP", _g))
        add(_named_item_token(latest["liver"], ["albumin", "albumin, serum"], "albumin", _g))
        for token in _liver_electrolyte_tokens(latest["liver"]):
            add(token)
    if "ggt" in latest:
        add(_named_item_token(latest["ggt"], ["ggt"], "GGT", _g))
    if "ck" in latest:
        add(_flag_token("CK", latest["ck"], _g))
    if "amylase" in latest:
        add(_named_flag_token(latest["amylase"], ["amylase", "amylase, serum"], "amylase"))
    if "lipase" in latest:
        add(_flag_token("lipase", latest["lipase"]))
    if "ana" in latest:
        add(_ana_token(latest["ana"]))
    for token in _esrcrp_tokens(latest):
        add(token)
    if "rf" in latest:
        add(_named_flag_token(latest["rf"], ["rheumatoid factor"], "RF"))
    if "ccp" in latest:
        add(_named_flag_token(latest["ccp"], ["cyclic citrullinated peptide (ccp) ab (igg)"], "Anti-CCP"))
    if "c3c4" in latest:
        for token in _c3c4_tokens(latest["c3c4"]):
            add(token)
    if "dsdna" in latest:
        add(_dsdna_token(latest["dsdna"]))
    if "crp_cardiac" in latest:
        add(_named_flag_token(latest["crp_cardiac"], ["c-reactive protein, cardiac", "hs crp"], "hsCRP", _g))
    if "hpylori" in latest:
        add(_hpylori_token(latest["hpylori"]))
    if "stool" in latest:
        add(_stool_token(latest["stool"]))
    for token in _stool_cx_tokens(latest):
        add(token)
    for token in _stool_para_tokens(latest):
        add(token)
    if "stool_cdiff" in latest:
        add(_stool_cdiff_token(latest["stool_cdiff"]))
    if "afp" in latest:
        # a normal AFP joins a negative eAg's `eAg/AFP neg` token
        # (rule 23): no separate `AFP nl`
        if not ("eag" in latest and _eag_state(latest) == "neg"
                and _afp_normal(latest["afp"])):
            add(_flag_token("AFP", latest["afp"]))
    if "cea" in latest:
        add(_flag_token("CEA", latest["cea"]))
    if "ca125" in latest:
        add(_flag_token("CA 125", latest["ca125"]))
    if "ca199" in latest:
        add(_named_flag_token(latest["ca199"], ["ca 19-9"], "CA 19-9"))
    if "ldh" in latest:
        add(_named_flag_token(latest["ldh"], ["ldh", "ld"], "LDH"))
    if "qtb" in latest:
        add(_qtb_token(latest["qtb"]))
    if "shield" in latest:
        add(_shield_token(latest["shield"]))
    if "abo" in latest:
        add(_abo_token(latest["abo"]))
    for token in _allergy_tokens(latest):
        add(token)
    add(_vacc_token(latest))

    if not tokens:
        return ""

    # Leading mm/yyyy from the newest contributing row: result_date,
    # else order date.
    prefix = ""
    for key in ("result_date", "date"):
        value = first.get(key)
        if not value:
            continue
        try:
            when = date.fromisoformat(str(value).strip()[:10])
        except ValueError:
            continue
        prefix = f"{when.month:02d}/{when.year}- "
        break
    return prefix + ", ".join(tokens)
