#!/usr/bin/env python3
"""
Run Calgary SWMM Continuous Simulation

This script:
1. Generates 30 years of Calgary synthetic rainfall data
2. Runs the SWMM simulation
3. Produces the .out file for OGS sizing analysis

Prerequisites:
    pip install swmm-toolkit numpy
"""

import time
import sys
from pathlib import Path


def main():
    print("=" * 60)
    print("CALGARY SWMM CONTINUOUS SIMULATION")
    print("=" * 60)
    
    # Step 1: Generate rainfall data
    print("\n[1/3] Generating Calgary rainfall data (1991-2020)...")
    print("-" * 60)
    
    t_start = time.perf_counter()
    
    # Import and run rainfall generator
    from generate_calgary_rainfall import generate_calgary_rainfall
    
    rainfall_stats = generate_calgary_rainfall(
        start_year=1991,
        end_year=2020,
        output_file="calgary_rainfall.dat",
        seed=42  # For reproducibility
    )
    
    t_rainfall = time.perf_counter() - t_start
    print(f"\nRainfall generation time: {t_rainfall:.2f} seconds")
    
    # Check files exist
    if not Path("calgary_rainfall.dat").exists():
        print("ERROR: Rainfall file not generated!")
        return 1
    
    if not Path("calgary_model.inp").exists():
        print("ERROR: calgary_model.inp not found!")
        return 1
    
    # Step 2: Run SWMM simulation
    print("\n[2/3] Running SWMM simulation...")
    print("-" * 60)
    print("This may take several minutes for 30 years of data...")
    
    t_start = time.perf_counter()
    
    try:
        from swmm.toolkit import solver
        
        # Run the simulation
        solver.run(
            "calgary_model.inp",
            "calgary_model.rpt", 
            "model_run.out"
        )
        
        t_sim = time.perf_counter() - t_start
        print(f"\nSimulation completed in {t_sim:.2f} seconds")
        
    except ImportError:
        print("\nERROR: swmm-toolkit not installed!")
        print("Install with: pip install swmm-toolkit")
        return 1
    except Exception as e:
        print(f"\nERROR during simulation: {e}")
        return 1
    
    # Verify output
    if not Path("model_run.out").exists():
        print("ERROR: Output file not generated!")
        return 1
    
    out_size = Path("model_run.out").stat().st_size / (1024 * 1024)
    print(f"Output file: model_run.out ({out_size:.1f} MB)")
    
    # Step 3: Summary
    print("\n[3/3] Summary")
    print("-" * 60)
    print(f"  Rainfall data:    calgary_rainfall.dat")
    print(f"  SWMM model:       calgary_model.inp")
    print(f"  Report file:      calgary_model.rpt")
    print(f"  Output file:      model_run.out")
    print(f"  Target link:      Link_1 (OGS inlet)")
    print(f"\n  Total runtime:    {t_rainfall + t_sim:.2f} seconds")
    
    print("\n" + "=" * 60)
    print("READY FOR OGS SIZING ANALYSIS")
    print("=" * 60)
    print("\nRun: python ogs_sizing.py")
    print("=" * 60)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

