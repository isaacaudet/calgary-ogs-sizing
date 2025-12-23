# Calgary OGS Sizing Analysis

**Water Quality Flow Rate (Q_wq) Calculator for Oil-Grit Separator Sizing**

Uses EPA SWMM continuous simulation (30 years) to calculate the flow rate required to treat 90% of total runoff volume.

## 🚀 Deploy to Railway

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template/new)

1. Fork this repository
2. Connect to Railway
3. Deploy - the simulation runs automatically

## 📊 What This Does

1. **Generates** 30 years of Calgary synthetic rainfall (1991-2020) based on Environment Canada climate normals
2. **Runs** EPA SWMM continuous simulation for a 66-hectare urban catchment
3. **Calculates** the Water Quality Flow Rate (Q_wq) at various capture percentages

### Calgary Model Specifications

| Parameter | Value |
|-----------|-------|
| Simulation Period | 1991-2020 (30 years) |
| Catchment Area | 66 hectares |
| Subcatchments | 6 (residential, commercial, parking, park) |
| Annual Rainfall | ~410 mm (Calgary average) |
| Report Timestep | 5 minutes |

## 📈 Output

```
CAPTURE CURVE RESULTS
======================================================================
Capture %       Q_wq (CMS)           Q_wq (L/s)      
----------------------------------------------------------------------
50%             0.001234             1.23
75%             0.003456             3.46
80%             0.004567             4.57
90%             0.007890             7.89 <<<
95%             0.012345             12.35
======================================================================

>>> WATER QUALITY FLOW RATE (90%): 0.007890 CMS (7.89 L/s) <<<
```

## 🔧 Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run full pipeline
python main.py

# Or run steps individually:
python generate_calgary_rainfall.py  # Generate rainfall
python run_simulation.py             # Run SWMM
python ogs_sizing.py                 # Calculate Q_wq
```

## 📁 Files

| File | Description |
|------|-------------|
| `main.py` | Main entry point - runs full pipeline |
| `calgary_model.inp` | SWMM model definition |
| `generate_calgary_rainfall.py` | Creates synthetic rainfall data |
| `ogs_sizing.py` | Q_wq calculation logic |
| `run_simulation.py` | SWMM simulation runner |

## ⏱️ Performance Benchmarks

Target benchmarks on Railway:

| Operation | Expected Time |
|-----------|---------------|
| SWMM Simulation (30 years) | 1-5 minutes |
| File Read | < 1 second |
| Q_wq Processing | < 0.1 seconds |

## 📚 References

- [EPA SWMM](https://www.epa.gov/water-research/storm-water-management-model-swmm)
- [swmm-toolkit](https://pypi.org/project/swmm-toolkit/)
- [Environment Canada Climate Normals](https://climate.weather.gc.ca/climate_normals/)
- Calgary International Airport (YYC) Station Data

## 📄 License

MIT

