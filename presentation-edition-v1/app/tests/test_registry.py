"""Registry sanity: unique ids, and every override merges into a valid Settings."""
import pytest

from ftlink_app import runner
from ftlink_app.registry import SCENARIOS, get


def test_ids_unique():
    ids = [s.id for s in SCENARIOS]
    assert len(ids) == len(set(ids))


def test_get_unknown_raises():
    with pytest.raises(KeyError):
        get("nope")


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.id)
def test_overrides_build_valid_settings(scenario):
    from ftlink.config import Settings

    merged = runner.build_settings_dict(scenario)
    settings = Settings(**merged)
    # the override must actually land in the settings object
    if scenario.id == "strict-linker":
        assert settings.linking.accept_threshold == 0.8
    if scenario.id == "no-percent-rescue":
        assert settings.ocr.percent_rescue is False
    if scenario.id == "footnote-12":
        assert settings.document.footnote_no == 12
    if scenario.id == "fallback-calibration":
        assert settings.confidence.extra_control_pages == []
    if scenario.id == "llm-tier":
        assert settings.linking.llm.enabled is True
    if scenario.id == "lenient-lexical":
        assert settings.linking.lexical_threshold == 0.4
    if scenario.id == "psm-6":
        assert settings.ocr.psm == 6
    if scenario.id == "dense-swap":
        assert "paraphrase" in settings.candidates.dense_model
        assert settings.candidates.dense_model_revision != \
            "614241f622f53c4eeff9890bdc4f31cfecc418b3"
    if scenario.id == "footnote-10":
        assert settings.document.footnote_no == 10


def test_output_dirs_disjoint_from_deliverable():
    from ftlink_app.paths import deliverable_root

    droot = str(deliverable_root())
    for s in SCENARIOS:
        merged = runner.build_settings_dict(s)
        assert not str(merged["output"]["dir"]).startswith(droot)


def test_reranker_swap_scenario_points_at_turkish_model():
    """The 29.08 model-swap scenario: only the cross-encoder moves (id + pinned revision), the
    dense channel and every threshold stay shipped, and the merged config is a valid Settings."""
    from ftlink.config import Settings

    scenario = get("reranker-tr-modernbert")
    settings = Settings(**runner.build_settings_dict(scenario))
    assert settings.linking.cross_encoder_model == "ytu-ce-cosmos/modernbert-tr-reranker"
    assert settings.linking.cross_encoder_revision == "d6aabbe061f1bf6cb796e317ecb6d9b8f7b96c54"
    assert settings.candidates.dense_model == "intfloat/multilingual-e5-small"
    assert settings.linking.accept_threshold == 0.5
    assert scenario.group == "linking" and scenario.precompute and scenario.eval_applicable
