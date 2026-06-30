"""Steelcase settings library + generator slotting — pure, no DWGs / DB / network.

Builds a Setting from a synthetic ExtractedLayout-shaped fixture (so it never depends on the real
application DWGs) and exercises the slotting that drops a setting's real furniture into a matching
generated room.
"""

from __future__ import annotations

from app.ingestion.schema import ExtractedLayout, FurnitureItem
from app.testfit.layout import FurnitureInstance, slot_settings
from app.testfit.settings import (
    Setting,
    SettingFurniture,
    build_setting,
    infer_setting_type,
    load_settings,
)


def _item(category, x, y, w, h, model=None, price=None) -> FurnitureItem:
    return FurnitureItem(
        category=category, block_name=f"{category}-blk", brand="Steelcase", model=model,
        x=x, y=y, w=w, h=h, rotation=0.0, list_price=price,
    )


def _layout(items: list[FurnitureItem]) -> ExtractedLayout:
    xs = [f.x for f in items] + [f.x + f.w for f in items] or [0.0]
    ys = [f.y for f in items] + [f.y + f.h for f in items] or [0.0]
    return ExtractedLayout(
        source="cad", units="ft",
        bounds=(min(xs), min(ys), max(xs), max(ys)), furniture=items,
    )


def test_build_setting_relative_pose_and_type():
    # A small private office offset from the origin — a desk + a task chair.
    layout = _layout([
        _item("desk", 10.0, 10.0, 5.0, 2.5, model="OBBORDER05", price=1200.0),
        _item("chair", 11.0, 13.0, 2.0, 2.0, model="442A40", price=1409.0),
    ])
    setting = build_setting(layout, "APL00122")

    assert setting is not None
    assert setting.id == "APL00122"
    assert setting.setting_type == "private_office"
    # footprint = furniture bbox: x 10..15, y 10..15 -> 5 x 5 = 25 sf
    assert (setting.width_ft, setting.height_ft, setting.sqft) == (5.0, 5.0, 25.0)
    # poses are RELATIVE to the bbox min-corner: the desk sits at the origin.
    desk = next(f for f in setting.furniture if f.category == "desk")
    assert (desk.dx, desk.dy) == (0.0, 0.0)
    assert desk.model == "OBBORDER05" and desk.list_price == 1200.0
    chair = next(f for f in setting.furniture if f.category == "chair")
    assert (chair.dx, chair.dy) == (1.0, 3.0)


def test_build_setting_none_without_furniture():
    assert build_setting(_layout([]), "EMPTY") is None


def test_infer_setting_type_mix():
    sofa = SettingFurniture("sofa", None, None, None, 0, 0, 6, 3, 0)
    table = SettingFurniture("table", None, None, None, 0, 0, 8, 4, 0)
    chair = SettingFurniture("chair", None, None, None, 0, 0, 2, 2, 0)
    desk = SettingFurniture("desk", None, None, None, 0, 0, 5, 2.5, 0)

    assert infer_setting_type([sofa, chair], 200) == "collaboration"
    assert infer_setting_type([table] + [chair] * 4, 240) == "meeting_room"
    assert infer_setting_type([desk, desk, chair, chair], 120) == "open"
    assert infer_setting_type([desk, chair], 90) == "private_office"


def _office_setting() -> Setting:
    return Setting(
        id="APL00122", setting_type="private_office", sqft=25.0, width_ft=5.0, height_ft=5.0,
        furniture=[
            SettingFurniture("desk", "Steelcase", "OBBORDER05", 1200.0, 0.0, 0.0, 5.0, 2.5, 0),
            SettingFurniture("chair", "Steelcase", "442A40", 1409.0, 1.0, 3.0, 2.0, 2.0, 0),
        ],
    )


def test_slotting_places_setting_into_matching_room():
    room = FurnitureInstance("private_office", x=20.0, y=30.0, w=10.0, h=12.0)
    out = slot_settings([room], [_office_setting()])

    assert room in out  # the room box is kept (metrics + outline depend on it)
    skued = [i for i in out if i.model is not None]
    assert {i.model for i in skued} == {"OBBORDER05", "442A40"}
    desk = next(i for i in skued if i.model == "OBBORDER05")
    # centred in the room: ox = room.x + (room.w - setting.w)/2 = 20 + (10-5)/2 = 22.5; oy = 33.5
    assert (desk.x, desk.y) == (22.5, 33.5)
    assert desk.type == "desk" and desk.brand == "Steelcase" and desk.list_price == 1200.0
    chair = next(i for i in skued if i.model == "442A40")
    assert (chair.x, chair.y) == (23.5, 36.5)


def test_slotting_is_noop_without_library():
    room = FurnitureInstance("private_office", x=20.0, y=30.0, w=10.0, h=12.0)
    assert slot_settings([room], []) == [room]


def test_slotting_skips_room_that_is_too_small_or_wrong_type():
    setting = _office_setting()
    too_small = FurnitureInstance("private_office", x=0.0, y=0.0, w=4.0, h=4.0)  # < 5x5 footprint
    wrong_type = FurnitureInstance("meeting_room", x=0.0, y=0.0, w=30.0, h=30.0)
    workstation = FurnitureInstance("workstation", x=0.0, y=0.0, w=30.0, h=30.0)

    out = slot_settings([too_small, wrong_type, workstation], [setting])
    assert out == [too_small, wrong_type, workstation]  # nothing added


