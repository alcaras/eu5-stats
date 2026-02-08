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


def load_human_countries() -> list[list[str]]:
    """Load human-controlled countries from HUMANS.txt.

    Each line can contain multiple tags (space-separated) representing
    the same player's tag history (e.g., "POL PLC" for Poland -> Commonwealth).
    Returns a list of tag-lists, where each inner list is one player's tags.
    """
    humans_file = SCRIPT_DIR / "HUMANS.txt"
    players = []
    if humans_file.exists():
        with open(humans_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    # Split by whitespace to get all tags for this player
                    tags = line.split()
                    if tags:
                        players.append(tags)
    return players


def get_player_tag_in_file(filepath: str, player_tags: list[str]) -> str | None:
    """Find which tag from a player's tag list exists in the save file.

    Tries tags in reverse order (most recent formation first).
    Returns the found tag or None.
    """
    for tag in reversed(player_tags):
        # Quick check if tag exists in file
        country_text = find_country_in_file(filepath, tag)
        if country_text:
            return tag
    return None


# Load player countries from config file
# PLAYER_TAGS is a list of tag-lists (one per player)
PLAYER_TAGS = load_human_countries()

# For backwards compatibility, also create flat dict of all tags
PLAYER_COUNTRIES = {}
for tags in PLAYER_TAGS:
    for tag in tags:
        PLAYER_COUNTRIES[tag] = tag

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
    ruler_age: int = 0
    ruler_birth_date: str = ""

    # Regency
    is_regency: bool = False
    regent_id: int = 0
    regent_name: str = ""
    regent_adm: int = 0
    regent_dip: int = 0
    regent_mil: int = 0
    regent_age: int = 0

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
    research_progress: float = 0.0  # Current progress toward next advance

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

    # Subjects
    subjects: list = field(default_factory=list)  # List of subject tags
    subject_data: list = field(default_factory=list)  # List of CountryStats for subjects
    total_population: float = 0.0  # Self + subjects
    total_tax_base: float = 0.0  # Self + subjects
    total_regiments: int = 0  # Self + subjects
    total_manpower: float = 0.0  # Self + subjects


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


def calculate_age(birth_date: str, current_date: str) -> int:
    """Calculate age from birth_date and current_date (both YYYY.M.D format)."""
    try:
        birth_parts = birth_date.split('.')
        current_parts = current_date.split('.')
        if len(birth_parts) >= 3 and len(current_parts) >= 3:
            birth_year = int(birth_parts[0])
            birth_month = int(birth_parts[1])
            current_year = int(current_parts[0])
            current_month = int(current_parts[1])
            age = current_year - birth_year
            if current_month < birth_month:
                age -= 1
            return max(0, age)
    except (ValueError, IndexError):
        pass
    return 0


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
                'birth_date': extract_value(text, r'birth_date=(\d+\.\d+\.\d+)', str, ""),
                'traits': traits,
            }
    return None


def find_regent_for_country(filepath: str, country_id: int) -> dict | None:
    """Find a character who is regent for the given country ID.

    Searches character_db for alive_data.regent_of containing the country_id.
    Returns character info dict or None.
    """
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        in_char_db = False
        in_database = False
        current_char_id = None
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

            # Look for character block starts
            stripped = line.strip()
            if not collecting:
                match = re.match(r'^(\d+)=\{', stripped)
                if match:
                    current_char_id = int(match.group(1))
                    collecting = True
                    lines = [line]
                    depth = line.count('{') - line.count('}')
            else:
                lines.append(line)
                depth += line.count('{') - line.count('}')
                if depth <= 0:
                    # End of character block - check if this is our regent
                    text = ''.join(lines)
                    # Look for regent_of containing our country_id
                    regent_match = re.search(r'regent_of=\{\s*(\d+)', text)
                    if regent_match and int(regent_match.group(1)) == country_id:
                        # Found the regent!
                        traits_match = re.search(r'traits=\{\s*([^}]+)\}', text)
                        traits = traits_match.group(1).split() if traits_match else []
                        return {
                            'char_id': current_char_id,
                            'adm': extract_value(text, r'adm=(\d+)', int, 0),
                            'dip': extract_value(text, r'dip=(\d+)', int, 0),
                            'mil': extract_value(text, r'mil=(\d+)', int, 0),
                            'first_name': extract_value(text, r'first_name="([^"]+)"', str, ""),
                            'birth_date': extract_value(text, r'birth_date=(\d+\.\d+\.\d+)', str, ""),
                            'traits': traits,
                        }
                    # Reset for next character
                    collecting = False
                    lines = []

            # Stop at end of character_db
            if stripped == '}' and in_database and not collecting:
                break

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
    # Check for regency - if there's an active_regent, use that for display
    active_regent_id = extract_value(govt_block, r'active_regent=(\d+)', int, 0)
    if active_regent_id:
        stats.is_regency = True
        stats.regent_id = active_regent_id
        # During regency, the heir might be in heir= field
        if not stats.ruler_id:
            stats.ruler_id = extract_value(govt_block, r'heir=(\d+)', int, 0)

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

    # Research progress - extract from current_research block
    research_block = extract_block(text, 'current_research')
    if research_block:
        stats.research_progress = extract_value(research_block, r'progress=([\d.]+)', float, 0.0)

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


