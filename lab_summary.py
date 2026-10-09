"""Build the one-line lab summary shown on the /patient page.

The /patient page shows a compact summary of the patient's most recent
labs: one token per category, in a fixed order, using the same
shorthand that gets written into the patient's yellow sticky note, eg

    11/2026- UA nl, TSH 2.5, A1c 6, LDL 104, LpA nl, uric acid 6.8, HBV/HCV neg

`build_lab_summary()` is a pure function mapping patient lab rows to a string.

Input
-----
`labs` is a sequence of mappings (e.g. `dict`s built from `lab`
table rows), **newest first**.  The caller is responsible for ordering
the rows exactly like the /patient labs table does::

    ORDER BY result_date DESC NULLS LAST, id DESC

The function trusts that order: within each category, the *first*
matching row is that patient's most recent result for the category,
and older rows of the same category are ignored.

For each row the function reads:

`name` (str or None)
    The lab test name (`lab.name`), e.g. `"UA, Routine"` (LabCorp)
    or `"UA, urine routine"` (Quest), `"TSH reflex to T4F"`
    (LabCorp), `"TSH W/REFLEX TO FT4"` (Quest) or `"TSH+FREE T4"`
    (Quest, a layout that reports the T4 as well), `"TSH"` (the
    standalone order, both vendors) or `"Free T4"` (a standalone
    free-T4 draw), `"Culture Urine, Routine"` (LabCorp).  Matching
    is done after stripping and lower-casing, so `"ua, routine"`
    and `"UA, Routine"` are the same category.
`result` (str or None)
    The lab's JSON result text (`lab.result`): a JSON array of item
    dicts, each with at least `itemName` and `value` plus a
    `flag` (Quest sends `"N"`/`"A"`; LabCorp mostly leaves the
    flag empty on normal items and sends `"H"`/`"L"`/`"A"` on
    abnormal ones), a reference `range` (e.g. `232-1245`) that may
    be empty, and a `paramNotes` result note (used only by the
    stool-culture rule, 36a, which reads the in-house orders'
    `No ... isolated` negative text out of it).
`result_date` (str or None)
    ISO result date (`YYYY-MM-DD`); used for the leading `mm/yyyy`.
`date` (str or None)
    ISO order date; only used as a fallback for the leading `mm/yyyy`
    when the newest row's `result_date` is missing or unparseable.

Any other key on the rows is ignored and missing keys are treated as
`None`.

We ignore rows with no usable lab/result, such as imaging rows like
`CT CARDIAC SCORING` or bone density that carry no result JSON.

Rules
-----
For each category below, the *first* row (newest first) whose
case-insensitive `name` is in the category's name list and which has
a usable result is the row for that category. An item counts as
*abnormal* when its `flag` is nonempty and not N.

Abnormal tokens carry the violated reference-range limit in
parentheses, eg `42(35)`: the upper limit for an `H` flag, the lower
limit for an `L` flag, via `_bound_for`; without a parsable bound the
token is plain `{val}`.  Values are written raw, to one decimal
(`_round1`, ties half up), with trailing zeros stripped (`%g`), or as
integers, as noted per rule.

Tokens are emitted in this fixed order and joined with `, `; a
category whose rule produces nothing is simply skipped:

1. **UA**. Normal: `UA nl`. Abnormal: `UA ` + the abnormal items in
   report order as short tokens joined with `, `: `pH {num}` /
   `pH<{num}` / `pH>{num}` for pH, `crystals+` for an abnormal
   crystals item, and `{name} {value}` in lower case (a `trace` value
   gains a `+`, eg `protein trace+`) for the rest.  The items and
   item/value pairs in `_UA_IGNORED_NAMES` / `_UA_IGNORED` (squamous
   epithelial cells, `Bacteria` = `Few`, `Ketones` = `Trace` or
   `2+`, `WBC Esterase` = `Trace`, `Occult Blood` = `Trace`) are not
   reported.
1a. **Ucx** (the urine culture).  The culture's result item decides
   (LabCorp's `Result 1`, the in-house order's item named after the
   order, Quest's `REFLEXIVE URINE CULTURE`): `Ucx neg` for a
   negative value (`No growth` and its friends); `Ucx {value}` for
   any other nonempty value, the organism text written as reported on
   the report (the yellow notes write a positive culture as `Ucx
   Staphy`, `Ucx- E Coli`, `Ucx+ Klebsiella`, ...).  A pending / empty
   value (the in-house culture item and Quest's reflex item both carry
   no value until a result is in) and a UA-with-reflex order whose
   reflex never fired (no culture item) produce nothing.
2. **TSH** (the `TSH W/REFLEX TO FT4` / `TSH reflex to T4F` /
   `TSH+FREE T4` / `TSH rfx on abnormal to free T4` layouts, the
   standalone `TSH` orders and LabCorp's `Thyroid Cascade
   Profile`).  Always emit `TSH {val}` (one decimal; raw value when
   not a number) from the result's first item; when the result also
   carries a free-T4 item, append `/T4 nl` for a normal T4 or `/T4
   {val}` for an abnormal one; when it does not (the standalone and
   cascade layouts), the newest standalone `free t4` order's item
   supplies the same suffix (the yellow notes write `TSH 2.1/T4 nl`
   for a standalone `TSH` order drawn next to a normal standalone
   free T4).
2a. **Thyroid cluster** (the thyroid tests besides the TSH of rule
   2): free T3 (Quest's `free t3` order, LabCorp's `free t3, serum`
   order), standalone free T4 (the `free t4` order, both vendors),
   the TPO and thyroglobulin antibodies (LabCorp's `Thyroid
   Peroxidase (TPO) Ab` and `Thyroid Antibodies` orders and Quest's
   `thyroid peroxidase and thyroglobulin antibodies` panel, plus the
   standalone `Thyroglobulin Antibod(y/ies)` orders for the TgAb
   alone) and TSI (Quest's `thyroid stim immunoglobulin` and `tsi
   (thyroid stimulating$immunoglobulin)` orders).  The normal members
   join one token, their labels -- in the fixed member order `T4`,
   `T3`, `TPO`, `thyroglobulin`, `TSI` (the yellow notes' labels;
   they write the TgAb as `thyroglobulin`) -- joined with `/` plus a
   single trailing ` nl` (e.g. `TPO/thyroglobulin nl`, `TSI nl`);
   each abnormal member reports its own `{label} {val}({bound})`
   token right after that one (value raw, bound via `_bound_for`),
   in the same member order.  A standalone free T4 is not a member
   when it supplied the TSH token's `/T4` suffix (a TSH row whose
   result carries no free-T4 item of its own).  A member whose
   newest row has no usable item / value produces nothing.
3. **FSH**. Normal: `FSH nl`. Abnormal: `FSH {val}({bound})`.
4. **Estradiol**. Normal: `Estradiol nl`. Abnormal: `Estradiol
   {val}({bound})`.
5. **A1c**. Always emit `A1c {val}` (trailing zeros stripped); with a
   usable glucose result from the liver panel, `Glu {glu}/A1c {val}`.
5a. **Standalone glucose**. Normal: omit. Abnormal: `Glu {val}({bound})`.
6. **Alb/Cr**. Normal: `Alb/Cr<30`. Abnormal: `Alb/Cr {val}`.
7. **LDL**. `LDL {val}` (the calculated-LDL item's raw value, normal
   and abnormal panels alike); when the panel's triglycerides are
   high, `{HDL}/{LDL}/{TG}({bound})` instead (the plain `LDL {val}`
   is kept when the HDL or LDL value is missing).  A panel without a
   calculated-LDL item produces nothing.
8. **LpA**. Normal: `LpA nl`. Abnormal: `LpA {val}({bound})` (the
   value rendered as an integer).
9. **ApoB**. Normal: `ApoB nl`. Abnormal: `ApoB {val}({bound})`.
10. **CBC**. Normal: omit. Abnormal: `RBC {val}({bound})`.
10a. **MCV (same CBC rows)**. Normal: omit. Abnormal: `MCV {val}({bound})`
     (trailing zeros stripped), for a violated limit in either
     direction.
10b. **WBC / Hb / Plt / Hct (same CBC rows)**. Normal: omit.
     Abnormal: one token per abnormal item, in that order,
     `WBC` / `Hb` / `Plt` / `Hematocrit` as `{label} {val}({bound})`
     (WBC and Hb to one decimal, Plt and Hct with trailing zeros
     stripped).
10c. **Eos (same CBC rows)** -- the *absolute* eosinophil item only
     (the percentage items carry no usable range).  Normal: omit.
     Abnormal: `Eos {val}({bound})` (trailing zeros stripped).
11. **VitD**. Always emit `VitD {val}` (the value rendered as an
    integer).
12. **PTH**. Normal: `PTH nl`. Abnormal: `PTH {val}({bound})`.
13. **Mg**. Normal: `Mg nl`. Abnormal: `Mg {val}({bound})`.
14. **Phos**. Normal: `Phos nl`. Abnormal: `Phos {val}({bound})`.
15. **Zinc**. Normal: `zinc nl`. Abnormal: `zinc {val}({bound})`.
16. **Uric acid**. Normal only: `uric acid {val}` with the item's raw
    value.
17. **PSA**. Always emit `PSA {val}` (trailing zeros stripped).
18. **INR / PT**. One token per abnormal item, `INR` first: `INR {val}({bound})`
    / `PT {val}({bound})` (trailing zeros stripped; the `INR` item
    usually carries no reference range, so plain `INR {val}`).
    Normal: `INR/PT nl` when both items are present, `INR nl` /
    `PT nl` when only one is.
19. **PTT**. Normal: `PTT nl`. Abnormal: `PTT {val}({bound})`.
20. **BNP**. Normal: `BNP nl`. Abnormal: `BNP {val}({bound})`.
21. **HBV/HCV/HIV/RPR/G-C/Treponema** -- the standard-infection-
    marker groups.  The token joins the groups that are present and
    negative, in that order, with `/` plus a trailing ` neg` (all
    negative: `HBV/HCV/HIV/RPR/HSV/G-C/Treponema neg`; only the hep
    trio: `HBV/HCV neg`).  The HBV/HCV group (the hep B/C trio) is
    negative when all three rows are present and the surface-antigen
    and HCV results are normal -- a REACTIVE surface Ab means
    immunity, not active hepatitis B, so it does not drop the group.
    HIV is negative when nothing is flagged abnormal and every item
    value is non-reactive -- except that a result carrying the `HIV
    FINAL INTERPRETATION` item (the reflex work-up) is negative only
    when it says `HIV NEGATIVE`.  RPR is negative when nothing is
    flagged abnormal and every value is non-reactive (LabCorp's `RPR,
    Rfx Qn RPR/Confirm TP` order reports only its RPR item, so its
    confirmatory treponemal result rides this group).  G-C (the
    chlamydia / gonorrhea NAA: the in-house `Chlamydia / GC urine`
    and `Chlamydia/GC Amplification` orders, Quest's `CHLAMYDIA/N.
    GONORRHOEAE$RNA, TMA` and its chlamydia-only `CHLAMYDIA
    TRACHOMATIS$RNA, TMA`) is negative when every pathogen item is
    negative / not detected; a detected / positive pathogen is its
    own `G-C+` token right after the STD token (Quest's `CHLAM-
    YDIA TRACHOMATIS, TMA (ALTERNATE TARGET)` reflex re-test is a
    separate order and is ignored).  Treponema (Quest's `TREPONEMA
    PALLIDUM AB` confirmatory) is negative on a NEGATIVE value; a
    POSITIVE value is its own `Treponema+` token right after the STD
    token.  A missing or abnormal member drops that group; when no
    group is left, nothing is emitted.
21a. **HSV 1/2 IgG** (the type-specific HSV antibody order reporting
    both types on one result: Quest's `HSV 1/2 IGG,
    HERPESELECT$W/REFL HSV2 INHIBITION` index items, LabCorp's
    `HSV 1 and 2 Ab, IgG` Reactive / Non Reactive items).  The
    negative types join the STD token's ` neg` list, after `RPR`:
    both types negative contribute `HSV` (`HBV/HCV/HIV/RPR/HSV
    neg`), one type negative contributes `HSV1` / `HSV2` (`HBV/HCV/
    HIV/RPR/HSV2 neg`).  A positive type is its own token right
    after the STD token, `HSV1+` / `HSV2+`, or one combined
    `HSV1/HSV2+` when both types are positive (the yellow notes'
    labels, e.g. `HBV/HCV/HIV/RPR/HSV2 neg, HSV1+` or `HBV/HCV/
    HIV/RPR neg, HSV1/HSV2+`).  The value decides, not the flag
    (Quest flags a positive index `H`, LabCorp flags `Reactive`
    `A`): a negative value (LabCorp's `Non Reactive`, Quest's
    `<0.90`) or an index below 0.90 is negative, `Reactive` /
    `Positive` or an index above 1.09 (a capped `>58.00` counts) is
    positive, and the 0.90-1.09 equivocal band, a pending / empty
    value and a missing item are undetermined -- they drop their
    type from the ` neg` list and produce no `+` token.  The
    `HSV 2 IGG INHIBITION, IA` reflex follow-up is a separate order
    and is ignored.
22. **HBV DNA**. `HBV DNA neg` for a not-detected result (LabCorp's
    `HBV DNA not detected` text counts); `HBV DNA <{lim}` for a
    result detected below the quantification limit (a limit reported
    in log10 is rendered as 10**lim: `<1.00 DETECTED` -> `HBV DNA
    <10`); otherwise `HBV DNA {linear}/{log10}`, the level written
    with its log10 the way the yellow notes do it (a value reported
    in log10 is reconstructed as 10**value, rounded to a whole
    number: `2.62` -> `HBV DNA 417/2.62`).  A pending / empty value
    (Quest's `TNP`) produces nothing.
22a. **HCV RNA** (the quantitative viral load, not a screen; the HCV
    Ab order with reflex to RNA is an Ab screen and is not in this
    category).  The same shorthand as the HBV DNA: `HCV RNA neg` for
    a not-detected result (Quest's `<15 NOT DETECTED`, LabCorp's
    `HCV Not Detected` text), `HCV RNA <{lim}` for a result detected
    below the quantification limit, otherwise `HCV RNA
    {linear}/{log10}` (Quest's layout reports the linear `IU/mL` item
    first and the `Log IU/mL` item second, and the token is built
    from the first; a value reported in log10 is reconstructed as
    10**value); a pending / empty value (Quest's `TNP`) produces
    nothing.
23. **eAg**. `eAg neg` when negative / non-reactive, `eAg+` when
    positive / reactive; a pending / not-performed value produces
    nothing.
24. **HBcAb**. `HBcAb neg` / `HBcAb+` like the eAg; a pending /
    not-performed value produces nothing.
24a. **HDV** (hepatitis D antibody; occurs only with an HBV
    infection).  `HDV neg` when negative / non-reactive (Quest's item
    is spelled `HEPATITIS D ANTIBODY,` with a trailing comma, LabCorp
    reports `Non Reactive`), `HDV+` when positive / reactive; a
    pending / empty value produces nothing.
24b. **HTLV I/II** (LabCorp's `HTLV-I/II Antibodies, Qual` screen;
    no Quest layout exists in the database).  `HTLV neg` when
    negative, `HTLV+` when positive; a pending / empty value produces
    nothing.
24c. **HBV Ab Quant** (LabCorp's `Hep B Surf Ab Quant` titer, range
    `Immunity>10`).  Emitted only when the titer is above the 10
    mIU/mL immunity cutoff: `HBV Ab+` (the level decides like the
    measles Ab, and a capped `>value` counts); a non-immune titer
    produces nothing (the yellow notes record it as `need HBV
    vacc`).
25. **HAV**. Emitted only when the total antibody is positive:
    `HAV Ab+`; a negative result produces nothing.  (`HAV IgM`, acute
    infection, is a different test.)
26. **Measles**. The measles item of the standalone orders (the
    single `MEASLES ANTIBODY (IGG)` / `Rubeola Ab, IgG` item) or of
    the MMR order (where it is one of three items): Quest's
    `MMR (IGG) PANEL (MEASLES, MUMPS, RUBELLA)` panel and LabCorp's
    `MMR` order.  Emitted only
    when the IgG level is immune -- above both vendors' cutoff,
    16.49 (the flag is unreliable, so the level decides, and a
    capped `>300.00` counts): `measles Ab+`; non-immune / equivocal
    / number-less levels produce nothing.
26a. **Mumps** (the mumps item of the MMR order -- Quest's `MUMPS
    VIRUS$ANTIBODY (IGG)` on the MMR panel, LabCorp's `Mumps Abs,
    IgG` on its `MMR` order; no standalone mumps order exists in the
    database).  Emitted
    only when the IgG level is immune -- above the 10.99 cutoff (the
    9.00-10.99 band is equivocal), the level deciding like the
    measles (a capped `>300.00` counts): `mumps Ab+`; non-immune /
    equivocal / number-less levels produce nothing (the yellow notes
    write a negative as `need Mumps vacc`).
26b. **Rubella** (the `RUBELLA ANTIBODY (IGG)` index item of the MMR
    panel, LabCorp's `Rubella Antibodies, IgG` item on its `MMR`
    order, both on the in-house `RUBELLA IMMUNE STATUS` order and on
    LabCorp's standalone `Rubella Antibodies, IgG` order).  Emitted only when the
    index is immune -- above 0.99 (Quest: `> or = 1.00 Consistent
    with immunity`, LabCorp's range `Immune >0.99`; the 0.90-0.99
    band is equivocal): `rubella Ab+`; non-immune / equivocal /
    number-less levels produce nothing (the yellow notes write a
    negative as `need Rubeola vacc`).
26c. **Varicella** (the VZV IgG item of the varicella orders --
    Quest's `VARICELLA ZOSTER VIRUS$ANTIBODY (IGG)`, LabCorp's
    `Varicella-Zoster V Ab, IgG`, and its `VARICELLA ZOSTER VIRUS
    ANTIBODIES (IGG,IGM)` combo, whose IgM item is the acute-
    infection marker and is not it).  Emitted only when the result is
    positive / reactive: `varicella Ab+`.  The value decides, not the
    flag (LabCorp sends none): the `Reactive` / `Positive` text is
    positive, `Non Reactive` / `Negative` negative; a numeric S/CO
    level is positive at or above 1.00 (a capped `<1.00` counts as
    below it); a numeric index level is positive at or above 165.00,
    negative below 135.00, and the 135.00-164.99 band equivocal --
    equivocal, negative and pending / empty values produce nothing
    (the yellow notes write a negative as `need varicella vacc`).
27. **Iron**. Normal: `iron nl` (every item of the panel normal).
    Abnormal: one token per abnormal item, in report order,
    `{label} {val}({bound})` (trailing zeros stripped) with the
    labels `iron`, `TIBC`, `iron%sat` and `ferritin` (the last only
    on Quest's ferritin-containing panel).  An abnormal item without
    a label (the derived `UIBC`, ...) yields no token, but any
    abnormal item suppresses the `iron nl`.
27a. **Ferritin (standalone)**. Normal: omit. Abnormal: `ferritin {val}({bound})`
     (trailing zeros stripped); renders right after the iron token
     (or in the iron category's place when there is no iron-panel
     row).
28. **B12**. Normal: omit. Abnormal: `B12 {val}({bound})`.
29. **FA** (the folate item of the B12/folate panel). Normal: `FA
    nl`. Abnormal: `FA {val}({bound})` (trailing zeros stripped; the
    token is plain `FA {val}` on Quest, whose item carries no range).
    A missing folate item produces nothing; the panel's B12 item is
    the separate B12 category (rule 28).
30. **AST/ALT** -- the liver panel (`CMP`, `BMP`, hepatic function
    panel).  Emitted only when a value is high: `AST/ALT {ast}({bound})/{alt}({bound})`
    with each high value's violated upper limit in parentheses (a
    not-high member written plain); when only one of the two items is
    present the high one is emitted alone, e.g. `ALT 54(46)`; when
    neither value is high nothing is produced.  A high total protein
    is reported right after as its own `protein {val}({bound})`
    token.  The panel's other named items are reported as their own
    tokens, right after the protein token and in this order, each
    emitted only when its item is abnormal: `BUN`, `Cr` / `CrCl`
    (the creatinine item plus, as CrCl, the panel's `EGFR` item; both
    abnormal -> one combined `Cr/CrCl {cr}/{crcl}({bound})` token),
    `bilirubin` (total only), `AP`, `albumin`, `Ca`, `Na`, `Cl`,
    `K`.  The panel's remaining items are ignored.  A standalone
    `ggt` order is the separate category of rule 30a.
30a. **GGT** (standalone order). Normal: omit. Abnormal: `GGT {val}({bound})`
     (trailing zeros stripped); renders right after the liver panel's
     tokens (or in the liver category's place when there is no
     liver-panel row).
31. **amylase**. Normal: `amylase nl`. Abnormal: `amylase {val}({bound})`.
32. **lipase**. Normal: `lipase nl`. Abnormal: `lipase {val}({bound})`.
33. **ANA**. `ANA+` when any item is flagged abnormal (the item's
    `1:{titer}` value appended when one is present: `ANA+ 1:80`);
    `ANA nl` when nothing is flagged abnormal; any other nonempty
    value produces nothing.
34. **ESR / CRP**. `ESR/CRP nl` when both tests are present and
    normal; otherwise the abnormal member(s) as `ESR {val}({bound})`
    / `CRP {val}({bound})` (ESR first), and a normal member reports
    `ESR nl` / `CRP nl` only when the other test is absent.
35. **H pylori**. `H pylori neg` when negative / not detected;
    `H pylori+` when any item is flagged abnormal; a pending / empty
    value produces nothing.
36. **stool occult**. `stool occult+` when any item is flagged abnormal, else
    `stool occult neg`.
36a. **Stool culture** (campylobacter, e. coli O157:H7
    and salmonella/shigella stool cultures).  `stool culture neg` when every
    present order is negative; one `{label}+` token per positive order:
    `Campylobactor+` / `E. coli O157:H7+` / `Salmonella/Shigella+` in that
    order . negative members are not reported.
37. **AFP**. Normal: `AFP nl`. Abnormal: `AFP {val}({bound})`.
38. **CEA**. Normal: `CEA nl`. Abnormal: `CEA {val}({bound})` (the
    item's range is the unparseable `See Note:`, so an abnormal
    result is usually plain `CEA {val}`).
39. **CA 125**. Normal: `CA 125 nl`. Abnormal: `CA 125 {val}({bound})`.
40. **CA 19-9**. Normal: `CA 19-9 nl`. Abnormal: `CA 19-9 {val}({bound})`.
41. **LDH**. Normal: `LDH nl`. Abnormal: `LDH {val}({bound})`.
42. **QTB**. Emitted only when the result's interpretation item is
    negative: `QTB neg`; positive / indeterminate results, and
    results with no interpretation item, produce nothing.

Everything else is ignored: creatine kinase, the remaining endocrine
tests (testosterone / DHEA /
cortisol / prolactin / LH), HCG, rheumatoid factor, the autoimmune
panel (C3 / C4 / dsDNA / ANCA / anti-CCP), the stool parasites
(ova and parasites, giardia, cryptosporidium) and C. diff toxin,
troponin / D-dimer, hep A IgM and copper -- no orders for the latter
two exist
in the database to learn their item layouts from -- and imaging (CT
cardiac scoring, ...).  A row that matches no rule above produces no
token.

The leading date is `mm/yyyy` (zero-padded month) of the newest result.
"""

