from core.skills.base import Skill


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        self._skills[skill.id] = skill

    def get(self, skill_id: str) -> Skill | None:
        return self._skills.get(skill_id)

    def list_skills(self) -> list[Skill]:
        return list(self._skills.values())

    def all(self) -> list[Skill]:
        return self.list_skills()


registry = SkillRegistry()
