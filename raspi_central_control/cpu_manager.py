"""
CPU Manager Module
Utility for process priority management.
"""

import os
import psutil
import logging

logger = logging.getLogger(__name__)

def set_realtime_priority(pid=None):
    """Set highest possible priority for process."""
    try:
        p = psutil.Process(pid or os.getpid())
        if hasattr(psutil, 'POSIX') and psutil.POSIX:
            p.nice(-20)
        elif hasattr(psutil, 'WINDOWS') and psutil.WINDOWS:
            p.nice(psutil.REALTIME_PRIORITY_CLASS)
        logger.info(f"Set REALTIME priority for PID {p.pid}")
        return True
    except Exception as e:
        logger.error(f"Failed to set realtime priority: {e}")
        return False
