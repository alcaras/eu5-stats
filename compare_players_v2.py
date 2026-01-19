#!/usr/bin/env python3
"""
EU5 Save File Player Comparison Tool v2
With ruler stats, proper population display, and time series graphs.
"""

import re
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

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
                    countries[line] = line
    return countries


# Load player countries from config file
PLAYER_COUNTRIES = load_human_countries()

# Religion ID to name mapping
RELIGION_NAMES = {
    0: 'bon', 1: 'mahayana', 2: 'shinto', 3: 'theravada',
    5: 'confucianism', 6: 'taoism', 7: 'hinduism',
    8: 'bogomilism', 9: 'bosnian_church', 10: 'paulicianism', 11: 'catharism',
    12: 'catholic', 13: 'hussite', 14: 'lollardism', 15: 'miaphysite',
    16: 'nestorianism', 17: 'strigolniki', 18: 'orthodox', 19: 'waldensian',
    20: 'judaism', 21: 'samaritanism', 22: 'karaism', 23: 'jain',
    24: 'sikhism', 25: 'druzism',
    152: 'tengri', 153: 'tungusic_shamanism', 158: 'namandu',
    280: 'ibadi', 281: 'ismaili', 282: 'yazidism', 283: 'zikri',
    284: 'ahmadiyya', 285: 'shia', 286: 'sunni',
}


@dataclass
class CountryStats:
    tag: str
    name: str = ""

    # Country color (RGB tuple 0-255)
    color: tuple = (128, 128, 128)

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

    # Population & Territory (in thousands, display as millions)
    population: float = 0.0
    num_provinces: int = 0

    # Military
    manpower: float = 0.0
    max_manpower: float = 0.0
    army_tradition: float = 0.0
    navy_tradition: float = 0.0
    num_subunits: int = 0

    # Production
    total_produced: float = 0.0

    # Tech
    num_researched_advances: int = 0
    institutions: list = field(default_factory=list)

    # Government
    government_type: str = ""
    stability: float = 0.0
    prestige: float = 0.0
    religion_name: str = ""

    # Time series data
    historical_population: list = field(default_factory=list)
    historical_tax_base: list = field(default_factory=list)
    monthly_gold: list = field(default_factory=list)


def extract_value(text: str, pattern: str, cast=str, default=None):
    match = re.search(pattern, text)
    if match:
        try:
            return cast(match.group(1))
        except (ValueError, TypeError):
            return default
    return default


def extract_list_values(text: str, key: str) -> list:
    """Extract numeric values from a block."""
    pattern = rf'{key}=\{{([^}}]+)\}}'
    match = re.search(pattern, text)
    if match:
        values = []
        for v in match.group(1).strip().split():
            try:
                values.append(float(v))
            except ValueError:
                pass
        return values
    return []


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
            if v == 'yes':
                result[k] = True
            elif v == 'no':
                result[k] = False
            else:
                result[k] = v
    return result


def find_character(filepath: str, char_id: int) -> dict | None:
    """Find a character by ID in character_db."""
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        in_char_db = False
        in_database = False
        collecting = False
        depth = 0
        lines = []
        target = f"\t\t{char_id}={{"

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
            return {
                'adm': extract_value(text, r'adm=(\d+)', int, 0),
                'dip': extract_value(text, r'dip=(\d+)', int, 0),
                'mil': extract_value(text, r'mil=(\d+)', int, 0),
                'first_name': extract_value(text, r'first_name="([^"]+)"', str, ""),
                'nickname': extract_value(text, r'nickname="([^"]+)"', str, ""),
                'traits': re.findall(r'traits=\{([^}]+)\}', text),
            }
    return None


