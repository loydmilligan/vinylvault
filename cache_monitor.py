#!/usr/bin/env python3
"""
VinylVault Image Cache Monitor

A simple monitoring script for the image cache system that provides:
- Cache performance metrics
- Memory usage monitoring
- Cleanup automation
- Health checks
- Performance reporting
"""

import time
import logging
import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any

from image_cache import get_image_cache, initialize_image_cache
from config import Config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class CacheMonitor:
    """Monitor and manage image cache performance."""
    
    def __init__(self, cache_dir: Path, database_path: Path):
        self.cache_dir = cache_dir
        self.database_path = database_path
        self.cache = None
        self.start_time = datetime.now()
        
    def initialize(self) -> bool:
        """Initialize the cache system."""
        try:
            success = initialize_image_cache(
                self.cache_dir,
                self.database_path,
                max_cache_size=2 * 1024 * 1024 * 1024  # 2GB
            )
            
            if success:
                self.cache = get_image_cache()
                logger.info("Cache monitor initialized successfully")
                return True
            else:
                logger.error("Failed to initialize cache")
                return False
                
        except Exception as e:
            logger.error(f"Error initializing cache monitor: {e}")
            return False
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get comprehensive performance metrics."""
        if not self.cache:
            return {}
        
        try:
            # Get cache stats
            stats = self.cache.get_cache_stats()
            
            # Get LRU cache stats
            lru_stats = self.cache.lru_cache.get_stats()
            
            # Calculate additional metrics
            uptime = (datetime.now() - self.start_time).total_seconds()
            cache_efficiency = (lru_stats['hits'] / max(lru_stats['total_requests'], 1)) * 100
            
            # Memory usage (approximate)
            memory_usage = self.cache.lru_cache.current_size_bytes
            memory_limit = self.cache.lru_cache.max_size_bytes
            memory_usage_percent = (memory_usage / memory_limit) * 100
            
            # Disk usage
            disk_usage = self._calculate_disk_usage()
            
            return {
                'timestamp': datetime.now().isoformat(),
                'uptime_seconds': uptime,
                'cache_stats': {
                    'total_entries': stats.total_entries,
                    'thumbnail_count': stats.thumbnail_count,
                    'detail_count': stats.detail_count,
                    'total_size_bytes': stats.total_size_bytes,
                    'total_size_mb': stats.total_size_bytes / (1024 * 1024),
                    'cache_limit_bytes': stats.cache_limit_bytes,
                    'cache_limit_mb': stats.cache_limit_bytes / (1024 * 1024),
                    'available_space_bytes': stats.available_space_bytes,
                    'available_space_mb': stats.available_space_bytes / (1024 * 1024)
                },
                'performance': {
                    'hit_rate': lru_stats['hit_rate'],
                    'cache_efficiency': cache_efficiency,
                    'total_requests': lru_stats['total_requests'],
                    'hits': lru_stats['hits'],
                    'misses': lru_stats['misses'],
                    'evictions': lru_stats['evictions']
                },
                'memory': {
                    'usage_bytes': memory_usage,
                    'usage_mb': memory_usage / (1024 * 1024),
                    'limit_bytes': memory_limit,
                    'limit_mb': memory_limit / (1024 * 1024),
                    'usage_percent': memory_usage_percent
                },
                'disk': disk_usage
            }
            
        except Exception as e:
            logger.error(f"Error getting performance metrics: {e}")
            return {}
    
    def _calculate_disk_usage(self) -> Dict[str, Any]:
        """Calculate disk usage for cache directories."""
        try:
            total_size = 0
            file_count = 0
            
            for size_dir in ['thumbnails', 'detail', 'placeholders']:
                size_path = self.cache_dir / size_dir
                if size_path.exists():
                    for file_path in size_path.glob('*.webp'):
                        try:
                            total_size += file_path.stat().st_size
                            file_count += 1
                        except OSError:
                            continue
            
            return {
                'total_size_bytes': total_size,
                'total_size_mb': total_size / (1024 * 1024),
                'file_count': file_count
            }
            
        except Exception as e:
            logger.error(f"Error calculating disk usage: {e}")
            return {
                'total_size_bytes': 0,
                'total_size_mb': 0,
                'file_count': 0
            }
    
    def health_check(self) -> Dict[str, Any]:
        """Perform health check on cache system."""
        health = {
            'timestamp': datetime.now().isoformat(),
            'status': 'healthy',
            'checks': {}
        }
        
        try:
            # Check if cache is initialized
            if not self.cache:
                health['status'] = 'unhealthy'
                health['checks']['cache_initialized'] = False
                return health
            
            health['checks']['cache_initialized'] = True
            
            # Check database connectivity
            try:
                stats = self.cache.get_cache_stats()
                health['checks']['database_accessible'] = True
            except Exception as e:
                health['checks']['database_accessible'] = False
                health['status'] = 'degraded'
                logger.error(f"Database check failed: {e}")
            
            # Check disk space
            disk_usage = self._calculate_disk_usage()
            cache_limit = self.cache.max_cache_size
            usage_percent = (disk_usage['total_size_bytes'] / cache_limit) * 100
            
            if usage_percent > 95:
                health['checks']['disk_space'] = 'critical'
                health['status'] = 'degraded'
            elif usage_percent > 80:
                health['checks']['disk_space'] = 'warning'
            else:
                health['checks']['disk_space'] = 'ok'
            
            # Check performance
            metrics = self.get_performance_metrics()
            if metrics:
                hit_rate = metrics.get('performance', {}).get('hit_rate', 0)
                if hit_rate < 50:
                    health['checks']['performance'] = 'poor'
                    health['status'] = 'degraded'
                elif hit_rate < 70:
                    health['checks']['performance'] = 'fair'
                else:
                    health['checks']['performance'] = 'good'
            
            # Check cache directories
            required_dirs = ['thumbnails', 'detail', 'placeholders']
            missing_dirs = []
            
            for dir_name in required_dirs:
                dir_path = self.cache_dir / dir_name
                if not dir_path.exists():
                    missing_dirs.append(dir_name)
            
            if missing_dirs:
                health['checks']['cache_directories'] = f'missing: {missing_dirs}'
                health['status'] = 'degraded'
            else:
                health['checks']['cache_directories'] = 'ok'
            
        except Exception as e:
            health['status'] = 'unhealthy'
            health['error'] = str(e)
            logger.error(f"Health check failed: {e}")
        
        return health
    
    def cleanup_old_entries(self, max_age_days: int = 30) -> Dict[str, Any]:
        """Clean up old cache entries."""
        if not self.cache:
            return {'error': 'Cache not initialized'}
        
        try:
            logger.info(f"Starting cleanup of entries older than {max_age_days} days")
            
            # Get metrics before cleanup
            before_stats = self.cache.get_cache_stats()
            
            # Perform cleanup
            cleaned_count = self.cache.cleanup_cache(max_age_days)
            
            # Get metrics after cleanup
            after_stats = self.cache.get_cache_stats()
            
            # Calculate savings
            size_saved = before_stats.total_size_bytes - after_stats.total_size_bytes
            
            result = {
                'timestamp': datetime.now().isoformat(),
                'max_age_days': max_age_days,
                'entries_cleaned': cleaned_count,
                'size_saved_bytes': size_saved,
                'size_saved_mb': size_saved / (1024 * 1024),
                'before': {
                    'entries': before_stats.total_entries,
                    'size_mb': before_stats.total_size_bytes / (1024 * 1024)
                },
                'after': {
                    'entries': after_stats.total_entries,
                    'size_mb': after_stats.total_size_bytes / (1024 * 1024)
                }
            }
            
            logger.info(f"Cleanup completed: {cleaned_count} entries, {size_saved / (1024*1024):.1f}MB saved")
            return result
            
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
            return {'error': str(e)}
    
    def generate_report(self) -> str:
        """Generate a comprehensive performance report."""
        try:
            metrics = self.get_performance_metrics()
            health = self.health_check()
            
            if not metrics:
                return "Error: Unable to generate report - no metrics available"
            
            report = []
            report.append("VinylVault Image Cache Performance Report")
            report.append("=" * 50)
            report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            report.append(f"Uptime: {metrics.get('uptime_seconds', 0) / 3600:.1f} hours")
            report.append("")
            
            # Cache Statistics
            cache_stats = metrics.get('cache_stats', {})
            report.append("Cache Statistics:")
            report.append("-" * 20)
            report.append(f"Total Entries: {cache_stats.get('total_entries', 0)}")
            report.append(f"  - Thumbnails: {cache_stats.get('thumbnail_count', 0)}")
            report.append(f"  - Detail Images: {cache_stats.get('detail_count', 0)}")
            report.append(f"Total Size: {cache_stats.get('total_size_mb', 0):.1f} MB")
            report.append(f"Cache Limit: {cache_stats.get('cache_limit_mb', 0):.1f} MB")
            report.append(f"Available Space: {cache_stats.get('available_space_mb', 0):.1f} MB")
            report.append("")
            
            # Performance Metrics
            performance = metrics.get('performance', {})
            report.append("Performance Metrics:")
            report.append("-" * 20)
            report.append(f"Hit Rate: {performance.get('hit_rate', 0):.1f}%")
            report.append(f"Total Requests: {performance.get('total_requests', 0)}")
            report.append(f"Cache Hits: {performance.get('hits', 0)}")
            report.append(f"Cache Misses: {performance.get('misses', 0)}")
            report.append(f"Evictions: {performance.get('evictions', 0)}")
            report.append("")
            
            # Memory Usage
            memory = metrics.get('memory', {})
            report.append("Memory Usage:")
            report.append("-" * 15)
            report.append(f"Current Usage: {memory.get('usage_mb', 0):.1f} MB ({memory.get('usage_percent', 0):.1f}%)")
            report.append(f"Memory Limit: {memory.get('limit_mb', 0):.1f} MB")
            report.append("")
            
            # Health Status
            report.append("Health Status:")
            report.append("-" * 15)
            report.append(f"Overall Status: {health.get('status', 'unknown').upper()}")
            
            checks = health.get('checks', {})
            for check, status in checks.items():
                report.append(f"  {check.replace('_', ' ').title()}: {status}")
            
            return "\n".join(report)
            
        except Exception as e:
            logger.error(f"Error generating report: {e}")
            return f"Error generating report: {str(e)}"
    
    def continuous_monitor(self, interval_seconds: int = 300, cleanup_interval_hours: int = 24):
        """Run continuous monitoring with periodic cleanup."""
        logger.info(f"Starting continuous monitoring (interval: {interval_seconds}s)")
        
        last_cleanup = datetime.now()
        
        try:
            while True:
                # Perform health check
                health = self.health_check()
                logger.info(f"Health status: {health['status']}")
                
                # Log performance metrics periodically
                if time.time() % (interval_seconds * 4) < interval_seconds:
                    metrics = self.get_performance_metrics()
                    if metrics:
                        performance = metrics.get('performance', {})
                        cache_stats = metrics.get('cache_stats', {})
                        logger.info(
                            f"Performance: {performance.get('hit_rate', 0):.1f}% hit rate, "
                            f"{cache_stats.get('total_entries', 0)} entries, "
                            f"{cache_stats.get('total_size_mb', 0):.1f}MB"
                        )
                
                # Perform cleanup if needed
                now = datetime.now()
                if (now - last_cleanup).total_seconds() > (cleanup_interval_hours * 3600):
                    logger.info("Performing scheduled cleanup")
                    cleanup_result = self.cleanup_old_entries()
                    if 'error' not in cleanup_result:
                        logger.info(f"Cleanup completed: {cleanup_result.get('entries_cleaned', 0)} entries removed")
                    last_cleanup = now
                
                # Wait for next check
                time.sleep(interval_seconds)
                
        except KeyboardInterrupt:
            logger.info("Monitoring stopped by user")
        except Exception as e:
            logger.error(f"Error in continuous monitoring: {e}")

def main():
    """Main entry point for cache monitor."""
    parser = argparse.ArgumentParser(description='VinylVault Image Cache Monitor')
    parser.add_argument('--action', choices=['status', 'health', 'cleanup', 'report', 'monitor'],
                       default='status', help='Action to perform')
    parser.add_argument('--cleanup-days', type=int, default=30,
                       help='Maximum age for cleanup (days)')
    parser.add_argument('--monitor-interval', type=int, default=300,
                       help='Monitoring interval (seconds)')
    parser.add_argument('--cache-dir', type=str, default='cache/covers',
                       help='Cache directory path')
    parser.add_argument('--database', type=str, default='cache/vinylvault.db',
                       help='Database path')
    parser.add_argument('--json', action='store_true',
                       help='Output in JSON format')
    
    args = parser.parse_args()
    
    # Initialize monitor
    cache_dir = Path(args.cache_dir)
    database_path = Path(args.database)
    
    monitor = CacheMonitor(cache_dir, database_path)
    
    if not monitor.initialize():
        print("Failed to initialize cache monitor")
        return 1
    
    # Perform requested action
    try:
        if args.action == 'status':
            metrics = monitor.get_performance_metrics()
            if args.json:
                print(json.dumps(metrics, indent=2))
            else:
                if metrics:
                    cache_stats = metrics.get('cache_stats', {})
                    performance = metrics.get('performance', {})
                    print(f"Cache Status:")
                    print(f"  Entries: {cache_stats.get('total_entries', 0)}")
                    print(f"  Size: {cache_stats.get('total_size_mb', 0):.1f} MB")
                    print(f"  Hit Rate: {performance.get('hit_rate', 0):.1f}%")
                else:
                    print("No metrics available")
        
        elif args.action == 'health':
            health = monitor.health_check()
            if args.json:
                print(json.dumps(health, indent=2))
            else:
                print(f"Health Status: {health.get('status', 'unknown').upper()}")
                checks = health.get('checks', {})
                for check, status in checks.items():
                    print(f"  {check.replace('_', ' ').title()}: {status}")
        
        elif args.action == 'cleanup':
            result = monitor.cleanup_old_entries(args.cleanup_days)
            if args.json:
                print(json.dumps(result, indent=2))
            else:
                if 'error' in result:
                    print(f"Cleanup failed: {result['error']}")
                else:
                    print(f"Cleanup completed:")
                    print(f"  Entries removed: {result.get('entries_cleaned', 0)}")
                    print(f"  Space saved: {result.get('size_saved_mb', 0):.1f} MB")
        
        elif args.action == 'report':
            report = monitor.generate_report()
            print(report)
        
        elif args.action == 'monitor':
            monitor.continuous_monitor(args.monitor_interval)
        
        return 0
        
    except Exception as e:
        logger.error(f"Error executing action '{args.action}': {e}")
        return 1

if __name__ == '__main__':
    exit(main())