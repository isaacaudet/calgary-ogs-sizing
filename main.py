#!/usr/bin/env python3
"""
Calgary OGS Sizing Analysis - Main Entry Point

Runs the complete pipeline:
1. Generate Calgary rainfall (if not exists)
2. Run SWMM continuous simulation
3. Calculate Q_wq (90% Water Quality Flow Rate)

For Railway cloud deployment benchmarking.
"""

import time
import sys
import os
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
    print("CALGARY OGS SIZING ANALYSIS - RAILWAY BENCHMARK")
    print("=" * 70)
    print(f"Python: {sys.version}")
    print(f"Working directory: {os.getcwd()}")
    print("=" * 70)
    
    # =========================================================================
    # STEP 1: Generate rainfall data (if needed)
    # =========================================================================
    print("\n[STEP 1/3] Checking rainfall data...")
    
    rainfall_file = Path("calgary_rainfall.dat")
    
    if not rainfall_file.exists():
        print("Generating 30 years of Calgary rainfall...")
        t_start = time.perf_counter()
        
        from generate_calgary_rainfall import generate_calgary_rainfall
        generate_calgary_rainfall(
            start_year=1991,
            end_year=2020,
            output_file="calgary_rainfall.dat",
            seed=42
        )
        
        t_rainfall = time.perf_counter() - t_start
        print(f"Rainfall generation: {t_rainfall:.2f} s")
    else:
        print(f"Using existing rainfall data: {rainfall_file}")
        print(f"Size: {rainfall_file.stat().st_size / 1024:.1f} KB")
    
    # =========================================================================
    # STEP 2: Run SWMM simulation
    # =========================================================================
    print("\n[STEP 2/3] Running SWMM simulation...")
    print("-" * 70)
    
    inp_file = Path("calgary_model.inp")
    out_file = Path("model_run.out")
    rpt_file = Path("calgary_model.rpt")
    
    if not inp_file.exists():
        print(f"ERROR: Model file not found: {inp_file}")
        return 1
    
    # Always delete old output to ensure fresh run
    if out_file.exists():
        out_file.unlink()
        print("Deleted old output file")
    if rpt_file.exists():
        rpt_file.unlink()
    
    print("Running 1-year continuous simulation (2020)...")
    print("Capturing flow data during simulation...")
    
    t_start = time.perf_counter()
    flow_data = []  # Store (elapsed_hours, flow_cms) tuples
    
    try:
        from swmm.toolkit import solver
        import numpy as np
        
        # Use stepped approach to capture flow data directly
        solver.swmm_open(str(inp_file), str(rpt_file), str(out_file))
        solver.swmm_start(1)  # 1 = save results
        
        # Find link index for Link_1
        link_idx = solver.swmm_getObjectIndex(3, "Link_1")  # 3 = LINK object type
        print(f"Link_1 index: {link_idx}")
        
        step_count = 0
        report_interval = 3600  # Report every hour (3600 seconds)
        last_report = 0
        
        while True:
            elapsed_sec = solver.swmm_step()
            if elapsed_sec == 0:
                break
            
            step_count += 1
            
            # Get flow at report intervals (approximately hourly)
            if elapsed_sec - last_report >= report_interval:
                # Get current flow rate for Link_1 (attribute 0 = flow rate)
                flow_cms = solver.swmm_getLinkResult(link_idx, 0)
                flow_data.append((elapsed_sec / 3600, flow_cms))  # Store hours, flow
                last_report = elapsed_sec
                
                if len(flow_data) % 100 == 0:
                    print(f"  Captured {len(flow_data)} flow records, elapsed: {elapsed_sec/86400:.1f} days")
        
        solver.swmm_end()
        solver.swmm_close()
        
        t_sim = time.perf_counter() - t_start
        print(f"\n>>> SWMM SIMULATION TIME: {t_sim:.2f} seconds <<<")
        print(f">>> Total steps: {step_count:,} <<<")
        print(f">>> Flow records captured: {len(flow_data):,} <<<")
        
        # Convert to numpy array for analysis
        if flow_data:
            flows = np.array([f[1] for f in flow_data])
            print(f"Flow stats: min={flows.min():.4f}, max={flows.max():.4f}, mean={flows.mean():.4f} CMS")
        
        # Print report file summary
        if rpt_file.exists():
            print("\n--- SWMM REPORT FILE (last 50 lines) ---")
            with open(rpt_file, 'r') as f:
                lines = f.readlines()
                for line in lines[-50:]:
                    print(line.rstrip())
            print("--- END REPORT ---\n")
        
    except Exception as e:
        print(f"ERROR during simulation: {e}")
        import traceback
        traceback.print_exc()
        # Try to close SWMM gracefully
        try:
            solver.swmm_end()
            solver.swmm_close()
        except:
            pass
        import sentry_sdk
        sentry_sdk.capture_exception(e)
        return 1
    
    # =========================================================================
    # STEP 3: OGS Sizing Analysis (using captured flow data)
    # =========================================================================
    print("\n[STEP 3/3] Calculating Q_wq (Water Quality Flow Rate)...")
    print("-" * 70)
    
    if not flow_data:
        print("ERROR: No flow data captured during simulation")
        return 1
    
    # Import analysis functions
    from ogs_sizing import calculate_qwq, format_flow
    import numpy as np
    
    CAPTURE_PERCENTAGES = [50, 75, 80, 90, 95]
    
    # Use captured flow data
    print(f"\nUsing {len(flow_data):,} captured flow records")
    flows = np.array([f[1] for f in flow_data])
    dt_seconds = 3600  # 1 hour intervals
    
    # Process data
    print("\nCalculating capture curve...")
    t_process_start = time.perf_counter()
    
    results = calculate_qwq(flows, dt_seconds, CAPTURE_PERCENTAGES)
    
    t_process = time.perf_counter() - t_process_start
    print(f">>> PROCESSING TIME: {t_process:.4f} seconds <<<")
    
    # =========================================================================
    # RESULTS
    # =========================================================================
    print("\n" + "=" * 70)
    print("CAPTURE CURVE RESULTS")
    print("=" * 70)
    print(f"{'Capture %':<15} {'Q_wq (CMS)':<20} {'Q_wq (L/s)':<15}")
    print("-" * 70)
    
    for pct in CAPTURE_PERCENTAGES:
        q_wq = results['capture_flows'][pct]
        marker = " <<<" if pct == 90 else ""
        print(f"{pct}%{'':<12} {q_wq:.6f}{'':<13} {q_wq*1000:.2f}{marker}")
    
    print("=" * 70)
    
    q_wq_90 = results['capture_flows'][90]
    print(f"\n>>> WATER QUALITY FLOW RATE (90%): {format_flow(q_wq_90)} <<<")
    print(f">>> Total runoff volume: {results['total_volume_m3']:,.0f} m³ <<<")
    
    # =========================================================================
    # TIMING SUMMARY
    # =========================================================================
    total_time = time.perf_counter() - total_start
    
    print("\n" + "=" * 70)
    print("BENCHMARK TIMING SUMMARY")
    print("=" * 70)
    print(f"  Simulation:     {t_sim:.2f} s")
    print(f"  Processing:     {t_process:.4f} s")
    print(f"  TOTAL RUNTIME:  {total_time:.2f} s")
    print("=" * 70)
    
    # Output JSON for programmatic access
    import json
    output = {
        "q_wq_90_cms": q_wq_90,
        "q_wq_90_lps": q_wq_90 * 1000,
        "total_volume_m3": results['total_volume_m3'],
        "wet_periods": results['total_wet_periods'],
        "dry_periods": results['total_dry_periods'],
        "capture_flows": {str(k): v for k, v in results['capture_flows'].items()},
        "timing": {
            "read_seconds": t_read,
            "process_seconds": t_process,
            "total_seconds": total_time
        },
        "stats": results['stats']
    }
    
    print("\n[JSON OUTPUT]")
    print(json.dumps(output, indent=2))
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

