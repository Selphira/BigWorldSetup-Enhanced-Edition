"""Game definition and validation models.

This module defines the data structures used to represent game installations,
their validation rules, and installation sequences. It supports complex
scenarios like EET (Enhanced Edition Trilogy) which requires multiple
game folders.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class InstallStepType(str, Enum):
    """Type of installation step.

    Attributes:
        INSTALL: Standard mod installation step
        DOWNLOAD: Download-only step (no installation)
        ANNOTATION: Comment/note in the installation order
    """
    INSTALL = "ins"
    DOWNLOAD = "dwn"
    ANNOTATION = "ann"

    @classmethod
    def from_string(cls, value: str | None) -> InstallStepType:
        """Convert string to InstallStepType.

        Args:
            value: String value ("dwn", "ins", or None)

        Returns:
            InstallStepType enum value (defaults to INSTALL if None)

        Raises:
            ValueError: If value is not a valid step type
        """
        if not value:
            return cls.INSTALL

        try:
            return cls(value)
        except ValueError:
            raise ValueError(
                f"Invalid step type: '{value}'. Must be 'dwn' or 'ins'"
            )


@dataclass(frozen=True, slots=True)
class InstallStep:
    """Single step in the mod installation sequence.

    Represents one mod component to be installed (or downloaded), or an
    annotation/comment in the installation order.

    Attributes:
        mod: Mod identifier
        comp: Component identifier/number
        step_type: Type of step (download-only or install)
        text: Annotation text (only used for ANNOTATION type)
    """

    mod: str = ""
    comp: str = ""
    step_type: InstallStepType = InstallStepType.INSTALL
    text: str = ""

    def __post_init__(self) -> None:
        """Validate the installation step."""
        if self.step_type == InstallStepType.ANNOTATION:
            if not self.text:
                raise ValueError("InstallStep of type ANNOTATION requires non-empty 'text'")
        else:
            if not self.mod:
                raise ValueError("InstallStep requires non-empty 'mod'")
            if not self.comp:
                raise ValueError("InstallStep requires non-empty 'comp'")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InstallStep:
        """Create installation step from dictionary configuration.

        Args:
            data: Dictionary containing step configuration with keys:
                  - type: Step type ("dwn", "ins", or "ann", optional, defaults to "ins")
                  - mod: Mod identifier (required for dwn/ins)
                  - comp: Component identifier (required for dwn/ins)
                  - text: Annotation text (required for ann)

        Returns:
            New InstallStep instance

        Raises:
            ValueError: If required fields are missing or invalid
        """
        step_type = InstallStepType.from_string(data.get("type"))

        if step_type == InstallStepType.ANNOTATION:
            text = data.get("text")
            if not text:
                raise ValueError("InstallStep of type 'ann' requires 'text' field")
            return cls(step_type=step_type, text=text)
        else:
            mod = data.get("mod")
            comp = data.get("comp")

            if not mod:
                raise ValueError("InstallStep requires 'mod' field")
            if not comp:
                raise ValueError("InstallStep requires 'comp' field")

            return cls(mod=mod, comp=comp, step_type=step_type)

    @property
    def is_download_only(self) -> bool:
        """Check if this is a download-only step.

        Returns:
            True if step type is DOWNLOAD, False otherwise
        """
        return self.step_type == InstallStepType.DOWNLOAD

    @property
    def is_install(self) -> bool:
        """Check if this is an installation step.

        Returns:
            True if step type is INSTALL, False otherwise
        """
        return self.step_type == InstallStepType.INSTALL

    @property
    def is_annotation(self) -> bool:
        """Check if this is an annotation step.

        Returns:
            True if step type is ANNOTATION, False otherwise
        """
        return self.step_type == InstallStepType.ANNOTATION

    def to_dict(self) -> dict[str, str]:
        """Convert installation step to dictionary.

        Returns:
            Dictionary representation of the step
        """
        if self.step_type == InstallStepType.ANNOTATION:
            return {
                "type": self.step_type.value,
                "text": self.text
            }

        result = {
            "mod": self.mod,
            "comp": self.comp
        }

        # Only include type if it's not the default (INSTALL)
        if self.step_type != InstallStepType.INSTALL:
            result["type"] = self.step_type.value

        return result

    def __str__(self) -> str:
        """String representation for logging and debugging."""
        if self.is_annotation:
            return f"[ANN] {self.text}"

        type_prefix = "[DWN] " if self.is_download_only else ""
        return f"{type_prefix}{self.mod}:{self.comp}"


@dataclass(frozen=True, slots=True)
class GameValidationRule:
    """Validation rules for a single game folder sequence.

    This class defines what files and Lua variables must be present
    to validate a game installation. It supports folder widget reuse
    through the 'game' reference.

    Attributes:
        required_files: Tuple of file paths that must exist in the game folder
        lua_checks: Dictionary mapping Lua variable names to expected values
        game: Reference to another game's folder for widget reuse
              (e.g., "sod" means this sequence shares SOD's folder widget)
    """

    required_files: tuple[str, ...] = ()
    lua_checks: dict[str, Any] = field(default_factory=dict)
    game: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GameValidationRule:
        """Create validation rule from dictionary configuration.

        Args:
            data: Dictionary containing validation configuration with keys:
                  - required_files: List of required file paths
                  - lua_checks: Dict of Lua variable checks
                  - game: Game reference for folder reuse

        Returns:
            GameValidationRule instance
        """
        return cls(
            required_files=tuple(data.get("required_files", [])),
            lua_checks=data.get("lua_checks", {}),
            game=data.get("game")
        )


@dataclass(frozen=True, slots=True)
class GameSequence:
    """Installation sequence for a game component (BG1, BG2, SoD, etc.).

    A game definition can have multiple sequences. For example, EET requires
    both SOD and BG2EE installations. Each sequence defines validation rules
    and mod filtering configuration.

    Attributes:
        game: Game identifier key used by the UI
        required_files: Files that must exist for this sequence
        lua_checks: Lua engine variables to validate
        allowed_mods: Whitelist of mod IDs (None = all allowed)
        blocked_mods: Blacklist of mod IDs (None = none ignored)
        allowed_components: Per-mod component filtering {mod_id: [component_ids]}
    """

    game: str
    required_files: tuple[str, ...] = ()
    lua_checks: dict[str, Any] = field(default_factory=dict)
    allowed_mods: tuple[str, ...] | None = None
    blocked_mods: tuple[str, ...] | None = None
    allowed_components: dict[str, tuple[str, ...]] = field(default_factory=dict)
    order: tuple[InstallStep, ...] = ()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GameSequence:
        """Create game sequence from dictionary configuration.

        Args:
            data: Dictionary containing sequence configuration

        Returns:
            New GameSequence instance

        Raises:
            ValueError: If 'game' key is missing from data
        """
        game = data.get("game")
        if not game:
            raise ValueError("GameSequence requires 'game' identifier")

        # Convert lists to tuples for immutability
        allowed_mods = data.get("allowed_mods")
        blocked_mods = data.get("blocked_mods")
        allowed_components_raw = data.get("allowed_components", {})
        order_raw = data.get("order", [])

        return cls(
            game=game,
            required_files=tuple(data.get("required_files", [])),
            lua_checks=data.get("lua_checks", {}),
            allowed_mods=tuple(allowed_mods) if allowed_mods else None,
            blocked_mods=tuple(blocked_mods) if blocked_mods else None,
            allowed_components={
                mod_id: tuple(components)
                for mod_id, components in allowed_components_raw.items()
            },
            order=tuple(InstallStep.from_dict(step) for step in order_raw)
        )

    def is_mod_allowed(self, mod_id: str) -> bool:
        """Check if a mod is allowed in this sequence.

        Args:
            mod_id: Identifier of the mod to check

        Returns:
            True if the mod is allowed, False otherwise

        Logic:
            - If in blocked_mods: False
            - If allowed_mods is None: True (all allowed by default)
            - If in allowed_mods: True
            - Otherwise: False
        """
        if self.blocked_mods and mod_id in self.blocked_mods:
            return False

        if self.allowed_mods is None:
            return True

        return mod_id in self.allowed_mods

    def is_component_allowed(self, mod_id: str, comp_key: str) -> bool:
        """Check if a specific mod component is allowed.

        Args:
            mod_id: Identifier of the mod
            comp_key: Identifier of the component

        Returns:
            True if the component is allowed, False otherwise

        Logic:
            - If mod has no component restrictions: True
            - If component in allowed list: True
            - Otherwise: False
        """
        if mod_id not in self.allowed_components:
            return True

        return comp_key in self.allowed_components[mod_id]

    def get_install_steps(self, include_downloads: bool = True) -> tuple[InstallStep, ...]:
        """Get installation steps, optionally filtering by type.

        Args:
            include_downloads: If False, exclude download-only steps

        Returns:
            Tuple of installation steps matching the filter
        """
        if include_downloads:
            return self.order

        return tuple(step for step in self.order if step.is_install)

    def get_download_steps(self) -> tuple[InstallStep, ...]:
        """Get only download steps from the installation order.
        
        Returns:
            Tuple of download-only installation steps
        """
        return tuple(step for step in self.order if step.is_download_only)


@dataclass(frozen=True, slots=True)
class GameDefinition:
    """Complete definition of a game installation.

    Represents a full game configuration (EET, BG2EE, IWDEE, etc.) with
    one or more installation sequences. Complex installations like EET
    require multiple sequences (SOD + BG2EE).

    Attributes:
        id: Unique game identifier
        name: Human-readable game name (translatable)
        sequences: List of installation sequences required for this game
    """

    id: str
    name: str
    sequences: tuple[GameSequence, ...]

    def __post_init__(self) -> None:
        """Validate the game definition after initialization."""
        if not self.id:
            raise ValueError("GameDefinition requires non-empty 'id'")
        if not self.name:
            raise ValueError("GameDefinition requires non-empty 'name'")
        if not self.sequences:
            raise ValueError("GameDefinition requires at least one sequence")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GameDefinition:
        """Create game definition from dictionary configuration.

        Args:
            data: Dictionary containing game configuration with keys:
                  - id: Game identifier
                  - name: Game display name
                  - sequences: List of sequence configurations

        Returns:
            New GameDefinition instance

        Raises:
            ValueError: If required fields are missing or invalid
        """
        game_id = data.get("id")
        name = data.get("name")
        sequences_data = data.get("sequences", [])

        if not game_id:
            raise ValueError("GameDefinition requires 'id' field")
        if not name:
            raise ValueError("GameDefinition requires 'name' field")
        if not sequences_data:
            raise ValueError("GameDefinition requires at least one sequence")

        sequences = tuple(
            GameSequence.from_dict(seq_data)
            for seq_data in sequences_data
        )

        return cls(id=game_id, name=name, sequences=sequences)

    def get_sequence(self, index: int) -> GameSequence | None:
        """Get a sequence by index.

        Args:
            index: Zero-based index of the sequence

        Returns:
            GameSequence at the given index, or None if out of bounds
        """
        if 0 <= index < len(self.sequences):
            return self.sequences[index]
        return None

    @property
    def sequence_count(self) -> int:
        """Get the number of installation sequences.

        Returns:
            Number of sequences in this game definition
        """
        return len(self.sequences)

    @property
    def has_multiple_sequences(self) -> bool:
        """Check if this game requires multiple installation sequences.

        Returns:
            True if more than one sequence, False otherwise
        """
        return self.sequence_count > 1

    def get_folder_keys(self) -> tuple[str, ...]:
        """Get unique folder keys needed for UI widgets.

        For standalone sequences: uses the game's own id
        For shared sequences: uses the referenced game id

        Returns:
            Tuple of folder keys for widget creation
        """
        folder_keys = []
        for sequence in self.sequences:
            # Use referenced game if specified, otherwise use own id
            key = sequence.game if sequence.game else self.id
            folder_keys.append(key)

        return tuple(folder_keys)
