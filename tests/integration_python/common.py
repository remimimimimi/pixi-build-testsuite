import os
import platform
import re
import shutil
import subprocess
from contextlib import contextmanager
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Any, Generator

import tomli_w
import yaml
from rattler import Platform

PIXI_VERSION = "0.47.0"


ALL_PLATFORMS = '["linux-64", "osx-64", "osx-arm64", "win-64", "linux-ppc64le", "linux-aarch64"]'

CURRENT_PLATFORM = str(Platform.current())

EMPTY_BOILERPLATE_PROJECT = f"""
[workspace]
name = "test"
channels = []
platforms = ["{CURRENT_PLATFORM}"]
"""

REMOTE_BACKEND_CHANNEL = "https://prefix.dev/pixi-build-backends"
_TEXT_FILE_SUFFIXES = {".toml", ".lock", ".yaml", ".yml", ".json"}
_LOCAL_BACKEND_CHANNEL_URI: str | None = None


def set_local_backend_channel(uri: str | None) -> None:
    global _LOCAL_BACKEND_CHANNEL_URI
    _LOCAL_BACKEND_CHANNEL_URI = uri


def get_local_backend_channel() -> str | None:
    return _LOCAL_BACKEND_CHANNEL_URI


def _channel_replacements(local_uri: str) -> dict[str, str]:
    normalized = local_uri.rstrip("/")
    return {
        REMOTE_BACKEND_CHANNEL: normalized,
        f"{REMOTE_BACKEND_CHANNEL}/": f"{normalized}/",
    }


def rewrite_backend_channels(root: Path, local_uri: str) -> None:
    replacements = _channel_replacements(local_uri)
    for file_path in root.rglob("*"):
        if not file_path.is_file():
            continue
        if file_path.suffix not in _TEXT_FILE_SUFFIXES:
            continue
        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        updated = content
        for source, target in replacements.items():
            updated = updated.replace(source, target)
        if updated != content:
            file_path.write_text(updated, encoding="utf-8")


def copy_manifest(
    src: str | os.PathLike[str],
    dst: str | os.PathLike[str],
    *,
    follow_symlinks: bool = True,
) -> str:
    copied_path = shutil.copy(src, dst, follow_symlinks=follow_symlinks)
    copied_str = str(copied_path)
    local_uri = _LOCAL_BACKEND_CHANNEL_URI
    if local_uri is None:
        return copied_str

    path = Path(copied_str)
    if path.suffix not in _TEXT_FILE_SUFFIXES or not path.is_file():
        return copied_str

    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return copied_str

    replacements = _channel_replacements(local_uri)
    updated = content
    for source, target in replacements.items():
        updated = updated.replace(source, target)

    if updated != content:
        path.write_text(updated, encoding="utf-8")

    return copied_str


def copytree_with_local_backend(
    src: str | os.PathLike[str],
    dst: str | os.PathLike[str],
    **kwargs: Any,
) -> str:
    kwargs.setdefault("copy_function", copy_manifest)
    copied_tree = shutil.copytree(src, dst, **kwargs)
    return str(copied_tree)


@dataclass
class Workspace:
    recipe: dict[str, Any]
    workspace_manifest: dict[str, Any]
    workspace_dir: Path
    package_manifest: dict[str, Any]
    package_dir: Path
    recipe_path: Path
    debug_dir: Path

    def write_files(self) -> None:
        self.recipe_path.write_text(yaml.dump(self.recipe))
        workspace_manifest_path = self.workspace_dir.joinpath("pixi.toml")
        workspace_manifest_path.write_text(tomli_w.dumps(self.workspace_manifest))
        package_manifest_path = self.package_dir.joinpath("pixi.toml")
        package_manifest_path.write_text(tomli_w.dumps(self.package_manifest))


class ExitCode(IntEnum):
    SUCCESS = 0
    FAILURE = 1
    INCORRECT_USAGE = 2
    COMMAND_NOT_FOUND = 127


class Output:
    command: list[Path | str]
    stdout: str
    stderr: str
    returncode: int

    def __init__(self, command: list[Path | str], stdout: str, stderr: str, returncode: int):
        self.command = command
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode

    def __str__(self) -> str:
        return f"command: {self.command}"


