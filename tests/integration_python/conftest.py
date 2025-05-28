from pathlib import Path

import pytest
import dotenv
import os

from .common import exec_extension


@pytest.fixture(scope="session", autouse=True)
def load_dotenv() -> None:
    dotenv.load_dotenv()


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--pixi-build",
        action="store",
        default="release",
        help="Specify the pixi build type (e.g., release or debug)",
    )


@pytest.fixture
def pixi() -> Path:
    """
    Returns the path to the Pixi executable.

    Uses the PIXI_BIN_DIR environment variable to locate the Pixi directory.
    Locally, this is typically done via the .env file.
    """
    pixi_bin_dir = os.getenv("PIXI_BIN_DIR")
    if not pixi_bin_dir:
        raise ValueError(
            "PIXI_BIN_DIR environment variable is not set. "
            "Please set it to the directory containing the Pixi executable."
        )

    pixi_bin_path = Path(pixi_bin_dir)
    if not pixi_bin_path.is_dir():
        raise ValueError(
            f"PIXI_BIN_DIR points to '{pixi_bin_dir}' which is not a valid directory. "
            "Please set it to a directory that exists and contains the Pixi executable."
        )

    pixi_executable = pixi_bin_path / exec_extension("pixi")

    if not pixi_executable.is_file():
        raise FileNotFoundError(f"Pixi executable not found at '{pixi_executable}'.")

    return pixi_executable


@pytest.fixture(scope="session", autouse=True)
def build_backends() -> None:
    """
    Sets up build backend environment variables for testing.

    Configures PIXI_BUILD_BACKEND_OVERRIDE environment variable with paths
    to the build backends.

    Requires the BUILD_BACKENDS_BIN_DIR environment variable to be set.
    Locally, this is typically done via the .env file.
    """
    build_backends_dir = os.getenv("BUILD_BACKENDS_BIN_DIR")

    if not build_backends_dir:
        raise ValueError(
            "BUILD_BACKENDS_BIN_DIR environment variable is not set. "
            "Please set it to a directory that contains build backend definitions."
        )

    build_backends_path = Path(build_backends_dir)
    if not build_backends_path.is_dir():
        raise ValueError(
            f"BUILD_BACKENDS_BIN_DIR points to '{build_backends_dir}' which is not a valid directory. "
            "Please set it to a directory that exists and contains build backend definitions."
        )

    # Define the build backends
    backends = [
        "pixi-build-cmake",
        "pixi-build-python",
        "pixi-build-rattler-build",
        "pixi-build-rust",
    ]

    # Build the override string in the format: tool_name=/path/to/executable::tool_name2=...
    override_parts = []
    for backend in backends:
        backend_path = build_backends_path / exec_extension(backend)
        if not backend_path.is_file():
            raise FileNotFoundError(f"'{backend}' not found at '{backend_path}'.")

        override_parts.append(f"{backend}={backend_path}")

    override_value = "::".join(override_parts)
    os.environ["PIXI_BUILD_BACKEND_OVERRIDE"] = override_value


@pytest.fixture
def tmp_pixi_workspace(tmp_path: Path) -> Path:
    pixi_config = """
# Reset to defaults
default-channels = ["conda-forge"]
shell.change-ps1 = true
tls-no-verify = false
detached-environments = false
pinning-strategy = "semver"

[concurrency]
downloads = 50

[experimental]
use-environment-activation-cache = false

# Enable sharded repodata
[repodata-config."https://prefix.dev/"]
disable-sharded = false
"""
    dot_pixi = tmp_path.joinpath(".pixi")
    dot_pixi.mkdir()
    dot_pixi.joinpath("config.toml").write_text(pixi_config)
    return tmp_path


@pytest.fixture
def test_data() -> Path:
    return Path(__file__).parents[1].joinpath("data").resolve()


@pytest.fixture
def pypi_data(test_data: Path) -> Path:
    """
    Returns the pixi pypi test data
    """
    return test_data.joinpath("pypi")


@pytest.fixture
def pixi_tomls(test_data: Path) -> Path:
    """
    Returns the pixi pypi test data
    """
    return test_data.joinpath("pixi_tomls")


@pytest.fixture
def mock_projects(test_data: Path) -> Path:
    return test_data.joinpath("mock-projects")


@pytest.fixture
def channels(test_data: Path) -> Path:
    return test_data.joinpath("channels", "channels")


@pytest.fixture
def dummy_channel_1(channels: Path) -> str:
    return channels.joinpath("dummy_channel_1").as_uri()


@pytest.fixture
def dummy_channel_2(channels: Path) -> str:
    return channels.joinpath("dummy_channel_2").as_uri()


@pytest.fixture
def multiple_versions_channel_1(channels: Path) -> str:
    return channels.joinpath("multiple_versions_channel_1").as_uri()


@pytest.fixture
def non_self_expose_channel_1(channels: Path) -> str:
    return channels.joinpath("non_self_expose_channel_1").as_uri()


@pytest.fixture
def non_self_expose_channel_2(channels: Path) -> str:
    return channels.joinpath("non_self_expose_channel_2").as_uri()


@pytest.fixture
def virtual_packages_channel(channels: Path) -> str:
    return channels.joinpath("virtual_packages").as_uri()


@pytest.fixture
def shortcuts_channel_1(channels: Path) -> str:
    return channels.joinpath("shortcuts_channel_1").as_uri()


@pytest.fixture
def post_link_script_channel(channels: Path) -> str:
    return channels.joinpath("post_link_script_channel").as_uri()


@pytest.fixture
def deno_channel(channels: Path) -> str:
    return channels.joinpath("deno_channel").as_uri()


@pytest.fixture
def completions_channel_1(channels: Path) -> str:
    return channels.joinpath("completions_channel_1").as_uri()
