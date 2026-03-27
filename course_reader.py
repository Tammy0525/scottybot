
import os
import re
from pathlib import Path

class CourseReader:
    def __init__(self, base_path='./course_materials'):
        self.base_path = base_path
        self.cache = {}  # Optional caching for performance

    async def get_content(self, day, section, use_cache=True):
        try:
            # Validate inputs
            if not day or not isinstance(day, int) or day < 1 or day > 10:
                raise ValueError(f"Invalid day: {day}. Must be an integer between 1 and 10.")
            
            if not section or not isinstance(section, str):
                raise ValueError(f"Invalid section: {section}. Must be a non-empty string.")
            
            # Check cache first if enabled
            cache_key = f"day{day}_{section}"
            if use_cache and cache_key in self.cache:
                return self.cache[cache_key]
            
            # File path construction
            file_name = f"day{day}-content.md.txt"
            file_path = os.path.join(self.base_path, file_name)
            
            # Read file content
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Extract the requested section using regex
            section_regex = re.compile(f"[#]{{1,2}}\\s*{section}[\\s\\S]*?(?=[#]{{1,2}}\\s|$)", re.IGNORECASE)
            section_match = section_regex.search(content)
            
            if not section_match:
                print(f'Section "{section}" not found in day {day} content.')
                return None
            
            # Extract content: remove the section header and trim whitespace
            extracted_content = re.sub(f"[#]{{1,2}}\\s*{section}", "", section_match.group(0), flags=re.IGNORECASE).strip()
            
            # Store in cache for future use if enabled
            if use_cache:
                self.cache[cache_key] = extracted_content
            
            return extracted_content

        except FileNotFoundError:
            print(f"Course file for day {day} not found at {file_path}")
            return None
        except Exception as error:
            print(f"Error in CourseReader.get_content({day}, {section}): {error}")
            raise

    async def list_sections(self, day):
        try:
            # Validate day
            if not day or not isinstance(day, int) or day < 1 or day > 10:
                raise ValueError(f"Invalid day: {day}. Must be an integer between 1 and 10.")
            
            # File path construction
            file_name = f"day{day}-content.md.txt"
            file_path = os.path.join(self.base_path, file_name)
            
            # Read file content
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Extract all section headers using regex
            section_regex = re.compile(r'[#]{1,2}\s*(.*?)(?=\n)')
            sections = [match.group(1).strip() for match in section_regex.finditer(content) if match.group(1).strip()]
            
            return sections

        except FileNotFoundError:
            print(f"Course file for day {day} not found at {file_path}")
            return []
        except Exception as error:
            print(f"Error in CourseReader.list_sections({day}): {error}")
            return []

    def clear_cache(self):
        self.cache = {}

    async def get_multiple_sections(self, day, sections):
        result = {}
        for section in sections:
            result[section] = await self.get_content(day, section)
        return result

    async def file_exists(self, day):
        try:
            file_name = f"day{day}-content.md.txt"
            file_path = os.path.join(self.base_path, file_name)
            return os.path.exists(file_path)
        except:
            return False
