"""Installation and update procedures for Payroll Indonesia."""
import logging
from typing import Dict, Any, Optional

import frappe
from frappe import _

from payroll_indonesia.config.config import get_config, get_live_config
from payroll_indonesia.frappe_helpers import safe_execute, ensure_doc_exists
from payroll_indonesia.setup import setup_module

# Configure logger
logger = logging.getLogger(__name__)


def before_install() -> None:
    """Run before app installation."""
    _run_before_install()


def after_install() -> None:
    """Run after app installation."""
    _run_after_install()


def after_update() -> None:
    """Run after app update."""
    _run_after_update()


def after_migrate() -> None:
    """Run after migrations."""
    _run_after_migrate()


@safe_execute(log_exception=True)
def _run_before_install() -> bool:
    """Prepare environment before installation."""
    logger.info(_("Starting Payroll Indonesia pre-installation checks"))
    config = get_config()
    
    # Verify configuration is loaded correctly
    if not config:
        logger.error(_("Configuration could not be loaded"))
        return False
    
    logger.info(_("Pre-installation checks completed successfully"))
    return True


@safe_execute(log_exception=True)
def _run_after_install() -> bool:
    """Setup required data after installation."""
    logger.info(_("Starting Payroll Indonesia post-installation setup"))
    config = get_live_config()
    
    # Run main setup module with loaded configuration
    result = setup_module.main(config)
    
    if result:
        logger.info(_("Post-installation setup completed successfully"))
    else:
        logger.warning(_("Post-installation setup completed with warnings"))
    
    return result


@safe_execute(log_exception=True)
def _run_after_update() -> bool:
    """Update application data after code update."""
    logger.info(_("Starting Payroll Indonesia post-update process"))
    config = get_live_config()
    
    # Update payroll components and settings after app update
    _update_payroll_components(config)
    _update_property_setters(config)
    
    logger.info(_("Post-update process completed successfully"))
    return True


@safe_execute(log_exception=True)
def _run_after_migrate() -> bool:
    """Migrate data after schema migrations."""
    logger.info(_("Starting Payroll Indonesia post-migration process"))
    config = get_live_config()
    
    # Migrate configuration from JSON to DocType if needed
    if _should_migrate_config_to_doctype():
        result = _migrate_config_to_doctype(config)
        if not result:
            logger.warning(_("Configuration migration failed or was incomplete"))
    
    logger.info(_("Post-migration process completed successfully"))
    return True


@safe_execute(log_exception=True)
def _update_payroll_components(config: Dict[str, Any]) -> bool:
    """Update payroll components based on configuration."""
    logger.info(_("Updating payroll components"))
    
    # Extract components from config
    components = config.get("salary_components", {})
    
    # Delegate to setup module
    return setup_module.setup_salary_components(components)


@safe_execute(log_exception=True)
def _update_property_setters(config: Dict[str, Any]) -> bool:
    """Update property setters based on configuration."""
    logger.info(_("Updating property setters"))
    return setup_module.setup_property_setters(config)


@safe_execute(log_exception=True)
def _should_migrate_config_to_doctype() -> bool:
    """Check if configuration should be migrated to DocType."""
    # Check if Settings DocType exists but no records
    if frappe.db.exists("DocType", "Payroll Indonesia Settings"):
        count = frappe.db.count("Payroll Indonesia Settings")
        return count == 0
    return False


@safe_execute(log_exception=True)
def _migrate_config_to_doctype(config: Dict[str, Any]) -> bool:
    """Migrate configuration from JSON to DocType."""
    logger.info(_("Migrating configuration to Payroll Indonesia Settings"))
    return setup_module.migrate_config_to_settings(config)
