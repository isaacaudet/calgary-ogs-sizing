#!/usr/bin/env python3
"""
Fast OGS Sizing - Uses pre-computed flow data for instant results.
"""

import time
import numpy as np
from pathlib import Path


# Pre-load flow data at module import (cold start optimization)
FLOWS_FILE = Path("calgary_flows_30yr.npy")
CACHED_FLOWS = None
DT_SECONDS = 3600  # 1-hour intervals


def load_flows():
    """Load pre-computed flows (cached after first load)."""
    global CACHED_FLOWS
    if CACHED_FLOWS is None:
        if not FLOWS_FILE.exists():
            raise FileNotFoundError(
                f"Pre-computed flows not found: {FLOWS_FILE}\n"
                "Run: python precompute_flows.py"
            )
        CACHED_FLOWS = np.load(FLOWS_FILE)
    return CACHED_FLOWS


def calculate_qwq_fast(area_ha=66.0, imperv_pct=55.0, capture_pcts=[50, 75, 80, 90, 95]):
    """
    Calculate Q_wq for given catchment parameters.
    
    Uses pre-computed flows scaled by catchment characteristics.
    
    Args:
        area_ha: Catchment area in hectares (default: 66 ha)
        imperv_pct: Percent impervious (default: 55%)
        capture_pcts: List of capture percentages to calculate
        
    Returns:
        Dictionary with Q_wq values and statistics
    """
    t_start = time.perf_counter()
    
    # Load pre-computed flows (for 66 ha, 55% impervious reference catchment)
    base_flows = load_flows()
    
    # Scale flows based on area and imperviousness
    # Reference: 66 ha, 55% impervious
    area_factor = area_ha / 66.0
    imperv_factor = imperv_pct / 55.0
    
    # Simple linear scaling (reasonable approximation)
    flows = base_flows * area_factor * imperv_factor
    
    # Filter dry weather (threshold: 0.0001 CMS = 0.1 L/s)
    wet_mask = flows > 0.0001
    wet_flows = flows[wet_mask]
    
    if len(wet_flows) == 0:
        return {"error": "No wet weather flows found"}
    
    # Calculate volumes
    volumes = wet_flows * DT_SECONDS  # m³
    total_volume = volumes.sum()
    
    # Sort flows ascending
    sorted_indices = np.argsort(wet_flows)
    sorted_flows = wet_flows[sorted_indices]
    sorted_volumes = volumes[sorted_indices]
    
    # Cumulative volume
    cumulative_volume = np.cumsum(sorted_volumes)
    cumulative_pct = cumulative_volume / total_volume * 100
    
    # Find Q_wq at each capture percentage
    capture_flows = {}
    for pct in capture_pcts:
        idx = np.searchsorted(cumulative_pct, pct)
        if idx >= len(sorted_flows):
            idx = len(sorted_flows) - 1
        capture_flows[pct] = float(sorted_flows[idx])
    
    t_process = time.perf_counter() - t_start
    
    return {
        "q_wq_90_cms": capture_flows.get(90, 0),
        "q_wq_90_lps": capture_flows.get(90, 0) * 1000,
        "total_volume_m3": float(total_volume),
        "wet_periods": int(wet_mask.sum()),
        "dry_periods": int((~wet_mask).sum()),
        "capture_flows": capture_flows,
        "input_params": {
            "area_ha": area_ha,
            "imperv_pct": imperv_pct
        },
        "timing": {
            "process_seconds": t_process
        },
        "stats": {
            "min_flow_cms": float(wet_flows.min()),
            "max_flow_cms": float(wet_flows.max()),
            "mean_flow_cms": float(wet_flows.mean()),
            "median_flow_cms": float(np.median(wet_flows))
        }
    }


def main():
    """Quick test of fast OGS sizing."""
    import json
    
    print("=" * 70)
    print("FAST OGS SIZING (Pre-computed Flows)")
    print("=" * 70)
    
    # Test with default parameters
    result = calculate_qwq_fast()
    
    print(f"\nProcessing time: {result['timing']['process_seconds']*1000:.2f} ms")
    print(f"\nQ_wq (90%): {result['q_wq_90_cms']:.4f} CMS ({result['q_wq_90_lps']:.1f} L/s)")
    print(f"Total volume: {result['total_volume_m3']:,.0f} m³")
    
    print("\nCapture Curve:")
    print("-" * 40)
    for pct, flow in result['capture_flows'].items():
        marker = " <<<" if pct == 90 else ""
        print(f"  {pct}%: {flow:.4f} CMS ({flow*1000:.1f} L/s){marker}")
    
    print("\n[JSON OUTPUT]")
    print(json.dumps(result, indent=2))
    
    # Test with different catchment sizes
    print("\n" + "=" * 70)
    print("SCALING TEST - Different Catchment Sizes")
    print("=" * 70)
    
    test_cases = [
        (10, 40),   # Small residential
        (66, 55),   # Reference (Calgary model)
        (100, 70),  # Large commercial
        (200, 80),  # Industrial
    ]
    
    print(f"\n{'Area (ha)':<12} {'Imperv %':<12} {'Q_wq 90% (L/s)':<18} {'Time (ms)':<12}")
    print("-" * 54)
    
    for area, imperv in test_cases:
        t0 = time.perf_counter()
        r = calculate_qwq_fast(area_ha=area, imperv_pct=imperv)
        t1 = time.perf_counter()
        print(f"{area:<12} {imperv:<12} {r['q_wq_90_lps']:<18.1f} {(t1-t0)*1000:<12.2f}")


if __name__ == "__main__":
    main()

