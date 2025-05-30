"""
Download pixi binary from the prefix-dev/pixi GitHub repository.

This script downloads the latest pixi binary artifact from the CI workflow
and extracts it to the specified directory.
"""

import argparse
import os
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

import requests
from github import Github
from rich.console import Console
from rich.progress import track

console = Console()


def download_pixi_binary(
    github_token: Optional[str] = None,
    output_dir: Optional[str] = None,
    platform: str = "linux-x86_64",
    branch: str = "main",
) -> bool:
    """
    Download the pixi binary from GitHub Actions artifacts.

    Args:
        github_token: GitHub token for authentication (optional)
        output_dir: Directory to save the binary (defaults to ./pixi_home/bin)
        platform: Platform to download (linux-x86_64, windows-x86_64, macos-aarch64)
        branch: Branch to download from (default: main)

    Returns:
        True if successful, False otherwise
    """
    try:
        # Initialize GitHub client
        g = Github(github_token) if github_token else Github()

        # Get the repository
        repo = g.get_repo("prefix-dev/pixi")
        console.print(f"[green]Connected to repository: {repo.full_name}")

        # Get the latest workflow run for the CI workflow on the specified branch
        workflows = repo.get_workflows()
        ci_workflow = None
        for workflow in workflows:
            if workflow.name == "CI" or workflow.path == ".github/workflows/CI.yml":
                ci_workflow = workflow
                break

        if not ci_workflow:
            console.print("[red]Could not find CI workflow")
            return False

        console.print(f"[blue]Found CI workflow: {ci_workflow.name}")

        # Get successful workflow runs from the specified branch
        runs = ci_workflow.get_runs(branch=branch, status="completed")

        latest_run = None
        for run in runs:
            latest_run = run
            break

        if not latest_run:
            console.print(f"[red]No successful workflow runs found on branch '{branch}'")
            return False

        console.print(f"[blue]Latest successful run: {latest_run.id} from {latest_run.created_at}")

        # Get artifacts for this run
        artifacts = latest_run.get_artifacts()

        # Find the artifact for our platform
        target_artifact = None
        artifact_name_pattern = f"pixi-{platform}"

        for artifact in artifacts:
            if artifact_name_pattern in artifact.name:
                target_artifact = artifact
                break

        if not target_artifact:
            console.print(
                f"[red]Could not find artifact matching pattern '{artifact_name_pattern}'"
            )
            console.print("[yellow]Available artifacts:")
            for artifact in artifacts:
                console.print(f"  - {artifact.name}")
            return False

        console.print(f"[green]Found artifact: {target_artifact.name}")

        # Set up output directory
        if output_dir is None:
            output_dir = Path.cwd() / "pixi_home" / "bin"
        else:
            output_dir = Path(output_dir)

        output_dir.mkdir(parents=True, exist_ok=True)
        console.print(f"[blue]Output directory: {output_dir}")

        # Download the artifact
        console.print("[blue]Downloading artifact...")
        download_url = target_artifact.archive_download_url

        # We need to use the GitHub API with authentication to download
        headers = {}
        if github_token:
            headers["Authorization"] = f"token {github_token}"

        response = requests.get(download_url, headers=headers, stream=True)
        response.raise_for_status()

        # Save to temporary file and extract
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as temp_file:
            total_size = int(response.headers.get("content-length", 0))

            if total_size > 0:
                for chunk in track(
                    response.iter_content(chunk_size=8192),
                    total=total_size // 8192,
                    description="Downloading...",
                ):
                    temp_file.write(chunk)
            else:
                for chunk in response.iter_content(chunk_size=8192):
                    temp_file.write(chunk)

            temp_zip_path = temp_file.name

        console.print("[blue]Extracting binary...")

        # Extract the zip file
        with zipfile.ZipFile(temp_zip_path, "r") as zip_ref:
            # List contents
            file_list = zip_ref.namelist()
            console.print(f"[blue]Archive contents: {file_list}")

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
                return False

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

        # Clean up temporary file
        os.unlink(temp_zip_path)

        # Verify the binary works
        console.print("[blue]Verifying binary...")
        import subprocess

        try:
            result = subprocess.run(
                [str(final_path), "--version"], capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                console.print(f"[green]✓ Binary verification successful: {result.stdout.strip()}")
            else:
                console.print(f"[yellow]⚠ Binary returned non-zero exit code: {result.returncode}")
        except Exception as e:
            console.print(f"[yellow]⚠ Could not verify binary: {e}")

        return True

    except Exception as e:
        console.print(f"[red]Error downloading pixi binary: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Download pixi binary from GitHub Actions")
    parser.add_argument(
        "--token", help="GitHub token for authentication (can also use GITHUB_TOKEN env var)"
    )
    parser.add_argument(
        "--output-dir", help="Directory to save the binary (default: ./pixi_home/bin)"
    )
    parser.add_argument(
        "--platform",
        default="linux-x86_64",
        choices=["linux-x86_64", "windows-x86_64", "macos-aarch64"],
        help="Platform to download (default: linux-x86_64)",
    )
    parser.add_argument("--branch", default="main", help="Branch to download from (default: main)")

    args = parser.parse_args()

    # Get GitHub token from argument or environment
    github_token = args.token or os.getenv("GITHUB_TOKEN")
    if not github_token:
        console.print("[yellow]⚠ No GitHub token provided. Rate limits may apply.")
        console.print("[yellow]  Set GITHUB_TOKEN environment variable or use --token argument")

    success = download_pixi_binary(
        github_token=github_token,
        output_dir=args.output_dir,
        platform=args.platform,
        branch=args.branch,
    )

    if success:
        console.print("[green]✓ Download completed successfully!")
        sys.exit(0)
    else:
        console.print("[red]✗ Download failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