def extract_country_tags(filepath: str) -> dict[int, str]:
    """Extract country ID -> tag mapping from countries.tags section."""
    tags = {}
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        in_countries = False
        in_tags = False
        for line in f:
            if not in_countries:
                if line.strip().startswith('countries='):
                    in_countries = True
                continue
            if not in_tags:
                if line.strip().startswith('tags='):
                    in_tags = True
                continue
            # Parse tag entries: ID=TAG
            stripped = line.strip()
            if stripped == '}':
                break
            match = re.match(r'(\d+)=(\w+)', stripped)
            if match:
                tags[int(match.group(1))] = match.group(2)
    return tags


def extract_location_control(filepath: str) -> dict[int, list[float]]:
    """Extract control values per owner ID from locations section.

    Returns dict mapping owner_id -> list of control values (0-1 scale).
    Locations without explicit control field have 0 control.
    """
    owner_controls = {}
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        in_locations = False
        in_inner_locations = False
        in_location_block = False
        current_owner = None
        current_control = None
        block_depth = 0

        for line in f:
            stripped = line.strip()

            # Find outer locations={ (at start of line, no indent)
            if not in_locations:
                if line.startswith('locations={'):
                    in_locations = True
                continue

            # Find inner locations={ (indented)
            if not in_inner_locations:
                if stripped == 'locations={':
                    in_inner_locations = True
                continue

            # Track block depth and detect location blocks (e.g., "123={")
            if re.match(r'\d+={', stripped):
                in_location_block = True
                block_depth = 1
                current_owner = None
                current_control = None
                continue

            if in_location_block:
                block_depth += stripped.count('{') - stripped.count('}')

                # Track current location's owner
                if stripped.startswith('owner='):
                    try:
                        current_owner = int(stripped.split('=')[1])
                    except ValueError:
                        current_owner = None

                # Track control value
                if stripped.startswith('control='):
                    try:
                        current_control = float(stripped.split('=')[1])
                    except ValueError:
                        current_control = 0.0

                # End of location block
                if block_depth <= 0:
                    if current_owner is not None:
                        control_val = current_control if current_control is not None else 0.0
                        if current_owner not in owner_controls:
                            owner_controls[current_owner] = []
                        owner_controls[current_owner].append(control_val)
                    in_location_block = False
                    current_owner = None
                    current_control = None

            # Stop at end of outer locations section (unindented closing brace)
            if line.startswith('}') and in_inner_locations:
                break

    return owner_controls


def calculate_average_control(filepath: str, player_tags: list[str]) -> dict[str, float]:
    """Calculate average control for each player country.

    Returns dict mapping tag -> average control (0-100 scale).
    """
    # Get ID -> tag mapping
    id_to_tag = extract_country_tags(filepath)
    tag_to_id = {v: k for k, v in id_to_tag.items()}

    # Get control data per owner ID
    owner_controls = extract_location_control(filepath)

    # Calculate average for each player tag
    result = {}
    for tag in player_tags:
        owner_id = tag_to_id.get(tag)
        if owner_id is not None and owner_id in owner_controls:
            controls = owner_controls[owner_id]
            avg = sum(controls) / len(controls) if controls else 0.0
            result[tag] = avg * 100  # Convert to 0-100 scale
        else:
            result[tag] = 0.0

    return result


