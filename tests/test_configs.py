import os

from otomai import configs
from omegaconf import OmegaConf


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
