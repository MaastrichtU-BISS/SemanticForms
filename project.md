# Semantic Forms update for multiple forms in a project

Projects can have multiple phases, and multiple questions which should be addressed per project phase. Hence, we want to update SemanticForms to handle the concept of projects, and for every project address specific CEDAR templates as questionnaires. This means that the configuration defines:

- The phases for every project
- The questionnaire (cedar template) to be answered during the specific phase

In the UI, this means people should be able to create a project (including a project name) for which metadata of the project can be recorded. This can be a cedar template as well.

In the end, I expect ever project to contain:
- A JSON-LD file containing the project metadata
- JSON-LD files containing the results of every cedar template within the project, for every project phase.

This project functionality should be optional. If not configured in config.yaml, it should follow the current default behaviour.

