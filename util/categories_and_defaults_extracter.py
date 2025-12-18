#!/usr/bin/env python3
"""
Script pour ajouter les catégories et valeurs par défaut aux composants JSON
à partir du fichier InstallOrder.ini

USAGE:
    python -m util.categories_and_defaults_extracter <ini_file> <json_target>

    ini_file: chemin vers le fichier InstallOrder.ini
    json_target: fichier .json OU dossier contenant des .json

EXEMPLES:
    # Traiter un fichier spécifique
    python -m util.categories_and_defaults_extracter InstallOrder.ini bp-bgt-worldmap.json

    # Traiter tous les fichiers d'un dossier
    python -m util.categories_and_defaults_extracter data/InstallOrder.ini json_folder/
"""

import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional

# Importer le CompactJSONEncoder
from util.ini_to_json_converter import CompactJSONEncoder

# Table de correspondance des catégories
CATEGORY_MAP = {
    "00": "util",
    "01": "patch",
    "02": "conv",
    "03": "quest",
    "04": "npc",
    "05": "npcx",
    "06": "tactic",
    "07": "gameplay",
    "08": "smith",
    "09": "conv",
    "10": "quest",
    "11": "mini",
    "12": "npc",
    "13": "npc1d",
    "14": "npcx",
    "15": "tactic",
    "16": "spell",
    "17": "smith",
    "18": "tactic",
    "19": "kit",
    "20": "ui",
    "21": "portrait",
}


class ComponentData:
    """Données d'un composant extrait de l'INI"""

    def __init__(
        self, comp_type: str, mod_name: str, component_id: str, category_code: str, flags: str
    ):
        self.type = comp_type
        self.mod_name = mod_name
        self.component_id = component_id
        self.category_code = category_code
        self.flags = flags
        self.category = CATEGORY_MAP.get(category_code, "unknown")
        self.flags_value = self._calculate_flags_value(flags)

    def _calculate_flags_value(self, flags: str) -> int:
        """Calcule la valeur numérique des flags (nombre de '1')"""
        return flags.count("1")

    def __repr__(self):
        return f"ComponentData({self.type}, {self.component_id}, cat={self.category}, flags={self.flags_value})"


