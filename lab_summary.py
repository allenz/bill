"""Build the one-line lab summary shown on the app.py /patient page.

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
    The lab test name (`lab.name`), e.g. `"UA, Routine"` /
    `"Urinalysis, Complete"` (LabCorp; the latter also carries the
    manual-microscopy block) or `"UA, urine routine"` (Quest),
    `"TSH reflex to T4F"`
    (LabCorp), `"TSH W/REFLEX TO FT4"` (Quest) or `"TSH+FREE T4"`
    (Quest, a layout that reports the T4 as well), `"TSH"` (the
    standalone order, both vendors) or `"Free T4"` (a standalone
    free-T4 draw), `"Culture Urine, Routine"` (LabCorp), or
    `"ALLERGY MOLD PANEL, COMPLETE"` / `"FOOD ALLERGY PANEL (REFL)"
    (the in-house allergy panels; see rule 44).  Matching is done
    after stripping and lower-casing, so `"ua, routine"` and
    `"UA, Routine"` are the same category.
`result` (str or None)
    The lab's JSON result text (`lab.result`): a JSON array of item
    dicts, each with at least `itemName` and `value` plus a
    `flag` (Quest sends `"N"`/`"A"`; LabCorp mostly leaves the
    flag empty on normal items and sends `"H"`/`"L"`/`"A"` on
    abnormal ones), a reference `range` (e.g. `232-1245`) that may
    be empty, and a `paramNotes` result note (read by the stool-
    culture rule, 36a, for the in-house orders' `No ... isolated`
    negative text, and by the stool-parasite / C. diff toxin rules,
    36b / 36c, for the `No ... seen` / `Not Detected` / `No
    toxigenic C. difficile detected` negative texts).  Imaging rows
    have the report instead: an array of dicts whose `notes` fields
    are the report text (`FINDINGS` / `IMPRESSION`).
`result_date` (str or None)
    ISO result date used for the leading `mm/yyyy`.
`date` (str or None)
    ISO order date; only used as a fallback for the leading `mm/yyyy`.

Any other key on the rows is ignored and missing keys are treated as
`None`.

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

1. **UA** (the LabCorp `UA, Routine` / `Urinalysis, Complete` orders
   -- the latter with a manual-microscopy block -- and Quest's `UA,
   urine routine` / in-house `URINALYSIS REFLEX` panels).  Normal:
   `UA nl`. Abnormal: `UA ` + the abnormal items in report order as
   short tokens joined with `, `: `pH {num}` / `pH<{num}` /
   `pH>{num}` for pH, `crystals+` for an abnormal crystals item, and
   `{name} {value}` in lower case (a `trace` value gains a `+`, eg
   `protein trace+`) for the rest.  The items and item/value pairs in
   `_UA_IGNORED_NAMES` / `_UA_IGNORED` (squamous epithelial cells,
   the `Microscopic Examination` section header, `Bacteria` = `Few`,
   `Ketones` = `Trace` or `2+`, `WBC Esterase` = `Trace`, `Occult
   Blood` = `Trace`) are not reported.  The microscopy count items
   (`WBC` / `RBC` / `Epithelial Cells (non renal)` / `Epithelial
   Cells (renal)`) are not reported when their value is an absent
   text (`None seen` / LabCorp's `NOSEE`, ...) or a count range
   starting at 0 (`0-5`: the tech could not confirm a presence;
   LabCorp flags its `Epithelial Cells (renal)` item A on the normal
   `0-10` value).
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
1b. **HCG** (the pregnancy test: Quest's `HCG, TOTAL, QN` serum
   quantitative and the in-house `HCG, QL, URINE` urine qualitative
   orders, one item named after the order each).  `HCG neg` when
   negative / non-reactive (the urine test's `NEGATIVE` value, or the
   serum test's a below-cutoff value -- its reference range
   (nonpregnant <5, postmenopausal <10) sits in the item's
   paramNotes, not its range field, so the lab's own flag decides:
   a flagged value is positive, an unflagged one below) and `HCG+`
   when positive / reactive; a pending / empty value produces
   nothing.
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
4. **Estradiol**. `Estradiol nl` or `Estradiol {val}({bound})`.
4a. **Testosterone**. Panel orders: all normal `testosterone T/F nl`,
   similarly if one is normal. Each abnormal item:
   `testosterone T {val}({bound})` or `testosterone F {val}({bound})`.
   Quest's standalone order: emit `testosterone {val}`.
4b. **Cortisol**. `cortisol nl` or `cortisol {val}`.
4c. **Prolactin**. `prolactin nl` or `prolactin {val}`.
4d. **LH**: `LH nl` or `LH {val}. The reference range is phase-dependent so no
   parseable bound.
4e. **Progesterone** (Quest's `PROGESTERONE` order).  `Progesterone
   nl` or `Progesterone {val}` (the value written raw -- the yellow
   notes write 17764's low value `Progesterone <0.5` and a normal
   `Progesterone nml`).  The reference range is phase-dependent
   (follicular / luteal) and sits in the item's paramNotes, not its
   range field, so a phase-appropriate value is not flagged and no
   bound is parseable (like LH, rule 4d).
4f. **AMH**.  `AMH nl` or `AMH {val}({bound})`.
5. **Glucose/A1c**. If we have both, always emit `Glu {glu}/A1c {val}`.
   If only A1c, always emit `A1c {val}`.
   If only glucose, emit `Glu {val}({bound})` if abnormal else omit.
6. **Alb/Cr**. Normal: `Alb/Cr<30`. Abnormal: `Alb/Cr {val}`.
7. **LDL / HDL**. If lipid panel triglycerides are high and we know
   HDL, emit `{HDL}/{LDL}/{TG}({bound})`. Else: if HDL is low emit
   `HDL {val}({bound})`, and always emit `LDL {val}`. We ignore other abnormal
   values like total cholesterol, non-HDL, CHOL/HDLC ratio, and high VLDL.
8. **LpA**. Normal: `LpA nl`. Abnormal: `LpA {val}({bound})`.
9. **ApoB**. Normal: `ApoB nl`. Abnormal: `ApoB {val}({bound})`.
9a. **CT CAC**. One token: `CAC={score}; {pctl}`. Additional
   findings: the `Aorta` section's sentence(s) naming an aortic ectasia
   / aneurysm / dilation e.g. `Ascending aortic ectasia 3.6 cm`.
   One `{vessel} {score}%` token per vessel at 90-100 stenosis.
   One `lung nodule(s)` token per `Other Findings` / `Aorta` / `Pericardium`
   sentence naming a pulmonary nodule, with its size and an `x{count}` if
   count > 1 eg `lung nodules x2 4 mm`.
9b. **Mammo**. BI-RADS 1-2: `Mammo nl`. Else report the `IMPRESSION` findings
   in full eg `Mammo: Probably benign right breast mass, which may reflect
   a fibroadenoma`. Skip lifetime-risk, `Key images`, patient discussion,
   addendum, outside-report, counseling block, the annual-screening scheduling
   line, and `No evidence ...`.
9c. **US**. Region label shortened from order name: `abd`, `breast`, `thyroid`,
   `renal`, `pelvic`, `carotid`, `AAA`, `neck`, `soft tissue`, `testicular`,
   else the first name word. `IMPRESSION` (or `ASSESSMENT/MANAGEMENT` in
   Plus breast reports'). `US {label} nl` or the finding sentences in full eg
   `US thyroid: Left mid thyroid nodule measuring 1.4 cm, moderately suspicious
   (TI-RADS 4); follow-up recommended at 1, 2, 3, 5 years`. A breast report
   with a `BI-RADS {n}` line is like the mammo: 1-2 -> `US
   breast nl`. Remove boilerplate.
9d. **BONE DENSITY**. All sites above -1.0: `Bone density nl`. Else the
   lowest T-score's site and value eg eg `Bone density femur -1.9`.
9e. **CT**. `chest` / `head` / `abd/pelvic` / `abd`, else the first part after
   CT. The report's `IMPRESSION` (or `CONCLUSION` /
   `ASSESSMENT`) section. `CT {label} nl` when the impression has no findings,
   else the finding sentences eg `CT chest: Multiple pulmonary nodules
   up to 6.3 mm. Recommend a repeat low-dose CT chest in 6 months`.
10. **CBC**. Normal: omit. Abnormal: eg `RBC {val}({bound})`.
10a. **MCV**. Normal: omit. Abnormal: `MCV {val}({bound})`.
10b. **WBC / Hb / Plt / Hct (same CBC rows)**. Normal: omit.
     Abnormal: one token per abnormal item, in that order,
     `WBC` / `Hb` / `Plt` / `Hematocrit` as `{label} {val}({bound})`.
10c. **Eos**.  Normal: omit. Abnormal: `Eos {val}({bound})`.
     Use the *absolute* eosinophil item only.
10d. **Plt est**. Normal (`ADEQUATE`): omit. Abnormal (`DECREASED` value):
     `plt est decreased` unless the newest CBC has already reported an
     abnormal platelet count.
11. **VitD**. Always emit `VitD {val}`.
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
17. **PSA**. Always emit `PSA {val}` for the total PSA. When the total is
    borderline (4-10 ng/mL) and free% is under 25, also emit `PSA%free {val}`.
18. **INR / PT**. One token per abnormal item, `INR` first: `INR {val}({bound})`
    / `PT {val}({bound})` (trailing zeros stripped; the `INR` item
    usually carries no reference range, so plain `INR {val}`).
    Normal: `INR/PT nl` when both items are present, `INR nl` /
    `PT nl` when only one is.
19. **PTT**. Normal: `PTT nl`. Abnormal: `PTT {val}({bound})`.
20. **BNP**. Normal: `BNP nl`. Abnormal: `BNP {val}({bound})`.
21. **HBV/HCV/HIV/RPR/G-C/Treponema**. all negative:
    `HBV/HCV/HIV/RPR/HSV/G-C/Treponema neg`. Only the hep
    trio: `HBV/HCV neg`. The HBV/HCV group (the hep B/C trio) is
    negative when all three rows are present and the surface-antigen
    and HCV results are normal -- a REACTIVE surface Ab means
    immunity, not active hepatitis B, so it does not drop the group.
    An abnormal surface-antigen / HCV result is its own
    `HBsAg+` / `HCV+` token right after the STD token. `HIV+`, `RPR+`. A
    negative surface-Ag screen of an incomplete trio
    (a missing HCV / surface-Ab row) reports its own `HBV neg` token right
    after the STD token, so a lone non-reactive screen is never silent.
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
24. **HBcAb**. `HBcAb neg` / `HBcAb+` like the eAg.
24a. **HDV** (hepatitis D antibody; occurs only with an HBV
    infection).  `HDV neg` when negative / non-reactive (Quest's item
    is spelled `HEPATITIS D ANTIBODY,` with a trailing comma, LabCorp
    reports `Non Reactive`), `HDV+` when positive / reactive; a
    pending / empty value produces nothing.
24b. **Hb electrophoresis / HTLV**. Eg `Hb electrophoresis/HTLV neg`,
    `HTLV neg`, `Hb electrophoresis+`, or `HTLV+` as appropriate.
24c. **HBV Ab**. Report `HBV Ab+` when reactive or
    the titer is immune (above 10 mIU/mL, the `Immunity>10` range).
    `HBV Ab neg` when non-reactive or non-immune.
25. **HAV**. Emit `HAV Ab+` when the total antibody is positive, else nothing.
25a. **HAV IgM**. Emit `HAV IgM+` or omit.
26. **Measles**. Emit `measles Ab+` if the IgG level > 16.49, else nothing.
    The flag is unreliable.
26a. **Mumps**. Emit `mumps Ab+` when the IgG level > 10.99, else nothing
    (the yellow notes write `need Mumps vacc`).
26b. **Rubella** (the `RUBELLA ANTIBODY (IGG)` index item of the MMR
    panel, LabCorp's `Rubella Antibodies, IgG` item on its `MMR`
    order, both on the in-house `RUBELLA IMMUNE STATUS` order and on
    LabCorp's standalone `Rubella Antibodies, IgG` order). Emitted only when the
    index is immune -- above 0.99 (Quest: `> or = 1.00 Consistent
    with immunity`, LabCorp's range `Immune >0.99`; the 0.90-0.99
    band is equivocal): `rubella Ab+`; non-immune / equivocal /
    number-less levels produce nothing (the yellow notes write a
    negative as `need Rubeola vacc`).
26c. **Varicella**. If positive / reactive: `varicella Ab+`. 
    Use the value because LabCorp does not set a flag:
    `Reactive` / `Positive` text is positive,
    `Non Reactive` / `Negative` negative; a numeric S/CO level >= 1.00 is
    positive; a numeric index level >= 165.00 is positive.
    Equivocal, negative and pending / empty values produce nothing
    (the yellow notes write a negative as `need varicella vacc`).
27. **Iron**. `iron nl` if every item of the panel is normal. Else one token
    per abnormal item, in report order, `{label} {val}({bound})` with the labels
    `iron`, `TIBC`, `iron%sat` and `ferritin`.
27a. **Ferritin (standalone)**. Normal: omit. Abnormal: `ferritin {val}({bound})`.
27b. **Iron (standalone)** (the serum-iron-without-TIBC orders: the
    in-house / Quest `Iron` order's `IRON, TOTAL` item and
    LabCorp's `Iron, Serum` order's item).  Normal: omit. Abnormal:
    `iron {val}({bound})`.
27c. **Copper (standalone)** (the in-house `COPPER` order -- its
    single `COPPER` item, the serum copper level in mcg/dL).
    `copper nl` or `copper {val}({bound})` (the yellow notes write
    a normal as `copper nl`).
28. **B12**. Abnormal: `B12 {val}({bound})`. normal: `B12 {val}`.
28a. **B1/B6** (thiamine / pyridoxine. Normal items grouped eg `B1/B6 nl`.
    Abnormal items each `{label} {val}({bound})`.
28b. **B2** (riboflavin; Quest's `VITAMIN B2 (RIBOFLAVIN), PLASMA`
    order, the `VITAMIN B2 (RIBOFLAVIN),` item).  `B2 nl` or
    `B2 {val}({bound})` (the yellow notes write a normal as `B2 nl`).
29. **FA**. `FA nl` or `FA {val}({bound})`.
30. **AST/ALT**. Emitted only when a value is high:
    `AST/ALT {ast}({bound})/{alt}({bound})`. When only one of the two items is
    present the high one is emitted alone, e.g. `ALT 54(46)`. When
    neither value is high nothing is produced. A high total protein
    is reported right after as its own `protein {val}({bound})`
    token. For other panel items, omit if normal else: `BUN`, `Cr` / `CrCl`
    (both abnormal -> one combined `Cr/CrCl {cr}/{crcl}({bound})`),
    `bilirubin` (total only), `AP`, `albumin`, `Ca`, `Na`, `Cl`,
    `CO2`, `K`. The panel's remaining items are ignored.
30a. **GGT** (standalone order). Normal: omit. Abnormal: `GGT {val}({bound})`.
30b. **CK** (creatine kinase, total; the in-house `CREATINE KINASE,
    TOTAL` order and LabCorp's `Creatine Kinase, Total,Serum`, one
    item named after the order each).  `CK nl` or `CK {val}({bound})`
    (the value's trailing zeros stripped via `%g`, the bound via
    `_bound_for`; unlike most of the other enzyme tokens a normal CK
    is reported -- the yellow notes write `CK nl`).
31. **amylase**. `amylase nl` or `amylase {val}({bound})`.
32. **lipase**. `lipase nl` or `lipase {val}({bound})`.
33. **ANA**. `ANA+` when any ANA item (`ANA PATTERN` /
    `ANA TITER` / `Antinuclear Antibodies, IFA` / `ANA Direct` /
    `ANA SCREEN, IFA`) is flagged abnormal (the item's
    `1:{titer}` value appended when one is present: `ANA+ 1:80`);
    `ANA nl` when no ANA item is flagged abnormal; any other
    nonempty ANA item value produces nothing.  LabCorp's
    ANA/Rheumatoid panel also feeds this category (via its
    `ANA SCREEN, IFA` item; its RF / CCP items are the separate
    categories of rules 34a / 34b).
34. **ESR / CRP**. `ESR/CRP nl` when both tests are present and
    normal; otherwise the abnormal member(s) as `ESR {val}({bound})`
    / `CRP {val}({bound})` (ESR first; the CRP value rendered as an
    integer, `14.8` -> `CRP 15(8)`), and a normal member reports
    `ESR nl` / `CRP nl` only when the other test is absent.
34a. **RF**. `RF nl` or `RF {val}({bound})`.
34b. **Anti-CCP**. `Anti-CCP nl` or `Anti-CCP {val}`.
34c. **C3 / C4**. One token per abnormal item
    `C3 {val}({bound})` / `C4 {val}({bound})`. `C3/C4 nl` when both are normal,
    `C3 nl` / `C4 nl` when only one is.
34d. **dsDNA**. `dsDNA+` if abnormal; `dsDNA neg` when its value is in the
    negative set, or its flag is normal. LabCorp sends '' on a
    negative, whose value is a small number such as 2; Quest sends
    flag N on a negative.
34e. **Cardiac CRP (hs-CRP)** (LabCorp's `CRP, Cardiac` order -- the
    `C-Reactive Protein, Cardiac` item, mg/L, 0.00-3.00 range; the
    note's legend stratifies the relative risk for a future
    cardiovascular event: low <1.00, average 1.00-3.00, high >3.00).
    `hsCRP nl` or `hsCRP {val}({bound})` -- a different test from
    the inflammatory CRP of rule 34, reported under its own label.
35. **H pylori**. `H pylori neg` when negative / not detected;
    `H pylori+` when any item is flagged abnormal; a pending / empty
    value produces nothing.
36. **stool occult**. `stool occult+` when any item is flagged abnormal, else
    `stool occult neg`.
36a. **Stool culture**. `stool culture neg` when every order is negative.
    One `{label}+` token per positive order:
    `Campylobactor+` / `E. coli O157:H7+` / `Salmonella/Shigella+` in that
    order . Negative members are not reported.
36b. **Stool parasites** (the ova-and-parasite orders -- Quest's
    `Stool Ova and Parasite` and LabCorp's `Stool Ova + Parasite
    Exam` -- and the `Stool Giardia Ag, EIA` / `Stool CRYPTOSPORIDIUM
    AG, EIA` antigen orders).  `stool O-P neg` when every present
    order is negative (the yellow notes' shorthand for a negative
    stool-parasite workup, labelled `O-P`); one `{label}+` token per
    positive order, `O-P+` / `Giardia+` / `Cryptosporidium+` in that
    order (the negative members are not reported).  A pending /
    unrecognized order produces nothing (a lone negative next to a
    pending one reports nothing either).
36c. **C. diff toxin** (the in-house `Stool C-diff Toxin` order).
    `C diff neg` when negative / not detected; `C diff+` when
    positive / detected; a pending / empty value produces nothing.
37. **AFP**. `AFP nl` or `AFP {val}({bound})`.
38. **CEA**. `CEA nl` or `CEA {val}`.
39. **CA 125**. `CA 125 nl` or `CA 125 {val}({bound})`.
40. **CA 19-9**. `CA 19-9 nl` or `CA 19-9 {val}({bound})`.
41. **LDH**. `LDH nl` or `LDH {val}({bound})`.
42. **QTB** (the QuantiFERON-TB Gold Plus test).  `QTB neg` when the
    interpretation item is negative, `QTB+` when it is positive (the
    yellow notes' shorthand for a positive result); an indeterminate
    value produces nothing.
43. **ABO / Rh** (the blood-type order: LabCorp's `ABO Grouping and
    Rho(D) Typing` order -- an `ABO Grouping` item carrying the ABO
    group letter (`A` / `B` / `AB` / `O`) plus a `Rh Factor` item
    (`Positive` / `Negative`) -- and Quest's `ABO GROUP AND RH TYPE`
    order -- an `ABO GROUP` item plus an `RH TYPE` item (`RH(D)
    POSITIVE` / `RH(D) NEGATIVE`)).  `ABO {group}{sign}` in the
    yellow notes' blood-type shorthand (eg `ABO A+`, `ABO O+`): a
    `+` for a Rho(D)-positive result, a `-` for a Rho(D)-negative
    one.  A pending / empty group or Rh value produces nothing.
44. **Allergy** (the allergen-specific IgE / IgG4 panels; the
    in-house `ALLERGY MOLD PANEL, COMPLETE`, `FOOD ALLERGY PANEL
    (REFL)` and `FOOD ALLERGY PROFILE WITH REFLEXES` panels, the
    `Allergy _ Cat IgE` order, the two dust-mite IgG4 orders,
    LabCorp's `Allergy Profile, Food` panel, and the two in-house
    respiratory panels (`ALLERGY EVALUATION 9, NORTHWEST` and
    `RESPIRATORY ALLERGY PROFILE REGION XVII`), which carry items of
    four families at once and so feed every respiratory group, like
    the MMR order feeds three).  The panel's items are grouped by
    their code tag's letter -- the in-house `({CODE})` tag and the
    LabCorp leading `{CODE}-` -- `M` mold, `D` dust mite, `E` animal
    dander (cat / dog), `T` / `W` / `G` tree / weed / grass pollen
    and `F` food (the mite IgG4 orders' code-less mite items join
    dust mite); the `CLASS` / `Class Description` items, the
    total-IgE / `Reflex` items and the unreportable cockroach item
    are not reported.  The negative groups join one token, their
    labels in the fixed group order `mold`, `dust mite`, `pollen`,
    `animal`, `food` joined with `/` plus a single trailing ` neg`
    (eg `allergy mold/dust mite/pollen neg`; the yellow notes write
    a negative panel as `all.ergy mold/dust mite/Pollen neg`,
    `animal/mold/pollen neg`, `food allergy neg`); each positive
    item (flagged, or an unflagged level at / above the positivity
    threshold -- 0.10 kU/L for the IgE items, which carry no
    reference range (the LabCorp items' range field carries their
    IgE class label instead) and whose not-performed `TNP`-valued
    items count as below it, the mite IgG4 items' range upper
    limit) reports
    its own `{group} {val}+({bound})` token right after that one, in
    group order then report order (the bound is the positivity
    threshold; the yellow notes write a positive mite as `dust mite
    0.23+(0.1)`).  A group whose newest row has no usable item /
    value produces nothing.

A row that matches no rule above produces no token.
In particular, if no orders exist then item layout is unknown:
DHEA, troponin, D-dimer, ANCA.

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

_UA_NAMES = frozenset({
    "ua, routine",  # LabCorp
    "urinalysis, complete",  # LabCorp
    "ua, urine routine",  # Quest
    "urinalysis reflex",  # in-house
})
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
# HCG (pregnancy test) order names per vendor / in-house (lower-cased);
# rule 1b.  The single item of each layout is named after the order:
# Quest's `HCG, TOTAL, QN` serum quantitative test reports the mIU/mL
# value (no reference range -- the nonpregnant <5 / postmenopausal
# <10 range sits in the item's paramNotes), and the in-house / Quest
# `HCG, QL, URINE` urine qualitative test reports the NEGATIVE /
# POSITIVE text.
_HCG_NAMES = frozenset({"hcg, total, qn", "hcg, ql, urine"})
# CBC order name per vendor (lower-cased); the LabCorp
# `CBC/Diff Ambiguous Default` order carries the LabCorp layout.
_CBC_NAMES = frozenset({
    "cbc (includes diff/plt)", "cbc with differential/platelet",
    "cbc/diff ambiguous default",
})
# In-house platelet-estimation order name (lower-cased); the single
# item is named after the order and reports the qualitative `ADEQUATE`
# / `DECREASED` value (rule 10d).
_PLT_EST_NAMES = frozenset({"platelet estimation"})
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
# reflex / ratio variants carry the same vendor item layouts; the
# in-house CARDIO IQ advanced lipid panel is Quest's CARDIO IQ panel
# (its item layout, including the `LDL-CHOLESTEROL` / `HDL
# CHOLESTEROL` / `TRIGLYCERIDES` items of rule 7, plus the `Lipid
# (a)`-family items of rules 8 / 9 and the items the summary does not
# name: total cholesterol, CHOL/HDLC RATIO, NON HDL CHOLESTEROL, LDL
# PARTICLE NUMBER, LDL PEAK SIZE / PATTERN, HDL LARGE, LDL SMALL /
# MEDIUM); the in-house `Lipid Panel+ApoB` order is LabCorp's lipid
# panel with the apolipoprotein-B add-on (LabCorp's item layout --
# `LDL-C (NIH Calc)` / `HDL-C` / `Triglycerides` -- plus the
# `Apolipoprotein B` item, rule 9).
_LIPID_NAMES = frozenset({
    "lipid panel", "lipid panel with ratios",
    "lipid panel with reflex to direct ldl",
    "lipid panel with ratios (refl)",
    "lipid panel with ldl/hdl ratio",
    "lipid _ cardio iq(r) advanced lipid panel",
    "lipid panel+apob",
})
# Calculated-LDL item names per vendor (lower-cased).  LabCorp's
# in-house `Lipid Panel+ApoB` order spells it `LDL-C (NIH Calc)`.  Other
# LDL-ish items (NON HDL CHOLESTEROL, LDL/HDL RATIO, VLDL Cholesterol
# Cal) are deliberately not the LDL item.
_LDL_ITEMS = frozenset(
    {"ldl chol calc (nih)", "ldl-cholesterol", "ldl-c (nih calc)"})
# HDL item names, lower-cased: both vendors' standard lipid orders
# collapse to `hdl cholesterol` after strip + lower, LabCorp's in-house
# `Lipid Panel+ApoB` order spells it `HDL-C`.
_HDL_ITEMS = frozenset({"hdl cholesterol", "hdl-c"})
_TG_ITEMS = frozenset({"triglycerides"})
_LPA_NAMES = frozenset({
    "lipoprotein (a)",
    "lipid _ cardio iq(r) advanced lipid panel",
})
# The Lipoprotein (a) item in both layouts (lower-cased): the
# standalone order's single item and the CARDIO IQ panel's
# mid-list item.
_LPA_ITEMS = frozenset({"lipoprotein (a)"})
# In-house (ECW) order names for the apolipoprotein B add-on; the
# result item is `Apolipoprotein B` in both spellings' layouts.  The
# in-house CARDIO IQ advanced lipid panel carries the same
# `Apolipoprotein B` item as a mid-list item too (rule 9), and so
# does the in-house `Lipid Panel+ApoB` order (LabCorp's lipid panel
# with the add-on).
_APOB_NAMES = frozenset(
    {"lipid _ apolipoprotein b", "lipid_ apolipoprotein b",
     "lipid _ cardio iq(r) advanced lipid panel",
     "lipid panel+apob"})
# The Apolipoprotein B item in both layouts (lower-cased): the
# add-on order's single item and the CARDIO IQ panel's mid-list
# item.
_APOB_ITEMS = frozenset({"apolipoprotein b"})
_CT_CAC_NAMES = frozenset({
    "ct cardiac scoring",
    "ct cardiac calcium score plus",
    "cardiac calcium score plus",
})
_CT_SCAN_NAME_RE = re.compile(r"^ct[\s\-]*(?:chest|head|abdomen)\b")
# Token order of the known CT region labels. Other labels follow.
_CT_LABEL_ORDER = ("chest", "head", "abd/pelvic", "abd")
_MAMMO_NAME_RE = re.compile(r"mammo|mamo")
_US_NAME_RE = re.compile(r"^us\b")
# Region labels per order name, checked in order.
_US_LABELS = (
    ("aaa", "AAA"),
    ("elastography", "abd w/ liver elastography"),
    ("breast", "breast"),
    ("thyroid", "thyroid"),
    ("renal", "renal"),
    ("pelvic", "pelvic"),
    ("carotid", "carotid"),
    ("neck", "neck"),
    ("soft tissue", "soft tissue"),
    ("testicular", "testicular"),
    ("abdomen", "abd"),
    ("abdominal", "abd"),
)
# Token order of the known region labels. Other tokens follow.
_US_LABEL_ORDER = (
    "abd w/ liver elastography", "abd", "breast", "thyroid", "renal",
    "pelvic", "carotid", "AAA", "neck", "testicular", "soft tissue",
)
# The in-house bone-density (DEXA) order names (lower-cased; rule
# 9d): the report's `FINDINGS` section is the exam's notes.
_BMD_NAME_RE = re.compile(r"bone density")
# In-house order name for serum magnesium.  `MAGNESIUM, RBC` (red-cell
# magnesium) is a different test and is deliberately not in this set;
# it has its own category (rule 13a).
_MG_NAMES = frozenset({"magnesium"})
# Red-cell magnesium order name (lower-cased; rule 13a): Quest's
# `MAGNESIUM, RBC` and LabCorp's `Magnesium, RBC` both match it after
# strip + lower.  The single item is named after the order in both
# layouts, the reference range on its range field (Quest's
# 4.0-6.4, LabCorp's 3.7-7.0 mg/dL).  A different test from the
# serum magnesium of rule 13 (range 1.6-2.3) -- the two are separate
# categories so a patient with both ordered is not reported with the
# wrong one.
_MG_RBC_NAMES = frozenset({"magnesium, rbc"})
# In-house / Quest order names; the single item is `FSH` in both
# layouts.
_FSH_NAMES = frozenset({"fsh, serum", "fsh"})
# In-house order name for serum estradiol; the single item is named
# after the order too (`ESTRADIOL`; the in-house order carries no
# reference range).
_ESTRADIOL_NAMES = frozenset({"estradiol"})
# Testosterone order names per vendor (lowercased); rule 4a.  The
# panel orders report the total and free testosterone items plus
# the items the summary does not name (SHBG, bioavailable / %
# bioavailable, albumin, % free); Quest's standalone total order
# is a single item.
_TESTO_NAMES = frozenset({
    "testosterone, free,bio$and total, lc/ms/ms",
    "testosterone,free and total",
    "testosterone  total/free",
    "testosterone, total, males (adult),ia (refl)",
})
# Total-testosterone item per layout (lowercased); Quest's
# standalone order's item is spelled `TESTOSTERONE, TOTAL,` (the
# trailing comma is part of the name).
_TESTO_TOTAL_ITEMS = frozenset({
    "testosterone, total,$lc/ms/ms",
    "testosterone, serum",
    "testosterone, serum (total)",
    "testosterone, total,",
})
# Free-testosterone item per layout (lowercased).  Every panel
# layout's result carries a free item, but the standalone total
# order's result does not, so a missing free item identifies the
# standalone layout (rule 4a).
_TESTO_FREE_ITEMS = frozenset({
    "testosterone, free",
    "free testosterone(direct)",
    "free testosterone, serum",
})
# A.M. cortisol (Quest's `CORTISOL, A.M.` order, lowercased); the
# single item is named after the order and the reference range
# (4.0-22.0 mcg/dL) sits in the item's paramNotes, not its range
# field (rule 4b).
_CORTISOL_NAMES = frozenset({"cortisol, a.m."})
# Prolactin (Quest's `PROLACTIN` order, lowercased); the single
# item is named after the order and the reference range (females,
# 3.0-30.0 ng/mL non-pregnant) sits in the item's paramNotes
# (rule 4c).
_PROLACTIN_NAMES = frozenset({"prolactin"})
# LH (luteinizing hormone) order names (lowercased): the in-house
# `LH hormone` order (the single `LH` item; its phase-dependent
# reference range sits in the item's paramNotes, not its range
# field) exists in the database; the Quest / LabCorp names follow
# the vendors' standard LH orders (no such layout is in the
# database yet), the FSH orders' pattern (rule 4d).
_LH_NAMES = frozenset(
    {"lh hormone", "lh, serum", "lh (luteinizing hormone)"})
_LH_ITEMS = frozenset({"lh", "lh (luteinizing hormone)"})
# Progesterone (Quest's `PROGESTERONE` order, lower-cased); rule 4e.
# The single item is named after the order; the reference range is
# phase-dependent (the female follicular / luteal phases) and sits
# in the item's paramNotes, not its range field, so a
# phase-appropriate value is not flagged -- like LH (rule 4d).
_PROGESTERONE_NAMES = frozenset({"progesterone"})
# Anti-Mullerian-hormone order names per vendor / in-house
# (lower-cased); rule 4f.  The in-house `Infertility _ AMH _
# Anti-Mullerian hormone` order (Quest's item layout) reports the
# `ANTI-MULLERIAN HORMONE (AMH), FEMALE` item, the age-dependent
# reference range on its range field; LabCorp's `AMH _ Anti-Mullerian
# hormone` order reports the `Anti-Mullerian Hormone (AMH)` item,
# whose age-dependent range sits in the item's paramNotes, not its
# range field (like the LH order's, rule 4d).
_AMH_NAMES = frozenset({
    "infertility _ amh _ anti-mullerian hormone",
    "amh _ anti-mullerian hormone",
})
# AMH item per layout (lower-cased).
_AMH_ITEMS = frozenset({
    "anti-mullerian hormone (amh), female",
    "anti-mullerian hormone (amh)",
})
_VITD_NAMES = frozenset(
    {"vitamin d,25-oh,total,ia", "vitamin d, 25-hydroxy"})
# Intact PTH per vendor (lower-cased); both report a single item.
_PTH_NAMES = frozenset({"pth, intact without$calcium", "pth, intact"})
# Ionized (free) calcium order names per vendor (lower-cased); rule
# 12a.  The single item is named after the order in both layouts
# (`Calcium, Ionized, Serum` / `CALCIUM, IONIZED`), the reference
# range on its range field (LabCorp's 4.5-5.6, Quest's 4.7-5.5
# mg/dL).  A different test from the liver panel's total-calcium item
# (rule 30) -- the yellow notes' label for it is `Free Calcium`.
_ICA_NAMES = frozenset({"calcium, ionized, serum", "calcium, ionized"})
_PSA_NAMES = frozenset({
    "psa, total", "psa",
    "psa total (reflex to free)", "psa total+% free",
})
_PSA_TOTAL_ITEM_NAMES = frozenset({
    "prostate specific ag, serum", "psa, total",
})
_PSA_PCT_FREE_NAMES = frozenset({"% free psa"})
# Coagulation order names. The`INR` order has a `PT` and an `INR` item.
# `INR /PT` has `INR` and `Prothrombin Time`. The combined prothrombin /
# partial-thromboplastin order has both plus the PTT item.
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
# item name has a literal `$` in the middle.
_PTT_ITEMS = frozenset({
    "partial thromboplastin time, activated",
    "partial thromboplastin$time, activated",
})
# BNP (B-type natriuretic peptide) per vendor (lower-cased); one
# item each, and Quest's item name has a literal `$`.
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
# in-house order has Quest's FIT, which leaves the value empty on
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
# Stool-parasite order names per vendor (lower-cased); rule 36b.
# Quest's `Stool Ova and Parasite` order has one item named after
# the order (`OVA AND PARASITES,$CONC AND PERM SMEAR`) whose result
# note has the smear result lines (`CONCENTRATION 1: ...`,
# `TRICHROME 1: ...`; its reference-range line also has the
# negative text); LabCorp's `Stool Ova + Parasite Exam` order has
# a header item (`Final report`) plus the `Result 1` result item,
# whose note is the result text itself; the giardia /
# cryptosporidium antigen orders are single-item orders whose note
# has the `Not Detected` result.
_STOOL_OVA_NAMES = frozenset(
    {"stool ova and parasite", "stool ova + parasite exam"})
_STOOL_GIARDIA_NAMES = frozenset({"stool giardia ag, eia"})
_STOOL_CRYPTO_NAMES = frozenset({"stool cryptosporidium ag, eia"})
# In-house C. diff toxin order name (lower-cased); rule 36c.  The
# single item (Quest's `CLOSTRIDIUM DIFFICILE$TOXIN/GDH W/REFL TO
# PCR`) leaves the value empty; the result note carries the GDH /
# Toxin A and B lines and the `No toxigenic C. difficile detected`
# negative comment.
_STOOL_CDIF_NAMES = frozenset({"stool c-diff toxin"})
# Serum phosphorus per vendor (lower-cased); one item each.
_PHOS_NAMES = frozenset({"phosphorus, serum", "phosphorus"})
# Zinc order names (lower-cased).  `ZINC, RBC` (red-cell zinc) is a
# different test and is not part of this category (rule 15); it has
# its own category (rule 15a).
_ZINC_NAMES = frozenset({"zinc, plasma or serum", "zinc"})
# Red-cell zinc order name (lower-cased; rule 15a).  The single item
# is named after the order, the reference range on its range field
# (Quest's 9.0-14.7).  A different test from the serum / plasma zinc
# of rule 15 (ranges 60-130 / 44-115) -- the two are separate
# categories so a patient with both ordered is not reported with the
# wrong one.
_ZINC_RBC_NAMES = frozenset({"zinc, rbc"})
# ANA order per vendor (lower-cased); the middle spacing on the Quest
# name is part of the real order name.  Quest reports `ANA PATTERN` /
# `ANA TITER` items (positive results often carry their titer in a
# note, so the values can be empty with an A/H flag); LabCorp's
# `Antinuclear Antibodies, IFA` is a single item, and its
# ANA/Rheumatoid panel (whose name ends `PANEL 1`) carries the
# `ANA SCREEN, IFA` item beside the RF / CCP items of rules 34a / b.
_ANA_NAMES = frozenset({
    "antinuclear antibodies   titer and pattern",
    "antinuclear antibodies, ifa",
    "antinuclear antibody",
    "ana screen",
    "ana screen, ifa, w/refl$titer and pattern",
    "ana scr, ifa, w/refl titer/pattern/rheumatoid arthritis panel 1",
})
# ANA item names per layout (lower-cased): Quest's `ANA PATTERN` /
# `ANA TITER` items, LabCorp's `Antinuclear Antibodies, IFA` item
# (the standalone order) and `ANA Direct` (its `ANA Screen` order),
# and `ANA SCREEN, IFA` (Quest's titer / pattern order and the
# LabCorp ANA/Rheumatoid panel, whose RF / CCP items are the
# separate categories of rules 34a / b and are not ANA items).
_ANA_ITEMS = frozenset({
    "ana pattern", "ana titer",
    "antinuclear antibodies, ifa",
    "ana direct",
    "ana screen, ifa",
})
# ESR / CRP order names (lower-cased).  CRP's `CRP, Cardiac` is the
# high-sensitivity cardiac CRP -- a different test with its own 0-3
# range -- and is deliberately not in this set (the separate category
# of rule 34e).
_ESR_NAMES = frozenset({
    "esr",
    "sed rate",
    "erythrocyte sedimentation rate",
})
_CRP_NAMES = frozenset({"crp", "crp, quant"})
# Cardiac (high-sensitivity) CRP order name (lower-cased); rule
# 34e.  The order's single `C-Reactive Protein, Cardiac` item (mg/L,
# 0.00-3.00 range) stratifies the relative risk for a future
# cardiovascular event in its note's legend: low <1.00, average
# 1.00-3.00, high >3.00.
_CRP_CARDIAC_NAMES = frozenset({"crp, cardiac"})
_CRP_CARDIAC_ITEMS = frozenset({"c-reactive protein, cardiac"})
# Rheumatoid factor order names (lower-cased).  Quest's
# `RHEUMATOID FACTOR` order carries a single item named after the
# order; LabCorp's ANA/Rheumatoid panel (whose name ends `PANEL 1`)
# carries the RF item of the same name plus the CCP item of rule
# 34b and the ANA item of rule 33.
_RF_NAMES = frozenset({
    "rheumatoid factor",
    "ana scr, ifa, w/refl titer/pattern/rheumatoid arthritis panel 1",
})
# The rheumatoid-factor item in both layouts (lower-cased).
_RF_ITEMS = frozenset({"rheumatoid factor"})
# Anti-CCP (cyclic citrullinated peptide antibody) order names
# (lower-cased): Quest's `Anti-CCP Abs` order (a single item) and
# LabCorp's ANA/Rheumatoid panel.
_CCP_NAMES = frozenset({
    "anti-ccp abs",
    "ana scr, ifa, w/refl titer/pattern/rheumatoid arthritis panel 1",
})
# The CCP item in both layouts (lower-cased; the name carries a
# literal `$`).
_CCP_ITEMS = frozenset({"cyclic citrullinated$peptide (ccp) ab (igg)"})
# Complement C3 + C4 (LabCorp's `COMPLEMENT COMP C3 + C4` order,
# lower-cased): both components are items on the one order (rule
# 34c).
_C3C4_NAMES = frozenset({"complement comp c3 + c4"})
_C3_ITEMS = frozenset({"complement component c3c"})
_C4_ITEMS = frozenset({"complement component c4c"})
# Anti ds-DNA (LabCorp's `Anti Ds-DNA` order, lower-cased); the
# single item's value is a small number (2, 1) on a negative result
# -- LabCorp sends '' on the flag for those, Quest's layout sends
# flag N (rule 34d).
_DSDNA_NAMES = frozenset({"anti ds-dna"})
_DSDNA_ITEMS = frozenset({"dna (ds) antibody"})
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
# Creatine-kinase (total) order names per vendor (lower-cased); rule
# 30b.  Both layouts report the single item named after the order
# (the in-house `CREATINE KINASE, TOTAL` on Quest's layout, LabCorp's
# `Creatine Kinase,Total,Serum`), the reference range on the item's
# range field.
_CK_NAMES = frozenset(
    {"creatine kinase, total", "creatine kinase, total,serum"})
# Standalone copper order (in-house, rule 27c); the single `COPPER`
# item is the serum copper level (mcg/dL), its reference range on
# the item's range field (eg `70-175`).
_COPPER_NAMES = frozenset({"copper"})
_URIC_NAMES = frozenset({"uric acid, serum", "uric acid"})
# HAV total antibody per vendor (lower-cased); the single item's value
# is REACTIVE / NON-REACTIVE (Quest) or Positive / Negative (LabCorp).
# `HAV IgM` / `Hep A Ab, IgM` (acute infection) are different tests
# with their own category (rule 25a, `_HAV_IGM_NAMES`), deliberately
# not in this set.
_HAV_NAMES = frozenset({"hep a total ab", "hep a ab, total"})
# HAV IgM (the acute-hepatitis-A screen, rule 25a) per vendor
# (lower-cased): Quest's `HAV IgM` order carries the `HEPATITIS A IGM`
# item (REACTIVE / NON-REACTIVE, flag N / A) and LabCorp's `Hep A Ab,
# IgM` order an item named after the order (Positive / Negative).
_HAV_IGM_NAMES = frozenset({"hav igm", "hep a ab, igm"})
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
# ABO-grouping / Rho(D)-typing order names per vendor (lower-cased);
# rule 43.  LabCorp's `ABO Grouping and Rho(D) Typing` order reports
# the `ABO Grouping` item (the ABO group letter: `A` / `B` / `AB`
# / `O`) and the `Rh Factor` item (`Positive` / `Negative`); Quest's
# `ABO GROUP AND RH TYPE` order reports the `ABO GROUP` and
# `RH TYPE` items (`RH(D) POSITIVE` / `RH(D) NEGATIVE`).
_ABO_NAMES = frozenset(
    {"abo grouping and rho(d) typing", "abo group and rh type"})
# ABO-group item per layout (lower-cased).
_ABO_ITEMS = frozenset({"abo grouping", "abo group"})
# Rho(D) item per layout (lower-cased).
_RH_ITEMS = frozenset({"rh factor", "rh type"})
# Allergen-specific IgE / IgG4 (allergy) order names (lower-cased);
# rule 44.  The in-house orders report their allergens as `... IGE`
# items named `{ALLERGEN} ({CODE}) IGE`, and LabCorp's `Allergy
# Profile, Food` panel reports `{CODE}-IgE {ALLERGEN}` items (eg
# `F014-IgE Soybean`), the code's letter naming the allergen family
# (`M` mold, `D` dust mite, `E` animal dander, `T` / `W` / `G` tree
# / weed / grass pollen, `F` food) beside the `CLASS` / `Class
# Description` items the summary does not report; the LabCorp items'
# range field carries their IgE class label (`Class 0/I`), not a
# numeric range, and the items the lab did not perform carry `TNP`
# values; the two dust-mite IgG4 orders report the mite item
# instead, code-less, its reference range (`<0.50`) on its range
# field.  The two in-house respiratory panels carry items of four
# families (tree / mold / cat / dust mite / dog / weed / grass), so
# they match every respiratory group's set -- the way the MMR order
# matches the measles / mumps / rubella sets -- and one row feeds
# several groups.
# The multi-family in-house respiratory panels (lower-cased); rule
# 44.
_ALLERGY_RESPIRATORY_PANEL_NAMES = frozenset({
    "allergy evaluation 9, northwest",
    "respiratory allergy profile region xvii",
})
# Mold group (rule 44): the standalone mold panel and the two
# multi-family respiratory panels.
_ALLERGY_MOLD_NAMES = frozenset(
    {"allergy mold panel, complete"} | _ALLERGY_RESPIRATORY_PANEL_NAMES)
# Dust-mite group (rule 44): the two mite IgG4 orders (the
# pteronyssinus spelling carries a double space) and the two
# multi-family respiratory panels.
_ALLERGY_MITE_NAMES = frozenset({
    "allergy _ d farinae mite igg4*",
    "allergy  _ d pteronyssinus mite igg4*",
} | _ALLERGY_RESPIRATORY_PANEL_NAMES)
# Animal-dander group (rule 44): the standalone cat-IgE order and
# the two multi-family respiratory panels (their cat / dog dander
# items).
_ALLERGY_ANIMAL_NAMES = frozenset(
    {"allergy _ cat ige"} | _ALLERGY_RESPIRATORY_PANEL_NAMES)
# Pollen group (rule 44): only the two multi-family respiratory
# panels carry tree / weed / grass items; no standalone pollen order
# exists in the database.
_ALLERGY_POLLEN_NAMES = _ALLERGY_RESPIRATORY_PANEL_NAMES
# Food group (rule 44): the in-house food panels' `(F#)` items and
# LabCorp's food panel's `F###-IgE` items.
_ALLERGY_FOOD_NAMES = frozenset({
    "food allergy panel (refl)",
    "food allergy profile with reflexes",
    "allergy profile, food",
})
# Allergen-family letter of an item's code tag (lower-cased) ->
# sticky group (rule 44): the in-house items' `({CODE})` tag (eg
# `(M6)`) or the LabCorp items' leading `{CODE}-` (eg `F014-`).
_ALLERGY_CODE_GROUPS = {
    "m": "mold",
    "d": "dust mite",
    "e": "animal",
    "t": "pollen",
    "w": "pollen",
    "g": "pollen",
    "f": "food",
}
# LabCorp's `{CODE}-IgE` item prefix (lower-cased, rule 44).
_ALLERGY_LEADING_CODE = re.compile(r"^([a-z])\d+-ige\b")
# The two dust-mite IgG4 orders' code-less mite items (lower-cased).
_ALLERGY_MITE_CODELESS = frozenset(
    {"d farinae mite", "d pteronyssinus mite"})
# The specific-IgE positivity threshold (kU/L): the IgE items carry
# no reference range (their `<0.10`-style values are below it), so
# an unflagged number decides against this cutoff, and a positive
# value is written with it as its bound (21309's yellow note:
# `dust mite 0.23+(0.1)`).
_ALLERGY_IGE_POSITIVE_AT = 0.10
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
# B12 order names (lower-cased); rule 28 -- the standalone orders
# (both vendors spell it `Vitamin B12` / `VITAMIN B12`) and the
# B12/folate panels (rule 29's names) alike.
_B12_NAMES = frozenset({
    "vitamin b12",
    "vitamin b12/folate,$serum panel",
    "vitamin b12 and folate",
})
# B12 item on every layout (lower-cased); both vendors name the panel
# item after the standalone order (rule 28).
_B12_ITEMS = frozenset({"vitamin b12"})
# Vitamin B6 (pyridoxine) order name per vendor (lower-cased); rule
# 28a.  Quest's order reports a `VITAMIN B6, PLASMA` item
# (ng/mL, range 5.1-54.8), LabCorp's a `Vitamin B6` item (ug/L,
# range 3.4-65.2 -- the note's deficiency / marginal bands ride
# alongside it); the flag and range field decide on both layouts.
_B6_NAMES = frozenset({"vitamin b6, plasma"})
# Thiamine (vitamin B1) order names (lower-cased); rule 28a.  The
# `Vitamin B1 (Thiamine), Blood` order reports the `Vit. B1, Whole
# Blood` item (nmol/L, whole blood) and Quest's `VITAMIN B1
# (THIAMINE), SERUM/PLASMA, LC/MS/MS` order the `VITAMIN B1
# (THIAMINE),` item (nmol/L, the trailing comma is part of the name)
# -- both carry their reference range on the item's range field.
_B1_NAMES = frozenset({
    "vitamin b1 (thiamine), blood",
    "vitamin b1 (thiamine), serum/plasma, lc/ms/ms",
})
# B1 item per layout (lower-cased).
_B1_ITEMS = frozenset({"vit. b1, whole blood", "vitamin b1 (thiamine),"})
# B6 item per layout (lower-cased): Quest's order's item is named
# after the order, LabCorp's is spelled `Vitamin B6`.  An abnormal
# B6's value and bound render via `_b6_value` (integer at 10 and up,
# two significant figures below, rule 28a).
_B6_ITEMS = frozenset({"vitamin b6, plasma", "vitamin b6"})
# Riboflavin (vitamin B2) order name (lower-cased); rule 28b.  Quest's
# order reports the `VITAMIN B2 (RIBOFLAVIN),` item (nmol/L, plasma;
# the trailing comma is part of the name), the range on its range
# field.
_B2_NAMES = frozenset({"vitamin b2 (riboflavin), plasma"})
_B2_ITEMS = frozenset({"vitamin b2 (riboflavin),"})
# B12/folate panel per vendor (lower-cased); the panel's folate item
# is the `FA` category (rule 29) and its B12 item joins the `B12`
# category (rule 28).
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
# Creatinine item per vendor (lower-cased): Quest's `CREATININE` and
# LabCorp's `Creatinine, Serum` (the in-house CMP / BMP orders carry
# either layout).
_CR_ITEMS = frozenset({"creatinine", "creatinine, serum"})
# CrCl is the CMP's eGFR item: LabCorp's `EGFR` and Quest's `eGFR`,
# or one of Quest's race-paired layouts (`eGFR AFRICAN AMERICAN` +
# `eGFR NON-AFR. AMERICAN` / `eGFR If Africn Am` + `eGFR If
# NonAfricn Am`), which report two items and flag abnormal only the
# race-appropriate value (lower-cased; `_cr_token` prefers a flagged
# item over the first-listed one).
_EGFR_ITEMS = frozenset({
    "egfr",
    "egfr african american", "egfr non-afr. american",
    "egfr if africn am", "egfr if nonafricn am",
})
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
# Carbon-dioxide (bicarbonate) item per vendor (lower-cased): Quest
# spells it `CARBON DIOXIDE`, LabCorp's in-house-CMP / BMP items
# `Carbon Dioxide, Total`.  Reported by its own token when abnormal
# (rule 30).
_CO2_ITEMS = frozenset({"carbon dioxide", "carbon dioxide, total"})
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
# Standalone serum-iron order names per vendor (lower-cased); rule
# 27b.  The in-house / Quest `Iron` order carries the `IRON, TOTAL`
# item (range on its range field), LabCorp's `Iron, Serum` order the
# `Iron, Serum` item.  The iron-panel orders are the separate
# category of rule 27.
_IRON_STANDALONE_NAMES = frozenset({"iron", "iron, serum"})
_IRON_STANDALONE_ITEMS = frozenset({"iron, total", "iron, serum"})
_ALBCR_NAMES = frozenset(
    {"microalb/creat ratio, randm ur", "microalbumin, random urine (w/creatinine)"})
# HCV antibody screen per vendor (lower-cased); rule 21's HBV/HCV
# group.  LabCorp's `Hep C Ab RFX to Quant PCR` order carries an
# `Interpretation:` note item plus the `HCV Ab` result item; Quest's
# `Hep C Ab reflex to RNA, QN, PCR` order the same and its
# `HEPATITIS C AB W/RFL RNA, PCR W/RFL GENOTYPE,LIPA` order a single
# `HEPATITIS C ANTIBODY` item (the reflex to RNA / genotype never
# fires on a non-reactive screen).
_HCV_NAMES = frozenset(
    {"hep c ab rfx to quant pcr", "hep c ab reflex to rna, qn, pcr",
     "hepatitis c ab w/rfl rna, pcr w/rfl genotype,lipa"})
_HBSAG_NAMES = frozenset({"hep b surface ag"})
_HBSAB_NAMES = frozenset({"hep b surface ab"})
_HBSAB_ITEMS = frozenset({
    "hepatitis b surface$antibody ql", "hep b surface ab, qual"})
_HBSABQ_NAMES = frozenset({"hep b surf ab quant"})
_HBSABQ_ITEMS = frozenset({"hepatitis b surf ab quant"})
# Surface-Ab titer level (mIU/mL) above which the range text
# (`Immunity>10`) calls the patient immune.
_HBSABQ_IMMUNE_ABOVE = 10.0
# HIV screen order names per vendor (lower-cased); the in-house
# order uses the same names.  LabCorp's `HIV-1/HIV-2 Qualitative
# RNA` confirmatory test (the reflex on a reactive screen, its
# `HIV-1 RNA` / `HIV-2 RNA` items) feeds the category too: negative
# on a `Non Reactive` value on every RNA item (20779's note writes
# its screen, whose only HIV row is this order, as `HIV ... neg`).
_HIV_NAMES = frozenset({
    "hiv 1/2 ag/ab, 4th generation", "hiv",
    "hiv-1/hiv-2 qualitative rna",
})
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
# GENOTYPE,LIPA` is an HCV Ab screen with reflex to RNA (in
# `_HCV_NAMES`), not an RNA order, and is deliberately not in this
# set.
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
# In-house Hb electrophoresis order name (lower-cased); the single
# item is `Hemoglobin (Hgb) Solubility` (the sickle-cell solubility
# screen, value Negative / Positive).  Rule 24b's cluster with the
# HTLV screen (the two are ordered together).  No LabCorp / Quest
# layout exists in the database to learn from.
_HB_ELEC_NAMES = frozenset({"hb electrophoresis"})
_HB_ELEC_ITEMS = frozenset({"hemoglobin (hgb) solubility"})

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
# cells are a sample-contamination artifact, not a finding, and
# `Microscopic Examination` is the LabCorp layouts' microscopy
# section header (`See below:`), not a result item.
_UA_IGNORED_NAMES = frozenset(
    {"squamous epithelial cells", "microscopic examination"})
# Values that mean nothing seen on the UA's microscopy items
# (lower-cased): the item ranges are `NONE OR FEW` / `NONE SEEN`, and
# LabCorp compresses the negative to `NOSEE`.  Any other value on an
# abnormal microscopy item means the finding is present.
_UA_MICRO_ABSENT = frozenset(
    {"", "none", "none seen", "nosee", "absent", "negative", "few"})
# The manual-microscopy count items of the LabCorp UA layouts
# (lower-cased).  They report either an absent text or a count range
# (`0-5`, `6-10`, `>30`); a range starting at 0 means the tech could
# not confirm a presence, so it is not a finding even when LabCorp
# flags it A (its `Epithelial Cells (renal)` item is flagged A on the
# normal `0-10` value).  The other microscopy items (`Casts`, `Mucus
# Threads`, `Bacteria`, `Yeast`, the crystals) are text items and go
# through the crystals / generic branches.
_UA_MICRO_COUNT_ITEMS = frozenset({
    "wbc", "rbc",
    "epithelial cells (non renal)", "epithelial cells (renal)",
})

# Category key -> row names.  The three hep B/C categories are
# separate so the HBV/HCV group of the STD token can require all
# three to be present and the surface-Ag / HCV results to be normal
# (the surface-Ab row's result is not consulted).
_CATEGORY_NAMES = {
    "ua": _UA_NAMES,
    "ucx": _UCX_NAMES,
    "hcg": _HCG_NAMES,
    "cbc": _CBC_NAMES,
    "plt_est": _PLT_EST_NAMES,
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
    "ica": _ICA_NAMES,
    "mg": _MG_NAMES,
    "mg_rbc": _MG_RBC_NAMES,
    "phos": _PHOS_NAMES,
    "zinc": _ZINC_NAMES,
    "zinc_rbc": _ZINC_RBC_NAMES,
    "fsh": _FSH_NAMES,
    "estradiol": _ESTRADIOL_NAMES,
    "testo": _TESTO_NAMES,
    "cortisol": _CORTISOL_NAMES,
    "prolactin": _PROLACTIN_NAMES,
    "lh": _LH_NAMES,
    "progesterone": _PROGESTERONE_NAMES,
    "amh": _AMH_NAMES,
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
    "stool_ova": _STOOL_OVA_NAMES,
    "stool_giardia": _STOOL_GIARDIA_NAMES,
    "stool_crypto": _STOOL_CRYPTO_NAMES,
    "stool_cdiff": _STOOL_CDIF_NAMES,
    "albcr": _ALBCR_NAMES,
    "hav": _HAV_NAMES,
    "hav_igm": _HAV_IGM_NAMES,
    "measles": _MEASLES_NAMES,
    "mumps": _MUMPS_NAMES,
    "rubella": _RUBELLA_NAMES,
    "varicella": _VARICELLA_NAMES,
    "iron": _IRON_NAMES,
    "ferritin": _FERRITIN_STANDALONE_NAMES,
    "iron_standalone": _IRON_STANDALONE_NAMES,
    "b12": _B12_NAMES,
    "b1": _B1_NAMES,
    "b6": _B6_NAMES,
    "b2": _B2_NAMES,
    "fa": _FA_NAMES,
    "liver": _LIVER_NAMES,
    "ggt": _GGT_NAMES,
    "ck": _CK_NAMES,
    "copper": _COPPER_NAMES,
    "amylase": _AMYLASE_NAMES,
    "lipase": _LIPASE_NAMES,
    "ana": _ANA_NAMES,
    "esr": _ESR_NAMES,
    "crp": _CRP_NAMES,
    "rf": _RF_NAMES,
    "ccp": _CCP_NAMES,
    "c3c4": _C3C4_NAMES,
    "dsdna": _DSDNA_NAMES,
    "crp_cardiac": _CRP_CARDIAC_NAMES,
    "afp": _AFP_NAMES,
    "cea": _CEA_NAMES,
    "ca125": _CA125_NAMES,
    "ca199": _CA199_NAMES,
    "ldh": _LDH_NAMES,
    "qtb": _QTB_NAMES,
    "abo": _ABO_NAMES,
    "allergy_mold": _ALLERGY_MOLD_NAMES,
    "allergy_mite": _ALLERGY_MITE_NAMES,
    "allergy_animal": _ALLERGY_ANIMAL_NAMES,
    "allergy_pollen": _ALLERGY_POLLEN_NAMES,
    "allergy_food": _ALLERGY_FOOD_NAMES,
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
    "hb_elec": _HB_ELEC_NAMES,
    "htlv": _HTLV_NAMES,
}


def _parse_items(result):
    """Parse a row's `result` JSON into a list of item dicts.

    Returns `None` when the row has no usable result.
    Items are normalised to `{"name": str, "value": str, "flag": str | None,
    "range": str, "units": str, "notes": str}` with "" for missing values.
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


