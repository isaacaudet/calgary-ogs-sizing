#!/usr/bin/env python3
"""
Calgary Synthetic Rainfall Generator

Generates 30+ years of hourly rainfall data based on Calgary, Alberta's 
actual climate statistics from Environment Canada.

Calgary Climate Characteristics:
- Semi-arid continental climate
- Annual precipitation: ~420mm (mostly rain May-September)
- Convective summer storms (short, intense)
- Occasional chinook-influenced winter events
- Average 112 days with measurable precipitation per year

Reference: Environment Canada Climate Normals 1991-2020
Station: Calgary International Airport (YYC)
"""

import numpy as np
from datetime import datetime, timedelta
from pathlib import Path

# Calgary monthly precipitation statistics (mm) - Environment Canada Normals
# https://climate.weather.gc.ca/climate_normals/
CALGARY_MONTHLY_PRECIP = {
    1: {"mean": 11.8, "days": 9},    # January
    2: {"mean": 9.3, "days": 7},     # February  
    3: {"mean": 18.4, "days": 9},    # March
    4: {"mean": 30.2, "days": 9},    # April
    5: {"mean": 56.8, "days": 12},   # May
    6: {"mean": 79.8, "days": 13},   # June (peak)
    7: {"mean": 67.0, "days": 11},   # July
    8: {"mean": 52.5, "days": 10},   # August
    9: {"mean": 41.3, "days": 8},    # September
    10: {"mean": 17.5, "days": 6},   # October
    11: {"mean": 13.1, "days": 7},   # November
    12: {"mean": 12.0, "days": 8},   # December
}

# Storm characteristics by season
STORM_PARAMS = {
    "winter": {  # Nov-Mar: frontal systems, longer duration, lower intensity
        "duration_mean": 8,  # hours
        "duration_std": 4,
        "intensity_max": 5,  # mm/hr
        "intensity_shape": 1.5,  # gamma distribution shape
    },
    "spring": {  # Apr-May: mixed events
        "duration_mean": 4,
        "duration_std": 3,
        "intensity_max": 15,
        "intensity_shape": 1.2,
    },
    "summer": {  # Jun-Aug: convective storms, short intense
        "duration_mean": 2,
        "duration_std": 1.5,
        "intensity_max": 40,  # Calgary can get intense thunderstorms
        "intensity_shape": 0.8,
    },
    "fall": {  # Sep-Oct: transitional
        "duration_mean": 5,
        "duration_std": 3,
        "intensity_max": 10,
        "intensity_shape": 1.3,
    },
}


def get_season(month: int) -> str:
    """Get season for storm parameter selection."""
    if month in [11, 12, 1, 2, 3]:
        return "winter"
    elif month in [4, 5]:
        return "spring"
    elif month in [6, 7, 8]:
        return "summer"
    else:
        return "fall"


def generate_storm(month: int, target_depth: float, rng: np.random.Generator) -> list:
    """
    Generate a single storm event with realistic temporal distribution.
    
    Returns list of hourly intensities (mm/hr).
    """
    season = get_season(month)
    params = STORM_PARAMS[season]
    
    # Storm duration (minimum 1 hour)
    duration = max(1, int(rng.normal(params["duration_mean"], params["duration_std"])))
    
    # Generate intensity profile using gamma distribution (realistic storm shape)
    # Peak typically in first third of storm
    peak_position = rng.uniform(0.2, 0.5)
    
    intensities = []
    for i in range(duration):
        # Position in storm (0-1)
        pos = i / duration
        
        # Intensity envelope: rises to peak, then decays
        if pos < peak_position:
            envelope = (pos / peak_position) ** 0.5
        else:
            envelope = np.exp(-2 * (pos - peak_position))
        
        # Add randomness
        noise = rng.gamma(params["intensity_shape"], 1.0)
        intensity = envelope * noise * params["intensity_max"] / 3
        
        intensities.append(max(0, intensity))
    
    # Scale to match target depth
    total = sum(intensities)
    if total > 0:
        scale = target_depth / total
        intensities = [i * scale for i in intensities]
    
    return intensities


