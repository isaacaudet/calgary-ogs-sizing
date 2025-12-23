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
    
    # Check if we need to re-run simulation
    run_sim = True
    if out_file.exists():
        # Check if output is newer than input
        if out_file.stat().st_mtime > inp_file.stat().st_mtime:
            print(f"Using existing output: {out_file}")
            print(f"Size: {out_file.stat().st_size / (1024*1024):.1f} MB")
            run_sim = False
    
    if run_sim:
        print("Running 1-year continuous simulation (2020)...")
        print("This may take 1-5 minutes depending on resources...")
        
        t_start = time.perf_counter()
        
        try:
            from swmm.toolkit import solver
            
            # Use full workflow to ensure proper output file finalization
            # swmm_run() alone may not properly close the output file
            solver.swmm_open(str(inp_file), str(rpt_file), str(out_file))
            solver.swmm_start(True)  # True = save results to output file
            
            # Run simulation step by step
            step_count = 0
            while True:
                elapsed_time = solver.swmm_step()
                step_count += 1
                if step_count % 1000 == 0:
                    print(f"  Step {step_count}, elapsed: {elapsed_time:.1f} seconds")
                if elapsed_time == 0:
                    break
            
            solver.swmm_end()
            solver.swmm_close()
            
            t_sim = time.perf_counter() - t_start
            print(f"\n>>> SWMM SIMULATION TIME: {t_sim:.2f} seconds <<<")
            print(f">>> Total steps: {step_count:,} <<<")
            
            if out_file.exists():
                print(f"Output file: {out_file}")
                print(f"Size: {out_file.stat().st_size / (1024*1024):.1f} MB")
            
            # Print report file to see any errors/warnings
            if rpt_file.exists():
                print("\n--- SWMM REPORT FILE (last 100 lines) ---")
                with open(rpt_file, 'r') as f:
                    lines = f.readlines()
                    for line in lines[-100:]:
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
    # STEP 3: OGS Sizing Analysis
    # =========================================================================
    print("\n[STEP 3/3] Calculating Q_wq (Water Quality Flow Rate)...")
    print("-" * 70)
    
    if not out_file.exists():
        print(f"ERROR: Output file not found: {out_file}")
        return 1
    
    # Import and run OGS analysis
    from ogs_sizing import read_link_flow_series, calculate_qwq, format_flow
    import logging
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    logger = logging.getLogger(__name__)
    
    LINK_ID = "Link_1"
    CAPTURE_PERCENTAGES = [50, 75, 80, 90, 95]
    
    # Read data
    print(f"\nReading flow series for link: {LINK_ID}")
    t_read_start = time.perf_counter()
    
    flows, dt_seconds = read_link_flow_series(str(out_file), LINK_ID)
    
    t_read = time.perf_counter() - t_read_start
    print(f">>> FILE READ TIME: {t_read:.4f} seconds <<<")
    print(f"Records: {len(flows):,}")
    print(f"Time span: {len(flows) * dt_seconds / 86400 / 365.25:.1f} years")
    
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
    print(f"  File Read:      {t_read:.4f} s")
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

