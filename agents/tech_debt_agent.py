import logging
from typing import Dict, Any
from agents.base_agent import BaseAgent, AgentState
from services.tech_debt_analyzer import TechDebtAnalyzer
from services.graph_service import GraphService
from services.openai_chat import chat_completions_create
from openai import OpenAI
from core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class TechDebtAgent(BaseAgent):
    """Agent that performs technical debt analysis and generates remediation plans."""
    
    def __init__(self):
        super().__init__(
            name="tech_debt_agent",
            description="Performs technical debt analysis and generates remediation plans"
        )
        self.debt_analyzer = TechDebtAnalyzer()
        self.graph_service = GraphService()
        self.client = None
        if settings.openai_api_key:
            self.client = OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url or None)
    
    def execute(self, state: AgentState) -> AgentState:
        """Execute tech debt analysis."""
        repository_id = state.get("repository_id")
        repository_path = state.get("repository_path")
        code_elements = state.get("code_elements", [])
        services = state.get("services", [])
        dependency_graph = state.get("dependency_graph")
        
        if not repository_id or not repository_path:
            logger.warning("Missing repository_id or repository_path for tech debt analysis")
            return state
        
        logger.info(f"Tech debt agent analyzing repository: {repository_id}")
        if dependency_graph is None and repository_id:
            try:
                dependency_graph = self.graph_service.get_dependency_graph(repository_id)
            except Exception as exc:
                logger.warning("Tech debt agent could not load dependency graph for %s: %s", repository_id, exc)
        
        # Run comprehensive debt analysis
        analysis_result = self.debt_analyzer.analyze_repository(
            repository_id=repository_id,
            repository_path=repository_path,
            code_elements=code_elements,
            services=services,
            dependency_graph=dependency_graph
        )
        
        # Generate remediation recommendations using LLM
        if self.client and analysis_result.get("debt_items"):
            top_items = analysis_result["debt_items"][:10]
            recommendations = self._generate_recommendations(top_items)
            analysis_result["ai_recommendations"] = recommendations
        
        # Generate remediation plan
        remediation_plan = self._generate_remediation_plan(analysis_result)
        analysis_result["remediation_plan"] = remediation_plan
        
        state.update("tech_debt_analysis", analysis_result)
        
        state.add_history({
            "agent": self.name,
            "action": "analyzed_tech_debt",
            "total_items": analysis_result.get("total_items", 0),
            "debt_score": analysis_result.get("total_debt_score", 0),
        })
        
        logger.info(f"Tech debt agent completed: {analysis_result.get('total_items', 0)} items found")
        return state
    
    def _generate_recommendations(
        self,
        debt_items: list
    ) -> Dict[str, Any]:
        """Generate AI-powered remediation recommendations."""
        if not self.client:
            return {}
        
        # Create prompt with top debt items
        items_summary = "\n".join([
            f"- {item.get('title')} ({item.get('severity')}): {item.get('description', '')[:100]}"
            for item in debt_items[:5]
        ])
        
        prompt = f"""Analyze the following technical debt items and provide remediation recommendations:

{items_summary}

For each item, provide:
1. Specific refactoring steps
2. Estimated effort (hours/days/weeks)
3. Priority level (1-4)
4. Quick wins that can be addressed immediately

Format as JSON with recommendations array."""

        try:
            response = chat_completions_create(
                self.client,
                messages=[
                    {"role": "system", "content": "You are a technical debt expert. Provide actionable remediation recommendations."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1000,
                response_format={"type": "json_object"}
            )
            
            import json
            recommendations = json.loads(response.choices[0].message.content)
            return recommendations
        
        except Exception as e:
            logger.error(f"Error generating recommendations: {e}")
            return {}
    
    def _generate_remediation_plan(
        self,
        analysis_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate a remediation plan with sprint allocation."""
        debt_items = analysis_result.get("debt_items", [])
        
        # Group by priority
        quick_wins = [item for item in debt_items if item.get("priority") == 1]
        strategic = [item for item in debt_items if item.get("priority") == 2]
        fill_ins = [item for item in debt_items if item.get("priority") == 3]
        
        # Estimate total effort
        effort_map = {"hours": 0.5, "days": 1, "weeks": 5}
        total_effort_days = sum(
            effort_map.get(item.get("effort_estimate", "days").lower().split()[0], 1)
            for item in debt_items
        )
        
        # Suggest sprint allocation
        sprint_allocation = {
            "sprint_1": {
                "items": quick_wins[:5],
                "estimated_effort": "2-3 days",
                "focus": "Quick wins for immediate impact"
            },
            "sprint_2_3": {
                "items": strategic[:10],
                "estimated_effort": "1-2 weeks",
                "focus": "Strategic improvements"
            },
            "backlog": {
                "items": fill_ins,
                "estimated_effort": "Ongoing",
                "focus": "Fill-in work during slower periods"
            }
        }
        
        return {
            "total_estimated_effort": f"{total_effort_days} days",
            "priority_breakdown": {
                "quick_wins": len(quick_wins),
                "strategic": len(strategic),
                "fill_ins": len(fill_ins),
            },
            "sprint_allocation": sprint_allocation,
            "roi_analysis": {
                "quick_wins_roi": "High - Low effort, High impact",
                "strategic_roi": "Medium - High effort, High impact",
                "fill_ins_roi": "Low - Low effort, Low impact",
            }
        }
