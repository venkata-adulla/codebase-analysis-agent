import logging
import json
from typing import Any, Optional
from core.database import get_redis_client
from core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class CacheService:
    """Service for caching analysis results and parsed code."""
    
    def __init__(self):
        try:
            self.redis = get_redis_client()
            self.enabled = True
        except Exception as e:
            logger.warning(f"Redis not available, caching disabled: {e}")
            self.redis = None
            self.enabled = False
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        if not self.enabled:
            return None
        
        try:
            value = self.redis.get(key)
            if value:
                return json.loads(value)
        except Exception as e:
            logger.error(f"Error getting from cache: {e}")
        
        return None
    
    def set(self, key: str, value: Any, ttl: int = 3600):
        """Set value in cache with TTL."""
        if not self.enabled:
            return
        
        try:
            self.redis.setex(key, ttl, json.dumps(value))
        except Exception as e:
            logger.error(f"Error setting cache: {e}")
    
    def delete(self, key: str):
        """Delete value from cache."""
        if not self.enabled:
            return
        
        try:
            self.redis.delete(key)
        except Exception as e:
            logger.error(f"Error deleting from cache: {e}")
    
    def get_parsed_file(self, file_path: str, file_hash: str) -> Optional[Any]:
        """Get parsed file from cache."""
        cache_key = f"parsed_file:{file_hash}:{file_path}"
        return self.get(cache_key)
    
    def set_parsed_file(self, file_path: str, file_hash: str, parsed_data: Any):
        """Cache parsed file data."""
        cache_key = f"parsed_file:{file_hash}:{file_path}"
        self.set(cache_key, parsed_data, ttl=86400)  # 24 hours
    
    def get_dependency_graph(self, repository_id: str) -> Optional[Any]:
        """Get dependency graph from cache."""
        cache_key = f"dependency_graph:{repository_id}"
        return self.get(cache_key)
    
    def set_dependency_graph(self, repository_id: str, graph_data: Any):
        """Cache dependency graph."""
        cache_key = f"dependency_graph:{repository_id}"
        self.set(cache_key, graph_data, ttl=3600)  # 1 hour
