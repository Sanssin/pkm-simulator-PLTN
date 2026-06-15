"""
CPU Manager Module
Utility for CPU affinity and priority management.
"""

import os
import logging
import psutil

logger = logging.getLogger(__name__)

def set_cpu_affinity(pid=None, cpus=None):
    """
    Set CPU affinity for a specific process or current process.
    
    Args:
        pid (int, optional): Process ID. If None, current process is used.
        cpus (list, optional): List of CPU core IDs to bind to (e.g., [0, 1]). 
                               If None, resets affinity to all available CPUs.
    Returns:
        bool: True if successful, False otherwise.
    """
    try:
        p = psutil.Process(pid or os.getpid())
        if cpus is None:
            # Reset to all available
            cpus = list(range(psutil.cpu_count()))
        p.cpu_affinity(cpus)
        logger.info(f"Set CPU affinity for PID {p.pid} to cores {cpus}")
        return True
    except Exception as e:
        logger.error(f"Failed to set CPU affinity: {e}")
        return False

def set_process_priority(pid=None, priority=None):
    """
    Set nice level (priority) for a process.
    
    Args:
        pid (int, optional): Process ID. If None, current process is used.
        priority (int, optional): Nice value (e.g., -20 to 19). Lower is higher priority.
    Returns:
        bool: True if successful, False otherwise.
    """
    try:
        p = psutil.Process(pid or os.getpid())
        if priority is not None:
            # Set the nice value
            p.nice(priority)
            logger.info(f"Set nice priority for PID {p.pid} to {priority}")
        return True
    except Exception as e:
        logger.error(f"Failed to set process priority: {e}")
        return False

def set_realtime_priority(pid=None):
    """
    Attempt to set real-time or highest possible priority for a process.
    Uses psutil to set highest priority depending on OS.
    
    Args:
        pid (int, optional): Process ID. If None, current process is used.
    Returns:
        bool: True if successful, False otherwise.
    """
    try:
        p = psutil.Process(pid or os.getpid())
        
        # In Linux/macOS, we can set nice to a very negative value
        if hasattr(psutil, 'POSIX') and psutil.POSIX:
            try:
                # -20 is highest priority on UNIX systems
                p.nice(-20)
                logger.info(f"Set max POSIX priority for PID {p.pid}")
                return True
            except psutil.AccessDenied:
                logger.warning("Access denied setting priority -20. Try running as root or adjust limits.")
                return False
        
        # On Windows (though this is for raspi which is Linux, adding for completeness)
        elif hasattr(psutil, 'WINDOWS') and psutil.WINDOWS:
            p.nice(psutil.REALTIME_PRIORITY_CLASS)
            logger.info(f"Set REALTIME priority for PID {p.pid}")
            return True
            
        return False
    except Exception as e:
        logger.error(f"Failed to set realtime priority: {e}")
        return False
