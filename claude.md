# EU5 Multiplayer Session Stats Tool

Tool for analyzing Europa Universalis 5 multiplayer save files and generating comparison reports for player-controlled countries.

## Quick Start

```bash
./run_reports.sh
```

This generates all reports and charts in a timestamped folder under `reports/`.

## Save File Setup

1. Use EU5's "melt" feature or Rakaly to convert binary save to text
2. Place the melted `.eu5` file in the `save/` folder
3. Run `./run_reports.sh`

## Player Countries

Edit `PLAYER_COUNTRIES` dict in `generate_report.py` and `compare_players_v2.py`:

```python
PLAYER_COUNTRIES = {
    'GBR': 'Great Britain',
    'POL': 'Poland',
    'FRA': 'France',
    # ... etc
}
```

Note: Use the country tag from the save file. For formed nations, check `flag=TAG` not `country_name`.

## Output Files

### Text Reports
- `session_summary.txt` - Discord-friendly summary (55 char width), GP rankings, rulers, economy, military, tech, government, societal values
- `country_details.txt` - Detailed profiles for each country with privileges by estate, reforms, all stats
- `laws_comparison.txt` - Laws grouped by category showing which countries have which laws
- `privileges_comparison.txt` - Privileges grouped by estate (Nobles, Clergy, Burghers, Peasants, Dhimmi, Tribes, General), shows which countries have each privilege, unique privileges per country

### Charts (numbered for Discord)
- `01_population_history.png` - Population over time (thick lines with labels)
- `02_taxbase_history.png` - Tax base over time
- `03_treemap_population.png` - Population treemap
- `04_treemap_taxbase.png` - Tax base treemap
- `05_treemap_military.png` - Regiments treemap
- `06_treemap_manpower.png` - Manpower treemap

### Other
- `gp_rankings.txt` - Great Power rankings as text
- `tech_advances.txt` - Tech advances with unique institutions analysis
- `player_comparison.png` - Combined comparison chart

## Key Files

- `run_reports.sh` - Main entry point, runs everything
- `generate_report.py` - Text report generation (summary, details, laws, privileges)
- `compare_players_v2.py` - Chart generation and comparison tables

## Technical Notes

### PDX Save Format
- Nested `key=value` pairs with `{}` blocks
- Country data starts at ~line 2.2M in a 287MB file
- Countries identified by `country_name="TAG"` or `flag=TAG` for formed nations
- Indent-aware parsing needed (country block at 2 tabs, name at 3 tabs)

### Key Country Fields
- `great_power_rank` - GP ranking (not `score_place`)
- `last_months_population` - Population in thousands
- `estimated_monthly_income` - Monthly income
- `current_tax_base` - Tax base
- `historical_population` / `historical_tax_base` - Time series data
- `implemented_laws` - Laws with category and object (choice)
- `implemented_privileges` - Privileges list
- `societal_values` - Slider values like centralization, serfdom, etc.

### Ruler Data
- Ruler ID in `government.ruler`
- Actual stats in `character_db` section (search by ID)
- Fields: `adm`, `dip`, `mil`, `first_name`, `traits`

### Privilege Classification
Privileges are classified by estate based on prefix:
- Nobles: `nobles_`, `noble_`, `auxilium`, `primacy_of_nobility`
- Clergy: `clergy_`, `clerical_`, `embellish_great_works`
- Burghers: `burghers_`, `formal_guilds`, `market_fairs`, `treasury_rights`, `commercial_`, `control_over_the_coinage`
- Peasants: `peasants_`, `land_owning_farmers`
- Dhimmi: `dhimmi_`, `jizya`
- Tribes: `tribes_`, `tribal_`, `expansionist_zealotry`
- General: everything else

## TODO / Future Ideas
- Subjects/vassals population chart (need to research EU5 subject system)
- Control metric (calculated from province proximity, not stored directly)
- More treemaps or charts as needed
