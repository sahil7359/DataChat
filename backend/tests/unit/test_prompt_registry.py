from app.application.prompts.registry import PROMPT_VERSIONS


def test_registry_catalogs_the_request_path_prompts() -> None:
    assert set(PROMPT_VERSIONS) == {
        "sql_generation",
        "explanation",
        "clarify",
        "faithfulness_judge",
    }


def test_versions_are_stable_identifiers() -> None:
    for name, version in PROMPT_VERSIONS.items():
        assert "@v" in version, f"{name} version should be pinned: {version}"
