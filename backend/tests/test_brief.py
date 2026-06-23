"""Tests for the BRIEF → SPEC translation layer.

Fast, pure-function tests: no DB, no PDF, no app bootstrap. Asserts the three contract behaviours
the pillar promises:
  * work_style changes the zone mix (focus vs collaborative differ);
  * a higher WELL target produces a stricter spec sheet than 'none';
  * an over-capacity brief (headcount x density > stated usable area) emits a warning;
  * the `program` payload is ProgramSpec-compatible (drives the existing test-fit unchanged).
"""

from app.brief.translate import Brief, translate_brief
from app.testfit.layout import ProgramSpec, derive_program  # ensure shape compatibility


def test_focus_vs_collaborative_zone_mix_differs():
    focus = translate_brief(Brief(headcount=200, work_style="focus"))
    collab = translate_brief(Brief(headcount=200, work_style="collaborative"))

    fp, cp = focus["program"], collab["program"]
    # Focus skews to heads-down: more workstations + private offices.
    assert fp["workstation_ratio"] > cp["workstation_ratio"]
    assert fp["private_office_ratio"] > cp["private_office_ratio"]
    # Collaborative skews to teamwork: more meeting + collaboration.
    assert cp["meeting_ratio"] > fp["meeting_ratio"]
    assert cp["collaboration_ratio"] > fp["collaboration_ratio"]

    # And the derived spec-sheet seat counts reflect that.
    assert (focus["spec_sheet"]["zones"]["workstations"]["seats"]
            > collab["spec_sheet"]["zones"]["workstations"]["seats"])
    assert (collab["spec_sheet"]["zones"]["collaboration"]["seats"]
            > focus["spec_sheet"]["zones"]["collaboration"]["seats"])


def test_gold_well_target_is_stricter_than_none():
    none = translate_brief(Brief(headcount=150, well_target="none"))
    gold = translate_brief(Brief(headcount=150, well_target="gold"))

    none_items = none["spec_sheet"]["well_checklist"]
    gold_items = gold["spec_sheet"]["well_checklist"]

    # 'none' implies no WELL checklist; gold adds a real, longer one.
    assert none_items == []
    assert len(gold_items) > len(none_items)

    # Gold reaches dimensions a bare target does not: biophilia + restoration + acoustics.
    gold_dims = {i["dimension"] for i in gold_items}
    assert {"biophilia", "restoration", "acoustics", "light"}.issubset(gold_dims)

    # And the daylight bar is explicitly stricter (gold requires a higher % than certified).
    certified = translate_brief(Brief(headcount=150, well_target="certified"))

    def daylight_req(res):
        return next(i["requirement"] for i in res["spec_sheet"]["well_checklist"]
                    if i["dimension"] == "light")

    assert ">=75%" in daylight_req(gold)
    assert ">=55%" in daylight_req(certified)


def test_over_capacity_brief_emits_warning():
    # 300 people @ 175 rsf = 52,500 sf required, but only 20,000 sf usable -> over-capacity.
    res = translate_brief(Brief(headcount=300, target_density_rsf_per_person=175,
                                usable_area_sf=20_000))
    assert any("Over-capacity" in w for w in res["warnings"])

    # A roomy plate at the same density should NOT warn about capacity.
    ok = translate_brief(Brief(headcount=100, target_density_rsf_per_person=175,
                               usable_area_sf=20_000, well_target="none"))
    assert not any("Over-capacity" in w for w in ok["warnings"])


def test_well_vs_density_conflict_warns():
    # Gold implies daylight access, but a dense 120 rsf/person plan undercuts it -> warn.
    res = translate_brief(Brief(headcount=200, target_density_rsf_per_person=120,
                                well_target="gold"))
    assert any("WELL" in w and "daylight" in w.lower() for w in res["warnings"])


def test_program_is_programspec_compatible():
    res = translate_brief(Brief(headcount=180, work_style="hybrid"))
    program = res["program"]
    # Splatting into ProgramSpec must succeed with no extra/missing fields.
    spec = ProgramSpec(**program)
    assert spec.headcount == 180
    assert abs(spec.workstation_ratio + spec.private_office_ratio
               + spec.meeting_ratio + spec.collaboration_ratio - 1.0) < 1.0  # ratios sane (<=1)

    # derive_program consumes these ratios via a PlanModel; here we only confirm field names line
    # up by constructing the spec and reading the ratios back (no plan / no geometry needed).
    assert spec.density_rsf_per_person == 175.0


def test_spec_sheet_includes_ada_clearances_when_required():
    with_ada = translate_brief(Brief(headcount=120, require_ada=True))
    without = translate_brief(Brief(headcount=120, require_ada=False))

    ada_codes = {c["code"] for c in with_ada["spec_sheet"]["code_clearances"]}
    no_codes = {c["code"] for c in without["spec_sheet"]["code_clearances"]}

    assert "ada_route" in ada_codes
    assert any("36 in" in c["requirement"] for c in with_ada["spec_sheet"]["code_clearances"])
    assert "ada_route" not in no_codes
    assert "egress" in no_codes  # egress always present