def _micro_count_absent(value):
    """True when a microscopy count item's value is not a finding: an
    absent text (`None seen` / `NOSEE`, ...) or a count range starting
    at 0 (`0-5` -- the tech could not confirm a presence)."""
    if value.lower() in _UA_MICRO_ABSENT:
        return True
    m = re.match(r"\s*(\d+(?:\.\d+)?)\s*-", value)
    return bool(m and not float(m.group(1)))


def _ua_token(items):
    """Token for a UA result: `UA nl`, or `UA ` + the abnormal items
    in report order as short tokens (see the module docstring):
    `pH<5`-style for pH, `crystals+` for an abnormal crystals item, and
    `{name} {value}` in lower case (a `trace` value gains a `+`) for
    the rest.  The ignored items and the microscopy count items'
    absent / `0-x` values are not reported."""
    parts = []
    for it in _abnormal_items(items):
        name = it["name"].strip().lower()
        value = it["value"].strip()
        if name in _UA_IGNORED_NAMES or (name, value.lower()) in _UA_IGNORED:
            continue
        if name in _UA_MICRO_COUNT_ITEMS and _micro_count_absent(value):
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
    return None


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
    `MCV` in both vendors' layouts) is abnormal: the value and the
    bound (the reference-range limit the value violates -- upper
    limit for `H`, lower limit for `L`) each rendered as an integer
    via `_int_value` (`63.7` in `81.4-101.7` -> `MCV 64(81)`, like
    the yellow notes; an unparseable value is written out raw);
    without a parsable range the token is plain `MCV {val}`.  A
    normal MCV produces nothing.  Emitted for a violated limit in
    either direction, like the RBC.
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
    shown = _int_value(value)
    bound = _bound_for(str(it["flag"] or "").strip().upper(), it["range"])
    if not bound:
        return f"MCV {shown}"
    return f"MCV {shown}({_int_value(bound)})"


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


