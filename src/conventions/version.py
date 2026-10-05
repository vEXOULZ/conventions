"""`conventions version`: a repo's own version, wherever it is written, and the next one.

A version lives in more than one file, and they have to agree:

- **Python:** `version` in `[project]` of the root `pyproject.toml`, the root project's entry in
  `uv.lock`, and a `__version__ = "..."` line in the package's `__init__.py` (`src/<name>/` or `<name>/`)
  when there is one. Workspace members keep their own versions and are left alone.
- **Node:** `version` in `package.json`, and at the top of `package-lock.json` and in its `packages[""]`.

A repo with neither (a docs repo) has no version, and every check here passes for it.

In a `flow = "dev"` repo a pull request into `main` is a release. Its version must be above the one on
`main`, and its tag must not exist yet, so the tag that follows the merge always matches the package.
"""

from __future__ import annotations

import json
import re
import subprocess
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from conventions.config import Config

SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
BUMPS = ("auto", "patch", "minor", "major")

# `type(scope)!: subject`, the Conventional Commits header.
_HEADER_RE = re.compile(r"^(?P<type>\w+)(?:\([^)]*\))?(?P<bang>!)?:")
_PYPROJECT_VERSION_RE = re.compile(r'^(version\s*=\s*)"([^"]*)"', re.M)
_DUNDER_RE = re.compile(r'^(__version__\s*=\s*)"([^"]*)"', re.M)
_JSON_VERSION_RE = re.compile(r'("version"\s*:\s*)"([^"]*)"')


class VersionError(Exception):
    pass


Semver = tuple[int, int, int]


def parse(text: str) -> Semver:
    m = SEMVER_RE.match(text.removeprefix("v"))
    if not m:
        raise VersionError(f"{text!r} is not a version like 1.2.3")
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def fmt(v: Semver) -> str:
    return f"{v[0]}.{v[1]}.{v[2]}"


@dataclass
class Source:
    """One place a version is written: a file, and what the version there is."""

    path: str
    label: str
    value: str


# --- reading -----------------------------------------------------------------------------------------


def _normalise_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _project_table(text: str) -> tuple[int, int]:
    """Start and end offsets of the `[project]` table in a pyproject.toml."""
    m = re.search(r"^\[project\]\s*$", text, re.M)
    if not m:
        raise VersionError("pyproject.toml has no [project] table")
    nxt = re.search(r"^\[", text[m.end() :], re.M)
    return m.end(), m.end() + nxt.start() if nxt else len(text)


def _uv_lock_block(text: str, name: str) -> tuple[int, int] | None:
    """Offsets of the root project's `[[package]]` block in uv.lock, by name and a `.` source."""
    starts = [m.start() for m in re.finditer(r"^\[\[package\]\]\s*$", text, re.M)] + [len(text)]
    for start, end in zip(starts, starts[1:], strict=False):
        block = text[start:end]
        m = re.search(r'^name\s*=\s*"([^"]*)"', block, re.M)
        if (
            m
            and _normalise_name(m.group(1)) == _normalise_name(name)
            and re.search(r'^source\s*=\s*\{\s*(editable|virtual)\s*=\s*"\."', block, re.M)
        ):
            return start, end
    return None


def _init_files(root: Path, name: str) -> list[str]:
    """The package `__init__.py` that may carry `__version__`: the module named after the project, or else
    the only package under src/ (a distribution name like vexoulz-conventions ships module conventions)."""
    module = re.sub(r"[-.]+", "_", name).lower()
    named = [rel for rel in (f"src/{module}/__init__.py", f"{module}/__init__.py") if (root / rel).is_file()]
    if named:
        return named
    packages = sorted(p for p in (root / "src").glob("*/__init__.py")) if (root / "src").is_dir() else []
    return [packages[0].relative_to(root).as_posix()] if len(packages) == 1 else []


