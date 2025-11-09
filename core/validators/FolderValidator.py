"""Folder validation system for game installations.

Provides a hierarchy of validators for different folder validation scenarios:
- FolderValidator: Base abstract validator
- ExistingFolderValidator: Validates folder existence
- WritableFolderValidator: Validates write permissions
- GameFolderValidator: Validates game-specific requirements
"""

import logging
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.TranslationManager import tr

logger = logging.getLogger(__name__)

# Type alias for validation result
ValidationResult = Tuple[bool, str]


class FolderValidator(ABC):
    """Base abstract validator for folder paths.

    All folder validators should inherit from this class and implement
    the validate method.
    """

    @abstractmethod
    def validate(self, path: str) -> ValidationResult:
        """Validate a folder path.

        Args:
            path: Path to validate

        Returns:
            Tuple of (is_valid, error_message).
            error_message is empty string if valid.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement validate()"
        )


class ExistingFolderValidator(FolderValidator):
    """Validates that a folder exists and is a directory."""

    def validate(self, path: str) -> ValidationResult:
        """Validate that folder exists.

        Args:
            path: Path to validate

        Returns:
            (True, "") if valid, (False, error_message) otherwise
        """
        # Check if path is provided
        if not path:
            return False, tr('validation.folder_required')

        folder = Path(path)

        # Check existence
        if not folder.exists():
            return False, tr('validation.folder_not_exist')

        # Check it's a directory
        if not folder.is_dir():
            return False, tr('validation.not_a_folder')

        return True, ""


class WritableFolderValidator(ExistingFolderValidator):
    """Validates that a folder exists and is writable."""

    TEST_FILE_NAME = '.write_test'

    def validate(self, path: str) -> ValidationResult:
        """Validate that folder exists and is writable.

        Args:
            path: Path to validate

        Returns:
            (True, "") if valid, (False, error_message) otherwise
        """
        # First check if folder exists
        valid, message = super().validate(path)
        if not valid:
            return valid, message

        # Test write permission by creating and deleting a test file
        folder = Path(path)
        test_file = folder / self.TEST_FILE_NAME

        try:
            test_file.touch()
            test_file.unlink()
            logger.debug(f"Folder is writable: {path}")
            return True, ""
        except PermissionError:
            logger.warning(f"Folder not writable: {path}")
            return False, tr('validation.folder_not_writable')
        except OSError as e:
            logger.warning(f"Error testing write permission for {path}: {e}")
            return False, tr('validation.folder_not_writable')


class GameFolderValidator(ExistingFolderValidator):
    """Validates a game folder against specific game requirements.

    Checks:
    - Folder existence (via parent class)
    - Required files presence
    - Lua variable conditions in engine.lua
    """

    # Regex to parse Lua numeric variables (e.g., "version = 2.5")
    _LUA_NUMBER_PATTERN = re.compile(
        r'(\w+)\s*=\s*(-?\d+(?:\.\d+)?)',
        re.MULTILINE
    )

    def __init__(self, validation_rules: Dict[str, Any]) -> None:
        """Initialize validator with game-specific rules.

        Args:
            validation_rules: Dictionary with validation rules:
                - required_files: List of required file names
                - lua_checks: Dict of variable_name -> expected_value
        """
        self.validation_rules = validation_rules
        logger.debug(f"GameFolderValidator initialized with rules: {validation_rules}")

    def validate(self, path: str) -> ValidationResult:
        """Validate game folder against rules.

        Args:
            path: Path to game folder

        Returns:
            (True, "") if valid, (False, error_message) otherwise
        """
        # First check if folder exists
        valid, message = super().validate(path)
        if not valid:
            return valid, message

        # Validate against game-specific rules
        if not self._validate_game_requirements(path):
            return False, tr('validation.invalid_game_folder')

        logger.info(f"Game folder validated successfully: {path}")
        return True, ""

    def _validate_game_requirements(self, folder_path: str) -> bool:
        """Validate folder against all game requirements.

        Args:
            folder_path: Path to game folder

        Returns:
            True if all requirements met
        """
        folder = Path(folder_path)

        if not folder.is_dir():
            logger.debug(f"Invalid folder: {folder_path}")
            return False

        # Check required files
        required_files = self.validation_rules.get("required_files", [])
        if required_files and not self._check_required_files(folder, required_files):
            return False

        # Check Lua conditions
        lua_checks = self.validation_rules.get("lua_checks", {})
        if lua_checks and not self._check_lua_conditions(folder, lua_checks):
            return False

        return True

    # ========================================
    # FILE OPERATIONS
    # ========================================

    @staticmethod
    def _file_exists_case_insensitive(folder: Path, filename: str) -> bool:
        """Check if a file exists (case-insensitive).

        Useful for cross-platform compatibility where file systems
        may have different case sensitivity.

        Args:
            folder: Folder to search in
            filename: File name to find

        Returns:
            True if file exists (any case)
        """
        # Try exact match first (faster)
        exact_path = folder / filename
        if exact_path.exists():
            return True

        # Fall back to case-insensitive search
        filename_lower = filename.lower()
        try:
            return any(
                item.is_file() and item.name.lower() == filename_lower
                for item in folder.iterdir()
            )
        except (PermissionError, OSError) as e:
            logger.warning(f"Cannot access folder {folder}: {e}")
            return False

    @staticmethod
    def _find_file_case_insensitive(folder: Path, filename: str) -> Optional[Path]:
        """Find a file in folder by name (case-insensitive).

        Args:
            folder: Folder to search in
            filename: File name to find

        Returns:
            Path to file if found, None otherwise
        """
        # Try exact match first
        exact_path = folder / filename
        if exact_path.exists():
            return exact_path

        # Fall back to case-insensitive search
        filename_lower = filename.lower()
        try:
            for item in folder.iterdir():
                if item.is_file() and item.name.lower() == filename_lower:
                    return item
        except (PermissionError, OSError) as e:
            logger.warning(f"Cannot access folder {folder}: {e}")

        return None

    # ========================================
    # VALIDATION CHECKS
    # ========================================

    def _check_required_files(self, folder: Path, required_files: List[str]) -> bool:
        """Ensure all required files exist in folder.

        Args:
            folder: Folder to check
            required_files: List of required file names

        Returns:
            True if all files exist
        """
        for filename in required_files:
            if not self._file_exists_case_insensitive(folder, filename):
                logger.debug(f"Missing required file: {filename} in {folder}")
                return False

        logger.debug(f"All required files present in {folder}")
        return True

    def _check_lua_conditions(self, folder: Path, lua_checks: Dict[str, Any]) -> bool:
        """Verify numeric variable conditions in engine.lua.

        Args:
            folder: Game folder
            lua_checks: Dict of variable_name -> expected_value

        Returns:
            True if all conditions met
        """
        # Find engine.lua (case-insensitive)
        engine_path = self._find_file_case_insensitive(folder, "engine.lua")

        if not engine_path:
            logger.debug(f"engine.lua not found in {folder}")
            return False

        # Parse Lua variables
        lua_vars = self._parse_lua_file(engine_path)

        # Check each condition
        for var_name, expected_value in lua_checks.items():
            actual_value = lua_vars.get(var_name)

            if actual_value != expected_value:
                logger.debug(
                    f"Lua variable mismatch in {engine_path}: "
                    f"{var_name} (expected={expected_value}, actual={actual_value})"
                )
                return False

        logger.debug(f"All Lua conditions met in {engine_path}")
        return True

    # ========================================
    # LUA PARSING
    # ========================================

    @classmethod
    def _parse_lua_file(cls, file_path: Path) -> Dict[str, Any]:
        """Parse a Lua file and extract numeric variables.

        Extracts variables in the format: variable_name = numeric_value
        Supports integers and floats.

        Args:
            file_path: Path to Lua file

        Returns:
            Dictionary of variable_name -> value
        """
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except (PermissionError, OSError) as e:
            logger.warning(f"Failed to read Lua file {file_path}: {e}")
            return {}

        # Extract all numeric variables with a single regex pass
        matches = cls._LUA_NUMBER_PATTERN.findall(content)

        # Convert to appropriate numeric type
        variables = {}
        for name, value in matches:
            # Use float if decimal point present, otherwise int
            variables[name] = float(value) if '.' in value else int(value)

        logger.debug(f"Parsed {len(variables)} variables from {file_path}")
        return variables

    # ========================================
    # UTILITY METHODS
    # ========================================

    def get_validation_rules(self) -> Dict[str, Any]:
        """Get current validation rules.

        Returns:
            Copy of validation rules dictionary
        """
        return self.validation_rules.copy()

    def update_validation_rules(self, rules: Dict[str, Any]) -> None:
        """Update validation rules.

        Args:
            rules: New validation rules (merged with existing)
        """
        self.validation_rules.update(rules)
        logger.debug(f"Validation rules updated: {self.validation_rules}")

    def __repr__(self) -> str:
        """String representation for debugging."""
        return f"<GameFolderValidator rules={self.validation_rules}>"