class INIParser:
    """Parse le fichier InstallOrder.ini"""

    def __init__(self, ini_path: Path):
        self.ini_path = ini_path
        self.components: Dict[str, List[ComponentData]] = {}

    def parse(self) -> Dict[str, List[ComponentData]]:
        """
        Parse le fichier INI et retourne un dict:
        {
            'mod_name': [ComponentData, ...]
        }
        """
        with open(self.ini_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()

                # Ignorer les lignes vides et commentaires
                if (
                    not line
                    or line.startswith("ANN;")
                    or line.startswith("CMD;")
                    or line.startswith("CMT;")
                    or line.startswith("PAUSE;")
                ):
                    continue

                # Parser les lignes de composants
                if line.startswith(("STD;", "MUC;", "SUB;", "DWN;")):
                    comp_data = self._parse_component_line(line)
                    if comp_data:
                        mod_name = comp_data.mod_name
                        if mod_name not in self.components:
                            self.components[mod_name] = []
                        self.components[mod_name].append(comp_data)

        return self.components

    def _parse_component_line(self, line: str) -> Optional[ComponentData]:
        """Parse une ligne de composant"""
        # Format: TYPE;mod_name;component_id;category;flags
        parts = line.split(";")

        if len(parts) < 5:
            return None

        comp_type = parts[0]
        mod_name = parts[1]
        component_id = parts[2]
        category_code = parts[3]
        flags = parts[4]

        return ComponentData(comp_type, mod_name, component_id, category_code, flags)


class JSONProcessor:
    """Traite les fichiers JSON pour ajouter catégories et defaults"""

    def __init__(self, components_data: Dict[str, List[ComponentData]]):
        self.components_data = components_data
        self.stats = {"processed": 0, "updated": 0, "skipped": 0, "errors": 0}

    def process_file(self, json_path: Path) -> bool:
        """Traite un fichier JSON"""
        try:
            # Lire le JSON
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Extraire le nom du mod (nom du fichier sans extension)
            mod_name = json_path.stem

            # Vérifier si on a des données pour ce mod
            if mod_name not in self.components_data:
                print(f"⊘ Aucune donnée INI pour {mod_name}, ignoré")
                self.stats["skipped"] += 1
                return False

            # Traiter les composants
            if "components" in data:
                modified = self._process_components(
                    data["components"],
                    data["categories"],
                    self.components_data[mod_name],
                    mod_name,
                )

                if modified:
                    # Sauvegarder le fichier modifié
                    with open(json_path, "w", encoding="utf-8") as f:
                        json_str = CompactJSONEncoder(indent=2, ensure_ascii=False).encode(data)
                        f.write(json_str)
                        f.write("\n")

                    print(f"✓ Mis à jour: {json_path.name}")
                    self.stats["updated"] += 1
                else:
                    print(f"○ Aucune modification: {json_path.name}")
                    self.stats["skipped"] += 1

            self.stats["processed"] += 1
            return True

        except Exception as e:
            print(f"✗ Erreur avec {json_path.name}: {e}")
            self.stats["errors"] += 1
            return False

    def _process_components(
        self,
        components: Dict[str, Any],
        categories: list[str],
        ini_components: List[ComponentData],
        mod_name: str,
    ) -> bool:
        """
        Traite la section components d'un JSON

        Returns:
            True si des modifications ont été faites
        """
        modified = False

        for comp_id, comp_data in components.items():
            if not isinstance(comp_data, dict):
                continue

            comp_type = comp_data.get("type")

            if comp_type == "std":
                # STD: ajouter la catégorie
                if self._add_category_to_std(comp_id, comp_data, ini_components, categories):
                    modified = True

            elif comp_type == "muc":
                # MUC: ajouter catégorie + default
                if self._add_category_and_default_to_muc(
                    comp_id, comp_data, ini_components, categories
                ):
                    modified = True

            elif comp_type == "sub":
                # SUB: ajouter catégorie + defaults pour chaque prompt
                if self._add_category_and_defaults_to_sub(
                    comp_id, comp_data, ini_components, categories
                ):
                    modified = True

        return modified

    def _add_category_to_std(
        self,
        comp_id: str,
        comp_data: Dict[str, Any],
        ini_components: List[ComponentData],
        categories: list[str],
    ) -> bool:
        """Ajoute la catégorie à un composant STD"""
        # Chercher le composant dans les données INI
        for ini_comp in ini_components:
            if ini_comp.type == "STD" and ini_comp.component_id == comp_id:
                if "category" not in comp_data and ini_comp.category not in categories:
                    comp_data["category"] = ini_comp.category
                    return True
                break
        return False

    def _add_category_and_default_to_muc(
        self,
        comp_id: str,
        comp_data: Dict[str, Any],
        ini_components: List[ComponentData],
        categories: list[str],
    ) -> bool:
        """Ajoute catégorie et default à un composant MUC"""
        modified = False

        # Récupérer la liste des composants du MUC
        muc_components = comp_data.get("components", [])
        if not muc_components:
            return False

        # Chercher les entrées Init dans l'INI
        init_entries = [
            comp
            for comp in ini_components
            if comp.type == "MUC" and comp.component_id == "Init"
        ]

        if not init_entries:
            return False

        # Trouver la catégorie (du premier Init qui correspond)
        category = None
        for ini_comp in init_entries:
            if category is None:
                category = ini_comp.category
                break

        # Ajouter la catégorie
        if category and "category" not in comp_data and ini_comp.category not in categories:
            comp_data["category"] = category
            modified = True

        # Trouver le composant par défaut (celui avec le plus de flags)
        best_comp = None
        best_flags = -1

        for muc_comp_id in muc_components:
            for ini_comp in ini_components:
                if (
                    ini_comp.type == "MUC"
                    and ini_comp.component_id == muc_comp_id
                    and ini_comp.flags_value > best_flags
                ):
                    best_comp = muc_comp_id
                    best_flags = ini_comp.flags_value

        # Ajouter le default
        if best_comp and "default" not in comp_data:
            comp_data["default"] = best_comp
            modified = True

        return modified

    def _add_category_and_defaults_to_sub(
        self,
        comp_id: str,
        comp_data: Dict[str, Any],
        ini_components: List[ComponentData],
        categories: list[str],
    ) -> bool:
        """Ajoute catégorie et defaults à un composant SUB"""
        modified = False

        # Chercher l'entrée sans '?' pour la catégorie
        for ini_comp in ini_components:
            if ini_comp.type == "SUB" and ini_comp.component_id == comp_id:
                print(f"{comp_data} - {ini_comp.category} not in {categories}")
                if "category" not in comp_data and ini_comp.category not in categories:
                    print("YES")
                    comp_data["category"] = ini_comp.category
                    modified = True
                break

        # Traiter chaque prompt
        prompts = comp_data.get("prompts", {})
        for prompt_id, prompt_data in prompts.items():
            if not isinstance(prompt_data, dict):
                continue

            options = prompt_data.get("options", [])
            if not options:
                continue

            # Trouver l'option avec le plus de flags pour ce prompt
            best_option = None
            best_flags = -1

            for option_id in options:
                # Format dans l'INI: "0?1_2" = composant 0, prompt 1, option 2
                search_id = f"{comp_id}?{prompt_id}_{option_id}"

                for ini_comp in ini_components:
                    if (
                        ini_comp.type == "SUB"
                        and ini_comp.component_id == search_id
                        and ini_comp.flags_value > best_flags
                    ):
                        best_option = option_id
                        best_flags = ini_comp.flags_value

            # Ajouter le default pour ce prompt
            if best_option and "default" not in prompt_data:
                prompt_data["default"] = best_option
                modified = True

        return modified

    def process_directory(self, json_dir: Path) -> Dict[str, int]:
        """Traite tous les fichiers JSON d'un dossier"""
        json_files = list(json_dir.glob("*.json"))

        if not json_files:
            print(f"⚠ Aucun fichier JSON trouvé dans {json_dir}")
            return self.stats

        print(f"ℹ Trouvé {len(json_files)} fichier(s) JSON\n")

        for json_file in json_files:
            self.process_file(json_file)

        return self.stats


def print_usage():
    """Affiche l'aide d'utilisation"""
    print("""
╔═══════════════════════════════════════════════════════════╗
║   AJOUT CATÉGORIES ET DEFAULTS AUX COMPOSANTS JSON        ║
╚═══════════════════════════════════════════════════════════╝

USAGE:
    python -m util.categories_and_defaults_extracter <ini_file> <json_target>

ARGUMENTS:
    ini_file     Chemin vers le fichier InstallOrder.ini
    json_target  Fichier .json OU dossier contenant des .json

EXEMPLES:
    # Traiter un fichier spécifique
    python -m util.categories_and_defaults_extracter InstallOrder.ini bp-bgt-worldmap.json

    # Traiter tous les fichiers d'un dossier
    python -m util.categories_and_defaults_extracter data/InstallOrder.ini json_output/

FONCTIONNALITÉS:
    • Ajoute l'attribut "category" à tous les composants
    • Ajoute "default" aux composants MUC (choix multiple)
    • Ajoute "default" à chaque prompt des composants SUB
    • Préserve le formatage JSON compact
    • Ne modifie que les fichiers ayant des correspondances INI

CATÉGORIES SUPPORTÉES:
    00:util   01:patch  02:conv   03:quest  04:npc    05:npcx
    06:tactic 07:gameplay 08:smith 09:conv  10:quest  11:mini
    12:npc    13:npc1d  14:npcx   15:tactic 16:spell  17:smith
    18:tactic 19:kit    20:ui     21:portrait
""")


def main():
    """Point d'entrée du script"""

    # Vérifier les arguments
    if len(sys.argv) != 3:
        print_usage()
        sys.exit(1)

    ini_file_arg = sys.argv[1]
    json_target_arg = sys.argv[2]

    # Affichage spécial pour l'aide
    if ini_file_arg in ["-h", "--help", "help"]:
        print_usage()
        sys.exit(0)

    # Convertir en Path
    ini_path = Path(ini_file_arg)
    json_target = Path(json_target_arg)

    # Vérifier que le fichier INI existe
    if not ini_path.is_file():
        print(f"✗ Erreur: {ini_path} n'est pas un fichier valide")
        sys.exit(1)

    if ini_path.suffix.lower() != ".ini":
        print(f"✗ Erreur: {ini_path} n'est pas un fichier .ini")
        sys.exit(1)

    # Banner
    print("\n" + "═" * 60)
    print("  AJOUT CATÉGORIES ET DEFAULTS")
    print("═" * 60 + "\n")

    # Parser le fichier INI
    print(f"ℹ Parsing de {ini_path.name}...")
    parser = INIParser(ini_path)
    components_data = parser.parse()
    print(f"✓ {len(components_data)} mod(s) trouvé(s) dans l'INI\n")

    # Créer le processeur
    processor = JSONProcessor(components_data)

    # Traiter
    if json_target.is_file():
        # Fichier unique
        if json_target.suffix.lower() != ".json":
            print(f"✗ Erreur: {json_target} n'est pas un fichier .json")
            sys.exit(1)

        processor.process_file(json_target)

    elif json_target.is_dir():
        # Dossier
        processor.process_directory(json_target)

    else:
        print(f"✗ Erreur: {json_target} n'existe pas")
        sys.exit(1)

    # Résumé
    stats = processor.stats
    print("\n" + "═" * 60)
    print("  RÉSUMÉ")
    print("═" * 60)
    print(f"  • Traités   : {stats['processed']}")
    print(f"  ✓ Mis à jour : {stats['updated']}")
    print(f"  ○ Inchangés  : {stats['skipped']}")
    print(f"  ✗ Erreurs    : {stats['errors']}")
    print("═" * 60 + "\n")

    # Code de sortie
    sys.exit(0 if stats['errors'] == 0 else 1)


if __name__ == "__main__":
    main()
