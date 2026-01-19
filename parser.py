"""
PDX Script Parser for EU5 save files.
Parses the Paradox script format into Python data structures.
"""

import re
from typing import Any, Iterator


class PDXParser:
    """Parser for Paradox script format (used in EU5 melted saves)."""

    def __init__(self, text: str):
        self.text = text
        self.pos = 0
        self.length = len(text)

    def skip_whitespace(self):
        """Skip whitespace and comments."""
        while self.pos < self.length:
            c = self.text[self.pos]
            if c in ' \t\n\r':
                self.pos += 1
            elif c == '#':
                # Skip comment until end of line
                while self.pos < self.length and self.text[self.pos] != '\n':
                    self.pos += 1
            else:
                break

    def peek(self) -> str | None:
        """Peek at the next character."""
        self.skip_whitespace()
        if self.pos >= self.length:
            return None
        return self.text[self.pos]

    def parse_string(self) -> str:
        """Parse a quoted string."""
        assert self.text[self.pos] == '"'
        self.pos += 1
        start = self.pos
        while self.pos < self.length and self.text[self.pos] != '"':
            if self.text[self.pos] == '\\':
                self.pos += 2  # Skip escaped character
            else:
                self.pos += 1
        result = self.text[start:self.pos]
        self.pos += 1  # Skip closing quote
        return result

    def parse_identifier(self) -> str:
        """Parse an identifier or unquoted value."""
        start = self.pos
        while self.pos < self.length:
            c = self.text[self.pos]
            if c in ' \t\n\r={}#':
                break
            self.pos += 1
        return self.text[start:self.pos]

    def parse_value(self) -> Any:
        """Parse a value (string, number, boolean, dict, or list)."""
        self.skip_whitespace()

        if self.pos >= self.length:
            return None

        c = self.text[self.pos]

        if c == '"':
            return self.parse_string()
        elif c == '{':
            return self.parse_block()
        else:
            ident = self.parse_identifier()
            if ident == 'yes':
                return True
            elif ident == 'no':
                return False
            # Try to parse as number
            try:
                if '.' in ident:
                    return float(ident)
                return int(ident)
            except ValueError:
                return ident

    def parse_block(self) -> dict | list:
        """Parse a block (either dict or list)."""
        assert self.text[self.pos] == '{'
        self.pos += 1

        self.skip_whitespace()

        if self.pos >= self.length or self.text[self.pos] == '}':
            self.pos += 1
            return {}

        # Check if this is a list or dict by looking for '='
        is_dict = False
        save_pos = self.pos

        # Scan ahead to determine structure
        depth = 0
        temp_pos = self.pos
        while temp_pos < self.length:
            c = self.text[temp_pos]
            if c == '{':
                depth += 1
            elif c == '}':
                if depth == 0:
                    break
                depth -= 1
            elif c == '=' and depth == 0:
                is_dict = True
                break
            elif c == '"':
                temp_pos += 1
                while temp_pos < self.length and self.text[temp_pos] != '"':
                    if self.text[temp_pos] == '\\':
                        temp_pos += 1
                    temp_pos += 1
            temp_pos += 1

        if is_dict:
            return self.parse_dict_contents()
        else:
            return self.parse_list_contents()

    def parse_dict_contents(self) -> dict:
        """Parse dictionary contents until closing brace."""
        result = {}

        while True:
            self.skip_whitespace()

            if self.pos >= self.length or self.text[self.pos] == '}':
                if self.pos < self.length:
                    self.pos += 1
                break

            # Parse key
            if self.text[self.pos] == '"':
                key = self.parse_string()
            else:
                key = self.parse_identifier()

            self.skip_whitespace()

            # Expect '='
            if self.pos < self.length and self.text[self.pos] == '=':
                self.pos += 1
            else:
                # Might be a standalone value in a mixed block
                continue

            # Parse value
            value = self.parse_value()

            # Handle duplicate keys by making them lists
            if key in result:
                if not isinstance(result[key], list):
                    result[key] = [result[key]]
                result[key].append(value)
            else:
                result[key] = value

        return result

    def parse_list_contents(self) -> list:
        """Parse list contents until closing brace."""
        result = []

        while True:
            self.skip_whitespace()

            if self.pos >= self.length or self.text[self.pos] == '}':
                if self.pos < self.length:
                    self.pos += 1
                break

            value = self.parse_value()
            result.append(value)

        return result

    def parse(self) -> dict:
        """Parse the entire text as a dictionary."""
        return self.parse_dict_contents()


