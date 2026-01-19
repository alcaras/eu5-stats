#!/usr/bin/env python3
"""
EU5 Save File Chart Generator
Creates various visualizations: treemaps, radar charts, stacked bars
"""

import re
import sys
from pathlib import Path
from dataclasses import dataclass, field
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

try:
    import squarify
    HAS_SQUARIFY = True
except ImportError:
    HAS_SQUARIFY = False
    print("Note: Install squarify for treemaps: pip install squarify")


# Player countries
PLAYER_COUNTRIES = {
    'GBR': 'Great Britain',
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

# Goods categories for EU5
GOODS_CATEGORIES = {
    'Food & Agriculture': ['wheat', 'livestock', 'fish', 'wild_game', 'fruit'],
    'Raw Materials': ['lumber', 'iron', 'copper', 'coal', 'stone', 'clay', 'sand', 'lead', 'tin'],
    'Precious': ['goods_gold', 'silver', 'gems'],
    'Textiles': ['wool', 'silk', 'fiber_crops', 'cotton', 'cloth', 'fine_cloth'],
    'Luxury': ['wine', 'spices', 'saffron', 'dyes', 'jewelry', 'porcelain'],
    'Industrial': ['tools', 'glass', 'paper', 'books', 'firearms', 'cannons', 'weaponry'],
    'Naval': ['naval_supplies', 'tar'],
    'Other': ['salt', 'alum', 'saltpeter', 'medicaments', 'marble', 'liquor', 'beer', 'leather'],
}


@dataclass
class CountryData:
    tag: str
    name: str = ""
    color: tuple = (128, 128, 128)
    population: float = 0.0
    monthly_income: float = 0.0
    tax_base: float = 0.0
    treasury: float = 0.0
    manpower: float = 0.0
    max_manpower: float = 0.0
    regiments: int = 0
    army_tradition: float = 0.0
    navy_tradition: float = 0.0
    advances: int = 0
    institutions: int = 0
    stability: float = 0.0
    prestige: float = 0.0
    great_power_rank: int = 0
    produced_goods: dict = field(default_factory=dict)
    total_produced: float = 0.0


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
    for match in re.finditer(r'(\w+)=([\d.-]+)', block):
        k = match.group(1)
        v = match.group(2)
        try:
            result[k] = float(v) if '.' in v else int(v)
        except ValueError:
            pass
    return result


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

        return ''.join(lines) if lines else None


def parse_country(text: str, tag: str) -> CountryData:
    data = CountryData(tag=tag, name=PLAYER_COUNTRIES.get(tag, tag))

    # Color from save
    color_match = re.search(r'color=rgb\s*\{\s*(\d+)\s+(\d+)\s+(\d+)\s*\}', text)
    if color_match:
        data.color = (int(color_match.group(1)), int(color_match.group(2)), int(color_match.group(3)))

    # Rank - use great_power_rank field
    data.great_power_rank = extract_value(text, r'great_power_rank=(\d+)', int, 0)

    # Currency
    currency = extract_block(text, 'currency_data')
    data.treasury = extract_value(currency, r'gold=([\d.-]+)', float, 0.0)
    data.stability = extract_value(currency, r'stability=([\d.-]+)', float, 0.0)
    data.prestige = extract_value(currency, r'prestige=([\d.-]+)', float, 0.0)
    data.army_tradition = extract_value(currency, r'army_tradition=([\d.]+)', float, 0.0)
    data.navy_tradition = extract_value(currency, r'navy_tradition=([\d.]+)', float, 0.0)
    data.manpower = extract_value(currency, r'manpower=([\d.]+)', float, 0.0)

    # Economy
    data.monthly_income = extract_value(text, r'estimated_monthly_income=([\d.]+)', float, 0.0)
    data.tax_base = extract_value(text, r'current_tax_base=([\d.]+)', float, 0.0)
    data.population = extract_value(text, r'last_months_population=([\d.]+)', float, 0.0)
    data.max_manpower = extract_value(text, r'max_manpower=([\d.]+)', float, 0.0)

    # Military
    subunits_match = re.search(r'owned_subunits=\{([^}]+)\}', text)
    data.regiments = len(subunits_match.group(1).split()) if subunits_match else 0

    # Production
    data.total_produced = extract_value(text, r'total_produced=([\d.]+)', float, 0.0)
    data.produced_goods = extract_dict(text, 'last_month_produced')

    # Tech
    advances = extract_dict(text, 'researched_advances')
    data.advances = sum(1 for v in advances.values() if v == True or v == 1)
    institutions = extract_dict(text, 'institutions')
    data.institutions = sum(1 for v in institutions.values() if v == True or v == 1)

    return data


def rgb_to_mpl(color_tuple):
    """Convert RGB 0-255 to matplotlib 0-1 format."""
    return (color_tuple[0] / 255, color_tuple[1] / 255, color_tuple[2] / 255)


def create_production_treemap(countries: list[CountryData], output_dir: Path):
    """Create treemap of goods production by country."""
    if not HAS_SQUARIFY:
        print("Skipping treemap (squarify not installed)")
        return

    # Aggregate production by goods across all countries
    goods_by_country = {}
    for c in countries:
        if c.total_produced > 0:
            goods_by_country[c.tag] = {
                'total': c.total_produced,
                'color': rgb_to_mpl(c.color),
                'goods': c.produced_goods
            }

    if not goods_by_country:
        return

    # Sort by total production
    sorted_countries = sorted(goods_by_country.items(), key=lambda x: x[1]['total'], reverse=True)

    fig, ax = plt.subplots(figsize=(14, 10))

    labels = [f"{tag}\n{data['total']:.0f}" for tag, data in sorted_countries]
    sizes = [data['total'] for _, data in sorted_countries]
    colors = [data['color'] for _, data in sorted_countries]

    squarify.plot(sizes=sizes, label=labels, color=colors, alpha=0.8, ax=ax,
                  text_kwargs={'fontsize': 10, 'fontweight': 'bold'})

    ax.set_title('Total Production by Country', fontsize=14, fontweight='bold')
    ax.axis('off')

    plt.tight_layout()
    plt.savefig(output_dir / 'treemap_production.png', dpi=150)
    plt.close()
    print(f"  Saved: treemap_production.png")


def create_goods_breakdown_chart(countries: list[CountryData], output_dir: Path):
    """Create stacked bar chart of goods production by category."""
    # Aggregate goods by category for each country
    country_categories = {}

    for c in countries:
        if not c.produced_goods:
            continue
        cat_totals = {cat: 0 for cat in GOODS_CATEGORIES}
        for good, amount in c.produced_goods.items():
            categorized = False
            for cat, goods_list in GOODS_CATEGORIES.items():
                if good in goods_list:
                    cat_totals[cat] += amount
                    categorized = True
                    break
            if not categorized:
                cat_totals['Other'] += amount
        country_categories[c.tag] = {'totals': cat_totals, 'color': c.color}

    if not country_categories:
        return

    # Sort by total production
    sorted_tags = sorted(country_categories.keys(),
                         key=lambda t: sum(country_categories[t]['totals'].values()),
                         reverse=True)

    # Filter to top producers
    sorted_tags = [t for t in sorted_tags if sum(country_categories[t]['totals'].values()) > 100]

    if not sorted_tags:
        return

    fig, ax = plt.subplots(figsize=(14, 8))

    categories = list(GOODS_CATEGORIES.keys())
    x = np.arange(len(sorted_tags))
    width = 0.8

    # Color palette for categories
    cat_colors = plt.cm.Set3(np.linspace(0, 1, len(categories)))

    bottom = np.zeros(len(sorted_tags))
    for i, cat in enumerate(categories):
        values = [country_categories[t]['totals'].get(cat, 0) for t in sorted_tags]
        ax.bar(x, values, width, label=cat, bottom=bottom, color=cat_colors[i])
        bottom += values

    ax.set_xlabel('Country')
    ax.set_ylabel('Production')
    ax.set_title('Goods Production by Category', fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(sorted_tags)
    ax.legend(loc='upper right', fontsize=8)

    plt.tight_layout()
    plt.savefig(output_dir / 'chart_goods_breakdown.png', dpi=150)
    plt.close()
    print(f"  Saved: chart_goods_breakdown.png")


def create_military_comparison(countries: list[CountryData], output_dir: Path):
    """Create military power comparison chart."""
    # Filter to countries with military
    military_countries = [c for c in countries if c.regiments > 0 or c.max_manpower > 0]
    military_countries.sort(key=lambda c: c.regiments, reverse=True)

    if not military_countries:
        return

    fig, axes = plt.subplots(1, 3, figsize=(15, 6))

    # 1. Regiments bar chart
    ax1 = axes[0]
    tags = [c.tag for c in military_countries]
    regiments = [c.regiments for c in military_countries]
    colors = [rgb_to_mpl(c.color) for c in military_countries]
    ax1.barh(tags, regiments, color=colors)
    ax1.set_xlabel('Regiments')
    ax1.set_title('Army Size (Regiments)')
    ax1.invert_yaxis()

    # 2. Manpower comparison
    ax2 = axes[1]
    manpower = [c.manpower for c in military_countries]
    max_mp = [c.max_manpower for c in military_countries]
    y = np.arange(len(tags))
    ax2.barh(y - 0.2, manpower, 0.4, label='Current', color='steelblue')
    ax2.barh(y + 0.2, max_mp, 0.4, label='Maximum', color='lightsteelblue')
    ax2.set_yticks(y)
    ax2.set_yticklabels(tags)
    ax2.set_xlabel('Manpower (thousands)')
    ax2.set_title('Manpower')
    ax2.legend()
    ax2.invert_yaxis()

    # 3. Traditions
    ax3 = axes[2]
    army_trad = [c.army_tradition for c in military_countries]
    navy_trad = [c.navy_tradition for c in military_countries]
    ax3.barh(y - 0.2, army_trad, 0.4, label='Army', color='darkred')
    ax3.barh(y + 0.2, navy_trad, 0.4, label='Navy', color='darkblue')
    ax3.set_yticks(y)
    ax3.set_yticklabels(tags)
    ax3.set_xlabel('Tradition')
    ax3.set_title('Military Traditions')
    ax3.legend()
    ax3.invert_yaxis()

    plt.suptitle('Military Power Comparison', fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(output_dir / 'chart_military.png', dpi=150)
    plt.close()
    print(f"  Saved: chart_military.png")


def create_radar_chart(countries: list[CountryData], output_dir: Path):
    """Create radar/spider chart comparing countries across dimensions."""
    # Filter to major countries
    major = [c for c in countries if c.great_power_rank > 0 and c.great_power_rank <= 50]
    major.sort(key=lambda c: c.great_power_rank)

    if len(major) < 2:
        return

    # Dimensions to compare (normalize to 0-100)
    dimensions = ['Population', 'Income', 'Military', 'Tech', 'Stability', 'Prestige']

    # Get max values for normalization
    max_pop = max(c.population for c in major) or 1
    max_income = max(c.monthly_income for c in major) or 1
    max_mil = max(c.regiments for c in major) or 1
    max_tech = max(c.advances for c in major) or 1
    max_stab = 100
    max_pres = max(abs(c.prestige) for c in major) or 1

    fig, ax = plt.subplots(figsize=(10, 10), subplot_kw=dict(projection='polar'))

    angles = np.linspace(0, 2 * np.pi, len(dimensions), endpoint=False).tolist()
    angles += angles[:1]  # Close the polygon

    for c in major[:6]:  # Limit to top 6
        values = [
            (c.population / max_pop) * 100,
            (c.monthly_income / max_income) * 100,
            (c.regiments / max_mil) * 100,
            (c.advances / max_tech) * 100,
            max(0, (c.stability + 100) / 2),  # Normalize -100 to 100 -> 0 to 100
            max(0, (c.prestige / max_pres) * 100) if c.prestige > 0 else 0,
        ]
        values += values[:1]

        color = rgb_to_mpl(c.color)
        ax.plot(angles, values, 'o-', linewidth=2, label=c.tag, color=color)
        ax.fill(angles, values, alpha=0.15, color=color)

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(dimensions)
    ax.set_ylim(0, 100)
    ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.0))
    ax.set_title('Country Comparison (Normalized)', fontsize=14, fontweight='bold', y=1.08)

    plt.tight_layout()
    plt.savefig(output_dir / 'chart_radar.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  Saved: chart_radar.png")


def create_economy_chart(countries: list[CountryData], output_dir: Path):
    """Create economy comparison chart."""
    # Sort by income
    sorted_countries = sorted(countries, key=lambda c: c.monthly_income, reverse=True)
    sorted_countries = [c for c in sorted_countries if c.monthly_income > 0]

    if not sorted_countries:
        return

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    # 1. Income vs Tax Base scatter
    ax1 = axes[0]
    for c in sorted_countries:
        color = rgb_to_mpl(c.color)
        ax1.scatter(c.tax_base, c.monthly_income, s=c.population / 20, c=[color],
                    alpha=0.7, edgecolors='black', linewidths=0.5)
        ax1.annotate(c.tag, (c.tax_base, c.monthly_income), fontsize=8,
                     xytext=(5, 5), textcoords='offset points')
    ax1.set_xlabel('Tax Base')
    ax1.set_ylabel('Monthly Income')
    ax1.set_title('Income vs Tax Base (bubble size = population)')

    # 2. Treasury bar chart
    ax2 = axes[1]
    tags = [c.tag for c in sorted_countries]
    treasury = [c.treasury for c in sorted_countries]
    colors = [rgb_to_mpl(c.color) for c in sorted_countries]
    ax2.barh(tags, treasury, color=colors)
    ax2.set_xlabel('Treasury (Gold)')
    ax2.set_title('Treasury')
    ax2.invert_yaxis()

    plt.suptitle('Economy Comparison', fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(output_dir / 'chart_economy.png', dpi=150)
    plt.close()
    print(f"  Saved: chart_economy.png")


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Generate EU5 charts and treemaps')
    parser.add_argument('-o', '--output', help='Output directory')
    args = parser.parse_args()

    base_dir = Path(__file__).parent.resolve()
    save_dir = base_dir / "save"
    save_files = list(save_dir.glob("*.eu5"))

    if not save_files:
        print("No .eu5 save files found")
        sys.exit(1)

    save_file = save_files[0]

    # Output directory
    if args.output:
        output_dir = Path(args.output)
    else:
        output_dir = base_dir / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Analyzing: {save_file.name}")
    print(f"Output: {output_dir}")

    # Parse all player countries
    countries = []
    for tag in PLAYER_COUNTRIES:
        print(f"  Parsing {tag}...", end=" ", flush=True)
        country_text = find_country_in_file(str(save_file), tag)
        if country_text:
            data = parse_country(country_text, tag)
            countries.append(data)
            print("OK")
        else:
            print("NOT FOUND")

    if not countries:
        print("No countries found!")
        return

    print("\nGenerating charts...")

    # Create all charts
    create_production_treemap(countries, output_dir)
    create_goods_breakdown_chart(countries, output_dir)
    create_military_comparison(countries, output_dir)
    create_economy_chart(countries, output_dir)

    print("\nDone!")


if __name__ == '__main__':
    main()