def _plt_est_token(items, cbc_plt_token):
    """`plt est {value}` (lower-cased, eg `plt est decreased`) for an
    abnormal platelet estimation (rule 10d; the in-house order's
    single item reports `ADEQUATE` / `DECREASED`): a `DECREASED`
    value, flagged or not, or a flagged value, yields the token; a
    normal / pending / empty value yields nothing.  `cbc_plt_token`
    is the newest CBC's rule 10b `Plt` token: when it is not `None`
    the measured count already reports the abnormality and the
    estimate is suppressed."""
    it = items[0]
    value = it["value"].strip()
    if not value:
        return None
    if value.lower() != "decreased" and not _is_abnormal(it["flag"]):
        return None
    if cbc_plt_token is not None:
        return None
    return f"plt est {value.lower()}"


def _liver_electrolyte_tokens(items):
    """The liver panel's electrolyte tokens (rule 30): one token per
    abnormal item, in the order Ca / Na / Cl / CO2 / K, `{label}
    {val} ({bound})` (the value's trailing zeros stripped via `%g`,
    the bound via `_bound_for`; a plain `{label} {val}` when
    unparseable) -- e.g. `Ca 10.3(10.2), Na 134(136), Cl 109(107),
    K 6(5.1)` -- and nothing for the normal items, like BUN / Cr.
    CO2 is the panel's carbon-dioxide (bicarbonate) item."""
    tokens = []
    for names, label in ((_CA_ITEMS, "Ca"), (_NA_ITEMS, "Na"),
                         (_CL_ITEMS, "Cl"), (_CO2_ITEMS, "CO2"),
                         (_K_ITEMS, "K")):
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
    ({bound})`; when neither is abnormal: nothing.  Quest's
    race-paired eGFR layouts report two eGFR items and flag abnormal
    only the race-appropriate one, so that flagged item is the one
    consulted (the first-listed item when none is flagged).  An item
    flagged abnormal with an empty value counts as normal."""
    cr = next(
        (it for it in items if it["name"].strip().lower() in _CR_ITEMS),
        None,
    )
    # Quest's race-paired eGFR layouts report two items and flag
    # abnormal only the race-appropriate value, so prefer a flagged
    # item over the first-listed one (the unflagged twin).
    egfrs = [it for it in items
             if it["name"].strip().lower() in _EGFR_ITEMS]
    egfr = next(
        (it for it in egfrs
         if _is_abnormal(it["flag"]) and it["value"].strip()),
        egfrs[0] if egfrs else None,
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


def _testo_tokens(items):
    """The testosterone tokens (rule 4a).  The panel layouts (Quest's
    LC/MS/MS panel, LabCorp's two panels) report the total (`T`)
    and free (`F`) items: the normal members join one token, their
    labels joined with `/` plus a single trailing ` nl` (`testos-
    terone T/F nl`, `testosterone F nl`); each abnormal member
    reports its own `testosterone T {val}({bound})` /
    `testosterone F {val}({bound})` token right after it, in member
    order (value raw, the bound via `_bound_for`; LabCorp's
    reference ranges sit in the items' paramNotes, so its abnormal
    members are usually plain).  A member whose newest row has no
    usable item / value produces nothing.  A result with no
    free-testosterone item is the standalone `TESTOSTERONE, TOTAL,
    MALES (ADULT),IA (REFL)` order: it emits `testosterone {val}`
    (the value's trailing zeros stripped, raw value when it is not
    a number) for normal and abnormal results alike."""
    free = next(
        (it for it in items if it["name"].strip().lower() in _TESTO_FREE_ITEMS),
        None,
    )
    if free is None:
        # the standalone total order: always emit the value
        total = next(
            (it for it in items
             if it["name"].strip().lower() in _TESTO_TOTAL_ITEMS),
            None,
        )
        if total is None:
            return []
        value = total["value"].strip()
        if not value:
            return []
        try:
            return [f"testosterone {float(value):g}"]
        except ValueError:
            return [f"testosterone {value}"]
    normal, abnormal = [], []
    for label, names in (("T", _TESTO_TOTAL_ITEMS), ("F", _TESTO_FREE_ITEMS)):
        token = _named_flag_token(items, names, f"testosterone {label}")
        if token is None:
            continue
        if token.endswith(" nl"):
            normal.append(label)
        else:
            abnormal.append(token)
    tokens = [f"testosterone {'/'.join(normal)} nl"] if normal else []
    tokens.extend(abnormal)
    return tokens


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


def _ldl_token(items):
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


def _hdl_token(items):
    tg = next(
        (it for it in items if it["name"].strip().lower() in _TG_ITEMS),
        None,
    )
    if tg is not None and _is_abnormal(tg["flag"]):
        return None
    hdl = next(
        (it for it in items if it["name"].strip().lower() in _HDL_ITEMS),
        None,
    )
    if hdl is None or not _is_abnormal(hdl["flag"]):
        return None
    value = hdl["value"].strip()
    if not value:
        return None
    bound = _bound_for(str(hdl["flag"] or "").strip().upper(), hdl["range"])
    if not bound:
        return f"HDL {value}"
    return f"HDL {value}({bound})"


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


def _imaging_notes(result):
    if not result:
        return ""
    try:
        data = json.loads(result)
    except (TypeError, json.JSONDecodeError):
        return ""
    if not isinstance(data, list):
        return ""
    parts = [str(entry["notes"]).strip() for entry in data
             if isinstance(entry, dict)
             and str(entry.get("notes") or "").strip()]
    return "\n".join(parts)


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


def _us_label(name):
    """The yellow notes' region label for a `US ...` order name
    (rule 9c): the first matching keyword's label, else the first
    name word that is not the `us` / `plus` / `ultrasound` shorthand
    or a `2d` / `3d` view tag."""
    for keyword, label in _US_LABELS:
        if keyword in name:
            return label
    for word in re.split(r"\W+", name):
        if word not in ("", "us", "plus", "ultrasound", "2d", "3d"):
            return word
    return "us"


# Report tails that end the `IMPRESSION` section (rule 9c).
_US_TAIL_RE = re.compile(
    r"electronically\s+signed|a\s+letter\s+stating"
    r"|in\s+compliance\s+with\s+mqsa|thank\s+you\s+for", re.I)


def _us_impression(notes):
    """The report's `IMPRESSION` section text -- the head is
    `IMPRESSION` / `CONCLUSION` / `ASSESSMENT...` (the Plus breast
    reports' `ASSESSMENT/MANAGEMENT`); when the report carries no
    such head, the whole report -- without the signed-by / letter /
    MQSA tail (rule 9c)."""
    m = re.search(r"^\s*(?:IMPRESSION|CONCLUSION|ASSESSMENT[^:]*)\s*:\s*",
                  notes, re.M | re.I)
    rest = notes[m.end():] if m is not None else notes
    if m := _US_TAIL_RE.search(rest):
        rest = rest[:m.start()]
    return rest


# Impression sentences that are boilerplate or advice, not findings
# (rule 9c): the lifetime-risk / Tyrer-Cuzick lines, the `BI-RADS` /
# `LI-RADS` assessment lines, the ACR TI-RADS guideline block and its
# source / disclaimer lines, the radiologist-signature lines (an
# `M.D.` / `DABR` / `CAQ` line), the `Given the positive findings`
# transmission line, the `refer to` deferral, the `rescanning may be
# considered` / `nonspecific finding` lines, the annual-screening-
# scheduling lines, the report's `Exam #` / `Exam Performed at` head
# lines (the reports with no `IMPRESSION` head), the liver-fat
# grading-scale lines (`Liver fat is graded...` / `hepatocytes
# contain fat` / `Grade N (...) = ...`), and the `correlate with
# ... laboratory parameters` / `clinical correlation` advice lines.
_US_SKIP_RE = re.compile(
    r"lifetime\s+risk|tyrer-?cuzick|breast\s+cancer\s+risk"
    r"|^\s*bi-?rads\b|^\s*li-?rads\b"
    r"|american\s+college\s+of\s+radiology|ti-?rads\s*\(tr\)"
    r"|\bTR\d\s*:|follow-up\s+ultrasound\s+guidelines"
    r"|^\s*source:|\btesler\b|j\s*am\s*coll\s*radiol|koios\s+ai\s+adapter"
    r"|\bM\.D\.?|\bDABR\b|\bCAQ\b"
    r"|\bgiven\s+the\s+positive\s+findings\b"
    r"|^\s*refer\s+to\b|^\s*exam\s*#|^\s*exam\s+performed\s+at\b"
    r"|\brescanning\s+may\s+be\s+considered|\bnonspecific\s+finding\b"
    r"|annual\s+routine\s+bilateral\s+screening"
    r"|increased\s+breast\s+density|adding\s+screening\s+ultrasound"
    r"|liver fat is graded|hepatocytes contain fat|^\s*grade \d+ \("
    r"|\bcorrelate\b.*\blaboratory\b|\bclinical\s+correlation\b"
    r"|^\s*correlate\s+with\b"
    r"|\bcorrelation\s+is\s+advised\b"
    r"|\bcorrelation\s+with\s+(?:liver\s+function\s+tests?|laboratory)\b",
    re.I)
