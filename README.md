# EU5 Multiplayer Stats

Tool for analyzing Europa Universalis 5 multiplayer save files and generating comparison reports for human-controlled countries.

## Features

- Great Power rankings with key metrics
- Ruler stats comparison
- Economy breakdown (income, treasury, tax base)
- Military overview (regiments, manpower)
- Population charts over time
- Technology/institution tracking
- Government, religion, and societal values
- Laws and privileges comparison by category
- Treemaps for visual comparison

## Quick Start

1. **Get your save file**: Upload your save to [pdx.tools](https://pdx.tools) and download the melted version
2. **Place save file**: Put the `.eu5` file in the `save/` folder
3. **Configure players**: Edit `HUMANS.txt` with the country tags of human players (one per line)
4. **Run reports**: `./run_reports.sh`

Reports and charts are generated in a timestamped folder under `reports/`.

## Configuration

### HUMANS.txt

List the 3-letter country tags of human-controlled players, one per line:

```
GBR
POL
FRA
SWE
BOH
```

**Note**: For formed nations, use the tag from the save file (check `flag=TAG`), not the original country tag.

## Output Files

### Text Reports
- `session_summary.txt` - Discord-friendly summary (narrow format for easy copy-paste)
- `country_details.txt` - Detailed per-country profiles
- `laws_comparison.txt` - Laws grouped by category
- `privileges_comparison.txt` - Privileges grouped by estate

### Charts
- `01_population_history.png` - Population over time
- `02_taxbase_history.png` - Tax base over time
- `03_treemap_population.png` - Population treemap
- `04_treemap_taxbase.png` - Tax base treemap
- `05_treemap_military.png` - Regiments treemap
- `06_treemap_manpower.png` - Manpower treemap

### Other
- `gp_rankings.txt` - Great Power rankings
- `tech_advances.txt` - Technology and institutions
- `player_comparison.png` - Combined comparison chart

## Sample Output

See `reports/sample_output/` for example reports from a 10-player multiplayer session at 1433.

## Requirements

- Python 3.8+
- matplotlib
- squarify

Install dependencies:
```bash
pip install matplotlib squarify
```

## License

MIT
