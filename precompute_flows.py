#!/usr/bin/env python3
"""
Pre-compute 30-year flow time series from SWMM simulation.
Run once during build, then OGS sizing is instant.
"""

import time
import numpy as np
from pathlib import Path


def precompute_flows():
    """Run SWMM simulation and save flow data to numpy file."""
    print("=" * 70)
    print("PRE-COMPUTING 30-YEAR FLOW TIME SERIES")
    print("=" * 70)
    
    # Generate rainfall if needed
    rainfall_file = Path("calgary_rainfall.dat")
    if not rainfall_file.exists():
        print("Generating rainfall data...")
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
    
    print(f"\nRunning 30-year SWMM simulation...")
    t_start = time.perf_counter()
    
    from pyswmm import Simulation, Links
    
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
    
    t_sim = time.perf_counter() - t_start
    print(f"\n>>> SIMULATION TIME: {t_sim:.1f} seconds <<<")
    print(f">>> Flow records: {len(flow_data):,} <<<")
    
    # Save to numpy file
    flows = np.array(flow_data, dtype=np.float32)
    output_file = Path("calgary_flows_30yr.npy")
    np.save(output_file, flows)
    
    print(f"\nSaved to: {output_file}")
    print(f"File size: {output_file.stat().st_size / 1024:.1f} KB")
    print(f"Flow stats: min={flows.min():.6f}, max={flows.max():.4f}, mean={flows.mean():.6f} CMS")
    
    return flows


if __name__ == "__main__":
    precompute_flows()

