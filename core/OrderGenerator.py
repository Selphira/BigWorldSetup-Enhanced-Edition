"""
Order generation from dependency and order rules.
"""

from collections import defaultdict, deque
import logging
from typing import TYPE_CHECKING

from core.ComponentReference import ComponentReference
from core.Rules import DependencyRule, OrderDirection, OrderRule

if TYPE_CHECKING:
    from core.RuleManager import RuleManager

logger = logging.getLogger(__name__)


class OrderGenerator:
    """Generates optimal installation order from dependency rules."""

    def __init__(self, rule_manager: "RuleManager"):
        """Initialize order generator.

        Args:
            rule_manager: RuleManager instance to get rules from
        """
        self._rule_manager = rule_manager

    def generate(
        self,
        selected_components: list[ComponentReference],
        base_order: list[ComponentReference] | None = None,
    ) -> list[ComponentReference]:
        """Generate installation order by completing base_order with dependency rules.

        Args:
            selected_components: All selected components
            base_order: Optional existing manual order to preserve (has priority)

        Returns:
            Ordered list of ComponentReference
        """
        if not selected_components:
            return []

        selected_set = set(selected_components)
        components_with_rules = self._get_components_with_rules(selected_set)

        if base_order:
            components_to_order = components_with_rules | set(
                ref for ref in base_order if ref in selected_set
            )
        else:
            components_to_order = components_with_rules

        if not components_to_order:
            return base_order if base_order else []

        graph, in_degree = self._build_dependency_graph(components_to_order)
        ideal_order = self._topological_sort(graph, in_degree, components_to_order)

        if not base_order:
            return ideal_order

        return self._merge_orders(ideal_order, base_order)

    def _get_components_with_rules(
        self, selected_refs: set[ComponentReference]
    ) -> set[ComponentReference]:
        """Find all components that have ordering rules (dependencies or explicit order).

        Returns:
            Set of components that appear in any rule (as source or target)
        """
        components_with_rules: set[ComponentReference] = set()

        for reference in selected_refs:
            rules = self._rule_manager.get_rules_for_component(reference)

            if not rules:
                continue

            components_with_rules.add(reference)

            # Add all targets from these rules
            for rule in rules:
                # Only include rules that affect ordering
                if isinstance(rule, DependencyRule) and not rule.implicit_order:
                    continue

                if not isinstance(rule, (DependencyRule, OrderRule)):
                    continue

                for target_ref in rule.targets:
                    if target_ref in selected_refs:
                        components_with_rules.add(target_ref)

        return components_with_rules

    def _build_dependency_graph(
        self, components_to_order: set[ComponentReference]
    ) -> tuple[
        dict[ComponentReference, set[ComponentReference]], dict[ComponentReference, int]
    ]:
        """Build dependency graph from rules.

        Edge u -> v means: u must be installed BEFORE v

        Args:
            components_to_order: Only these components are included in graph

        Returns:
            (graph, in_degree) where:
            - graph[u] = set of nodes that depend on u (u -> v)
            - in_degree[v] = number of dependencies v has
        """
        graph: dict[ComponentReference, set[ComponentReference]] = defaultdict(set)
        in_degree: dict[ComponentReference, int] = {ref: 0 for ref in components_to_order}

        def add_edge(before: ComponentReference, after: ComponentReference):
            """Add edge: before -> after."""
            if before == after:
                return
            if before not in components_to_order or after not in components_to_order:
                return

            if after not in graph[before]:
                graph[before].add(after)
                in_degree[after] += 1

        # Process DEPENDENCY rules: dependencies come BEFORE dependents
        for rule in self._rule_manager.get_dependency_rules():
            if not rule.implicit_order:
                continue

            sources = [ref for ref in components_to_order if ref in rule.sources]
            if not sources:
                continue

            targets = [ref for ref in components_to_order if ref in rule.targets]
            if not targets:
                continue

            # Add edges: target -> source (dependency BEFORE dependent)
            for target in targets:
                for source in sources:
                    add_edge(target, source)

        # Process ORDER rules
        for rule in self._rule_manager.get_order_rules():
            sources = [ref for ref in components_to_order if ref in rule.sources]
            if not sources:
                continue

            targets = [ref for ref in components_to_order if ref in rule.targets]
            if not targets:
                continue

            for source in sources:
                for target in targets:
                    if rule.order_direction == OrderDirection.BEFORE:
                        # source BEFORE target
                        add_edge(source, target)
                    else:
                        # source AFTER target -> target BEFORE source
                        add_edge(target, source)

        return graph, in_degree

    @staticmethod
    def _topological_sort(
        graph: dict[ComponentReference, set[ComponentReference]],
        in_degree: dict[ComponentReference, int],
        components_to_order: set[ComponentReference],
    ) -> list[ComponentReference]:
        """Kahn's algorithm for topological sort.

        Returns deterministic order by sorting at each step.

        Args:
            graph: Dependency graph
            in_degree: In-degree for each node
            components_to_order: Set of components to order

        Returns:
            Topologically sorted list of components
        """
        # Find nodes with no dependencies
        zero_degree = deque(
            sorted(
                [ref for ref in components_to_order if in_degree[ref] == 0],
                key=lambda r: (r.mod_id, r.comp_key),
            )
        )

        result: list[ComponentReference] = []
        in_degree_copy = in_degree.copy()

        while zero_degree:
            current = zero_degree.popleft()
            result.append(current)

            # Process neighbors (nodes that depend on current)
            for neighbor in sorted(
                graph.get(current, []), key=lambda r: (r.mod_id, r.comp_key)
            ):
                in_degree_copy[neighbor] -= 1
                if in_degree_copy[neighbor] == 0:
                    zero_degree.append(neighbor)

        # Check for cycles
        if len(result) != len(components_to_order):
            logger.warning("Circular dependencies detected - adding remaining nodes")
            unprocessed = components_to_order - set(result)
            result.extend(sorted(unprocessed, key=lambda r: (r.mod_id, r.comp_key)))

        return result

    def _merge_orders(
        self,
        ideal_order: list[ComponentReference],
        base_order: list[ComponentReference],
    ) -> list[ComponentReference]:
        """Merge ideal_order with base_order while preserving:
        1. Relative positions from base_order where possible
        2. Dependency constraints from ideal_order
        """
        # Find components that need to be inserted
        base_set = set(base_order)
        to_insert = [ref for ref in ideal_order if ref not in base_set]

        if not to_insert:
            return base_order

        # Build position map from ideal_order (for constraint checking)
        ideal_positions = {ref: idx for idx, ref in enumerate(ideal_order)}

        # Insert each component at the best position
        result = base_order.copy()

        for ref_to_insert in to_insert:
            best_position = self._find_best_position(ref_to_insert, result, ideal_positions)
            result.insert(best_position, ref_to_insert)

        return result

    @staticmethod
    def _find_best_position(
        ref: ComponentReference,
        current_order: list[ComponentReference],
        ideal_positions: dict[ComponentReference, int],
    ) -> int:
        """Find best position to insert ref into current_order.

        Rules:
        1. Must respect dependency constraints from ideal_positions
        2. Insert as close as possible to ideal position

        Args:
            ref: Reference to insert
            current_order: Current order
            ideal_positions: Position map from ideal order

        Returns:
            Index where ref should be inserted
        """
        if not current_order:
            return 0

        ref_ideal_pos = ideal_positions[ref]

        # Find valid range based on dependencies
        min_pos = 0  # Earliest valid position
        max_pos = len(current_order)  # Latest valid position

        for idx, existing_ref in enumerate(current_order):
            existing_ideal_pos = ideal_positions.get(existing_ref)

            if existing_ideal_pos is None:
                continue

            # If existing should come BEFORE ref in ideal order
            if existing_ideal_pos < ref_ideal_pos:
                min_pos = max(min_pos, idx + 1)

            # If existing should come AFTER ref in ideal order
            elif existing_ideal_pos > ref_ideal_pos:
                max_pos = min(max_pos, idx)

        # Insert at min_pos (respects all constraints and closest to ideal)
        return min_pos