def parse_country_block(text: str, tag: str) -> CountryStats:
    stats = CountryStats(tag=tag)
    stats.name = PLAYER_COUNTRIES.get(tag, tag)

    # Country color from save file
    color_match = re.search(r'color=rgb\s*\{\s*(\d+)\s+(\d+)\s+(\d+)\s*\}', text)
    if color_match:
        stats.color = (int(color_match.group(1)), int(color_match.group(2)), int(color_match.group(3)))

    # Ruler ID
    govt_block = extract_block(text, 'government')
    stats.ruler_id = extract_value(govt_block, r'ruler=(\d+)', int, 0)

    # Great Power Rank - use great_power_rank field
    stats.great_power_rank = extract_value(text, r'great_power_rank=(\d+)', int, 0)

    # Currency/Resources
    currency_block = extract_block(text, 'currency_data')
    stats.gold = extract_value(currency_block, r'gold=([\d.-]+)', float, 0.0)
    stats.stability = extract_value(currency_block, r'stability=([\d.-]+)', float, 0.0)
    stats.prestige = extract_value(currency_block, r'prestige=([\d.-]+)', float, 0.0)
    stats.army_tradition = extract_value(currency_block, r'army_tradition=([\d.]+)', float, 0.0)
    stats.navy_tradition = extract_value(currency_block, r'navy_tradition=([\d.]+)', float, 0.0)
    stats.manpower = extract_value(currency_block, r'manpower=([\d.]+)', float, 0.0)

    # Economy
    stats.monthly_income = extract_value(text, r'estimated_monthly_income=([\d.]+)', float, 0.0)
    stats.current_tax_base = extract_value(text, r'current_tax_base=([\d.]+)', float, 0.0)
    economy_block = extract_block(text, 'economy')
    stats.loan_capacity = extract_value(economy_block, r'loan_capacity=([\d.]+)', float, 0.0)

    # Population & Territory
    stats.population = extract_value(text, r'last_months_population=([\d.]+)', float, 0.0)
    stats.max_manpower = extract_value(text, r'max_manpower=([\d.]+)', float, 0.0)

    # Count provinces
    provinces_match = re.search(r'provinces=\{([^}]+)\}', text)
    if provinces_match:
        stats.num_provinces = len(provinces_match.group(1).split())

    # Military
    subunits_match = re.search(r'owned_subunits=\{([^}]+)\}', text)
    if subunits_match:
        stats.num_subunits = len(subunits_match.group(1).split())

    # Production
    stats.total_produced = extract_value(text, r'total_produced=([\d.]+)', float, 0.0)

    # Tech
    advances = extract_dict(text, 'researched_advances')
    stats.num_researched_advances = sum(1 for v in advances.values() if v == True)
    stats.institutions = [k for k, v in extract_dict(text, 'institutions').items() if v == True]

    # Government
    stats.government_type = extract_value(govt_block, r'type=(\w+)', str, "")

    # Religion
    religion_id = extract_value(text, r'primary_religion=(\d+)', int, 0)
    stats.religion_name = RELIGION_NAMES.get(religion_id, f"id_{religion_id}")

    # Time series data
    stats.historical_population = extract_list_values(text, 'historical_population')
    stats.historical_tax_base = extract_list_values(text, 'historical_tax_base')
    stats.monthly_gold = extract_list_values(text, 'monthly_gold')

    return stats


def find_country_in_file(filepath: str, tag: str) -> str | None:
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        in_countries = False
        in_database = False
        collecting = False
        depth = 0
        lines = []
        recent_lines = []

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
                recent_lines.append(line)
                if len(recent_lines) > 10:
                    recent_lines.pop(0)

                if f'country_name="{tag}"' in line or f'flag={tag}' in line:
                    collecting = True
                    # Get indent level of country_name line (country block starts one level up)
                    name_indent = len(line) - len(line.lstrip('\t'))
                    target_indent = name_indent - 1
                    # Search backward for block start at correct indent
                    for i in range(len(recent_lines) - 1, -1, -1):
                        prev = recent_lines[i]
                        prev_indent = len(prev) - len(prev.lstrip('\t'))
                        stripped = prev.strip()
                        if prev_indent == target_indent and '={' in stripped and stripped[0].isdigit():
                            lines.extend(recent_lines[i:])
                            depth = sum(l.count('{') - l.count('}') for l in lines)
                            break
                    else:
                        lines.extend(recent_lines)
                        depth = sum(l.count('{') - l.count('}') for l in lines)
            else:
                lines.append(line)
                depth += line.count('{') - line.count('}')
                if depth <= 0:
                    break

        if lines:
            return ''.join(lines)
    return None