def test_load_settings_absent_returns_empty(tmp_path):
    assert load_settings(tmp_path / "nope.json") == []


def test_save_load_round_trip(tmp_path):
    from app.testfit.settings import save_settings

    settings = [_office_setting()]
    path = save_settings(settings, tmp_path / "settings.json")
    assert load_settings(path) == settings


def test_generator_furnishes_rooms_from_settings_and_is_parametric_without():
    """Through the real generator: with a Steelcase library, each enclosed room is sized to a real
    application and furnished from it (SKU-tagged, slotted); with no library, rooms are parametric
    boxes with no furniture."""
    from app.floorplan.dxf_ingest import PlanModel
    from app.testfit.layout import ProgramSpec, generate_mixed_layout

    w, h = 140.0, 90.0
    plan = PlanModel(
        units="feet", sqft_factor=1.0,
        boundary=[(0.0, 0.0), (w, 0.0), (w, h), (0.0, h), (0.0, 0.0)],
        gross_area_sf=w * h, core_area_sf=0.0, usable_area_sf=w * h,
        columns=[], cores=[], needs_confirmation=False, notes=[],
    )
    program = ProgramSpec(headcount=40)
    # a realistic-footprint office application (within the placeable size band)
    office = Setting(
        id="APL1", setting_type="private_office", sqft=132.0, width_ft=12.0, height_ft=11.0,
        furniture=[
            SettingFurniture("desk", "Steelcase", "OBBORDER05", 1200.0, 1.0, 1.0, 5.0, 2.5, 0),
            SettingFurniture("chair", "Steelcase", "442A40", 1409.0, 5.0, 6.0, 2.0, 2.0, 0),
        ],
    )

    bare = generate_mixed_layout(plan, program=program, settings=[])
    furnished = generate_mixed_layout(plan, program=program, settings=[office])

    assert any(i.type == "private_office" for i in bare.instances)
    assert not any(i.model for i in bare.instances)  # parametric: no furniture
    placed = [i for i in furnished.instances if i.model == "OBBORDER05"]
    assert placed and all(i.slotted for i in placed)  # furnished from the application, marked slotted


def test_products_only_skud_and_alternatives_queries():
    """build_products keeps only real SKU'd furniture (drops un-spec'd sub-parts); settings_for
    fits by type+footprint; products_for filters by category."""
    from app.testfit.settings import (
        Setting, SettingFurniture, build_products, products_for, settings_for,
    )

    def sf(cat, model, price, w=2, h=2):
        return SettingFurniture(category=cat, brand="Steelcase" if model else None, model=model,
                                list_price=price, dx=0, dy=0, w=w, h=h, rotation=0)

    office = Setting(id="o", setting_type="private_office", sqft=120, width_ft=10, height_ft=12,
                     furniture=[sf("desk", "DSK1", 900), sf("chair", "CH1", 500),
                                sf("other", None, None)])  # sub-part, no SKU
    big = Setting(id="b", setting_type="private_office", sqft=300, width_ft=15, height_ft=20,
                  furniture=[sf("desk", "DSK2", 1100)])
    products = build_products([office, big])

    assert all(p.model for p in products)  # no un-spec'd sub-parts
    assert {p.model for p in products} == {"DSK1", "CH1", "DSK2"}

    fits = settings_for([office, big], "private_office", max_w=12, max_h=14)
    assert [s.id for s in fits] == ["o"]  # the 15x20 'big' doesn't fit a 12x14 room

    chairs = products_for(products, "chair")
    assert len(chairs) == 1 and chairs[0].model == "CH1"


def test_symbol_outline_missing_sku_is_none():
    """A SKU with no product model resolves to None (caller falls back to footprint) — never errors."""
    from app.testfit.settings import symbol_outline

    assert symbol_outline("__no_such_sku__") is None


def test_resolve_symbol_matches_base_and_variant(monkeypatch):
    """A configured CET part number resolves to the base symbol (trailing options trimmed) or to a
    variant that extends it — but never to an unrelated product (>= 6 shared chars required)."""
    from pathlib import Path

    from app.testfit import settings as S

    idx = {
        "COTO96": Path("coto96.dxf"),       # base symbol
        "419A000B2": Path("419.dxf"),       # configured variant in the library
        "COWK1": Path("cowk1.dxf"),         # too-short base (5 chars)
    }
    monkeypatch.setattr(S, "_symbol_paths", idx)
    monkeypatch.setattr(S, "_symbol_keys", None)

    assert S._resolve_symbol("COTO96") == idx["COTO96"]          # exact
    assert S._resolve_symbol("COTO96WB15") == idx["COTO96"]      # part extends base -> base
    assert S._resolve_symbol("419A000") == idx["419A000B2"]      # library variant extends the part
    assert S._resolve_symbol("COWK100") is None                  # COWK1 too short -> no risky match
    assert S._resolve_symbol("UNRELATED9") is None
