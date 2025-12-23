#!/usr/bin/env python3
"""
OGS (Oil Grit Separator) Sizing Analysis Script

Calculates the Water Quality Flow Rate (Q_wq) required to treat 90% of the 
total cumulative runoff volume from SWMM continuous simulation output.

Uses swmm-toolkit (swmm.output) for lightweight, fast binary file reading.
"""

import time
import logging
from pathlib import Path
import numpy as np

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def get_swmm_output_module():
    """
    Import and return the appropriate SWMM output module.
    """
    try:
        from swmm.toolkit import output, shared_enum
        return output, shared_enum
    except ImportError:
        raise ImportError(
            "swmm-toolkit not installed. Install with: pip install swmm-toolkit"
        )


def find_link_index(handle, output, shared_enum, link_id: str) -> int:
    """
    Find the index of a link by its ID/name.
    
    swmm-toolkit doesn't provide a direct get_link_index() function,
    so we iterate through all links to find the matching name.
    
    Args:
        handle: SWMM output handle
        output: swmm.toolkit.output module
        shared_enum: swmm.toolkit.shared_enum module
        link_id: The link ID to find
        
    Returns:
        Link index (0-based)
        
    Raises:
        ValueError: If link not found
    """
    # Get project size to find number of links
    proj_size = output.get_proj_size(handle)
    n_links = proj_size[shared_enum.ElementType.LINK]
    
    # Search for the link by name
    for idx in range(n_links):
        name = output.get_elem_name(handle, shared_enum.ElementType.LINK, idx)
        if name == link_id:
            return idx
    
    # If not found, list available links for debugging
    available_links = []
    for idx in range(min(n_links, 10)):  # First 10 links
        available_links.append(output.get_elem_name(handle, shared_enum.ElementType.LINK, idx))
    
    raise ValueError(
        f"Link '{link_id}' not found in output file. "
        f"Available links (first 10): {available_links}"
    )


def read_link_flow_series(
    outfile_path: str, 
    link_id: str
) -> tuple[np.ndarray, float]:
    """
    Read flow time series for a specific link from SWMM binary output.
    
    Args:
        outfile_path: Path to .out file
        link_id: SWMM link identifier
        
    Returns:
        Tuple of (flow_rates, report_step_seconds)
    """
    output, shared_enum = get_swmm_output_module()
    logger.info(f"  Using: swmm-toolkit")
    
    handle = None
    try:
        # Initialize and open the binary output file
        handle = output.init()
        output.open(handle, outfile_path)
        
        # Get project size info
        proj_size = output.get_proj_size(handle)
        n_links = proj_size[shared_enum.ElementType.LINK]
        n_periods = proj_size[4]  # PERIODS is index 4
        logger.info(f"  Total links: {n_links}, Total periods: {n_periods:,}")
        
        # Find link index by name
        link_index = find_link_index(handle, output, shared_enum, link_id)
        logger.info(f"  Link '{link_id}' found at index: {link_index}")
        
        # Get report step duration in seconds
        report_step_sec = output.get_times(handle, shared_enum.Time.REPORT_STEP)
        
        # Get the full flow series for the link
        # LinkAttribute.FLOW_RATE = 0
        flow_series = output.get_link_series(
            handle, 
            link_index, 
            shared_enum.LinkAttribute.FLOW_RATE,
            0,              # Start period (0-indexed)
            n_periods - 1   # End period (inclusive)
        )
        
        # Convert to numpy array for vectorized operations
        flows = np.array(flow_series, dtype=np.float64)
        
        return flows, float(report_step_sec)
        
    finally:
        if handle is not None:
            output.close(handle)


def calculate_qwq(
    flows: np.ndarray, 
    dt_seconds: float,
    capture_pcts: list[float] = [50, 75, 80, 90, 95],
    flow_threshold: float = 0.0001  # CMS threshold for "wet" flow
) -> dict:
    """
    Calculate the Water Quality Flow Rate for specified capture percentages.
    
    The algorithm:
    1. Filter out dry weather (zero/low) flows
    2. Calculate volume = flow * time_step for each period
    3. Sort flows from low to high
    4. Calculate cumulative volume
    5. Find flow rate at each target capture percentage
    
    Args:
        flows: Array of flow rates (CMS)
        dt_seconds: Time step duration in seconds
        capture_pcts: List of capture percentages to calculate
        flow_threshold: Minimum flow to consider (filters dry weather)
        
    Returns:
        Dictionary with results including Q_wq values and stats
    """
    # Filter out dry weather flows (below threshold)
    wet_mask = flows > flow_threshold
    wet_flows = flows[wet_mask]
    
    if len(wet_flows) == 0:
        raise ValueError("No wet weather flows found above threshold")
    
    # Calculate volumes (CMS * seconds = cubic meters)
    volumes = wet_flows * dt_seconds
    
    # Sort flows from low to high for cumulative analysis
    # We need to sort both flows and their corresponding volumes together
    sort_indices = np.argsort(wet_flows)
    sorted_flows = wet_flows[sort_indices]
    sorted_volumes = volumes[sort_indices]
    
    # Calculate cumulative volume from low flows to high flows
    cumulative_volume = np.cumsum(sorted_volumes)
    total_volume = cumulative_volume[-1]
    
    # Calculate cumulative percentage
    cumulative_pct = (cumulative_volume / total_volume) * 100
    
    # Find Q_wq for each capture percentage
    results = {
        'total_volume_m3': total_volume,
        'total_wet_periods': len(wet_flows),
        'total_dry_periods': int(np.sum(~wet_mask)),
        'capture_flows': {},
        'stats': {
            'min_flow_cms': float(np.min(wet_flows)),
            'max_flow_cms': float(np.max(wet_flows)),
            'mean_flow_cms': float(np.mean(wet_flows)),
            'median_flow_cms': float(np.median(wet_flows)),
        }
    }
    
    for pct in capture_pcts:
        # Find index where cumulative percentage first reaches target
        idx = np.searchsorted(cumulative_pct, pct)
        if idx >= len(sorted_flows):
            idx = len(sorted_flows) - 1
        
        q_wq = sorted_flows[idx]
        results['capture_flows'][pct] = float(q_wq)
    
    return results


