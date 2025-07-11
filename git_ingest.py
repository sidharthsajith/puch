import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Tuple, List

__all__ = [
    "ingest_repo",
]


MAX_FILE_SIZE = 100 * 1024  # 100 KB – skip larger files to avoid bloating output
TEXT_FILE_EXTS: set[str] = {
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".json",
    ".yml",
    ".yaml",
    ".toml",
    ".ini",
    ".md",
    ".rst",
    ".txt",
    ".html",
    ".css",
    ".scss",
    ".go",
    ".rs",
    ".java",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".sh",
    ".bat",
    ".ps1",
    ".sql",
    ".kt",
    ".swift",
    ".dart",
    ".php",
}

# Binary file detection fallback – reject if NUL byte present in first 1024 bytes

def _is_probably_binary(path: Path) -> bool:
    try:
        with path.open("rb") as f:
            chunk = f.read(1024)
        return b"\0" in chunk
    except (OSError, IOError):
        return True


def _run(cmd: List[str], cwd: str | Path | None = None) -> None:
    """Run a command, raising CalledProcessError on failure."""
    result = subprocess.run(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, cmd, result.stdout, result.stderr)


def _clone_repo(url: str, tmpdir: Path) -> Path:
    """Shallow-clone *url* into *tmpdir*/repo and return that path."""
    repo_dir = tmpdir / "repo"
    _run(["git", "clone", "--depth", "1", url, str(repo_dir)])
    # Remove Git metadata to avoid accidental traversal of .git internals
    shutil.rmtree(repo_dir / ".git", ignore_errors=True)
    return repo_dir


def _gather_tree(root: Path, max_depth: int = 3, prefix: str = "") -> List[str]:
    """Return a simple text representation of the directory tree (limited depth)."""
    lines: List[str] = []
    if max_depth < 0:
        return lines
    entries = sorted(root.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    for i, entry in enumerate(entries):
        connector = "└── " if i == len(entries) - 1 else "├── "
        lines.append(f"{prefix}{connector}{entry.name}")
        if entry.is_dir():
            extension = "    " if i == len(entries) - 1 else "│   "
            lines.extend(_gather_tree(entry, max_depth - 1, prefix + extension))
    return lines


def _collect_file_content(path: Path) -> str | None:
    if path.stat().st_size > MAX_FILE_SIZE:
        return None
    if _is_probably_binary(path):
        return None
    try:
        text = path.read_text(errors="replace")
        return text
    except Exception:  # noqa: BLE001
        return None


def ingest_repo(repo_url: str) -> Tuple[str, str, str]:
    """Clone *repo_url*, traverse files and return (summary, tree, content) strings.

    This is a lightweight approximation of the \``gitingest`\` package suitable for LLM input.
    """
    with tempfile.TemporaryDirectory(prefix="git_ingest_") as tmp:
        tmpdir = Path(tmp)
        repo_path = _clone_repo(repo_url, tmpdir)

        # Build tree (depth-limited)
        tree_lines = [repo_path.name]
        tree_lines.extend(_gather_tree(repo_path))
        tree_str = "\n".join(tree_lines)

        file_count = 0
        total_bytes = 0
        contents_parts: List[str] = []

        for path in repo_path.rglob("*"):
            if path.is_file():
                rel = path.relative_to(repo_path)
                content = _collect_file_content(path)
                if content is None:
                    continue
                file_count += 1
                total_bytes += path.stat().st_size
                contents_parts.append(f"\n\n===== BEGIN {rel} =====\n{content}\n===== END {rel} =====")

        summary = (
            f"Repository: {repo_url}\n"
            f"Files included: {file_count}\n"
            f"Total bytes: {total_bytes}\n"
            f"Max per file: {MAX_FILE_SIZE}\n"
        )
        content_str = "".join(contents_parts)
        return summary, tree_str, content_str


def _main() -> None:  # pragma: no cover
    import argparse, textwrap, json  # noqa: E402

    parser = argparse.ArgumentParser(
        prog="git-ingest-lite",
        description="Generate LLM-ready digest for a public GitHub repository.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("repo", help="GitHub repository URL, e.g. https://github.com/user/repo")
    parser.add_argument("--json", action="store_true", help="Output JSON with summary, tree, content")

    args = parser.parse_args()
    summary, tree, content = ingest_repo(args.repo)

    if args.json:
        print(
            json.dumps(
                {
                    "summary": summary,
                    "tree": tree,
                    "content": content,
                },
                indent=2,
            )
        )
    else:
        print("# Summary\n" + summary + "\n\n# Tree\n" + tree + "\n\n# Content\n" + content)


if __name__ == "__main__":  # pragma: no cover
    _main()
