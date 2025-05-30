import argparse
import os
import platform
import sys
import tempfile
import zipfile
from pathlib import Path

import httpx
from github import Github
from rich.console import Console
from rich.progress import track

console = Console()


def get_current_platform() -> str:
    """Get the current platform string for artifact naming."""
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "linux":
        if machine in ["x86_64", "amd64"]:
            return "linux-x86_64"
        elif machine in ["aarch64", "arm64"]:
            return "linux-aarch64"
    elif system == "darwin":
        if machine in ["arm64", "aarch64"]:
            return "macos-aarch64"
        elif machine in ["x86_64", "amd64"]:
            return "macos-x86_64"
    elif system == "windows":
        if machine in ["x86_64", "amd64"]:
            return "windows-x86_64"

    raise ValueError(f"Unsupported platform: {system}-{machine}")


def get_conda_target() -> str:
    """Get the conda target string for conda package artifacts."""
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "linux":
        if machine in ["x86_64", "amd64"]:
            return "linux-64"
        elif machine in ["aarch64", "arm64"]:
            return "linux-aarch64"
        elif machine in ["ppc64le"]:
            return "linux-ppc64le"
    elif system == "darwin":
        if machine in ["arm64", "aarch64"]:
            return "osx-arm64"
        elif machine in ["x86_64", "amd64"]:
            return "osx-64"
    elif system == "windows":
        if machine in ["x86_64", "amd64"]:
            return "win-64"

    raise ValueError(f"Unsupported platform: {system}-{machine}")


def download_and_extract_artifact(
    target_artifact, github_token: str | None, output_dir: Path, artifact_type: str = "pixi"
) -> None:
    """Download and extract artifact, return path to extracted binary."""
    # Download the artifact
    console.print("[blue]Downloading artifact...")
    download_url = target_artifact.archive_download_url

    # Use httpx to download with authentication and follow redirects
    headers = {}
    if github_token:
        headers["Authorization"] = f"token {github_token}"

    with httpx.stream(
        "GET", download_url, headers=headers, follow_redirects=True, timeout=30.0
    ) as response:
        response.raise_for_status()

        # Save to temporary file and extract
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as temp_file:
            total_size = int(response.headers.get("content-length", 0))

            if total_size > 0:
                for chunk in track(
                    response.iter_bytes(chunk_size=8192),
                    total=total_size // 8192,
                    description="Downloading...",
                ):
                    temp_file.write(chunk)
            else:
                for chunk in response.iter_bytes(chunk_size=8192):
                    temp_file.write(chunk)

            temp_zip_path = temp_file.name

    console.print("[blue]Extracting artifact...")

    # Extract the zip file
    with zipfile.ZipFile(temp_zip_path, "r") as zip_ref:
        # List contents
        file_list = zip_ref.namelist()
        console.print(f"[blue]Archive contents: {file_list}")

        if artifact_type == "pixi":
            # Find the pixi binary
            pixi_binary = None
            for file_name in file_list:
                if (
                    file_name == "pixi"
                    or file_name.endswith("/pixi")
                    or file_name.endswith("pixi.exe")
                ):
                    pixi_binary = file_name
                    break

            if not pixi_binary:
                console.print("[red]Could not find pixi binary in archive")
                raise FileNotFoundError(
                    f"Could not find pixi binary in archive. Archive contents: {file_list}"
                )

            # Extract the binary
            zip_ref.extract(pixi_binary, output_dir)

            # Move to correct location if it was in a subdirectory
            extracted_path = output_dir / pixi_binary
            final_path = output_dir / Path(pixi_binary).name

            if extracted_path != final_path:
                extracted_path.rename(final_path)

            # Make executable on Unix systems
            if not sys.platform.startswith("win"):
                final_path.chmod(0o755)

            console.print(f"[green]Successfully downloaded pixi binary to: {final_path}")

        elif artifact_type == "conda":
            # Extract all conda packages
            conda_files = [f for f in file_list if f.endswith(".conda")]

            if not conda_files:
                console.print("[red]Could not find any .conda files in archive")
                raise FileNotFoundError(
                    f"Could not find any .conda files in archive. Archive contents: {file_list}"
                )

            console.print(f"[blue]Found {len(conda_files)} conda package(s)")

            # Extract all conda files
            for conda_file in conda_files:
                zip_ref.extract(conda_file, output_dir)
                extracted_path = output_dir / conda_file
                final_path = output_dir / Path(conda_file).name

                if extracted_path != final_path:
                    extracted_path.rename(final_path)

                console.print(f"[green]Extracted conda package: {final_path}")

        else:
            raise ValueError(f"Unsupported artifact type: {artifact_type}")

    # Clean up temporary file
    os.unlink(temp_zip_path)


