import logging
from typing import List, Dict, Any, Optional
from services.graph_service import GraphService

logger = logging.getLogger(__name__)


class ImpactEngine:
    """Engine for analyzing change impact."""
    
    def __init__(self):
        self.graph_service = GraphService()
    
    def analyze_impact(
        self,
        repository_id: str,
        change_description: str,
        affected_files: Optional[List[str]] = None,
        affected_services: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Analyze the impact of a change."""
        impacted_services = []
        
        # If specific services are affected, analyze those
        if affected_services:
            for service_id in affected_services:
                dependents = self.graph_service.find_impacted_services(service_id)
                for dependent in dependents:
                    if dependent not in impacted_services:
                        impacted_services.append({
                            "service_id": dependent["service_id"],
                            "service_name": dependent["name"],
                            "impact_score": self._calculate_impact_score(
                                dependent["depth"],
                                change_description
                            ),
                            "impact_type": "transitive",
                            "reason": f"Depends on {service_id}",
                            "depth": dependent["depth"],
                        })
        
        # If files are affected, find their services
        elif affected_files:
            # This would require mapping files to services
            # For now, we'll use a simplified approach
            pass
        
        # Calculate risk level
        risk_level = self._calculate_risk_level(impacted_services)
        
        # Generate recommendations
        recommendations = self._generate_recommendations(impacted_services, risk_level)
        
        return {
            "change_description": change_description,
            "impacted_services": impacted_services,
            "risk_level": risk_level,
            "recommendations": recommendations,
            "total_impacted": len(impacted_services),
        }
    
    def _calculate_impact_score(
        self,
        depth: int,
        change_description: str
    ) -> float:
        """Calculate impact score (0-1)."""
        # Deeper dependencies have lower impact scores
        base_score = 1.0 / (depth + 1)
        
        # Adjust based on change description keywords
        high_impact_keywords = ["breaking", "remove", "delete", "deprecate"]
        low_impact_keywords = ["add", "enhance", "optimize"]
        
        description_lower = change_description.lower()
        
        if any(keyword in description_lower for keyword in high_impact_keywords):
            base_score *= 1.5
        elif any(keyword in description_lower for keyword in low_impact_keywords):
            base_score *= 0.7
        
        return min(base_score, 1.0)
    
    def _calculate_risk_level(self, impacted_services: List[Dict[str, Any]]) -> str:
        """Calculate overall risk level."""
        if not impacted_services:
            return "low"
        
        high_impact_count = sum(
            1 for s in impacted_services
            if s["impact_score"] > 0.7
        )
        
        if high_impact_count > 5:
            return "critical"
        elif high_impact_count > 2:
            return "high"
        elif high_impact_count > 0:
            return "medium"
        else:
            return "low"
    
    def _generate_recommendations(
        self,
        impacted_services: List[Dict[str, Any]],
        risk_level: str
    ) -> List[str]:
        """Generate recommendations based on impact analysis."""
        recommendations = []
        
        if risk_level == "critical":
            recommendations.append("This change has critical impact. Review all affected services carefully.")
            recommendations.append("Consider staging the change in phases.")
            recommendations.append("Ensure comprehensive testing of all dependent services.")
        elif risk_level == "high":
            recommendations.append("This change has high impact. Test affected services thoroughly.")
            recommendations.append("Consider backward compatibility if possible.")
        elif risk_level == "medium":
            recommendations.append("This change has medium impact. Review affected services.")
        else:
            recommendations.append("This change has low impact. Standard testing should suffice.")
        
        if len(impacted_services) > 10:
            recommendations.append(f"Large number of affected services ({len(impacted_services)}). Consider impact mitigation strategies.")
        
        return recommendations
