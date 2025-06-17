# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last updated: 2025-05-23 04:01:12 by dannyaudian

import frappe
from frappe import _
from frappe.utils import now, getdate, add_days, cint
from frappe.utils.background_jobs import get_jobs, get_job_status, enqueue
from typing import Dict, List, Any, Optional, Callable


# ======== Logging Utilities ========


def get_logger(module_name: str = "batch_processing") -> frappe.logger:
    """
    Get a properly configured logger for batch processing

    Args:
        module_name: Optional module name for the logger

    Returns:
        frappe.logger: Configured logger instance
    """
    return frappe.logger(module_name, with_more_info=True)


def log_batch_event(
    message: str, batch_id: str = None, job_name: str = None, level: str = "info"
) -> None:
    """
    Log a batch processing event with proper formatting

    Args:
        message: The message to log
        batch_id: Optional batch ID for tracking
        job_name: Optional job name for tracking
        level: Log level (debug, info, warning, error)
    """
    logger = get_logger()

    # Format the message with batch information
    formatted_message = message
    if batch_id:
        formatted_message = f"[Batch: {batch_id}] {formatted_message}"
    if job_name:
        formatted_message = f"[Job: {job_name}] {formatted_message}"

    # Log at the appropriate level
    if level == "debug":
        logger.debug(formatted_message)
    elif level == "warning":
        logger.warning(formatted_message)
    elif level == "error":
        logger.error(formatted_message)
    else:
        logger.info(formatted_message)


# ======== Job Management ========


def get_batch_jobs(job_prefix: str = None) -> List[Dict[str, Any]]:
    """
    Get all jobs related to batch processing

    Args:
        job_prefix: Optional prefix to filter jobs

    Returns:
        List[Dict[str, Any]]: List of jobs with their status
    """
    all_jobs = get_jobs()

    # Filter jobs by prefix if specified
    batch_jobs = []
    for job in all_jobs:
        # Skip jobs that don't match our prefix
        if job_prefix and not job.get("job_name", "").startswith(job_prefix):
            continue

        # Get job status
        job_status = get_job_status(job.get("job_name"))

        # Add to batch jobs list
        batch_jobs.append(
            {
                "job_name": job.get("job_name"),
                "status": job_status,
                "creation": job.get("creation"),
                "queue": job.get("queue"),
                "job_id": job.get("job_id"),
            }
        )

    return batch_jobs


def cancel_batch_jobs(job_prefix: str) -> Dict[str, Any]:
    """
    Cancel all running jobs with a specific prefix

    Args:
        job_prefix: Prefix to identify jobs to cancel

    Returns:
        Dict[str, Any]: Result of the operation with counts
    """
    redis_conn = frappe.cache().redis
    if not redis_conn:
        return {"status": "error", "message": "Redis connection not available"}

    # Get all jobs with the prefix
    matching_jobs = get_batch_jobs(job_prefix)

    # Count statistics
    total = len(matching_jobs)
    cancelled = 0
    failed = 0
    errors = []

    # Attempt to cancel each job
    for job in matching_jobs:
        try:
            job_id = job.get("job_id")
            if not job_id:
                continue

            # Only cancel if job is not already finished
            if job.get("status") not in ["finished", "failed"]:
                # Delete the job
                redis_conn.delete(job_id)
                # Delete from the queue
                queue_key = f"rq:queue:{job.get('queue')}"
                redis_conn.lrem(queue_key, 0, job_id)
                cancelled += 1

        except Exception as e:
            failed += 1
            errors.append({"job": job.get("job_name"), "error": str(e)})

    return {
        "status": "success",
        "total_jobs": total,
        "cancelled": cancelled,
        "failed": failed,
        "errors": errors,
    }


def is_job_active(job_name: str) -> bool:
    """
    Check if a job is currently active (queued or running)

    Args:
        job_name: The name of the job to check

    Returns:
        bool: True if the job is active
    """
    return frappe.get_all(
        "Background Jobs",
        filters={"job_name": job_name, "status": ["in", ["queued", "started"]]},
        limit=1,
    )


def cleanup_old_batch_jobs(days: int = 7) -> Dict[str, Any]:
    """
    Clean up old completed batch jobs from the database
    This should be called from a scheduler event

    Args:
        days: Number of days to keep (delete older than this)

    Returns:
        Dict[str, Any]: Status and counts of the cleanup
    """
    cutoff_date = getdate(add_days(now(), -days))

    # Delete old completed jobs
    count = frappe.db.count(
        "Background Jobs",
        {
            "creation": ["<", cutoff_date],
            "status": ["in", ["finished", "failed", "cancelled"]],
            "job_name": ["like", "batch_%"],
        },
    )

    if count > 0:
        frappe.db.delete(
            "Background Jobs",
            {
                "creation": ["<", cutoff_date],
                "status": ["in", ["finished", "failed", "cancelled"]],
                "job_name": ["like", "batch_%"],
            },
        )

    # Log the cleanup
    log_batch_event(f"Cleaned up {count} old batch jobs older than {days} days")

    return {"status": "success", "deleted_count": count, "cutoff_date": cutoff_date}