def format_pop(val: float) -> str:
    """Format population in millions."""
    if val >= 1000:
        return f"{val/1000:.1f}M"
    else:
        return f"{val:.0f}K"


def format_number(val: float) -> str:
    if val >= 1000:
        return f"{val/1000:.1f}K"
    return f"{val:.0f}"


def print_comparison(countries: list[CountryStats]):
    countries.sort(key=lambda c: (c.great_power_rank if c.great_power_rank > 0 else 9999))

    print("\n" + "="*130)
    print("EU5 PLAYER COUNTRY COMPARISON")
    print("="*130)

    tags = [c.tag for c in countries]
    print(f"\n{'Metric':<25} " + " ".join(f"{t:>11}" for t in tags))
    print("-"*130)

    # Rank
    print(f"\n{'=== RANK ===':<25}")
    print(f"{'Great Power Rank':<25} " + " ".join(f"{c.great_power_rank:>11}" for c in countries))

    # Ruler
    print(f"\n{'=== RULER STATS ===':<25}")
    print(f"{'Ruler ADM':<25} " + " ".join(f"{c.ruler_adm:>11}" for c in countries))
    print(f"{'Ruler DIP':<25} " + " ".join(f"{c.ruler_dip:>11}" for c in countries))
    print(f"{'Ruler MIL':<25} " + " ".join(f"{c.ruler_mil:>11}" for c in countries))

    # Economy
    print(f"\n{'=== ECONOMY ===':<25}")
    print(f"{'Treasury (Gold)':<25} " + " ".join(f"{format_number(c.gold):>11}" for c in countries))
    print(f"{'Monthly Income':<25} " + " ".join(f"{format_number(c.monthly_income):>11}" for c in countries))
    print(f"{'Tax Base':<25} " + " ".join(f"{format_number(c.current_tax_base):>11}" for c in countries))

    # Population & Territory
    print(f"\n{'=== POPULATION ===':<25}")
    print(f"{'Population':<25} " + " ".join(f"{format_pop(c.population):>11}" for c in countries))
    print(f"{'Provinces':<25} " + " ".join(f"{c.num_provinces:>11}" for c in countries))

    # Military
    print(f"\n{'=== MILITARY ===':<25}")
    print(f"{'Manpower':<25} " + " ".join(f"{c.manpower:>11.1f}" for c in countries))
    print(f"{'Max Manpower':<25} " + " ".join(f"{c.max_manpower:>11.1f}" for c in countries))
    print(f"{'Army Tradition':<25} " + " ".join(f"{c.army_tradition:>11.1f}" for c in countries))
    print(f"{'Regiments':<25} " + " ".join(f"{c.num_subunits:>11}" for c in countries))

    # Tech
    print(f"\n{'=== TECH ===':<25}")
    print(f"{'Advances':<25} " + " ".join(f"{c.num_researched_advances:>11}" for c in countries))
    print(f"{'Institutions':<25} " + " ".join(f"{len(c.institutions):>11}" for c in countries))

    # Government
    print(f"\n{'=== GOVERNMENT ===':<25}")
    print(f"{'Type':<25} " + " ".join(f"{c.government_type:>11}" for c in countries))
    print(f"{'Religion':<25} " + " ".join(f"{c.religion_name:>11}" for c in countries))
    print(f"{'Stability':<25} " + " ".join(f"{c.stability:>11.1f}" for c in countries))

    print("\n" + "="*130)


