import logging
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime
from services.code_quality_analyzer import CodeQualityAnalyzer
from services.architecture_analyzer import ArchitectureAnalyzer
from services.dependency_vulnerability_scanner import DependencyVulnerabilityScanner
from services.documentation_debt_analyzer import DocumentationDebtAnalyzer
from services.tech_debt_advisor import build_score_explanation

logger = logging.getLogger(__name__)

CATEGORY_ALIASES = {
    "test": "test_coverage",
    "tests": "test_coverage",
}


class TechDebtAnalyzer:
    """Main tech debt analysis engine that orchestrates all debt analysis types."""
    
    def __init__(self):
        self.code_quality_analyzer = CodeQualityAnalyzer()
        self.architecture_analyzer = ArchitectureAnalyzer()
        self.dependency_scanner = DependencyVulnerabilityScanner()
        self.documentation_analyzer = DocumentationDebtAnalyzer()
    
    def analyze_repository(
        self,
        repository_id: str,
        repository_path: str,
        code_elements: List[Dict[str, Any]],
        services: List[Dict[str, Any]],
        dependency_graph: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Main analysis entry point."""
        logger.info(f"Starting tech debt analysis for repository: {repository_id}")
        
        all_debt_items = []
        assessment_coverage = {
            "code_quality": {
                "supported": True,
                "confidence": "high" if code_elements else "low",
                "note": "Parsed code elements are used to detect long functions, duplication, nesting, and similar code-quality issues."
                if code_elements
                else "Code-quality checks are limited because parsed code elements were not available for this run.",
            },
            "architecture": {
                "supported": True,
                "confidence": "high" if dependency_graph and services else "low",
                "note": "Architecture findings use the dependency graph and discovered services."
                if dependency_graph and services
                else "Architecture checks are limited because service inventory or dependency graph context was missing.",
            },
            "dependency": {
                "supported": True,
                "confidence": "medium",
                "note": "Dependency analysis currently focuses on static dependency manifests and known vulnerability or pinning issues.",
            },
            "documentation": {
                "supported": True,
                "confidence": "medium",
                "note": "Documentation analysis is heuristic and currently checks repository docs presence plus missing Python docstrings.",
            },
            "test_coverage": {
                "supported": False,
                "confidence": "low",
                "note": "Automated test-coverage analysis is not implemented yet; a zero score here does not imply good coverage.",
            },
        }
        
        # Run code quality analysis
        try:
            code_quality_items = self.code_quality_analyzer.analyze(
                repository_path,
                code_elements
            )
            all_debt_items.extend(code_quality_items)
            logger.info(f"Found {len(code_quality_items)} code quality issues")
        except Exception as e:
            logger.error(f"Error in code quality analysis: {e}")
        
        # Run architecture analysis
        try:
            architecture_items = self.architecture_analyzer.analyze(
                repository_id,
                services,
                dependency_graph
            )
            all_debt_items.extend(architecture_items)
            logger.info(f"Found {len(architecture_items)} architecture issues")
        except Exception as e:
            logger.error(f"Error in architecture analysis: {e}")
        
        # Run dependency vulnerability scan
        try:
            dependency_items = self.dependency_scanner.scan(repository_path)
            all_debt_items.extend(dependency_items)
            logger.info(f"Found {len(dependency_items)} dependency issues")
        except Exception as e:
            logger.error(f"Error in dependency scanning: {e}")

        # Run documentation analysis
        try:
            documentation_items = self.documentation_analyzer.analyze(repository_path)
            all_debt_items.extend(documentation_items)
            logger.info(f"Found {len(documentation_items)} documentation issues")
        except Exception as e:
            logger.error(f"Error in documentation analysis: {e}")
        
        # Calculate scores and prioritize
        debt_scores = self._calculate_category_scores(all_debt_items, assessment_coverage)
        total_debt_score = self.calculate_debt_score(all_debt_items, debt_scores=debt_scores)
        prioritized_items = self.prioritize_debt(all_debt_items)
        
        # Calculate metrics
        total_lines = sum(
            e.get("line_end", 0) - e.get("line_start", 0) + 1
            for e in code_elements
        )
        debt_density = (len(all_debt_items) / max(total_lines / 1000, 1)) if total_lines > 0 else 0
        
        return {
            "repository_id": repository_id,
            "total_debt_score": total_debt_score,
            "debt_density": debt_density,
            "total_items": len(all_debt_items),
            "debt_items": prioritized_items,
            "category_scores": debt_scores,
            "items_by_category": self._group_by_category(all_debt_items),
            "items_by_severity": self._group_by_severity(all_debt_items),
            "assessment_coverage": assessment_coverage,
            "score_explanation": build_score_explanation(),
            "analyzed_at": datetime.utcnow().isoformat(),
        }
    
    def calculate_debt_score(
        self,
        debt_items: List[Dict[str, Any]],
        *,
        debt_scores: Optional[Dict[str, float]] = None,
    ) -> float:
        """Calculate overall debt score (0-100, higher = more debt)."""
        if not debt_items and not debt_scores:
            return 0.0
        
        # Calculate category scores
        category_scores = debt_scores or self._calculate_category_scores(debt_items)
        
        # Weighted average
        total_score = (
            category_scores.get("code_quality", 0) * 0.30 +
            category_scores.get("architecture", 0) * 0.25 +
            category_scores.get("dependency", 0) * 0.20 +
            category_scores.get("documentation", 0) * 0.15 +
            category_scores.get("test_coverage", 0) * 0.10
        )
        
        return min(total_score, 100.0)
    
    def _calculate_category_scores(
        self,
        debt_items: List[Dict[str, Any]],
        assessment_coverage: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, float]:
        """Calculate debt scores by category."""
        category_weights = {
            "low": 1.0,
            "medium": 2.5,
            "high": 5.0,
            "critical": 10.0,
        }
        
        category_scores = {}
        categories = [
            "code_quality",
            "architecture",
            "dependency",
            "documentation",
            "test_coverage",
            "performance",
            "security",
        ]

        for category in categories:
            category_items = [
                item
                for item in debt_items
                if CATEGORY_ALIASES.get(str(item.get("category") or "").strip(), str(item.get("category") or "").strip())
                == category
            ]
            if not category_items:
                cov = (assessment_coverage or {}).get(category) or {}
                if cov.get("supported") is False:
                    category_scores[category] = 0.0
                else:
                    confidence = str(cov.get("confidence") or "").lower()
                    if confidence == "high":
                        category_scores[category] = 6.0
                    elif confidence == "medium":
                        category_scores[category] = 4.0
                    elif confidence == "low":
                        category_scores[category] = 2.0
                    else:
                        category_scores[category] = 0.0
                continue
            
            # Calculate weighted score
            weighted_sum = sum(
                category_weights.get(item.get("severity", "low"), 1.0) * item.get("impact_score", 0.5)
                for item in category_items
            )
            
            # Normalize to 0-100 scale
            max_possible = len(category_items) * 10.0  # Assuming all critical
            category_scores[category] = min((weighted_sum / max_possible) * 100, 100.0)
        
        return category_scores
    
    def prioritize_debt(self, debt_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Sort debt items by priority (impact × effort)."""
        for item in debt_items:
            # Calculate priority based on impact and effort
            impact = item.get("impact_score", 0.5)
            effort_str = item.get("effort_estimate", "medium")
            
            # Convert effort to numeric (lower = better)
            effort_map = {
                "hours": 1,
                "days": 2,
                "weeks": 3,
                "months": 4,
            }
            effort_value = effort_map.get(effort_str.lower().split()[0] if effort_str else "days", 2)
            
            # Priority: High Impact, Low Effort = Priority 1
            if impact > 0.7 and effort_value <= 1:
                priority = 1  # Quick wins
            elif impact > 0.7 and effort_value > 1:
                priority = 2  # Strategic
            elif impact <= 0.7 and effort_value <= 2:
                priority = 3  # Fill-ins
            else:
                priority = 4  # Avoid
            
            item["priority"] = priority
        
        # Sort by priority (ascending), then by impact (descending)
        return sorted(
            debt_items,
            key=lambda x: (x.get("priority", 4), -x.get("impact_score", 0))
        )
    
    def _group_by_category(self, debt_items: List[Dict[str, Any]]) -> Dict[str, int]:
        """Group debt items by category."""
        grouped = {}
        for item in debt_items:
            raw = str(item.get("category", "unknown")).strip()
            category = CATEGORY_ALIASES.get(raw, raw)
            grouped[category] = grouped.get(category, 0) + 1
        return grouped
    
    def _group_by_severity(self, debt_items: List[Dict[str, Any]]) -> Dict[str, int]:
        """Group debt items by severity."""
        grouped = {}
        for item in debt_items:
            severity = item.get("severity", "low")
            grouped[severity] = grouped.get(severity, 0) + 1
        return grouped
    
    def generate_report(self, repository_id: str, analysis_result: Dict[str, Any]) -> Dict[str, Any]:
        """Generate comprehensive debt report."""
        return {
            "report_id": str(uuid.uuid4()),
            "repository_id": repository_id,
            "summary": {
                "total_debt_score": analysis_result["total_debt_score"],
                "debt_density": analysis_result["debt_density"],
                "total_items": analysis_result["total_items"],
                "items_by_category": analysis_result["items_by_category"],
                "items_by_severity": analysis_result["items_by_severity"],
            },
            "category_scores": analysis_result["category_scores"],
            "top_priority_items": analysis_result["debt_items"][:10],
            "quick_wins": [
                item for item in analysis_result["debt_items"]
                if item.get("priority") == 1
            ][:5],
            "critical_items": [
                item for item in analysis_result["debt_items"]
                if item.get("severity") == "critical"
            ],
            "generated_at": datetime.utcnow().isoformat(),
        }
