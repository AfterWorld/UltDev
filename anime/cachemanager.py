import time
import logging
from typing import Dict, Any, Optional, List
from collections import OrderedDict

log = logging.getLogger("red.animeforum.cache_manager")

class CacheManager:
    """Efficient in-memory cache with expiration and LRU eviction"""
    
    def __init__(self, expiry: int = 3600, max_size: int = 1000):
        """
        Initialize cache manager
        
        Parameters:
        -----------
        expiry: int
            Default cache expiry time in seconds
        max_size: int
            Maximum number of items to store before evicting
        """
        self.expiry = expiry
        self.max_size = max_size
        self.cache = OrderedDict()  # {key: (value, expiry_timestamp)}
        
    def get(self, key: str) -> Optional[Any]:
        """Get a value from the cache if it exists and isn't expired"""
        if key not in self.cache:
            return None
            
        value, expiry_time = self.cache[key]
        
        # Check if expired
        if expiry_time < time.time():
            self.delete(key)
            return None
            
        # Move to end (most recently used)
        self.cache.move_to_end(key)
        return value
        
    def set(self, key: str, value: Any, expiry: int = None) -> None:
        """
        Add or update a value in the cache
        
        Parameters:
        -----------
        key: str
            Cache key
        value: Any
            Value to store
        expiry: int, optional
            Custom expiry time in seconds, or None for default
        """
        # Use default expiry if none provided
        if expiry is None:
            expiry = self.expiry
            
        # Calculate expiry timestamp
        expiry_time = time.time() + expiry
        
        # Check if we need to evict (only if adding new key)
        if key not in self.cache and len(self.cache) >= self.max_size:
            # Remove oldest (first) item
            self.cache.popitem(last=False)
            
        # Add or update the item
        self.cache[key] = (value, expiry_time)
        # Move to end (most recently used)
        self.cache.move_to_end(key)
        
    def delete(self, key: str) -> bool:
        """
        Delete a key from the cache
        
        Returns:
        --------
        bool: True if key was found and deleted, False otherwise
        """
        if key in self.cache:
            del self.cache[key]
            return True
        return False
        
    def clear(self) -> None:
        """Clear all items from the cache"""
        self.cache.clear()
        
    def get_many(self, keys: List[str]) -> Dict[str, Any]:
        """
        Get multiple values from the cache at once
        
        Returns:
        --------
        Dict[str, Any]: Dictionary of {key: value} for all valid keys
        """
        result = {}
        for key in keys:
            value = self.get(key)
            if value is not None:
                result[key] = value
        return result
        
    def set_many(self, values: Dict[str, Any], expiry: int = None) -> None:
        """
        Set multiple values in the cache at once
        
        Parameters:
        -----------
        values: Dict[str, Any]
            Dictionary of {key: value} pairs to store
        expiry: int, optional
            Custom expiry time in seconds, or None for default
        """
        for key, value in values.items():
            self.set(key, value, expiry)
            
    def clean_expired(self) -> int:
        """
        Remove all expired items from the cache
        
        Returns:
        --------
        int: Number of items removed
        """
        current_time = time.time()
        keys_to_delete = []
        
        # Find expired keys
        for key, (_, expiry_time) in self.cache.items():
            if expiry_time < current_time:
                keys_to_delete.append(key)
                
        # Delete expired keys
        for key in keys_to_delete:
            self.delete(key)
            
        return len(keys_to_delete)
        
    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics
        
        Returns:
        --------
        Dict[str, Any]: Dictionary with cache statistics
        """
        return {
            "size": len(self.cache),
            "max_size": self.max_size,
            "default_expiry": self.expiry,
            "expired_items": self.clean_expired()
        }
    
    def exists(self, key: str) -> bool:
        """
        Check if a key exists in the cache and is not expired
        
        Returns:
        --------
        bool: True if the key exists and is not expired
        """
        if key not in self.cache:
            return False
            
        _, expiry_time = self.cache[key]
        
        # Check if expired
        if expiry_time < time.time():
            self.delete(key)
            return False
            
        return True
        
    def touch(self, key: str, expiry: int = None) -> bool:
        """
        Update the expiry time for a key
        
        Parameters:
        -----------
        key: str
            Cache key
        expiry: int, optional
            New expiry time in seconds, or None for default
            
        Returns:
        --------
        bool: True if the key exists and expiry was updated
        """
        if key not in self.cache:
            return False
            
        value, _ = self.cache[key]
        
        # Use default expiry if none provided
        if expiry is None:
            expiry = self.expiry
            
        # Calculate new expiry timestamp
        expiry_time = time.time() + expiry
        
        # Update the expiry time
        self.cache[key] = (value, expiry_time)
        
        # Move to end (most recently used)
        self.cache.move_to_end(key)
        
        return True
        
    def get_keys(self) -> List[str]:
        """
        Get all keys in the cache
        
        Returns:
        --------
        List[str]: List of all keys in the cache
        """
        # Clean expired items first
        self.clean_expired()
        
        # Return all remaining keys
        return list(self.cache.keys())
        
    def get_expired_keys(self) -> List[str]:
        """
        Get all expired keys in the cache
        
        Returns:
        --------
        List[str]: List of all expired keys
        """
        current_time = time.time()
        expired_keys = []
        
        for key, (_, expiry_time) in self.cache.items():
            if expiry_time < current_time:
                expired_keys.append(key)
                
        return expired_keys
