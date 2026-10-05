"""`.conventions.toml`: which version a repo pins, its profile and its release flow."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_NAME = ".conventions.toml"

# Profile -> the language its files and checks come from (None: no language-specific files).
PROFILES: dict[str, str | None] = {
    "python-service": "python",
    "python-lib": "python",
    "node-lib": "node",
    "site": "node",
    "docs": None,
}
FLOWS = ("trunk", "dev")

# Required checks, as GitHub names them: "<caller job> / <reusable workflow job>". Every repo's ci.yml
# calls conventions-check.yml as job `conventions`, the language workflow as job `ci`, and (for a
# service) publish-image.yml as job `image`, so the names are the same everywhere.
COMMON_CHECKS = ["conventions / branch-name", "conventions / check", "conventions / version"]
PROFILE_CHECKS: dict[str, list[str]] = {
    "python-service": ["ci / lint", "ci / test", "image / build"],
    "python-lib": ["ci / lint", "ci / test"],
    "node-lib": ["ci / lint", "ci / test", "ci / build"],
    "site": ["ci / lint", "ci / test", "ci / build"],
    "docs": [],
}

VERSION_RE = re.compile(r"^v\d+\.\d+\.\d+$")


class ConfigError(Exception):
    pass


@dataclass
class Config:
    version: str
    profile: str
    flow: str = "trunk"
    extra_checks: list[str] = field(default_factory=list)
    extra_workflows: list[str] = field(default_factory=list)
    # True only in vEXOULZ/conventions itself, which checks against its own checkout rather than a pin.
    self_repo: bool = False

    @property
    def language(self) -> str | None:
        return PROFILES[self.profile]

    @property
    def required_checks(self) -> list[str]:
        return COMMON_CHECKS + PROFILE_CHECKS[self.profile] + self.extra_checks

    @property
    def protected_branches(self) -> list[str]:
        return ["main", "dev"] if self.flow == "dev" else ["main"]


def load(root: Path) -> Config:
    path = root / CONFIG_NAME
    if not path.is_file():
        raise ConfigError(f"no {CONFIG_NAME} here; start with `conventions init --profile <profile>`")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{CONFIG_NAME}: {e}") from e

    known = {"version", "profile", "flow", "extra_checks", "extra_workflows", "self"}
    unknown = sorted(set(data) - known)
    if unknown:
        raise ConfigError(f"{CONFIG_NAME}: unknown keys {', '.join(unknown)}")

    version = data.get("version")
    if not isinstance(version, str) or not VERSION_RE.match(version):
        raise ConfigError(f'{CONFIG_NAME}: version must look like "v1.2.3", got {version!r}')
    profile = data.get("profile")
    if profile not in PROFILES:
        raise ConfigError(f"{CONFIG_NAME}: profile must be one of {', '.join(PROFILES)}, got {profile!r}")
    flow = data.get("flow", "trunk")
    if flow not in FLOWS:
        raise ConfigError(f"{CONFIG_NAME}: flow must be one of {', '.join(FLOWS)}, got {flow!r}")

    def str_list(key: str) -> list[str]:
        value = data.get(key, [])
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise ConfigError(f"{CONFIG_NAME}: {key} must be a list of strings")
        return value

    self_repo = data.get("self", False)
    if not isinstance(self_repo, bool):
        raise ConfigError(f"{CONFIG_NAME}: self must be true or false")

    return Config(
        version=version,
        profile=profile,
        flow=flow,
        extra_checks=str_list("extra_checks"),
        extra_workflows=str_list("extra_workflows"),
        self_repo=self_repo,
    )


def render(version: str, profile: str, flow: str) -> str:
    return (
        "# Which version of vEXOULZ/conventions this repo follows, and how.\n"
        "# See https://github.com/vEXOULZ/conventions#conventionstoml\n"
        f'version = "{version}"\n'
        f'profile = "{profile}"\n'
        f'flow = "{flow}"\n'
        "# extra_checks = []      # required checks beyond the profile's, e.g. a repo-specific job\n"
        "# extra_workflows = []   # workflow files beyond ci.yml and publish.yml\n"
    )
