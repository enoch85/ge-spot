"""Core test runner functionality for GE-Spot integration."""
import logging
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any

import aiohttp

from ..utils.general import get_all_areas, get_all_apis
from ..api.api_testing import run_tests as run_api_tests
from ..api.date_range_testing import run_tests as run_date_range_tests
from ..api.date_range_testing import print_summary as print_date_range_summary
from .reporting import print_summary

logger = logging.getLogger(__name__)


async def run_with_session_cleanup(args):
    """Run tests and ensure all sessions are properly closed.
    
    Args:
        args: Command-line arguments
    """
    start_time = datetime.now()
    
    # Create a list to track all created sessions
    all_sessions = []
    
    # Create a patched version of ClientSession that tracks creation
    original_init = aiohttp.ClientSession.__init__
    
    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        all_sessions.append(self)
    
    # Apply the monkey patch
    aiohttp.ClientSession.__init__ = patched_init
    
    try:
        # Configure logging
        logging.basicConfig(
            level=getattr(logging, args.log_level),
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        
        # Get all available areas and APIs
        all_areas = get_all_areas()
        all_apis = get_all_apis()
        
        # Filter areas and APIs based on command-line arguments
        areas_to_test = args.regions if args.regions else all_areas
        apis_to_test = args.apis if args.apis else all_apis
        
        logger.info(f"Testing {len(apis_to_test)}/{len(all_apis)} APIs and {len(areas_to_test)}/{len(all_areas)} regions")
        logger.info(f"APIs to test: {', '.join(apis_to_test)}")
        logger.info(f"Using request timeout: {args.timeout} seconds")
        
        # Check if we're running date range tests
        is_date_range_test = hasattr(args, 'reference_time') or hasattr(args, 'test_tomorrow')
        
        # Parse reference time if provided
        reference_time = None
        if hasattr(args, 'reference_time') and args.reference_time:
            try:
                reference_time = datetime.fromisoformat(args.reference_time)
                if reference_time.tzinfo is None:
                    # Add UTC timezone if not specified
                    reference_time = reference_time.replace(tzinfo=timezone.utc)
                logger.info(f"Using reference time: {reference_time.isoformat()}")
            except ValueError as e:
                logger.error(f"Invalid reference time format: {e}")
                return
        
        # Run the appropriate tests
        if is_date_range_test:
            # Run date range tests
            test_tomorrow = hasattr(args, 'test_tomorrow') and args.test_tomorrow
            results = await run_date_range_tests(
                apis_to_test,
                areas_to_test,
                args.timeout,
                reference_time,
                test_tomorrow
            )
        else:
            # Run regular API tests
            results = await run_api_tests(apis_to_test, areas_to_test, args.timeout)
        
        # Calculate test duration
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        results["duration"] = duration
        
        # Print summary
        if is_date_range_test:
            print_date_range_summary(results)
        else:
            print_summary(results)
    
    finally:
        # Clean up all sessions
        for session in all_sessions:
            if not session.closed:
                try:
                    await session.close()
                    logger.debug(f"Closed unclosed session: {session}")
                except Exception as e:
                    logger.error(f"Error closing session: {e}")
        
        # Wait for all connections to be properly closed
        await asyncio.sleep(0.25)
        
        # Restore the original method
        aiohttp.ClientSession.__init__ = original_init
