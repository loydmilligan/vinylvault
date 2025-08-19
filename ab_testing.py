#!/usr/bin/env python3
"""
A/B Testing Framework for VinylVault Random Algorithm

This module provides tools for testing different algorithm configurations
and measuring their effectiveness through user feedback and engagement metrics.
"""

import json
import sqlite3
import random
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from collections import defaultdict
import hashlib

from random_algorithm import AlgorithmConfig, RandomAlgorithm

logger = logging.getLogger(__name__)


@dataclass
class ABTestConfig:
    """Configuration for A/B testing."""
    test_name: str
    description: str
    start_date: datetime
    end_date: datetime
    traffic_split: float  # Percentage of users in test group (0.0 - 1.0)
    control_config: AlgorithmConfig
    test_config: AlgorithmConfig
    active: bool = True
    
    
@dataclass
class ABTestResults:
    """Results from an A/B test."""
    test_name: str
    control_group_size: int
    test_group_size: int
    control_satisfaction: float
    test_satisfaction: float
    control_engagement: float  # Selections per session
    test_engagement: float
    statistical_significance: float
    winner: str  # 'control', 'test', or 'inconclusive'
    confidence_level: float


class ABTestManager:
    """Manages A/B tests for the random algorithm."""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._initialize_ab_tables()
    
    def _initialize_ab_tables(self):
        """Initialize A/B testing database tables."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            
            # A/B test configurations table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ab_tests (
                    id INTEGER PRIMARY KEY,
                    test_name TEXT UNIQUE NOT NULL,
                    description TEXT,
                    start_date TIMESTAMP,
                    end_date TIMESTAMP,
                    traffic_split REAL DEFAULT 0.5,
                    control_config TEXT,  -- JSON
                    test_config TEXT,     -- JSON
                    active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # User assignments table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ab_user_assignments (
                    id INTEGER PRIMARY KEY,
                    session_id TEXT,
                    test_name TEXT,
                    group_name TEXT,  -- 'control' or 'test'
                    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (test_name) REFERENCES ab_tests (test_name)
                )
            """)
            
            # Test metrics table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ab_test_metrics (
                    id INTEGER PRIMARY KEY,
                    test_name TEXT,
                    session_id TEXT,
                    group_name TEXT,
                    metric_name TEXT,  -- 'selection', 'feedback', 'engagement'
                    metric_value REAL,
                    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (test_name) REFERENCES ab_tests (test_name)
                )
            """)
            
            # Create indexes
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ab_assignments_session ON ab_user_assignments (session_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ab_assignments_test ON ab_user_assignments (test_name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ab_metrics_test ON ab_test_metrics (test_name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ab_metrics_session ON ab_test_metrics (session_id)")
            
            conn.commit()
    
    def create_test(self, test_config: ABTestConfig) -> bool:
        """Create a new A/B test."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO ab_tests 
                    (test_name, description, start_date, end_date, traffic_split, 
                     control_config, test_config, active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    test_config.test_name,
                    test_config.description,
                    test_config.start_date.isoformat(),
                    test_config.end_date.isoformat(),
                    test_config.traffic_split,
                    json.dumps(asdict(test_config.control_config)),
                    json.dumps(asdict(test_config.test_config)),
                    test_config.active
                ))
                conn.commit()
                
            logger.info(f"Created A/B test: {test_config.test_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error creating A/B test: {e}")
            return False
    
    def assign_user_to_group(self, session_id: str, test_name: str = None) -> Tuple[str, AlgorithmConfig]:
        """Assign user to control or test group and return the configuration."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                # Get active test if not specified
                if not test_name:
                    cursor = conn.execute("""
                        SELECT test_name FROM ab_tests 
                        WHERE active = 1 
                          AND start_date <= datetime('now')
                          AND end_date >= datetime('now')
                        ORDER BY created_at DESC
                        LIMIT 1
                    """)
                    test_row = cursor.fetchone()
                    if not test_row:
                        # No active test, return default config
                        return 'control', AlgorithmConfig()
                    test_name = test_row['test_name']
                
                # Check if user is already assigned
                cursor = conn.execute("""
                    SELECT group_name FROM ab_user_assignments
                    WHERE session_id = ? AND test_name = ?
                """, (session_id, test_name))
                assignment = cursor.fetchone()
                
                if assignment:
                    group = assignment['group_name']
                else:
                    # Assign user to group using deterministic hash
                    hash_input = f"{session_id}:{test_name}"
                    hash_value = int(hashlib.md5(hash_input.encode()).hexdigest(), 16)
                    hash_ratio = (hash_value % 1000) / 1000.0
                    
                    # Get test configuration
                    cursor = conn.execute("""
                        SELECT traffic_split FROM ab_tests WHERE test_name = ?
                    """, (test_name,))
                    test_row = cursor.fetchone()
                    
                    if not test_row:
                        return 'control', AlgorithmConfig()
                    
                    traffic_split = test_row['traffic_split']
                    group = 'test' if hash_ratio < traffic_split else 'control'
                    
                    # Record assignment
                    conn.execute("""
                        INSERT INTO ab_user_assignments (session_id, test_name, group_name)
                        VALUES (?, ?, ?)
                    """, (session_id, test_name, group))
                    conn.commit()
                
                # Get appropriate configuration
                cursor = conn.execute("""
                    SELECT control_config, test_config FROM ab_tests WHERE test_name = ?
                """, (test_name,))
                config_row = cursor.fetchone()
                
                if not config_row:
                    return 'control', AlgorithmConfig()
                
                if group == 'test':
                    config_dict = json.loads(config_row['test_config'])
                else:
                    config_dict = json.loads(config_row['control_config'])
                
                config = AlgorithmConfig(**config_dict)
                return group, config
                
        except Exception as e:
            logger.error(f"Error assigning user to group: {e}")
            return 'control', AlgorithmConfig()
    
    def record_metric(self, session_id: str, metric_name: str, metric_value: float, test_name: str = None):
        """Record a metric for A/B testing analysis."""
        try:
            if not test_name:
                # Get current active test
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute("""
                        SELECT test_name FROM ab_tests 
                        WHERE active = 1 
                          AND start_date <= datetime('now')
                          AND end_date >= datetime('now')
                        ORDER BY created_at DESC
                        LIMIT 1
                    """)
                    test_row = cursor.fetchone()
                    if not test_row:
                        return
                    test_name = test_row[0]
            
            # Get user's group assignment
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    SELECT group_name FROM ab_user_assignments
                    WHERE session_id = ? AND test_name = ?
                """, (session_id, test_name))
                assignment = cursor.fetchone()
                
                if not assignment:
                    return
                
                group = assignment[0]
                
                # Record metric
                conn.execute("""
                    INSERT INTO ab_test_metrics 
                    (test_name, session_id, group_name, metric_name, metric_value)
                    VALUES (?, ?, ?, ?, ?)
                """, (test_name, session_id, group, metric_name, metric_value))
                conn.commit()
                
        except Exception as e:
            logger.error(f"Error recording A/B test metric: {e}")
    
    def get_test_results(self, test_name: str) -> Optional[ABTestResults]:
        """Analyze and return results for an A/B test."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                # Get group sizes
                cursor = conn.execute("""
                    SELECT group_name, COUNT(DISTINCT session_id) as users
                    FROM ab_user_assignments
                    WHERE test_name = ?
                    GROUP BY group_name
                """, (test_name,))
                
                group_sizes = {row['group_name']: row['users'] for row in cursor.fetchall()}
                control_size = group_sizes.get('control', 0)
                test_size = group_sizes.get('test', 0)
                
                if control_size == 0 or test_size == 0:
                    return None
                
                # Calculate satisfaction scores (from feedback)
                cursor = conn.execute("""
                    SELECT group_name, AVG(metric_value) as avg_satisfaction
                    FROM ab_test_metrics
                    WHERE test_name = ? AND metric_name = 'feedback'
                    GROUP BY group_name
                """, (test_name,))
                
                satisfaction_scores = {row['group_name']: row['avg_satisfaction'] or 0 
                                     for row in cursor.fetchall()}
                control_satisfaction = satisfaction_scores.get('control', 0.0)
                test_satisfaction = satisfaction_scores.get('test', 0.0)
                
                # Calculate engagement (selections per user)
                cursor = conn.execute("""
                    SELECT group_name, COUNT(*) * 1.0 / COUNT(DISTINCT session_id) as avg_engagement
                    FROM ab_test_metrics
                    WHERE test_name = ? AND metric_name = 'selection'
                    GROUP BY group_name
                """, (test_name,))
                
                engagement_scores = {row['group_name']: row['avg_engagement'] or 0 
                                   for row in cursor.fetchall()}
                control_engagement = engagement_scores.get('control', 0.0)
                test_engagement = engagement_scores.get('test', 0.0)
                
                # Simple statistical significance calculation
                # (In production, you'd want more sophisticated analysis)
                total_users = control_size + test_size
                min_sample_size = 100
                
                if total_users < min_sample_size:
                    significance = 0.0
                    winner = 'inconclusive'
                    confidence = 0.0
                else:
                    # Basic effect size calculation
                    satisfaction_diff = abs(test_satisfaction - control_satisfaction)
                    engagement_diff = abs(test_engagement - control_engagement)
                    
                    # Simple confidence calculation based on sample size and effect size
                    confidence = min(0.95, (total_users / min_sample_size) * (satisfaction_diff + engagement_diff))
                    significance = confidence
                    
                    # Determine winner
                    if confidence > 0.8:
                        if test_satisfaction > control_satisfaction and test_engagement >= control_engagement:
                            winner = 'test'
                        elif control_satisfaction > test_satisfaction and control_engagement >= test_engagement:
                            winner = 'control'
                        else:
                            winner = 'inconclusive'
                    else:
                        winner = 'inconclusive'
                
                return ABTestResults(
                    test_name=test_name,
                    control_group_size=control_size,
                    test_group_size=test_size,
                    control_satisfaction=control_satisfaction,
                    test_satisfaction=test_satisfaction,
                    control_engagement=control_engagement,
                    test_engagement=test_engagement,
                    statistical_significance=significance,
                    winner=winner,
                    confidence_level=confidence
                )
                
        except Exception as e:
            logger.error(f"Error getting test results: {e}")
            return None
    
    def list_tests(self) -> List[Dict[str, Any]]:
        """List all A/B tests."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("""
                    SELECT * FROM ab_tests ORDER BY created_at DESC
                """)
                
                tests = []
                for row in cursor.fetchall():
                    test_dict = dict(row)
                    test_dict['start_date'] = datetime.fromisoformat(test_dict['start_date'])
                    test_dict['end_date'] = datetime.fromisoformat(test_dict['end_date'])
                    test_dict['created_at'] = datetime.fromisoformat(test_dict['created_at'])
                    tests.append(test_dict)
                
                return tests
                
        except Exception as e:
            logger.error(f"Error listing tests: {e}")
            return []
    
    def stop_test(self, test_name: str) -> bool:
        """Stop an active A/B test."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    UPDATE ab_tests SET active = 0 WHERE test_name = ?
                """, (test_name,))
                conn.commit()
                
            logger.info(f"Stopped A/B test: {test_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error stopping test: {e}")
            return False


# Predefined test configurations for common scenarios
def create_rating_weight_test() -> ABTestConfig:
    """Create a test for different rating weight values."""
    return ABTestConfig(
        test_name="rating_weight_boost",
        description="Test higher rating weight to favor highly rated albums",
        start_date=datetime.now(),
        end_date=datetime.now() + timedelta(days=14),
        traffic_split=0.5,
        control_config=AlgorithmConfig(rating_weight=2.0),
        test_config=AlgorithmConfig(rating_weight=3.0)
    )


def create_diversity_weight_test() -> ABTestConfig:
    """Create a test for different genre diversity weights."""
    return ABTestConfig(
        test_name="diversity_emphasis",
        description="Test higher diversity weight to improve genre variety",
        start_date=datetime.now(),
        end_date=datetime.now() + timedelta(days=14),
        traffic_split=0.5,
        control_config=AlgorithmConfig(genre_diversity_weight=1.2),
        test_config=AlgorithmConfig(genre_diversity_weight=2.0)
    )


def create_recency_bias_test() -> ABTestConfig:
    """Create a test for different recency bias values."""
    return ABTestConfig(
        test_name="recency_bias_reduction",
        description="Test lower recency weight to reduce bias toward new additions",
        start_date=datetime.now(),
        end_date=datetime.now() + timedelta(days=14),
        traffic_split=0.5,
        control_config=AlgorithmConfig(recency_weight=0.8),
        test_config=AlgorithmConfig(recency_weight=0.4)
    )


# Global A/B test manager instance
_ab_manager = None


def get_ab_manager(db_path: str) -> ABTestManager:
    """Get or create the global A/B test manager."""
    global _ab_manager
    if _ab_manager is None:
        _ab_manager = ABTestManager(db_path)
    return _ab_manager


def get_user_algorithm_config(session_id: str, db_path: str) -> Tuple[str, AlgorithmConfig]:
    """Get the algorithm configuration for a user based on A/B test assignment."""
    manager = get_ab_manager(db_path)
    return manager.assign_user_to_group(session_id)


def record_selection_metric(session_id: str, db_path: str):
    """Record a selection metric for A/B testing."""
    manager = get_ab_manager(db_path)
    manager.record_metric(session_id, 'selection', 1.0)


def record_feedback_metric(session_id: str, feedback_value: float, db_path: str):
    """Record feedback metric for A/B testing."""
    manager = get_ab_manager(db_path)
    manager.record_metric(session_id, 'feedback', feedback_value)