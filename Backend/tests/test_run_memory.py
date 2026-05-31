from __future__ import annotations

from app.services.run_memory import _infer_tag, _is_persistable_hypothesis


def test_infer_tag_does_not_treat_plain_texture_mentions_as_visual_glitches() -> None:
    assert _infer_tag("The red-textured corridor leads to a Demon encounter.") == "ENCOUNTER_HOTSPOT"
    assert _infer_tag("Confirmed missing texture on north wall.") == "VISUAL_GLITCH"


def test_persistable_hypothesis_requires_confirmed_evidence() -> None:
    assert _is_persistable_hypothesis("Confirmed blocked after three USE probes at the blue door.") is True
    assert _is_persistable_hypothesis("Red-textured corridor appears to be the next route.") is False