def verify_cli_command(
    command: list[Path | str],
    expected_exit_code: ExitCode = ExitCode.SUCCESS,
    stdout_contains: str | list[str] | None = None,
    stdout_excludes: str | list[str] | None = None,
    stderr_contains: str | list[str] | None = None,
    stderr_excludes: str | list[str] | None = None,
    env: dict[str, str] | None = None,
    cwd: str | Path | None = None,
    reset_env: bool = False,
    strip_ansi: bool = False,
) -> Output:
    base_env = {} if reset_env else dict(os.environ)
    complete_env = base_env if env is None else base_env | env
    # Set `PIXI_NO_WRAP` to avoid to have miette wrapping lines
    complete_env |= {"PIXI_NO_WRAP": "1"}

    process = subprocess.run(
        command,
        capture_output=True,
        env=complete_env,
        cwd=cwd,
    )
    # Decode stdout and stderr explicitly using UTF-8
    stdout = process.stdout.decode("utf-8", errors="replace")
    stderr = process.stderr.decode("utf-8", errors="replace")

    if strip_ansi:
        # sanitise coloured output to match plain strings
        ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
        stdout = ansi_escape.sub("", stdout)
        stderr = ansi_escape.sub("", stderr)

    returncode = process.returncode
    output = Output(command, stdout, stderr, returncode)
    print(f"command: {command}, stdout: {stdout}, stderr: {stderr}, code: {returncode}")
    assert returncode == expected_exit_code, (
        f"Return code was {returncode}, expected {expected_exit_code}, stderr: {stderr}"
    )

    if stdout_contains:
        if isinstance(stdout_contains, str):
            stdout_contains = [stdout_contains]
        for substring in stdout_contains:
            assert substring in stdout, f"'{substring}'\n not found in stdout:\n {stdout}"

    if stdout_excludes:
        if isinstance(stdout_excludes, str):
            stdout_excludes = [stdout_excludes]
        for substring in stdout_excludes:
            assert substring not in stdout, (
                f"'{substring}'\n unexpectedly found in stdout:\n {stdout}"
            )

    if stderr_contains:
        if isinstance(stderr_contains, str):
            stderr_contains = [stderr_contains]
        for substring in stderr_contains:
            assert substring in stderr, f"'{substring}'\n not found in stderr:\n {stderr}"

    if stderr_excludes:
        if isinstance(stderr_excludes, str):
            stderr_excludes = [stderr_excludes]
        for substring in stderr_excludes:
            assert substring not in stderr, (
                f"'{substring}'\n unexpectedly found in stderr:\n {stderr}"
            )

    return output


def bat_extension(exe_name: str) -> str:
    if platform.system() == "Windows":
        return exe_name + ".bat"
    else:
        return exe_name


def exec_extension(exe_name: str) -> str:
    if platform.system() == "Windows":
        return exe_name + ".exe"
    else:
        return exe_name


def is_binary(path: Path) -> bool:
    textchars = bytearray({7, 8, 9, 10, 12, 13, 27} | set(range(0x20, 0x100)) - {0x7F})
    with open(path, "rb") as f:
        return bool(f.read(2048).translate(None, bytes(textchars)))


def pixi_dir(project_root: Path) -> Path:
    return project_root.joinpath(".pixi")


def default_env_path(project_root: Path) -> Path:
    return pixi_dir(project_root).joinpath("envs", "default")


def repo_root() -> Path:
    return Path(__file__).parents[2]


def current_platform() -> str:
    return str(Platform.current())


def get_manifest(directory: Path) -> Path:
    pixi_toml = directory / "pixi.toml"
    pyproject_toml = directory / "pyproject.toml"

    if pixi_toml.exists():
        return pixi_toml
    elif pyproject_toml.exists():
        return pyproject_toml
    else:
        raise ValueError("Neither pixi.toml nor pyproject.toml found")


@contextmanager
def cwd(path: str | Path) -> Generator[None, None, None]:
    oldpwd = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(oldpwd)


def git_test_repo(source_dir: Path, repo_name: str, target_dir: Path) -> str:
    """Create a git repository from the source directory in a target directory."""
    repo_path: Path = target_dir / repo_name

    # Copy source directory to temp
    copytree_with_local_backend(source_dir, repo_path, copy_function=copy_manifest)

    # Initialize git repository in the copied source
    subprocess.run(
        ["git", "init"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    # Add all files and commit
    subprocess.run(
        ["git", "add", "."],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "bot@prefix.dev"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Bot"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "--message", "Initial commit"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    return f"file://{repo_path}"