def format_flow(cms: float) -> str:
    """Format flow rate with appropriate units."""
    if cms < 0.001:
        return f"{cms * 1000:.4f} L/s"
    elif cms < 1.0:
        return f"{cms:.6f} CMS ({cms * 1000:.2f} L/s)"
    else:
        return f"{cms:.4f} CMS"


def main():
    """Main execution function with timing benchmarks."""
    
    # Configuration
    OUTFILE = "model_run.out"
    LINK_ID = "Link_1"
    CAPTURE_PERCENTAGES = [50, 75, 80, 90, 95]
    
    logger.info("=" * 60)
    logger.info("OGS SIZING ANALYSIS - Water Quality Flow Rate Calculation")
    logger.info("=" * 60)
    logger.info(f"Input file: {OUTFILE}")
    logger.info(f"Target link: {LINK_ID}")
    
    # Check file exists
    if not Path(OUTFILE).exists():
        logger.error(f"Output file not found: {OUTFILE}")
        logger.error("Please ensure 'model_run.out' is in the current directory")
        return None
    
    # =========================================================================
    # PHASE 1: READ DATA (benchmark file I/O)
    # =========================================================================
    logger.info("-" * 60)
    logger.info("PHASE 1: Reading SWMM binary output...")
    
    t_read_start = time.perf_counter()
    
    try:
        flows, dt_seconds = read_link_flow_series(OUTFILE, LINK_ID)
    except Exception as e:
        logger.error(f"Failed to read output file: {e}")
        raise
    
    t_read_end = time.perf_counter()
    t_read = t_read_end - t_read_start
    
    logger.info(f"  Records read: {len(flows):,}")
    logger.info(f"  Report step: {dt_seconds:.0f} seconds")
    logger.info(f"  Time span: {len(flows) * dt_seconds / 86400 / 365.25:.1f} years")
    logger.info(f"  READ TIME: {t_read:.4f} seconds")
    
    # =========================================================================
    # PHASE 2: PROCESS DATA (benchmark computation)
    # =========================================================================
    logger.info("-" * 60)
    logger.info("PHASE 2: Processing flow data...")
    
    t_process_start = time.perf_counter()
    
    results = calculate_qwq(flows, dt_seconds, CAPTURE_PERCENTAGES)
    
    t_process_end = time.perf_counter()
    t_process = t_process_end - t_process_start
    
    logger.info(f"  Wet weather periods: {results['total_wet_periods']:,}")
    logger.info(f"  Dry weather periods: {results['total_dry_periods']:,}")
    logger.info(f"  Total runoff volume: {results['total_volume_m3']:,.0f} m³")
    logger.info(f"  PROCESS TIME: {t_process:.4f} seconds")
    
    # =========================================================================
    # RESULTS: Q_wq Capture Curve Summary
    # =========================================================================
    logger.info("-" * 60)
    logger.info("CAPTURE CURVE SUMMARY")
    logger.info("-" * 60)
    
    print("\n" + "=" * 60)
    print("  CAPTURE RATE  |  Q_wq (Flow Rate)")
    print("=" * 60)
    
    for pct in CAPTURE_PERCENTAGES:
        q_wq = results['capture_flows'][pct]
        marker = " <<<" if pct == 90 else ""
        print(f"      {pct:3d}%      |  {format_flow(q_wq)}{marker}")
    
    print("=" * 60)
    
    # Highlight the target 90% Q_wq
    q_wq_90 = results['capture_flows'][90]
    print(f"\n>>> WATER QUALITY FLOW RATE (90% capture): {format_flow(q_wq_90)}")
    print(f">>> This flow treats 90% of the total {results['total_volume_m3']:,.0f} m³ runoff\n")
    
    # =========================================================================
    # FLOW STATISTICS
    # =========================================================================
    logger.info("-" * 60)
    logger.info("FLOW STATISTICS")
    stats = results['stats']
    logger.info(f"  Min flow:    {format_flow(stats['min_flow_cms'])}")
    logger.info(f"  Max flow:    {format_flow(stats['max_flow_cms'])}")
    logger.info(f"  Mean flow:   {format_flow(stats['mean_flow_cms'])}")
    logger.info(f"  Median flow: {format_flow(stats['median_flow_cms'])}")
    
    # =========================================================================
    # TIMING SUMMARY
    # =========================================================================
    t_total = t_read + t_process
    logger.info("-" * 60)
    logger.info("TIMING BENCHMARK SUMMARY")
    logger.info(f"  File Read:     {t_read:.4f} s ({t_read/t_total*100:.1f}%)")
    logger.info(f"  Processing:    {t_process:.4f} s ({t_process/t_total*100:.1f}%)")
    logger.info(f"  TOTAL:         {t_total:.4f} s")
    logger.info("=" * 60)
    
    return results


if __name__ == "__main__":
    main()
