"""
Frontend Validation Script
Test domain models, themes, and utilities
"""

import sys

try:
    # Test domain models and theme system
    from src.presentation.frontend.state import GlobalState, UserRole, UserSession, CompanyInfo, SyncStatusInfo
    from src.presentation.frontend.styles.themes import ThemeConfig, ThemeSystem
    from src.presentation.frontend.styles.colors import LOGOS_DARK, LOGOS_LIGHT
    from src.presentation.frontend.utils import FormValidator, PerformanceMonitor
    
    print("✅ Core imports successful!")
    
    # Test GlobalState instantiation
    state = GlobalState()
    print(f"✅ GlobalState: version={state.version}, dark_mode={state.is_dark_mode}")
    
    # Test UserSession
    user = UserSession(user_id="test", email="test@test.com", name="Test", role=UserRole.DIRECTOR, is_authenticated=True)
    print(f"✅ UserSession: name={user.name}, is_director={user.is_director()}")
    
    # Test Theme
    theme = ThemeSystem()
    print(f"✅ ThemeSystem: mode={theme.config.mode}")
    
    # Test FormValidator
    valid, msg = FormValidator.validate_email("test@example.com")
    print(f"✅ FormValidator: email valid={valid}")
    
    # Test PerformanceMonitor
    PerformanceMonitor.record_metric("render_time", 42.5)
    stats = PerformanceMonitor.get_metric_stats("render_time")
    print(f"✅ PerformanceMonitor: metrics recorded")
    
    # Test state transitions
    state.mark_syncing(total=100)
    print(f"✅ Sync status: {state.sync_status.status.value}")
    
    state.mark_sync_success()
    print(f"✅ Sync completed: {state.sync_status.status.value}")
    
    # Test theme switching
    theme.switch_theme("light")
    print(f"✅ Theme switched to: {theme.config.mode}")
    
    theme.switch_theme("dark")
    print(f"✅ Theme switched to: {theme.config.mode}")
    
    print("\n🎉 ALL VALIDATION TESTS PASSED!")
    sys.exit(0)

except Exception as e:
    print(f"❌ VALIDATION FAILED: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