# A two-word name line (a radiologist's signature on the old
# Health-Diagnostics reports), case-sensitive (rule 9c).
_US_NAME_LINE_RE = re.compile(r"^\s*[\w.]+ [A-Z][\w.]*$")
# Negative-statement / limitation phrases that make an impression
# sentence an `nl` statement, not a finding (rule 9c): a `... are
# obscured` sentence is the exam's limitation, not a finding.
_US_NEG_PHRASE_RE = re.compile(
    r"unremarkable|\bwithin normal limits\b|no evidence|no acute process"
    r"|no other significant|no abnormal|\bwithout residual abnormality\b"
    r"|\bwithout focal\b|\bis not seen\b|\bnot seen at present\b|\bobscured\b"
    r"|\bno significant interval change\b|\bno further follow-?up\b"
    r"|not significantly changed|\bappears? (?:to be )?normal\b|\bis normal\b",
    re.I)
# The finding words that keep a `No ...` / `Normal ...` sentence a
# finding (a followed-up mass, a stone, a nodule `measuring` a size,
# a fatty liver) (rule 9c).
_US_FINDING_RE = re.compile(
    r"\bmasses?\b|\bpolyps?\b|\bstones?\b|\bcalcul|\bplaques?\b"
    r"|\bnodules?[^.]*\bmeasuring\b|\bfatty\b|\bsteatos", re.I)