import json
import math
import re
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

# Flag values that count as normal after strip().lower(); anything else
# (A, H, L, ...) is abnormal.  None counts as normal.
_NORMAL_FLAGS = frozenset({"", "n"})

# Category name lists, lower-cased; matched after strip + lower.
_UA_NAMES = frozenset(
    {"ua, routine", "ua, urine routine", "urinalysis reflex"})
# Urine-culture order names per vendor / in-house (lower-cased).  The
# LabCorp `Culture Urine, Routine` order carries a `Urine Culture,
# Routine` header item (`Final report`) plus the `Result 1` result
# item; the in-house order is a single item named after the order
# (an empty value is a pending culture); Quest's `urine reflex to
# culture` carries a `REFLEXIVE URINE CULTURE` item (empty when the
# reflex never fired); the LabCorp UA-with-reflex order matches too --
# an order whose reflex never fired carries no culture item and yields
# nothing (rule 1a).
_UCX_NAMES = frozenset({
    "culture urine, routine", "culture, urine, routine",
    "urine reflex to culture", "ua/m w/rflx culture, routine",
})
# Culture result item per layout (lower-cased); the LabCorp header
# item `Urine Culture, Routine` is not it.
_UCX_ITEMS = frozenset({
    "result 1", "culture, urine, routine", "reflexive urine culture",
})
# Culture result values (lower-cased) that mean a negative culture.
_UCX_NEGATIVE = frozenset({"no growth", "none", "negative"})
# CBC order name per vendor (lower-cased); the LabCorp
# `CBC/Diff Ambiguous Default` order carries the LabCorp layout.
_CBC_NAMES = frozenset({
    "cbc (includes diff/plt)", "cbc with differential/platelet",
    "cbc/diff ambiguous default",
})
# Red blood cell count item name per vendor (lower-cased).
_RBC_ITEMS = frozenset({"red blood cell count", "rbc"})
# MCV item name; both vendors spell it `MCV` (lower-cased).
_MCV_ITEMS = frozenset({"mcv"})
# WBC / Hb / Plt / Hct item names per vendor (lower-cased).
_WBC_ITEMS = frozenset({"white blood cell count", "wbc"})
# `Hemoglobin` in both vendors' layouts (lower-cased).
_HB_ITEMS = frozenset({"hemoglobin"})
# Platelet count item name per vendor (lower-cased).
_PLT_ITEMS = frozenset({"platelet count", "platelets"})
# Hematocrit item name; both vendors' layouts (lower-cased).
_HCT_ITEMS = frozenset({"hematocrit"})
# Absolute-eosinophil item per vendor (lower-cased): Quest's CBC
# spells it `ABSOLUTE EOSINOPHILS` (cells/uL, range `15-500`),
# LabCorp's `Eos (Absolute)` (x10E3/uL, range `0.0-0.4`).  The
# percentage items (`EOSINOPHILS` / `Eos`) carry no usable range
# on either vendor and are not it.
_EOS_ITEMS = frozenset({"absolute eosinophils", "eos (absolute)"})
_TSH_NAMES = frozenset({
    "tsh w/reflex to ft4", "tsh reflex to t4f", "tsh+free t4",
    "tsh rfx on abnormal to free t4",
    # the standalone TSH orders (both vendors' single `TSH` item, with
    # or without a reference range) and LabCorp's thyroid cascade
    # profile (a single `TSH` item plus an interpretation note)
    "tsh", "thyroid cascade profile",
})

# Thyroid-cluster order names (lower-cased; rule 2a).  Quest's `free
# t3` order reports a `T3, FREE` item and LabCorp's `free t3, serum`
# order a `Triiodothyronine,Free,Serum` item; the standalone `free
# t4` order (both vendors) reports a `T4, FREE` (Quest) /
# `T4,Free(Direct)` (LabCorp) item -- a free-T4 item inside a TSH
# result is not this category (it joins the TSH token, rule 2).
_T3_NAMES = frozenset({"free t3", "free t3, serum"})
_T3_ITEMS = frozenset({"t3, free", "triiodothyronine,free,serum"})
_T4_NAMES = frozenset({"free t4"})
_T4_ITEMS = frozenset({"t4, free", "t4,free(direct)"})
# TPO / TgAb order names (lower-cased): LabCorp's `Thyroid
# Peroxidase (TPO) Ab` order reports a `Thyroid Peroxidase (TPO) Ab`
# item, its `Thyroid Antibodies` order both that item and a
# `Thyroglobulin Antibody` item, and Quest's `thyroid peroxidase and
# thyroglobulin antibodies` panel the `THYROID PEROXIDASE$
# ANTIBODIES` and `THYROGLOBULIN ANTIBODIES` items (so one row feeds
# both categories, like the MMR order feeds three); the standalone
# `Thyroglobulin Antibod(y/ies)` orders carry the TgAb item alone.
_TPO_NAMES = frozenset({
    "thyroid peroxidase (tpo) ab", "thyroid antibodies",
    "thyroid peroxidase and thyroglobulin antibodies",
})
_TPO_ITEMS = frozenset(
    {"thyroid peroxidase (tpo) ab", "thyroid peroxidase$antibodies"})
_TGAB_NAMES = frozenset({
    "thyroid antibodies",
    "thyroid peroxidase and thyroglobulin antibodies",
    "thyroglobulin antibody", "thyroglobulin antibodies",
})
_TGAB_ITEMS = frozenset({"thyroglobulin antibody",
                         "thyroglobulin antibodies"})
# TSI (TSH-receptor stimulating immunoglobulin) order names
# (lower-cased): Quest's `thyroid stim immunoglobulin` order reports
# a `Thyroid Stim Immunoglobulin` item (IU/L, 0.00-0.55) and its
# `tsi (thyroid stimulating$immunoglobulin)` order a `TSI` item
# (% baseline, >= 140 is positive).
_TSI_NAMES = frozenset({
    "thyroid stim immunoglobulin",
    "tsi (thyroid stimulating$immunoglobulin)",
})
_TSI_ITEMS = frozenset({"thyroid stim immunoglobulin", "tsi"})
_A1C_NAMES = frozenset({"hemoglobin a1c"})
# Lipid-panel order names per vendor / in-house (lower-cased).  The
# reflex / ratio variants carry the same vendor item layouts.
_LIPID_NAMES = frozenset({
    "lipid panel", "lipid panel with ratios",
    "lipid panel with reflex to direct ldl",
    "lipid panel with ratios (refl)",
    "lipid panel with ldl/hdl ratio",
})
# Calculated-LDL item names per vendor (lower-cased).  Other LDL-ish
# items (NON HDL CHOLESTEROL, LDL/HDL RATIO, VLDL Cholesterol Cal) are
# deliberately not the LDL item.
_LDL_ITEMS = frozenset({"ldl chol calc (nih)", "ldl-cholesterol"})
# HDL and triglyceride item names, lower-cased; both vendors collapse
# to the same name after strip + lower.
_HDL_ITEMS = frozenset({"hdl cholesterol"})
_TG_ITEMS = frozenset({"triglycerides"})
_LPA_NAMES = frozenset({"lipoprotein (a)"})
# In-house (ECW) order names for the apolipoprotein B add-on; the
# result item is `Apolipoprotein B` in both spellings' layouts.
_APOB_NAMES = frozenset(
    {"lipid _ apolipoprotein b", "lipid_ apolipoprotein b"})
