
import logging
import os
from logging.handlers import RotatingFileHandler


# Create logs directory if it doesn't exist
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

def setup_logger(name, log_file, level=logging.INFO):
    """Function to setup as many loggers as you want"""
    
    formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
    
    handler = RotatingFileHandler(os.path.join(LOG_DIR, log_file), maxBytes=10*1024*1024, backupCount=5)
    handler.setFormatter(formatter)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    if not logger.handlers:
        logger.addHandler(handler)

    return logger

# Create specific loggers
trade_logger = setup_logger('trade_journal', 'trade_journal.log')
execution_logger = setup_logger('execution', 'execution.log')
error_logger = setup_logger('error_log', 'error.log')
system_logger = setup_logger('system', 'system.log')
