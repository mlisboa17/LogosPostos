#!/usr/bin/env python3
"""
Local Validation Script: Complete Infrastructure Stack

Executa todos os testes de validação para GEMINI 2.0 + GROK 4.
"""

import subprocess
import sys
import time
import os
from pathlib import Path

# Fix encoding for Windows
if sys.platform == "win32":
    os.environ["PYTHONIOENCODING"] = "utf-8"


def print_header(title: str):
    """Print formatted header."""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


def run_command(cmd: str, description: str) -> bool:
    """Execute command and return success status."""
    print(f"[*] {description}...")
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=120,
            encoding="utf-8"
        )
        
        if result.returncode == 0:
            print(f"[✓] {description}: SUCCESS")
            return True
        else:
            print(f"[✗] {description}: FAILED")
            if result.stderr:
                lines = result.stderr.split('\n')[:5]  # First 5 lines
                for line in lines:
                    if line.strip():
                        print(f"    Error: {line[:100]}")
            return False
    
    except subprocess.TimeoutExpired:
        print(f"[!] {description}: TIMEOUT (120s)")
        return False
    except Exception as e:
        print(f"[✗] {description}: ERROR - {str(e)[:100]}")
        return False


def main():
    """Run complete validation suite."""
    
    project_root = Path(__file__).parent
    
    print_header("GEMINI 2.0 + GROK 4: Local Validation Suite")
    
    # ===== PHASE 1: Unit Tests =====
    print_header("PHASE 1: Unit Tests (Domain + Infrastructure)")
    
    tests_passed = []
    tests_failed = []
    
    # Domain tests
    if run_command(
        "pytest tests/unit/domain/test_claude_tasks.py -v --tb=short",
        "Domain Layer Tests"
    ):
        tests_passed.append("Domain Tests")
    else:
        tests_failed.append("Domain Tests")
    
    # Security tests
    if run_command(
        "pytest tests/unit/shared/test_security.py -v --tb=short",
        "Security Layer Tests"
    ):
        tests_passed.append("Security Tests")
    else:
        tests_failed.append("Security Tests")
    
    # Integration tests
    if run_command(
        "pytest tests/integration/test_infrastructure.py -v --tb=short",
        "Integration Tests"
    ):
        tests_passed.append("Integration Tests")
    else:
        tests_failed.append("Integration Tests")
    
    # ===== PHASE 2: Stress Tests =====
    print_header("PHASE 2: Stress & Performance Tests")
    
    if run_command(
        "pytest tests/stress/test_stress.py -v -s --tb=short 2>&1",
        "Stress Tests (10k+ validations/sec)"
    ):
        tests_passed.append("Stress Tests")
    else:
        tests_failed.append("Stress Tests")
    
    # ===== PHASE 3: Code Quality =====
    print_header("PHASE 3: Code Quality Checks")
    
    if run_command(
        "mypy src/domain src/shared --strict --ignore-missing-imports 2>&1 | head -20",
        "Type Checking (MyPy strict)"
    ):
        tests_passed.append("Type Checking")
    else:
        tests_failed.append("Type Checking")
    
    # Coverage report
    if run_command(
        "pytest tests/unit --cov=src --cov-report=term-missing -q 2>&1 | tail -15",
        "Coverage Report"
    ):
        tests_passed.append("Coverage Report")
    else:
        tests_failed.append("Coverage Report")
    
    # ===== SUMMARY =====
    print_header("Test Execution Summary")
    
    print(f"[+] Passed: {len(tests_passed)}")
    for test in tests_passed:
        print(f"    [✓] {test}")
    
    if tests_failed:
        print(f"\n[-] Failed: {len(tests_failed)}")
        for test in tests_failed:
            print(f"    [✗] {test}")
    
    total = len(tests_passed) + len(tests_failed)
    success_rate = (len(tests_passed) / total * 100) if total > 0 else 0
    
    print(f"\n{'='*70}")
    print(f"  Overall Success Rate: {success_rate:.1f}%")
    print(f"  {'='*70}\n")
    
    # ===== NEXT STEPS =====
    if len(tests_failed) == 0:
        print_header("All Tests Passed!")
        print("Next Steps:")
        print("1. Start local Docker stack: docker-compose -f docker-compose.dev.yml up")
        print("2. Test API: curl http://localhost:8000/health")
        print("3. Access Adminer: http://localhost:8080")
        print("4. View API docs: http://localhost:8000/docs")
        print("5. Run integration with real DB: pytest tests/integration -v")
        return 0
    else:
        print_header("Some Tests Failed")
        print("Please review the errors above and fix before proceeding.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