def extract_dependencies(filepath: str) -> dict[int, list[tuple[int, str]]]:
    """Extract all subject/dependency relationships from diplomacy_manager.

    Returns dict mapping overlord_id -> [(subject_id, subject_type), ...]
    """
    dependencies = {}
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        in_diplomacy = False
        in_dependency = False
        current_first = None
        current_second = None
        current_type = None

        for line in f:
            stripped = line.strip()

            # Find diplomacy_manager section
            if not in_diplomacy:
                if line.startswith('diplomacy_manager={'):
                    in_diplomacy = True
                continue

            # Look for dependency blocks
            if stripped == 'dependency={':
                in_dependency = True
                current_first = None
                current_second = None
                current_type = None
                continue

            if in_dependency:
                if stripped.startswith('first='):
                    try:
                        current_first = int(stripped.split('=')[1])
                    except ValueError:
                        pass
                elif stripped.startswith('second='):
                    try:
                        current_second = int(stripped.split('=')[1])
                    except ValueError:
                        pass
                elif stripped.startswith('subject_type='):
                    current_type = stripped.split('=')[1]

                # End of dependency block
                if stripped == '}':
                    if current_first is not None and current_second is not None and current_type:
                        if current_first not in dependencies:
                            dependencies[current_first] = []
                        dependencies[current_first].append((current_second, current_type))
                    in_dependency = False

            # Stop at end of diplomacy_manager section
            if line.startswith('}') and in_diplomacy and not in_dependency:
                break

    return dependencies


def get_subjects_for_countries(filepath: str, player_tags: list[str]) -> dict[str, list[str]]:
    """Get all subject country tags for each player country.

    Returns dict mapping player_tag -> [subject_tag, ...]
    """
    id_to_tag = extract_country_tags(filepath)
    tag_to_id = {v: k for k, v in id_to_tag.items()}

    dependencies = extract_dependencies(filepath)

    result = {}
    for tag in player_tags:
        overlord_id = tag_to_id.get(tag)
        if overlord_id is not None and overlord_id in dependencies:
            subject_tags = []
            for subject_id, subject_type in dependencies[overlord_id]:
                subject_tag = id_to_tag.get(subject_id)
                if subject_tag:
                    subject_tags.append(subject_tag)
            result[tag] = subject_tags
        else:
            result[tag] = []

    return result


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
    lines.append(f"{'Tag':<5}{'A':<4}{'D':<4}{'M':<4}{'Tot':<5}{'Age':<5}{'Name':<15}")
    lines.append("-" * W)

    # For sorting, use regent stats if no ruler
    def get_effective_stats(c):
        if c.ruler_adm or c.ruler_dip or c.ruler_mil:
            return c.ruler_adm + c.ruler_dip + c.ruler_mil
        return c.regent_adm + c.regent_dip + c.regent_mil

    by_ruler = sorted(countries, key=get_effective_stats, reverse=True)
    for c in by_ruler:
        # Use regent stats if no ruler (pure regency with no heir data)
        if c.ruler_adm or c.ruler_dip or c.ruler_mil or c.ruler_name:
            adm, dip, mil = c.ruler_adm, c.ruler_dip, c.ruler_mil
            age_str = str(c.ruler_age) if c.ruler_age > 0 else "?"
            name_str = c.ruler_name[:14]
            if c.is_regency:
                name_str += " [R]"
        else:
            # No ruler data - show regent
            adm, dip, mil = c.regent_adm, c.regent_dip, c.regent_mil
            age_str = str(c.regent_age) if c.regent_age > 0 else "?"
            name_str = (c.regent_name[:11] + " [Reg]") if c.regent_name else "?"
        total = adm + dip + mil
        lines.append(f"{c.tag:<5}{adm:<4}{dip:<4}{mil:<4}{total:<5}{age_str:<5}{name_str:<15}")

    # Show traits on separate lines
    lines.append("")
    lines.append("Ruler Traits:")
    for c in by_ruler:
        if c.ruler_traits:
            traits_str = ", ".join(c.ruler_traits[:4])
            if len(c.ruler_traits) > 4:
                traits_str += f" (+{len(c.ruler_traits)-4})"
            lines.append(f"  {c.tag}: {traits_str}")

    # Show regencies separately if any
    regencies = [c for c in countries if c.is_regency]
    if regencies:
        lines.append("")
        lines.append("Regencies:")
        for c in regencies:
            regent_age_str = str(c.regent_age) if c.regent_age > 0 else "?"
            lines.append(f"  {c.tag}: Regent {c.regent_name} ({c.regent_adm}/{c.regent_dip}/{c.regent_mil}, age {regent_age_str})")
            if c.ruler_name:
                heir_age_str = str(c.ruler_age) if c.ruler_age > 0 else "?"
                lines.append(f"       Heir {c.ruler_name} ({c.ruler_adm}/{c.ruler_dip}/{c.ruler_mil}, age {heir_age_str})")
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

    # === CONTROL ===
    lines.append("=" * W)
    lines.append("CONTROL (avg across all locations)")
    lines.append("-" * W)
    lines.append(f"{'Tag':<5}{'Control':<10}{'Provs':<7}")
    lines.append("-" * W)

    by_control = sorted(countries, key=lambda c: c.average_control, reverse=True)
    for c in by_control:
        lines.append(f"{c.tag:<5}{c.average_control:<10.1f}{c.num_provinces:<7}")
    lines.append("")

    # === SUBJECTS ===
    # Only show if any country has subjects
    has_subjects = any(len(c.subjects) > 0 for c in countries)
    if has_subjects:
        lines.append("=" * W)
        lines.append("SUBJECTS (with combined totals)")
        lines.append("-" * W)
        lines.append(f"{'Tag':<5}{'#':<3}{'Subjects':<20}{'TotPop':<9}{'TotTax':<9}")
        lines.append("-" * W)

        by_subjects = sorted(countries, key=lambda c: len(c.subjects), reverse=True)
        for c in by_subjects:
            if c.subjects:
                subj_str = ",".join(c.subjects[:4])
                if len(c.subjects) > 4:
                    subj_str += "..."
                lines.append(f"{c.tag:<5}{len(c.subjects):<3}{subj_str:<20}{fmt_pop(c.total_population):<9}{fmt_num(c.total_tax_base):<9}")
            else:
                lines.append(f"{c.tag:<5}{0:<3}{'-':<20}{fmt_pop(c.population):<9}{fmt_num(c.current_tax_base):<9}")
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
        age_str = f", age {c.ruler_age}" if c.ruler_age > 0 else ""
        if c.is_regency:
            lines.append(f"REGENCY - Heir: {c.ruler_name} ({c.ruler_adm}/{c.ruler_dip}/{c.ruler_mil}{age_str})")
            regent_age_str = f", age {c.regent_age}" if c.regent_age > 0 else ""
            lines.append(f"          Regent: {c.regent_name} ({c.regent_adm}/{c.regent_dip}/{c.regent_mil}{regent_age_str})")
        else:
            lines.append(f"Ruler: {c.ruler_name} ({c.ruler_adm}/{c.ruler_dip}/{c.ruler_mil}{age_str})")
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


