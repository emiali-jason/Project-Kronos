"""Opt-in child bootstrap for the guarded test launcher only."""
import os
if os.environ.get('KRONOS_TEST_ISOLATION_MANIFEST'):
    try:
        from kronos_test_isolation import install
        install(required=True)
    except Exception:
        os.write(2, b'KRONOS_TEST_ISOLATION_BOOTSTRAP_FAILED\n')
        os._exit(78)
