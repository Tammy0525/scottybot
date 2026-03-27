import os
import re
from pathlib import Path

VALID_STYLES = {"visual", "auditory", "reading_writing", "kinesthetic"}


class CourseReader:
    def __init__(self, base_path="./course_materials"):
        self.base_path = base_path
        self.adapted_path = os.path.join(base_path, "adapted")
        self.cache = {}

    def _adapted_file(self, day: int, style: str) -> str:
        return os.path.join(self.adapted_path, style, f"day{day}-{style}.md.txt")

    def _base_file(self, day: int) -> str:
        return os.path.join(self.base_path, f"day{day}-content.md.txt")

    def _has_adapted(self, day: int, style: str) -> bool:
        return bool(style and style in VALID_STYLES and os.path.exists(self._adapted_file(day, style)))

    async def get_content(self, day, section, learning_style=None, use_cache=True):
        try:
            if not isinstance(day, int) or day < 1 or day > 10:
                raise ValueError(f"Invalid day: {day}")
            if not section or not isinstance(section, str):
                raise ValueError(f"Invalid section: {section}")

            cache_key = f"day{day}_{section}_{learning_style}"
            if use_cache and cache_key in self.cache:
                return self.cache[cache_key]

            # Choose file: adapted if available, otherwise base
            if self._has_adapted(day, learning_style):
                file_path = self._adapted_file(day, learning_style)
            else:
                file_path = self._base_file(day)

            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            section_regex = re.compile(
                f"[#]{{1,2}}\\s*{re.escape(section)}[\\s\\S]*?(?=[#]{{1,2}}\\s|$)",
                re.IGNORECASE,
            )
            match = section_regex.search(content)
            if not match:
                print(f'Section "{section}" not found in day {day} ({learning_style or "base"}).')
                return None

            extracted = re.sub(
                f"[#]{{1,2}}\\s*{re.escape(section)}", "", match.group(0), flags=re.IGNORECASE
            ).strip()

            if use_cache:
                self.cache[cache_key] = extracted

            return extracted

        except FileNotFoundError:
            print(f"Course file for day {day} not found.")
            return None
        except Exception as e:
            print(f"CourseReader.get_content({day}, {section}): {e}")
            raise

    async def list_sections(self, day):
        try:
            if not isinstance(day, int) or day < 1 or day > 10:
                raise ValueError(f"Invalid day: {day}")
            file_path = self._base_file(day)
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            return [
                m.group(1).strip()
                for m in re.finditer(r"[#]{1,2}\s*(.*?)(?=\n)", content)
                if m.group(1).strip()
            ]
        except FileNotFoundError:
            return []
        except Exception as e:
            print(f"CourseReader.list_sections({day}): {e}")
            return []

    async def get_multiple_sections(self, day, sections, learning_style=None):
        return {s: await self.get_content(day, s, learning_style=learning_style) for s in sections}

    async def file_exists(self, day):
        return os.path.exists(self._base_file(day))

    def adapted_exists(self, day: int, style: str) -> bool:
        return self._has_adapted(day, style)

    def clear_cache(self):
        self.cache = {}
