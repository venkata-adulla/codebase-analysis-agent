import logging
from typing import Dict, Any
from agents.base_agent import BaseAgent, AgentState
from openai import OpenAI
from core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class DocumentationAgent(BaseAgent):
    """Agent that generates service documentation using LLM."""
    
    def __init__(self):
        super().__init__(
            name="documentation_agent",
            description="Generates service documentation using LLM"
        )
        self.client = None
        if settings.openai_api_key:
            self.client = OpenAI(api_key=settings.openai_api_key)
    
    def execute(self, state: AgentState) -> AgentState:
        """Execute documentation generation."""
        services = state.get("services", [])
        
        if not services:
            logger.warning("No services found for documentation")
            return state
        
        logger.info(f"Documentation agent generating docs for {len(services)} services")
        
        documentation = {}
        
        for service in services:
            try:
                doc = self._generate_documentation(service, state)
                documentation[service["id"]] = doc
            except Exception as e:
                logger.error(f"Error generating documentation for {service['id']}: {e}")
                documentation[service["id"]] = {
                    "error": str(e),
                    "description": f"Service: {service['name']}",
                }
        
        state.update("documentation", documentation)
        
        state.add_history({
            "agent": self.name,
            "action": "generated_documentation",
            "services_documented": len(documentation),
        })
        
        logger.info(f"Documentation agent completed: {len(documentation)} services documented")
        return state
    
    def _generate_documentation(
        self,
        service: Dict[str, Any],
        state: AgentState
    ) -> Dict[str, Any]:
        """Generate documentation for a service."""
        if not self.client:
            return {
                "description": f"Service: {service['name']}",
                "language": service.get("language", "unknown"),
                "note": "OpenAI API key not configured",
            }
        
        # Get code elements for this service
        code_elements = state.get("code_elements", [])
        service_elements = [
            e for e in code_elements
            if service["path"] in e.get("file_path", "")
        ]
        
        # Create prompt
        prompt = f"""Generate documentation for a service named {service['name']} written in {service.get('language', 'unknown')}.

Service path: {service.get('path', '')}

Code elements found:
{len(service_elements)} elements

Please provide:
1. A brief description of what this service does
2. Main functionality
3. Key components
4. Dependencies
5. API endpoints (if any)

Keep it concise and professional."""

        try:
            response = self.client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": "You are a technical documentation expert."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=500,
            )
            
            doc_text = response.choices[0].message.content
            
            return {
                "description": doc_text,
                "language": service.get("language", "unknown"),
                "elements_count": len(service_elements),
            }
        except Exception as e:
            logger.error(f"Error calling OpenAI API: {e}")
            return {
                "description": f"Service: {service['name']}",
                "language": service.get("language", "unknown"),
                "error": str(e),
            }
