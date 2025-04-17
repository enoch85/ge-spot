"""Test result reporting functionality."""
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


def format_api_area_pairs(pairs):
    """Format API-area pairs for display.
    
    Args:
        pairs: List of (api, area) tuples
        
    Returns:
        Formatted string of API-area pairs
    """
    return ', '.join([f"{api}:{area}" for api, area in sorted(pairs)])


def print_summary(results: Dict[str, Any]):
    """Print a summary of test results.
    
    Args:
        results: Dictionary with test results from run_tests
    """
    logger.info("")
    logger.info("=" * 70)
    logger.info(f"TEST RESULTS SUMMARY (Completed in {results.get('duration', 0):.2f} seconds)")
    logger.info("=" * 70)
    logger.info(f"Total tests run: {results['tests_run']}")

    successful = results["by_status"]["success"]
    skipped = results["by_status"]["skipped"]
    not_available = results["by_status"]["not_available"] 
    failed = results["by_status"]["failure"]
    
    # Print by status
    logger.info(f"Successful tests: {len(successful)}")
    if len(successful) <= 20 and successful:  # Only list them if not too many
        logger.info(f"  {format_api_area_pairs(successful)}")
    
    if skipped:
        logger.info(f"Skipped tests: {len(skipped)}")
        if len(skipped) <= 20:
            logger.info(f"  {format_api_area_pairs(skipped)}")
    
    if not_available:
        logger.info(f"Data Not Available: {len(not_available)}")
        if len(not_available) <= 20:
            logger.info(f"  {format_api_area_pairs(not_available)}")
    
    if failed:
        logger.info(f"Failed tests: {len(failed)}")
        if len(failed) <= 20:
            logger.info(f"  {format_api_area_pairs(failed)}")
    
    # Print per-API results
    logger.info("")
    logger.info("Per-API Results Summary:")
    for api, counts in sorted(results["by_api"].items()):
        success_rate = (counts["success"] / counts["total"]) * 100 if counts["total"] > 0 else 0
        logger.info(f"  {api}: Success: {counts['success']}/{counts['total']} ({success_rate:.1f}%), " +
                   f"Skipped: {counts['skipped']}, NotAvailable: {counts['not_available']}, Failed: {counts['failure']}")
    
    # Print overall status
    logger.info("")
    if failed:
        logger.error("❌ OVERALL STATUS: SOME TESTS FAILED")
    elif skipped or not_available:
        logger.warning("⚠️ OVERALL STATUS: PARTIAL SUCCESS (some tests skipped or data not available)")
    else:
        logger.info("✅ ALL TESTS PASSED!")
    
    # Print debug information for failed tests
    if failed and logger.level <= logging.DEBUG:
        logger.debug("")
        logger.debug("Detailed information for failed tests:")
        for result in results["all_results"]:
            if result["status"] == "failure":
                logger.debug(f"  API: {result['api']}, Area: {result['area']}")
                logger.debug(f"  Message: {result['message']}")
                logger.debug(f"  Debug Info: {result['debug_info']}")
                logger.debug("")
