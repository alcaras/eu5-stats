#!/usr/bin/env python3
"""
EU5 Save File Player Comparison Tool
Extracts and compares player-controlled countries from an EU5 melted save file.
"""

import re
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any


# Player countries with their tags
PLAYER_COUNTRIES = {
    'BRI': 'Britain',
    'POL': 'Poland',
    'FRA': 'France',
    'SWE': 'Sweden',
    'SKO': 'Sokoto',
    'BOH': 'Bohemia',
    'MLO': 'Milan',
    'SER': 'Serbia',
    'TUR': 'Ottoman',
    'IRE': 'Ireland',
}


@dataclass
class CountryStats:
    tag: str
    name: str = ""

    # Score
    score_place: int = 0
    score_adm: float = 0.0
    score_dip: float = 0.0
    score_mil: float = 0.0
    great_power_rank: int = 0

    # Economy
    gold: float = 0.0
    monthly_income: float = 0.0
    current_tax_base: float = 0.0
    loan_capacity: float = 0.0
    total_debt: float = 0.0

    # Population & Territory
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

    # Tech & Institutions
    institutions: list = field(default_factory=list)
    num_researched_advances: int = 0
    researched_advances: list = field(default_factory=list)

    # Government
    government_type: str = ""
    employment_system: str = ""
    stability: float = 0.0
    prestige: float = 0.0

    # Religion
    religion_id: int = 0
    religion_name: str = ""

    # Privileges & Reforms
    num_privileges: int = 0
    privileges: list = field(default_factory=list)
    num_reforms: int = 0
    reforms: list = field(default_factory=list)

    # Laws
    laws: dict = field(default_factory=dict)

    # Values (societal_values)
    values: dict = field(default_factory=dict)


# Religion ID to name mapping (extracted from religion_manager)
RELIGION_NAMES = {
    0: 'bon', 1: 'mahayana', 2: 'shinto', 3: 'theravada',
    5: 'confucianism', 6: 'taoism', 7: 'hinduism',
    8: 'bogomilism', 9: 'bosnian_church', 10: 'paulicianism', 11: 'catharism',
    12: 'catholic', 13: 'hussite', 14: 'lollardism', 15: 'miaphysite',
    16: 'nestorianism', 17: 'strigolniki', 18: 'orthodox', 19: 'waldensian',
    20: 'judaism', 21: 'samaritanism', 22: 'karaism', 23: 'jain',
    24: 'sikhism', 25: 'druzism',
    152: 'tengri', 153: 'tungusic_shamanism', 154: 'yukaghir_shamanism',
    155: 'yupik_shamanism', 156: 'dreamtime', 157: 'akinha_ekugu',
    158: 'namandu', 159: 'tunpa', 160: 'doi_wahire',
    280: 'ibadi', 281: 'ismaili', 282: 'yazidism', 283: 'zikri',
    284: 'ahmadiyya', 285: 'shia', 286: 'sunni',
}


def extract_value(text: str, pattern: str, cast=str, default=None):
    """Extract a value using regex pattern."""
    match = re.search(pattern, text)
    if match:
        try:
            return cast(match.group(1))
        except (ValueError, TypeError):
            return default
    return default


def extract_block(text: str, key: str) -> str:
    """Extract a block { } after a key."""
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


def extract_list(text: str, key: str) -> list:
    """Extract a list of values from a block."""
    block = extract_block(text, key)
    if not block:
        return []

    # Split on whitespace, filter empty
    items = block.split()
    return [item.strip() for item in items if item.strip()]


def extract_dict(text: str, key: str) -> dict:
    """Extract key=value pairs from a block."""
    block = extract_block(text, key)
    if not block:
        return {}

    result = {}
    # Match key=value patterns (handles both quoted and unquoted values)
    for match in re.finditer(r'(\w+)=([^\s{}\n]+|"[^"]*")', block):
        k = match.group(1)
        v = match.group(2).strip('"')
        try:
            if '.' in v:
                result[k] = float(v)
            else:
                result[k] = int(v)
        except ValueError:
            if v == 'yes':
                result[k] = True
            elif v == 'no':
                result[k] = False
            else:
                result[k] = v

    return result