def get_color_for_matplotlib(color_tuple):
    """Convert RGB 0-255 tuple to matplotlib 0-1 format."""
    return (color_tuple[0] / 255, color_tuple[1] / 255, color_tuple[2] / 255)


def simple_treemap(ax, sizes, labels, colors, title):
    """Create a simple treemap using matplotlib rectangles."""
    import matplotlib.patches as mpatches

    # Filter out zero/negative values
    data = [(s, l, c) for s, l, c in zip(sizes, labels, colors) if s > 0]
    if not data:
        return

    data.sort(key=lambda x: x[0], reverse=True)
    sizes = [d[0] for d in data]
    labels = [d[1] for d in data]
    colors = [d[2] for d in data]

    total = sum(sizes)
    normed = [s / total for s in sizes]

    # Simple slice-and-dice layout
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_aspect('equal')
    ax.axis('off')
    ax.set_title(title, fontsize=14, fontweight='bold')

    x, y = 0, 0
    width = 1
    height = 1
    horizontal = True

    rects = []
    for i, (size, label, color) in enumerate(zip(normed, labels, colors)):
        if horizontal:
            rect_width = size / (sum(normed[i:]) if sum(normed[i:]) > 0 else 1) * width
            rect_height = height
            rect = mpatches.Rectangle((x, y), rect_width, rect_height,
                                       facecolor=color, edgecolor='white', linewidth=2)
            ax.add_patch(rect)
            # Add label
            cx, cy = x + rect_width / 2, y + rect_height / 2
            ax.text(cx, cy, f"{label}\n{sizes[i]:,.0f}", ha='center', va='center',
                    fontsize=10, fontweight='bold', color='white',
                    bbox=dict(boxstyle='round', facecolor='black', alpha=0.3))
            x += rect_width
            width -= rect_width
        else:
            rect_width = width
            rect_height = size / (sum(normed[i:]) if sum(normed[i:]) > 0 else 1) * height
            rect = mpatches.Rectangle((x, y), rect_width, rect_height,
                                       facecolor=color, edgecolor='white', linewidth=2)
            ax.add_patch(rect)
            cx, cy = x + rect_width / 2, y + rect_height / 2
            ax.text(cx, cy, f"{label}\n{sizes[i]:,.0f}", ha='center', va='center',
                    fontsize=10, fontweight='bold', color='white',
                    bbox=dict(boxstyle='round', facecolor='black', alpha=0.3))
            y += rect_height
            height -= rect_height
        horizontal = not horizontal