def download_github_artifact(
    github_token: str | None,
    output_dir: str,
    repo: str,
    workflow: str,
    run_id: int | None = None,
    artifact_type: str = "pixi",
) -> None:
    # Get current platform
    if artifact_type == "pixi":
        current_platform = get_current_platform()
        console.print(f"[blue]Detected platform: {current_platform}")
    elif artifact_type == "conda":
        current_platform = get_conda_target()
        console.print(f"[blue]Detected conda target: {current_platform}")
    else:
        raise ValueError(f"Unsupported artifact type: {artifact_type}")

    # Initialize GitHub client
    gh = Github(github_token)

    # Get the repository
    repository = gh.get_repo(repo)
    console.print(f"[green]Connected to repository: {repository.full_name}")

    # Get the workflow run
    if run_id:
        # Use specific run ID - no need to find workflow first
        console.print(f"[blue]Using specified run ID: {run_id}")
        latest_run = repository.get_workflow_run(run_id)
        if latest_run.conclusion != "success":
            console.print(
                f"[yellow]Warning: Run {run_id} did not complete successfully (status: {latest_run.conclusion})"
            )

    else:
        # Get the latest workflow run for the specified workflow
        workflows = repository.get_workflows()
        target_workflow = None
        for wf in workflows:
            if wf.name == workflow:
                target_workflow = wf
                break

        if not target_workflow:
            console.print(f"[red]Could not find workflow: {workflow}")
            raise ValueError(f"Could not find workflow: {workflow}")

        console.print(f"[blue]Found workflow: {target_workflow.name}")

        # Get latest successful workflow run from main branch
        console.print("[blue]Finding latest successful workflow run from main branch")
        runs = target_workflow.get_runs(branch="main", status="completed")

        latest_run = None
        for run in runs:
            if run.conclusion == "success":
                latest_run = run
                break

        if not latest_run:
            console.print("[red]No successful workflow runs found on main branch")
            raise ValueError("No successful workflow runs found on main branch")

    console.print(f"[blue]Latest successful run: {latest_run.id} from {latest_run.created_at}")

    # Get artifacts for this run
    artifacts = latest_run.get_artifacts()

    # Find the artifact for our platform
    target_artifact = None
    if artifact_type == "pixi":
        artifact_name_pattern = f"pixi-{current_platform}"
    elif artifact_type == "conda":
        artifact_name_pattern = f"conda-packages-{current_platform}"
    else:
        raise ValueError(f"Unsupported artifact type: {artifact_type}")

    for artifact in artifacts:
        if artifact_name_pattern in artifact.name:
            target_artifact = artifact
            break

    if not target_artifact:
        console.print(f"[red]Could not find artifact matching pattern '{artifact_name_pattern}'")
        console.print("[yellow]Available artifacts:")
        available_artifacts = [artifact.name for artifact in artifacts]
        for artifact in artifacts:
            console.print(f"  - {artifact.name}")
        raise FileNotFoundError(
            f"Could not find artifact matching pattern '{artifact_name_pattern}'. "
            f"Available artifacts: {available_artifacts}"
        )

    console.print(f"[green]Found artifact: {target_artifact.name}")

    # Set up output directory
    if output_dir is None:
        if artifact_type == "pixi":
            output_dir = Path.cwd() / "pixi_home" / "bin"
        elif artifact_type == "conda":
            output_dir = Path.cwd() / "conda_packages"
        else:
            output_dir = Path.cwd() / "downloads"
    else:
        output_dir = Path(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)
    console.print(f"[blue]Output directory: {output_dir}")

    # Download and extract the artifact
    download_and_extract_artifact(target_artifact, github_token, output_dir, artifact_type)


def main():
    parser = argparse.ArgumentParser(description="Download artifacts from GitHub Actions")
    parser.add_argument(
        "--token",
        help="GitHub token for authentication (can also use GITHUB_TOKEN env var)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Directory to save the artifacts (default depends on artifact type)",
    )
    parser.add_argument(
        "--run-id",
        type=int,
        help="Specific workflow run ID to download from (optional)",
    )
    parser.add_argument(
        "artifact_type",
        choices=["pixi", "conda"],
        help="Type of artifact to download: 'pixi' for pixi binaries or 'conda' for conda packages",
    )

    args = parser.parse_args()

    # Set repo and workflow based on artifact type
    if args.artifact_type == "pixi":
        repo = "prefix-dev/pixi"
        workflow = "CI"
    elif args.artifact_type == "conda":
        repo = "prefix-dev/pixi-build-backends"
        workflow = "Conda Packages"

    # Get GitHub token from argument or environment
    github_token = args.token or os.getenv("GITHUB_TOKEN")
    if not github_token:
        console.print("[red]✗ No GitHub token provided")
        console.print("[red]  Set GITHUB_TOKEN environment variable or use --token argument")
        sys.exit()

    try:
        download_github_artifact(
            github_token, args.output_dir, repo, workflow, args.run_id, args.artifact_type
        )
        console.print("[green]✓ Download completed successfully!")
        sys.exit(0)
    except Exception as e:
        console.print(f"[red]✗ Download failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