# In-house order name for serum magnesium.  `MAGNESIUM, RBC` (red-cell
# magnesium) is a different test and is deliberately not in this set.
_MG_NAMES = frozenset({"magnesium"})
# In-house / Quest order names; the single item is `FSH` in both
# layouts.
_FSH_NAMES = frozenset({"fsh, serum", "fsh"})
# In-house order name for serum estradiol; the single item is named
# after the order too (`ESTRADIOL`; the in-house order carries no
# reference range).
_ESTRADIOL_NAMES = frozenset({"estradiol"})
_VITD_NAMES = frozenset(
    {"vitamin d,25-oh,total,ia", "vitamin d, 25-hydroxy"})
# Intact PTH per vendor (lower-cased); both report a single item.
_PTH_NAMES = frozenset({"pth, intact without$calcium", "pth, intact"})
_PSA_NAMES = frozenset({
    "psa, total", "psa",
    "psa total (reflex to free)", "psa total+% free",
})
# Coagulation order names per vendor / in-house (lower-cased).  The
# `INR` order carries a `PT` and an `INR` item; `INR /PT` carries
# `INR` and `Prothrombin Time`; the combined prothrombin /
# partial-thromboplastin order carries both plus the PTT item.
_INRPT_NAMES = frozenset(
    {"inr", "inr /pt",
     "prothrombin w/inr + partial thromboplastin times"})
_PTT_TTT_NAMES = frozenset(
    {"ptt", "prothrombin w/inr + partial thromboplastin times"})
# `INR` item in all three layouts (lower-cased).
_INR_ITEMS = frozenset({"inr"})
# Prothrombin-time item per layout (lower-cased): `PT` on the `INR`
# and combined orders, `Prothrombin Time` on `INR /PT`.
_PT_ITEMS = frozenset({"pt", "prothrombin time"})
# Partial-thromboplastin-time item per layout (lower-cased); Quest's
# item name carries a literal `$` in the middle.
_PTT_ITEMS = frozenset({
    "partial thromboplastin time, activated",
    "partial thromboplastin$time, activated",
})
# BNP (B-type natriuretic peptide) per vendor (lower-cased); one
# item each, and Quest's item name carries a literal `$`.
_BNP_NAMES = frozenset({"bnp"})
_BNP_ITEMS = frozenset({
    "b-type natriuretic peptide",
    "b type natriuretic$peptide (bnp)",
})
# H. pylori order names per vendor (lowercased).  The stool-antigen
# EIA and the breath-test collection kit are H. pylori orders too but
# usually carry no value yet (pending collection / reporting); they
# match, and an empty value simply yields no token (rule 35).
_HPYLORI_NAMES = frozenset({
    "h pylori,$urea breath test",
    "h pylori breath test",
    "h pylori ag,$eia, stool",
    "h. pylori breath collection",
})
# Stool occult blood order names per vendor (lowercased).  The
# in-house order carries Quest's FIT, which leaves the value empty on
# a negative result (rule 36); LabCorp reports `Negative` /
# `Positive` text on `Occult Blood, Fecal, IA`.
_STOOL_NAMES = frozenset({"stool occult", "stool occult blood"})
# In-house stool-culture order names (lower-cased).  The campylobacter
# order reports `NOT ISOLATED` / `ISOLATED` in the `CULTURE` item's
# value; the e. coli O157:H7 and salmonella/shigella orders leave the
# value empty and report the negative in the result note (`No ...`
# `isolated` text).  The antimicrobial-susceptibility and bacterial-ID
# follow-ups are separate orders and are not in these sets (rule 36a).
_STOOL_CX_CAMPY_NAMES = frozenset({"stool culture - campylobacter"})
_STOOL_CX_ECOLI_NAMES = frozenset({"stool culture for ecoli o157:h7"})
_STOOL_CX_SALM_NAMES = frozenset({"salmonella and shigella, culture"})
# Serum phosphorus per vendor (lower-cased); one item each.
_PHOS_NAMES = frozenset({"phosphorus, serum", "phosphorus"})
# Zinc order names (lower-cased).  `ZINC, RBC` (red-cell zinc) is a
# different test and is not part of this category (rule 15).
_ZINC_NAMES = frozenset({"zinc, plasma or serum", "zinc"})
# ANA order per vendor (lower-cased); the middle spacing on the Quest
# name is part of the real order name.  Quest reports `ANA PATTERN` /
# `ANA TITER` items (positive results often carry their titer in a
# note, so the values can be empty with an A/H flag); LabCorp's
# `Antinuclear Antibodies, IFA` is a single item.
_ANA_NAMES = frozenset({
    "antinuclear antibodies   titer and pattern",
    "antinuclear antibodies, ifa",
    "antinuclear antibody",
    "ana screen",
    "ana screen, ifa, w/refl$titer and pattern",
    "ana scr, ifa, w/refl titer/pattern/rheumatoid arthritis",
})
# ESR / CRP order names (lower-cased).  CRP's `CRP, Cardiac` is the
# high-sensitivity cardiac CRP -- a different test with its own 0-3
# range -- and is deliberately not in this set (rule 34).
_ESR_NAMES = frozenset({
    "esr",
    "sed rate",
    "erythrocyte sedimentation rate",
})
_CRP_NAMES = frozenset({"crp", "crp, quant"})
# Lipase per vendor (lower-cased); one item each.
_LIPASE_NAMES = frozenset({"lipase", "lipase, serum"})
# Tumor-marker order names per vendor (lower-cased), one item each.
# Quest spells the AFP order out as `ALPHA FETOPROTEIN,$TUMOR MARKER`
# (the `$` is part of the name, as on its other orders).
_AFP_NAMES = frozenset(
    {"afp", "afp, serum, tumor marker",
     "alpha fetoprotein,$tumor marker"})
_CEA_NAMES = frozenset({"cea"})
_CA125_NAMES = frozenset({"ca 125", "ca-125"})
# CA 19-9 (in-house order; the single item is `CA 19-9`).
_CA199_NAMES = frozenset({"ca 19-9"})
_CA199_ITEMS = frozenset({"ca 19-9"})
# Amylase (in-house order; the single item is `AMYLASE`).
_AMYLASE_NAMES = frozenset({"amylase"})
_AMYLASE_ITEMS = frozenset({"amylase"})
# LDH; the single item is LabCorp's `LDH` or Quest's `LD`.
_LDH_NAMES = frozenset({"ldh"})
_LDH_ITEMS = frozenset({"ldh", "ld"})
# Standalone GGT order (LabCorp); the single item is `GGT`.
_GGT_NAMES = frozenset({"ggt"})
_GGT_ITEMS = frozenset({"ggt"})
_URIC_NAMES = frozenset({"uric acid, serum", "uric acid"})
# HAV total antibody per vendor (lower-cased); the single item's value
# is REACTIVE / NON-REACTIVE (Quest) or Positive / Negative (LabCorp).
# `HAV IgM` / `Hep A Ab, IgM` (acute infection) are different tests
# and are deliberately not in this set.
_HAV_NAMES = frozenset({"hep a total ab", "hep a ab, total"})
_MEASLES_NAMES = frozenset(
    {"measles _ rubeola, igg", "measle _ rubeola _ igg",
     "mmr (igg) panel (measles, mumps, rubella)",
     "mmr"})
# Measles item per layout (lower-cased): Quest's `MEASLES ANTIBODY
# (IGG)` (on the standalone orders and the MMR panel) and LabCorp's
# `Rubeola Ab, IgG` (standalone and on its `MMR` order).  The MMR
# order's other items are the separate mumps / rubella categories
# (rules 26a / 26b).
_MEASLES_ITEMS = frozenset({"measles antibody (igg)", "rubeola ab, igg"})
# Mumps order names (lower-cased): Quest's MMR panel and LabCorp's
# `MMR` order share the category with the measles / rubella names
# (rule 26a); no standalone mumps order exists in the database.
_MUMPS_NAMES = frozenset(
    {"mmr (igg) panel (measles, mumps, rubella)", "mmr"})
# Mumps item per layout (lower-cased): Quest's `MUMPS VIRUS$
# ANTIBODY (IGG)` (the `$` is part of the name, as on its other
# items) and LabCorp's `Mumps Abs, IgG` (range `Immune >10.9`).
_MUMPS_ITEMS = frozenset(
    {"mumps virus$antibody (igg)", "mumps abs, igg"})
# Rubella order names per vendor / in-house (lower-cased); the MMR
# orders' rubella items are the same items as the in-house `RUBELLA
# IMMUNE STATUS` order's (rule 26b).
_RUBELLA_NAMES = frozenset(
    {"rubella immune status", "rubella antibodies, igg",
     "mmr (igg) panel (measles, mumps, rubella)", "mmr"})
# Rubella item per layout (lower-cased): Quest's `RUBELLA ANTIBODY
# (IGG)` (the MMR panel and the in-house `RUBELLA IMMUNE STATUS`)
# and LabCorp's `Rubella Antibodies, IgG` (standalone and on its
# `MMR` order).
_RUBELLA_ITEMS = frozenset(
    {"rubella antibody (igg)", "rubella antibodies, igg"})
# Varicella (VZV) IgG order names per vendor (lower-cased).  The
# LabCorp `VARICELLA ZOSTER VIRUS ANTIBODIES (IGG,IGM)` combo order
# carries the IgG item too -- only that item is consulted, its IgM
# item is the acute-infection marker and is not it (rule 26c).
_VARICELLA_NAMES = frozenset({
    "varicella zoster virus$antibody (igg)",
    "varicella-zoster v ab, igg",
    "varicella zoster virus antibodies (igg,igm)",
})
# VZV IgG item per layout (lower-cased): Quest's current layout names
# the item after the order, the older Quest layout and LabCorp's
# `Varicella-Zoster V Ab, IgG` report `Varicella Zoster IgG`, and the
# LabCorp combo reports `VARICELLA ZOSTER VIRUS ANTIBODY (IGG)`.
_VARICELLA_ITEMS = frozenset({
    "varicella zoster virus$antibody (igg)",
    "varicella zoster igg",
    "varicella zoster virus antibody (igg)",
})
_QTB_NAMES = frozenset({
    "quantiferon-tb gold plus",
    "quantiferon(r)-tb gold plus, 1 tube",
})
# Interpretation values the two vendors use on the QTB result item that
# is named after the test (the numeric tube values are not it).
_QTB_INTERPRETATIONS = frozenset({"negative", "positive", "indeterminate"})
# Measles IgG (AU/mL) level above which both vendors' interpretations
# (Quest: ">16.49 consistent with immunity"; LabCorp: "Immune >16.4")
# call the patient immune; 13.5-16.49 is the equivocal band.  The
# flag is unreliable (Quest sends "N" on a strong positive, LabCorp
# sends "L" on a non-immune value like "<13.5"), so the level itself
# decides; non-numeric values (e.g. "<13.5") parse as non-immune.
_MEASLES_IMMUNE_ABOVE = 16.49
# Mumps IgG (AU/mL) level above which the MMR panel's item note
# ("9.00-10.99 Equivocal", ">10.99 Consistent with immunity") calls
# the patient immune; the level decides like the measles, and a
# capped `>300.00` counts (rule 26a).
_MUMPS_IMMUNE_ABOVE = 10.99
# Rubella IgG (index) level above which both vendors' interpretations
# (Quest's item note: "> or = 1.00 Consistent with immunity";
# LabCorp's range: `Immune >0.99`) call the patient immune;
# 0.90-0.99 is the equivocal band (rule 26b).
_RUBELLA_IMMUNE_ABOVE = 0.99
# VZV IgG cutoffs per layout, from the item notes' interpretations
# (rule 26c): the S/CO layout is `> or = 1.00 Positive`; the index
# layout is `>= 165.00 Positive`, `<135.00 Negative`, the
# 135.00-164.99 band equivocal.
_VARICELLA_SCO_POSITIVE_AT = 1.00
_VARICELLA_INDEX_POSITIVE_AT = 165.00
_VARICELLA_INDEX_NEGATIVE_BELOW = 135.00
_B12_NAMES = frozenset({"vitamin b12"})
# B12/folate panel per vendor (lower-cased).  The panel's folate item
# is the `FA` category (rule 29); its B12 item is not part of the B12
# category (rule 28 uses the standalone `Vitamin B12` order).
_FA_NAMES = frozenset({
    "vitamin b12/folate,$serum panel",
    "vitamin b12 and folate",
})
# Folate item per vendor (lower-cased); Quest's panel item carries no
# reference range, LabCorp's does (e.g. `>3.0`).
_FA_ITEMS = frozenset({
    "folate, serum",
    "folate (folic acid), serum",
    "folate",
})
# Liver panel per vendor / in-house (lower-cased).  The in-house CMP
# and BMP orders carry Quest or LabCorp items (the CMP's, among them
# the AST / ALT pair; the BMP the CMP's items minus the liver ones,
# its `GLUCOSE` item joining the A1c token via `_liver_glucose`).
_LIVER_NAMES = frozenset(
    {"cmp", "bmp",
     "hepatic function panel", "hepatic function panel (7)"})
_AST_ITEMS = frozenset({"ast", "ast (sgot)"})
_ALT_ITEMS = frozenset({"alt", "alt (sgpt)"})
# Total-protein item per vendor (lower-cased): Quest's CMP items
# spell it `PROTEIN, TOTAL`, LabCorp's hepatic function panel
# `Protein, Total, Serum`.
_PROTEIN_ITEMS = frozenset({"protein, total", "protein, total, serum"})
# Named items of the liver panel reported by their own tokens
# (lower-cased); per-vendor spellings where they differ.
_BUN_ITEMS = frozenset({"urea nitrogen (bun)", "bun"})
# `CREATININE` in both vendors' layouts (lower-cased).
_CR_ITEMS = frozenset({"creatinine"})
# CrCl is the CMP's `EGFR` item (both vendors, lower-cased).
_EGFR_ITEMS = frozenset({"egfr"})
# Total bilirubin item per vendor (lower-cased).  The panel's
# `BILIRUBIN, DIRECT` item is a different item and is not it.
_BILI_ITEMS = frozenset({"bilirubin, total"})
_ALP_ITEMS = frozenset({"alkaline phosphatase", "alkaline phosphatase, s"})
_ALB_ITEMS = frozenset({"albumin", "albumin, serum"})
# The liver panel's electrolyte items per vendor (lower-cased):
# Quest spells them `SODIUM` / `POTASSIUM` / `CHLORIDE` /
# `CALCIUM`, LabCorp's in-house-CMP items `Sodium, Serum` &c.
# Reported by their own tokens when abnormal (rule 30).
_NA_ITEMS = frozenset({"sodium", "sodium, serum"})
_K_ITEMS = frozenset({"potassium", "potassium, serum"})
_CL_ITEMS = frozenset({"chloride", "chloride, serum"})
_CA_ITEMS = frozenset({"calcium", "calcium, serum"})
# Glucose item per vendor (lower-cased): Quest's CMP items spell it
# `GLUCOSE`, LabCorp's (on the in-house CMP) `Glucose, Serum`; the
# standalone hepatic function panels carry no glucose item.  The
# value joins the A1c token as `Glu {val}/A1c {val}`.
_GLUCOSE_ITEMS = frozenset({"glucose", "glucose, serum"})
# Standalone glucose order names per vendor (lower-cased); the item
# set is the same as the liver panel's glucose item.  Reported by
# rule 5a as its own abnormal-only token, separate from the
# liver-panel glucose that joins the A1c token (rule 5).
_GLU_NAMES = frozenset({"glucose", "glucose, serum"})
_IRON_NAMES = frozenset({
    "iron and tibc",
    "iron, tibc and ferritin panel",
    "iron and total iron$binding capacity",
})
# Iron-panel item names per vendor (lower-cased), each with its sticky
# label; items outside these four sets (the derived `UIBC`, ...) yield
# no token of their own.
_IRON_SERUM_ITEMS = frozenset({"iron, serum", "iron, total"})
_TIBC_ITEMS = frozenset({"iron bind.cap.(tibc)", "iron binding capacity"})
_IRONSAT_ITEMS = frozenset({"iron saturation", "% saturation"})
# `FERRITIN` only on Quest's `IRON, TIBC AND FERRITIN PANEL`;
# the standalone `Ferritin` / `ferritin, serum` orders are the
# separate ferritin category (rule 27a).
_FERRITIN_ITEMS = frozenset({"ferritin"})
# Standalone ferritin order names (lower-cased, per vendor): in-house
# / Quest's `Ferritin` carries the `FERRITIN` item, LabCorp's
# `ferritin, serum` carries `Ferritin, Serum`.
_FERRITIN_STANDALONE_NAMES = frozenset({"ferritin", "ferritin, serum"})
_FERRITIN_STANDALONE_ITEMS = frozenset({"ferritin", "ferritin, serum"})
_ALBCR_NAMES = frozenset(
    {"microalb/creat ratio, randm ur", "microalbumin, random urine (w/creatinine)"})