def count_nested_objects(text: str, key: str) -> int:
    """Count objects in a block (objects are separated by { })."""
    block = extract_block(text, key)
    if not block:
        return 0

    # Count opening braces at depth 0 (top-level objects)
    count = 0
    depth = 0
    for char in block:
        if char == '{':
            if depth == 0:
                count += 1
            depth += 1
        elif char == '}':
            depth -= 1

    return count


def extract_nested_objects(text: str, key: str) -> list:
    """Extract the 'object' field from each nested item."""
    block = extract_block(text, key)
    if not block:
        return []

    objects = []
    for match in re.finditer(r'object=(\w+)', block):
        objects.append(match.group(1))

    return objects


def parse_country_block(text: str, tag: str) -> CountryStats:
    """Parse a country block and extract all relevant stats."""
    stats = CountryStats(tag=tag)
    stats.name = PLAYER_COUNTRIES.get(tag, tag)

    # Score
    score_block = extract_block(text, 'score')
    stats.score_place = extract_value(score_block, r'score_place=(\d+)', int, 0)
    rating_block = extract_block(score_block, 'score_rating')
    stats.score_adm = extract_value(rating_block, r'ADM=([\d.]+)', float, 0.0)
    stats.score_dip = extract_value(rating_block, r'DIP=([\d.]+)', float, 0.0)
    stats.score_mil = extract_value(rating_block, r'MIL=([\d.]+)', float, 0.0)

    # Currency/Resources
    currency_block = extract_block(text, 'currency_data')
    stats.manpower = extract_value(currency_block, r'manpower=([\d.]+)', float, 0.0)
    stats.sailors = extract_value(currency_block, r'sailors=([\d.]+)', float, 0.0)
    stats.gold = extract_value(currency_block, r'gold=([\d.-]+)', float, 0.0)
    stats.stability = extract_value(currency_block, r'stability=([\d.-]+)', float, 0.0)
    stats.prestige = extract_value(currency_block, r'prestige=([\d.-]+)', float, 0.0)
    stats.army_tradition = extract_value(currency_block, r'army_tradition=([\d.]+)', float, 0.0)
    stats.navy_tradition = extract_value(currency_block, r'navy_tradition=([\d.]+)', float, 0.0)

    # Economy
    stats.monthly_income = extract_value(text, r'estimated_monthly_income=([\d.]+)', float, 0.0)
    stats.current_tax_base = extract_value(text, r'current_tax_base=([\d.]+)', float, 0.0)
    economy_block = extract_block(text, 'economy')
    stats.loan_capacity = extract_value(economy_block, r'loan_capacity=([\d.]+)', float, 0.0)

    # Population & Territory
    stats.population = extract_value(text, r'last_months_population=([\d.]+)', float, 0.0)
    stats.great_power_rank = extract_value(text, r'great_power_rank=(\d+)', int, 0)

    # Count provinces
    provinces_list = extract_list(text, 'provinces')
    stats.num_provinces = len(provinces_list)

    # Military
    stats.max_manpower = extract_value(text, r'max_manpower=([\d.]+)', float, 0.0)
    stats.monthly_manpower = extract_value(text, r'monthly_manpower=([\d.]+)', float, 0.0)
    stats.max_sailors = extract_value(text, r'max_sailors=([\d.]+)', float, 0.0)

    units_list = extract_list(text, r'\bunits')
    stats.num_units = len(units_list)
    subunits_list = extract_list(text, 'owned_subunits')
    stats.num_subunits = len(subunits_list)

    # Production
    stats.total_produced = extract_value(text, r'total_produced=([\d.]+)', float, 0.0)
    stats.produced_goods = extract_dict(text, 'last_month_produced')

    # Institutions & Tech
    stats.institutions = [k for k, v in extract_dict(text, 'institutions').items() if v == True]
    advances = extract_dict(text, 'researched_advances')
    stats.researched_advances = [k for k, v in advances.items() if v == True]
    stats.num_researched_advances = len(stats.researched_advances)

    # Government
    govt_block = extract_block(text, 'government')
    stats.government_type = extract_value(govt_block, r'type=(\w+)', str, "")
    stats.employment_system = extract_value(text, r'employment_system=(\w+)', str, "")

    # Religion
    stats.religion_id = extract_value(text, r'primary_religion=(\d+)', int, 0)
    stats.religion_name = RELIGION_NAMES.get(stats.religion_id, f"unknown_{stats.religion_id}")

    # Privileges & Reforms
    stats.privileges = extract_nested_objects(govt_block, 'implemented_privileges')
    stats.num_privileges = len(stats.privileges)
    stats.reforms = extract_nested_objects(govt_block, 'implemented_reforms')
    stats.num_reforms = len(stats.reforms)

    # Laws
    laws_block = extract_block(govt_block, 'implemented_laws')
    for match in re.finditer(r'(\w+_law)=\{[^}]*object=(\w+)', laws_block):
        stats.laws[match.group(1)] = match.group(2)

    # Societal Values
    stats.values = extract_dict(text, 'societal_values')

    return stats


