class PromptNameMapper:
    """
    A utility class to map prompt names to their corresponding file names of the files.
    This allows for a more flexible and maintainable way to retrieve prompts based on names like discipline, role.
    """
    
    @staticmethod
    def get_discipline_prompt_name(discipline_value: str) -> str:
        """
        Retrieve the corresponding key for a given discipline value.
        """
        
        _DISCIPLINE_PROMPT_MAP = {
            "registered_nurse": "registered_nurse",
            "licensed_practical_nurse": "licensed_practical_nurse",
            "physical_therapist": "physical_therapist",
            "physical_therapist_assistant": "physical_therapist_assistant",
            "occupational_therapist": "occupational_therapist",
            "occupational_therapist_assistant": "occupational_therapist_assistant",
            "speech_language_pathologist": "speech_language_pathologist",
            "medical_social_worker": "medical_social_worker",
            "home_health_aide": "home_health_aide"
        }
        
        return _DISCIPLINE_PROMPT_MAP.get(discipline_value, "default_discipline")
