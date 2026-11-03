import os

from omegaconf import OmegaConf

from otomai import configs


def test_parse_file__local(tmp_path: str) -> None:
    text = """
    a: 1
    b: True
    c: [3, 4]
    """
    path = os.path.join(tmp_path, "config.yml")
    with open(path, "w", encoding="utf-8") as writer:
        writer.write(text)
    config = configs.parse_file(path)
    assert config == {
        "a": 1,
        "b": True,
        "c": [3, 4],
    }, "Local file config should be loaded correctly!"


def test_parse_string() -> None:
    text = """{"a": 1, "b": 2, "data": [3, 4]}"""
    config = configs.parse_string(text)
    assert config == {
        "a": 1,
        "b": 2,
        "data": [3, 4],
    }, "String config should be loaded correctly!"


# %% MERGERS


def test_merge_configs() -> None:
    confs = [OmegaConf.create({"x": i, i: i}) for i in range(3)]
    config = configs.merge_configs(confs)
    assert config == {
        0: 0,
        1: 1,
        2: 2,
        "x": 2,
    }, "Configs should be merged correctly!"


# %% CONVERTERS


def test_to_object() -> None:
    values = {
        "a": 1,
        "b": True,
        "c": [3, 4],
    }
    config = OmegaConf.create(values)
    object_ = configs.to_object(config)
    assert object_ == values, "Object should be the same!"
    assert isinstance(object_, dict), "Object should be a dict!"


def test_environment_directory_and_injected_value_precedence(tmp_path, monkeypatch):
    monkeypatch.setenv("OTOMAI_ENV_DIR", str(tmp_path))
    monkeypatch.setenv("STRATEGY", "listing_volume_short")
    monkeypatch.setenv("ENV", "prod")
    monkeypatch.delenv("OTOMAI_TEST_SETTING", raising=False)
    monkeypatch.setenv("OTOMAI_TEST_INJECTED", "process")
    (tmp_path / "base.env").write_text("OTOMAI_TEST_SETTING=base\nOTOMAI_TEST_INJECTED=base\n")
    (tmp_path / "listing_volume_short").mkdir()
    (tmp_path / "listing_volume_short/prod.env").write_text(
        "OTOMAI_TEST_SETTING=strategy\nOTOMAI_TEST_INJECTED=file\n"
    )
    configs.load_env()
    assert os.environ["OTOMAI_TEST_SETTING"] == "strategy"
    assert os.environ["OTOMAI_TEST_INJECTED"] == "process"


def test_process_only_environment_needs_no_dotenv_file(tmp_path, monkeypatch):
    monkeypatch.setenv("OTOMAI_ENV_DIR", str(tmp_path))
    monkeypatch.setenv("OTOMAI_TEST_INJECTED", "process")
    configs.load_env()
    assert os.environ["OTOMAI_TEST_INJECTED"] == "process"