def create_graphs(countries: list[CountryStats], save_dir: Path):
    """Create charts and text reports."""

    # Filter countries with data
    countries_with_pop = [c for c in countries if c.historical_population]
    countries_with_tax = [c for c in countries if c.historical_tax_base]
    countries_with_income = [c for c in countries if c.monthly_gold]

    # Build color map from country colors
    color_map = {c.tag: get_color_for_matplotlib(c.color) for c in countries}

    # Determine year range
    start_year = 1337
    chart_num = 1

    # === TIME SERIES CHARTS ===

    # Chart 1: Population over time
    if countries_with_pop:
        fig, ax = plt.subplots(figsize=(14, 7))
        for c in countries_with_pop:
            years = [start_year + i for i in range(len(c.historical_population))]
            pop_millions = [p / 1000 for p in c.historical_population]
            ax.plot(years, pop_millions, label=c.tag, linewidth=3, color=color_map[c.tag])
            # Add label at end of line
            if years and pop_millions:
                ax.annotate(c.tag, (years[-1], pop_millions[-1]), textcoords="offset points",
                           xytext=(5, 0), ha='left', fontsize=9, fontweight='bold',
                           color=color_map[c.tag])
        ax.set_xlabel('Year')
        ax.set_ylabel('Population (millions)')
        ax.set_title(f'{chart_num}. Population Over Time')
        ax.legend(loc='upper left', fontsize=9)
        ax.grid(True, alpha=0.3)
        # Add margin on right for labels
        ax.margins(x=0.1)
        plt.tight_layout()
        plt.savefig(save_dir / f'{chart_num:02d}_population_history.png', dpi=150)
        print(f"  Saved: {chart_num:02d}_population_history.png")
        plt.close()
        chart_num += 1

    # Chart 2: Tax Base over time
    if countries_with_tax:
        fig, ax = plt.subplots(figsize=(14, 7))
        for c in countries_with_tax:
            years = [start_year + i for i in range(len(c.historical_tax_base))]
            ax.plot(years, c.historical_tax_base, label=c.tag, linewidth=3, color=color_map[c.tag])
            # Add label at end of line
            if years and c.historical_tax_base:
                ax.annotate(c.tag, (years[-1], c.historical_tax_base[-1]), textcoords="offset points",
                           xytext=(5, 0), ha='left', fontsize=9, fontweight='bold',
                           color=color_map[c.tag])
        ax.set_xlabel('Year')
        ax.set_ylabel('Tax Base')
        ax.set_title(f'{chart_num}. Tax Base Over Time')
        ax.legend(loc='upper left', fontsize=9)
        ax.grid(True, alpha=0.3)
        ax.margins(x=0.1)
        plt.tight_layout()
        plt.savefig(save_dir / f'{chart_num:02d}_taxbase_history.png', dpi=150)
        print(f"  Saved: {chart_num:02d}_taxbase_history.png")
        plt.close()
        chart_num += 1

    # === TREEMAP CHARTS ===

    # Treemap 4: Population
    fig, ax = plt.subplots(figsize=(12, 8))
    countries_sorted = sorted(countries, key=lambda c: c.population, reverse=True)
    sizes = [c.population for c in countries_sorted]
    labels = [c.tag for c in countries_sorted]
    colors = [color_map[c.tag] for c in countries_sorted]
    simple_treemap(ax, sizes, labels, colors, f'{chart_num}. Population Treemap (thousands)')
    plt.tight_layout()
    plt.savefig(save_dir / f'{chart_num:02d}_treemap_population.png', dpi=150)
    print(f"  Saved: {chart_num:02d}_treemap_population.png")
    plt.close()
    chart_num += 1

    # Treemap 5: Tax Base
    fig, ax = plt.subplots(figsize=(12, 8))
    countries_sorted = sorted(countries, key=lambda c: c.current_tax_base, reverse=True)
    sizes = [c.current_tax_base for c in countries_sorted]
    labels = [c.tag for c in countries_sorted]
    colors = [color_map[c.tag] for c in countries_sorted]
    simple_treemap(ax, sizes, labels, colors, f'{chart_num}. Tax Base Treemap')
    plt.tight_layout()
    plt.savefig(save_dir / f'{chart_num:02d}_treemap_taxbase.png', dpi=150)
    print(f"  Saved: {chart_num:02d}_treemap_taxbase.png")
    plt.close()
    chart_num += 1

    # Treemap 6: Military (Regiments)
    fig, ax = plt.subplots(figsize=(12, 8))
    countries_sorted = sorted(countries, key=lambda c: c.num_subunits, reverse=True)
    sizes = [c.num_subunits for c in countries_sorted]
    labels = [c.tag for c in countries_sorted]
    colors = [color_map[c.tag] for c in countries_sorted]
    simple_treemap(ax, sizes, labels, colors, f'{chart_num}. Military Regiments Treemap')
    plt.tight_layout()
    plt.savefig(save_dir / f'{chart_num:02d}_treemap_military.png', dpi=150)
    print(f"  Saved: {chart_num:02d}_treemap_military.png")
    plt.close()
    chart_num += 1

    # Treemap 7: Manpower
    fig, ax = plt.subplots(figsize=(12, 8))
    countries_sorted = sorted(countries, key=lambda c: c.manpower, reverse=True)
    sizes = [c.manpower for c in countries_sorted]
    labels = [c.tag for c in countries_sorted]
    colors = [color_map[c.tag] for c in countries_sorted]
    simple_treemap(ax, sizes, labels, colors, f'{chart_num}. Manpower Treemap')
    plt.tight_layout()
    plt.savefig(save_dir / f'{chart_num:02d}_treemap_manpower.png', dpi=150)
    print(f"  Saved: {chart_num:02d}_treemap_manpower.png")
    plt.close()
    chart_num += 1

    # === TEXT FILES ===

    # Text file: GP Rankings
    with open(save_dir / 'gp_rankings.txt', 'w') as f:
        f.write("GREAT POWER RANKINGS\n")
        f.write("=" * 50 + "\n\n")
        countries_sorted = sorted(countries, key=lambda c: c.great_power_rank)
        for i, c in enumerate(countries_sorted, 1):
            f.write(f"{i:2}. {c.tag:<5} - GP #{c.great_power_rank:<4} | Pop: {c.population/1000:.2f}M | Income: {c.monthly_income:.0f}\n")
    print(f"  Saved: gp_rankings.txt")

    # Text file: Tech Advances with unique advances
    with open(save_dir / 'tech_advances.txt', 'w') as f:
        f.write("TECHNOLOGY ADVANCES\n")
        f.write("=" * 60 + "\n\n")

        # Get all advances for each country
        all_advances = {}
        for c in countries:
            all_advances[c.tag] = set(c.institutions) if c.institutions else set()

        # Find common advances (all players have)
        if all_advances:
            common = set.intersection(*all_advances.values()) if len(all_advances) > 1 else set()
        else:
            common = set()

        # Sort by advance count
        countries_sorted = sorted(countries, key=lambda c: c.num_researched_advances, reverse=True)

        f.write("SUMMARY BY COUNTRY\n")
        f.write("-" * 40 + "\n")
        for c in countries_sorted:
            f.write(f"{c.tag:<5}: {c.num_researched_advances} advances, {len(c.institutions)} institutions\n")

        f.write("\n\nINSTITUTIONS BY COUNTRY\n")
        f.write("-" * 40 + "\n")
        for c in countries_sorted:
            inst_list = ", ".join(reversed(c.institutions)) if c.institutions else "None"
            f.write(f"{c.tag}: {inst_list}\n")

        f.write("\n\nUNIQUE INSTITUTIONS (not shared by all)\n")
        f.write("-" * 40 + "\n")
        for c in countries_sorted:
            unique = set(c.institutions) - common if c.institutions else set()
            missing = common - set(c.institutions) if c.institutions else common
            if unique:
                f.write(f"{c.tag} has: {', '.join(unique)}\n")
            if missing:
                f.write(f"{c.tag} missing: {', '.join(missing)}\n")

    print(f"  Saved: tech_advances.txt")

    # Legacy combined view
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle('EU5 Player Countries - Overview', fontsize=14, fontweight='bold')

    if countries_with_pop:
        ax1 = axes[0, 0]
        for c in countries_with_pop:
            years = [start_year + i for i in range(len(c.historical_population))]
            pop_millions = [p / 1000 for p in c.historical_population]
            ax1.plot(years, pop_millions, label=c.tag, linewidth=2, color=color_map[c.tag])
        ax1.set_xlabel('Year')
        ax1.set_ylabel('Population (millions)')
        ax1.set_title('Population Over Time')
        ax1.legend(loc='upper left', fontsize=8)
        ax1.grid(True, alpha=0.3)

    if countries_with_tax:
        ax2 = axes[0, 1]
        for c in countries_with_tax:
            years = [start_year + i for i in range(len(c.historical_tax_base))]
            ax2.plot(years, c.historical_tax_base, label=c.tag, linewidth=2, color=color_map[c.tag])
        ax2.set_xlabel('Year')
        ax2.set_ylabel('Tax Base')
        ax2.set_title('Tax Base Over Time')
        ax2.legend(loc='upper left', fontsize=8)
        ax2.grid(True, alpha=0.3)

    ax3 = axes[1, 0]
    countries_sorted = sorted(countries, key=lambda c: c.population, reverse=True)
    tags = [c.tag for c in countries_sorted]
    pops = [c.population / 1000 for c in countries_sorted]
    bar_colors = [color_map[c.tag] for c in countries_sorted]
    ax3.barh(tags, pops, color=bar_colors)
    ax3.set_xlabel('Population (millions)')
    ax3.set_title('Current Population')
    ax3.invert_yaxis()

    ax4 = axes[1, 1]
    countries_sorted = sorted(countries, key=lambda c: c.monthly_income, reverse=True)
    tags = [c.tag for c in countries_sorted]
    incomes = [c.monthly_income for c in countries_sorted]
    bar_colors = [color_map[c.tag] for c in countries_sorted]
    ax4.barh(tags, incomes, color=bar_colors)
    ax4.set_xlabel('Monthly Income')
    ax4.set_title('Current Monthly Income')
    ax4.invert_yaxis()

    plt.tight_layout()
    plt.savefig(save_dir / 'player_comparison.png', dpi=150)
    print(f"\nCombined graph saved to: player_comparison.png")
    plt.close()


