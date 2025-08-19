#!/usr/bin/env python3
"""
VinylVault Test Runner Script

Comprehensive test runner for VinylVault application that executes all test categories
and generates detailed reports for deployment readiness assessment.
"""

import os
import sys
import subprocess
import json
import time
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional
import argparse


@dataclass
class TestResult:
    """Test result data structure."""
    category: str
    passed: int
    failed: int
    skipped: int
    duration: float
    coverage: Optional[float] = None
    errors: List[str] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []
    
    @property
    def total(self) -> int:
        return self.passed + self.failed + self.skipped
    
    @property
    def success_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return (self.passed / self.total) * 100


class VinylVaultTestRunner:
    """Main test runner for VinylVault application."""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.test_dir = project_root / "tests"
        self.results: List[TestResult] = []
        self.start_time = None
        self.end_time = None
    
    def setup_environment(self):
        """Setup test environment and dependencies."""
        print("🔧 Setting up test environment...")
        
        # Check Python version
        if sys.version_info < (3, 8):
            raise RuntimeError("Python 3.8+ required for testing")
        
        # Install test dependencies
        requirements_file = self.project_root / "test-requirements.txt"
        if requirements_file.exists():
            try:
                subprocess.run([
                    sys.executable, "-m", "pip", "install", "-r", str(requirements_file)
                ], check=True, capture_output=True)
                print("✓ Test dependencies installed")
            except subprocess.CalledProcessError as e:
                print(f"⚠ Warning: Failed to install test dependencies: {e}")
        
        # Check if Docker is available for deployment tests
        try:
            subprocess.run(["docker", "--version"], check=True, capture_output=True)
            print("✓ Docker available for deployment tests")
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("⚠ Warning: Docker not available - deployment tests will be skipped")
    
    def run_test_category(self, category: str, test_path: str, markers: List[str] = None) -> TestResult:
        """Run a specific test category."""
        print(f"\n🧪 Running {category} tests...")
        
        cmd = [
            sys.executable, "-m", "pytest",
            test_path,
            "-v",
            "--tb=short",
            "--duration=10",
            "--junit-xml=test-results/{category}-results.xml".format(category=category.lower().replace(' ', '-')),
            "--cov=.",
            "--cov-report=term-missing",
            "--cov-report=html:htmlcov/{category}".format(category=category.lower().replace(' ', '-')),
        ]
        
        if markers:
            for marker in markers:
                cmd.extend(["-m", marker])
        
        start_time = time.time()
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=self.project_root)
            duration = time.time() - start_time
            
            # Parse pytest output
            output_lines = result.stdout.split('\n')
            
            # Extract test counts from summary line
            passed, failed, skipped = 0, 0, 0
            errors = []
            
            for line in output_lines:
                if "passed" in line or "failed" in line or "skipped" in line:
                    # Parse pytest summary line
                    if " passed" in line:
                        passed = self._extract_count(line, "passed")
                    if " failed" in line:
                        failed = self._extract_count(line, "failed")
                    if " skipped" in line:
                        skipped = self._extract_count(line, "skipped")
                
                if "ERROR" in line or "FAILED" in line:
                    errors.append(line.strip())
            
            # Extract coverage if available
            coverage = None
            for line in output_lines:
                if "TOTAL" in line and "%" in line:
                    try:
                        coverage_str = line.split()[-1].replace('%', '')
                        coverage = float(coverage_str)
                    except (IndexError, ValueError):
                        pass
            
            print(f"✓ {category}: {passed} passed, {failed} failed, {skipped} skipped ({duration:.1f}s)")
            
            return TestResult(
                category=category,
                passed=passed,
                failed=failed,
                skipped=skipped,
                duration=duration,
                coverage=coverage,
                errors=errors[:10]  # Limit to first 10 errors
            )
            
        except subprocess.CalledProcessError as e:
            duration = time.time() - start_time
            print(f"❌ {category} tests failed to run: {e}")
            
            return TestResult(
                category=category,
                passed=0,
                failed=1,
                skipped=0,
                duration=duration,
                errors=[f"Test execution failed: {e}"]
            )
    
    def _extract_count(self, line: str, keyword: str) -> int:
        """Extract test count from pytest output line."""
        try:
            parts = line.split()
            for i, part in enumerate(parts):
                if keyword in part and i > 0:
                    return int(parts[i-1])
        except (ValueError, IndexError):
            pass
        return 0
    
    def run_all_tests(self, categories: List[str] = None) -> bool:
        """Run all test categories."""
        self.start_time = time.time()
        
        # Define test categories
        test_categories = [
            ("Unit Tests", "tests/unit", ["unit"]),
            ("Integration Tests", "tests/integration", ["integration"]),
            ("API Tests", "tests/unit/test_api_endpoints.py", ["api"]),
            ("Performance Tests", "tests/performance", ["performance"]),
            ("Deployment Tests", "tests/deployment", ["deployment", "docker"])
        ]
        
        # Filter categories if specified
        if categories:
            test_categories = [
                (name, path, markers) for name, path, markers in test_categories
                if any(cat.lower() in name.lower() for cat in categories)
            ]
        
        # Create results directory
        results_dir = self.project_root / "test-results"
        results_dir.mkdir(exist_ok=True)
        
        htmlcov_dir = self.project_root / "htmlcov"
        htmlcov_dir.mkdir(exist_ok=True)
        
        # Run each test category
        for category, test_path, markers in test_categories:
            if not (self.project_root / test_path).exists():
                print(f"⚠ Skipping {category}: {test_path} not found")
                continue
            
            result = self.run_test_category(category, test_path, markers)
            self.results.append(result)
        
        self.end_time = time.time()
        
        # Generate report
        self.generate_report()
        
        # Return overall success
        total_failed = sum(r.failed for r in self.results)
        return total_failed == 0
    
    def generate_report(self):
        """Generate comprehensive test report."""
        print("\n" + "="*80)
        print("🎯 VINYLVAULT TEST REPORT")
        print("="*80)
        
        total_duration = self.end_time - self.start_time if self.end_time and self.start_time else 0
        
        # Summary statistics
        total_passed = sum(r.passed for r in self.results)
        total_failed = sum(r.failed for r in self.results)
        total_skipped = sum(r.skipped for r in self.results)
        total_tests = total_passed + total_failed + total_skipped
        
        print(f"📊 Overall Results:")
        print(f"   Total Tests: {total_tests}")
        print(f"   Passed: {total_passed} ({(total_passed/total_tests*100):.1f}%)" if total_tests > 0 else "   Passed: 0")
        print(f"   Failed: {total_failed} ({(total_failed/total_tests*100):.1f}%)" if total_tests > 0 else "   Failed: 0")
        print(f"   Skipped: {total_skipped} ({(total_skipped/total_tests*100):.1f}%)" if total_tests > 0 else "   Skipped: 0")
        print(f"   Duration: {total_duration:.1f} seconds")
        
        # Category breakdown
        print(f"\n📋 Category Breakdown:")
        for result in self.results:
            status = "✓" if result.failed == 0 else "❌"
            coverage_str = f" ({result.coverage:.1f}% coverage)" if result.coverage else ""
            print(f"   {status} {result.category}: {result.passed}/{result.total} passed{coverage_str} ({result.duration:.1f}s)")
        
        # Deployment readiness assessment
        print(f"\n🚀 Deployment Readiness Assessment:")
        self.assess_deployment_readiness()
        
        # Save detailed results
        self.save_results()
        
        print(f"\n📁 Detailed reports saved to:")
        print(f"   - test-results/ (JUnit XML)")
        print(f"   - htmlcov/ (Coverage reports)")
        print(f"   - test-results/test-report.json (JSON summary)")
    
    def assess_deployment_readiness(self):
        """Assess deployment readiness based on test results."""
        criteria = {
            "Unit Tests": {"min_pass_rate": 95, "required": True},
            "Integration Tests": {"min_pass_rate": 90, "required": True},
            "API Tests": {"min_pass_rate": 95, "required": True},
            "Performance Tests": {"min_pass_rate": 80, "required": False},
            "Deployment Tests": {"min_pass_rate": 85, "required": False}
        }
        
        deployment_ready = True
        issues = []
        
        for result in self.results:
            criterion = criteria.get(result.category, {"min_pass_rate": 80, "required": False})
            
            if result.total == 0:
                if criterion["required"]:
                    deployment_ready = False
                    issues.append(f"❌ {result.category}: No tests found (required)")
                else:
                    issues.append(f"⚠ {result.category}: No tests found (optional)")
                continue
            
            pass_rate = result.success_rate
            min_rate = criterion["min_pass_rate"]
            
            if pass_rate < min_rate:
                if criterion["required"]:
                    deployment_ready = False
                    issues.append(f"❌ {result.category}: {pass_rate:.1f}% < {min_rate}% required")
                else:
                    issues.append(f"⚠ {result.category}: {pass_rate:.1f}% < {min_rate}% recommended")
            else:
                issues.append(f"✓ {result.category}: {pass_rate:.1f}% ≥ {min_rate}% required")
        
        # Overall assessment
        if deployment_ready:
            print("   🎉 READY FOR DEPLOYMENT")
            print("   All critical tests pass deployment criteria")
        else:
            print("   ⚠ NOT READY FOR DEPLOYMENT")
            print("   Critical issues found that must be resolved")
        
        print("\n   Detailed Assessment:")
        for issue in issues:
            print(f"     {issue}")
        
        # Performance considerations for Raspberry Pi
        performance_result = next((r for r in self.results if "Performance" in r.category), None)
        if performance_result and performance_result.failed == 0:
            print("   ✓ Performance tests pass - suitable for Raspberry Pi deployment")
        elif performance_result:
            print("   ⚠ Performance issues detected - may impact Raspberry Pi performance")
        
        return deployment_ready
    
    def save_results(self):
        """Save test results to JSON file."""
        results_data = {
            "timestamp": time.time(),
            "duration": self.end_time - self.start_time if self.end_time and self.start_time else 0,
            "results": [asdict(result) for result in self.results],
            "summary": {
                "total_passed": sum(r.passed for r in self.results),
                "total_failed": sum(r.failed for r in self.results),
                "total_skipped": sum(r.skipped for r in self.results),
                "total_tests": sum(r.total for r in self.results),
                "deployment_ready": sum(r.failed for r in self.results) == 0
            }
        }
        
        results_file = self.project_root / "test-results" / "test-report.json"
        with open(results_file, 'w') as f:
            json.dump(results_data, f, indent=2)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="VinylVault Test Runner")
    parser.add_argument("--categories", nargs="+", help="Test categories to run")
    parser.add_argument("--skip-setup", action="store_true", help="Skip environment setup")
    parser.add_argument("--quick", action="store_true", help="Run quick tests only (skip slow tests)")
    
    args = parser.parse_args()
    
    # Find project root
    script_dir = Path(__file__).parent
    project_root = script_dir
    
    # Initialize test runner
    runner = VinylVaultTestRunner(project_root)
    
    try:
        # Setup environment
        if not args.skip_setup:
            runner.setup_environment()
        
        # Run tests
        print(f"\n🚀 Starting VinylVault test suite...")
        print(f"Project root: {project_root}")
        
        success = runner.run_all_tests(args.categories)
        
        # Exit with appropriate code
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        print("\n❌ Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Test runner failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()