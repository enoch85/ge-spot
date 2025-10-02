#!/usr/bin/env python3
"""
Debug script to analyze the attribute reset timing pattern.
This helps confirm the cache mutation hypothesis.

Usage:
    python3 scripts/debug_attribute_reset.py

Expected findings if cache mutation bug exists:
- Random timing between updates (6-15 seconds)
- Multiple cache access patterns
- Timestamp changes even when price data hasn't changed
"""

import sys
from datetime import datetime, timedelta
from typing import List, Dict, Any
import statistics


class UpdateEvent:
    """Represents a single attribute update event."""
    
    def __init__(self, timestamp: datetime, source: str):
        self.timestamp = timestamp
        self.source = source


class AttributeResetAnalyzer:
    """Analyzes attribute reset patterns."""
    
    def __init__(self):
        self.events: List[UpdateEvent] = []
        self.intervals: List[float] = []
    
    def add_event(self, timestamp: datetime, source: str = "unknown"):
        """Add an observed update event."""
        event = UpdateEvent(timestamp, source)
        self.events.append(event)
        
        # Calculate interval from last event
        if len(self.events) > 1:
            interval = (event.timestamp - self.events[-2].timestamp).total_seconds()
            self.intervals.append(interval)
    
    def analyze(self) -> Dict[str, Any]:
        """Analyze the update pattern."""
        if not self.intervals:
            return {
                "status": "insufficient_data",
                "message": "Not enough events to analyze"
            }
        
        return {
            "status": "analyzed",
            "event_count": len(self.events),
            "min_interval": min(self.intervals),
            "max_interval": max(self.intervals),
            "avg_interval": statistics.mean(self.intervals),
            "median_interval": statistics.median(self.intervals),
            "std_dev": statistics.stdev(self.intervals) if len(self.intervals) > 1 else 0,
            "intervals": self.intervals,
            "diagnosis": self._diagnose()
        }
    
    def _diagnose(self) -> str:
        """Provide a diagnosis based on the pattern."""
        if not self.intervals:
            return "Insufficient data"
        
        avg = statistics.mean(self.intervals)
        std_dev = statistics.stdev(self.intervals) if len(self.intervals) > 1 else 0
        min_int = min(self.intervals)
        max_int = max(self.intervals)
        
        # High variability suggests cache mutation bug
        variability = (max_int - min_int) / avg if avg > 0 else 0
        
        if variability > 0.5 and min_int < 10 and max_int < 20:
            return (
                "HIGH PROBABILITY: Cache Mutation Bug\n"
                f"    - Random intervals ({min_int:.1f}s - {max_int:.1f}s)\n"
                f"    - High variability (CV: {variability:.2f})\n"
                "    - Suggests multiple async processes triggering updates\n"
                "    - Recommendation: Apply cache deep-copy fixes immediately"
            )
        elif avg > 840:  # ~14 minutes
            return (
                "NORMAL: Regular coordinator updates\n"
                f"    - Average interval: {avg/60:.1f} minutes\n"
                "    - Matches expected 15-minute update interval\n"
                "    - No immediate action needed"
            )
        else:
            return (
                "ABNORMAL: Frequent updates detected\n"
                f"    - Average interval: {avg:.1f}s\n"
                "    - More frequent than expected\n"
                "    - Investigate coordinator and sensor update logic"
            )
    
    def print_report(self):
        """Print a detailed report."""
        analysis = self.analyze()
        
        print("=" * 70)
        print("ATTRIBUTE RESET TIMING ANALYSIS")
        print("=" * 70)
        print(f"Status: {analysis['status']}")
        
        if analysis['status'] == 'analyzed':
            print(f"\nEvent Count: {analysis['event_count']}")
            print(f"Time Range: {self.intervals[0]:.1f}s to {self.intervals[-1]:.1f}s")
            print(f"\nInterval Statistics:")
            print(f"  Minimum:  {analysis['min_interval']:.2f}s")
            print(f"  Maximum:  {analysis['max_interval']:.2f}s")
            print(f"  Average:  {analysis['avg_interval']:.2f}s")
            print(f"  Median:   {analysis['median_interval']:.2f}s")
            print(f"  Std Dev:  {analysis['std_dev']:.2f}s")
            print(f"\nDiagnosis:")
            print(analysis['diagnosis'])
            
            print(f"\nAll Intervals (seconds):")
            for i, interval in enumerate(self.intervals, 1):
                print(f"  {i}: {interval:.2f}s")
        else:
            print(f"Message: {analysis['message']}")
        
        print("=" * 70)


def simulate_bug_scenario():
    """Simulate the observed bug scenario."""
    print("Simulating observed bug scenario (random 6-15 second updates)...\n")
    
    analyzer = AttributeResetAnalyzer()
    
    # Simulate observed pattern based on user report
    base_time = datetime.now()
    
    # Simulate random intervals between 6-15 seconds
    observed_intervals = [8.3, 12.1, 6.7, 14.2, 9.5, 11.8, 7.4, 13.6, 10.2, 6.9, 15.1, 8.8]
    
    current_time = base_time
    analyzer.add_event(current_time, "initial")
    
    for interval in observed_intervals:
        current_time = current_time + timedelta(seconds=interval)
        analyzer.add_event(current_time, "update")
    
    analyzer.print_report()
    
    print("\nRECOMMENDED ACTION:")
    print("  1. Apply cache deep-copy fixes in cache_manager.py")
    print("  2. Remove direct cache mutations in unified_price_manager.py")
    print("  3. Monitor timing pattern after fixes (should stabilize)")
    print("\nFor detailed fix instructions, see:")
    print("  planning_docs/ATTRIBUTE_RESET_BUG_FIX.md")


def analyze_home_assistant_logs(log_file: str = None):
    """
    Analyze Home Assistant logs for update patterns.
    
    This is a placeholder - actual implementation would parse HA logs
    to extract actual timing data.
    """
    print("Log analysis feature - coming soon")
    print("Would parse home-assistant.log for GE-Spot update events")
    return None


if __name__ == "__main__":
    print("GE-Spot Attribute Reset Debug Analyzer")
    print("======================================\n")
    
    if len(sys.argv) > 1 and sys.argv[1] == "logs":
        analyze_home_assistant_logs()
    else:
        simulate_bug_scenario()