def sources(root: Path) -> list[Source]:
    """Every place this repo writes its own version; empty when it has none."""
    found: list[Source] = []
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        project = data.get("project", {})
        if "version" in project.get("dynamic", []):
            raise VersionError('pyproject.toml: a dynamic version isn\'t supported; write `version = "..."`')
        if "version" in project:
            name = str(project.get("name", ""))
            found.append(Source("pyproject.toml", "[project] version", str(project["version"])))
            lock = root / "uv.lock"
            if lock.is_file():
                text = lock.read_text(encoding="utf-8")
                span = _uv_lock_block(text, name)
                if span:
                    m = re.search(r'^version\s*=\s*"([^"]*)"', text[span[0] : span[1]], re.M)
                    if m:
                        found.append(Source("uv.lock", f"package {name}", m.group(1)))
            for rel in _init_files(root, name):
                m = _DUNDER_RE.search((root / rel).read_text(encoding="utf-8"))
                if m:
                    found.append(Source(rel, "__version__", m.group(2)))

    package = root / "package.json"
    if package.is_file():
        data = json.loads(package.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "version" in data:
            found.append(Source("package.json", "version", str(data["version"])))
            lock = root / "package-lock.json"
            if lock.is_file():
                ldata = json.loads(lock.read_text(encoding="utf-8"))
                if "version" in ldata:
                    found.append(Source("package-lock.json", "version", str(ldata["version"])))
                root_pkg = ldata.get("packages", {}).get("", {})
                if "version" in root_pkg:
                    found.append(Source("package-lock.json", 'packages[""].version', str(root_pkg["version"])))
    return found


def current(root: Path) -> str | None:
    """The repo's version, or None if it has none. Raises when its files disagree."""
    found = sources(root)
    if not found:
        return None
    values = {s.value for s in found}
    if len(values) > 1:
        listed = ", ".join(f"{s.path} ({s.label}) {s.value}" for s in found)
        raise VersionError(f"the version files disagree: {listed}; `conventions version set X.Y.Z` writes them all")
    value = found[0].value
    parse(value)
    return value


# --- writing -----------------------------------------------------------------------------------------


def _sub_once(text: str, pattern: re.Pattern[str], new: str, where: str) -> str:
    out, n = pattern.subn(lambda m: f'{m.group(1)}"{new}"', text, count=1)
    if n != 1:
        raise VersionError(f"no version line found in {where}")
    return out


def _rewrite(path: Path, edit: Callable[[str], str]) -> None:
    """Apply `edit` to a file's text, keeping its line endings."""
    raw = path.read_bytes().decode("utf-8")
    crlf = "\r\n" in raw
    text = edit(raw.replace("\r\n", "\n"))
    path.write_bytes((text.replace("\n", "\r\n") if crlf else text).encode("utf-8"))


def _editor(root: Path, rel: str, new: str) -> Callable[[str], str]:
    """What writes `new` into the file `rel`, as a function of its text."""
    if rel == "pyproject.toml":

        def edit(text: str) -> str:
            start, end = _project_table(text)
            return text[:start] + _sub_once(text[start:end], _PYPROJECT_VERSION_RE, new, "[project]") + text[end:]

    elif rel == "uv.lock":
        name = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["name"]

        def edit(text: str) -> str:
            span = _uv_lock_block(text, name)
            assert span is not None
            block = _sub_once(text[span[0] : span[1]], _PYPROJECT_VERSION_RE, new, "uv.lock")
            return text[: span[0]] + block + text[span[1] :]

    elif rel.endswith("__init__.py"):

        def edit(text: str) -> str:
            return _sub_once(text, _DUNDER_RE, new, rel)

    elif rel == "package.json":

        def edit(text: str) -> str:
            return _sub_once(text, _JSON_VERSION_RE, new, "package.json")

    else:  # package-lock.json: the top-level version, and the root package's in packages[""]

        def edit(text: str) -> str:
            data = json.loads(text)
            data["version"] = new
            if "" in data.get("packages", {}):
                data["packages"][""]["version"] = new
            return json.dumps(data, indent=2, ensure_ascii=False) + "\n"

    return edit


def set_version(root: Path, new: str) -> list[str]:
    """Write `new` everywhere the version is written. Returns the files changed."""
    parse(new)
    found = sources(root)
    if not found:
        raise VersionError("this repo has no version (no [project] version, no package.json version)")
    changed: list[str] = []
    for rel in dict.fromkeys(s.path for s in found):
        path = root / rel
        before = path.read_bytes()
        _rewrite(path, _editor(root, rel, new))
        if path.read_bytes() != before:
            changed.append(rel)
    if current(root) != new:
        raise VersionError(f"wrote {new}, but the files now say {current(root)}")
    return changed


# --- the next version --------------------------------------------------------------------------------


def git(root: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=False)
    if check and proc.returncode != 0:
        raise VersionError(f"git {' '.join(args)}: {proc.stderr.strip()}")
    return proc.stdout


def last_tag(root: Path, ref: str = "HEAD") -> str | None:
    """The newest `vX.Y.Z` tag reachable from `ref`."""
    out = git(root, "describe", "--tags", "--abbrev=0", "--match", "v[0-9]*", ref, check=False).strip()
    return out or None


def kind_of(messages: list[str]) -> str:
    """The bump a list of commit messages asks for: major, minor or patch (Conventional Commits)."""
    kind = "patch"
    for message in messages:
        header, _, body = message.partition("\n")
        m = _HEADER_RE.match(header)
        if (m and m.group("bang")) or re.search(r"^BREAKING[ -]CHANGE:", body, re.M):
            return "major"
        if m and m.group("type") == "feat":
            kind = "minor"
    return kind


def bump(v: Semver, kind: str) -> Semver:
    if kind == "major":
        # Before 1.0.0 a breaking change is a minor: 0.y.z makes no stability promise to break.
        return (v[0], v[1] + 1, 0) if v[0] == 0 else (v[0] + 1, 0, 0)
    if kind == "minor":
        return v[0], v[1] + 1, 0
    return v[0], v[1], v[2] + 1


def commits_since(root: Path, tag: str | None, ref: str = "HEAD") -> list[str]:
    """The messages of the non-merge commits in `ref` since `tag` (all of them without a tag)."""
    span = f"{tag}..{ref}" if tag else ref
    out = git(root, "log", "--no-merges", "--format=%B%x1e", span)
    return [m.strip() for m in out.split("\x1e") if m.strip()]


@dataclass
class Next:
    version: str
    kind: str
    since: str | None
    commits: int


def next_version(root: Path, requested: str = "auto", ref: str = "HEAD") -> Next:
    """The version the next release of `ref` should carry.

    It counts from the last release tag. `auto` reads the commits since then; patch, minor and major
    force the bump. A version already raised by hand on the branch wins when it is higher.
    """
    if requested not in BUMPS:
        raise VersionError(f"bump must be one of {', '.join(BUMPS)}")
    here = current(root)
    if here is None:
        raise VersionError("this repo has no version to bump")
    tag = last_tag(root, ref)
    messages = commits_since(root, tag, ref)
    if tag and not messages:
        raise VersionError(f"nothing to release: no commits since {tag}")
    kind = kind_of(messages) if requested == "auto" else requested
    base = parse(tag) if tag else parse(here)
    candidate = max(bump(base, kind), parse(here))
    return Next(fmt(candidate), kind, tag, len(messages))


# --- the pull request check --------------------------------------------------------------------------


def _version_at(root: Path, ref: str) -> str | None:
    """The primary version (pyproject.toml, else package.json) as of `ref`."""
    for rel in ("pyproject.toml", "package.json"):
        proc = subprocess.run(
            ["git", "-C", str(root), "show", f"{ref}:{rel}"], capture_output=True, text=True, check=False
        )
        if proc.returncode != 0:
            continue
        if rel == "pyproject.toml":
            value = tomllib.loads(proc.stdout).get("project", {}).get("version")
        else:
            value = json.loads(proc.stdout).get("version")
        if value is not None:
            return str(value)
    return None


def tag_exists(root: Path, tag: str) -> bool:
    return bool(git(root, "tag", "--list", tag).strip())


def check(root: Path, cfg: Config, against: str | None = None) -> tuple[list[str], list[str]]:
    """Problems and notes. The version files must agree. With `against` (the base of a pull request into
    `main`) in a `flow = "dev"` repo, the version must also be above the base's and its tag unused."""
    notes: list[str] = []
    try:
        here = current(root)
    except VersionError as e:
        return [str(e)], notes
    if here is None:
        notes.append("no version in this repo; nothing to check")
        return [], notes
    notes.append(f"version {here}, in " + ", ".join(dict.fromkeys(s.path for s in sources(root))))
    if against is None:
        return [], notes
    if cfg.flow != "dev":
        notes.append('flow = "trunk": a pull request into main isn\'t a release, so the version may stay')
        return [], notes

    problems: list[str] = []
    base = _version_at(root, against)
    if base is not None and parse(here) <= parse(base):
        problems.append(
            f"a pull request into main is a release, and its version must go up: {against} has {base}, "
            f"this branch {here}. Run the release workflow, or `conventions version set X.Y.Z` on a "
            "release/* branch"
        )
    elif base is not None:
        notes.append(f"{base} on {against} → {here}")
    if tag_exists(root, f"v{here}"):
        problems.append(f"tag v{here} already exists; this release needs a version of its own")
    return problems, notes