def find_country_in_file(filepath: str, tag: str) -> str | None:
    """Find and extract a country block from the save file."""
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        in_countries = False
        in_database = False
        collecting = False
        depth = 0
        lines = []
        prev_line = ""

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
                if f'country_name="{tag}"' in line:
                    collecting = True
                    # Include previous line which has the opening brace (e.g., "206={")
                    if prev_line:
                        lines.append(prev_line)
                        depth = prev_line.count('{') - prev_line.count('}')
                    lines.append(line)
                    depth += line.count('{') - line.count('}')
                prev_line = line
            else:
                lines.append(line)
                depth += line.count('{') - line.count('}')

                if depth <= 0:
                    break

        if lines:
            return ''.join(lines)

    return None


def format_number(val: float, decimals: int = 1) -> str:
    """Format a number for display."""
    if val >= 1000000:
        return f"{val/1000000:.1f}M"
    elif val >= 1000:
        return f"{val/1000:.1f}K"
    elif isinstance(val, float):
        return f"{val:.{decimals}f}"
    return str(val)


def print_comparison(countries: list[CountryStats]):
    """Print a formatted comparison table."""
    # Sort by Great Power Rank (ascending - lower is better)
    countries.sort(key=lambda c: (c.great_power_rank if c.great_power_rank > 0 else 9999))

    print("\n" + "="*120)
    print("EU5 PLAYER COUNTRY COMPARISON")
    print("="*120)

    # Header row
    tags = [c.tag for c in countries]
    print(f"\n{'Metric':<30} " + " ".join(f"{t:>10}" for t in tags))
    print("-"*120)

    # Rank & Score
    print(f"\n{'=== RANK & SCORE ===':<30}")
    print(f"{'Great Power Rank':<30} " + " ".join(f"{c.great_power_rank:>10}" for c in countries))
    print(f"{'ADM Score':<30} " + " ".join(f"{c.score_adm:>10.1f}" for c in countries))
    print(f"{'DIP Score':<30} " + " ".join(f"{c.score_dip:>10.1f}" for c in countries))
    print(f"{'MIL Score':<30} " + " ".join(f"{c.score_mil:>10.1f}" for c in countries))

    # Economy
    print(f"\n{'=== ECONOMY ===':<30}")
    print(f"{'Treasury (Gold)':<30} " + " ".join(f"{format_number(c.gold):>10}" for c in countries))
    print(f"{'Monthly Income':<30} " + " ".join(f"{format_number(c.monthly_income):>10}" for c in countries))
    print(f"{'Tax Base':<30} " + " ".join(f"{format_number(c.current_tax_base):>10}" for c in countries))
    print(f"{'Loan Capacity':<30} " + " ".join(f"{format_number(c.loan_capacity):>10}" for c in countries))

    # Population & Territory
    print(f"\n{'=== POPULATION & TERRITORY ===':<30}")
    print(f"{'Population':<30} " + " ".join(f"{format_number(c.population):>10}" for c in countries))
    print(f"{'Provinces Owned':<30} " + " ".join(f"{c.num_provinces:>10}" for c in countries))

    # Military
    print(f"\n{'=== MILITARY ===':<30}")
    print(f"{'Manpower':<30} " + " ".join(f"{format_number(c.manpower):>10}" for c in countries))
    print(f"{'Max Manpower':<30} " + " ".join(f"{format_number(c.max_manpower):>10}" for c in countries))
    print(f"{'Monthly Manpower':<30} " + " ".join(f"{c.monthly_manpower:>10.2f}" for c in countries))
    print(f"{'Sailors':<30} " + " ".join(f"{format_number(c.sailors):>10}" for c in countries))
    print(f"{'Max Sailors':<30} " + " ".join(f"{format_number(c.max_sailors):>10}" for c in countries))
    print(f"{'Army Tradition':<30} " + " ".join(f"{c.army_tradition:>10.1f}" for c in countries))
    print(f"{'Navy Tradition':<30} " + " ".join(f"{c.navy_tradition:>10.1f}" for c in countries))
    print(f"{'Units (Armies/Navies)':<30} " + " ".join(f"{c.num_units:>10}" for c in countries))
    print(f"{'Subunits (Regiments)':<30} " + " ".join(f"{c.num_subunits:>10}" for c in countries))

    # Production
    print(f"\n{'=== PRODUCTION ===':<30}")
    print(f"{'Total Produced':<30} " + " ".join(f"{format_number(c.total_produced):>10}" for c in countries))

    # Tech & Institutions
    print(f"\n{'=== TECH & INSTITUTIONS ===':<30}")
    print(f"{'Researched Advances':<30} " + " ".join(f"{c.num_researched_advances:>10}" for c in countries))
    print(f"{'Institutions':<30} " + " ".join(f"{len(c.institutions):>10}" for c in countries))

    # Government & Religion
    print(f"\n{'=== GOVERNMENT & RELIGION ===':<30}")
    print(f"{'Government Type':<30} " + " ".join(f"{c.government_type:>10}" for c in countries))
    print(f"{'Religion':<30} " + " ".join(f"{c.religion_name:>10}" for c in countries))
    print(f"{'Stability':<30} " + " ".join(f"{c.stability:>10.1f}" for c in countries))
    print(f"{'Prestige':<30} " + " ".join(f"{c.prestige:>10.1f}" for c in countries))
    print(f"{'Privileges':<30} " + " ".join(f"{c.num_privileges:>10}" for c in countries))
    print(f"{'Reforms':<30} " + " ".join(f"{c.num_reforms:>10}" for c in countries))
    print(f"{'Laws':<30} " + " ".join(f"{len(c.laws):>10}" for c in countries))

    print("\n" + "="*120)

    # Detailed sections
    print("\n\n" + "="*80)
    print("DETAILED STATS BY COUNTRY")
    print("="*80)

    for c in countries:
        print(f"\n{'='*60}")
        print(f"{c.tag} - {c.name}")
        print(f"{'='*60}")

        print(f"\nInstitutions: {', '.join(c.institutions)}")

        if c.values:
            print(f"\nSocietal Values:")
            for k, v in sorted(c.values.items()):
                if v != -999:  # Skip unavailable values
                    print(f"  {k}: {v:.1f}")

        print(f"\nTop 10 Produced Goods:")
        sorted_goods = sorted(c.produced_goods.items(), key=lambda x: x[1], reverse=True)[:10]
        for good, amount in sorted_goods:
            print(f"  {good}: {amount:.1f}")

        if c.privileges:
            print(f"\nPrivileges ({len(c.privileges)}):")
            for p in c.privileges[:10]:  # Show first 10
                print(f"  - {p}")
            if len(c.privileges) > 10:
                print(f"  ... and {len(c.privileges) - 10} more")

        if c.reforms:
            print(f"\nReforms ({len(c.reforms)}):")
            for r in c.reforms:
                print(f"  - {r}")

        if c.laws:
            print(f"\nLaws ({len(c.laws)}):")
            for law_type, policy in sorted(c.laws.items()):
                print(f"  - {law_type}: {policy}")


def main():
    # Default save file path
    save_dir = Path(__file__).parent.resolve() / "save"
    save_files = list(save_dir.glob("*.eu5"))

    if not save_files:
        print("No .eu5 save files found in save directory")
        sys.exit(1)

    save_file = save_files[0]  # Use first save file found
    print(f"Analyzing save file: {save_file.name}")
    print(f"Looking for {len(PLAYER_COUNTRIES)} player countries: {', '.join(PLAYER_COUNTRIES.keys())}")

    countries = []
    for tag, name in PLAYER_COUNTRIES.items():
        print(f"  Extracting {tag} ({name})...", end=" ", flush=True)
        country_text = find_country_in_file(str(save_file), tag)

        if country_text:
            stats = parse_country_block(country_text, tag)
            countries.append(stats)
            print(f"OK (Score: {stats.score_place}, Pop: {format_number(stats.population)})")
        else:
            print("NOT FOUND")

    if countries:
        print_comparison(countries)
    else:
        print("No player countries found!")


if __name__ == '__main__':
    main()
