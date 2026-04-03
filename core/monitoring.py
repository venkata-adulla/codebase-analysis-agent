import logging
import time
from functools import wraps
from typing import Callable, Any
from prometheus_client import Counter, Histogram, Gauge

logger = logging.getLogger(__name__)

# Prometheus metrics
request_count = Counter(
    'api_requests_total',
    'Total number of API requests',
    ['method', 'endpoint', 'status']
)

request_duration = Histogram(
    'api_request_duration_seconds',
    'API request duration in seconds',
    ['method', 'endpoint']
)

active_analyses = Gauge(
    'active_analyses',
    'Number of active analyses'
)

agent_executions = Counter(
    'agent_executions_total',
    'Total number of agent executions',
    ['agent_name', 'status']
)


def monitor_request(func: Callable) -> Callable:
    """Decorator to monitor API requests."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.time()
        status = "success"
        
        try:
            result = await func(*args, **kwargs)
            return result
        except Exception as e:
            status = "error"
            logger.error(f"Request error: {e}")
            raise
        finally:
            duration = time.time() - start_time
            # Extract method and endpoint from function/request if available
            request_count.labels(method="unknown", endpoint=func.__name__, status=status).inc()
            request_duration.labels(method="unknown", endpoint=func.__name__).observe(duration)
    
    return wrapper


def track_agent_execution(agent_name: str):
    """Decorator to track agent executions."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            status = "success"
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                status = "error"
                logger.error(f"Agent execution error: {e}")
                raise
            finally:
                agent_executions.labels(agent_name=agent_name, status=status).inc()
        
        return wrapper
    return decorator