# ======== Batch Processing ========


def create_batch_id() -> str:
    """
    Generate a unique batch ID for tracking

    Returns:
        str: A unique batch identifier
    """
    return f"batch_{getdate().strftime('%Y%m%d')}_{frappe.generate_hash(length=8)}"


def split_into_batches(items: List[Any], batch_size: int = 20) -> List[List[Any]]:
    """
    Split a list of items into batches of a specific size

    Args:
        items: List of items to split
        batch_size: Maximum items per batch

    Returns:
        List[List[Any]]: List of batches
    """
    batches = []
    for i in range(0, len(items), batch_size):
        batches.append(items[i : i + batch_size])
    return batches


def process_in_batches(
    items: List[Any],
    process_func: Callable[[List[Any], str, Any], Any],
    batch_size: int = 20,
    is_async: bool = True,
    queue: str = "long",
    timeout: int = 1800,
    batch_id: str = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    Process a list of items in batches

    Args:
        items: List of items to process
        process_func: Function to process each batch
        batch_size: Maximum items per batch
        is_async: Whether to process in background jobs
        queue: Queue to use for background jobs
        timeout: Timeout for background jobs in seconds
        batch_id: Optional batch ID for tracking
        **kwargs: Additional arguments to pass to process_func

    Returns:
        Dict[str, Any]: Job information and batch details
    """
    # Generate batch ID if not provided
    if not batch_id:
        batch_id = create_batch_id()

    # Split items into batches
    batches = split_into_batches(items, batch_size)

    # Log batch creation
    log_batch_event(
        f"Created batch {batch_id} with {len(batches)} sub-batches of {batch_size} items each",
        batch_id=batch_id,
    )

    if is_async:
        # Process batches asynchronously
        batch_jobs = []
        for i, batch in enumerate(batches):
            job_name = f"{batch_id}_sub{i+1}"

            # Queue the batch processing job
            enqueue(
                process_func,
                queue=queue,
                timeout=timeout,
                is_async=True,
                job_name=job_name,
                items=batch,
                batch_id=batch_id,
                sub_batch=i + 1,
                total_batches=len(batches),
                **kwargs,
            )

            batch_jobs.append(job_name)

        return {
            "status": "queued",
            "batch_id": batch_id,
            "total_items": len(items),
            "batch_size": batch_size,
            "total_batches": len(batches),
            "batch_jobs": batch_jobs,
        }
    else:
        # Process batches synchronously
        results = []
        for i, batch in enumerate(batches):
            try:
                batch_result = process_func(
                    batch, batch_id=batch_id, sub_batch=i + 1, total_batches=len(batches), **kwargs
                )
                results.append(batch_result)
            except Exception as e:
                # Log error but continue with other batches
                log_batch_event(
                    f"Error processing sub-batch {i+1}: {str(e)}", batch_id=batch_id, level="error"
                )
                results.append({"status": "error", "error": str(e), "sub_batch": i + 1})

        return {
            "status": "completed",
            "batch_id": batch_id,
            "total_items": len(items),
            "batch_size": batch_size,
            "total_batches": len(batches),
            "results": results,
        }


def get_batch_status(batch_id: str) -> Dict[str, Any]:
    """
    Get the status of a batch processing job

    Args:
        batch_id: The batch ID to check

    Returns:
        Dict[str, Any]: Status information for the batch
    """
    # Get all jobs for this batch
    batch_jobs = get_batch_jobs(batch_id)

    if not batch_jobs:
        return {"status": "not_found", "batch_id": batch_id}

    # Count job status
    total_jobs = len(batch_jobs)
    status_counts = {"queued": 0, "started": 0, "finished": 0, "failed": 0}

    for job in batch_jobs:
        job_status = job.get("status")
        if job_status in status_counts:
            status_counts[job_status] += 1

    # Determine overall batch status
    if status_counts["failed"] == total_jobs:
        overall_status = "failed"
    elif status_counts["finished"] == total_jobs:
        overall_status = "completed"
    elif status_counts["queued"] + status_counts["started"] == 0:
        overall_status = "partially_completed"
    else:
        overall_status = "in_progress"

    # Calculate completion percentage
    completed = status_counts["finished"] + status_counts["failed"]
    completion_percentage = round((completed / total_jobs) * 100, 2) if total_jobs > 0 else 0

    return {
        "batch_id": batch_id,
        "status": overall_status,
        "total_jobs": total_jobs,
        "job_status": status_counts,
        "completion_percentage": completion_percentage,
        "is_complete": overall_status in ["completed", "failed"],
        "creation": batch_jobs[0].get("creation") if batch_jobs else None,
        "jobs": batch_jobs,
    }


# ======== Tax Summary-Specific Batch Functions ========


@frappe.whitelist()
def process_tax_summary_batch(
    items: List[str], batch_id: str = None, sub_batch: int = 1, total_batches: int = 1, **kwargs
) -> Dict[str, Any]:
    """
    Process a batch of tax summary updates

    Args:
        items: List of employee IDs or salary slip IDs
        batch_id: Batch ID for tracking
        sub_batch: Sub-batch number
        total_batches: Total number of sub-batches
        **kwargs: Additional arguments like year, force, etc.

    Returns:
        Dict[str, Any]: Results of processing the batch
    """
    # Process parameters
    is_salary_slip = kwargs.get("is_salary_slip", False)
    year = kwargs.get("year", getdate().year)
    force = kwargs.get("force", False)

    # Initialize results
    results = {
        "batch_id": batch_id,
        "sub_batch": sub_batch,
        "total_batches": total_batches,
        "processed": 0,
        "success": 0,
        "failed": 0,
        "errors": [],
    }

    # Import the appropriate functions
    from payroll_indonesia.payroll_indonesia.doctype.employee_tax_summary.employee_tax_summary import (
        create_from_salary_slip,
        refresh_tax_summary,
    )

    # Log start of batch processing
    log_batch_event(
        f"Starting sub-batch {sub_batch}/{total_batches} with {len(items)} items",
        batch_id=batch_id,
        job_name=f"{batch_id}_sub{sub_batch}",
    )

    # Process each item in the batch
    for item in items:
        try:
            if is_salary_slip:
                # Process a salary slip
                result = create_from_salary_slip(item, "reprocess")
                if result:
                    results["success"] += 1
                else:
                    results["failed"] += 1
                    results["errors"].append(
                        {"item": item, "error": "Failed to update tax summary from salary slip"}
                    )
            else:
                # Process an employee
                refresh_result = refresh_tax_summary(item, year=year, force=force)
                if refresh_result.get("status") == "success":
                    results["success"] += 1
                else:
                    results["failed"] += 1
                    results["errors"].append(
                        {"item": item, "error": refresh_result.get("message", "Unknown error")}
                    )

        except Exception as e:
            results["failed"] += 1
            results["errors"].append({"item": item, "error": str(e)})

        finally:
            results["processed"] += 1

    # Log completion of batch processing
    log_batch_event(
        f"Completed sub-batch {sub_batch}/{total_batches}: "
        f"{results['success']} succeeded, {results['failed']} failed",
        batch_id=batch_id,
        job_name=f"{batch_id}_sub{sub_batch}",
    )

    return results


@frappe.whitelist()
def bulk_refresh_tax_summaries_by_company(
    company: str, year: Optional[int] = None, batch_size: int = 20, force: bool = False
) -> Dict[str, Any]:
    """
    Refresh tax summaries for all employees in a company

    Args:
        company: Company to process
        year: Tax year to process (defaults to current year)
        batch_size: Size of each batch
        force: Whether to force recreation of tax summaries

    Returns:
        Dict[str, Any]: Batch information
    """
    # Check permissions
    if not frappe.has_permission("Employee Tax Summary", "write"):
        frappe.throw(_("Not permitted to update Tax Summary data"), frappe.PermissionError)

    # Set default year
    if not year:
        year = getdate().year
    else:
        year = cint(year)

    # Get all active employees for company
    employees = [
        e.name
        for e in frappe.get_all(
            "Employee", filters={"company": company, "status": "Active"}, fields=["name"]
        )
    ]

    if not employees:
        return {
            "status": "error",
            "message": _("No active employees found for company {0}").format(company),
        }

    # Generate batch ID
    batch_id = create_batch_id()

    # Process in batches
    result = process_in_batches(
        items=employees,
        process_func=process_tax_summary_batch,
        batch_size=batch_size,
        is_async=True,
        queue="long",
        timeout=1800,  # 30 minutes timeout
        batch_id=batch_id,
        year=year,
        force=force,
        is_salary_slip=False,
    )

    # Add company info to result
    result["company"] = company
    result["year"] = year
    result["employee_count"] = len(employees)

    return result


@frappe.whitelist()
def bulk_refresh_tax_summaries_by_department(
    company: str,
    department: str,
    year: Optional[int] = None,
    batch_size: int = 20,
    force: bool = False,
) -> Dict[str, Any]:
    """
    Refresh tax summaries for all employees in a department

    Args:
        company: Company to process
        department: Department to process
        year: Tax year to process (defaults to current year)
        batch_size: Size of each batch
        force: Whether to force recreation of tax summaries

    Returns:
        Dict[str, Any]: Batch information
    """
    # Check permissions
    if not frappe.has_permission("Employee Tax Summary", "write"):
        frappe.throw(_("Not permitted to update Tax Summary data"), frappe.PermissionError)

    # Set default year
    if not year:
        year = getdate().year
    else:
        year = cint(year)

    # Get all active employees for company and department
    employees = [
        e.name
        for e in frappe.get_all(
            "Employee",
            filters={"company": company, "department": department, "status": "Active"},
            fields=["name"],
        )
    ]

    if not employees:
        return {
            "status": "error",
            "message": _("No active employees found for department {0} in company {1}").format(
                department, company
            ),
        }

    # Generate batch ID
    batch_id = create_batch_id()

    # Process in batches
    result = process_in_batches(
        items=employees,
        process_func=process_tax_summary_batch,
        batch_size=batch_size,
        is_async=True,
        queue="long",
        timeout=1800,  # 30 minutes timeout
        batch_id=batch_id,
        year=year,
        force=force,
        is_salary_slip=False,
    )

    # Add extra info to result
    result["company"] = company
    result["department"] = department
    result["year"] = year
    result["employee_count"] = len(employees)

    return result


# ======== Cleanup Functions ========


def cleanup_old_batch_jobs_extended(days: int = 7) -> Dict[str, Any]:
    """
    Clean up old completed batch jobs from the database
    This should be called from a scheduler event
    This is an extended version that also logs the cleanup event.

    Args:
        days: Number of days to keep (delete older than this)

    Returns:
        Dict[str, Any]: Status and counts of the cleanup
    """
    cutoff_date = add_days(now(), -days)

    # Delete old completed jobs
    count = frappe.db.count(
        "Background Jobs",
        {
            "creation": ["<", cutoff_date],
            "status": ["in", ["finished", "failed", "cancelled"]],
            "job_name": ["like", "batch_%"],
        },
    )

    if count > 0:
        frappe.db.delete(
            "Background Jobs",
            {
                "creation": ["<", cutoff_date],
                "status": ["in", ["finished", "failed", "cancelled"]],
                "job_name": ["like", "batch_%"],
            },
        )

    # Log the cleanup
    log_batch_event(f"Cleaned up {count} old batch jobs older than {days} days")

    return {"status": "success", "deleted_count": count, "cutoff_date": cutoff_date}


# ======== Migration Utilities ========


def run_migration_in_batches(
    doctype: str, migration_func: Callable, filters: Dict[str, Any] = None, batch_size: int = 100
) -> Dict[str, Any]:
    """
    Run a data migration function on all records of a doctype in batches

    Args:
        doctype: DocType to migrate
        migration_func: Function to process each record
        filters: Filters to apply to record fetch
        batch_size: Size of each batch

    Returns:
        Dict[str, Any]: Migration results
    """
    # Get all record IDs
    filters = filters or {}
    records = frappe.get_all(doctype, filters=filters, pluck="name")

    if not records:
        return {"status": "error", "message": f"No {doctype} records found matching filters"}

    # Define batch processing function
    def process_migration_batch(items, batch_id, sub_batch, **kwargs):
        results = {
            "batch_id": batch_id,
            "sub_batch": sub_batch,
            "processed": 0,
            "success": 0,
            "failed": 0,
            "errors": [],
        }

        for item in items:
            try:
                # Apply migration function to this record
                doc = frappe.get_doc(doctype, item)
                migration_func(doc)
                results["success"] += 1
            except Exception as e:
                results["failed"] += 1
                results["errors"].append({"record": item, "error": str(e)})
            finally:
                results["processed"] += 1

        return results

    # Generate batch ID
    batch_id = f"migrate_{doctype.lower().replace(' ', '_')}_{getdate().strftime('%Y%m%d%H%M%S')}"

    # Process in batches
    return process_in_batches(
        items=records,
        process_func=process_migration_batch,
        batch_size=batch_size,
        is_async=True,
        queue="long",
        timeout=3600,  # 1 hour timeout
        batch_id=batch_id,
    )