def generate_comparison_report(current: list[CountryStats], previous: list[CountryStats],
                                current_date: str, previous_date: str,
                                player_matches: list[tuple[str, str]] = None) -> str:
    """Generate a comparison report showing deltas between two saves.

    Args:
        current: List of country stats from current save
        previous: List of country stats from previous save
        current_date: Date string from current save
        previous_date: Date string from previous save
        player_matches: Optional list of (current_tag, previous_tag) tuples for
                       players who changed tags (e.g., POL -> PLC)
    """
    lines = []
    W = 55

    # Build lookup by tag
    prev_lookup = {c.tag: c for c in previous}
    curr_lookup = {c.tag: c for c in current}

    # Build list of (current_stats, previous_stats) pairs
    countries_to_compare = []

    # First, handle explicit player matches (for tag changes)
    matched_curr_tags = set()
    matched_prev_tags = set()
    if player_matches:
        for curr_tag, prev_tag in player_matches:
            if curr_tag in curr_lookup and prev_tag in prev_lookup:
                countries_to_compare.append((curr_lookup[curr_tag], prev_lookup[prev_tag]))
                matched_curr_tags.add(curr_tag)
                matched_prev_tags.add(prev_tag)

    # Then, match remaining countries by same tag
    for tag in curr_lookup:
        if tag not in matched_curr_tags and tag in prev_lookup and tag not in matched_prev_tags:
            countries_to_compare.append((curr_lookup[tag], prev_lookup[tag]))

    if not countries_to_compare:
        return "No common countries to compare."

    # Sort by current GP rank
    countries_to_compare.sort(key=lambda x: x[0].great_power_rank if x[0].great_power_rank > 0 else 9999)

    lines.append("=" * W)
    lines.append("SESSION COMPARISON REPORT")
    lines.append("=" * W)
    lines.append(f"Previous: {previous_date}")
    lines.append(f"Current:  {current_date}")
    lines.append(f"Players:  {len(countries_to_compare)}")

    # Show any tag changes
    tag_changes = [(curr.tag, prev.tag) for curr, prev in countries_to_compare if curr.tag != prev.tag]
    if tag_changes:
        lines.append("")
        lines.append("Tag changes:")
        for new_tag, old_tag in tag_changes:
            lines.append(f"  {old_tag} → {new_tag}")
    lines.append("")

    def fmt_tag(curr_tag: str, prev_tag: str) -> str:
        """Format tag, showing old tag if different."""
        if curr_tag != prev_tag:
            return f"{curr_tag}←{prev_tag}"
        return curr_tag

    def fmt_delta(val: float, precision: int = 0) -> str:
        """Format a delta value with + or - prefix."""
        if precision == 0:
            return f"+{val:.0f}" if val >= 0 else f"{val:.0f}"
        return f"+{val:.{precision}f}" if val >= 0 else f"{val:.{precision}f}"

    def fmt_pop_delta(val: float) -> str:
        """Format population delta (in thousands -> display as K or M)."""
        if abs(val) >= 1000:
            return f"+{val/1000:.2f}M" if val >= 0 else f"{val/1000:.2f}M"
        return f"+{val:.1f}K" if val >= 0 else f"{val:.1f}K"

    # === GREAT POWER RANK CHANGES ===
    lines.append("=" * W)
    lines.append("GREAT POWER RANK CHANGES")
    lines.append("-" * W)

    rank_changes = []
    for curr, prev in countries_to_compare:
        if prev.great_power_rank > 0 and curr.great_power_rank > 0:
            change = prev.great_power_rank - curr.great_power_rank  # Positive = improved
            rank_changes.append((curr.tag, prev.great_power_rank, curr.great_power_rank, change))

    rank_changes.sort(key=lambda x: -x[3])  # Best improvement first
    for tag, old_rank, new_rank, change in rank_changes:
        if change > 0:
            symbol = f"↑{change}"
        elif change < 0:
            symbol = f"↓{-change}"
        else:
            symbol = "="
        lines.append(f"  {tag:<5} #{old_rank} → #{new_rank}  ({symbol})")
    lines.append("")

    # === POPULATION CHANGES ===
    lines.append("=" * W)
    lines.append("POPULATION GROWTH")
    lines.append("-" * W)
    lines.append(f"{'Tag':<5}{'Previous':<10}{'Current':<10}{'Delta':<10}{'%':<8}")
    lines.append("-" * W)

    pop_changes = []
    for curr, prev in countries_to_compare:
        delta = curr.population - prev.population
        pct = (delta / prev.population * 100) if prev.population > 0 else 0
        pop_changes.append((curr.tag, prev.population, curr.population, delta, pct))

    pop_changes.sort(key=lambda x: -x[4])  # Best % growth first
    for tag, old_pop, new_pop, delta, pct in pop_changes:
        lines.append(f"{tag:<5}{fmt_pop(old_pop):<10}{fmt_pop(new_pop):<10}{fmt_pop_delta(delta):<10}{fmt_delta(pct, 1)}%")
    lines.append("")

    # === TAX BASE CHANGES ===
    lines.append("=" * W)
    lines.append("TAX BASE GROWTH")
    lines.append("-" * W)
    lines.append(f"{'Tag':<5}{'Previous':<10}{'Current':<10}{'Delta':<10}{'%':<8}")
    lines.append("-" * W)

    tax_changes = []
    for curr, prev in countries_to_compare:
        delta = curr.current_tax_base - prev.current_tax_base
        pct = (delta / prev.current_tax_base * 100) if prev.current_tax_base > 0 else 0
        tax_changes.append((curr.tag, prev.current_tax_base, curr.current_tax_base, delta, pct))

    tax_changes.sort(key=lambda x: -x[4])  # Best % growth first
    for tag, old_tax, new_tax, delta, pct in tax_changes:
        lines.append(f"{tag:<5}{fmt_num(old_tax):<10}{fmt_num(new_tax):<10}{fmt_delta(delta):<10}{fmt_delta(pct, 1)}%")
    lines.append("")

    # === INCOME CHANGES ===
    lines.append("=" * W)
    lines.append("MONTHLY INCOME CHANGES")
    lines.append("-" * W)
    lines.append(f"{'Tag':<5}{'Previous':<10}{'Current':<10}{'Delta':<10}{'%':<8}")
    lines.append("-" * W)

    income_changes = []
    for curr, prev in countries_to_compare:
        delta = curr.monthly_income - prev.monthly_income
        pct = (delta / prev.monthly_income * 100) if prev.monthly_income > 0 else 0
        income_changes.append((curr.tag, prev.monthly_income, curr.monthly_income, delta, pct))

    income_changes.sort(key=lambda x: -x[4])
    for tag, old_inc, new_inc, delta, pct in income_changes:
        lines.append(f"{tag:<5}{fmt_num(old_inc):<10}{fmt_num(new_inc):<10}{fmt_delta(delta):<10}{fmt_delta(pct, 1)}%")
    lines.append("")

    # === TREASURY CHANGES ===
    lines.append("=" * W)
    lines.append("TREASURY CHANGES")
    lines.append("-" * W)
    lines.append(f"{'Tag':<5}{'Previous':<10}{'Current':<10}{'Delta':<12}")
    lines.append("-" * W)

    treasury_changes = []
    for curr, prev in countries_to_compare:
        delta = curr.gold - prev.gold
        treasury_changes.append((curr.tag, prev.gold, curr.gold, delta))

    treasury_changes.sort(key=lambda x: -x[3])
    for tag, old_gold, new_gold, delta in treasury_changes:
        lines.append(f"{tag:<5}{fmt_num(old_gold):<10}{fmt_num(new_gold):<10}{fmt_delta(delta)}")
    lines.append("")

    # === MILITARY CHANGES ===
    lines.append("=" * W)
    lines.append("MILITARY CHANGES (Regiments)")
    lines.append("-" * W)
    lines.append(f"{'Tag':<5}{'Previous':<10}{'Current':<10}{'Delta':<10}")
    lines.append("-" * W)

    mil_changes = []
    for curr, prev in countries_to_compare:
        delta = curr.num_subunits - prev.num_subunits
        mil_changes.append((curr.tag, prev.num_subunits, curr.num_subunits, delta))

    mil_changes.sort(key=lambda x: -x[3])
    for tag, old_mil, new_mil, delta in mil_changes:
        lines.append(f"{tag:<5}{old_mil:<10}{new_mil:<10}{fmt_delta(delta)}")
    lines.append("")

    # === MANPOWER CHANGES ===
    lines.append("=" * W)
    lines.append("MAX MANPOWER CHANGES")
    lines.append("-" * W)
    lines.append(f"{'Tag':<5}{'Previous':<10}{'Current':<10}{'Delta':<10}{'%':<8}")
    lines.append("-" * W)

    mp_changes = []
    for curr, prev in countries_to_compare:
        delta = curr.max_manpower - prev.max_manpower
        pct = (delta / prev.max_manpower * 100) if prev.max_manpower > 0 else 0
        mp_changes.append((curr.tag, prev.max_manpower, curr.max_manpower, delta, pct))

    mp_changes.sort(key=lambda x: -x[4])
    for tag, old_mp, new_mp, delta, pct in mp_changes:
        lines.append(f"{tag:<5}{old_mp:<10.1f}{new_mp:<10.1f}{fmt_delta(delta, 1):<10}{fmt_delta(pct, 1)}%")
    lines.append("")

    # === TECHNOLOGY CHANGES ===
    lines.append("=" * W)
    lines.append("TECHNOLOGY ADVANCES GAINED")
    lines.append("-" * W)

    tech_changes = []
    for curr, prev in countries_to_compare:
        delta = curr.num_researched_advances - prev.num_researched_advances
        tech_changes.append((curr.tag, prev.num_researched_advances, curr.num_researched_advances, delta))

    tech_changes.sort(key=lambda x: -x[3])  # Sort by advances gained
    for tag, old_adv, new_adv, delta in tech_changes:
        lines.append(f"  {tag:<5} {old_adv} → {new_adv}  ({fmt_delta(delta)} advances)")
    lines.append("")

    # === PROVINCE CHANGES ===
    lines.append("=" * W)
    lines.append("TERRITORY CHANGES (Provinces)")
    lines.append("-" * W)

    prov_changes = []
    for curr, prev in countries_to_compare:
        delta = curr.num_provinces - prev.num_provinces
        prov_changes.append((curr.tag, prev.num_provinces, curr.num_provinces, delta))

    prov_changes.sort(key=lambda x: -x[3])
    for tag, old_prov, new_prov, delta in prov_changes:
        if delta != 0:
            lines.append(f"  {tag:<5} {old_prov} → {new_prov}  ({fmt_delta(delta)} provinces)")
        else:
            lines.append(f"  {tag:<5} {old_prov} → {new_prov}  (unchanged)")
    lines.append("")

    # === STABILITY/PRESTIGE ===
    lines.append("=" * W)
    lines.append("STABILITY & PRESTIGE")
    lines.append("-" * W)
    lines.append(f"{'Tag':<5}{'Stab Δ':<10}{'Prest Δ':<10}{'ArmyT Δ':<10}{'NavyT Δ':<10}")
    lines.append("-" * W)

    for curr, prev in countries_to_compare:
        stab_d = curr.stability - prev.stability
        pres_d = curr.prestige - prev.prestige
        army_d = curr.army_tradition - prev.army_tradition
        navy_d = curr.navy_tradition - prev.navy_tradition
        lines.append(f"{curr.tag:<5}{fmt_delta(stab_d, 1):<10}{fmt_delta(pres_d, 1):<10}{fmt_delta(army_d, 1):<10}{fmt_delta(navy_d, 1):<10}")
    lines.append("")

    # === SUBJECT CHANGES ===
    # Check if any country has subjects in either save
    has_subjects = any(len(c.subjects) > 0 for c, _ in countries_to_compare) or \
                   any(len(p.subjects) > 0 for _, p in countries_to_compare)
    if has_subjects:
        lines.append("=" * W)
        lines.append("SUBJECT CHANGES")
        lines.append("-" * W)

        for curr, prev in countries_to_compare:
            curr_subjs = set(curr.subjects)
            prev_subjs = set(prev.subjects)
            gained = curr_subjs - prev_subjs
            lost = prev_subjs - curr_subjs

            if gained or lost:
                lines.append(f"{curr.tag}:")
                if gained:
                    lines.append(f"  Gained: {', '.join(gained)}")
                if lost:
                    lines.append(f"  Lost: {', '.join(lost)}")
        lines.append("")

    # === SUMMARY: BIGGEST GAINERS ===
    lines.append("=" * W)
    lines.append("SESSION MVPs")
    lines.append("-" * W)

    # Find leaders in each category
    if pop_changes:
        best_pop = max(pop_changes, key=lambda x: x[4])
        lines.append(f"  Pop Growth:  {best_pop[0]} ({fmt_delta(best_pop[4], 1)}%)")

    if tax_changes:
        best_tax = max(tax_changes, key=lambda x: x[4])
        lines.append(f"  Tax Growth:  {best_tax[0]} ({fmt_delta(best_tax[4], 1)}%)")

    if income_changes:
        best_inc = max(income_changes, key=lambda x: x[4])
        lines.append(f"  Income Growth: {best_inc[0]} ({fmt_delta(best_inc[4], 1)}%)")

    if mil_changes:
        best_mil = max(mil_changes, key=lambda x: x[3])
        lines.append(f"  Military:    {best_mil[0]} ({fmt_delta(best_mil[3])} regiments)")

    if tech_changes:
        best_tech = max(tech_changes, key=lambda x: x[3])
        lines.append(f"  Tech:        {best_tech[0]} ({fmt_delta(best_tech[3])} advances)")

    if prov_changes:
        best_prov = max(prov_changes, key=lambda x: x[3])
        if best_prov[3] > 0:
            lines.append(f"  Expansion:   {best_prov[0]} ({fmt_delta(best_prov[3])} provinces)")

    lines.append("")
    lines.append("=" * W)
    lines.append("END OF COMPARISON REPORT")
    lines.append("=" * W)

    return "\n".join(lines)


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Generate EU5 multiplayer session report')
    parser.add_argument('save_file', nargs='?', help='Save file to analyze (default: most recent in save/)')
    parser.add_argument('-o', '--output', help='Output directory (default: reports/)')
    parser.add_argument('--no-timestamp', action='store_true', help='Don\'t create timestamped subfolder')
    parser.add_argument('--compare', help='Previous save file to compare against')
    args = parser.parse_args()

    # Find save file
    if args.save_file:
        save_file = Path(args.save_file)
    else:
        save_dir = SCRIPT_DIR / "save"
        save_files = sorted(save_dir.glob("*.eu5"), key=lambda f: f.stat().st_mtime, reverse=True)
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
    for player_tags in PLAYER_TAGS:
        # Try each tag in the player's tag list (newest/formed nation first)
        found = False
        for tag in reversed(player_tags):
            print(f"  Parsing {tag}...", file=sys.stderr, end=" ", flush=True)
            country_text = find_country_in_file(str(save_file), tag)

            if country_text:
                stats = parse_country(country_text, tag)

                # Get ruler stats
                if stats.ruler_id:
                    ruler = find_character(str(save_file), stats.ruler_id)
                    if ruler:
                        stats.ruler_adm = int(ruler['adm'])
                        stats.ruler_dip = int(ruler['dip'])
                        stats.ruler_mil = int(ruler['mil'])
                        stats.ruler_name = ruler['first_name'].replace('name_', '').title()
                        stats.ruler_traits = ruler.get('traits', [])
                        stats.ruler_birth_date = ruler.get('birth_date', '')
                        if stats.ruler_birth_date:
                            stats.ruler_age = calculate_age(stats.ruler_birth_date, save_date)

                # Get regent stats if in regency
                if stats.regent_id:
                    regent = find_character(str(save_file), stats.regent_id)
                    if regent:
                        stats.regent_adm = int(regent['adm'])
                        stats.regent_dip = int(regent['dip'])
                        stats.regent_mil = int(regent['mil'])
                        stats.regent_name = regent['first_name'].replace('name_', '').title()
                        if regent.get('birth_date'):
                            stats.regent_age = calculate_age(regent['birth_date'], save_date)

                countries.append(stats)
                print("OK", file=sys.stderr)
                found = True
                break
            else:
                print("not found, ", file=sys.stderr, end="")

        if not found:
            print(f"NOT FOUND (tried: {', '.join(player_tags)})", file=sys.stderr)

    if countries:
        # Calculate control values from locations data
        print("  Calculating control...", file=sys.stderr, end=" ", flush=True)
        control_data = calculate_average_control(str(save_file), [c.tag for c in countries])
        for c in countries:
            c.average_control = control_data.get(c.tag, 0.0)
        print("OK", file=sys.stderr)

        # Extract subject relationships
        print("  Finding subjects...", file=sys.stderr, end=" ", flush=True)
        subjects_map = get_subjects_for_countries(str(save_file), [c.tag for c in countries])

        # Parse subject country data
        all_subject_tags = set()
        for subj_list in subjects_map.values():
            all_subject_tags.update(subj_list)

        subject_stats = {}
        for subj_tag in all_subject_tags:
            subj_text = find_country_in_file(str(save_file), subj_tag)
            if subj_text:
                subject_stats[subj_tag] = parse_country(subj_text, subj_tag)

        # Attach subjects to their overlords and calculate totals
        for c in countries:
            c.subjects = subjects_map.get(c.tag, [])
            c.subject_data = [subject_stats[t] for t in c.subjects if t in subject_stats]

            # Calculate totals (self + subjects)
            c.total_population = c.population + sum(s.population for s in c.subject_data)
            c.total_tax_base = c.current_tax_base + sum(s.current_tax_base for s in c.subject_data)
            c.total_regiments = c.num_subunits + sum(s.num_subunits for s in c.subject_data)
            c.total_manpower = c.max_manpower + sum(s.max_manpower for s in c.subject_data)

        total_subjects = sum(len(c.subjects) for c in countries)
        print(f"OK ({total_subjects} subjects found)", file=sys.stderr)

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

        # Generate comparison report if previous save provided
        if args.compare:
            prev_file = Path(args.compare)
            if prev_file.exists():
                print(f"  Loading previous save for comparison...", file=sys.stderr)
                prev_date = get_save_date(str(prev_file))

                # For each player, find their tag in the previous save
                # This handles tag changes (e.g., POL -> PLC)
                prev_countries = []
                player_matches = []  # List of (current_tag, previous_tag) for tag changes

                for player_tags in PLAYER_TAGS:
                    # Find which tag this player has in previous save
                    prev_tag = None
                    for tag in reversed(player_tags):  # Try newest first
                        country_text = find_country_in_file(str(prev_file), tag)
                        if country_text:
                            prev_tag = tag
                            stats = parse_country(country_text, tag)
                            prev_countries.append(stats)
                            break

                    # Find which tag this player has in current save
                    curr_tag = None
                    for c in countries:
                        if c.tag in player_tags:
                            curr_tag = c.tag
                            break

                    # Record the match if both exist (even if same tag)
                    if curr_tag and prev_tag:
                        player_matches.append((curr_tag, prev_tag))

                if prev_countries:
                    # Get subjects for previous save
                    prev_subjects_map = get_subjects_for_countries(str(prev_file), [c.tag for c in prev_countries])
                    for c in prev_countries:
                        c.subjects = prev_subjects_map.get(c.tag, [])

                    comparison_file = report_dir / "comparison_report.txt"
                    with open(comparison_file, 'w') as f:
                        f.write(generate_comparison_report(countries, prev_countries, save_date, prev_date, player_matches))
                    print(f"Comparison saved to: {comparison_file}", file=sys.stderr)
            else:
                print(f"Warning: Previous save not found: {prev_file}", file=sys.stderr)


if __name__ == '__main__':
    main()
