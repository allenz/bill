`+` on some high values in `lab_summary.py`

Prefer simple code

## What patient.yellow_note has

- **High values get `+`** — mostly on values that also show a
  parenthesized range limit: `ApoB 121+(90)` @14103,
  `albumin 5.4++(5.1)` @14103, `LpA 105+` @14717, `T4 1.9+(1.8)`
  @14500, `ALT 39+` @17264, `Mg 6.5+(6.4)` @16473,
  `calcium 10.3+(10.2)` @22322, `Eos 0.6++(0.5)` @16734,
  `Plt 468++(400)` @18511, `TSH 5.3++(4.5)` @19048,
  `uric acid 9.2++(8)` @17504, `PSA 7.4++(4)` @14289,
  `Alb/Cr 66+(30)` @14716, `A1c 6.1++` @22231, `LDL 132+` @22045,
  and in-range high values like VitD (`VitD 62+` @15225; a flagged
  VitD gains its range limit too, `VitD 23(30)` @22586, `VitD
  110+(100)`). (`++` occurs
  throughout; the code keeps a single `+`.)
- **A `+` does not mean the token renders a bound** (VitD's in-range
  `+` has none; its flagged values render one).
- **Glu / A1c highs are almost never signed** in the notes: of ~35
  recent high A1c values exactly one is signed (`A1c 6.1++` @22231)
  and no high Glu ever is -- the 6/2026 @22231 pair reads
  `Glu 121/A1c 6.1++` (Glu unsigned, A1c signed). The code signs
  neither member.
- **TSH** is signed in scattered notes (`5.3++(4.5)` @19048,
  `6.2++(4.5)` @20472, `5++` @22493) but the newest (10-11/2026)
  leave highs unsigned with the bound (`9.7(4.5)` @21152, `9.9(4.5)`
  @22466, `7(4.5)` @12708) -- the split is not severity-based (a
  `4.52 (4.5)` @16839 is unsigned, a `4.8++` @20469 signed), just
  inconsistent; the code follows the newest style (bound, no sign).
  High **T4** reads the same way in the notes (`T4 5.1(4.5)` @17632,
  `2.13` @14402, `3.03` @13952 unsigned; only `1.9+(1.8)` @14500 is
  signed), so the `/T4` suffix follows TSH.
- **BMP / coag / copper / cortisol highs are marked with the bound
  only**, a separate style from the `+` clusters (lipid / CBC / tumor
  marker / thyroid-Ab / PTH): `Cr 1.72(1.3)` @16535, `Cr/CrCl
  2.1(1.3)` @17154, `BUN 40(25)` @19240, `PTT 33(32)` @21484,
  `CO2 33 (32)` @17369, `Cl 113` @16535, `cortisol 24 (22)` @16648,
  `copper 180(175)` @17641 -- no high Cr is signed anywhere. RF is
  mixed (`RF 42(16)` unsigned @19793 vs `RA 18++(15)` @17044).
- **Low values are (nearly) never signed** (`Hb 11(12)` @13681,
  `HDL 35(39)` @22396, `Phos 2.3(2.5)` @21340, `CrCl 41(60)`
  @16535, `T4 0.37` @19589, `VitD 27(30)`); the only signed lows are
  `PSA%free 16++(35)` @14289 (doctor's "attention" mark, not a
  direction) and `LDL 80++` @19728.

## Design

- **High value → `+` on the value; low values never signed; no bound
  definitions change** -- with exceptions: TSH and T4, and the
  Cr / CrCl / BUN / PT / PTT / CO2 / Cl / cortisol / copper cluster,
  render abnormal values as `({bound})` without a sign; the `Glu` / `A1c` pair is unsigned on highs.
- The `+` applies to the numeric value tokens listed below (the
  untouched list excepts them), whether or not the token renders
  `({bound})` (with a bound it reads `val+(bound)`, e.g. `Mg
  6.5+(6.4)`; without one, `PSA 7.4+`, `VitD 62+`).
- High = the item's flag says so (`H` / `HH`; an undirected `A` counts
  as high when the value parses above its range's upper limit).
- VitD keeps its own rule (value above 50 → `+`, even in-range); a
  flagged value also renders its range limit via the shared
  `_bound_for` (low `VitD 23(30)` @22586, high `VitD 110+(100)`),
  so a flagged high needs no extra rule.
- Untouched (their `+` / `neg` is positive/negative semantics, not a
  value mark): PSA%free (low → unsigned), serology / Ab screens
  (`HBsAg+`, `HSV1+`, `HBV Ab+`, `eAg` / `HBcAb` / `HDV` / `HTLV` /
  `Hb electrophoresis+`, `RTC ... vacc`, `dsDNA+`), UA tokens (incl.
  `pH`, `trace+`), `ANA+`, `H pylori+`, `QTB+`, stool tokens, HCG,
  ABO/Rh, allergy `{val}+`, imaging (CAC / US / CT / mammo / BMD),
  `HBV DNA` / `HCV RNA` levels, `plt est`, and `B12` (the notes never
  sign a high B12: `B12 770` @19082, `B12 4,214` @14754).

## Categories gaining `+` on a high value

- via the shared value formatters: MCV, HDL, LpA, ApoB, BNP, FA, RF
  (mixed in the notes, see verified), Anti-CCP, hsCRP, CA 19-9, LDH,
  Estradiol, LH, AMH, B1, B6, B2, thyroid cluster (T3 / TPO /
  thyroglobulin / TSI), testosterone, FSH, prolactin, progesterone,
  Free Calcium, Mg, Mg RBC, Phos, zinc, zinc RBC, CK, amylase,
  lipase, AFP, CEA, CA 125, ESR, CRP, RBC, WBC, Hb, Plt, Eos, iron
  (panel: `iron` / `TIBC` / `iron%sat`, signed in the notes: `TIBC
  479++(400)` @20429, `iron%sat 51++(45)` @12803; + standalone),
  ferritin, GGT, bilirubin, AP, albumin, Ca, Na, K, INR, C3, C4, PTH,
  uric acid.
- custom tokens: plain `LDL` and the high components of the
  `HDL/LDL/TG` triplet, total PSA, `Alb/Cr` ratio, total protein
  (high-only formatter), AST (currently only ALT gains `+`).
- TSH value and the `/T4 {val}` suffix (and standalone T4): abnormal →
  `{val}({bound})`, no sign (`TSH 9.7(4.5)`, `TSH 0.5/T4 1.9(1.8)`);
  a TSH row without a parsable range renders the plain value.
- Bound only, no sign (the notes mark these with the bound): Cr / CrCl,
  BUN, PT / PTT, CO2, Cl, cortisol, copper -- abnormal → `{val}({bound})`.
- `Glu` / `A1c` pair: no sign at any value (`Glu 121/A1c 6.1`); an
  abnormal standalone Glu keeps its existing `({bound})` rendering.