def get_save_date(filepath: str) -> str:
    """Extract save date from save file."""
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        for i, line in enumerate(f):
            if 'date=' in line and '.' in line:
                match = re.search(r'date=(\d+\.\d+\.\d+)', line)
                if match:
                    return match.group(1)
            if i > 100:
                break
    return "Unknown"


def main():
    import argparse
    from datetime import datetime

    parser = argparse.ArgumentParser(description='Generate EU5 player comparison with graphs')
    parser.add_argument('-o', '--output', help='Output directory for graphs')
    parser.add_argument('--no-timestamp', action='store_true', help='Don\'t create timestamped subfolder')
    args = parser.parse_args()

    base_dir = SCRIPT_DIR
    save_dir = base_dir / "save"
    save_files = list(save_dir.glob("*.eu5"))

    if not save_files:
        print("No .eu5 save files found")
        sys.exit(1)

    save_file = save_files[0]
    save_date = get_save_date(str(save_file))
    print(f"Analyzing: {save_file.name} ({save_date})")

    # Determine output directory
    if args.output:
        output_dir = Path(args.output)
    else:
        output_dir = base_dir / "reports"

    # Create timestamped subfolder unless disabled
    if not args.no_timestamp:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_date_clean = save_date.replace('.', '_')
        output_dir = output_dir / f"{save_date_clean}_{timestamp}"

    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output: {output_dir}")

    countries = []
    for tag, name in PLAYER_COUNTRIES.items():
        print(f"  {tag}...", end=" ", flush=True)
        country_text = find_country_in_file(str(save_file), tag)

        if country_text:
            stats = parse_country_block(country_text, tag)

            # Get ruler stats
            if stats.ruler_id:
                ruler = find_character(str(save_file), stats.ruler_id)
                if ruler:
                    stats.ruler_adm = ruler['adm']
                    stats.ruler_dip = ruler['dip']
                    stats.ruler_mil = ruler['mil']
                    name_parts = []
                    if ruler['first_name']:
                        name_parts.append(ruler['first_name'].replace('name_', ''))
                    if ruler['nickname']:
                        name_parts.append(f'"{ruler["nickname"]}"')
                    stats.ruler_name = ' '.join(name_parts)

            countries.append(stats)
            print(f"GP#{stats.great_power_rank}, Pop: {format_pop(stats.population)}, Ruler: {stats.ruler_adm}/{stats.ruler_dip}/{stats.ruler_mil}")
        else:
            print("NOT FOUND")

    if countries:
        print_comparison(countries)
        create_graphs(countries, output_dir)


if __name__ == '__main__':
    main()
