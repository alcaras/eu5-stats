#!/usr/bin/env python3
"""
EU5 Save File Comprehensive Report Generator
Outputs all reports in order for easy copy-paste.
"""

import re
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any
from datetime import datetime

# Script directory for relative paths
SCRIPT_DIR = Path(__file__).parent.resolve()


def load_human_countries() -> dict[str, str]:
    """Load human-controlled countries from HUMANS.txt"""
    humans_file = SCRIPT_DIR / "HUMANS.txt"
    countries = {}
    if humans_file.exists():
        with open(humans_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    # Tag only, use tag as name
                    countries[line] = line
    return countries


# Load player countries from config file
PLAYER_COUNTRIES = load_human_countries()

RELIGION_NAMES = {
    12: 'Catholic', 13: 'Hussite', 18: 'Orthodox',
    22: 'Karaism', 158: 'Namandu', 285: 'Shia', 286: 'Sunni',
}


@dataclass
class CountryStats:
    tag: str
    name: str = ""

    # Ruler
    ruler_id: int = 0
    ruler_name: str = ""
    ruler_adm: int = 0
    ruler_dip: int = 0
    ruler_mil: int = 0
    ruler_traits: list = field(default_factory=list)

    # Rank
    great_power_rank: int = 0

    # Economy
    gold: float = 0.0
    monthly_income: float = 0.0
    current_tax_base: float = 0.0
    loan_capacity: float = 0.0
    total_debt: float = 0.0

    # Population (in thousands)
    population: float = 0.0
    num_provinces: int = 0

    # Military
    manpower: float = 0.0
    max_manpower: float = 0.0
    monthly_manpower: float = 0.0
    sailors: float = 0.0
    max_sailors: float = 0.0
    army_tradition: float = 0.0
    navy_tradition: float = 0.0
    num_units: int = 0
    num_subunits: int = 0

    # Production
    total_produced: float = 0.0
    produced_goods: dict = field(default_factory=dict)

    # Tech
    num_researched_advances: int = 0
    institutions: list = field(default_factory=list)

    # Government
    government_type: str = ""
    employment_system: str = ""
    stability: float = 0.0
    prestige: float = 0.0
    religion_id: int = 0
    religion_name: str = ""

    # Privileges & Reforms
    num_privileges: int = 0
    privileges: list = field(default_factory=list)
    num_reforms: int = 0
    reforms: list = field(default_factory=list)
    laws: dict = field(default_factory=dict)

    # Values
    values: dict = field(default_factory=dict)

    # Control (0-100 scale, represents government's administrative reach)
    average_control: float = 0.0

    # Time series
    historical_population: list = field(default_factory=list)
    historical_tax_base: list = field(default_factory=list)


def extract_value(text: str, pattern: str, cast=str, default=None):
    match = re.search(pattern, text)
    if match:
        try:
            return cast(match.group(1))
        except:
            return default
    return default


def extract_block(text: str, key: str) -> str:
    pattern = rf'{key}=\{{'
    match = re.search(pattern, text)
    if not match:
        return ""
    start = match.end()
    depth = 1
    pos = start
    while pos < len(text) and depth > 0:
        if text[pos] == '{':
            depth += 1
        elif text[pos] == '}':
            depth -= 1
        pos += 1
    return text[start:pos-1]


def extract_dict(text: str, key: str) -> dict:
    block = extract_block(text, key)
    if not block:
        return {}
    result = {}
    for match in re.finditer(r'(\w+)=([^\s{}\n]+|"[^"]*")', block):
        k = match.group(1)
        v = match.group(2).strip('"')
        try:
            if '.' in v:
                result[k] = float(v)
            else:
                result[k] = int(v)
        except ValueError:
            result[k] = True if v == 'yes' else (False if v == 'no' else v)
    return result


def extract_list_values(text: str, key: str) -> list:
    pattern = rf'{key}=\{{([^}}]+)\}}'
    match = re.search(pattern, text)
    if match:
        return [float(v) for v in match.group(1).split() if v.replace('.','').replace('-','').isdigit()]
    return []


def extract_nested_objects(text: str, key: str) -> list:
    block = extract_block(text, key)
    return re.findall(r'object=(\w+)', block) if block else []


def find_character(filepath: str, char_id: int) -> dict | None:
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        in_char_db = False
        in_database = False
        collecting = False
        depth = 0
        lines = []

        for line in f:
            if not in_char_db:
                if 'character_db={' in line:
                    in_char_db = True
                continue
            if not in_database:
                if 'database={' in line:
                    in_database = True
                continue
            if not collecting:
                if line.strip().startswith(f'{char_id}={{'):
                    collecting = True
                    lines.append(line)
                    depth = line.count('{') - line.count('}')
            else:
                lines.append(line)
                depth += line.count('{') - line.count('}')
                if depth <= 0:
                    break

        if lines:
            text = ''.join(lines)
            # Extract traits
            traits_match = re.search(r'traits=\{\s*([^}]+)\}', text)
            traits = traits_match.group(1).split() if traits_match else []
            return {
                'adm': extract_value(text, r'adm=(\d+)', int, 0),
                'dip': extract_value(text, r'dip=(\d+)', int, 0),
                'mil': extract_value(text, r'mil=(\d+)', int, 0),
                'first_name': extract_value(text, r'first_name="([^"]+)"', str, ""),
                'traits': traits,
            }
    return None


def find_country_in_file(filepath: str, tag: str) -> str | None:
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        in_countries = False
        in_database = False
        collecting = False
        depth = 0
        lines = []
        recent_lines = []  # Keep track of recent lines to find block start

        for line in f:
            if not in_countries:
                if line.strip().startswith('countries='):
                    in_countries = True
                continue
            if not in_database:
                if line.strip().startswith('database='):
                    in_database = True
                continue
            if not collecting:
                # Keep last 10 lines to find the block start (country_name={ name="X" } adds extra lines)
                recent_lines.append(line)
                if len(recent_lines) > 10:
                    recent_lines.pop(0)

                # Match: country_name="TAG" or flag=TAG
                if f'country_name="{tag}"' in line or f'flag={tag}' in line:
                    collecting = True
                    # Get indent level of country_name line (country block start is one level less)
                    name_indent = len(line) - len(line.lstrip('\t'))
                    target_indent = name_indent - 1  # Country block starts one tab level up
                    # Find the line with ID={ pattern at correct indent level
                    for i in range(len(recent_lines) - 1, -1, -1):  # Search backward
                        prev = recent_lines[i]
                        prev_indent = len(prev) - len(prev.lstrip('\t'))
                        stripped = prev.strip()
                        if prev_indent == target_indent and '={' in stripped and stripped[0].isdigit():
                            lines.extend(recent_lines[i:])
                            depth = sum(l.count('{') - l.count('}') for l in lines)
                            break
                    else:
                        # Fallback: use all recent lines
                        lines.extend(recent_lines)
                        depth = sum(l.count('{') - l.count('}') for l in lines)
            else:
                lines.append(line)
                depth += line.count('{') - line.count('}')
                if depth <= 0:
                    break

        return ''.join(lines) if lines else None


def parse_country(text: str, tag: str) -> CountryStats:
    stats = CountryStats(tag=tag, name=PLAYER_COUNTRIES.get(tag, tag))

    # Ruler
    govt_block = extract_block(text, 'government')
    stats.ruler_id = extract_value(govt_block, r'ruler=(\d+)', int, 0)

    # Rank - use great_power_rank field (not score_place which is different)
    stats.great_power_rank = extract_value(text, r'great_power_rank=(\d+)', int, 0)

    # Currency
    currency = extract_block(text, 'currency_data')
    stats.gold = extract_value(currency, r'gold=([\d.-]+)', float, 0.0)
    stats.stability = extract_value(currency, r'stability=([\d.-]+)', float, 0.0)
    stats.prestige = extract_value(currency, r'prestige=([\d.-]+)', float, 0.0)
    stats.army_tradition = extract_value(currency, r'army_tradition=([\d.]+)', float, 0.0)
    stats.navy_tradition = extract_value(currency, r'navy_tradition=([\d.]+)', float, 0.0)
    stats.manpower = extract_value(currency, r'manpower=([\d.]+)', float, 0.0)
    stats.sailors = extract_value(currency, r'sailors=([\d.]+)', float, 0.0)

    # Economy
    stats.monthly_income = extract_value(text, r'estimated_monthly_income=([\d.]+)', float, 0.0)
    stats.current_tax_base = extract_value(text, r'current_tax_base=([\d.]+)', float, 0.0)
    economy = extract_block(text, 'economy')
    stats.loan_capacity = extract_value(economy, r'loan_capacity=([\d.]+)', float, 0.0)

    # Population
    stats.population = extract_value(text, r'last_months_population=([\d.]+)', float, 0.0)
    stats.max_manpower = extract_value(text, r'max_manpower=([\d.]+)', float, 0.0)
    stats.monthly_manpower = extract_value(text, r'monthly_manpower=([\d.]+)', float, 0.0)
    stats.max_sailors = extract_value(text, r'max_sailors=([\d.]+)', float, 0.0)

    # Provinces
    prov_match = re.search(r'provinces=\{([^}]+)\}', text)
    stats.num_provinces = len(prov_match.group(1).split()) if prov_match else 0

    # Military
    units_match = re.search(r'\bunits=\{([^}]+)\}', text)
    stats.num_units = len(units_match.group(1).split()) if units_match else 0
    subunits_match = re.search(r'owned_subunits=\{([^}]+)\}', text)
    stats.num_subunits = len(subunits_match.group(1).split()) if subunits_match else 0

    # Production
    stats.total_produced = extract_value(text, r'total_produced=([\d.]+)', float, 0.0)
    stats.produced_goods = extract_dict(text, 'last_month_produced')

    # Tech
    advances = extract_dict(text, 'researched_advances')
    stats.num_researched_advances = sum(1 for v in advances.values() if v == True)
    stats.institutions = [k for k, v in extract_dict(text, 'institutions').items() if v == True]

    # Government
    stats.government_type = extract_value(govt_block, r'type=(\w+)', str, "")
    stats.employment_system = extract_value(text, r'employment_system=(\w+)', str, "")
    stats.religion_id = extract_value(text, r'primary_religion=(\d+)', int, 0)
    stats.religion_name = RELIGION_NAMES.get(stats.religion_id, f"id_{stats.religion_id}")

    # Privileges & Reforms
    stats.privileges = extract_nested_objects(govt_block, 'implemented_privileges')
    stats.num_privileges = len(stats.privileges)
    stats.reforms = extract_nested_objects(govt_block, 'implemented_reforms')
    stats.num_reforms = len(stats.reforms)

    # Laws
    laws_block = extract_block(govt_block, 'implemented_laws')
    for match in re.finditer(r'(\w+)=\{[^}]*object=(\w+)', laws_block):
        stats.laws[match.group(1)] = match.group(2)

    # Values
    stats.values = extract_dict(text, 'societal_values')

    # Control - extract from variables section
    # Pattern: flag=average_control_in_home_region_target_variable followed by identity=XXXXX
    control_match = re.search(
        r'flag=average_control_in_home_region_target_variable[\s\n\t]*data=\{[\s\n\t]*type=value[\s\n\t]*identity=(\d+)',
        text
    )
    if control_match:
        stats.average_control = int(control_match.group(1)) / 1000  # Convert from internal format

    # Time series
    stats.historical_population = extract_list_values(text, 'historical_population')
    stats.historical_tax_base = extract_list_values(text, 'historical_tax_base')

    return stats


def get_save_date(filepath: str) -> str:
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        for i, line in enumerate(f):
            if 'date=' in line and '.' in line:
                match = re.search(r'date=(\d+\.\d+\.\d+)', line)
                if match:
                    return match.group(1)
            if i > 100:
                break
    return "Unknown"


def fmt_pop(val: float) -> str:
    """Population in millions."""
    return f"{val/1000:.2f}M" if val >= 100 else f"{val:.1f}K"


def fmt_num(val: float) -> str:
    if val >= 10000:
        return f"{val/1000:.1f}K"
    elif val >= 1000:
        return f"{val:,.0f}"
    return f"{val:.1f}"


def generate_summary_report(countries: list[CountryStats], save_date: str) -> str:
    """Generate the summary report (Discord-friendly, narrow format)."""
    lines = []
    W = 55  # Max line width for Discord

    lines.append("=" * W)
    lines.append("EU5 MP SESSION REPORT")
    lines.append("=" * W)
    lines.append(f"Save: {save_date} | Players: {len(countries)}")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")

    by_gp = sorted(countries, key=lambda c: c.great_power_rank if c.great_power_rank > 0 else 9999)

    # === GREAT POWER RANKINGS ===
    lines.append("=" * W)
    lines.append("GREAT POWER RANKINGS")
    lines.append("-" * W)
    lines.append(f"{'#':<3}{'Tag':<5}{'GP':<4}{'Pop':<8}{'Income':<8}{'TaxBase':<8}")
    lines.append("-" * W)
    for i, c in enumerate(by_gp, 1):
        lines.append(f"{i:<3}{c.tag:<5}{c.great_power_rank:<4}{fmt_pop(c.population):<8}{fmt_num(c.monthly_income):<8}{fmt_num(c.current_tax_base):<8}")
    lines.append("")

    # === RULER STATS ===
    lines.append("=" * W)
    lines.append("RULERS (sorted by total stats)")
    lines.append("-" * W)
    lines.append(f"{'Tag':<5}{'A':<4}{'D':<4}{'M':<4}{'Tot':<5}{'Name':<12}{'Traits':<20}")
    lines.append("-" * W)

    by_ruler = sorted(countries, key=lambda c: c.ruler_adm + c.ruler_dip + c.ruler_mil, reverse=True)
    for c in by_ruler:
        total = c.ruler_adm + c.ruler_dip + c.ruler_mil
        traits_str = ", ".join(c.ruler_traits[:2]) if c.ruler_traits else ""
        if len(c.ruler_traits) > 2:
            traits_str += "..."
        lines.append(f"{c.tag:<5}{c.ruler_adm:<4}{c.ruler_dip:<4}{c.ruler_mil:<4}{total:<5}{c.ruler_name[:11]:<12}{traits_str[:20]}")
    lines.append("")

    # === ECONOMY ===
    lines.append("=" * W)
    lines.append("ECONOMY (by income)")
    lines.append("-" * W)
    lines.append(f"{'Tag':<5}{'Income':<9}{'Treasury':<10}{'TaxBase':<9}{'LoanCap':<9}")
    lines.append("-" * W)

    by_income = sorted(countries, key=lambda c: c.monthly_income, reverse=True)
    for c in by_income:
        lines.append(f"{c.tag:<5}{fmt_num(c.monthly_income):<9}{fmt_num(c.gold):<10}{fmt_num(c.current_tax_base):<9}{fmt_num(c.loan_capacity):<9}")
    lines.append("")

    # === POPULATION ===
    lines.append("=" * W)
    lines.append("POPULATION")
    lines.append("-" * W)
    lines.append(f"{'Tag':<5}{'Pop':<10}{'Provs':<7}{'Pop/Prov':<10}")
    lines.append("-" * W)

    by_pop = sorted(countries, key=lambda c: c.population, reverse=True)
    for c in by_pop:
        pop_per_prov = c.population / c.num_provinces if c.num_provinces > 0 else 0
        lines.append(f"{c.tag:<5}{fmt_pop(c.population):<10}{c.num_provinces:<7}{fmt_pop(pop_per_prov):<10}")
    lines.append("")

    # === MILITARY ===
    lines.append("=" * W)
    lines.append("MILITARY (by regiments)")
    lines.append("-" * W)
    lines.append(f"{'Tag':<5}{'Regs':<6}{'MP':<7}{'MaxMP':<7}{'ArmyT':<7}{'NavyT':<7}")
    lines.append("-" * W)

    by_mil = sorted(countries, key=lambda c: c.num_subunits, reverse=True)
    for c in by_mil:
        lines.append(f"{c.tag:<5}{c.num_subunits:<6}{c.manpower:<7.1f}{c.max_manpower:<7.1f}{c.army_tradition:<7.1f}{c.navy_tradition:<7.1f}")
    lines.append("")

    # === PRODUCTION ===
    lines.append("=" * W)
    lines.append("PRODUCTION")
    lines.append("-" * W)
    lines.append(f"{'Tag':<5}{'Total':<8}{'Top 3 Goods':<40}")
    lines.append("-" * W)

    by_prod = sorted(countries, key=lambda c: c.total_produced, reverse=True)
    for c in by_prod:
        top_goods = sorted(c.produced_goods.items(), key=lambda x: x[1], reverse=True)[:3]
        goods_str = ", ".join(f"{g[0]}:{g[1]:.0f}" for g in top_goods)
        lines.append(f"{c.tag:<5}{fmt_num(c.total_produced):<8}{goods_str[:40]}")
    lines.append("")

    # === TECHNOLOGY ===
    lines.append("=" * W)
    lines.append("TECHNOLOGY")
    lines.append("-" * W)

    # Find baseline institutions (what most countries have)
    all_institutions = set()
    for c in countries:
        all_institutions.update(c.institutions)

    # Count how many countries have each institution
    inst_counts = {inst: sum(1 for c in countries if inst in c.institutions) for inst in all_institutions}
    # Baseline = institutions that majority have
    baseline = {inst for inst, count in inst_counts.items() if count > len(countries) // 2}

    lines.append(f"{'Tag':<5}{'Advs':<6}{'Inst':<5}{'Missing/Extra':<35}")
    lines.append("-" * W)

    by_tech = sorted(countries, key=lambda c: c.num_researched_advances, reverse=True)
    for c in by_tech:
        c_inst = set(c.institutions)
        missing = baseline - c_inst
        extra = c_inst - baseline

        if missing:
            inst_str = ", ".join(f"-{i}" for i in sorted(missing))
        elif extra:
            inst_str = ", ".join(f"+{i}" for i in sorted(extra))
        else:
            inst_str = "(complete)"

        lines.append(f"{c.tag:<5}{c.num_researched_advances:<6}{len(c.institutions):<5}{inst_str[:35]}")
    lines.append("")

    # === GOVERNMENT ===
    lines.append("=" * W)
    lines.append("GOVERNMENT & RELIGION")
    lines.append("-" * W)
    lines.append(f"{'Tag':<5}{'Type':<10}{'Religion':<10}{'Stab':<7}{'Prest':<7}")
    lines.append("-" * W)

    for c in by_gp:
        lines.append(f"{c.tag:<5}{c.government_type[:9]:<10}{c.religion_name[:9]:<10}{c.stability:<7.1f}{c.prestige:<7.1f}")
    lines.append("")

    # === SOCIETAL VALUES - Compact ===
    lines.append("=" * W)
    lines.append("VALUES (cent/serf/arist/trad/spirit)")
    lines.append("-" * W)
    value_keys_1 = ['centralization_vs_decentralization', 'serfdom_vs_free_subjects',
                    'aristocracy_vs_plutocracy', 'traditionalist_vs_innovative', 'spiritualist_vs_humanist']
    for c in by_gp:
        vals = [c.values.get(k, -999) for k in value_keys_1]
        val_strs = [f"{v:>4.0f}" if v != -999 else "   -" for v in vals]
        lines.append(f"{c.tag:<5} {' '.join(val_strs)}")
    lines.append("")

    lines.append("VALUES (capital/indiv/qual/offen/land/bell)")
    lines.append("-" * W)
    value_keys_2 = ['capital_economy_vs_traditional_economy', 'individualism_vs_communalism',
                    'quality_vs_quantity', 'offensive_vs_defensive', 'land_vs_naval', 'belligerent_vs_conciliatory']
    for c in by_gp:
        vals = [c.values.get(k, -999) for k in value_keys_2]
        val_strs = [f"{v:>4.0f}" if v != -999 else "   -" for v in vals]
        lines.append(f"{c.tag:<5} {' '.join(val_strs)}")
    lines.append("")

    lines.append("=" * W)
    lines.append("END OF SUMMARY")
    lines.append("=" * W)

    return "\n".join(lines)


def generate_detailed_profiles(countries: list[CountryStats], save_date: str) -> str:
    """Generate detailed country profiles (separate file)."""
    lines = []

    lines.append("=" * 60)
    lines.append("DETAILED COUNTRY PROFILES")
    lines.append(f"Save: {save_date}")
    lines.append("=" * 60)

    by_gp = sorted(countries, key=lambda c: c.great_power_rank if c.great_power_rank > 0 else 9999)

    for c in by_gp:
        lines.append("")
        lines.append(f"{'='*60}")
        lines.append(f"{c.tag} ({c.name}) - GP #{c.great_power_rank}")
        lines.append(f"{'='*60}")

        # Ruler
        ruler_info = f"Ruler: {c.ruler_name} ({c.ruler_adm}/{c.ruler_dip}/{c.ruler_mil})"
        lines.append(ruler_info)
        if c.ruler_traits:
            lines.append(f"Traits: {', '.join(c.ruler_traits)}")

        lines.append("")
        lines.append(f"Government: {c.government_type} | Religion: {c.religion_name}")
        lines.append(f"Stability: {c.stability:.1f} | Prestige: {c.prestige:.1f}")
        if c.average_control > 0:
            lines.append(f"Average Control: {c.average_control:.1f}%")

        lines.append("")
        lines.append(f"Population: {fmt_pop(c.population)} across {c.num_provinces} provinces")
        lines.append(f"Income: {fmt_num(c.monthly_income)} | Treasury: {fmt_num(c.gold)}")
        lines.append(f"Tax Base: {fmt_num(c.current_tax_base)} | Loan Cap: {fmt_num(c.loan_capacity)}")

        lines.append("")
        lines.append(f"Manpower: {c.manpower:.1f}/{c.max_manpower:.1f}")
        lines.append(f"Regiments: {c.num_subunits}")
        lines.append(f"Army Tradition: {c.army_tradition:.1f} | Navy: {c.navy_tradition:.1f}")

        lines.append("")
        lines.append(f"Tech: {c.num_researched_advances} advances")
        lines.append(f"Institutions ({len(c.institutions)}): {', '.join(reversed(c.institutions))}")

        if c.reforms:
            lines.append("")
            lines.append(f"Reforms: {', '.join(c.reforms)}")

        if c.privileges:
            lines.append("")
            lines.append(f"Privileges ({c.num_privileges} total):")
            # Organize by estate
            estates = {
                'Nobles': [], 'Clergy': [], 'Burghers': [],
                'Peasants': [], 'Dhimmi': [], 'Tribes': [],
                'Cossacks': [], 'General': []
            }
            for p in c.privileges:
                if p.startswith(('nobles_', 'noble_', 'auxilium', 'primacy_of_nobility')):
                    estates['Nobles'].append(p)
                elif p.startswith(('clergy_', 'clerical_')):
                    estates['Clergy'].append(p)
                elif p.startswith(('burghers_', 'burgher_', 'formal_guilds', 'free_city', 'polish_merchant')):
                    estates['Burghers'].append(p)
                elif p.startswith(('peasants_', 'peasant_')):
                    estates['Peasants'].append(p)
                elif p.startswith(('dhimmi_', 'jizya')):
                    estates['Dhimmi'].append(p)
                elif p.startswith(('tribes_', 'tribal_')):
                    estates['Tribes'].append(p)
                elif p.startswith(('cossacks_', 'cossack_')):
                    estates['Cossacks'].append(p)
                else:
                    estates['General'].append(p)

            for estate, privs in estates.items():
                if privs:
                    lines.append(f"  {estate}: {', '.join(privs)}")

        # Societal values
        lines.append("")
        lines.append("Societal Values:")
        value_names = {
            'centralization_vs_decentralization': 'Centralization',
            'serfdom_vs_free_subjects': 'Serfdom',
            'aristocracy_vs_plutocracy': 'Aristocracy',
            'traditionalist_vs_innovative': 'Traditional',
            'spiritualist_vs_humanist': 'Spiritualist',
            'capital_economy_vs_traditional_economy': 'Capital Econ',
            'individualism_vs_communalism': 'Individualism',
            'quality_vs_quantity': 'Quality',
            'offensive_vs_defensive': 'Offensive',
            'land_vs_naval': 'Land Focus',
            'belligerent_vs_conciliatory': 'Belligerent',
        }
        for key, name in value_names.items():
            val = c.values.get(key, None)
            if val is not None:
                lines.append(f"  {name}: {val:.0f}")

    lines.append("")
    lines.append("=" * 60)
    lines.append("END OF DETAILED PROFILES")
    lines.append("=" * 60)

    return "\n".join(lines)


def generate_laws_report(countries: list[CountryStats], save_date: str) -> str:
    """Generate a laws comparison report grouped by law category."""
    lines = []
    W = 55

    # Define law categories with display names
    LAW_CATEGORIES = {
        'feudal_de_jure_law': 'Succession Law',
        'medieval_levy_law': 'Military Levy',
        'royal_court_customs_law': 'Court Customs',
        'censorship': 'Censorship',
        'education_masses_law': 'Education',
        'administrative_system': 'Administration',
        'cultural_traditions_law': 'Cultural Traditions',
        'marriage_law': 'Marriage Law',
        'heir_religion_law': 'Heir Religion',
        'mining_law': 'Mining Rights',
        'immigration_law': 'Immigration',
        'legal_code_law': 'Legal Code',
        'maritime_law': 'Maritime Policy',
        'piracy_law': 'Piracy Policy',
        'distribution_of_power_law': 'Distribution of Power',
    }

    # Collect all law categories from all countries
    all_categories = set()
    for c in countries:
        all_categories.update(c.laws.keys())

    lines.append("=" * W)
    lines.append("EU5 LAWS COMPARISON")
    lines.append("=" * W)
    lines.append(f"Save: {save_date} | Players: {len(countries)}")
    lines.append("")

    # Sort countries by GP rank
    by_gp = sorted(countries, key=lambda c: c.great_power_rank if c.great_power_rank > 0 else 9999)
    tags = [c.tag for c in by_gp]

    # For each law category, show which law each country has
    for category in sorted(all_categories):
        display_name = LAW_CATEGORIES.get(category, category.replace('_', ' ').title())

        lines.append("-" * W)
        lines.append(f"{display_name}")
        lines.append("-" * W)

        # Group countries by their law choice
        law_to_countries = {}
        for c in by_gp:
            law_choice = c.laws.get(category, None)
            if law_choice:
                if law_choice not in law_to_countries:
                    law_to_countries[law_choice] = []
                law_to_countries[law_choice].append(c.tag)

        # Display each law option and which countries have it
        for law_choice, ctags in sorted(law_to_countries.items(), key=lambda x: -len(x[1])):
            # Clean up the law name for display
            law_display = law_choice.replace('_', ' ').replace(' policy', '').title()
            lines.append(f"  {law_display}: {', '.join(ctags)}")

        lines.append("")

    # Summary table: laws per country
    lines.append("=" * W)
    lines.append("LAWS BY COUNTRY")
    lines.append("-" * W)
    for c in by_gp:
        lines.append(f"\n{c.tag} ({len(c.laws)} laws):")
        for cat, law in sorted(c.laws.items()):
            cat_display = LAW_CATEGORIES.get(cat, cat.replace('_', ' '))
            law_display = law.replace('_', ' ').title()
            lines.append(f"  {cat_display}: {law_display}")

    lines.append("")
    lines.append("=" * W)
    lines.append("END OF LAWS REPORT")
    lines.append("=" * W)

    return "\n".join(lines)


def classify_privilege(priv: str) -> str:
    """Classify a privilege into an estate category."""
    if priv.startswith(('nobles_', 'noble_', 'auxilium', 'primacy_of_nobility')):
        return 'Nobles'
    elif priv.startswith(('clergy_', 'clerical_', 'embellish_great_works')):
        return 'Clergy'
    elif priv.startswith(('burghers_', 'burgher_', 'formal_guilds', 'free_city', 'polish_merchant', 'market_fairs', 'treasury_rights', 'commercial_', 'control_over_the_coinage')):
        return 'Burghers'
    elif priv.startswith(('peasants_', 'peasant_', 'land_owning_farmers')):
        return 'Peasants'
    elif priv.startswith(('dhimmi_', 'jizya')):
        return 'Dhimmi'
    elif priv.startswith(('tribes_', 'tribal_', 'expansionist_zealotry')):
        return 'Tribes'
    elif priv.startswith(('cossacks_', 'cossack_')):
        return 'Cossacks'
    else:
        return 'General'


def generate_privileges_report(countries: list[CountryStats], save_date: str) -> str:
    """Generate a privileges comparison report grouped by estate."""
    lines = []
    W = 55

    lines.append("=" * W)
    lines.append("EU5 PRIVILEGES COMPARISON")
    lines.append("=" * W)
    lines.append(f"Save: {save_date} | Players: {len(countries)}")
    lines.append("")

    # Sort countries by GP rank
    by_gp = sorted(countries, key=lambda c: c.great_power_rank if c.great_power_rank > 0 else 9999)

    # Collect all privileges by estate
    estate_privs = {}  # estate -> {priv -> [countries]}
    for c in by_gp:
        for priv in c.privileges:
            estate = classify_privilege(priv)
            if estate not in estate_privs:
                estate_privs[estate] = {}
            if priv not in estate_privs[estate]:
                estate_privs[estate][priv] = []
            estate_privs[estate][priv].append(c.tag)

    # Define estate order
    estate_order = ['Nobles', 'Clergy', 'Burghers', 'Peasants', 'Dhimmi', 'Tribes', 'Cossacks', 'General']

    # For each estate, show privileges and which countries have them
    for estate in estate_order:
        if estate not in estate_privs:
            continue

        privs = estate_privs[estate]
        lines.append("=" * W)
        lines.append(f"{estate.upper()} PRIVILEGES ({len(privs)} unique)")
        lines.append("=" * W)

        # Sort by number of countries (most common first)
        for priv, ctags in sorted(privs.items(), key=lambda x: (-len(x[1]), x[0])):
            priv_display = priv.replace('_', ' ').title()
            if len(ctags) == len(by_gp):
                # All countries have it
                lines.append(f"  {priv_display}: ALL")
            else:
                lines.append(f"  {priv_display}: {', '.join(ctags)}")

        lines.append("")

    # Summary: privilege count by country
    lines.append("=" * W)
    lines.append("PRIVILEGES BY COUNTRY")
    lines.append("-" * W)

    for c in by_gp:
        # Count by estate
        estate_counts = {}
        for priv in c.privileges:
            estate = classify_privilege(priv)
            estate_counts[estate] = estate_counts.get(estate, 0) + 1

        counts_str = ", ".join(f"{e}:{n}" for e, n in sorted(estate_counts.items()) if n > 0)
        lines.append(f"{c.tag}: {c.num_privileges} total ({counts_str})")

    lines.append("")

    # Unique privileges (only one country has)
    lines.append("=" * W)
    lines.append("UNIQUE PRIVILEGES (only one country)")
    lines.append("-" * W)

    unique_found = False
    for estate in estate_order:
        if estate not in estate_privs:
            continue
        for priv, ctags in sorted(estate_privs[estate].items()):
            if len(ctags) == 1:
                priv_display = priv.replace('_', ' ').title()
                lines.append(f"  {ctags[0]}: {priv_display}")
                unique_found = True

    if not unique_found:
        lines.append("  (none)")

    lines.append("")
    lines.append("=" * W)
    lines.append("END OF PRIVILEGES REPORT")
    lines.append("=" * W)

    return "\n".join(lines)


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Generate EU5 multiplayer session report')
    parser.add_argument('-o', '--output', help='Output directory (default: reports/)')
    parser.add_argument('--no-timestamp', action='store_true', help='Don\'t create timestamped subfolder')
    args = parser.parse_args()

    # Find save file
    save_dir = SCRIPT_DIR / "save"
    save_files = list(save_dir.glob("*.eu5"))

    if not save_files:
        print("No .eu5 save files found")
        sys.exit(1)

    save_file = save_files[0]
    save_date = get_save_date(str(save_file))

    # Determine output directory
    if args.output:
        report_dir = Path(args.output)
    else:
        report_dir = SCRIPT_DIR / "reports"

    # Create timestamped subfolder unless disabled
    if not args.no_timestamp:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_date_clean = save_date.replace('.', '_')
        report_dir = report_dir / f"{save_date_clean}_{timestamp}"

    report_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading: {save_file.name}", file=sys.stderr)
    print(f"Output: {report_dir}", file=sys.stderr)

    countries = []
    for tag, name in PLAYER_COUNTRIES.items():
        print(f"  Parsing {tag}...", file=sys.stderr, end=" ", flush=True)
        country_text = find_country_in_file(str(save_file), tag)

        if country_text:
            stats = parse_country(country_text, tag)

            # Get ruler stats
            if stats.ruler_id:
                ruler = find_character(str(save_file), stats.ruler_id)
                if ruler:
                    stats.ruler_adm = ruler['adm']
                    stats.ruler_dip = ruler['dip']
                    stats.ruler_mil = ruler['mil']
                    stats.ruler_name = ruler['first_name'].replace('name_', '').title()
                    stats.ruler_traits = ruler.get('traits', [])

            countries.append(stats)
            print("OK", file=sys.stderr)
        else:
            print("NOT FOUND", file=sys.stderr)

    if countries:
        # Write summary report (Discord-friendly)
        summary_file = report_dir / "session_summary.txt"
        with open(summary_file, 'w') as f:
            f.write(generate_summary_report(countries, save_date))
        print(f"Summary saved to: {summary_file}", file=sys.stderr)

        # Write detailed profiles (separate file for upload)
        details_file = report_dir / "country_details.txt"
        with open(details_file, 'w') as f:
            f.write(generate_detailed_profiles(countries, save_date))
        print(f"Details saved to: {details_file}", file=sys.stderr)

        # Write laws comparison report
        laws_file = report_dir / "laws_comparison.txt"
        with open(laws_file, 'w') as f:
            f.write(generate_laws_report(countries, save_date))
        print(f"Laws saved to: {laws_file}", file=sys.stderr)

        # Write privileges comparison report
        privs_file = report_dir / "privileges_comparison.txt"
        with open(privs_file, 'w') as f:
            f.write(generate_privileges_report(countries, save_date))
        print(f"Privileges saved to: {privs_file}", file=sys.stderr)


if __name__ == '__main__':
    main()