_HCV_NAMES = frozenset(
    {"hep c ab rfx to quant pcr", "hep c ab reflex to rna, qn, pcr"})
_HBSAG_NAMES = frozenset({"hep b surface ag"})
_HBSAB_NAMES = frozenset({"hep b surface ab"})
# Hep B surface-Ab titer (LabCorp's `Hep B Surf Ab Quant`,
# lower-cased); the single item is `Hepatitis B Surf Ab Quant` (the
# range is `Immunity>10`).  The qualitative surface-Ab row is part of
# the hep B/C trio (rule 21); this titer order is the separate
# follow-up of rule 24c.
_HBSABQ_NAMES = frozenset({"hep b surf ab quant"})
_HBSABQ_ITEMS = frozenset({"hepatitis b surf ab quant"})
# Surface-Ab titer level (mIU/mL) above which the range text
# (`Immunity>10`) calls the patient immune.
_HBSABQ_IMMUNE_ABOVE = 10.0
# HIV screen per vendor (lower-cased); the in-house order uses the
# same names.  `HIV-1/HIV-2 Qualitative RNA` (LabCorp) is a confirm-
# atory test, not the screen, and is deliberately not in this set.
_HIV_NAMES = frozenset({"hiv 1/2 ag/ab, 4th generation", "hiv"})
# RPR screen per vendor (lower-cased); the in-house order uses the
# same names.
_RPR_NAMES = frozenset({
    "rpr (dx) w/ confirmatory", "rpr", "rpr, rfx qn rpr/confirm tp"})
# HSV 1/2 IgG (HerpesSelect) order per vendor (lower-cased).  Both
# types are reported as items on the one order: Quest's `HSV 1/2
# IGG, HERPESELECT$W/REFL HSV2 INHIBITION` with the `HSV 1/2 IGG
# TYPE SPECIFIC$AB` index items, LabCorp's `HSV 1 and 2 Ab, IgG`
# with the `HSV N IgG, Type Spec` Reactive / Non Reactive items.
# The `HSV 2 IGG INHIBITION, IA` reflex follow-up is a separate
# order and is not in this set (rule 21a).
_HSV_NAMES = frozenset({
    "hsv 1/2 igg, herpeselect$w/refl hsv2 inhibition",
    "hsv 1 and 2 ab, igg",
})
# HSV type-specific IgG items per vendor (lower-cased).
_HSV1_ITEMS = frozenset({
    "hsv 1 igg type specific$ab", "hsv 1 igg, type spec"})
_HSV2_ITEMS = frozenset({
    "hsv 2 igg type specific$ab", "hsv 2 igg, type spec"})
# Quest's HerpesSelect index cutoffs (LabCorp reports Reactive /
# Non Reactive text instead): below 0.90 negative, 0.90-1.09
# equivocal, above 1.09 positive.  The value decides, not the flag
# (Quest flags a positive index H, LabCorp flags Reactive A).
_HSV_NEGATIVE_BELOW = 0.90
_HSV_POSITIVE_ABOVE = 1.09
# Chlamydia / gonorrhea (G-C) NAA order names per vendor / in-house
# (lower-cased).  Every layout reports its pathogens as items on the
# one order: the in-house `Chlamydia / GC urine` carries Quest's
# `CHLAMYDIA TRACHOMATIS` / `NEISSERIA GONORRHOEAE` items (Detected
# / Not Detected values), LabCorp's `Chlamydia/GC Amplification` its
# `... , NAA` items (Negative / Positive values), Quest's
# `CHLAMYDIA/N. GONORRHOEAE$RNA, TMA` its `$RNA, TMA` items (NOT
# DETECTED / DETECTED values), and Quest's chlamydia-only
# `CHLAMYDIA TRACHOMATIS$RNA, TMA` the chlamydia item alone.
# Quest's `CHLAMYDIA TRACHOMATIS, TMA (ALTERNATE TARGET)` reflex
# re-test of a positive chlamydia result is a separate order and is
# not in this set (like the HSV 2 inhibition reflex, rule 21a).
_GC_NAMES = frozenset({
    "chlamydia / gc urine",
    "chlamydia/gc amplification",
    "chlamydia/n. gonorrhoeae$rna, tma",
    "chlamydia trachomatis$rna, tma",
})
# The G-C order's pathogen items per vendor (lower-cased); Quest's
# layouts carry an `(Always Message)` note item that is not a
# pathogen.
_GC_ITEMS = frozenset({
    "chlamydia trachomatis",
    "chlamydia trachomatis, naa",
    "chlamydia trachomatis$rna, tma",
    "neisseria gonorrhoeae",
    "neisseria gonorrhoeae, naa",
    "neisseria gonorrhoeae$rna, tma",
})
# Treponema pallidum antibody (Quest's syphilis confirmatory / the
# immigration screen, lower-cased); the single item is named after
# the test (NEGATIVE / POSITIVE value).  LabCorp's `RPR, Rfx Qn
# RPR/Confirm TP` order reports only its `RPR` item, so its
# confirmatory treponemal result rides the RPR group.
_TREPONEMA_NAMES = frozenset({"treponema pallidum ab"})
_TREPONEMA_ITEMS = frozenset({"treponema pallidum ab"})
# Result values (lower-cased) that mean positive on the HAV total
# antibody and the hep B e-antigen / core-antibody orders in both
# vendors' layouts (Quest: REACTIVE / NON-REACTIVE, LabCorp:
# Positive / Negative).
_POSITIVE_VALUES = frozenset({"reactive", "positive"})
# Result values (lower-cased) that mean negative / non-reactive in
# both vendors' HIV and RPR layouts.
_NEGATIVE_VALUES = frozenset(
    {"negative", "non-reactive", "non reactive",
     "hiv negative", "not detected"})
# HBV DNA order per vendor (lower-cased); the single item is
# `HEPATITIS B VIRUS DNA` in both layouts.  The result values are
# `NOT DETECTED`-style text (negative), `<10 DETECTED`-style text
# (detected below the quantification limit), or an IU/mL number
# (rule 22).
_HBV_DNA_NAMES = frozenset({"hep b dna, pcr", "hbv dna",
                            "hep b real-time pcr, quant",
                            "hbv rt pcr, quant (graph)"})
# HCV RNA quantitative follow-up orders per vendor (lower-cased); the
# test is a viral load, not a screen.  Quest's two layouts report the
# same item name twice (the linear `IU/mL` item first, then the
# `Log IU/mL` one); LabCorp's `Hepatitis C Quantitation` item holds
# the value (or the `HCV Not Detected` text) plus a `Test
# Information:` note item.  `HEPATITIS C AB W/RFL RNA, PCR W/RFL
# GENOTYPE,LIPA` is an HCV Ab screen with reflex to RNA, not an RNA
# order, and is deliberately not in this set.
_HCV_RNA_NAMES = frozenset({
    "hcv rna, quantitative real time pcr",
    "hcv rna, quantitative$real time pcr",
    "hcv rt-pcr, quant (non-graph)",
})
# Hep B e-antigen orders (lower-cased); the item is Quest's
# `HEPATITIS BE ANTIGEN` or LabCorp's `Hep Be Ag`.
_EAG_NAMES = frozenset({"hep b eag", "hep be ag"})
_EAG_ITEMS = frozenset({"hepatitis be antigen", "hep be ag"})
# Hep B core-antibody orders (lower-cased); the item is Quest's
# `HEPATITIS B CORE AB TOTAL` or LabCorp's `Hep B Core Ab, Tot`.
_HBCAB_NAMES = frozenset({"hep b core ab", "hep b core ab, tot"})
_HBCAB_ITEMS = frozenset({
    "hepatitis b core ab total", "hep b core ab, tot"})
# Hepatitis D antibody orders per vendor (lower-cased); the item is
# Quest's `HEPATITIS D ANTIBODY,` (note the trailing comma) or
# LabCorp's `HDV Antibody, IgG/IgM`.  HDV occurs only with an HBV
# infection, so the order rides the hep B work-up.
_HDV_NAMES = frozenset({"hep d antibody", "hepatitis d antibody, igg/igm"})
_HDV_ITEMS = frozenset({"hepatitis d antibody,", "hdv antibody, igg/igm"})
# HTLV I/II antibody screen (LabCorp's `HTLV-I/II Antibodies, Qual`,
# lower-cased); the single item is named after the test (Negative /
# Positive value).  No Quest / in-house layout exists in the database
# to learn from.
_HTLV_NAMES = frozenset({"htlv-i/ii antibodies, qual"})
_HTLV_ITEMS = frozenset({"htlv-i/ii antibodies, qual"})

# (item name, value) pairs, lower-cased, that recent Quest/LabCorp UAs
# flag abnormal but that are not reported in the summary.
_UA_IGNORED = frozenset({
    ("ketones", "trace"),
    ("ketones", "2+"),
    ("wbc esterase", "trace"),
    ("leukocyte esterase", "trace"),  # Quest's name for WBC esterase
    ("occult blood", "trace"),
    ("bacteria", "few"),
})
# Item names, lower-cased, ignored on any value: squamous epithelial
# cells are a sample-contamination artifact, not a finding.
_UA_IGNORED_NAMES = frozenset({"squamous epithelial cells"})
# Crystal values that mean no crystals (the ranges are "NONE OR FEW"
# / "NONE SEEN"); any other value on an abnormal crystal item means
# crystals are present.
_UA_CRYSTALS_ABSENT = frozenset(
    {"", "none", "none seen", "absent", "negative", "few"})

# Category key -> row names.  The three hep B/C categories are
# separate so the HBV/HCV group of the STD token can require all
# three to be present and the surface-Ag / HCV results to be normal
# (the surface-Ab row's result is not consulted).
_CATEGORY_NAMES = {
    "ua": _UA_NAMES,
    "ucx": _UCX_NAMES,
    "cbc": _CBC_NAMES,
    "tsh": _TSH_NAMES,
    "t3": _T3_NAMES,
    "t4": _T4_NAMES,
    "tpo": _TPO_NAMES,
    "tgab": _TGAB_NAMES,
    "tsi": _TSI_NAMES,
    "a1c": _A1C_NAMES,
    "glu": _GLU_NAMES,
    "lipid": _LIPID_NAMES,
    "lpa": _LPA_NAMES,
    "apob": _APOB_NAMES,
    "vitd": _VITD_NAMES,
    "pth": _PTH_NAMES,
    "mg": _MG_NAMES,
    "phos": _PHOS_NAMES,
    "zinc": _ZINC_NAMES,
    "fsh": _FSH_NAMES,
    "estradiol": _ESTRADIOL_NAMES,
    "uric": _URIC_NAMES,
    "psa": _PSA_NAMES,
    "inrpt": _INRPT_NAMES,
    "ptt": _PTT_TTT_NAMES,
    "bnp": _BNP_NAMES,
    "hpylori": _HPYLORI_NAMES,
    "stool": _STOOL_NAMES,
    "stool_cx_campy": _STOOL_CX_CAMPY_NAMES,
    "stool_cx_ecoli": _STOOL_CX_ECOLI_NAMES,
    "stool_cx_salm": _STOOL_CX_SALM_NAMES,
    "albcr": _ALBCR_NAMES,
    "hav": _HAV_NAMES,
    "measles": _MEASLES_NAMES,
    "mumps": _MUMPS_NAMES,
    "rubella": _RUBELLA_NAMES,
    "varicella": _VARICELLA_NAMES,
    "iron": _IRON_NAMES,
    "ferritin": _FERRITIN_STANDALONE_NAMES,
    "b12": _B12_NAMES,
    "fa": _FA_NAMES,
    "liver": _LIVER_NAMES,
    "ggt": _GGT_NAMES,
    "amylase": _AMYLASE_NAMES,
    "lipase": _LIPASE_NAMES,
    "ana": _ANA_NAMES,
    "esr": _ESR_NAMES,
    "crp": _CRP_NAMES,
    "afp": _AFP_NAMES,
    "cea": _CEA_NAMES,
    "ca125": _CA125_NAMES,
    "ca199": _CA199_NAMES,
    "ldh": _LDH_NAMES,
    "qtb": _QTB_NAMES,
    "hcv": _HCV_NAMES,
    "hbsag": _HBSAG_NAMES,
    "hbsab": _HBSAB_NAMES,
    "hbsabq": _HBSABQ_NAMES,
    "hiv": _HIV_NAMES,
    "rpr": _RPR_NAMES,
    "hsv": _HSV_NAMES,
    "gc": _GC_NAMES,
    "treponema": _TREPONEMA_NAMES,
    "hbv_dna": _HBV_DNA_NAMES,
    "hcv_rna": _HCV_RNA_NAMES,
    "eag": _EAG_NAMES,
    "hbcab": _HBCAB_NAMES,
    "hdv": _HDV_NAMES,
    "htlv": _HTLV_NAMES,
}