def _us_findings(notes):
    rest = _us_impression(notes)
    # The breast report's `BI-RADS {n}` assessment line is not a
    # finding, nor is anything after it; the same for the ACR
    # TI-RADS guideline block, the WFUMB elastography guideline
    # table and the Koios disclaimer that trail the impression.
    for cut in (r"\bBI-?RADS\b", r"american\s+college\s+of\s+radiology",
                r"world\s+federation\s+of\s+ultrasound",
                r"koios\s+ai\s+adapter"):
        if m := re.search(cut, rest, re.I):
            rest = rest[:m.start()]
    # The `1. ` / `2. ` numbering is dropped; a lower-case-opening
    # (or parenthetical) line continues the previous line's sentence
    # (a wrapped sentence, eg the carotid report's `... stenosis on
    # either / side.`).
    segs = []
    for raw in rest.splitlines():
        line = re.sub(r"^\s*\d+\.\s*", "", raw.strip())
        if not line:
            continue
        if segs and (line[0].islower() or line[0] in "(-"):
            segs[-1] += " " + line
        else:
            segs.append(line)
    findings = []
    any_sent = False
    for seg in segs:
        seg = re.sub(r"\s+", " ", seg).strip()
        for sent in re.split(r"(?<=[.!?;])\s+(?=[A-Z\"(])", seg):
            sent = sent.strip()
            if not sent or _US_SKIP_RE.search(sent) \
                    or _US_NAME_LINE_RE.search(sent):
                continue
            any_sent = True
            if _US_NEG_PHRASE_RE.search(sent):
                continue
            if (re.match(r"^(?:no|non)[\s\-]", sent, re.I)
                    or re.match(r"^(?:otherwise\s+)?normal\b", sent, re.I)):
                if not _US_FINDING_RE.search(sent):
                    continue
            findings.append(sent.rstrip("."))
    return findings, any_sent