def parse_pdx(text: str) -> dict:
    """Parse PDX script format text into a Python dictionary."""
    parser = PDXParser(text)
    return parser.parse()


def extract_section(filepath: str, section_name: str) -> str:
    """Extract a specific top-level section from a large file efficiently."""
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        in_section = False
        depth = 0
        section_lines = []

        for line in f:
            if not in_section:
                # Look for section start
                if line.strip().startswith(f'{section_name}='):
                    in_section = True
                    section_lines.append(line)
                    depth = line.count('{') - line.count('}')
            else:
                section_lines.append(line)
                depth += line.count('{') - line.count('}')

                if depth <= 0:
                    break

        return ''.join(section_lines)


def find_country_by_tag(filepath: str, tag: str) -> dict | None:
    """Find a country entry by its tag efficiently."""
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        in_countries = False
        in_country = False
        depth = 0
        country_lines = []
        found_tag = False

        for line in f:
            if not in_countries:
                if line.strip().startswith('countries='):
                    in_countries = True
                continue

            if not in_country:
                # Look for country_name="TAG"
                if f'country_name="{tag}"' in line:
                    # Found it - need to backtrack to find the start of this country block
                    # We'll re-scan to get the full block
                    found_tag = True
                    break

        if not found_tag:
            return None

        # Now re-scan to extract the full country block
        f.seek(0)
        in_countries = False
        collecting = False
        depth = 0
        country_lines = []

        for line in f:
            if not in_countries:
                if line.strip().startswith('countries='):
                    in_countries = True
                continue

            if not collecting:
                if f'country_name="{tag}"' in line:
                    collecting = True
                    # Find the opening brace for this country
                    # Go back a bit in the line buffer
                    country_lines.append(line)
                    depth = line.count('{') - line.count('}')
            else:
                country_lines.append(line)
                depth += line.count('{') - line.count('}')

                if depth <= 0:
                    break

        if country_lines:
            # Extract just the content after country_name
            text = ''.join(country_lines)
            return parse_pdx(text)

    return None


def stream_countries(filepath: str) -> Iterator[tuple[str, dict]]:
    """Stream through all countries, yielding (tag, data) pairs."""
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        in_countries = False
        in_database = False
        in_country = False
        depth = 0
        country_lines = []
        current_tag = None

        for line in f:
            if not in_countries:
                if line.strip().startswith('countries='):
                    in_countries = True
                continue

            if not in_database:
                if line.strip().startswith('database='):
                    in_database = True
                continue

            if not in_country:
                # Look for a new country entry (number={)
                stripped = line.strip()
                if stripped and stripped[0].isdigit() and '={' in stripped:
                    in_country = True
                    country_lines = [line]
                    depth = line.count('{') - line.count('}')
                    current_tag = None
            else:
                country_lines.append(line)
                depth += line.count('{') - line.count('}')

                # Extract tag if we see it
                if current_tag is None and 'country_name="' in line:
                    match = re.search(r'country_name="(\w+)"', line)
                    if match:
                        current_tag = match.group(1)

                if depth <= 0:
                    # End of country block
                    if current_tag and country_lines:
                        text = ''.join(country_lines)
                        try:
                            data = parse_pdx(text)
                            yield (current_tag, data)
                        except Exception:
                            pass  # Skip malformed entries

                    in_country = False
                    country_lines = []
                    current_tag = None


if __name__ == '__main__':
    # Test with a small sample
    sample = '''
    test={
        name="Hello"
        value=42
        flag=yes
        nested={
            a=1
            b=2
        }
        list={
            1 2 3 4 5
        }
    }
    '''
    result = parse_pdx(sample)
    print(result)