def generate_calgary_rainfall(
    start_year: int = 1991,
    end_year: int = 2020,
    output_file: str = "calgary_rainfall.dat",
    seed: int = 42
) -> dict:
    """
    Generate synthetic Calgary rainfall data for SWMM continuous simulation.
    
    Args:
        start_year: Start year of simulation
        end_year: End year of simulation (inclusive)
        output_file: Output filename for SWMM rainfall data
        seed: Random seed for reproducibility
        
    Returns:
        Dictionary with generation statistics
    """
    rng = np.random.default_rng(seed)
    
    # Initialize tracking
    start_date = datetime(start_year, 1, 1)
    end_date = datetime(end_year + 1, 1, 1)
    total_hours = int((end_date - start_date).total_seconds() / 3600)
    
    # Pre-allocate rainfall array (hourly values)
    rainfall = np.zeros(total_hours)
    
    print(f"Generating {end_year - start_year + 1} years of Calgary rainfall...")
    print(f"Period: {start_year}-01-01 to {end_year}-12-31")
    print(f"Total hours: {total_hours:,}")
    
    # Generate monthly storms
    current_date = start_date
    total_precip = 0
    storm_count = 0
    
    while current_date < end_date:
        month = current_date.month
        year = current_date.year
        
        # Get monthly target
        monthly_stats = CALGARY_MONTHLY_PRECIP[month]
        
        # Add year-to-year variability (±30%)
        annual_factor = rng.normal(1.0, 0.15)
        monthly_target = monthly_stats["mean"] * max(0.5, min(1.5, annual_factor))
        
        # Number of wet days this month (with variability)
        n_storms = max(1, int(rng.poisson(monthly_stats["days"] * 0.7)))
        
        # Distribute precipitation among storms (unequal distribution)
        storm_weights = rng.exponential(1.0, n_storms)
        storm_weights /= storm_weights.sum()
        storm_depths = monthly_target * storm_weights
        
        # Place storms randomly throughout the month
        days_in_month = (datetime(year, month % 12 + 1, 1) if month < 12 
                        else datetime(year + 1, 1, 1)) - datetime(year, month, 1)
        storm_days = sorted(rng.choice(days_in_month.days, size=min(n_storms, days_in_month.days), replace=False))
        
        for day_offset, depth in zip(storm_days, storm_depths):
            if depth < 0.1:  # Skip trace amounts
                continue
                
            # Random start hour (afternoon bias for summer convective storms)
            if get_season(month) == "summer":
                start_hour = int(rng.triangular(12, 16, 22))  # Afternoon bias
            else:
                start_hour = rng.integers(0, 24)
            
            # Generate storm
            storm = generate_storm(month, depth, rng)
            
            # Calculate position in rainfall array
            storm_start = datetime(year, month, day_offset + 1, start_hour)
            hour_offset = int((storm_start - start_date).total_seconds() / 3600)
            
            # Add storm to rainfall array
            for i, intensity in enumerate(storm):
                idx = hour_offset + i
                if 0 <= idx < total_hours:
                    rainfall[idx] += intensity
            
            total_precip += depth
            storm_count += 1
        
        # Move to next month
        if month == 12:
            current_date = datetime(year + 1, 1, 1)
        else:
            current_date = datetime(year, month + 1, 1)
    
    # Write SWMM rainfall file (DAT format)
    print(f"\nWriting {output_file}...")
    
    with open(output_file, 'w') as f:
        # Write header comment
        f.write(";; Calgary Synthetic Rainfall Data\n")
        f.write(f";; Period: {start_year}-{end_year}\n")
        f.write(f";; Generated for SWMM Continuous Simulation\n")
        f.write(";; Station: CALGARY_SYN\n")
        f.write(";;\n")
        
        # Write non-zero rainfall values in SWMM format
        # Format: STA_ID  YYYY  MM  DD  HH  MM  VALUE
        current = start_date
        records_written = 0
        
        for i, value in enumerate(rainfall):
            if value > 0.001:  # Only write non-zero values
                f.write(f"CALGARY_SYN  {current.year}  {current.month:2d}  "
                       f"{current.day:2d}  {current.hour:2d}  00  {value:.4f}\n")
                records_written += 1
            current += timedelta(hours=1)
    
    # Calculate statistics
    wet_hours = np.sum(rainfall > 0.001)
    max_intensity = np.max(rainfall)
    annual_avg = total_precip / (end_year - start_year + 1)
    
    stats = {
        "period": f"{start_year}-{end_year}",
        "total_years": end_year - start_year + 1,
        "total_hours": total_hours,
        "total_precip_mm": total_precip,
        "annual_avg_mm": annual_avg,
        "storm_count": storm_count,
        "wet_hours": int(wet_hours),
        "wet_percent": wet_hours / total_hours * 100,
        "max_intensity_mmhr": max_intensity,
        "records_written": records_written,
        "output_file": output_file,
    }
    
    print(f"\n{'='*50}")
    print("GENERATION COMPLETE")
    print(f"{'='*50}")
    print(f"  Total precipitation: {total_precip:,.1f} mm")
    print(f"  Annual average: {annual_avg:.1f} mm (Calgary normal: ~420 mm)")
    print(f"  Storm events: {storm_count:,}")
    print(f"  Wet hours: {wet_hours:,} ({wet_hours/total_hours*100:.2f}%)")
    print(f"  Max intensity: {max_intensity:.2f} mm/hr")
    print(f"  Records written: {records_written:,}")
    print(f"  Output file: {output_file}")
    print(f"{'='*50}")
    
    return stats


if __name__ == "__main__":
    stats = generate_calgary_rainfall(
        start_year=1991,
        end_year=2020,
        output_file="calgary_rainfall.dat",
        seed=42
    )