def _us_token(notes, label):
    matches = list(_BIRADS_RE.finditer(notes))
    if matches:
        n = int(matches[-1].group(1))
        if n in (1, 2):
            return f"US {label} nl"
    findings, any_sent = _us_findings(notes)
    if not any_sent or (matches and not findings):
        return None
    if not findings:
        return f"US {label} nl"
    return f"US {label}: " + ". ".join(findings)


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


def _ct_label(name):
    if "chest" in name or "thorax" in name or "thoracic" in name:
        return "chest"
    if "head" in name or "brain" in name:
        return "head"
    if "abdomen" in name or "abdominal" in name:
        if "pelvis" in name or "pelvic" in name:
            return "abd/pelvic"
        return "abd"
    for part in re.split(r"[\s\-]+", name):
        if part not in ("", "ct"):
            return part
    return "ct"


# The report tails that end the `IMPRESSION` section (rule 9e): the
# signed-by / radiologist-hotline / referral-letter lines, the
# report's `RECOMMENDATION` / `DIAGNOSES` / `ADDENDUM` / `DISCLAIMER`
# section heads, and the `FLEISCHNER SOCIETY FOLLOW-UP GUIDELINES`
# head whose nodule-size table trails the impression.
_CT_TAIL_RE = re.compile(
    r"electronically\s+signed\s+by"
    r"|\bthank\s+you\s+for\s+your\s+kind\s+referral\b"
    r"|radiologist\s+hotline"
    r"|^\s*(?:recommendations?|diagnoses|addendum|disclaimer)\s*:"
    r"|^\s*recommended\s+follow[- ]?up\s*:?\s*$"
    r"|^\s*fleischner\s+society\b"
    r"|^\s*computed tomography\s+of\b|^\s*history\s*:"
    r"|^\s*findings\s*:", re.M | re.I)
# The Fleischner / ACR-White-Paper guideline citations that trail a
# finding's follow-up sentence (rule 9e): the citation and the
# guideline's own recommendation text are not part of the finding.
_CT_GUIDE_CITE_RE = re.compile(
    r"\b(?:\d{4}\s+ACR\s+)?Fleischner\b|\bACR\s+White\s+Paper\b"
    r"|\bMacMahon\b|Herts et al", re.I)
# Impression sentences that are boilerplate or counseling, not
# findings (rule 9e): the report-transmission lines, the radiologist-
# signature lines (an `M.D.` / `Diplomate` / `CAQ` line), the emphysema
# report's LDCT-screening counseling block, the `recommendation applies
# unless` / `advised to consult` advice lines, the AI nodule-detection
# disclaimer lines, the guideline-citation journal lines that the
# sentence split leaves behind, and the exam-head / technique / dose
# lines of a report with no `IMPRESSION` section (the
# `_ct_impression`'s head check keeps those out of the impression;
# the lines are skipped for safety), the `chronic and ancillary` /
# `Please see above` filler lines, and the LUNG-RADS template's
# version / category lines.
_CT_SKIP_RE = re.compile(
    r"^\s*exam\s*#|^\s*exam\s+performed\s+at\b"
    r"|^\s*indication\b|^\s*technique\b|^\s*comparison\b"
    r"|^\s*contrast\s*:|radiation\s+dose|ctdi\s+volume|\balara\b"
    r"|optiray|\bdlp\b|prior known ct or cardiac"
    r"|given\s+the\s+positive\s+findings|simonmed\s+assistant"
    r"|to be communicated to the ordering"
    r"|\bM\.D\.?\b|\bDiplomate\b|American Board of Radiology"
    r"|\bCAQ\b|\bDABR\b"
    r"|\bdisclaimer\b|ai lung nodule detection|nodule prediction"
    r"|ai-assisted analysis|refer to the radiologist"
    r"|independent\s+risk\s+factor\s+for\s+lung\s+cancer"
    r"|\bldct\b|low-dose\s+ct\s+(?:lung\s+cancer\s+)?screening"
    r"|\bconsider\s+enrollment\b|recommendation\s+applies\s+unless"
    r"|\badvised\s+to\s+consult\b|comprehensive\s+cardiovascular\s+risk"
    r"|baseline\s+for\s+future\s+screening"
    r"|chronic\s+and\s+ancillary|please\s+see\s+above"
    r"|^\s*clinical\s+indication\b|contrast\s+used\b|highest\s+ctdi\b"
    r"|multiplanar\s+reconstructions"
    r"|\bversion\s+\d\s+\.\s+\d\s+edition\b|^\s*category\s+\d"
    r"|correlation with urine analysis"
    r"|\bet\s+al\b|\bJ\s+Am\s+Coll\s+Radiol\b"
    r"|\bRadiology\s+\d{4}\b|\bsuggest\s+the\s+following\b"
    r"|\bhigh\s+index\s+of\s+suspicion\b"
    r"|\bas\s+clinically\s+indicated\b"
    r"|\bclinical\s+correlation\b", re.I)
# A `No A, B or C ...` list of absent findings (the head reports'
# `No hemorrhage, mass or large infarct identified`, `No free fluid
# or free air`) is a negative statement, not a finding (rule 9e).
_CT_NEG_LIST_RE = re.compile(r"^\s*no\s+.+\bor\b", re.I)
# Negative-statement phrases that make an impression sentence an `nl`
# statement, not a finding (rule 9e).
_CT_NEG_PHRASE_RE = re.compile(
    r"unremarkable|\bwithin normal limits\b|\bno evidence\b"
    r"|\bno acute\b|\bno abnormal\b|\bno suspicious\b|\bno focal\b"
    r"|\bno definite\b"
    r"|\bno\s+(?:other\s+|additional\s+)?significant\b"
    r"|\bno significant interval change\b"
    r"|\bno need for (?:further\s+)?follow-?up\b"
    r"|\bno further (?:follow-?up|evaluation)\b"
    r"|\bno hemorrhage\b"
    r"|\bnot (?:seen|dilated|enlarged)\b|\bis not seen\b"
    r"|\bappears? (?:to be )?normal\b|\bis normal\b|\bgrossly normal\b"
    r"|\bno (?:free fluid|free air)\b", re.I)
# The finding words that keep a `No ...` / `Normal ...` sentence a
# finding (a followed-up mass, a nodule `measuring` a size, a fatty
# liver) (rule 9e).
_CT_FINDING_RE = re.compile(
    r"\bmasses?\b|\bcysts?\b|\bstones?\b|\bcalcul\w*"
    r"|\bnodules?[^.]*\bmeasuring\b|\bfatty\b|\bsteatos\b", re.I)
