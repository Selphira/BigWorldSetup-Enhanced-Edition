from dataclasses import dataclass
from enum import Enum


class ComponentStatus(Enum):
    """Status of a component installation."""

    INSTALLING = "installing"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    SKIPPED = "skipped"
    ALREADY_INSTALLED = "already_installed"


@dataclass
class InstallResult:
    """Result of a component installation."""

    status: ComponentStatus
    return_code: int
    stdout: str
    stderr: str
    warnings: list[str]
    errors: list[str]
    debug_log: str = ""


@dataclass
class ComponentInfo:
    """Information about a component to install."""

    mod_id: str
    component_key: str
    tp2_name: str
    sequence_idx: int
    requirements: set[tuple[str, str]] = ()
    subcomponent_answers: list[str] = None
    extra_args: list[str] = None

    def __post_init__(self):
        """Ensure subcomponent_answers is a list."""
        if self.subcomponent_answers is None:
            self.subcomponent_answers = []
