#!/usr/bin/env python3
"""
Calgary OGS Sizing Analysis - Main Entry Point

Fast mode: Uses pre-computed 30-year flows (~10ms)
Full mode: Runs SWMM simulation if pre-computed data missing (~4 min)
"""

import time
import sys
import os
import json
from pathlib import Path

# Initialize Sentry for error tracking
import sentry_sdk

sentry_sdk.init(
    dsn="https://3ccbff0225190883daf241fbfbac83e9@o4510583078322176.ingest.us.sentry.io/4510583080681472",
    traces_sample_rate=1.0,
    send_default_pii=True,
    environment=os.environ.get("RAILWAY_ENVIRONMENT", "production"),
)
print("Sentry initialized for error tracking")


def main():
    total_start = time.perf_counter()
    
    print("=" * 70)
    print("CALGARY OGS SIZING ANALYSIS")
    print("=" * 70)
    print(f"Python: {sys.version}")
    print(f"Working directory: {os.getcwd()}")
    print("=" * 70)
    
    # Check for pre-computed flows (fast path)
    flows_file = Path("calgary_flows_30yr.npy")
    
    if flows_file.exists():
        # =====================================================================
        # FAST MODE: Use pre-computed flows
        # =====================================================================
        print("\n[FAST MODE] Using pre-computed 30-year flows")
        print("-" * 70)
        
        from fast_ogs_sizing import calculate_qwq_fast
        
        # Get parameters from environment or use defaults
        area_ha = float(os.environ.get("AREA_HA", 66.0))
        imperv_pct = float(os.environ.get("IMPERV_PCT", 55.0))
        
        print(f"Catchment: {area_ha} ha, {imperv_pct}% impervious")
        
        t_start = time.perf_counter()
        result = calculate_qwq_fast(area_ha=area_ha, imperv_pct=imperv_pct)
        t_process = time.perf_counter() - t_start
        
        print(f"\n>>> PROCESSING TIME: {t_process*1000:.2f} ms <<<")
        
    else:
        # =====================================================================
        # FULL MODE: Run SWMM simulation
        # =====================================================================
        print("\n[FULL MODE] Pre-computed flows not found, running simulation...")
        print("-" * 70)
        
        # Generate rainfall if needed
        rainfall_file = Path("calgary_rainfall.dat")
        if not rainfall_file.exists():
            print("Generating 30-year rainfall data...")
            from generate_calgary_rainfall import generate_calgary_rainfall
            generate_calgary_rainfall(
                start_year=1991,
                end_year=2020,
                output_file="calgary_rainfall.dat",
                seed=42
            )
        
        inp_file = Path("calgary_model.inp")
        rpt_file = Path("calgary_model.rpt")
        out_file = Path("model_run.out")
        
        print("Running 30-year SWMM simulation...")
        t_sim_start = time.perf_counter()
        
        from pyswmm import Simulation, Links
        import numpy as np
        
        flow_data = []
        
        with Simulation(str(inp_file)) as sim:
            link = Links(sim)["Link_1"]
            print(f"Found Link_1: {link.linkid}")
            
            step_count = 0
            last_hour = -1
            
            for step in sim:
                step_count += 1
                current_hour = sim.current_time.hour + (sim.current_time.day - 1) * 24
                
                if current_hour != last_hour:
                    flow_cms = abs(link.flow)
                    flow_data.append(flow_cms)
                    last_hour = current_hour
                    
                    if len(flow_data) % 50000 == 0:
                        print(f"  Captured {len(flow_data):,} flow records...")
        
        t_sim = time.perf_counter() - t_sim_start
        print(f"\n>>> SIMULATION TIME: {t_sim:.1f} seconds <<<")
        
        # Save for next time
        flows = np.array(flow_data, dtype=np.float32)
        np.save(flows_file, flows)
        print(f"Saved flows to: {flows_file}")
        
        # Calculate Q_wq
        from ogs_sizing import calculate_qwq
        
        t_process_start = time.perf_counter()
        result = calculate_qwq(flows, dt_seconds=3600, capture_percentages=[50, 75, 80, 90, 95])
        t_process = time.perf_counter() - t_process_start
        
        # Format result to match fast_ogs_sizing output
        result = {
            "q_wq_90_cms": result['capture_flows'][90],
            "q_wq_90_lps": result['capture_flows'][90] * 1000,
            "total_volume_m3": result['total_volume_m3'],
            "wet_periods": result['total_wet_periods'],
            "dry_periods": result['total_dry_periods'],
            "capture_flows": {str(k): v for k, v in result['capture_flows'].items()},
            "timing": {
                "simulation_seconds": t_sim,
                "process_seconds": t_process
            },
            "stats": result['stats']
        }
    
    # =========================================================================
    # OUTPUT RESULTS
    # =========================================================================
    total_time = time.perf_counter() - total_start
    
    print("\n" + "=" * 70)
    print("CAPTURE CURVE RESULTS")
    print("=" * 70)
    print(f"{'Capture %':<15} {'Q_wq (CMS)':<20} {'Q_wq (L/s)':<15}")
    print("-" * 70)
    
    for pct in [50, 75, 80, 90, 95]:
        pct_key = pct if pct in result['capture_flows'] else str(pct)
        q_wq = result['capture_flows'].get(pct_key, 0)
        marker = " <<<" if pct == 90 else ""
        print(f"{pct}%{'':<12} {q_wq:.6f}{'':<13} {q_wq*1000:.2f}{marker}")
    
    print("=" * 70)
    print(f"\n>>> WATER QUALITY FLOW RATE (90%): {result['q_wq_90_cms']:.4f} CMS <<<")
    print(f">>> Q_wq (90%): {result['q_wq_90_lps']:.1f} L/s <<<")
    print(f">>> Total runoff volume: {result['total_volume_m3']:,.0f} m³ <<<")
    
    print("\n" + "=" * 70)
    print("TIMING SUMMARY")
    print("=" * 70)
    print(f"  Total runtime: {total_time*1000:.1f} ms ({total_time:.2f} s)")
    print("=" * 70)
    
    # Add total time to result
    result['timing']['total_seconds'] = total_time
    
    print("\n[JSON OUTPUT]")
    print(json.dumps(result, indent=2))
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