# A bare two-word line / sentence with no punctuation (the
# radiologist's signature name `Piampiano Peter` / `ZINN WILLIAM`, the
# report's `Or her` dictation typo) is not a finding (rule 9e).
_CT_NAME_LINE_RE = re.compile(r"^\s*[A-Z]\w*\s+\w+\s*$")
# A bare all-caps section header with nothing after its colon (the
# report template's empty `MIPS:` attestation line) is not a finding
# (rule 9e).
_CT_HEADER_RE = re.compile(r"^\s*[A-Z][A-Z0-9 /&\-]*:\s*$")
# Remove just the trailing cross-reference in a finding sentence
# (`..., and additional findings as above`,
#  `... and other chronic and ancillary findings as described above`)
_CROSSREF_TAIL_RE = re.compile(
    r"\s*[,;]?\s*(?:and\s+)?"
    r"(?:other\s+|additional\s+)?"
    r"(?:chronic\s+and\s+ancillary\s+)?"
    r"findings?(?:\s+and\s+details)?\s+as\s+(?:above|described)\s*\.?$")


def _ct_impression(notes):
    m = re.search(r"^\s*(?:IMPRESSION|CONCLUSION|ASSESSMENT)\s*:?\s*",
                  notes, re.M | re.I)
    if m is None:
        return None
    rest = notes[m.end():]
    cuts = [mm.start() for mm in _CT_TAIL_RE.finditer(rest)]
    if cuts:
        rest = rest[:min(cuts)]
    return rest


def _ct_cut_citation(sent):
    """The sentence without its Fleischner / ACR-White-Paper guideline."""
    m = _CT_GUIDE_CITE_RE.search(sent)
    if m is None:
        return sent
    cut = re.sub(r"(\s*(?:in keeping with|per|according to|as))+\s*$",
                 "", sent[:m.start()].rstrip(), flags=re.I)
    return re.sub(r"\s*(?:;|,)\s*$", "", cut)


def _ct_findings(notes):
    impression = _ct_impression(notes)
    if impression is None:
        return [], False
    segs = []
    for raw in impression.splitlines():
        line = re.sub(r"^\s*\d+\.\s*", "", raw.strip())
        if not line:
            continue
        if _CT_NAME_LINE_RE.match(line):
            continue
        if _CT_HEADER_RE.match(line):
            continue
        if segs and (line[0].islower() or line[0] in "(-"):
            segs[-1] += " " + line
        else:
            segs.append(line)
    findings = []
    any_sent = False
    for seg in segs:
        seg = re.sub(r"\s+", " ", seg).strip()
        for sent in re.split(r"(?<=[.!?;])\s+(?=[A-Z\"(])", seg):
            sent = sent.strip()
            if not sent:
                continue
            # the citation is cut before the skip checks: a finding's
            # sentence can carry the citation's journal line in the
            # same sentence (the guideline block trails it)
            sent = _ct_cut_citation(sent)
            if not sent or _CT_NAME_LINE_RE.match(sent) \
                    or _CT_SKIP_RE.search(sent):
                continue
            # the cross-reference tail pointing back at the findings
            # section is cut, the finding kept; a sentence of only
            # tail is dropped and does not count as usable
            sent = _CROSSREF_TAIL_RE.sub("", sent).strip()
            if not sent.rstrip("."):
                continue
            any_sent = True
            if _CT_NEG_PHRASE_RE.search(sent):
                continue
            if (re.match(r"^(?:no|non)[\s\-]", sent, re.I)
                    or re.match(r"^(?:otherwise\s+)?normal\b", sent, re.I)):
                if _CT_NEG_LIST_RE.search(sent) \
                        or not _CT_FINDING_RE.search(sent):
                    continue
            findings.append(sent.rstrip("."))
    return findings, any_sent


def _ct_token(notes, label):
    findings, any_sent = _ct_findings(notes)
    if not any_sent:
        return None
    if not findings:
        return f"CT {label} nl"
    return f"CT {label}: " + ". ".join(findings)


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


def _uric_token(items):
    """normal `uric acid {val}`. abnormal `uric acid {val}({bound})`."""
    it = items[0]
    value = it["value"].strip()
    if not value:
        return None
    shown = _g(value)
    if not _is_abnormal(it["flag"]):
        return f"uric acid {shown}"
    bound = _bound_for(str(it["flag"] or "").strip().upper(), it["range"])
    if not bound:
        return f"uric acid {shown}"
    return f"uric acid {shown}({bound})"


def _psa_tokens(items):
    """`PSA {val}` for the total PSA item. When the total is borderline
    (4-10 ng/mL) and the free% item is under 25, add `PSA%free {val}`."""
    it = next((it for it in items
               if it["name"].strip().lower() in _PSA_TOTAL_ITEM_NAMES),
              items[0])
    value = it["value"].strip()
    if not value:
        return []
    try:
        total = float(value)
        first = f"PSA {_g(_round1(value))}"
    except ValueError:
        total = None
        first = f"PSA {value}"
    tokens = [first]
    pct = next((it for it in items
                if it["name"].strip().lower() in _PSA_PCT_FREE_NAMES),
               None)
    if pct is None or total is None:
        return tokens
    pct_value = pct["value"].strip()
    try:
        pct_num = float(pct_value)
    except ValueError:
        return tokens
    # The range top the total (if flagged high) violates, else the
    # standard PSA upper limit of 4.0.
    upper = 4.0
    bound = _bound_for(str(it["flag"] or "").strip().upper(), it["range"])
    if bound is not None:
        upper = float(bound)
    if total >= upper and total < 10.0 and pct_num < 25.0:
        tokens.append(f"PSA%free {_int_value(pct_value)}")
    return tokens


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


def _hav_token(items):
    """`HAV Ab+` when the HAV total antibody (single item in both
    vendors' layouts) is positive (Quest's `REACTIVE`, LabCorp's
    `Positive`); a negative / equivocal value produces nothing.  HAV
    IgM is a different test and is not part of this category."""
    value = items[0]["value"].strip().lower()
    return "HAV Ab+" if value in _POSITIVE_VALUES else None


def _hav_igm_token(items):
    """`HAV IgM+` when the HAV IgM screen (the acute-hepatitis-A test;
    the single item in both vendors' layouts) is positive (Quest's
    `REACTIVE`, LabCorp's `Positive`); a negative value produces
    nothing -- the yellow notes omit a negative HAV IgM (rule 25a)."""
    value = items[0]["value"].strip().lower()
    return "HAV IgM+" if value in _POSITIVE_VALUES else None


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


def _b12_token(items):
    it = next(
        (it for it in items if it["name"].strip().lower() in _B12_ITEMS),
        None,
    )
    if it is None:
        return None
    value = it["value"].strip()
    if not value:
        return None
    if not _is_abnormal(it["flag"]):
        return f"B12 {value}"
    rng = it["range"].strip()
    flag = str(it["flag"] or "").strip().upper()
    bound = rng
    if "-" in rng:
        lo, hi = (part.strip() for part in rng.split("-", 1))
        bound = hi if flag == "H" else (lo if flag == "L" else rng)
    if not bound:
        return f"B12 {value}"
    return f"B12 {value}({bound})"


def _b6_value(value):
    """Round to integer above 10, else two sig figs eg 3.4."""
    try:
        num = float(value.strip())
    except ValueError:
        return value
    return f"{num:.0f}" if abs(num) >= 10 else f"{num:.2g}"


def _b6_token(items):
    """Normal `B6 nl`. Abnormal `B6 {val}({bound})`."""
    it = next(
        (it for it in items if it["name"].strip().lower() in _B6_ITEMS),
        None,
    )
    if it is None:
        return None
    if not _is_abnormal(it["flag"]):
        return "B6 nl"
    value = it["value"].strip()
    if not value:
        return None
    shown = _b6_value(value)
    bound = _bound_for(str(it["flag"] or "").strip().upper(), it["range"])
    if not bound:
        return f"B6 {shown}"
    return f"B6 {shown}({_b6_value(bound)})"


def _b1b6_tokens(latest):
    """Normal `B1/B6 nl`. Abnormal `{label} {val}({bound})`."""
    members = []
    if "b1" in latest:
        members.append(("b1", "B1", _B1_ITEMS))
    if "b6" in latest:
        members.append(("b6", "B6", _B6_ITEMS))
    normal, abnormal = [], []
    for category, label, item_names in members:
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
    does not (an abnormal surface-Ag / HCV result reports its own
    `HBsAg+` / `HCV+` token, see `_hbsag_token` / `_hcv_token`) --
    and an abnormal HIV / RPR result drops its group (its positive
    result reports its own `HIV+` / `RPR+` token, see `_hiv_token` /
    `_rpr_token`); a
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


def _hbsag_token(latest):
    """The hep B surface-antigen positive token (rule 21): `HBsAg+`
    right after the STD token when the surface-Ag screen is abnormal
    (the HBV/HCV group of the STD token drops from its ` neg` list
    instead, see `_std_token`).  The token also covers a partial trio
    (a surface-Ag order without the other two hep B/C rows), so a
    lone reactive screen is never silent.  A normal / pending screen
    produces nothing (a negative result of an incomplete trio reports
    its own `HBV neg` token, see `_hbv_neg_token`; otherwise it joins
    the STD token only when the whole trio is present)."""
    if "hbsag" in latest and _abnormal_items(latest["hbsag"]):
        return "HBsAg+"
    return None


def _hbv_neg_token(latest):
    """`HBV neg` right after the STD token when the surface-Ag
    screen is negative but the hep B/C trio is incomplete (a missing
    HCV / surface-Ab row), so the negative result would otherwise be
    silent. The complete trio reports `HBV/HCV neg` instead."""
    if "hbsag" not in latest:
        return None
    # the complete trio reports its HBV half in the STD token
    if "hcv" in latest and "hbsab" in latest:
        return None
    if _abnormal_items(latest["hbsag"]):
        return None
    # the explicit negative value decides: a pending / empty screen
    # is undetermined, not negative
    if not any(it["value"].strip().lower() in _NEGATIVE_VALUES
               for it in latest["hbsag"]):
        return None
    return "HBV neg"


def _hcv_token(latest):
    """The HCV Ab positive token (rule 21): `HCV+` right after the
    STD token when the HCV Ab screen is abnormal (the HBV/HCV group
    of the STD token drops from its ` neg` list instead, see
    `_std_token`).  The token also covers a partial trio (an HCV
    order without the other two hep B/C rows), so a lone reactive
    screen is never silent.  A non-reactive / pending screen produces
    nothing (the negative result joins the STD token only when the
    whole trio is present; a detected reflexed RNA reports its own
    `HCV RNA` token, rule 22a)."""
    if "hcv" in latest and _abnormal_items(latest["hcv"]):
        return "HCV+"
    return None


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
    valued = [it for it in items if it["value"].strip()]
    return any(it["value"].strip().lower() in _POSITIVE_VALUES
               for it in valued)


def _hiv_token(latest):
    """The HIV positive token (rule 21): `HIV+` right after the STD
    token when the screen is positive (see `_hiv_positive`); the HIV
    group of the STD token drops from its ` neg` list instead (see
    `_std_token`).  A negative / pending result produces nothing."""
    if "hiv" in latest and _hiv_positive(latest["hiv"]):
        return "HIV+"
    return None


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


def _rpr_token(latest):
    """The RPR positive token (rule 21): `RPR+` right after the STD
    token when the screen is reactive (see `_rpr_positive`); the RPR
    group of the STD token drops from its ` neg` list instead (see
    `_std_token`).  A non-reactive / pending result produces
    nothing."""
    if "rpr" in latest and _rpr_positive(latest["rpr"]):
        return "RPR+"
    return None


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
    layouts) is negative, `QTB+` when it is positive; an indeterminate
    / missing interpretation produces nothing."""
    for it in items:
        value = it["value"].strip().lower()
        if value in _QTB_INTERPRETATIONS:
            if value == "negative":
                return "QTB neg"
            if value == "positive":
                return "QTB+"
            return None
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
        (it for it in items if it["name"].strip().lower() in _ABO_ITEMS),
        None,
    )
    rh = next(
        (it for it in items if it["name"].strip().lower() in _RH_ITEMS),
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
    """The sticky allergen group of an allergy-panel item name
    (rule 44), or None for the items the summary does not report
    (the `CLASS` / `Class Description` items, the total-IgE / `Reflex`
    items, the unreportable cockroach `(I6)` item): the item's code
    tag's letter -- the in-house `({CODE})` tag (`(M6)` -> mold,
    `(D2)` -> dust mite, `(E1)` -> animal, `(T2)` / `(W10)` /
    `(G8)` -> pollen, `(F13)` -> food) or the LabCorp leading
    `{CODE}-` (likewise) -- or, code-less, the two mite IgG4
    orders' mite items (dust mite)."""
    name = name.strip().lower()
    m = re.search(r"\(([a-z])\d+\)", name)
    if m:
        return _ALLERGY_CODE_GROUPS.get(m.group(1))
    m = _ALLERGY_LEADING_CODE.match(name)
    if m:
        return _ALLERGY_CODE_GROUPS.get(m.group(1))
    if name in _ALLERGY_MITE_CODELESS:
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