def _parse_items(result):
    """Parse a row's `result` JSON into a list of item dicts.

    Returns `None` when the row has no usable result: `result` is
    `None`/empty, is not a JSON array, or the array holds no item
    dicts with an `itemName`.  Items are normalised to
    `{"name": str, "value": str, "flag": str | None,
    "range": str, "units": str, "notes": str}`; a missing or null
    value becomes `""`, a missing or null range becomes `""`, a
    missing units becomes `""` and a missing or null `paramNotes`
    becomes `""`.
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
            "name": str(item_name),
            "value": "" if value is None else str(value),
            "flag": entry.get("flag"),
            "range": "" if rng is None else str(rng),
            "units": str(entry.get("units") or ""),
            "notes": "" if notes is None else str(notes),
        })
    return items or None


def _is_abnormal(flag):
    """True when an item flag marks the item abnormal (see module doc)."""
    if flag is None:
        return False
    return str(flag).strip().lower() not in _NORMAL_FLAGS


def _abnormal_items(items):
    """The abnormal items of a parsed result, in report order."""
    return [it for it in items if _is_abnormal(it["flag"])]


def _bound_for(flag, rng):
    """The reference-range limit a flagged value violates, rendered
    without trailing zeros (``<75.0`` -> ``75``, ``16-77`` + ``H`` ->
    ``77``, ``2.5-10.2`` + ``L`` -> ``2.5``).  ``None`` when the
    range has no parsable limit for the flag: an empty range, an
    ``A`` flag on a two-sided range, or a one-sided bound in the
    other direction (an ``H`` flag on ``>39``)."""
    rng = rng.strip()
    if not rng:
        return None
    if rng.startswith("<"):
        # One-sided upper limit; violated by a high (or an
        # undirected abnormal) flag.  The bound's number is parsed
        # out, so both `<75.0` and `< OR = 75` render `75`.
        part = rng if flag in ("H", "A") else None
    elif rng.startswith(">"):
        # One-sided lower limit; violated by a low flag.
        part = rng if flag in ("L", "A") else None
    elif "-" in rng:
        lo, hi = (part.strip() for part in rng.split("-", 1))
        part = hi if flag == "H" else (lo if flag == "L" else None)
    else:
        part = None
    if part is None:
        return None
    m = re.search(r"\d+(?:\.\d+)?", part)
    if m is None:
        return None
    return f"{float(m.group()):g}"


def _flag_token(label, items, fmt=None):
    """`{label} nl` when the result's first item is normal; otherwise
    `{label} {val}({bound})` where the bound is the reference-range
    limit the flagged value violates (`_bound_for`); without a
    parsable bound the token is plain `{label} {val}`.  When `fmt` is
    given it maps the raw value to its rendered form (LpA renders
    the value as an integer).  None when the value is empty on an
    abnormal result."""
    it = items[0]
    if not _is_abnormal(it["flag"]):
        return f"{label} nl"
    value = it["value"].strip()
    if not value:
        return None
    shown = fmt(value) if fmt is not None else value
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
    m = re.search(r"\d+(?:\.\d+)?", value)
    if m:
        num = f"{float(m.group()):g}"
        if "<" in value:
            return f"pH<{num}"
        if ">" in value:
            return f"pH>{num}"
        return f"pH {num}"
    return f"pH {value}" if value else None


def _ua_token(items):
    """Token for a UA result: `UA nl`, or `UA ` + the abnormal items
    in report order as short tokens (see the module docstring):
    `pH<5`-style for pH, `crystals+` for an abnormal crystals item, and
    `{name} {value}` in lower case (a `trace` value gains a `+`) for
    the rest."""
    parts = []
    for it in _abnormal_items(items):
        name = it["name"].strip().lower()
        value = it["value"].strip()
        if name in _UA_IGNORED_NAMES or (name, value.lower()) in _UA_IGNORED:
            continue
        if "crystals" in name:
            if value.lower() not in _UA_CRYSTALS_ABSENT:
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
    """The urine-culture token (rule 1a): `Ucx neg` for a negative
    result (the result item's `No growth` value and its friends);
    `Ucx {value}` for any other nonempty value, the organism text
    written as reported on the report (the yellow notes write a
    positive culture as `Ucx Staphy`, `Ucx- E Coli`, ...).  A pending
    / empty value and a reflex that never fired (no culture item)
    produce nothing."""
    it = next(
        (it for it in items if it["name"].strip().lower() in _UCX_ITEMS),
        None,
    )
    if it is None:
        return None
    value = it["value"].strip()
    if not value:
        return None
    if value.lower() in _UCX_NEGATIVE:
        return "Ucx neg"
    return f"Ucx {value}"


def _round1(value):
    """`value` rounded to one decimal place, a `.x5` tie rounded half
    up (`6.85` -> `6.9`; float formatting sees `6.85` as
    `6.84999...` and would render `6.8`); an unparseable value is
    written out raw.  The yellow sticky notes round ties up.
    """
    try:
        rounded = Decimal(value.strip()).quantize(
            Decimal("0.1"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return value
    return f"{rounded:f}"


def _g(value):
    """A numeric value with its trailing zeros stripped via `%g`
    (`101.0` -> `101`, `86.2` stays `86.2`); an unparseable value is
    written out as-is."""
    try:
        return f"{float(value):g}"
    except ValueError:
        return value


def _cbc_token(items):
    """`RBC {val}({bound})` when the CBC result's red blood cell
    count item is abnormal: the value rounded to one decimal place
    (5.43 -> `RBC 5.4(5.1)`, a `.x5` tie half up, 6.85 -> `RBC
    6.9(5.8)`; raw value when it is not a number) and the bound is
    the reference-range limit the value violates
    (`_bound_for`); without a parsable bound the token is plain
    `RBC {val}`.  A normal RBC produces nothing."""
    it = next(
        (it for it in items if it["name"].strip().lower() in _RBC_ITEMS),
        None,
    )
    if it is None or not _is_abnormal(it["flag"]):
        return None
    value = it["value"].strip()
    if not value:
        return None
    shown = _round1(value)
    bound = _bound_for(str(it["flag"] or "").strip().upper(), it["range"])
    if not bound:
        return f"RBC {shown}"
    return f"RBC {shown}({bound})"


def _cbc_mcv_token(items):
    """`MCV {val}({bound})` when the CBC result's MCV item (named
    `MCV` in both vendors' layouts) is abnormal: the value's
    trailing zeros stripped (`101.0` -> `MCV 101`, `86.2` -> `MCV
    86.2`; an unparseable value is written out raw) and the bound is
    the reference-range limit the value violates (upper limit for
    `H`, lower limit for `L`; `79-97` + `L` -> `MCV 70(79)`,
    `79-97` + `H` -> `MCV 105(97)`); without a parsable range the
    token is plain `MCV {val}`.  A normal MCV produces nothing.
    Emitted for a violated limit in either direction, like the RBC.
    """
    it = next(
        (it for it in items if it["name"].strip().lower() in _MCV_ITEMS),
        None,
    )
    if it is None or not _is_abnormal(it["flag"]):
        return None
    value = it["value"].strip()
    if not value:
        return None
    try:
        shown = f"{float(value):g}"
    except ValueError:
        shown = value
    bound = _bound_for(str(it["flag"] or "").strip().upper(), it["range"])
    if not bound:
        return f"MCV {shown}"
    return f"MCV {shown}({bound})"


def _named_item_token(items, names, label, fmt):
    """`{label} {val}({bound})` for the result's first item whose
    stripped, lower-cased name is in `names` and which is flagged
    abnormal: the value is rendered with `fmt` and the parenthesized
    bound is the reference-range limit the value violates
    (`_bound_for`; a plain `{label} {val}` when the bound is not
    parseable).  Normal, missing or empty-valued items yield nothing.
    (The CBC's WBC / Hb / Plt / Hct items and the liver panel's BUN /
    bilirubin / AP / albumin items all share this shape.)"""
    it = next(
        (it for it in items if it["name"].strip().lower() in names),
        None,
    )
    if it is None or not _is_abnormal(it["flag"]):
        return None
    value = it["value"].strip()
    if not value:
        return None
    shown = fmt(value)
    bound = _bound_for(str(it["flag"] or "").strip().upper(), it["range"])
    if not bound:
        return f"{label} {shown}"
    return f"{label} {shown}({bound})"


def _named_flag_token(items, names, label, fmt=None):
    """`{label} nl` when the result's first item whose stripped,
    lower-cased name is in `names` is normal; otherwise `{label}
    {val}({bound})` where the bound is the reference-range limit the
    flagged value violates (`_bound_for`; a plain `{label} {val}`
    when the bound is not parseable).  `fmt` maps the raw value to
    its rendered form when given; an empty value on an abnormal
    result yields nothing, and a missing item yields nothing too.
    (The estradiol / INR-PT / PTT / BNP / amylase / lipase / CA 19-9
    / LDH categories share this shape.)"""
    it = next(
        (it for it in items if it["name"].strip().lower() in names),
        None,
    )
    if it is None:
        return None
    if not _is_abnormal(it["flag"]):
        return f"{label} nl"
    value = it["value"].strip()
    if not value:
        return None
    shown = fmt(value) if fmt is not None else value
    bound = _bound_for(str(it["flag"] or "").strip().upper(), it["range"])
    if not bound:
        return f"{label} {shown}"
    return f"{label} {shown}({bound})"


def _cbc_wbc_token(items):
    """`WBC {val}({bound})` for an abnormal white blood cell count
    item (`WHITE BLOOD CELL COUNT` / `WBC`): the value to one decimal
    via `_round1` (like RBC), the bound via `_bound_for` (plain
    `WBC {val}` when unparseable); a normal item produces nothing."""
    return _named_item_token(items, _WBC_ITEMS, "WBC", _round1)


def _cbc_hb_token(items):
    """`Hb {val}({bound})` for an abnormal hemoglobin item
    (`HEMOGLOBIN` / `Hemoglobin`): the value to one decimal via
    `_round1` (like RBC), the bound via `_bound_for`; a normal item
    produces nothing."""
    return _named_item_token(items, _HB_ITEMS, "Hb", _round1)


def _cbc_plt_token(items):
    """`Plt {val}({bound})` for an abnormal platelet count item
    (`PLATELET COUNT` / `Platelets`): the value's trailing zeros
    stripped via `%g`, the bound via `_bound_for`; a normal item
    produces nothing."""
    return _named_item_token(items, _PLT_ITEMS, "Plt", _g)


def _cbc_hct_token(items):
    """`Hematocrit {val}({bound})` for an abnormal hematocrit item
    (`HEMATOCRIT` / `Hematocrit`): the value's trailing zeros stripped
    via `%g`, the bound via `_bound_for`; a normal item produces
    nothing."""
    return _named_item_token(items, _HCT_ITEMS, "Hematocrit", _g)


def _cbc_eos_token(items):
    """`Eos {val}({bound})` for an abnormal absolute-eosinophil item
    of a CBC (`ABSOLUTE EOSINOPHILS` on Quest, `Eos (Absolute)` on
    LabCorp): the value's trailing zeros stripped via `%g` (LabCorp's
    `0.5` in `0.0-0.4` -> `Eos 0.5(0.4)`, Quest's `526` in
    `15-500` -> `Eos 526(500)`), the bound via `_bound_for`; a
    normal item produces nothing.  The percentage eosinophil items
    are not it."""
    return _named_item_token(items, _EOS_ITEMS, "Eos", _g)


def _liver_bun_token(items):
    """`BUN {val}({bound})` for an abnormal urea-nitrogen item of a
    liver panel (`UREA NITROGEN (BUN)` / `BUN`): the value's trailing
    zeros stripped via `%g`, the bound via `_bound_for` (a plain
    `BUN {val}` when unparseable); a normal item produces nothing."""
    return _named_item_token(items, _BUN_ITEMS, "BUN", _g)


def _liver_bilirubin_token(items):
    """`bilirubin {val}({bound})` for an abnormal total-bilirubin item
    of a liver panel (`BILIRUBIN, TOTAL` / `Bilirubin, Total`); a
    normal item produces nothing."""
    return _named_item_token(items, _BILI_ITEMS, "bilirubin", _g)


def _ggt_token(items):
    """`GGT {val}({bound})` for an abnormal standalone GGT order
    (rule 30a): the `GGT` item's value with its trailing zeros
    stripped via `%g`, the bound via `_bound_for` (a plain
    `GGT {val}` when unparseable); e.g. `GGT 85(60)`.  Normal
    results produce nothing."""
    return _named_item_token(items, _GGT_ITEMS, "GGT", _g)


def _liver_alp_token(items):
    """`AP {val}({bound})` for an abnormal alkaline-phosphatase item of
    a liver panel (`ALKALINE PHOSPHATASE` / `Alkaline Phosphatase, S`);
    a normal item produces nothing."""
    return _named_item_token(items, _ALP_ITEMS, "AP", _g)


def _liver_albumin_token(items):
    """`albumin {val}({bound})` for an abnormal albumin item of a liver
    panel (`ALBUMIN` / `Albumin, Serum`); a normal item produces
    nothing."""
    return _named_item_token(items, _ALB_ITEMS, "albumin", _g)


def _liver_electrolyte_tokens(items):
    """The liver panel's electrolyte tokens (rule 30): one token per
    abnormal item, in the order Ca / Na / Cl / K, `{label} {val}
    ({bound})` (the value's trailing zeros stripped via `%g`, the
    bound via `_bound_for`; a plain `{label} {val}` when
    unparseable) -- e.g. `Ca 10.3(10.2), Na 134(136), Cl 109(107),
    K 6(5.1)` -- and nothing for the normal items, like BUN / Cr."""
    tokens = []
    for names, label in ((_CA_ITEMS, "Ca"), (_NA_ITEMS, "Na"),
                         (_CL_ITEMS, "Cl"), (_K_ITEMS, "K")):
        token = _named_item_token(items, names, label, _g)
        if token:
            tokens.append(token)
    return tokens


def _cr_token(items):
    """The creatinine / CrCl token of a liver panel: the `CREATININE`
    item plus, as CrCl, the panel's `EGFR` item (the standalone
    hepatic-function panels carry neither).  When both are abnormal,
    one combined token `Cr/CrCl {cr}/{crcl}({bound})` -- Cr the raw
    value, CrCl via `%g`, the trailing bound the limit CrCl violates
    (the 60 floor of the one-sided `> OR = 60` range via
    `_bound_for` on the `L` flag; it falls back to Cr's bound if
    CrCl's is unparseable).  When only Cr is abnormal: `Cr
    {val}({bound})`; when only eGFR is abnormal: `CrCl {val}
    ({bound})`; when neither is abnormal: nothing.  An item flagged
    abnormal with an empty value counts as normal."""
    cr = next(
        (it for it in items if it["name"].strip().lower() in _CR_ITEMS),
        None,
    )
    egfr = next(
        (it for it in items if it["name"].strip().lower() in _EGFR_ITEMS),
        None,
    )
    cr_abn = cr is not None and _is_abnormal(cr["flag"]) \
        and bool(cr["value"].strip())
    egfr_abn = egfr is not None and _is_abnormal(egfr["flag"]) \
        and bool(egfr["value"].strip())
    if not cr_abn and not egfr_abn:
        return None
    if cr_abn and not egfr_abn:
        return _val_bound("Cr", cr, None)
    if egfr_abn and not cr_abn:
        return _val_bound("CrCl", egfr, _g)
    bound = _bound_for(str(egfr["flag"] or "").strip().upper(), egfr["range"]) \
        or _bound_for(str(cr["flag"] or "").strip().upper(), cr["range"])
    token = f"Cr/CrCl {cr['value'].strip()}/{_g(egfr['value'].strip())}"
    if bound:
        token += f"({bound})"
    return token


def _val_bound(label, it, fmt):
    """`{label} {val}({bound})` for one flagged item: the value via
    `fmt` when given (Cr writes its raw value, CrCl via `%g`), the
    bound via `_bound_for` (a plain `{label} {val}` when unparseable)."""
    value = it["value"].strip()
    shown = fmt(value) if fmt is not None else value
    bound = _bound_for(str(it["flag"] or "").strip().upper(), it["range"])
    if not bound:
        return f"{label} {shown}"
    return f"{label} {shown}({bound})"


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


def _tsh_token(latest):
    """`TSH {val:.1f}` from the result's first item (the TSH value in
    all of the category's layouts); raw value if it is not a number,
    None if the value is empty.  When the result carries a free-T4
    item the token gains a suffix: `/T4 nl` for a normal T4, `/T4
    {val}` (raw value) for an abnormal one, e.g. `TSH 0.8/T4 nl`; when
    it does not (the standalone `TSH` / cascade-profile layouts), the
    newest standalone `free t4` order's item supplies the same suffix
    (rule 2), and that T4 is then not a thyroid-cluster member
    (`_thyroid_cluster_tokens`)."""
    items = latest["tsh"]
    value = items[0]["value"].strip()
    if not value:
        return None
    try:
        token = f"TSH {float(value):.1f}"
    except ValueError:
        token = f"TSH {value}"
    t4 = _t4_item(items)
    if t4 is None and "t4" in latest:
        t4 = next(
            (it for it in latest["t4"]
             if it["name"].strip().lower() in _T4_ITEMS),
            None,
        )
    if t4 is not None and t4["value"].strip():
        if _is_abnormal(t4["flag"]):
            token += f"/T4 {t4['value'].strip()}"
        else:
            token += "/T4 nl"
    return token


def _thyroid_cluster_tokens(latest):
    """The thyroid-cluster tokens (rule 2a): the thyroid members the
    TSH token does not carry -- free T3, the TPO and thyroglobulin
    antibodies, and TSI, plus the standalone free T4 when it did not
    supply a TSH token's `/T4` suffix (no TSH row, or a TSH result
    with its own free-T4 item).  The normal members join one token,
    their labels in the fixed member order `T4` / `T3` / `TPO` /
    `thyroglobulin` / `TSI` joined with `/` and a single trailing
    ` nl` (`TPO/thyroglobulin nl`, `TSI nl`); each abnormal member
    reports its own `{label} {val}({bound})` token right after it, in
    the same member order (value raw, bound via `_bound_for`).  A
    member whose newest row has no usable item / value produces
    nothing (a pending free T4 that a TSH token would have taken on
    produces neither suffix nor member)."""
    t4_joined = ("tsh" in latest and _t4_item(latest["tsh"]) is None
                 and "t4" in latest)
    members = []
    if "t4" in latest and not t4_joined:
        members.append(("t4", "T4", _T4_ITEMS))
    for category, label, item_names in (
            ("t3", "T3", _T3_ITEMS),
            ("tpo", "TPO", _TPO_ITEMS),
            ("tgab", "thyroglobulin", _TGAB_ITEMS),
            ("tsi", "TSI", _TSI_ITEMS),
    ):
        if category in latest:
            members.append((category, label, item_names))
    normal, abnormal = [], []
    for category, label, item_names in members:
        token = _named_flag_token(latest[category], item_names, label)
        if token is None:
            continue
        if token.endswith(" nl"):
            normal.append(label)
        else:
            abnormal.append(token)
    tokens = ["/".join(normal) + " nl"] if normal else []
    tokens.extend(abnormal)
    return tokens


def _fsh_token(items):
    """`FSH nl` when the FSH result is normal; `FSH {val}({bound})`
    when abnormal (the bound via `_bound_for`; the in-house order
    carries no reference range, so usually plain `FSH {val}`)."""
    return _flag_token("FSH", items)


def _estradiol_token(items):
    """`Estradiol nl` when the estradiol result is normal; `Estradiol
    {val}({bound})` when abnormal (the in-house order carries no
    reference range, so usually plain `Estradiol {val}`; rule 4)."""
    return _named_flag_token(items, _ESTRADIOL_NAMES, "Estradiol")


def _a1c_token(items, glu=None):
    """`A1c {val}` with the value's trailing zeros stripped (a
    numeric value renders via `%g`, so `6.0` -> `A1c 6`); raw
    value when not a number; emitted for normal and abnormal results
    alike.  When `glu` (the newest liver panel's glucose value, via
    `_liver_glucose`) is not None the token is instead `Glu
    {glu}/A1c {val}` with the glucose value rendered the same way
    (22457's GLUCOSE 86 and A1c 5.7 -> `Glu 86/A1c 5.7`)."""
    it = items[0]
    value = it["value"].strip()
    if not value:
        return None
    try:
        a1c = f"{float(value):g}"
    except ValueError:
        a1c = value
    if glu is None:
        return f"A1c {a1c}"
    try:
        g = f"{float(glu):g}"
    except ValueError:
        g = glu
    return f"Glu {g}/A1c {a1c}"


def _glu_token(items):
    """`Glu {val}({bound})` for an abnormal standalone-glucose order
    (rule 5a): the `GLUCOSE` / `Glucose, Serum` item's value's
    trailing zeros stripped via `%g`, the bound via `_bound_for` (a
    plain `Glu {val}` when unparseable); e.g. `Glu 122(99)`.  Normal
    results produce nothing.  It is separate from the liver panel's
    glucose, which joins the A1c token (rule 5)."""
    return _named_item_token(items, _GLUCOSE_ITEMS, "Glu", _g)


def _ldl_token(items):
    """`LDL {val}` (raw value of the calculated-LDL item, LabCorp's
    `LDL Chol Calc (NIH)` or Quest's `LDL-CHOLESTEROL`) for normal
    and abnormal panels alike, whenever the panel carries that item
    and its value is usable (a normal panel's LDL 39 renders `LDL
    39`).  When the panel's triglycerides are high the token is
    instead the shorthand `{HDL}/{LDL}/{TG}({bound})` -- the panel's
    HDL value, the calculated-LDL value, and the triglyceride value,
    with the triglyceride's reference upper limit in parentheses
    (`_bound_for` on the TG item's range, such as `0-149` ->
    `45/131/151(149)`); without a parsable bound there are no
    parentheses.  When the high-TG panel lacks an HDL or a
    calculated-LDL value the plain `LDL {val}` token is kept.  A
    panel that carries no calculated-LDL item produces nothing, in
    either case."""
    ldl = next(
        (it for it in items if it["name"].strip().lower() in _LDL_ITEMS),
        None,
    )
    if ldl is None:
        return None
    ldl_value = ldl["value"].strip()
    if not ldl_value:
        return None
    tg = next(
        (it for it in items if it["name"].strip().lower() in _TG_ITEMS),
        None,
    )
    if tg is None or not _is_abnormal(tg["flag"]):
        return f"LDL {ldl_value}"
    tg_value = tg["value"].strip()
    hdl = next(
        (it for it in items if it["name"].strip().lower() in _HDL_ITEMS),
        None,
    )
    hdl_value = (hdl["value"].strip() if hdl is not None else "")
    if not tg_value or not hdl_value:
        return f"LDL {ldl_value}"
    bound = _bound_for(str(tg["flag"] or "").strip().upper(), tg["range"])
    if not bound:
        return f"{hdl_value}/{ldl_value}/{tg_value}"
    return f"{hdl_value}/{ldl_value}/{tg_value}({bound})"


def _albc_token(items):
    """`Alb/Cr<30` when the microalbumin/creatinine result is normal
    (no abnormal item); `Alb/Cr {val}` (raw value of the ratio item,
    the first item whose name contains "ratio") when abnormal."""
    ratio = next((it for it in items if "ratio" in it["name"].lower()), None)
    if ratio is None:
        return None
    if _abnormal_items(items):
        value = ratio["value"].strip()
        return f"Alb/Cr {value}" if value else None
    return "Alb/Cr<30"


def _int_value(value):
    """A value rendered as an integer (`227.3` -> `227`, `42.2` ->
    `42`); an unparseable value is written out raw."""
    try:
        return f"{float(value):.0f}"
    except ValueError:
        return value


def _lpa_token(items):
    """`LpA nl` when the Lipoprotein (a) result is normal; `LpA
    {val}({bound})` when abnormal, the value rendered as an integer
    and the bound being the upper limit parsed from the one-sided
    `<{hi}` range (227.3 in `<75.0` -> `LpA 227(75)`); without a
    parsable bound the token is plain `LpA {val}`."""
    return _flag_token("LpA", items, _int_value)


def _apob_token(items):
    """`ApoB nl` when the apolipoprotein B result is normal; `ApoB
    {val}({bound})` when abnormal, the bound being the upper limit
    parsed from the one-sided `<{hi}` range (102 in `<90` -> `ApoB
    102(90)`); without a parsable bound the token is plain
    `ApoB {val}`."""
    return _flag_token("ApoB", items)


def _vitd_token(items):
    """`VitD {val}` with the value rendered as an integer (`42.2` ->
    `VitD 42`; raw value when it is not a number), emitted for normal
    and abnormal results alike."""
    it = next(
        (it for it in items if "vitamin d" in it["name"].lower()),
        items[0],
    )
    value = it["value"].strip()
    if not value:
        return None
    return f"VitD {_int_value(value)}"


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
    if not bound:
        return f"PTH {value}"
    return f"PTH {value}({bound})"


def _mg_token(items):
    """`Mg nl` when the serum magnesium result is normal; `Mg
    {val}({bound})` when abnormal (the bound via `_bound_for`)."""
    return _flag_token("Mg", items)


def _uric_token(items):
    """`uric acid {val}` (raw value) when the uric acid result is
    normal."""
    it = items[0]
    if _is_abnormal(it["flag"]):
        return None
    value = it["value"].strip()
    return f"uric acid {value}" if value else None


def _psa_token(items):
    """`PSA {val}` with the value's trailing zeros stripped (a
    numeric value renders via `%g`, so `1.40` -> `PSA 1.4`); raw
    value when not a number; emitted for normal and abnormal results
    alike."""
    it = items[0]
    value = it["value"].strip()
    if not value:
        return None
    try:
        return f"PSA {float(value):g}"
    except ValueError:
        return f"PSA {value}"


def _inrpt_tokens(items):
    """The INR / PT tokens (rule 18): the result's `INR` and
    prothrombin-time items (`PT` / `Prothrombin Time`).  One token
    per abnormal item, `INR` first: `INR {val}({bound})` / `PT
    {val}({bound})` (the values' trailing zeros stripped via `%g`,
    the bound via `_bound_for`; the `INR` item usually carries no
    reference range, so an abnormal INR is usually plain `INR
    {val}`).  When neither item is abnormal: `INR/PT nl` when both
    items are present (a valued item), `INR nl` / `PT nl` when only
    one is."""
    inr = next(
        (it for it in items if it["name"].strip().lower() in _INR_ITEMS),
        None,
    )
    pt = next(
        (it for it in items if it["name"].strip().lower() in _PT_ITEMS),
        None,
    )
    tokens = []
    for label, it in (("INR", inr), ("PT", pt)):
        if it is None:
            continue
        if _is_abnormal(it["flag"]) and it["value"].strip():
            tokens.append(_val_bound(label, it, _g))
    if tokens:
        return tokens
    present = [label for label, it in (("INR", inr), ("PT", pt))
               if it is not None and it["value"].strip()]
    if len(present) == 2:
        return ["INR/PT nl"]
    if len(present) == 1:
        return [f"{present[0]} nl"]
    return []


def _ptt_token(items):
    """`PTT nl` / `PTT {val}({bound})` for the partial-thromboplastin-
    time result (the `_named_flag_token` shape, on the `PARTIAL
    THROMBOPLASTIN TIME, ACTIVATED` / `PARTIAL THROMBOPLASTIN$TIME,
    ACTIVATED` item; rule 19)."""
    return _named_flag_token(items, _PTT_ITEMS, "PTT")


def _bnp_token(items):
    """`BNP nl` / `BNP {val}({bound})` for the B-type natriuretic-
    peptide result (the `_named_flag_token` shape; rule 20)."""
    return _named_flag_token(items, _BNP_ITEMS, "BNP")


def _hav_token(items):
    """`HAV Ab+` when the HAV total antibody (single item in both
    vendors' layouts) is positive (Quest's `REACTIVE`, LabCorp's
    `Positive`); a negative / equivocal value produces nothing.  HAV
    IgM is a different test and is not part of this category."""
    value = items[0]["value"].strip().lower()
    return "HAV Ab+" if value in _POSITIVE_VALUES else None


def _measles_token(items):
    """`measles Ab+` when the measles IgG level (the `MEASLES
    ANTIBODY (IGG)` / `Rubeola Ab, IgG` item -- the result's only
    item on the standalone orders, one of three on the MMR panel; AU/mL
    in both vendors' layouts, Quest caps it at `>300.00`) is above the
    immunity cutoff; the level is the value's number, so a capped
    `>300.00` counts; non-immune / equivocal / number-less levels
    produce nothing (rule 26)."""
    it = next(
        (it for it in items
         if it["name"].strip().lower() in _MEASLES_ITEMS),
        None,
    )
    if it is None:
        return None
    value = it["value"].strip()
    m = re.search(r"\d+(?:\.\d+)?", value)
    if m is None:
        return None
    level = float(m.group())
    return "measles Ab+" if level > _MEASLES_IMMUNE_ABOVE else None


def _mumps_token(items):
    """`mumps Ab+` when the mumps IgG level (the mumps item of the
    MMR order -- `MUMPS VIRUS$ANTIBODY (IGG)` on Quest's MMR panel,
    `Mumps Abs, IgG` on LabCorp's `MMR` order; AU/mL, Quest caps it
    at `>300.00`) is above the immunity cutoff (the 9.00-10.99 band
    is equivocal); the level is the value's number, so a capped
    `>300.00` counts; non-immune / equivocal / number-less levels
    produce nothing (rule 26a)."""
    it = next(
        (it for it in items if it["name"].strip().lower() in _MUMPS_ITEMS),
        None,
    )
    if it is None:
        return None
    value = it["value"].strip()
    m = re.search(r"\d+(?:\.\d+)?", value)
    if m is None:
        return None
    level = float(m.group())
    return "mumps Ab+" if level > _MUMPS_IMMUNE_ABOVE else None


def _rubella_token(items):
    """`rubella Ab+` when the rubella IgG index (the `RUBELLA
    ANTIBODY (IGG)` / `Rubella Antibodies, IgG` item, both vendors'
    layouts -- LabCorp's on the standalone order and its `MMR` order)
    is above the immunity cutoff (the 0.90-0.99 band is equivocal);
    the level is the value's number, so a capped value
    counts when its number is above; non-immune / equivocal /
    number-less levels produce nothing (rule 26b)."""
    it = next(
        (it for it in items
         if it["name"].strip().lower() in _RUBELLA_ITEMS),
        None,
    )
    if it is None:
        return None
    value = it["value"].strip()
    m = re.search(r"\d+(?:\.\d+)?", value)
    if m is None:
        return None
    level = float(m.group())
    return "rubella Ab+" if level > _RUBELLA_IMMUNE_ABOVE else None


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
    m = re.search(r"\d+(?:\.\d+)?", value)
    if m is None:
        return None
    num = float(m.group())
    units = it["units"].strip().lower()
    if "s/co" in units:
        if value.startswith("<"):
            return "neg"
        return "pos" if num >= _VARICELLA_SCO_POSITIVE_AT else "neg"
    if "index" in units:
        if value.startswith("<"):
            if num < _VARICELLA_INDEX_NEGATIVE_BELOW:
                return "neg"
            return None
        if num >= _VARICELLA_INDEX_POSITIVE_AT:
            return "pos"
        if num < _VARICELLA_INDEX_NEGATIVE_BELOW:
            return "neg"
        return None
    return None


def _varicella_token(items):
    """`varicella Ab+` when the VZV IgG result (the IgG item of the
    varicella order, per layout; the combo order's IgM item is the
    acute-infection marker and is not it) is positive / reactive
    (`_varicella_state`); a negative / non-reactive result, an
    equivocal value and a missing IgG item produce nothing (rule
    26c)."""
    it = next(
        (it for it in items
         if it["name"].strip().lower() in _VARICELLA_ITEMS),
        None,
    )
    if _varicella_state(it) == "pos":
        return "varicella Ab+"
    return None


def _iron_label(name):
    """The sticky label for an iron-panel item name, or None for items
    the summary does not name (the derived `UIBC`, ...)."""
    n = name.strip().lower()
    if n in _IRON_SERUM_ITEMS:
        return "iron"
    if n in _TIBC_ITEMS:
        return "TIBC"
    if n in _IRONSAT_ITEMS:
        return "iron%sat"
    if n in _FERRITIN_ITEMS:
        return "ferritin"
    return None


def _iron_token(items):
    """`iron nl` when every item of the iron panel is normal.  When the
    panel is abnormal, one token per abnormal item, in report order,
    `{label} {val}({bound})` (labels via `_iron_label`; the bound via
    `_bound_for`, a plain `{label} {val}` when unparseable; the value's
    trailing zeros stripped via `%g`; an abnormal item with no label or
    an empty value yields no token of its own but still suppresses the
    `iron nl`, like `UIBC`)."""
    tokens = []
    for it in _abnormal_items(items):
        label = _iron_label(it["name"])
        if label is None:
            continue
        value = it["value"].strip()
        if not value:
            continue
        shown = _g(value)
        bound = _bound_for(str(it["flag"] or "").strip().upper(), it["range"])
        tokens.append(
            f"{label} {shown}({bound})" if bound else f"{label} {shown}")
    if not tokens:
        return None if _abnormal_items(items) else "iron nl"
    return ", ".join(tokens)


def _ferritin_token(items):
    """`ferritin {val}({bound})` for an abnormal standalone-ferritin
    order (rule 27a): the `FERRITIN` / `Ferritin, Serum` item's value
    with its trailing zeros stripped via `%g`, the bound via
    `_bound_for` (a plain `ferritin {val}` when unparseable); e.g.
    `ferritin 693(400)`.  Normal results produce nothing."""
    return _named_item_token(
        items, _FERRITIN_STANDALONE_ITEMS, "ferritin", _g)


def _b12_token(items):
    """`B12 {val}({bound})` for an abnormal B12 (first item, both
    vendors' layouts): the bound is the reference-range limit the value
    violates (upper limit for `H`, lower limit for `L`, parsed from
    a `lo-hi` range); without a parsable range the token is plain
    `B12 {val}`.  Normal results produce nothing."""
    it = items[0]
    flag = str(it["flag"] or "").strip().upper()
    if flag in ("", "N"):
        return None
    value = it["value"].strip()
    if not value:
        return None
    rng = it["range"].strip()
    bound = rng
    if "-" in rng:
        lo, hi = (part.strip() for part in rng.split("-", 1))
        bound = hi if flag == "H" else (lo if flag == "L" else rng)
    if not bound:
        return f"B12 {value}"
    return f"B12 {value}({bound})"


def _value_above(it):
    """True when an item's value is above its reference range's upper
    limit: an `H` flag, or an undirected `A` flag whose value parses
    above a `lo-hi` range's limit (an `A` on a one-sided or empty
    range is not above).  Normal and low flags are not above."""
    flag = str(it["flag"] or "").strip().upper()
    if flag == "H":
        return True
    if flag != "A":
        return False
    rng = it["range"].strip()
    if "-" not in rng:
        return False
    m_hi = re.search(r"\d+(?:\.\d+)?", rng.split("-", 1)[1])
    m_val = re.search(r"\d+(?:\.\d+)?", it["value"])
    if m_hi is None or m_val is None:
        return False
    return float(m_val.group()) > float(m_hi.group())


def _hi_bound(rng):
    """The upper limit of a reference range as a number without
    trailing zeros (`10-35` -> `35`, `9-46` -> `46`, `<46` -> `46`);
    None when the range has no parsable upper limit (an empty range,
    a one-sided lower limit such as `> OR = 60`, or no number)."""
    rng = rng.strip()
    if not rng or rng.startswith(">"):
        return None
    part = rng.split("-", 1)[1] if "-" in rng else rng
    m = re.search(r"\d+(?:\.\d+)?", part)
    if m is None:
        return None
    return f"{float(m.group()):g}"


def _astalt_token(items):
    """The AST/ALT pair of a liver panel (CMP / hepatic function
    panel; the items named `AST` / `AST (SGOT)` and `ALT` /
    `ALT (SGPT)`).  Emitted only when either value is high
    (`_value_above`): `AST/ALT {ast}({bound})/{alt}({bound})` with
    each high value's violated upper limit in parentheses
    (`_hi_bound`; AST 42 in `10-35` and ALT 62 in `9-46` ->
    `AST/ALT 42(35)/62(46)`), a not-high member written plain; a
    high value without a parsable upper limit is plain too.  When
    only one of the two items is present the high one is emitted
    alone, e.g. `ALT 54(46)`; when neither value is high (or no item
    has a usable value) nothing is emitted."""
    ast = next(
        (it for it in items if it["name"].strip().lower() in _AST_ITEMS),
        None,
    )
    alt = next(
        (it for it in items if it["name"].strip().lower() in _ALT_ITEMS),
        None,
    )
    vals = []
    high = False
    for label, it in (("AST", ast), ("ALT", alt)):
        if it is None:
            continue
        value = it["value"].strip()
        if not value:
            continue
        if _value_above(it):
            high = True
            bound = _hi_bound(it["range"])
            if bound:
                vals.append((label, f"{value}({bound})"))
            else:
                vals.append((label, value))
        else:
            vals.append((label, value))
    if not high or not vals:
        return None
    if len(vals) == 1:
        # One item (or one usable value) only: emit it under its own
        # label, e.g. `ALT 54(46)`.
        return f"{vals[0][0]} {vals[0][1]}"
    return "AST/ALT " + "/".join(v for _, v in vals)


def _protein_token(items):
    """The total-protein token of a liver panel (Quest's `PROTEIN,
    TOTAL` item, LabCorp's `Protein, Total, Serum`): emitted only when
    the value is high (`_value_above`), as `protein {val}({bound})`
    with the violated upper limit in parentheses (`_hi_bound`; 8.4 in
    `6.1-8.1` -> `protein 8.4(8.1)`); a high value without a parsable
    upper limit is plain, and a not-high protein (or a missing /
    empty-valued item) produces nothing."""
    it = next(
        (it for it in items if it["name"].strip().lower() in _PROTEIN_ITEMS),
        None,
    )
    if it is None:
        return None
    value = it["value"].strip()
    if not value or not _value_above(it):
        return None
    bound = _hi_bound(it["range"])
    if not bound:
        return f"protein {value}"
    return f"protein {value}({bound})"


def _liver_glucose(items):
    """The glucose value of a liver panel (Quest's `GLUCOSE` item,
    LabCorp's `Glucose, Serum`), stripped; `None` when the panel has
    no glucose item or its value is empty (the hepatic function
    panels carry no glucose item at all).  The value joins the A1c
    token as `Glu {val}/A1c {val}` (see `_a1c_token`)."""
    it = next(
        (it for it in items if it["name"].strip().lower() in _GLUCOSE_ITEMS),
        None,
    )
    if it is None:
        return None
    value = it["value"].strip()
    return value or None


def _hiv_negative(items):
    """True when an HIV result is negative.

    Quest's 4th-gen Ag/Ab screen can be REACTIVE (flag N) on an
    HIV-negative patient: the reflex HIV 1/2 Ab and HIV RNA work-up
    decides, and its verdict is the `HIV FINAL INTERPRETATION` item
    (``HIV NEGATIVE``).  A result without that item (LabCorp's
    single `HIV Screen 4th Generation wRfx` item) is negative when
    nothing is flagged abnormal and every item value is
    non-reactive / negative.
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
    """`neg` / `pos` for one HSV type-specific IgG item (rule 21a),
    or `None` when the result is undetermined (a missing / pending /
    empty value, the 0.90-1.09 equivocal band, or an unrecognized
    value).  The value decides, not the flag (see
    `_HSV_POSITIVE_ABOVE`): a negative value (LabCorp's `Non
    Reactive`, Quest's `<0.90`) or an index below 0.90 is negative;
    `Reactive` / `Positive` or an index above 1.09 (a capped
    `>58.00` counts) is positive."""
    if it is None:
        return None
    value = it["value"].strip()
    if not value:
        return None
    low = value.lower()
    if low in _NEGATIVE_VALUES or low.startswith("<"):
        return "neg"
    if low in _POSITIVE_VALUES:
        return "pos"
    m = re.search(r"\d+(?:\.\d+)?", value)
    if m is not None:
        num = float(m.group())
        if num > _HSV_POSITIVE_ABOVE:
            return "pos"
        if num < _HSV_NEGATIVE_BELOW:
            return "neg"
    return None


def _hsv_states(latest):
    """The `(state1, state2)` of the HSV order's two type items (rule
    21a), each `neg` / `pos` / None via `_hsv_type_state` (a missing
    type item is None); both None when there is no `hsv` row."""
    if "hsv" not in latest:
        return None, None
    items = latest["hsv"]
    h1 = next((it for it in items
               if it["name"].strip().lower() in _HSV1_ITEMS), None)
    h2 = next((it for it in items
               if it["name"].strip().lower() in _HSV2_ITEMS), None)
    return _hsv_type_state(h1), _hsv_type_state(h2)


def _std_token(latest):
    """The STD-marker token: one segment per group that is present
    and negative -- `HBV/HCV` (the hep B/C trio), `HIV`, `RPR`, the
    HSV types of rule 21a (`HSV` when both types are negative,
    `HSV1` / `HSV2` when only one is), `G-C` (the chlamydia /
    gonorrhea NAA, rule 21) and `Treponema` (the treponemal
    confirmatory, rule 21) -- joined with `/` and a trailing ` neg`,
    e.g. `HBV/HCV/HIV/RPR/HSV/G-C/Treponema neg` when everything is
    negative and `HBV/HCV neg` when only the hep trio is.  A missing
    member (or an abnormal surface-Ag / HCV result) drops the HBV/HCV
    group -- a reactive surface Ab is immunity, not infection, so it
    does not -- and an abnormal HIV / RPR result drops its group; a
    positive / undetermined HSV type drops only its own segment (the
    positive types report their own `HSV1+` / `HSV2+` tokens, see
    `_hsv_tokens`) and a positive / undetermined G-C / Treponema
    group drops only its own segment (a positive group reports its
    own `G-C+` / `Treponema+` token, see `_gc_token` /
    `_treponema_token`); nothing is emitted when no group is
    left."""
    parts = []
    if all(key in latest for key in ("hcv", "hbsag", "hbsab")) \
            and not _abnormal_items(latest["hcv"]) \
            and not _abnormal_items(latest["hbsag"]):
        parts.append("HBV/HCV")
    if "hiv" in latest and _hiv_negative(latest["hiv"]):
        parts.append("HIV")
    if "rpr" in latest and _rpr_negative(latest["rpr"]):
        parts.append("RPR")
    neg = [t for t, state in zip(("1", "2"), _hsv_states(latest))
           if state == "neg"]
    if len(neg) == 2:
        parts.append("HSV")
    elif neg:
        parts.append(f"HSV{neg[0]}")
    if "gc" in latest and _gc_state(latest["gc"]) == "neg":
        parts.append("G-C")
    if "treponema" in latest and \
            _treponema_state(latest["treponema"]) == "neg":
        parts.append("Treponema")
    if not parts:
        return None
    return "/".join(parts) + " neg"


def _hsv_tokens(latest):
    """The HSV positive tokens (rule 21a): one `HSV1+` / `HSV2+`
    token per positive type, or one combined `HSV1/HSV2+` when both
    types are positive (the yellow notes' labels); the negative
    types join the STD token's ` neg` list instead (`_std_token`).
    Undetermined types (the equivocal band, a pending / empty value,
    a missing item) produce nothing."""
    pos = [t for t, state in zip(("1", "2"), _hsv_states(latest))
           if state == "pos"]
    if len(pos) == 2:
        return ["HSV1/HSV2+"]
    if pos:
        return [f"HSV{pos[0]}+"]
    return []


def _naa_state(it):
    """`neg` / `pos` for one NAA pathogen item of the G-C / Treponema
    groups (rule 21), or `None` when undetermined (an empty / pending
    value or an unrecognized value).  A flagged-abnormal item is
    positive (Quest flags a detected NAA `A`, LabCorp a positive one
    `A`); a negative / not-detected value is negative; a positive /
    detected value is positive."""
    value = it["value"].strip().lower()
    if _is_abnormal(it["flag"]):
        return "pos"
    if not value:
        return None
    if value in _NEGATIVE_VALUES:
        return "neg"
    if value in _POSITIVE_VALUES or value == "detected":
        return "pos"
    return None


def _gc_items(items):
    """The G-C order's pathogen items (rule 21), in report order: the
    chlamydia and gonorrhea NAA items of the in-house / LabCorp /
    Quest layouts (Quest's chlamydia-only order carries the chlamydia
    item alone); Quest's layouts' `(Always Message)` note item is not
    a pathogen."""
    return [it for it in items if it["name"].strip().lower() in _GC_ITEMS]


def _gc_state(items):
    """`neg` / `pos` for the G-C group of the STD token (rule 21), or
    `None` when undetermined (no pathogen item, a pending / empty
    value, or an unrecognized value).  Any positive pathogen item
    makes the group positive; it is negative when every pathogen item
    is negative / not detected."""
    states = [_naa_state(it) for it in _gc_items(items)]
    if not states:
        return None
    if any(state == "pos" for state in states):
        return "pos"
    if all(state == "neg" for state in states):
        return "neg"
    return None


def _treponema_state(items):
    """`neg` / `pos` for the Treponema group of the STD token (rule
    21), or `None` when undetermined (no treponemal item, a pending /
    empty value, or an unrecognized value).  A positive item makes the
    group positive; it is negative when every treponemal item is
    negative."""
    states = [
        _naa_state(it) for it in items
        if it["name"].strip().lower() in _TREPONEMA_ITEMS
    ]
    if not states:
        return None
    if any(state == "pos" for state in states):
        return "pos"
    if all(state == "neg" for state in states):
        return "neg"
    return None


def _gc_token(latest):
    """The G-C positive token (rule 21): `G-C+` right after the STD
    token when the group is positive (any pathogen item detected /
    positive); the negative group joins the STD token's ` neg` list
    instead (`_std_token`), and an undetermined group produces
    nothing."""
    if "gc" in latest and _gc_state(latest["gc"]) == "pos":
        return "G-C+"
    return None


def _treponema_token(latest):
    """The Treponema positive token (rule 21): `Treponema+` right
    after the STD token when the group is positive (a POSITIVE
    value); the negative group joins the STD token's ` neg` list
    instead (`_std_token`), and an undetermined group produces
    nothing."""
    if "treponema" in latest and \
            _treponema_state(latest["treponema"]) == "pos":
        return "Treponema+"
    return None


def _qtb_token(items):
    """`QTB neg` when the QuantiFERON-TB interpretation item (the one
    whose value is NEGATIVE / POSITIVE / INDETERMINATE in both vendors'
    layouts) is negative; positive / indeterminate / missing produces
    nothing."""
    for it in items:
        value = it["value"].strip().lower()
        if value in _QTB_INTERPRETATIONS:
            return "QTB neg" if value == "negative" else None
    return None


def _fa_token(items):
    """`FA nl` when the B12/folate panel's folate item (Quest's
    `FOLATE, SERUM`, LabCorp's `Folate (Folic Acid), Serum`) is
    normal; `FA {val}({bound})` when it is flagged abnormal (the
    value's trailing zeros stripped via `%g`, the bound via
    `_bound_for` -- Quest's panel item carries no range, so the token
    is plain `FA {val}` there).  A missing folate item produces
    nothing (rule 29)."""
    it = next(
        (it for it in items if it["name"].strip().lower() in _FA_ITEMS),
        None,
    )
    if it is None:
        return None
    if not _is_abnormal(it["flag"]):
        return "FA nl"
    value = it["value"].strip()
    if not value:
        return None
    shown = _g(value)
    bound = _bound_for(str(it["flag"] or "").strip().upper(), it["range"])
    if not bound:
        return f"FA {shown}"
    return f"FA {shown}({bound})"


def _ana_token(items):
    """`ANA+` (with the item's titer appended, `ANA+ 1:80`, when a
    result value is one) when any ANA item is flagged abnormal; `ANA
    nl` when nothing is flagged abnormal (Quest's negative results
    and its empty-valued items both fall here); any other nonempty
    value produces nothing (rule 33)."""
    if _abnormal_items(items):
        for it in items:
            value = it["value"].strip()
            if re.fullmatch(r"1:\d+", value):
                return f"ANA+ {value}"
        return "ANA+"
    for it in items:
        value = it["value"].strip().lower()
        if not value:
            continue
        if value in _NEGATIVE_VALUES:
            continue
        return None
    return "ANA nl"


def _esrcrp_tokens(latest):
    """The ESR/CRP tokens (rule 34): `ESR/CRP nl` when both tests are
    present and normal; otherwise the abnormal member(s) as
    `ESR {val}({bound})` / `CRP {val}({bound})` (ESR first, the
    `_flag_token` shape) and a normal member reports its `ESR nl` /
    `CRP nl` only when the other test is absent."""
    esr = _flag_token("ESR", latest["esr"]) if "esr" in latest else None
    crp = _flag_token("CRP", latest["crp"]) if "crp" in latest else None
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
    LabCorp (`Hep B Real-Time PCR, Quant` / `HBV RT PCR, Quant
    (Graph)`) uses no flags and two items: the first, `HBV IU/mL`,
    carries the linear value (or the `HBV DNA not detected` text,
    which renders `HBV DNA neg`); the `log10 HBV IU/mL` item is
    ignored."""
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


def _eag_token(items):
    """`eAg neg` when the hepatitis B e-antigen (Quest's `HEPATITIS
    BE ANTIGEN` item, LabCorp's `Hep Be Ag`) is negative /
    non-reactive; `eAg+` when positive / reactive; a pending /
    not-performed value (LabCorp's `TNP`) produces nothing (rule
    23)."""
    it = next(
        (it for it in items if it["name"].strip().lower() in _EAG_ITEMS),
        None,
    )
    if it is None:
        return None
    value = it["value"].strip().lower()
    if value in _POSITIVE_VALUES:
        return "eAg+"
    if value in _NEGATIVE_VALUES:
        return "eAg neg"
    return None


def _hbcab_token(items):
    """`HBcAb neg` when the hepatitis B core antibody (Quest's
    `HEPATITIS B CORE AB TOTAL` item, LabCorp's `Hep B Core Ab,
    Tot`) is negative / non-reactive; `HBcAb+` when positive /
    reactive; a pending / not-performed value produces nothing
    (rule 24)."""
    it = next(
        (it for it in items if it["name"].strip().lower() in _HBCAB_ITEMS),
        None,
    )
    if it is None:
        return None
    value = it["value"].strip().lower()
    if value in _POSITIVE_VALUES:
        return "HBcAb+"
    if value in _NEGATIVE_VALUES:
        return "HBcAb neg"
    return None


def _hdv_token(items):
    """`HDV neg` when the hepatitis D antibody (Quest's `HEPATITIS D
    ANTIBODY,` item, LabCorp's `HDV Antibody, IgG/IgM`) is negative /
    non-reactive; `HDV+` when positive / reactive; a pending / empty
    value produces nothing (rule 24a)."""
    it = next(
        (it for it in items if it["name"].strip().lower() in _HDV_ITEMS),
        None,
    )
    if it is None:
        return None
    value = it["value"].strip().lower()
    if value in _POSITIVE_VALUES:
        return "HDV+"
    if value in _NEGATIVE_VALUES:
        return "HDV neg"
    return None


def _htlv_token(items):
    """`HTLV neg` when the HTLV I/II antibody screen (LabCorp's
    `HTLV-I/II Antibodies, Qual` item) is negative; `HTLV+` when
    positive; a pending / empty value produces nothing (rule 24b)."""
    it = next(
        (it for it in items if it["name"].strip().lower() in _HTLV_ITEMS),
        None,
    )
    if it is None:
        return None
    value = it["value"].strip().lower()
    if value in _POSITIVE_VALUES:
        return "HTLV+"
    if value in _NEGATIVE_VALUES:
        return "HTLV neg"
    return None


def _hbsabq_token(items):
    """`HBV Ab+` when the Hep B surface-Ab titer (LabCorp's
    `Hepatitis B Surf Ab Quant` item, range `Immunity>10`) is above
    the 10 mIU/mL immunity cutoff -- the level is the value's number,
    so a capped `>value` counts; non-immune / equivocal / number-less
    values produce nothing (rule 24c)."""
    it = next(
        (it for it in items if it["name"].strip().lower() in _HBSABQ_ITEMS),
        None,
    )
    if it is None:
        return None
    m = re.search(r"\d+(?:\.\d+)?", it["value"].strip())
    if m is None:
        return None
    level = float(m.group())
    return "HBV Ab+" if level > _HBSABQ_IMMUNE_ABOVE else None


def _phos_token(items):
    """`Phos nl` / `Phos {val}({bound})` for the phosphorus result
    (the `_flag_token` shape; rule 14)."""
    return _flag_token("Phos", items)


def _zinc_token(items):
    """`zinc nl` / `zinc {val}({bound})` for the serum/plasma zinc
    result (the `_flag_token` shape; rule 15)."""
    return _flag_token("zinc", items)


def _amylase_token(items):
    """`amylase nl` / `amylase {val}({bound})` for the amylase
    result (the `_flag_token` shape; rule 31)."""
    return _named_flag_token(items, _AMYLASE_ITEMS, "amylase")


def _lipase_token(items):
    """`lipase nl` / `lipase {val}({bound})` for the lipase result
    (the `_flag_token` shape; rule 32)."""
    return _flag_token("lipase", items)


def _afp_token(items):
    """`AFP nl` / `AFP {val}({bound})` for the alpha-fetoprotein
    result (the `_flag_token` shape; rule 37)."""
    return _flag_token("AFP", items)


def _cea_token(items):
    """`CEA nl` / `CEA {val}({bound})` for the CEA result (the
    `_flag_token` shape; LabCorp's range is the unparseable `See
    Note:`, so an abnormal result is usually plain `CEA {val}`;
    rule 38)."""
    return _flag_token("CEA", items)


def _ca125_token(items):
    """`CA 125 nl` / `CA 125 {val}({bound})` for the CA 125 result
    (the `_flag_token` shape; rule 39)."""
    return _flag_token("CA 125", items)


def _ca199_token(items):
    """`CA 19-9 nl` / `CA 19-9 {val}({bound})` for the CA 19-9
    result (the `_flag_token` shape, like CEA; rule 40)."""
    return _named_flag_token(items, _CA199_ITEMS, "CA 19-9")


def _ldh_token(items):
    """`LDH nl` / `LDH {val}({bound})` for the LDH result (the
    `_flag_token` shape, on the `LDH` / `LD` item; rule 41)."""
    return _named_flag_token(items, _LDH_ITEMS, "LDH")


def _hpylori_token(items):
    """`H pylori neg` when the H. pylori test is negative (Quest's
    `NOT DETECTED` breath-test value / LabCorp's `Negative`), `H
    pylori+` when any item is flagged abnormal (Quest's `DETECTED`,
    LabCorp's `Positive`); a pending / empty value (Quest's `TNP`,
    the collection-kit rows) produces nothing (rule 35)."""
    if _abnormal_items(items):
        return "H pylori+"
    for it in items:
        value = it["value"].strip().lower()
        if not value:
            continue
        if value in _NEGATIVE_VALUES:
            return "H pylori neg"
        return None
    return None


def _stool_token(items):
    """`stool occult neg` when nothing is flagged abnormal (an
    all-empty value set is the in-house FIT negative pattern); `stool
    occult+` when any item is flagged abnormal (a flagged empty FIT
    value counts too); any other nonempty value produces nothing
    (rule 36)."""
    if not items:
        return None
    if _abnormal_items(items):
        return "stool occult+"
    for it in items:
        value = it["value"].strip().lower()
        if not value:
            continue
        if value in _NEGATIVE_VALUES:
            return "stool occult neg"
        return None
    return "stool occult neg"


def _stool_cx_state(items, negative_note):
    """`neg` / `pos` for one in-house stool-culture order's result
    items, or `None` when the result is pending / unrecognized (rule
    36a).  The `CULTURE` item's `NOT ISOLATED` value is a negative
    culture, an `ISOLATED` value or a flagged item a positive one, an
    empty value a negative culture when the result note carries the
    order's `No ... isolated` text, and otherwise pending (an in-
    process result's note carries no marker)."""
    it = next(
        (it for it in items if it["name"].strip().lower() == "culture"),
        None,
    )
    if it is None:
        return None
    value = it["value"].strip()
    if value:
        if value.lower() == "not isolated":
            return "neg"
        if value.lower() == "isolated" or _is_abnormal(it["flag"]):
            return "pos"
        return None
    if _is_abnormal(it["flag"]):
        return "pos"
    if negative_note and negative_note in it["notes"].lower():
        return "neg"
    return None


def _stool_cx_tokens(latest):
    """The stool-culture tokens (rule 36a): `stool culture neg` when
    every present in-house stool culture (campylobacter, e. coli
    O157:H7, salmonella/shigella) is negative; one `{label}+` token
    per positive culture -- `Campylobactor+` / `E. coli O157:H7+` /
    `Salmonella/Shigella+`, in that order, the yellow notes' labels
    -- and the negative members are not reported.  Pending /
    unrecognized cultures produce nothing (a lone negative next to a
    pending one reports nothing either)."""
    states = [
        (label, _stool_cx_state(latest[key], note))
        for key, note, label in (
            ("stool_cx_campy", None, "Campylobactor"),
            ("stool_cx_ecoli", "no escherichia coli o157 isolated",
             "E. coli O157:H7"),
            ("stool_cx_salm", "no salmonella or shigella isolated",
             "Salmonella/Shigella"),
        )
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
    for row in labs:
        items = _parse_items(row.get("result"))
        if items is not None:
            rows.append((row, items))
    if not rows:
        return ""

    # The newest (first) row per category.
    latest = {}
    for row, items in rows:
        name = (row.get("name") or "").strip().lower()
        for category, names in _CATEGORY_NAMES.items():
            if name in names and category not in latest:
                latest[category] = items

    tokens = []

    def add(token):
        if token:
            tokens.append(token)

    # Fixed token order (see the module docstring).
    if "ua" in latest:
        add(_ua_token(latest["ua"]))
    if "ucx" in latest:
        add(_ucx_token(latest["ucx"]))
    if "tsh" in latest:
        add(_tsh_token(latest))
    for token in _thyroid_cluster_tokens(latest):
        add(token)
    if "fsh" in latest:
        add(_fsh_token(latest["fsh"]))
    if "estradiol" in latest:
        add(_estradiol_token(latest["estradiol"]))
    if "a1c" in latest:
        glu = _liver_glucose(latest["liver"]) if "liver" in latest else None
        add(_a1c_token(latest["a1c"], glu))
    if "glu" in latest:
        add(_glu_token(latest["glu"]))
    if "albcr" in latest:
        add(_albc_token(latest["albcr"]))
    if "lipid" in latest:
        add(_ldl_token(latest["lipid"]))
    if "lpa" in latest:
        add(_lpa_token(latest["lpa"]))
    if "apob" in latest:
        add(_apob_token(latest["apob"]))
    if "cbc" in latest:
        add(_cbc_token(latest["cbc"]))
        add(_cbc_mcv_token(latest["cbc"]))
        add(_cbc_wbc_token(latest["cbc"]))
        add(_cbc_hb_token(latest["cbc"]))
        add(_cbc_plt_token(latest["cbc"]))
        add(_cbc_hct_token(latest["cbc"]))
        add(_cbc_eos_token(latest["cbc"]))
    if "vitd" in latest:
        add(_vitd_token(latest["vitd"]))
    if "pth" in latest:
        add(_pth_token(latest["pth"]))
    if "mg" in latest:
        add(_mg_token(latest["mg"]))
    if "phos" in latest:
        add(_phos_token(latest["phos"]))
    if "zinc" in latest:
        add(_zinc_token(latest["zinc"]))
    if "uric" in latest:
        add(_uric_token(latest["uric"]))
    if "psa" in latest:
        add(_psa_token(latest["psa"]))
    if "inrpt" in latest:
        for token in _inrpt_tokens(latest["inrpt"]):
            add(token)
    if "ptt" in latest:
        add(_ptt_token(latest["ptt"]))
    if "bnp" in latest:
        add(_bnp_token(latest["bnp"]))
    add(_std_token(latest))
    for token in _hsv_tokens(latest):
        add(token)
    add(_gc_token(latest))
    add(_treponema_token(latest))
    if "hbv_dna" in latest:
        add(_hbv_dna_token(latest["hbv_dna"]))
    if "hcv_rna" in latest:
        add(_hcv_rna_token(latest["hcv_rna"]))
    if "eag" in latest:
        add(_eag_token(latest["eag"]))
    if "hbcab" in latest:
        add(_hbcab_token(latest["hbcab"]))
    if "hdv" in latest:
        add(_hdv_token(latest["hdv"]))
    if "htlv" in latest:
        add(_htlv_token(latest["htlv"]))
    if "hbsabq" in latest:
        add(_hbsabq_token(latest["hbsabq"]))
    if "hav" in latest:
        add(_hav_token(latest["hav"]))
    if "measles" in latest:
        add(_measles_token(latest["measles"]))
    if "mumps" in latest:
        add(_mumps_token(latest["mumps"]))
    if "rubella" in latest:
        add(_rubella_token(latest["rubella"]))
    if "varicella" in latest:
        add(_varicella_token(latest["varicella"]))
    if "iron" in latest:
        add(_iron_token(latest["iron"]))
    if "ferritin" in latest:
        add(_ferritin_token(latest["ferritin"]))
    if "b12" in latest:
        add(_b12_token(latest["b12"]))
    if "fa" in latest:
        add(_fa_token(latest["fa"]))
    if "liver" in latest:
        add(_astalt_token(latest["liver"]))
        add(_protein_token(latest["liver"]))
        add(_liver_bun_token(latest["liver"]))
        add(_cr_token(latest["liver"]))
        add(_liver_bilirubin_token(latest["liver"]))
        add(_liver_alp_token(latest["liver"]))
        add(_liver_albumin_token(latest["liver"]))
        for token in _liver_electrolyte_tokens(latest["liver"]):
            add(token)
    if "ggt" in latest:
        add(_ggt_token(latest["ggt"]))
    if "amylase" in latest:
        add(_amylase_token(latest["amylase"]))
    if "lipase" in latest:
        add(_lipase_token(latest["lipase"]))
    if "ana" in latest:
        add(_ana_token(latest["ana"]))
    for token in _esrcrp_tokens(latest):
        add(token)
    if "hpylori" in latest:
        add(_hpylori_token(latest["hpylori"]))
    if "stool" in latest:
        add(_stool_token(latest["stool"]))
    for token in _stool_cx_tokens(latest):
        add(token)
    if "afp" in latest:
        add(_afp_token(latest["afp"]))
    if "cea" in latest:
        add(_cea_token(latest["cea"]))
    if "ca125" in latest:
        add(_ca125_token(latest["ca125"]))
    if "ca199" in latest:
        add(_ca199_token(latest["ca199"]))
    if "ldh" in latest:
        add(_ldh_token(latest["ldh"]))
    if "qtb" in latest:
        add(_qtb_token(latest["qtb"]))

    if not tokens:
        return ""

    # Leading mm/yyyy from the newest row: result_date, else order date.
    first = rows[0][0]
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