def _allergy_positive(it, group):
    """True when one allergen item is positive (rule 44): a flagged-
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
    m = re.search(r"\d+(?:\.\d+)?", value)
    if m is None:
        return False
    num = float(m.group())
    bound = _allergy_bound(it)
    if bound is not None:
        return num >= float(bound)
    return num >= _ALLERGY_IGE_POSITIVE_AT


def _allergy_tokens(latest):
    """The allergy-panel tokens (rule 44): the negative groups join
    one token, their labels in the fixed group order `mold` /
    `dust mite` / `pollen` / `animal` / `food` joined with `/` plus
    a single trailing ` neg` (eg `allergy mold/dust mite/pollen
    neg`; the yellow notes write a negative panel as `all.ergy
    mold/dust mite/Pollen neg`); each positive item reports its own
    `{group} {val}+({bound})` token right after that one, in group
    order then report order (the value's trailing zeros stripped;
    the parenthesized bound the item's positivity threshold -- the
    mite IgG4 items' range upper limit, the specific-IgE 0.10
    cutoff for the rest -- 21309's yellow note writes a positive
    mite `dust mite 0.23+(0.1)`).  A group whose newest row has no
    usable item / value produces nothing (a pending panel)."""
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
                     if _allergy_positive(it, group)]
        if positives:
            for it in positives:
                shown = _g(it["value"].strip())
                bound = _allergy_bound(it)
                if bound is None:
                    bound = _g(_ALLERGY_IGE_POSITIVE_AT)
                tokens.append(f"{group} {shown}+({bound})")
        else:
            normal.append(group)
    if normal:
        tokens.insert(0, "allergy " + "/".join(normal) + " neg")
    return tokens


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
    result value is one) when any ANA item (`_ANA_ITEMS`) is flagged
    abnormal; `ANA nl` when no ANA item is flagged abnormal (Quest's
    negative results and its empty-valued items both fall here);
    any other nonempty ANA item value produces nothing (rule 33).
    The panel's RF / CCP items are the categories of rules 34a /
    b, not ANA items, so their values do not affect the verdict."""
    ana = [it for it in items if it["name"].strip().lower() in _ANA_ITEMS]
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
        (it for it in items if it["name"].strip().lower() in _C3_ITEMS),
        None,
    )
    c4 = next(
        (it for it in items if it["name"].strip().lower() in _C4_ITEMS),
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
        (it for it in items if it["name"].strip().lower() in _DSDNA_ITEMS),
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


def _hb_htlv_tokens(latest):
    members = []
    if "hb_elec" in latest:
        members.append(("hb_elec", "Hb electrophoresis", _HB_ELEC_ITEMS))
    if "htlv" in latest:
        members.append(("htlv", "HTLV", _HTLV_ITEMS))
    normal, positive = [], []
    for category, label, item_names in members:
        it = next(
            (it for it in latest[category]
             if it["name"].strip().lower() in item_names),
            None,
        )
        if it is None:
            continue
        value = it["value"].strip().lower()
        if value in _POSITIVE_VALUES:
            positive.append(f"{label}+")
        elif value in _NEGATIVE_VALUES:
            normal.append(label)
    tokens = ["/".join(normal) + " neg"] if normal else []
    tokens.extend(positive)
    return tokens


def _hbsab_token(latest):
    if "hbsabq" in latest:
        it = next(
            (it for it in latest["hbsabq"]
             if it["name"].strip().lower() in _HBSABQ_ITEMS),
            None,
        )
        if it is not None:
            m = re.search(r"\d+(?:\.\d+)?", it["value"].strip())
            if m is not None:
                level = float(m.group())
                if level > _HBSABQ_IMMUNE_ABOVE:
                    return "HBV Ab+"
                return "HBV Ab neg"
        return None
    if "hbsab" in latest:
        it = next(
            (it for it in latest["hbsab"]
             if it["name"].strip().lower() in _HBSAB_ITEMS),
            None,
        )
        if it is not None:
            value = it["value"].strip().lower()
            if value in _POSITIVE_VALUES:
                return "HBV Ab+"
            if value in _NEGATIVE_VALUES:
                return "HBV Ab neg"
    return None


def _hpylori_token(items):
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
    it = next(
        (it for it in items if it["name"].strip().lower() == "result 1"),
        items[0],
    )
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
    states = []
    for line in it["notes"].lower().splitlines():
        label, sep, text = line.partition(":")
        if not sep or not label.strip().lower().startswith(
                ("concentration", "trichrome")):
            continue
        text = text.strip()
        if text.startswith("no ova or parasites"):
            states.append("neg")
        elif "seen" in text:
            states.append("pos")
    if states:
        return "pos" if "pos" in states else "neg"
    notes = it["notes"].lower()
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
    """The stool-parasite tokens (rule 36b): `stool O-P neg` when
    every present ova-and-parasite / giardia / cryptosporidium order
    is negative (the yellow notes' shorthand for a negative
    stool-parasite workup); one `{label}+` token per positive order
    -- `O-P+` / `Giardia+` / `Cryptosporidium+`, in that order -- and
    the negative members are not reported.  Pending / unrecognized
    orders produce nothing (a lone negative next to a pending one
    reports nothing either)."""
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
        return ["stool O-P neg"]
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
        name = (row.get("name") or "").strip().lower()
        if name in _CT_CAC_NAMES:
            if ct_notes is None:
                notes = _imaging_notes(row.get("result"))
                if notes:
                    ct_notes = notes
                    if first is None:
                        first = row
            continue
        if _MAMMO_NAME_RE.search(name):
            if mammo_notes is None:
                notes = _imaging_notes(row.get("result"))
                if notes:
                    mammo_notes = notes
                    if first is None:
                        first = row
            continue
        if _US_NAME_RE.match(name):
            notes = _imaging_notes(row.get("result"))
            if notes:
                label = _us_label(name)
                if label not in us_notes:
                    # a `refer to ... report` deferral is not used for
                    # the region's newest result
                    if _us_findings(notes)[1]:
                        us_notes[label] = notes
                        if first is None:
                            first = row
            continue
        if _BMD_NAME_RE.search(name):
            if bmd_notes is None:
                notes = _imaging_notes(row.get("result"))
                if notes and _bmd_sites(notes):
                    # skip a report that names no T-score
                    bmd_notes = notes
                    if first is None:
                        first = row
            continue
        if _CT_SCAN_NAME_RE.match(name):
            notes = _imaging_notes(row.get("result"))
            if notes:
                label = _ct_label(name)
                if label not in ct_scan_notes:
                    # skip a report without an `IMPRESSION` section
                    if _ct_findings(notes)[1]:
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
    if "hcg" in latest:
        add(_hcg_token(latest["hcg"]))
    if "tsh" in latest:
        add(_tsh_token(latest))
    for token in _thyroid_cluster_tokens(latest):
        add(token)
    if "fsh" in latest:
        add(_flag_token("FSH", latest["fsh"]))
    if "estradiol" in latest:
        add(_named_flag_token(latest["estradiol"], _ESTRADIOL_NAMES, "Estradiol"))
    if "testo" in latest:
        for token in _testo_tokens(latest["testo"]):
            add(token)
    if "cortisol" in latest:
        add(_flag_token("cortisol", latest["cortisol"]))
    if "prolactin" in latest:
        add(_flag_token("prolactin", latest["prolactin"]))
    if "lh" in latest:
        add(_named_flag_token(latest["lh"], _LH_ITEMS, "LH", _int_value))
    if "progesterone" in latest:
        add(_flag_token("Progesterone", latest["progesterone"]))
    if "amh" in latest:
        add(_named_flag_token(latest["amh"], _AMH_ITEMS, "AMH", _g))
    if "a1c" in latest:
        glu = _liver_glucose(latest["liver"]) if "liver" in latest else None
        token = _a1c_token(latest["a1c"], glu)
        if not token and "liver" in latest:
            # a pending / empty A1c leaves the panel's glucose
            # unpaired: report it like the standalone order's
            token = _named_item_token(latest["liver"], _GLUCOSE_ITEMS, "Glu", _g)
        add(token)
    elif "liver" in latest:
        # no A1c order: the panel's glucose stands in for the
        # standalone-glucose token of rule 5a
        add(_named_item_token(latest["liver"], _GLUCOSE_ITEMS, "Glu", _g))
    if "glu" in latest:
        add(_named_item_token(latest["glu"], _GLUCOSE_ITEMS, "Glu", _g))
    if "albcr" in latest:
        add(_albc_token(latest["albcr"]))
    if "lipid" in latest:
        add(_hdl_token(latest["lipid"]))
        add(_ldl_token(latest["lipid"]))
    if "lpa" in latest:
        add(_named_flag_token(latest["lpa"], _LPA_ITEMS, "LpA", _int_value))
    if "apob" in latest:
        add(_named_flag_token(latest["apob"], _APOB_ITEMS, "ApoB"))
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
        for label in _US_LABEL_ORDER:
            if label in us_notes:
                add(_us_token(us_notes[label], label))
        for label in us_notes:
            if label not in _US_LABEL_ORDER:
                add(_us_token(us_notes[label], label))
    if bmd_notes is not None:
        add(_bmd_token(bmd_notes))
    if ct_scan_notes:
        for label in _CT_LABEL_ORDER:
            if label in ct_scan_notes:
                add(_ct_token(ct_scan_notes[label], label))
        for label in ct_scan_notes:
            if label not in _CT_LABEL_ORDER:
                add(_ct_token(ct_scan_notes[label], label))
    if "cbc" in latest:
        add(_cbc_token(latest["cbc"]))
        add(_cbc_mcv_token(latest["cbc"]))
        add(_named_item_token(latest["cbc"], _WBC_ITEMS, "WBC", _round1))
        add(_named_item_token(latest["cbc"], _HB_ITEMS, "Hb", _round1))
        add(_named_item_token(latest["cbc"], _PLT_ITEMS, "Plt", _g))
        add(_named_item_token(latest["cbc"], _HCT_ITEMS, "Hematocrit", _g))
        add(_named_item_token(latest["cbc"], _EOS_ITEMS, "Eos", _g))
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
        add(_named_flag_token(latest["ptt"], _PTT_ITEMS, "PTT"))
    if "bnp" in latest:
        add(_named_flag_token(latest["bnp"], _BNP_ITEMS, "BNP"))
    add(_std_token(latest))
    add(_hbv_neg_token(latest))
    add(_hbsag_token(latest))
    add(_hcv_token(latest))
    add(_hiv_token(latest))
    add(_rpr_token(latest))
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
    for token in _hb_htlv_tokens(latest):
        add(token)
    add(_hbsab_token(latest))
    if "hav" in latest:
        add(_hav_token(latest["hav"]))
    if "hav_igm" in latest:
        add(_hav_igm_token(latest["hav_igm"]))
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
        add(_named_item_token(latest["ferritin"], _FERRITIN_STANDALONE_ITEMS, "ferritin", _g))
    if "iron_standalone" in latest:
        add(_named_item_token(latest["iron_standalone"], _IRON_STANDALONE_ITEMS, "iron", _g))
    if "copper" in latest:
        add(_flag_token("copper", latest["copper"], _g))
    if "b12" in latest:
        add(_b12_token(latest["b12"]))
    for token in _b1b6_tokens(latest):
        add(token)
    if "b2" in latest:
        add(_flag_token("B2", latest["b2"]))
    if "fa" in latest:
        add(_fa_token(latest["fa"]))
    if "liver" in latest:
        add(_astalt_token(latest["liver"]))
        add(_protein_token(latest["liver"]))
        add(_named_item_token(latest["liver"], _BUN_ITEMS, "BUN", _g))
        add(_cr_token(latest["liver"]))
        add(_named_item_token(latest["liver"], _BILI_ITEMS, "bilirubin", _g))
        add(_named_item_token(latest["liver"], _ALP_ITEMS, "AP", _g))
        add(_named_item_token(latest["liver"], _ALB_ITEMS, "albumin", _g))
        for token in _liver_electrolyte_tokens(latest["liver"]):
            add(token)
    if "ggt" in latest:
        add(_named_item_token(latest["ggt"], _GGT_ITEMS, "GGT", _g))
    if "ck" in latest:
        add(_flag_token("CK", latest["ck"], _g))
    if "amylase" in latest:
        add(_named_flag_token(latest["amylase"], _AMYLASE_ITEMS, "amylase"))
    if "lipase" in latest:
        add(_flag_token("lipase", latest["lipase"]))
    if "ana" in latest:
        add(_ana_token(latest["ana"]))
    for token in _esrcrp_tokens(latest):
        add(token)
    if "rf" in latest:
        add(_named_flag_token(latest["rf"], _RF_ITEMS, "RF"))
    if "ccp" in latest:
        add(_named_flag_token(latest["ccp"], _CCP_ITEMS, "Anti-CCP"))
    if "c3c4" in latest:
        for token in _c3c4_tokens(latest["c3c4"]):
            add(token)
    if "dsdna" in latest:
        add(_dsdna_token(latest["dsdna"]))
    if "crp_cardiac" in latest:
        add(_named_flag_token(latest["crp_cardiac"], _CRP_CARDIAC_ITEMS, "hsCRP", _g))
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
        add(_flag_token("AFP", latest["afp"]))
    if "cea" in latest:
        add(_flag_token("CEA", latest["cea"]))
    if "ca125" in latest:
        add(_flag_token("CA 125", latest["ca125"]))
    if "ca199" in latest:
        add(_named_flag_token(latest["ca199"], _CA199_ITEMS, "CA 19-9"))
    if "ldh" in latest:
        add(_named_flag_token(latest["ldh"], _LDH_ITEMS, "LDH"))
    if "qtb" in latest:
        add(_qtb_token(latest["qtb"]))
    if "abo" in latest:
        add(_abo_token(latest["abo"]))
    for token in _allergy_tokens(latest):
        add(token)

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
